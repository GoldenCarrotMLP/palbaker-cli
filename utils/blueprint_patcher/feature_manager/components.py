# utils/blueprint_patcher/feature_manager/components.py
import uuid
from utils.uasset_helper import sync_namemap

class ComponentManagerMixin:
    """
    Manages SimpleConstructionScript (SCS), component template exports (*_GEN_VARIABLE),
    and class-level variable registrations in LoadedProperties.
    """

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
        template_properties: list[dict] = None,
        attach_to_name: str = None,
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

        # Resolution of TemplateIndex for both Blueprint classes and Native C++ classes
        clean_pkg = comp_class_package.replace("\\", "/").strip()
        pkg_idx = self.find_or_add_import(clean_pkg, "Package", "/Script/CoreUObject", 0)
        template_idx = self.find_or_add_import(
            object_name=f"Default__{comp_class_name}",
            class_name=comp_class_name,
            class_package=clean_pkg,
            outer_index=pkg_idx
        )

        # Prevent duplicate component templates and SCS nodes if component already exists
        if self.has_component(var_name):
            template_idx_val = None
            for exp in self.exports:
                if exp.get("ObjectName") == f"{var_name}_GEN_VARIABLE":
                    if template_properties:
                        exp["Data"] = template_properties
                    template_idx_val = self.exports.index(exp) + 1
                    break

            # Update the existing SCS_Node's AttachToName socket linkage
            if attach_to_name:
                for exp in self.exports:
                    data_props = exp.get("Data")
                    if isinstance(data_props, list):
                        is_target_node = any(
                            isinstance(p, dict) and p.get("Name") == "InternalVariableName" and p.get("Value") == var_name
                            for p in data_props
                        )
                        if is_target_node:
                            attach_prop = next((p for p in data_props if isinstance(p, dict) and p.get("Name") == "AttachToName"), None)
                            if attach_prop:
                                attach_prop["Value"] = attach_to_name
                            else:
                                data_props.insert(2, {
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
                            break

            sync_namemap(self.data)
            return template_idx_val or 1
        # 1. Register in LoadedProperties (matches native UE5 schema)
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

        # Update Class EDL Dependencies to prevent null pointer render crashes
        class_deps = self.class_export.setdefault("CreateBeforeSerializationDependencies", [])
        if comp_class_idx not in class_deps:
            class_deps.append(comp_class_idx)

        serialization_before_create = [comp_class_idx]
        if template_idx < 0:
            serialization_before_create.append(template_idx)

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
            "TemplateIndex": template_idx,
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
            "SerializationBeforeCreateDependencies": serialization_before_create,
            "CreateBeforeCreateDependencies": [1],
            "Extras": "AAAAAA=="
        }
        template_idx_val = self._append_export(template_export)

        # 3. Append SCS_Node Export
        node_export_name = f"SCS_Node_{len(self.exports)}"
        node_guid = "{" + str(uuid.uuid4()).upper() + "}"
        default_scs_node_idx = self.find_or_add_import(
            "Default__SCS_Node", "SCS_Node", "/Script/Engine",
            self.find_or_add_import("/Script/Engine", "Package", "/Script/CoreUObject", 0)
        )

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
                "Value": template_idx_val
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
            "TemplateIndex": default_scs_node_idx,
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
            "CreateBeforeSerializationDependencies": [template_idx_val, comp_class_idx],
            "SerializationBeforeCreateDependencies": [scs_node_class_idx, default_scs_node_idx],
            "CreateBeforeCreateDependencies": [scs_idx],
            "Extras": ""
        }
        new_node_idx = self._append_export(node_export)

        # 4. Register in SCS.AllNodes (and RootNodes if parent is native)
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
                elif isinstance(prop, dict) and prop.get("Name") == "RootNodes" and b_is_parent_native:
                    root_arr = prop.setdefault("Value", [])
                    root_arr.append({
                        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                        "Name": str(len(root_arr)),
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": new_node_idx
                    })

        scs_deps = scs_export.setdefault("CreateBeforeSerializationDependencies", [])
        if new_node_idx not in scs_deps:
            scs_deps.append(new_node_idx)

        sync_namemap(self.data)
        return new_node_idx

    def remove_component(self, var_name: str):
        """
        Safely unlinks and removes a component:
        1. Transmutes its FObjectProperty to SceneComponent in LoadedProperties.
        2. Unlinks its SCS_Node from SimpleConstructionScript.AllNodes & RootNodes.
        3. Transmutes the Template Export and SCS_Node to SceneComponent and severs class dependencies.
        """
        engine_pkg_idx = self.find_or_add_import("/Script/Engine", "Package", "/Script/CoreUObject", 0)
        scene_comp_class_idx = self.find_or_add_import("SceneComponent", "Class", "/Script/CoreUObject", engine_pkg_idx)
        scene_comp_template_idx = self.find_or_add_import("Default__SceneComponent", "SceneComponent", "/Script/Engine", engine_pkg_idx)

        # 1. Transmute FObjectProperty to SceneComponent in LoadedProperties
        loaded_props = self.class_export.get("LoadedProperties", [])
        if isinstance(loaded_props, list):
            for p in loaded_props:
                if isinstance(p, dict) and p.get("Name") == var_name:
                    p["PropertyClass"] = scene_comp_class_idx

        # 2. Find SCS_Node index and template export
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

        # 3. Unlink from SCS and transmute variable to make it fully inert
        if target_node_idx:
            old_class_idx = None
            for exp in self.exports:
                if exp.get("ObjectName") == f"{var_name}_GEN_VARIABLE":
                    old_class_idx = exp.get("ClassIndex")
                    exp["Data"] = []
                    exp["CreateBeforeSerializationDependencies"] = []
                    exp["ClassIndex"] = scene_comp_class_idx
                    exp["TemplateIndex"] = scene_comp_template_idx
                    exp["SerializationBeforeCreateDependencies"] = [scene_comp_class_idx, scene_comp_template_idx]

            # Clean ClassExport dependencies on the old component class
            cb_deps = self.class_export.get("CreateBeforeSerializationDependencies", [])
            if isinstance(cb_deps, list) and old_class_idx and old_class_idx in cb_deps:
                self.class_export["CreateBeforeSerializationDependencies"] = [
                    scene_comp_class_idx if d == old_class_idx else d for d in cb_deps
                ]

            if target_exp and isinstance(target_exp.get("Data"), list):
                for prop in target_exp["Data"]:
                    if isinstance(prop, dict) and prop.get("Name") == "InternalVariableName":
                        prop["Value"] = f"{var_name}_REMOVED"
                    elif isinstance(prop, dict) and prop.get("Name") == "ComponentClass":
                        prop["Value"] = scene_comp_class_idx
                target_exp["CreateBeforeSerializationDependencies"] = [
                    scene_comp_class_idx if d == old_class_idx else d
                    for d in target_exp.get("CreateBeforeSerializationDependencies", [])
                ]

            _, scs_export = self.find_scs_export()
            if scs_export and isinstance(scs_export.get("Data"), list):
                for prop in scs_export["Data"]:
                    if isinstance(prop, dict) and prop.get("Name") in ["AllNodes", "RootNodes"] and isinstance(prop.get("Value"), list):
                        new_list = [
                            n for n in prop["Value"] 
                            if not (isinstance(n, dict) and n.get("Value") == target_node_idx)
                        ]
                        for i, n in enumerate(new_list):
                            if isinstance(n, dict):
                                n["Name"] = str(i)
                        prop["Value"] = new_list

                scs_deps = scs_export.get("CreateBeforeSerializationDependencies", [])
                if isinstance(scs_deps, list) and target_node_idx in scs_deps:
                    scs_export["CreateBeforeSerializationDependencies"] = [idx for idx in scs_deps if idx != target_node_idx]

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