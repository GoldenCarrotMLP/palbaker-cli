import json
import uuid
from utils.uasset_helper import sync_namemap

class BlueprintFeatureManager:
    """
    High-level AST controller for Unreal Engine 5.1 Pal Actor Blueprints.
    Provides safe, index-aware operations to add, remove, and mutate components,
    inherited overrides, CDO action maps, and EventGraph bytecode.
    """

    def __init__(self, data: dict):
        self.data = data
        self.exports = data.setdefault("Exports", [])
        self.imports = data.setdefault("Imports", [])
        self.class_export = self.exports[0] if self.exports else None

    # =========================================================================
    # 0. AST SYNCHRONIZATION HELPERS
    # =========================================================================

    def _append_export(self, export_node: dict) -> int:
        """
        Safely appends an export node to the Blueprint, ensuring that
        DependsMap and Generation counts remain perfectly synchronized.
        Returns the 1-based index of the newly added export.
        """
        self.exports.append(export_node)
        new_idx = len(self.exports)

        # Synchronize DependsMap array size
        depends_map = self.data.setdefault("DependsMap", [])
        while len(depends_map) < len(self.exports):
            depends_map.append([])

        # Synchronize Generation ExportCount
        generations = self.data.get("Generations", [])
        if generations and isinstance(generations, list):
            generations[0]["ExportCount"] = new_idx

        return new_idx

    # =========================================================================
    # 1. IMPORT & SYMBOLIC LINKING SUBSYSTEM
    # =========================================================================

    def find_or_add_import(self, object_name: str, class_name: str, class_package: str = "/Script/Engine", outer_index: int = 0) -> int:
        """
        Finds an existing import matching object_name and outer_index, or appends a new one.
        Returns the negative 1-based import index.
        """
        for idx, imp in enumerate(self.imports):
            if imp.get("ObjectName") == object_name and imp.get("OuterIndex") == outer_index:
                return -(idx + 1)

        new_import = {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": object_name,
            "OuterIndex": outer_index,
            "ClassPackage": class_package,
            "ClassName": class_name,
            "PackageName": None,
            "bImportOptional": False
        }
        self.imports.append(new_import)
        return -len(self.imports)

    def ensure_import_chain(self, package_path: str, class_name: str, class_type: str = "BlueprintGeneratedClass") -> int:
        """
        Resolves or creates the standard two-level package -> class import hierarchy.
        E.g., package '/Game/.../BP_CoopParam_Weapon' -> class 'BP_CoopParam_Weapon_C'.
        """
        clean_pkg = package_path.replace("\\", "/").strip()
        pkg_idx = self.find_or_add_import(clean_pkg, "Package", "/Script/CoreUObject", 0)
        class_idx = self.find_or_add_import(class_name, class_type, "/Script/Engine", pkg_idx)
        return class_idx

    def _build_import_map(self, src_imports: list) -> dict:
        """Recursively builds a translation map matching all source imports to target imports."""
        import_map = {}
        def resolve_src_import(src_idx: int) -> int:
            if src_idx >= 0: return src_idx
            if src_idx in import_map: return import_map[src_idx]

            src_imp = src_imports[-src_idx - 1]
            src_outer = src_imp.get("OuterIndex", 0)
            
            target_outer = resolve_src_import(src_outer) if src_outer < 0 else 0
            
            target_idx = self.find_or_add_import(
                object_name=src_imp.get("ObjectName"),
                class_name=src_imp.get("ClassName"),
                class_package=src_imp.get("ClassPackage"),
                outer_index=target_outer
            )
            import_map[src_idx] = target_idx
            return target_idx

        for i in range(len(src_imports)):
            resolve_src_import(-(i + 1))
            
        return import_map

    def _remap_asset_indices(self, node, import_map: dict, src_uber_idx: int, new_uber_idx: int, src_delegate_idx: int, new_delegate_idx: int):
        """Recursively remaps bytecode property pointers and stack nodes to the new target indices."""
        def get_new_idx(idx):
            if idx < 0:
                return import_map.get(idx, idx)
            elif idx == src_uber_idx:
                return new_uber_idx
            elif idx == src_delegate_idx:
                return new_delegate_idx
            return idx

        if isinstance(node, dict):
            for key in ["ClassIndex", "TemplateIndex", "SuperIndex", "OuterIndex", "PropertyClass", "Struct", "StackNode", "Object"]:
                if key in node and isinstance(node[key], int) and node[key] != 0:
                    node[key] = get_new_idx(node[key])

            if node.get("$type", "").endswith("ObjectPropertyData, UAssetAPI") and "Value" in node and isinstance(node["Value"], int) and node["Value"] != 0:
                node["Value"] = get_new_idx(node["Value"])

            if "ResolvedOwner" in node and isinstance(node["ResolvedOwner"], int) and node["ResolvedOwner"] != 0:
                node["ResolvedOwner"] = get_new_idx(node["ResolvedOwner"])

            for v in node.values():
                self._remap_asset_indices(v, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)

        elif isinstance(node, list):
            for item in node:
                self._remap_asset_indices(item, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)

    # =========================================================================
    # 2. SIMPLE CONSTRUCTION SCRIPT (SCS) & COMPONENT SUBSYSTEM
    # =========================================================================

    def find_scs_export(self) -> tuple[int, dict | None]:
        """Locates the SimpleConstructionScript_0 export and its 1-based index."""
        for idx, exp in enumerate(self.exports):
            if exp.get("ObjectName") == "SimpleConstructionScript_0" or "SimpleConstructionScript" in exp.get("$type", ""):
                return idx + 1, exp
        return 0, None

    def add_component(
        self,
        var_name: str,
        comp_class_package: str,
        comp_class_name: str,
        template_properties: list[dict] | None = None,
        attach_to_name: str | None = None,
        parent_var_name: str = "CharacterMesh0",
        b_is_parent_native: bool = True
    ) -> int:
        """
        Instantiates a new component on the Blueprint:
        1. Declares FObjectProperty on ClassExport.LoadedProperties.
        2. Appends the Component Template export (*_GEN_VARIABLE).
        3. Appends the SCS_Node export.
        4. Registers the SCS_Node in SimpleConstructionScript.AllNodes.
        """
        scs_idx, scs_export = self.find_scs_export()
        if not scs_export:
            raise RuntimeError("Target Blueprint lacks a SimpleConstructionScript_0 export.")

        comp_class_idx = self.ensure_import_chain(comp_class_package, comp_class_name)
        scs_node_class_idx = self.find_or_add_import(
            "SCS_Node", "Class", "/Script/CoreUObject",
            self.find_or_add_import("/Script/Engine", "Package", "/Script/CoreUObject", 0)
        )

        # 1. Add variable declaration to LoadedProperties
        loaded_props = self.class_export.setdefault("LoadedProperties", [])
        if not any(isinstance(p, dict) and p.get("Name") == var_name for p in loaded_props):
            loaded_props.append({
                "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
                "PropertyClass": comp_class_idx,
                "ArrayDim": "TArray",
                "ElementSize": 8,
                "PropertyFlags": "CPF_BlueprintVisible, CPF_InstancedReference, CPF_NonTransactional",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "ObjectProperty",
                "Name": var_name,
                "Flags": "RF_Public, RF_LoadCompleted",
                "MetaDataMap": None
            })

        # 2. Append Component Template Export (*_GEN_VARIABLE)
        template_export_name = f"{var_name}_GEN_VARIABLE"
        template_export = {
            "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
            "Data": template_properties or [],
            "ObjectGuid": None,
            "SerializationControl": "NoExtension",
            "Operation": "None",
            "HasLeadingFourNullBytes": False,
            "ObjectName": template_export_name,
            "OuterIndex": 1,
            "ClassIndex": comp_class_idx,
            "SuperIndex": 0,
            "TemplateIndex": 0,
            "ObjectFlags": "RF_Public, RF_Transactional, RF_ArchetypeObject",
            "SerialSize": 0,
            "SerialOffset": 0,
            "ScriptSerializationStartOffset": 0,
            "ScriptSerializationEndOffset": 0,
            "bForcedExport": False,
            "bNotForClient": False,
            "bNotForServer": False,
            "PackageGuid": "{00000000-0000-0000-0000-000000000000}",
            "IsInheritedInstance": False,
            "PackageFlags": "PKG_None",
            "bNotAlwaysLoadedForEditorGame": False,
            "bIsAsset": False,
            "GeneratePublicHash": False,
            "SerializationBeforeSerializationDependencies": [1],
            "CreateBeforeSerializationDependencies": [],
            "SerializationBeforeCreateDependencies": [],
            "CreateBeforeCreateDependencies": [1],
            "Extras": "AAAAAA=="
        }
        template_idx = self._append_export(template_export)

        # 3. Append SCS_Node Export
        node_export_name = f"SCS_Node_{len(self.exports)}"
        node_guid = "{" + str(uuid.uuid4()).upper() + "}"
        node_data = [
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": "ComponentClass",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": comp_class_idx
            },
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": "ComponentTemplate",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": template_idx
            },
            {
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "Guid",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": "VariableGuid",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Structs.GuidPropertyData, UAssetAPI",
                        "Name": "VariableGuid",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": node_guid
                    }
                ]
            },
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                "Name": "InternalVariableName",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": var_name
            }
        ]

        if attach_to_name:
            node_data.insert(2, {
                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                "Name": "AttachToName",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": attach_to_name
            })
            node_data.insert(3, {
                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                "Name": "ParentComponentOrVariableName",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": parent_var_name
            })
            node_data.insert(4, {
                "$type": "UAssetAPI.PropertyTypes.Objects.BoolPropertyData, UAssetAPI",
                "Name": "bIsParentComponentNative",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": b_is_parent_native
            })

        node_export = {
            "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
            "Data": node_data,
            "ObjectGuid": None,
            "SerializationControl": "NoExtension",
            "Operation": "None",
            "HasLeadingFourNullBytes": False,
            "ObjectName": node_export_name,
            "OuterIndex": scs_idx,
            "ClassIndex": scs_node_class_idx,
            "SuperIndex": 0,
            "TemplateIndex": 0,
            "ObjectFlags": "RF_Transactional",
            "SerialSize": 0,
            "SerialOffset": 0,
            "ScriptSerializationStartOffset": 0,
            "ScriptSerializationEndOffset": 0,
            "bForcedExport": False,
            "bNotForClient": False,
            "bNotForServer": False,
            "PackageGuid": "{00000000-0000-0000-0000-000000000000}",
            "IsInheritedInstance": False,
            "PackageFlags": "PKG_None",
            "bNotAlwaysLoadedForEditorGame": False,
            "bIsAsset": False,
            "GeneratePublicHash": False,
            "SerializationBeforeSerializationDependencies": [],
            "CreateBeforeSerializationDependencies": [template_idx, comp_class_idx],
            "SerializationBeforeCreateDependencies": [],
            "CreateBeforeCreateDependencies": [scs_idx],
            "Extras": ""
        }
        new_node_idx = self._append_export(node_export)

        # 4. Register in SCS.AllNodes
        scs_data = scs_export.get("Data")
        if isinstance(scs_data, list):
            for prop in scs_data:
                if isinstance(prop, dict) and prop.get("Name") == "AllNodes":
                    nodes_arr = prop.setdefault("Value", [])
                    nodes_arr.append({
                        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                        "Name": str(len(nodes_arr)),
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": new_node_idx
                    })
                    break

        sync_namemap(self.data)
        return new_node_idx

    # =========================================================================
    # SADDLE & RIDING SUBSYSTEM
    # =========================================================================

    def add_saddle(
        self,
        ride_position_type: str = "HorseRide",
        attach_socket: str = "PlayerRideMarker",
        relative_rotation: dict | None = None,
        ride_action_class_path: str = "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionRideCall.BP_AIActionRideCall_C"
    ) -> int:
        """
        Gives any Pal the ability to be ridden:
        1. Injects the BP_PalRideMarkerSaddle component and SCS Node.
        2. Configures EPalRidePositionType and pitch/yaw rotation offsets.
        3. Sets AIActionMap Cooperation to BP_AIActionRideCall_C.
        """
        template_props = [
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                "EnumType": "EPalRidePositionType",
                "InnerType": "ByteProperty",
                "Name": "RidePositionType",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": ride_position_type
            }
        ]

        if relative_rotation:
            template_props.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "Rotator",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": "RelativeRotation",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Structs.RotatorPropertyData, UAssetAPI",
                        "Name": "RelativeRotation",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": {
                            "$type": "UAssetAPI.UnrealTypes.FRotator, UAssetAPI",
                            "Pitch": float(relative_rotation.get("Pitch", 90.0)),
                            "Yaw": float(relative_rotation.get("Yaw", 0.0)),
                            "Roll": float(relative_rotation.get("Roll", 0.0))
                        }
                    }
                ]
            })

        node_idx = self.add_component(
            var_name="BP_PalRideMarkerSaddle",
            comp_class_package="/Game/Pal/Blueprint/Component/RideMarker/BP_PalRideMarkerSaddle",
            comp_class_name="BP_PalRideMarkerSaddle_C",
            template_properties=template_props,
            attach_to_name=attach_socket,
            parent_var_name="CharacterMesh0",
            b_is_parent_native=True
        )

        self.set_ai_action("EPalAIActionType::Cooperation", ride_action_class_path)
        sync_namemap(self.data)
        return node_idx

    def remove_saddle(self):
        """Removes the saddle marker component and unbinds ride cooperation."""
        self.remove_component("BP_PalRideMarkerSaddle")
        self.remove_ai_action("EPalAIActionType::Cooperation")
        sync_namemap(self.data)

    def has_saddle(self) -> bool:
        """Returns True if the Pal has a saddle marker component attached."""
        return self.has_component("BP_PalRideMarkerSaddle")

    def remove_component(self, var_name: str):
        """
        Safely unlinks and removes a component without index-shifting:
        1. Removes from LoadedProperties.
        2. Unlinks its SCS_Node from SimpleConstructionScript.AllNodes & RootNodes.
        """
        # 1. Remove from LoadedProperties
        loaded_props = self.class_export.get("LoadedProperties", [])
        if isinstance(loaded_props, list):
            self.class_export["LoadedProperties"] = [
                p for p in loaded_props 
                if not (isinstance(p, dict) and p.get("Name") == var_name)
            ]

        # 2. Find SCS_Node index
        target_node_idx = None
        target_exp = None
        for idx, exp in enumerate(self.exports):
            data_props = exp.get("Data")
            if isinstance(data_props, list):
                for prop in data_props:
                    if isinstance(prop, dict) and prop.get("Name") == "InternalVariableName" and prop.get("Value") == var_name:
                        target_node_idx = idx + 1
                        target_exp = exp
                        break
            if target_node_idx:
                break

        # 3. Unlink from SCS and rename variable to make it fully inert
        if target_node_idx:
            if target_exp and isinstance(target_exp.get("Data"), list):
                for prop in target_exp["Data"]:
                    if isinstance(prop, dict) and prop.get("Name") == "InternalVariableName":
                        prop["Value"] = f"{var_name}_REMOVED"
                        
            _, scs_export = self.find_scs_export()
            if scs_export and isinstance(scs_export.get("Data"), list):
                for prop in scs_export["Data"]:
                    if isinstance(prop, dict) and prop.get("Name") in ["AllNodes", "RootNodes"] and isinstance(prop.get("Value"), list):
                        prop["Value"] = [
                            n for n in prop["Value"] 
                            if not (isinstance(n, dict) and n.get("Value") == target_node_idx)
                        ]

        sync_namemap(self.data)

    def has_component(self, var_name: str) -> bool:
        """Returns True if the component exists in LoadedProperties or is actively linked in SCS."""
        if self.class_export and isinstance(self.class_export.get("LoadedProperties"), list):
            for p in self.class_export["LoadedProperties"]:
                if isinstance(p, dict) and p.get("Name") == var_name:
                    return True
                    
        _, scs_export = self.find_scs_export()
        if scs_export and isinstance(scs_export.get("Data"), list):
            active_node_indices = []
            for prop in scs_export["Data"]:
                if isinstance(prop, dict) and prop.get("Name") in ["AllNodes", "RootNodes"] and isinstance(prop.get("Value"), list):
                    for n in prop["Value"]:
                        if isinstance(n, dict) and isinstance(n.get("Value"), int):
                            active_node_indices.append(n["Value"])
                            
            for idx in active_node_indices:
                if 1 <= idx <= len(self.exports):
                    exp = self.exports[idx - 1]
                    if isinstance(exp.get("Data"), list):
                        for p in exp["Data"]:
                            if isinstance(p, dict) and p.get("Name") == "InternalVariableName" and p.get("Value") == var_name:
                                return True
        return False

    # =========================================================================
    # 3. INHERITABLE COMPONENT HANDLER (ICH) SUBSYSTEM
    # =========================================================================

    def find_ich_export(self) -> tuple[int, dict | None]:
        """Locates the InheritableComponentHandler export and its 1-based index."""
        for idx, exp in enumerate(self.exports):
            if exp.get("ObjectName") == "InheritableComponentHandler":
                return idx + 1, exp
        return 0, None

    def set_partner_funnel_params(self, funnel_character_class: str, funnel_controller_class: str, funnel_waza_id: str):
        """
        Injects or updates Funnel parameters in InheritableComponentHandler.Records[PalPartnerSkillParameter].
        """
        _, ich_export = self.find_ich_export()
        if not ich_export or not isinstance(ich_export.get("Data"), list):
            return

        funnel_char_idx = self.ensure_import_chain(funnel_character_class.rsplit(".", 1)[0], funnel_character_class.split(".")[-1])
        funnel_ctrl_idx = self.ensure_import_chain(funnel_controller_class.rsplit(".", 1)[0], funnel_controller_class.split(".")[-1])

        records_prop = next((p for p in ich_export["Data"] if isinstance(p, dict) and p.get("Name") == "Records"), None)
        if not records_prop or not isinstance(records_prop.get("Value"), list):
            return

        target_template_idx = None
        for rec in records_prop["Value"]:
            if not isinstance(rec, dict): continue
            comp_key = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentKey"), None)
            if comp_key and isinstance(comp_key.get("Value"), list):
                var_prop = next((p for p in comp_key["Value"] if isinstance(p, dict) and p.get("Name") == "SCSVariableName"), None)
                if var_prop and var_prop.get("Value") == "PalPartnerSkillParameter":
                    tmpl_prop = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentTemplate"), None)
                    if tmpl_prop:
                        target_template_idx = tmpl_prop.get("Value")
                        break

        if target_template_idx and 1 <= target_template_idx <= len(self.exports):
            tmpl_export = self.exports[target_template_idx - 1]
            tmpl_data = tmpl_export.get("Data")
            if not isinstance(tmpl_data, list):
                tmpl_data = []
                tmpl_export["Data"] = tmpl_data

            tmpl_export["Data"] = [
                p for p in tmpl_data
                if isinstance(p, dict) and p.get("Name") not in ["FunnelCharacterClass", "FunnelControllerClass", "FunnelAttackWazaID"]
            ]
            
            tmpl_export["Data"].extend([
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": "FunnelCharacterClass",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": funnel_char_idx
                },
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": "FunnelControllerClass",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": funnel_ctrl_idx
                },
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                    "EnumType": "EPalWazaID",
                    "InnerType": "UInt16Property",
                    "Name": "FunnelAttackWazaID",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": funnel_waza_id
                }
            ])

        sync_namemap(self.data)

    # =========================================================================
    # 4. CDO & STATIC CHARACTER PARAMETER SUBSYSTEM
    # =========================================================================

    def find_static_char_param_export(self) -> dict | None:
        """Locates the StaticCharacterParameterComponent export."""
        for exp in self.exports:
            if exp.get("ObjectName") == "StaticCharacterParameterComponent":
                return exp
        return None

    def set_ai_action(self, action_type_enum: str, action_class_path: str):
        """Sets or updates an action mapping in StaticCharacterParameterComponent.AIActionMap."""
        comp = self.find_static_char_param_export()
        if not comp:
            return

        action_class_idx = self.ensure_import_chain(action_class_path.rsplit(".", 1)[0], action_class_path.split(".")[-1])

        comp_data = comp.get("Data")
        if not isinstance(comp_data, list):
            comp_data = []
            comp["Data"] = comp_data

        ai_map_prop = next((p for p in comp_data if isinstance(p, dict) and p.get("Name") == "AIActionMap"), None)
        if not ai_map_prop:
            ai_map_prop = {
                "$type": "UAssetAPI.PropertyTypes.Objects.MapPropertyData, UAssetAPI",
                "Name": "AIActionMap",
                "Value": [],
                "KeysToRemove": []
            }
            comp_data.append(ai_map_prop)

        map_val = ai_map_prop.setdefault("Value", [])
        updated = False
        for entry in map_val:
            if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[0], dict) and entry[0].get("Value") == action_type_enum:
                if isinstance(entry[1], dict):
                    entry[1]["Value"] = action_class_idx
                    updated = True
                    break

        if not updated:
            map_val.append([
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                    "EnumType": None,
                    "InnerType": None,
                    "Name": "AIActionMap",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": action_type_enum
                },
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": "AIActionMap",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": action_class_idx
                }
            ])

        sync_namemap(self.data)

    def remove_ai_action(self, action_type_enum: str):
        """Removes an action mapping from StaticCharacterParameterComponent.AIActionMap."""
        comp = self.find_static_char_param_export()
        if not comp or not isinstance(comp.get("Data"), list):
            return
        ai_map_prop = next((p for p in comp["Data"] if isinstance(p, dict) and p.get("Name") == "AIActionMap"), None)
        if ai_map_prop and isinstance(ai_map_prop.get("Value"), list):
            ai_map_prop["Value"] = [
                e for e in ai_map_prop["Value"]
                if not (isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and e[0].get("Value") == action_type_enum)
            ]
        sync_namemap(self.data)

    def set_waza_declaration(self, waza_id_enum: str, action_class_package: str, action_class_name: str):
        """Sets or updates WazaActionDeclarationMap (e.g. Unique_SheepBall_Roll)."""
        comp = self.find_static_char_param_export()
        if not comp:
            return

        comp_data = comp.get("Data")
        if not isinstance(comp_data, list):
            comp_data = []
            comp["Data"] = comp_data

        waza_prop = next((p for p in comp_data if isinstance(p, dict) and p.get("Name") == "WazaActionDeclarationMap"), None)
        if not waza_prop:
            waza_prop = {
                "$type": "UAssetAPI.PropertyTypes.Objects.MapPropertyData, UAssetAPI",
                "Name": "WazaActionDeclarationMap",
                "Value": [],
                "KeysToRemove": []
            }
            comp_data.append(waza_prop)

        map_val = waza_prop.setdefault("Value", [])
        map_val.append([
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                "EnumType": None,
                "InnerType": None,
                "Name": "WazaActionDeclarationMap",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": waza_id_enum
            },
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.SoftObjectPropertyData, UAssetAPI",
                "Name": "WazaActionDeclarationMap",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": {
                    "$type": "UAssetAPI.PropertyTypes.Objects.FSoftObjectPath, UAssetAPI",
                    "AssetPath": {
                        "$type": "UAssetAPI.PropertyTypes.Objects.FTopLevelAssetPath, UAssetAPI",
                        "PackageName": action_class_package,
                        "AssetName": action_class_name
                    },
                    "SubPathString": None
                }
            }
        ])
        sync_namemap(self.data)

    # =========================================================================
    # 5. BYTECODE & EVENTGRAPH TRANSFERENCE SUBSYSTEM
    # =========================================================================

    def transfer_uber_graph(self, src_data: dict, target_class_name: str):
        """
        Transfers Ubergraph functions, bytecode, and delegate bindings from a source Blueprint:
        1. Copies FunctionExports (ExecuteUbergraph and delegate signatures) and remaps references.
        2. Copies ComponentDelegateBinding export.
        3. Updates ClassExport (FuncMap, Children, UberGraphFunction, DynamicBindingObjects).
        4. Injects UberGraphFrame into LoadedProperties.
        """
        src_exports = src_data.get("Exports", [])
        src_imports = src_data.get("Imports", [])

        uber_func_src = next((e for e in src_exports if "ExecuteUbergraph" in str(e.get("ObjectName", ""))), None)
        delegate_func_src = next((e for e in src_exports if "BndEvt__" in str(e.get("ObjectName", ""))), None)
        binding_src = next((e for e in src_exports if e.get("ObjectName") == "ComponentDelegateBinding_0"), None)

        if not uber_func_src or not delegate_func_src:
            return
            
        import_map = self._build_import_map(src_imports)
        
        src_uber_idx = src_exports.index(uber_func_src) + 1
        src_delegate_idx = src_exports.index(delegate_func_src) + 1

        # 1. Ensure UberGraphFrame property exists in target LoadedProperties
        loaded_props = self.class_export.setdefault("LoadedProperties", [])
        if not any(isinstance(p, dict) and p.get("Name") == "UberGraphFrame" for p in loaded_props):
            coreuobj_pkg = self.find_or_add_import("/Script/CoreUObject", "Package", "/Script/CoreUObject", 0)
            struct_ptr_idx = self.find_or_add_import("PointerToUberGraphFrame", "ScriptStruct", "/Script/CoreUObject", coreuobj_pkg)
            loaded_props.insert(0, {
                "$type": "UAssetAPI.FieldTypes.FStructProperty, UAssetAPI",
                "Struct": struct_ptr_idx,
                "ArrayDim": "TArray",
                "ElementSize": 16,
                "PropertyFlags": "CPF_Transient, CPF_DuplicateTransient",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "StructProperty",
                "Name": "UberGraphFrame",
                "Flags": "RF_Public, RF_LoadCompleted",
                "MetaDataMap": None
            })

        new_delegate_func_name = f"BndEvt__{target_class_name}_PalPartnerSkillParameter_K2Node_ComponentBoundEvent_2_OnStop__DelegateSignature"
        new_uber_func_name = f"ExecuteUbergraph_{target_class_name}"

        # Resolve clean function and binding class imports in target
        coreuobj_pkg = self.find_or_add_import("/Script/CoreUObject", "Package", "/Script/CoreUObject", 0)
        func_class_idx = self.find_or_add_import("Function", "Class", "/Script/CoreUObject", coreuobj_pkg)
        func_default_idx = self.find_or_add_import("Default__Function", "Function", "/Script/CoreUObject", coreuobj_pkg)

        engine_pkg = self.find_or_add_import("/Script/Engine", "Package", "/Script/CoreUObject", 0)
        binding_class_idx = self.find_or_add_import("ComponentDelegateBinding", "Class", "/Script/CoreUObject", engine_pkg)
        binding_default_idx = self.find_or_add_import("Default__ComponentDelegateBinding", "ComponentDelegateBinding", "/Script/Engine", engine_pkg)

        # 2. Clone and append Delegate Binding export with clean dependencies
        binding_idx = None
        if binding_src:
            cloned_binding = json.loads(json.dumps(binding_src))
            self._remap_asset_indices(cloned_binding, import_map, src_uber_idx, -999, src_delegate_idx, -999)
            cloned_binding["OuterIndex"] = 1
            cloned_binding["ClassIndex"] = binding_class_idx
            cloned_binding["TemplateIndex"] = binding_default_idx
            cloned_binding["SerializationBeforeSerializationDependencies"] = []
            cloned_binding["CreateBeforeSerializationDependencies"] = []
            cloned_binding["SerializationBeforeCreateDependencies"] = [binding_class_idx, binding_default_idx]
            cloned_binding["CreateBeforeCreateDependencies"] = [1]
            
            binding_data = cloned_binding.get("Data")
            if isinstance(binding_data, list):
                for prop in binding_data:
                    if isinstance(prop, dict) and isinstance(prop.get("Value"), list):
                        for b_val in prop["Value"]:
                            if isinstance(b_val, dict) and isinstance(b_val.get("Value"), list):
                                for inner_p in b_val["Value"]:
                                    if isinstance(inner_p, dict) and inner_p.get("Name") == "FunctionNameToBind":
                                        inner_p["Value"] = new_delegate_func_name
            binding_idx = self._append_export(cloned_binding)

        # 3. Clone and append Ubergraph Function export with clean dependencies
        cloned_uber = json.loads(json.dumps(uber_func_src))
        cloned_uber["ObjectName"] = new_uber_func_name
        cloned_uber["OuterIndex"] = 1
        cloned_uber["ClassIndex"] = func_class_idx
        cloned_uber["TemplateIndex"] = func_default_idx
        cloned_uber["SerializationBeforeSerializationDependencies"] = []
        cloned_uber["CreateBeforeSerializationDependencies"] = []
        cloned_uber["SerializationBeforeCreateDependencies"] = []
        cloned_uber["CreateBeforeCreateDependencies"] = [1]
        new_uber_idx = self._append_export(cloned_uber)
        
        # 4. Clone and append Delegate Signature Function export with clean dependencies
        cloned_delegate = json.loads(json.dumps(delegate_func_src))
        cloned_delegate["ObjectName"] = new_delegate_func_name
        cloned_delegate["OuterIndex"] = 1
        cloned_delegate["ClassIndex"] = func_class_idx
        cloned_delegate["TemplateIndex"] = func_default_idx
        cloned_delegate["SerializationBeforeSerializationDependencies"] = []
        cloned_delegate["CreateBeforeSerializationDependencies"] = [new_uber_idx]
        cloned_delegate["SerializationBeforeCreateDependencies"] = []
        cloned_delegate["CreateBeforeCreateDependencies"] = [1]
        new_delegate_idx = self._append_export(cloned_delegate)
        
        # Remap bytecode internals now that target indices are finalized
        self._remap_asset_indices(cloned_uber, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)
        self._remap_asset_indices(cloned_delegate, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)

        # 5. Link in ClassExport
        func_map = self.class_export.setdefault("FuncMap", [])
        func_map.append([new_uber_func_name, new_uber_idx])
        func_map.append([new_delegate_func_name, new_delegate_idx])

        children = self.class_export.setdefault("Children", [])
        if new_delegate_idx not in children:
            children.append(new_delegate_idx)
        if new_uber_idx not in children:
            children.append(new_uber_idx)

        class_data = self.class_export.setdefault("Data", [])
        
        uber_prop = next((p for p in class_data if isinstance(p, dict) and p.get("Name") == "UberGraphFunction"), None)
        if uber_prop:
            uber_prop["Value"] = new_uber_idx
        else:
            class_data.append({
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": "UberGraphFunction",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": new_uber_idx
            })

        if binding_idx:
            dyn_prop = next((p for p in class_data if isinstance(p, dict) and p.get("Name") == "DynamicBindingObjects"), None)
            if dyn_prop and isinstance(dyn_prop.get("Value"), list):
                dyn_prop["Value"].append({
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": str(len(dyn_prop["Value"])),
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": binding_idx
                })
            else:
                class_data.append({
                    "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                    "ArrayType": "ObjectProperty",
                    "Name": "DynamicBindingObjects",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                            "Name": "0",
                            "ArrayIndex": 0,
                            "PropertyGuid": None,
                            "IsZero": False,
                            "PropertyTagFlags": "None",
                            "PropertyTypeName": None,
                            "PropertyTagExtensions": "NoExtension",
                            "Value": binding_idx
                        }
                    ]
                })

        sync_namemap(self.data)