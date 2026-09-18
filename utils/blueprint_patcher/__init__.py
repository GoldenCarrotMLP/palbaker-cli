# utils/blueprint_patcher/__init__.py
import os
import re
import json
import shutil
import glob
import subprocess
from utils.extractor.core import extract_game_files

from .patch_mesh import patch_mesh_references, patch_physics_asset
from .clone_weapons import clone_partner_weapons
from .clone_actions import clone_unique_actions
from .clone_funnels import clone_funnel_character
from .build_variants import build_boss_variant, build_predator_variant

def find_skeleton_guid_in_json(json_path: str) -> str:
    if not json_path or not os.path.exists(json_path):
        return ""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        def search(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.lower() in ["skeletonguid", "virtualboneguid", "guid"] and isinstance(v, str) and len(v) >= 32:
                        return v
                    res = search(v)
                    if res: return res
            elif isinstance(node, list):
                for item in node:
                    res = search(item)
                    if res: return res
            return None
        return search(data) or ""
    except Exception:
        return ""

def patch_actor_blueprint(settings: dict, pal_id: str, template_id: str, pal_data: dict = None, log_callback=None, has_anims: bool = False, category: str = "Monster", base_pal: str = "") -> bool:
    """
    Unified Blueprint Pipeline Orchestrator
    Dynamically maps, clones, retargets, and compiles BP, ABP, BS, and Actions in one pass.
    """
    def log(msg, cat="standard"):
        if log_callback: log_callback(msg, cat)
        else: print(f"[Blueprint Patch] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    if not os.path.exists(uasset_gui):
        log(f"Error: UAssetGUI.exe not found at {uasset_gui}", "error")
        return False

    uproject = settings.get("uproject", "")
    project_dir = os.path.dirname(uproject) if uproject else ""
    project_name = os.path.splitext(os.path.basename(uproject))[0] if uproject else ""

    fmodel_output = settings.get("fmodel_output", "")
    if pal_data is None and fmodel_output:
        creator_json = os.path.normpath(os.path.join(fmodel_output, "Exports", "Pal", "Content", "Palbaker", "Creator", f"{pal_id}_creator.json"))
        if os.path.exists(creator_json):
            try:
                with open(creator_json, "r", encoding="utf-8") as f:
                    pal_data = json.load(f)
            except Exception: pal_data = {}
        else: pal_data = {}
    elif pal_data is None: pal_data = {}

    is_custom_pal = bool(pal_data and pal_data.get("CharacterID") == pal_id)
    is_variant = (not is_custom_pal and base_pal and base_pal.lower() != pal_id.lower())

    # Target folder strictly inside Saved/Cooked/
    if is_variant:
        cooked_bp_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Character", "Monster", "PalActorBP", base_pal, pal_id)
    else:
        cooked_bp_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Character", "Monster", "PalActorBP", pal_id)
    os.makedirs(cooked_bp_dir, exist_ok=True)

    temp_dir = os.path.join(repo_root, "temp_bp_extract")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # STEP 1: Identify Base Source
        has_funnel = pal_data.get("HasFunnel", False)
        funnel_base = "RaijinDaughter" if "RaijinDaughter" in pal_data.get("FunnelWazaID", "") else "DreamDemon"
        bp_source_name = funnel_base if has_funnel else template_id

        extraction_queue = [
            f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/BP_{bp_source_name}.uasset",
            f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/BP_{bp_source_name}.uexp"
        ]

        if has_anims:
            log(f"  Fetching animation stack for template {template_id} (ABP, BlendSpaces)...")
            extraction_queue.extend([
                f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/ABP_{template_id}*",
                f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BS_*",
                f"Pal/Content/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton*"
            ])

        success, msg = extract_game_files(settings, extraction_queue, temp_dir, format_type="raw")
        if not success:
            log(f"Failed to extract base blueprint: {msg}", "error")
            return False

        # Dynamically locate the extracted base blueprint asset on disk
        src_base_uasset = None
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.lower() == f"bp_{bp_source_name.lower()}.uasset":
                    src_base_uasset = os.path.join(root, f)
                    break
            if src_base_uasset: break

        if not src_base_uasset or not os.path.exists(src_base_uasset):
            log(f"Failed to locate extracted base blueprint: BP_{bp_source_name}.uasset", "error")
            return False

        temp_base_json = os.path.join(temp_dir, f"BP_{bp_source_name}.json")
        subprocess.run([uasset_gui, "tojson", src_base_uasset, temp_base_json, "VER_UE5_1"], check=True, creationflags=flags)

        with open(temp_base_json, "r", encoding="utf-8") as f:
            base_json_str = f.read()

        # Funnel hijacking
        if has_funnel:
            log(f"Retargeting Funnel {funnel_base} -> {template_id}...", "standard")
            custom_waza = pal_data.get("FunnelWazaID", f"Funnel_{funnel_base}")
            base_json_str = base_json_str.replace(f"Funnel_{funnel_base}", "FUNNEL_PROTECTED_ID")
            base_json_str = base_json_str.replace(funnel_base, template_id)
            base_json_str = base_json_str.replace("FUNNEL_PROTECTED_ID", custom_waza)
            base_json_str = base_json_str.replace(f"BP_FunnelCharacter_{template_id}", f"BP_FunnelCharacter_{pal_id}")
            
        base_json_data = json.loads(base_json_str)

        # STEP 3: Clone Weapons, Actions, and Funnels (Custom Pals Only)
        if is_custom_pal:
            base_json_data, base_json_str = clone_partner_weapons(
                base_json_data, base_json_str, template_id, pal_id, settings,
                temp_dir, cooked_bp_dir, uasset_gui, flags, log, pal_data=pal_data
            )
            base_json_data, base_json_str = clone_unique_actions(
                base_json_data, base_json_str, template_id, pal_id, settings,
                temp_dir, cooked_bp_dir, uasset_gui, flags, log
            )
            base_json_data, base_json_str = clone_funnel_character(
                base_json_data, base_json_str, template_id, pal_id, settings,
                temp_dir, cooked_bp_dir, uasset_gui, flags, log, pal_data=pal_data
            )

        # STEP 4: Retrieve custom anims metadata and GUIDs
        vanilla_guid = "BF21DEE0-4BCF0A09-60C97DA1-367595A0"
        custom_guid = "F3642458-43D36EB4-2B398F89-8DDC8313"
        custom_anims = {}

        if has_anims:
            vanilla_skel_disk = None
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if f.lower() == f"sk_{template_id.lower()}_skeleton.uasset":
                        vanilla_skel_disk = os.path.join(root, f)
                        break
                if vanilla_skel_disk: break
                
            if vanilla_skel_disk:
                sk_json = os.path.join(temp_dir, "vanilla_skel.json")
                subprocess.run([uasset_gui, "tojson", vanilla_skel_disk, sk_json, "VER_UE5_1"], check=True, creationflags=flags)
                vanilla_guid = find_skeleton_guid_in_json(sk_json) or vanilla_guid

            cat_sanitized = category.replace(" ", "_")
            if is_variant:
                sidecar_path = os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal, pal_id, f"{pal_id}_blend.json")
            else:
                sidecar_path = os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, pal_id, f"{pal_id}_blend.json")

            if os.path.exists(sidecar_path):
                try:
                    with open(sidecar_path, "r", encoding="utf-8") as f_sc:
                        sc_data = json.load(f_sc)
                        custom_anims = sc_data.get("custom_animations", {})
                        custom_guid = custom_anims.get("custom_skeleton_guid", custom_guid)
                except Exception: pass

        # STEP 5: Patch JSON String (Global Replacements across BP, ABP, BS)
        def patch_content_paths(content: str) -> str:
            # 1. Mesh & Physics
            content = content.replace(f"SK_{template_id}", f"SK_{pal_id}")
            content = content.replace(f"PA_{template_id}", f"PA_{pal_id}")
            content = content.replace(f"/Model/Character/Monster/{template_id}", f"/Model/Character/Monster/{pal_id}")
            content = content.replace(f"/Model/Character/{category.replace(' ', '_')}/{template_id}", f"/Model/Character/{category.replace(' ', '_')}/{pal_id}")

            # 2. Actor Class Name
            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}_C(?![A-Za-z0-9_])", f"BP_{pal_id}_C", content)
            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}(?![A-Za-z0-9_])", f"BP_{pal_id}", content)

            # 3. Animation Framework Retargeting
            if has_anims:
                content = content.replace(vanilla_guid, custom_guid)
                content = content.replace(f"ABP_{template_id}", f"ABP_{pal_id}")
                content = content.replace(f"SK_{template_id}_Skeleton", f"SK_{pal_id}_Skeleton")
                
                content = content.replace(f"Animation/Character/Monster/{template_id}", f"Animation/Character/Monster/{pal_id}")
                content = content.replace(f"Animation/Character/{category.replace(' ', '_')}/{template_id}", f"Animation/Character/{category.replace(' ', '_')}/{pal_id}")
                
                content = content.replace(f"AS_{template_id}_", f"AS_{pal_id}_")
                content = content.replace(f"AM_{template_id}_", f"AM_{pal_id}_")
                content = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{template_id}([_'\"])", rf"\1_{pal_id}\2", content)
            
            return content

        # Apply Global Patching to Actor BP
        base_json_str = patch_content_paths(base_json_str)
        try:
            base_json_data = json.loads(base_json_str)
        except Exception: pass

        # STEP 6: Inject RandomRestMontageInfos into BP (If Anims Active)
        if has_anims and "anims" in custom_anims:
            rest_anims = [a for a in custom_anims["anims"].values() if a.get("category") == "RandomRest"]
            if rest_anims:
                try:
                    new_rest_infos = []
                    rest_anims.sort(key=lambda x: x.get("enum_key", ""))
                    for ra in rest_anims:
                        props = ra.get("rest_props", {})
                        m_asset = ra.get("montage_asset", "")
                        if not m_asset: continue
                        
                        cat_san = category.replace(" ", "_")
                        if is_variant:
                            m_pkg = f"/Game/Pal/Animation/Character/{cat_san}/{base_pal}/{pal_id}/{m_asset}"
                        else:
                            m_pkg = f"/Game/Pal/Animation/Character/{cat_san}/{pal_id}/{m_asset}"

                        new_rest_infos.append({
                            "RandomRestMontage": {
                                "ObjectName": f"AnimMontage'{m_asset}'",
                                "ObjectPath": f"{m_pkg}.0"
                            },
                            "Weight": float(props.get("weight", 1.0)),
                            "LoopNum_Min": int(props.get("loop_min", 1)),
                            "LoopNum_Max": int(props.get("loop_max", 1)),
                            "AfterIdleTime": float(props.get("after_idle_time", 2.0))
                        })

                    for exp in base_json_data.get("Exports", []):
                        if exp.get("Type") == "PalStaticCharacterParameterComponent" or "StaticCharacterParameterComponent" in exp.get("Name", ""):
                            exp.setdefault("Properties", {})["RandomRestMontageInfos"] = new_rest_infos

                    base_json_str = json.dumps(base_json_data, indent=4)
                except Exception as e:
                    log(f"Warning: Failed to inject Random Rests: {e}", "warning")

        # STEP 7: Recompile Actor Blueprint
        with open(temp_base_json, "w", encoding="utf-8") as f:
            f.write(base_json_str)

        dest_base_uasset = os.path.join(cooked_bp_dir, f"BP_{pal_id}.uasset")
        subprocess.run([uasset_gui, "fromjson", temp_base_json, dest_base_uasset], check=True, creationflags=flags)
        log(f"  ✓ Compiled Actor Blueprint: BP_{pal_id}.uasset", "success")

        # STEP 8: Process ABP and BlendSpaces (If Anims Active)
        if has_anims:
            anim_files = []
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if (f.startswith("ABP_") or f.startswith("BS_")) and f.endswith(".uasset"):
                        anim_files.append(os.path.join(root, f))

            for a_uasset in anim_files:
                a_json = a_uasset.replace(".uasset", ".json")
                subprocess.run([uasset_gui, "tojson", a_uasset, a_json, "VER_UE5_1"], check=True, creationflags=flags)

                with open(a_json, "r", encoding="utf-8") as f_aj:
                    a_str = f_aj.read()

                # Run Global Patcher on ABP/BS
                a_str = patch_content_paths(a_str)

                with open(a_json, "w", encoding="utf-8") as f_aj:
                    f_aj.write(a_str)

                orig_filename = os.path.basename(a_uasset).replace(".uasset", "")
                
                # Regex replace BS_Move_Template -> BS_Move_CustomPal
                target_dest_filename = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{template_id}", rf"\1_{pal_id}", orig_filename)
                target_dest_filename = target_dest_filename.replace(template_id, pal_id) + ".uasset"

                dest_anim_uasset = os.path.join(cooked_bp_dir, target_dest_filename)
                subprocess.run([uasset_gui, "fromjson", a_json, dest_anim_uasset], check=True, creationflags=flags)
                log(f"  ✓ Compiled Animation Framework: {target_dest_filename}", "success")

        # STEP 9: Build Boss & Predator Variants
        boss_scale = float(pal_data.get("BossScale", 1.4))
        generate_boss = pal_data.get("GenerateBoss", True) is not False
        generate_predator = bool(pal_data.get("GeneratePredator", False))

        if generate_boss:
            build_boss_variant(
                base_json_str, template_id, pal_id, boss_scale, settings,
                temp_dir, cooked_bp_dir, uasset_gui, flags, log
            )
        if generate_predator:
            build_predator_variant(
                template_id, pal_id, generate_boss, settings,
                temp_dir, cooked_bp_dir, uasset_gui, flags, log
            )

        shutil.rmtree(temp_dir, ignore_errors=True)
        return True

    except Exception as e:
        log(f"Fatal error during unified blueprint patching: {e}", "error")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False