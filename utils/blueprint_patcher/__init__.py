# utils/blueprint_patcher/__init__.py
import os
import json
import shutil
import subprocess
from utils.extractor.core import extract_game_files

from .patch_mesh import patch_mesh_references, patch_physics_asset
from .patch_classes import patch_actor_class_and_cdo
from .clone_weapons import clone_partner_weapons
from .clone_actions import clone_unique_actions
from .build_variants import build_boss_variant, build_predator_variant

def patch_actor_blueprint(settings: dict, pal_id: str, template_id: str, pal_data: dict = None, log_callback=None) -> bool:
    """
    Modular Blueprint Pipeline Orchestrator:
    Step 1: Extract & Decompile Base Template
    Step 2: Clone & Retarget Partner Weapons (e.g. Flamethrower)
    Step 3: Clone & Retarget Unique Actions (e.g. Unique Attacks)
    Step 4: Atomic Mutations (Mesh, Physics, Class, CDO)
    Step 5: Compile Base Actor Blueprint (BP_{pal_id})
    Step 6: Build Alpha Boss Variant (BP_{pal_id}_BOSS)
    Step 7: Build Rampaging Predator Variant (BP_{pal_id}_PREDATOR)
    """
    def log(msg, category="standard"):
        if log_callback:
            log_callback(msg, category)
        else:
            print(f"[Blueprint Patch] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui_exe = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    
    if not os.path.exists(uasset_gui_exe):
        log(f"Error: UAssetGUI.exe not found at {uasset_gui_exe}", "error")
        return False

    uproject = settings.get("uproject", "")
    project_dir = os.path.dirname(uproject) if uproject else ""
    project_name = os.path.splitext(os.path.basename(uproject))[0] if uproject else ""
    
    if not project_dir or not os.path.exists(project_dir):
        log("Project directory not found in settings.", "error")
        return False

    if pal_data is None:
        fmodel_output = settings.get("fmodel_output", "")
        creator_json = os.path.normpath(os.path.join(fmodel_output, "Exports", "Pal", "Content", "Palbaker", "Creator", f"{pal_id}_creator.json")) if fmodel_output else ""
        if os.path.exists(creator_json):
            try:
                with open(creator_json, "r", encoding="utf-8") as f:
                    pal_data = json.load(f)
            except Exception:
                pal_data = {}
        else:
            pal_data = {}

    generate_boss = pal_data.get("GenerateBoss", True) is not False
    generate_predator = bool(pal_data.get("GeneratePredator", False))
    boss_scale = float(pal_data.get("BossScale", 1.4))

    cooked_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Character", "Monster", "PalActorBP", pal_id)
    os.makedirs(cooked_dir, exist_ok=True)

    temp_dir = os.path.join(repo_root, "temp_bp_extract")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    try:
        # STEP 1: Extract Base Template Blueprint
        log(f"Extracting base blueprint for {template_id}...")
        rel_uasset = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}.uasset"
        rel_uexp = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}.uexp"
        
        success, msg = extract_game_files(settings, [rel_uasset, rel_uexp], temp_dir, format_type="raw")
        if not success:
            log(f"Failed to extract base blueprint: {msg}", "error")
            return False

        src_uasset = os.path.join(temp_dir, rel_uasset)
        temp_base_json = os.path.join(temp_dir, "base_blueprint.json")
        subprocess.run([uasset_gui_exe, "tojson", src_uasset, temp_base_json, "VER_UE5_1"], check=True, creationflags=creation_flags)

        with open(temp_base_json, "r", encoding="utf-8") as f:
            base_json_data = json.load(f)
            f.seek(0)
            base_json_str = f.read()

        # STEP 2: Clone & Retarget Partner Weapons
        base_json_data, base_json_str = clone_partner_weapons(
            base_json_data, base_json_str, template_id, pal_id, settings,
            temp_dir, cooked_dir, uasset_gui_exe, creation_flags, log, pal_data=pal_data
        )

        # STEP 3: Clone & Retarget Unique Actions
        base_json_data, base_json_str = clone_unique_actions(
            base_json_data, base_json_str, template_id, pal_id, settings,
            temp_dir, cooked_dir, uasset_gui_exe, creation_flags, log
        )

        # STEP 4: Atomic Mutations (Mesh, Physics, Class, CDO)
        base_json_str = patch_mesh_references(base_json_str, template_id, pal_id, log)
        base_json_str = patch_physics_asset(base_json_str, template_id, pal_id, log)
        base_json_str = patch_actor_class_and_cdo(base_json_str, template_id, pal_id, log)

        # STEP 5: Compile Base Actor Blueprint
        with open(temp_base_json, "w", encoding="utf-8") as f:
            f.write(base_json_str)

        dest_base_uasset = os.path.join(cooked_dir, f"BP_{pal_id}.uasset")
        subprocess.run([uasset_gui_exe, "fromjson", temp_base_json, dest_base_uasset], check=True, creationflags=creation_flags)
        log(f"  ✓ Compiled base actor blueprint: BP_{pal_id}.uasset", "success")

        # STEP 6: Build Alpha Boss Variant
        if generate_boss:
            build_boss_variant(
                base_json_str, template_id, pal_id, boss_scale, settings,
                temp_dir, cooked_dir, uasset_gui_exe, creation_flags, log
            )

        # STEP 7: Build Rampaging Predator Variant
        if generate_predator:
            build_predator_variant(
                template_id, pal_id, generate_boss, settings,
                temp_dir, cooked_dir, uasset_gui_exe, creation_flags, log
            )

        log(f"  [DEBUG] Blueprint JSONs preserved for inspection at: {temp_dir}", "warning")
        return True

    except Exception as e:
        log(f"Fatal error during blueprint patching: {e}", "error")
        log(f"  [DEBUG] Blueprint JSONs preserved for inspection at: {temp_dir}", "warning")
        return False
    finally:
        pass