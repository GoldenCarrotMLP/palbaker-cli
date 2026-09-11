# utils/blueprint_patcher/clone_funnels.py
import os
import json
import subprocess
from utils.extractor.core import extract_game_files

def clone_funnel_character(json_data: dict, json_str: str, template_id: str, pal_id: str, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, pal_data: dict = None) -> tuple[dict, str]:
    if pal_data is None:
        pal_data = {}

    has_funnel = pal_data.get("HasFunnel", False)
    if not has_funnel:
        return json_data, json_str

    log(f"  [Action: Funnel] Compiling standalone Funnel Character BP_{pal_id}...", "standard")

    custom_waza = pal_data.get("FunnelWazaID", "Funnel_DreamDemon")
    funnel_base = "RaijinDaughter" if "RaijinDaughter" in custom_waza else "DreamDemon"

    source_funnel = f"BP_FunnelCharacter_{funnel_base}"
    new_funnel_name = f"BP_FunnelCharacter_{pal_id}"

    # Target the vanilla funnel directory: .../Pal/Blueprint/Character/Funnel/
    funnel_cooked_dir = os.path.normpath(os.path.join(cooked_dir, "..", "..", "..", "Funnel"))
    os.makedirs(funnel_cooked_dir, exist_ok=True)

    # 1. Extract Base Funnel Blueprint
    extract_game_files(settings, [f"Pal/Content/Pal/Blueprint/Character/Funnel/{source_funnel}*"], temp_dir, format_type="raw")

    source_disk = None
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"{source_funnel.lower()}.uasset":
                source_disk = os.path.join(root, f)
                break
        if source_disk:
            break

    if not source_disk or not os.path.exists(source_disk):
        log(f"  [Action: Funnel] Warning: Failed to extract {source_funnel}.", "warning")
        return json_data, json_str

    temp_funnel_json = os.path.join(temp_dir, f"{new_funnel_name}.json")
    subprocess.run([uasset_gui, "tojson", source_disk, temp_funnel_json, "VER_UE5_1"], check=True, creationflags=flags)

    with open(temp_funnel_json, "r", encoding="utf-8") as f:
        f_str = f.read()

    # 2. Retarget Names and Skeletal Meshes inside the Funnel BP
    f_str = f_str.replace(f"{source_funnel}_C", f"{new_funnel_name}_C")
    f_str = f_str.replace(source_funnel, new_funnel_name)

    # First, retarget the SkeletalMesh folder specifically to pal_id's folder (NOT template_id!)
    for prefix in ["Pal/Content/Pal/Model/Character/Monster", "/Game/Pal/Model/Character/Monster", "Pal/Model/Character/Monster"]:
        f_str = f_str.replace(f"{prefix}/{funnel_base}/SK_{funnel_base}", f"{prefix}/{pal_id}/SK_{pal_id}")
        f_str = f_str.replace(f"{prefix}/{funnel_base}", f"{prefix}/{pal_id}")

    f_str = f_str.replace(f"SkeletalMesh'SK_{funnel_base}'", f"SkeletalMesh'SK_{pal_id}'")
    f_str = f_str.replace(f'"SK_{funnel_base}"', f'"SK_{pal_id}"')
    f_str = f_str.replace(f"SK_{funnel_base}", f"SK_{pal_id}")

    # Now retarget all remaining animations, montages, and AnimBPs to the parent Template
    f_str = f_str.replace(funnel_base, template_id)
    
    # If user picked Flopie or Mothgirl Waza, switch the AI Action Class
    if "Flopie" in custom_waza:
        f_str = f_str.replace("BP_AIActionFunnelSkill_ShadowBall_C", "BP_AIActionFunnelSkill_SeedMachinegun_C")
        f_str = f_str.replace("BP_AIActionFunnelSkill_ShadowBall", "BP_AIActionFunnelSkill_SeedMachinegun")
    elif "MothGirl" in custom_waza:
        f_str = f_str.replace("BP_AIActionFunnelSkill_ShadowBall_C", "BP_AIActionFunnelSkill_Thunderbolt_C")
        f_str = f_str.replace("BP_AIActionFunnelSkill_ShadowBall", "BP_AIActionFunnelSkill_Thunderbolt")

    with open(temp_funnel_json, "w", encoding="utf-8") as f:
        f.write(f_str)

    # 3. Compile into cooked_dir so the packager bundles it natively
    dest_funnel_uasset = os.path.join(funnel_cooked_dir, f"{new_funnel_name}.uasset")
    subprocess.run([uasset_gui, "fromjson", temp_funnel_json, dest_funnel_uasset], check=True, creationflags=flags)
    log(f"  ✓ Compiled standalone funnel blueprint: {dest_funnel_uasset}", "success")

    # Ensure the main actor blueprint string also swaps the BP_FunnelCharacter reference to pal_id
    json_str = json_str.replace(f"BP_FunnelCharacter_{template_id}", f"BP_FunnelCharacter_{pal_id}")
    json_str = json_str.replace(f"BP_FunnelCharacter_{funnel_base}", f"BP_FunnelCharacter_{pal_id}")
    try:
        json_data = json.loads(json_str)
    except Exception:
            pass

    return json_data, json_str