# utils/blueprint_patcher/feature_manager/ich.py
import uuid
from utils.uasset_helper import sync_namemap

class ICHManagerMixin:
    """
    Manages InheritableComponentHandler (ICH) records, allowing child
    Blueprints to override properties on components inherited from BP_MonsterBase_C.
    """

    def find_ich_export(self) -> tuple[int, dict | None]:
        """Locates the InheritableComponentHandler export and its 1-based index."""
        for idx, exp in enumerate(self.exports):
            if exp.get("ObjectName") == "InheritableComponentHandler":
                return idx + 1, exp
        return 0, None

    def set_partner_funnel_params(
        self,
        funnel_character_class: str,
        funnel_controller_class: str,
        funnel_waza_id: str
    ):
        """
        Injects or updates Funnel parameters in InheritableComponentHandler.Records[PalPartnerSkillParameter].
        If the Pal does not already have an ICH record for PalPartnerSkillParameter, synthesizes one.
        """
        ich_idx, ich_export = self.find_ich_export()
        if not ich_export:
            return

        comp_data = ich_export.get("Data")
        if not isinstance(comp_data, list):
            comp_data = []
            ich_export["Data"] = comp_data

        # 1. Ensure Records array property exists on InheritableComponentHandler
        records_prop = next((p for p in comp_data if isinstance(p, dict) and p.get("Name") == "Records"), None)
        if not records_prop:
            records_prop = {
                "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                "ArrayType": "StructProperty",
                "Name": "Records",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": []
            }
            comp_data.append(records_prop)

        records_val = records_prop.setdefault("Value", [])

        funnel_char_idx = self.ensure_import_chain(funnel_character_class.rsplit(".", 1)[0], funnel_character_class.split(".")[-1])
        funnel_ctrl_idx = self.ensure_import_chain(funnel_controller_class.rsplit(".", 1)[0], funnel_controller_class.split(".")[-1])

        # Strip namespace prefix so UAssetGUI can serialize into uint16 enum map in usmap
        bare_waza_name = funnel_waza_id.split("::")[-1] if "::" in funnel_waza_id else funnel_waza_id

        # 2. Check if PalPartnerSkillParameter record already exists
        target_template_idx = None
        for rec in records_val:
            if not isinstance(rec, dict):
                continue
            comp_key = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentKey"), None)
            if comp_key and isinstance(comp_key.get("Value"), list):
                var_prop = next((p for p in comp_key["Value"] if isinstance(p, dict) and p.get("Name") == "SCSVariableName"), None)
                if var_prop and var_prop.get("Value") == "PalPartnerSkillParameter":
                    tmpl_prop = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentTemplate"), None)
                    if tmpl_prop:
                        target_template_idx = tmpl_prop.get("Value")
                        break

        # 3. Synthesize a brand-new ComponentOverrideRecord and Template Export if missing
        if target_template_idx is None:
            monster_base_class_idx = self.ensure_import_chain(
                "/Game/Pal/Blueprint/Character/Monster/BP_MonsterBase",
                "BP_MonsterBase_C"
            )
            comp_class_idx = self.ensure_import_chain(
                "/Script/Pal",
                "PalPartnerSkillParameterComponent",
                class_type="Class"
            )

            pal_pkg_idx = self.find_or_add_import("/Script/Pal", "Package", "/Script/CoreUObject", 0)

            # The archetype template for an inherited component must be the parent's template from BP_MonsterBase_C
            parent_tmpl_idx = self.find_or_add_import(
                "PalPartnerSkillParameter_GEN_VARIABLE",
                "PalPartnerSkillParameterComponent",
                "/Script/Pal",
                monster_base_class_idx
            )

            template_export_name = "PalPartnerSkillParameter_GEN_VARIABLE"
            tmpl_export = {
                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                "Data": [],
                "ObjectGuid": None,
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "HasLeadingFourNullBytes": False,
                "ObjectName": template_export_name,
                "OuterIndex": 1,
                "ClassIndex": comp_class_idx,
                "SuperIndex": 0,
                "TemplateIndex": parent_tmpl_idx,
                "ObjectFlags": "RF_Public, RF_Transactional, RF_ArchetypeObject, RF_InheritableComponentTemplate",
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
                "SerializationBeforeCreateDependencies": [comp_class_idx, parent_tmpl_idx],
                "CreateBeforeCreateDependencies": [1],
                "Extras": "AAAAAA=="
            }
            target_template_idx = self._append_export(tmpl_export)

            # --- CRITICAL FIX: HARDCODED GUID ---
            # InheritableComponentHandler override records MUST point to the exact GUID 
            # of the parent class's SCS Node. For BP_MonsterBase_C's PalPartnerSkillParameter,
            # the GUID is statically {D3F63977-4633-371F-44BA-068B1594045A}.
            record_guid = "{D3F63977-4633-371F-44BA-068B1594045A}"
            new_record = {
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "ComponentOverrideRecord",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": str(len(records_val)),
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                        "StructType": "ComponentKey",
                        "SerializeNone": True,
                        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                        "SerializationControl": "NoExtension",
                        "Operation": "None",
                        "Name": "ComponentKey",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": [
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                                "Name": "OwnerClass",
                                "ArrayIndex": 0,
                                "PropertyGuid": None,
                                "IsZero": False,
                                "PropertyTagFlags": "None",
                                "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension",
                                "Value": monster_base_class_idx
                            },
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                                "Name": "SCSVariableName",
                                "ArrayIndex": 0,
                                "PropertyGuid": None,
                                "IsZero": False,
                                "PropertyTagFlags": "None",
                                "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension",
                                "Value": "PalPartnerSkillParameter"
                            },
                            {
                                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                                "StructType": "Guid",
                                "SerializeNone": True,
                                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                                "SerializationControl": "NoExtension",
                                "Operation": "None",
                                "Name": "AssociatedGuid",
                                "ArrayIndex": 0,
                                "PropertyGuid": None,
                                "IsZero": False,
                                "PropertyTagFlags": "None",
                                "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension",
                                "Value": [
                                    {
                                        "$type": "UAssetAPI.PropertyTypes.Structs.GuidPropertyData, UAssetAPI",
                                        "Name": "AssociatedGuid",
                                        "ArrayIndex": 0,
                                        "PropertyGuid": None,
                                        "IsZero": False,
                                        "PropertyTagFlags": "None",
                                        "PropertyTypeName": None,
                                        "PropertyTagExtensions": "NoExtension",
                                        "Value": record_guid
                                    }
                                ]
                            }
                        ]
                    },
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
                        "Value": target_template_idx
                    },
                    {
                        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                        "StructType": "BlueprintCookedComponentInstancingData",
                        "SerializeNone": True,
                        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                        "SerializationControl": "NoExtension",
                        "Operation": "None",
                        "Name": "CookedComponentInstancingData",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": [
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                                "ArrayType": "StructProperty",
                                "DummyStruct": {
                                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                                    "StructType": "BlueprintComponentChangedPropertyInfo",
                                    "Name": "ChangedPropertyList",
                                    "Value": []
                                },
                                "Name": "ChangedPropertyList",
                                "ArrayIndex": 0,
                                "PropertyGuid": None,
                                "IsZero": True,
                                "PropertyTagFlags": "None",
                                "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension",
                                "Value": []
                            },
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.BoolPropertyData, UAssetAPI",
                                "Name": "bHasValidCookedData",
                                "ArrayIndex": 0,
                                "PropertyGuid": None,
                                "IsZero": True,
                                "PropertyTagFlags": "None",
                                "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension",
                                "Value": False
                            }
                        ]
                    }
                ]
            }
            records_val.append(new_record)

            # Ensure the newly created template is registered as a serialization dependency
            ich_deps = ich_export.setdefault("CreateBeforeSerializationDependencies", [])
            if target_template_idx not in ich_deps:
                ich_deps.append(target_template_idx)

        # 4. Populate Template Export with the funnel properties
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
                    "Value": bare_waza_name
                }
            ])

        sync_namemap(self.data)

    def get_partner_funnel_params(self) -> dict:
        """
        Parses and returns the currently configured funnel parameters in InheritableComponentHandler.
        Returns: {'FunnelCharacterClass': str, 'FunnelControllerClass': str, 'FunnelAttackWazaID': str}
        """
        _, ich_export = self.find_ich_export()
        if not ich_export or not isinstance(ich_export.get("Data"), list):
            return {}

        records_prop = next((p for p in ich_export["Data"] if isinstance(p, dict) and p.get("Name") == "Records"), None)
        if not records_prop or not isinstance(records_prop.get("Value"), list):
            return {}

        target_template_idx = None
        for rec in records_prop["Value"]:
            if not isinstance(rec, dict):
                continue
            comp_key = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentKey"), None)
            if comp_key and isinstance(comp_key.get("Value"), list):
                var_prop = next((p for p in comp_key["Value"] if isinstance(p, dict) and p.get("Name") == "SCSVariableName"), None)
                if var_prop and var_prop.get("Value") == "PalPartnerSkillParameter":
                    tmpl_prop = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentTemplate"), None)
                    if tmpl_prop:
                        target_template_idx = tmpl_prop.get("Value")
                        break

        if not target_template_idx or not (1 <= target_template_idx <= len(self.exports)):
            return {}

        tmpl_export = self.exports[target_template_idx - 1]
        tmpl_data = tmpl_export.get("Data", [])

        result = {}
        for prop in tmpl_data:
            if isinstance(prop, dict):
                p_name = prop.get("Name")
                if p_name in ["FunnelCharacterClass", "FunnelControllerClass"]:
                    imp_idx = prop.get("Value")
                    if isinstance(imp_idx, int) and imp_idx < 0 and (-imp_idx - 1) < len(self.imports):
                        imp = self.imports[-imp_idx - 1]
                        result[p_name] = f"{imp.get('ObjectName')}"
                elif p_name == "FunnelAttackWazaID":
                    val = prop.get("Value")
                    if isinstance(val, str) and val and not val.startswith("EPalWazaID::"):
                        val = f"EPalWazaID::{val}"
                    result[p_name] = val

        return result

    def clear_partner_funnel(self):
        """Strips funnel parameters from ICH PalPartnerSkillParameter."""
        _, ich_export = self.find_ich_export()
        if not ich_export or not isinstance(ich_export.get("Data"), list):
            return

        records_prop = next((p for p in ich_export["Data"] if isinstance(p, dict) and p.get("Name") == "Records"), None)
        if not records_prop or not isinstance(records_prop.get("Value"), list):
            return

        target_template_idx = None
        for rec in records_prop["Value"]:
            if not isinstance(rec, dict):
                continue
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
            if isinstance(tmpl_data, list):
                tmpl_export["Data"] = [
                    p for p in tmpl_data
                    if isinstance(p, dict) and p.get("Name") not in ["FunnelCharacterClass", "FunnelControllerClass", "FunnelAttackWazaID"]
                ]

        sync_namemap(self.data)