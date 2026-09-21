# utils/blueprint_patcher/build_variants.py
import os
import re
import json
import subprocess
from utils.extractor.core import extract_game_files

def build_boss_variant(base_json_str: str, template_id: str, pal_id: str, boss_scale: float, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, usmap_path: str = None) -> bool:
    """Builds BP_{pal_id}_BOSS from official template or synthesizes one by scaling CharacterMesh0."""
    log(f"  [Action: Variant] Generating Alpha Boss blueprint: BP_{pal_id}_BOSS...", "standard")
    boss_candidates = [
        f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}_BOSS.uasset",
        f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}_MiddleBoss.uasset"
    ]
    
    from utils.uasset_helper import decompile_uasset, compile_uasset, sync_namemap

    for cand in boss_candidates:
        success, _ = extract_game_files(settings, [cand, cand.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
        cand_disk = os.path.join(temp_dir, cand)
        if success and os.path.exists(cand_disk):
            temp_boss_json = os.path.join(temp_dir, "boss_blueprint.json")
            decompile_uasset(uasset_gui, cand_disk, temp_boss_json, usmap_path)
            
            with open(temp_boss_json, "r", encoding="utf-8") as f:
                boss_str = f.read()

            cand_name = os.path.splitext(os.path.basename(cand))[0]
            boss_str = boss_str.replace(cand, f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{pal_id}/BP_{pal_id}_BOSS.uasset")
            boss_str = boss_str.replace(f"/PalActorBP/{template_id}/{cand_name}", f"/PalActorBP/{pal_id}/BP_{pal_id}_BOSS")
            boss_str = boss_str.replace(f"/PalActorBP/{template_id}/BP_{template_id}", f"/PalActorBP/{pal_id}/BP_{pal_id}")
            boss_str = boss_str.replace(f"SK_{template_id}", f"SK_{pal_id}")
            boss_str = boss_str.replace(f"PA_{template_id}", f"PA_{pal_id}")

            boss_str = re.sub(rf"Default__{cand_name}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_BOSS_C", boss_str)
            boss_str = re.sub(rf"Default__{cand_name}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_BOSS", boss_str)
            boss_str = re.sub(rf"Default__BP_{template_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_C", boss_str)
            boss_str = re.sub(rf"(?<![a-zA-Z0-9_]){cand_name}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_BOSS_C", boss_str)
            boss_str = re.sub(rf"(?<![a-zA-Z0-9_]){cand_name}(?![a-zA-Z0-9_])", f"BP_{pal_id}_BOSS", boss_str)
            boss_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{template_id}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_C", boss_str)

            try:
                boss_data = json.loads(boss_str)
                sync_namemap(boss_data)
                with open(temp_boss_json, "w", encoding="utf-8") as f:
                    json.dump(boss_data, f, indent=4)
            except Exception:
                with open(temp_boss_json, "w", encoding="utf-8") as f:
                    f.write(boss_str)

            dest_boss_uasset = os.path.join(cooked_dir, f"BP_{pal_id}_BOSS.uasset")
            compile_uasset(uasset_gui, temp_boss_json, dest_boss_uasset, usmap_path)
            log(f"  ✓ Compiled official Alpha Boss blueprint: BP_{pal_id}_BOSS.uasset", "success")
            return True

    # Fallback: Synthesize from base blueprint
    temp_synth_json = os.path.join(temp_dir, "boss_synth.json")
    synth_str = base_json_str
    synth_str = re.sub(rf"Default__BP_{pal_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_BOSS_C", synth_str)
    synth_str = re.sub(rf"Default__BP_{pal_id}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_BOSS", synth_str)
    synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_BOSS_C", synth_str)
    synth_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{pal_id}(?![a-zA-Z0-9_])", f"BP_{pal_id}_BOSS", synth_str)

    try:
        synth_data = json.loads(synth_str)
        synth_data["IsUnversioned"] = False
        flags_str = synth_data.get("PackageFlags", "")
        if "PKG_UnversionedProperties" in flags_str:
            flags_list = [f.strip() for f in flags_str.split(",")]
            flags_list = [f for f in flags_list if f != "PKG_UnversionedProperties"]
            synth_data["PackageFlags"] = ", ".join(flags_list)

        for exp in synth_data.get("Exports", []):
            if exp.get("ObjectName") == "CharacterMesh0":
                props = exp.setdefault("Properties", {})
                
                # Check for NormalExport structured arrays vs RawExport dicts dynamically
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
                else:
                    props["RelativeScale3D"] = {"X": boss_scale, "Y": boss_scale, "Z": boss_scale}
                    
        sync_namemap(synth_data)
        with open(temp_synth_json, "w", encoding="utf-8") as f:
            json.dump(synth_data, f, indent=4)
    except Exception:
        with open(temp_synth_json, "w", encoding="utf-8") as f:
            f.write(synth_str)

    dest_boss_uasset = os.path.join(cooked_dir, f"BP_{pal_id}_BOSS.uasset")
    compile_uasset(uasset_gui, temp_synth_json, dest_boss_uasset, usmap_path)
    log(f"  ✓ Synthesized Alpha Boss blueprint: BP_{pal_id}_BOSS.uasset", "success")
    return True

def build_predator_variant(template_id: str, pal_id: str, generate_boss: bool, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, usmap_path: str = None) -> bool:
    """Builds BP_{pal_id}_PREDATOR by retargeting template or the universal Niagara Predator template."""
    log(f"  [Action: Variant] Generating Rampaging Predator blueprint: BP_{pal_id}_PREDATOR...", "standard")
    pred_candidates = [
        f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}_BOSS_Predator.uasset",
        f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}_Predator.uasset"
    ]
    
    from utils.uasset_helper import decompile_uasset, compile_uasset, sync_namemap

    for cand in pred_candidates:
        success, _ = extract_game_files(settings, [cand, cand.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
        cand_disk = os.path.join(temp_dir, cand)
        if success and os.path.exists(cand_disk):
            temp_pred_json = os.path.join(temp_dir, "pred_blueprint.json")
            decompile_uasset(uasset_gui, cand_disk, temp_pred_json, usmap_path)
            
            with open(temp_pred_json, "r", encoding="utf-8") as f:
                pred_str = f.read()

            cand_name = os.path.splitext(os.path.basename(cand))[0]
            pred_str = pred_str.replace(cand, f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{pal_id}/BP_{pal_id}_PREDATOR.uasset")
            pred_str = pred_str.replace(f"/PalActorBP/{template_id}/{cand_name}", f"/PalActorBP/{pal_id}/BP_{pal_id}_PREDATOR")
            pred_str = pred_str.replace(f"/PalActorBP/{template_id}/BP_{template_id}", f"/PalActorBP/{pal_id}/BP_{pal_id}")
            pred_str = pred_str.replace(f"SK_{template_id}", f"SK_{pal_id}")
            pred_str = pred_str.replace(f"PA_{template_id}", f"PA_{pal_id}")

            pred_str = re.sub(rf"Default__{cand_name}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_PREDATOR_C", pred_str)
            pred_str = re.sub(rf"Default__{cand_name}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_PREDATOR", pred_str)
            pred_str = re.sub(rf"(?<![a-zA-Z0-9_]){cand_name}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_PREDATOR_C", pred_str)
            pred_str = re.sub(rf"(?<![a-zA-Z0-9_]){cand_name}(?![a-zA-Z0-9_])", f"BP_{pal_id}_PREDATOR", pred_str)
            pred_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{template_id}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_C", pred_str)

            try:
                pred_data = json.loads(pred_str)
                sync_namemap(pred_data)
                with open(temp_pred_json, "w", encoding="utf-8") as f:
                    json.dump(pred_data, f, indent=4)
            except Exception:
                with open(temp_pred_json, "w", encoding="utf-8") as f:
                    f.write(pred_str)

            dest_pred_uasset = os.path.join(cooked_dir, f"BP_{pal_id}_PREDATOR.uasset")
            compile_uasset(uasset_gui, temp_pred_json, dest_pred_uasset, usmap_path)
            log(f"  ✓ Compiled official Predator blueprint: BP_{pal_id}_PREDATOR.uasset", "success")
            return True

    # Fallback: Retarget universal Niagara predator template
    univ_rel = "Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/Baphomet/BP_Baphomet_Dark_BOSS_Predator.uasset"
    univ_exp = "Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/Baphomet/BP_Baphomet_Dark_BOSS_Predator.uexp"
    extract_game_files(settings, [univ_rel, univ_exp], temp_dir, format_type="raw")
    
    univ_disk = os.path.join(temp_dir, univ_rel)
    if os.path.exists(univ_disk):
        temp_univ_json = os.path.join(temp_dir, "universal_pred.json")
        decompile_uasset(uasset_gui, univ_disk, temp_univ_json, usmap_path)
        
        with open(temp_univ_json, "r", encoding="utf-8") as f:
            univ_str = f.read()

        univ_str = univ_str.replace("/PalActorBP/Baphomet/BP_Baphomet_Dark_BOSS_Predator", f"/PalActorBP/{pal_id}/BP_{pal_id}_PREDATOR")
        univ_str = univ_str.replace("/PalActorBP/Baphomet/BP_Baphomet_Dark_BOSS", f"/PalActorBP/{pal_id}/BP_{pal_id}_BOSS" if generate_boss else f"/PalActorBP/{pal_id}/BP_{pal_id}")
        univ_str = re.sub(rf"Default__BP_Baphomet_Dark_BOSS_Predator_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_PREDATOR_C", univ_str)
        univ_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_Baphomet_Dark_BOSS_Predator_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_PREDATOR_C", univ_str)
        univ_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_Baphomet_Dark_BOSS_Predator(?![a-zA-Z0-9_])", f"BP_{pal_id}_PREDATOR", univ_str)
        univ_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_Baphomet_Dark_BOSS_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_BOSS_C" if generate_boss else f"BP_{pal_id}_C", univ_str)
        univ_str = univ_str.replace("SK_Baphomet_Dark", f"SK_{pal_id}")
        univ_str = univ_str.replace("PA_Baphomet", f"PA_{pal_id}")
        univ_str = univ_str.replace("SK_Baphomet_Skeleton", f"SK_{template_id}_Skeleton")

        try:
            univ_data = json.loads(univ_str)
            sync_namemap(univ_data)
            with open(temp_univ_json, "w", encoding="utf-8") as f:
                json.dump(univ_data, f, indent=4)
        except Exception:
            with open(temp_univ_json, "w", encoding="utf-8") as f:
                f.write(univ_str)

        dest_pred_uasset = os.path.join(cooked_dir, f"BP_{pal_id}_PREDATOR.uasset")
        compile_uasset(uasset_gui, temp_univ_json, dest_pred_uasset, usmap_path)
        log(f"  ✓ Compiled Rampaging Predator blueprint: BP_{pal_id}_PREDATOR.uasset", "success")
        return True

    return False