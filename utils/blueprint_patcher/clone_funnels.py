# utils/blueprint_patcher/clone_funnels.py
import os
import json
import subprocess
from utils.extractor.core import extract_game_files

def clone_funnel_character(json_data: dict, json_str: str, template_id: str, pal_id: str, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, pal_data: dict = None, usmap_path: str = None) -> tuple[dict, str]:
    if pal_data is None:
        pal_data = {}

    funnel = pal_data.get("Features", {}).get("Funnel", {})
    has_funnel = funnel.get("Enabled", pal_data.get("HasFunnel", False))
    if not has_funnel:
        return json_data, json_str

    log(f"  [Action: Funnel] Compiling standalone Funnel Character BP_FunnelCharacter_{pal_id}...", "standard")

    custom_waza = funnel.get("CustomWazaID", pal_data.get("FunnelWazaID", "Funnel_DreamDemon"))
    funnel_preset = funnel.get("Preset", "DreamDemon")
    targeting_action = funnel.get("TargetingAction", "ShadowBall")
    
    if "RaijinDaughter" in custom_waza or funnel_preset == "Dazzi":
        funnel_base = "RaijinDaughter"
    elif "Flopie" in custom_waza or funnel_preset == "Flopie":
        funnel_base = "FlowerRabbit"
    else:
        funnel_base = "DreamDemon"

    source_funnel = f"BP_FunnelCharacter_{funnel_base}"
    new_funnel_name = f"BP_FunnelCharacter_{pal_id}"

    # Target the vanilla funnel directory in Cooked: .../Content/Pal/Blueprint/Character/Funnel/
    project_dir = os.path.dirname(settings.get("uproject", ""))
    project_name = os.path.splitext(os.path.basename(settings.get("uproject", "")))[0]
    funnel_cooked_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Character", "Funnel")
    os.makedirs(funnel_cooked_dir, exist_ok=True)

    # 1. Extract Base Funnel Blueprint from game paks
    extract_game_files(settings, [
        f"Pal/Content/Pal/Blueprint/Character/Funnel/{source_funnel}.uasset",
        f"Pal/Content/Pal/Blueprint/Character/Funnel/{source_funnel}.uexp"
    ], temp_dir, format_type="raw")

    source_disk = None
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"{source_funnel.lower()}.uasset":
                source_disk = os.path.join(root, f)
                break
        if source_disk: break

    if not source_disk or not os.path.exists(source_disk):
        log(f"  [Action: Funnel] Warning: Failed to extract {source_funnel}.", "warning")
        return json_data, json_str

    from utils.uasset_helper import decompile_uasset, compile_uasset, sync_namemap
    from utils.blueprint_patcher.feature_manager import synthesize_funnel_character_ast

    temp_funnel_json = os.path.join(temp_dir, f"{source_funnel}.json")
    if not decompile_uasset(uasset_gui, source_disk, temp_funnel_json, usmap_path):
        log(f"  [Action: Funnel] Warning: Failed to decompile {source_funnel}.", "warning")
        return json_data, json_str

    with open(temp_funnel_json, "r", encoding="utf-8") as f_seed:
        seed_funnel_data = json.load(f_seed)

    # 2. Synthesize using AST builder
    funnel_ast = synthesize_funnel_character_ast(
        seed_funnel_data=seed_funnel_data,
        target_pal_id=pal_id,
        template_pal_id=template_id,
        targeting_action=targeting_action
    )

    out_funnel_json = os.path.join(temp_dir, f"{new_funnel_name}.json")
    with open(out_funnel_json, "w", encoding="utf-8") as f_out:
        json.dump(funnel_ast, f_out, indent=2)

    # 3. Compile to Cooked folder with usmap
    dest_funnel_uasset = os.path.join(funnel_cooked_dir, f"{new_funnel_name}.uasset")
    compile_ok = compile_uasset(uasset_gui, out_funnel_json, dest_funnel_uasset, usmap_path)
    
    if compile_ok and os.path.exists(dest_funnel_uasset):
        log(f"  ✓ Compiled standalone funnel blueprint: {dest_funnel_uasset}", "success")
    else:
        log(f"  ❌ Failed to compile standalone funnel blueprint: {dest_funnel_uasset}", "error")

    return json_data, json_str