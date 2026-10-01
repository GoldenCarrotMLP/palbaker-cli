# utils/blueprint_patcher/build_variants.py
import os
import re
import json

def build_boss_variant(base_json_str: str, template_id: str, pal_id: str, boss_scale: float, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, usmap_path: str = None) -> bool:
    """Synthesizes BP_{pal_id}_BOSS perfectly from the freshly compiled base blueprint."""
    log(f"  [Action: Variant] Synthesizing Alpha Boss blueprint: BP_{pal_id}_BOSS...", "standard")
    
    temp_synth_json = os.path.join(temp_dir, "boss_synth.json")
    
    # 1. Strip base class strings and promote to BOSS
    synth_str = base_json_str
    synth_str = re.sub(rf"Default__BP_{pal_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_BOSS_C", synth_str)
    synth_str = re.sub(rf"Default__BP_{pal_id}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_BOSS", synth_str)
    synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_BOSS_C", synth_str)
    synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}(?![a-zA-Z0-9_])", f"BP_{pal_id}_BOSS", synth_str)

    try:
        synth_data = json.loads(synth_str)

        # 2. Safely inject the 1.4x Boss Scale into CharacterMesh0
        for exp in synth_data.get("Exports", []):
            if exp.get("ObjectName") == "CharacterMesh0":
                props = exp.get("Data", [])
                if isinstance(props, list):
                    scale_prop = next((p for p in props if p.get("Name") == "RelativeScale3D"), None)
                    if scale_prop:
                        val = scale_prop.get("Value", [{}])[0].get("Value", {})
                        val["X"] = boss_scale
                        val["Y"] = boss_scale
                        val["Z"] = boss_scale
                    else:
                        props.append({
                            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                            "StructType": "Vector",
                            "SerializeNone": True,
                            "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                            "SerializationControl": "NoExtension",
                            "Operation": "None",
                            "Name": "RelativeScale3D",
                            "ArrayIndex": 0,
                            "PropertyGuid": None,
                            "IsZero": False,
                            "PropertyTagFlags": "None",
                            "PropertyTypeName": None,
                            "PropertyTagExtensions": "NoExtension",
                            "Value": [
                                {
                                    "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                                    "Name": "RelativeScale3D",
                                    "ArrayIndex": 0,
                                    "PropertyGuid": None,
                                    "IsZero": False,
                                    "PropertyTagFlags": "None",
                                    "PropertyTypeName": None,
                                    "PropertyTagExtensions": "NoExtension",
                                    "Value": { "X": boss_scale, "Y": boss_scale, "Z": boss_scale }
                                }
                            ]
                        })
                break
                
        from utils.uasset_helper import sync_namemap
        sync_namemap(synth_data)
        with open(temp_synth_json, "w", encoding="utf-8") as f:
            json.dump(synth_data, f, indent=4)
    except Exception:
        with open(temp_synth_json, "w", encoding="utf-8") as f:
            f.write(synth_str)

    dest_boss_uasset = os.path.join(cooked_dir, f"BP_{pal_id}_BOSS.uasset")
    from utils.uasset_helper import compile_uasset
    compile_uasset(uasset_gui, temp_synth_json, dest_boss_uasset, usmap_path)
    log(f"  ✓ Synthesized Alpha Boss blueprint: BP_{pal_id}_BOSS.uasset", "success")
    return True


def build_predator_variant(template_id: str, pal_id: str, generate_boss: bool, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, usmap_path: str = None) -> bool:
    """Synthesizes BP_{pal_id}_PREDATOR perfectly from the freshly compiled base blueprint."""
    log(f"  [Action: Variant] Synthesizing Rampaging Predator blueprint: BP_{pal_id}_PREDATOR...", "standard")
    
    temp_pred_json = os.path.join(temp_dir, "pred_synth.json")
    
    # Read the base json string directly from disk to ensure clean AST separation
    base_json_path = os.path.join(temp_dir, f"BP_{pal_id}.json")
    if os.path.exists(base_json_path):
        with open(base_json_path, "r", encoding="utf-8") as f:
            synth_str = f.read()
    else:
        log(f"  ❌ Cannot synthesize Predator. Base blueprint missing.", "error")
        return False

    synth_str = re.sub(rf"Default__BP_{pal_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_PREDATOR_C", synth_str)
    synth_str = re.sub(rf"Default__BP_{pal_id}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_PREDATOR", synth_str)
    synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_PREDATOR_C", synth_str)
    synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}(?![a-zA-Z0-9_])", f"BP_{pal_id}_PREDATOR", synth_str)

    try:
        synth_data = json.loads(synth_str)

        for exp in synth_data.get("Exports", []):
            if exp.get("ObjectName") == "CharacterMesh0":
                props = exp.get("Data", [])
                if isinstance(props, list):
                    scale_prop = next((p for p in props if p.get("Name") == "RelativeScale3D"), None)
                    if scale_prop:
                        val = scale_prop.get("Value", [{}])[0].get("Value", {})
                        val["X"] = 1.4
                        val["Y"] = 1.4
                        val["Z"] = 1.4
                    else:
                        props.append({
                            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                            "StructType": "Vector",
                            "SerializeNone": True,
                            "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                            "SerializationControl": "NoExtension",
                            "Operation": "None",
                            "Name": "RelativeScale3D",
                            "ArrayIndex": 0,
                            "PropertyGuid": None,
                            "IsZero": False,
                            "PropertyTagFlags": "None",
                            "PropertyTypeName": None,
                            "PropertyTagExtensions": "NoExtension",
                            "Value": [
                                {
                                    "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                                    "Name": "RelativeScale3D",
                                    "ArrayIndex": 0,
                                    "PropertyGuid": None,
                                    "IsZero": False,
                                    "PropertyTagFlags": "None",
                                    "PropertyTypeName": None,
                                    "PropertyTagExtensions": "NoExtension",
                                    "Value": { "X": 1.4, "Y": 1.4, "Z": 1.4 }
                                }
                            ]
                        })
                break
                
        from utils.uasset_helper import sync_namemap
        sync_namemap(synth_data)
        with open(temp_pred_json, "w", encoding="utf-8") as f:
            json.dump(synth_data, f, indent=4)
    except Exception:
        with open(temp_pred_json, "w", encoding="utf-8") as f:
            f.write(synth_str)

    dest_pred_uasset = os.path.join(cooked_dir, f"BP_{pal_id}_PREDATOR.uasset")
    from utils.uasset_helper import compile_uasset
    compile_uasset(uasset_gui, temp_pred_json, dest_pred_uasset, usmap_path)
    log(f"  ✓ Synthesized Rampaging Predator blueprint: BP_{pal_id}_PREDATOR.uasset", "success")
    return True


def build_raid_variant(template_id: str, pal_id: str, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, usmap_path: str = None) -> bool:
    """Synthesizes BP_{pal_id}_RAID from the base blueprint if a template raid variant exists."""
    raid_candidates = [
        f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}_RAID.uasset"
    ]
    
    from utils.extractor.core import extract_game_files
    for cand in raid_candidates:
        success, _ = extract_game_files(settings, [cand, cand.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
        cand_disk = os.path.join(temp_dir, cand)
        if not os.path.exists(cand_disk):
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if f.lower() == f"bp_{template_id.lower()}_raid.uasset":
                        cand_disk = os.path.join(root, f)
                        break
                if cand_disk and os.path.exists(cand_disk):
                    break

        if cand_disk and os.path.exists(cand_disk):
            log(f"  [Action: Variant] Synthesizing Raid Boss blueprint: BP_{pal_id}_RAID...", "standard")
            temp_raid_json = os.path.join(temp_dir, "raid_synth.json")
            
            base_json_path = os.path.join(temp_dir, f"BP_{pal_id}.json")
            if os.path.exists(base_json_path):
                with open(base_json_path, "r", encoding="utf-8") as f:
                    synth_str = f.read()
            else:
                return False

            synth_str = re.sub(rf"Default__BP_{pal_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_RAID_C", synth_str)
            synth_str = re.sub(rf"Default__BP_{pal_id}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_RAID", synth_str)
            synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_RAID_C", synth_str)
            synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}(?![a-zA-Z0-9_])", f"BP_{pal_id}_RAID", synth_str)

            try:
                synth_data = json.loads(synth_str)
                from utils.uasset_helper import sync_namemap
                sync_namemap(synth_data)
                with open(temp_raid_json, "w", encoding="utf-8") as f:
                    json.dump(synth_data, f, indent=4)
            except Exception:
                with open(temp_raid_json, "w", encoding="utf-8") as f:
                    f.write(synth_str)

            dest_raid_uasset = os.path.join(cooked_dir, f"BP_{pal_id}_RAID.uasset")
            from utils.uasset_helper import compile_uasset
            compile_uasset(uasset_gui, temp_raid_json, dest_raid_uasset, usmap_path)
            log(f"  ✓ Synthesized Raid Boss blueprint: BP_{pal_id}_RAID.uasset", "success")
            return True
            
    return False