# utils/blueprint_patcher/feature_manager/cdo.py
from utils.uasset_helper import sync_namemap

class CDOManagerMixin:
    """
    Manages Class Default Object (CDO) parameters: StaticCharacterParameterComponent,
    AIActionMap, and WazaActionDeclarationMap.
    """

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

        comp_deps = comp.setdefault("CreateBeforeSerializationDependencies", [])
        if action_class_idx not in comp_deps:
            comp_deps.append(action_class_idx)

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
            if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[0], dict):
                val_str = str(entry[0].get("Value", ""))
                if val_str == action_type_enum or val_str.endswith(action_type_enum.split("::")[-1]):
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
                    "Value": action_type_enum if "::" in action_type_enum else f"EPalAIActionType::{action_type_enum}"
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

        clean_waza_key = waza_id_enum if "::" in waza_id_enum else f"EPalWazaID::{waza_id_enum}"

        map_val = waza_prop.setdefault("Value", [])
        # In-place deduplication to prevent map collision
        waza_prop["Value"] = [
            e for e in map_val
            if not (isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and e[0].get("Value") == clean_waza_key)
        ]
        map_val = waza_prop["Value"]

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
                "Value": clean_waza_key
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