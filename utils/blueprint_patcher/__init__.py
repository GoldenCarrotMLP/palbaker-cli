# utils/blueprint_patcher/__init__.py
import os
import sys
import re
import json
import shutil
import glob
import subprocess

from utils.extractor.core import extract_game_files
from utils.uasset_helper import decompile_uasset, compile_uasset, sync_namemap, patch_montage_ast, encode_guid_to_extras
from .build_variants import build_boss_variant, build_predator_variant, build_raid_variant
from .feature_manager import (
    BlueprintFeatureManager,
    synthesize_funnel_character_ast,
    synthesize_flamethrower_cluster
)

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

def _retarget_additive_hit_animations(
    settings: dict,
    template_id: str,
    pal_id: str,
    category: str,
    base_pal: str,
    is_variant: bool,
    custom_guid: str,
    has_anims: bool,
    temp_dir: str,
    cooked_anims_dir: str,
    uasset_gui_exe: str,
    usmap_path: str,
    log
):
    """
    Extracts pristine additive Hit animations (AS_*_Hit and AM_*_Hit) from the parent template,
    retargets them to the target Pal's skeleton and package paths, and writes them to the
    cooked animations folder, guaranteeing that additive mesh-space hit flinches work 1:1.
    """
    cat_sanitized = category.replace(" ", "_")
    target_skel_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
    target_anims_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id

    v_new_anim_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}"
    v_new_skel_pkg = f"/Game/Pal/Model/Character/Skeleton/{target_skel_folder}"

    extract_patterns = [
        f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/AS_{template_id}_Hit*.uasset",
        f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/AS_{template_id}_Hit*.uexp",
        f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/AM_{template_id}_Hit*.uasset",
        f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/AM_{template_id}_Hit*.uexp",
        f"Pal/Content/Pal/Animation/Character/Pending_Monster/{template_id}/AS_{template_id}_Hit*.uasset",
        f"Pal/Content/Pal/Animation/Character/Pending_Monster/{template_id}/AS_{template_id}_Hit*.uexp",
        f"Pal/Content/Pal/Animation/Character/Pending_Monster/{template_id}/AM_{template_id}_Hit*.uasset",
        f"Pal/Content/Pal/Animation/Character/Pending_Monster/{template_id}/AM_{template_id}_Hit*.uexp",
    ]
    extract_game_files(settings, extract_patterns, temp_dir, format_type="raw")

    hit_uassets = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            f_lower = f.lower()
            if (f_lower.startswith(f"as_{template_id.lower()}_hit") or f_lower.startswith(f"am_{template_id.lower()}_hit")) and f_lower.endswith(".uasset"):
                hit_uassets.append(os.path.join(root, f))

    if not hit_uassets:
        return

    log(f"  [Hit Retargeting] Discovered {len(hit_uassets)} parent Hit asset(s) to retarget...", "standard")

    for uasset_path in hit_uassets:
        base_fname = os.path.splitext(os.path.basename(uasset_path))[0]
        new_fname = base_fname.replace(template_id, pal_id)
        json_path = os.path.join(temp_dir, f"{base_fname}_retarget.json")

        if not decompile_uasset(uasset_gui_exe, uasset_path, json_path, usmap_path):
            continue

        with open(json_path, "r", encoding="utf-8") as f_json:
            content = f_json.read()

        # Retarget asset and sequence names
        content = content.replace(f"AS_{template_id}_", f"AS_{pal_id}_")
        content = content.replace(f"AM_{template_id}_", f"AM_{pal_id}_")

        # Retarget animation package paths
        content = content.replace(
            f"/Game/Pal/Animation/Character/{cat_sanitized}/{template_id}/",
            f"{v_new_anim_pkg}/"
        )
        content = content.replace(
            f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/",
            f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}/"
        )

        # Retarget skeleton references if custom animations / dedicated skeleton is active
        if has_anims:
            content = content.replace(
                f"/Game/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton",
                f"{v_new_skel_pkg}/SK_{pal_id}_Skeleton"
            )
            content = content.replace(f"SK_{template_id}_Skeleton", f"SK_{pal_id}_Skeleton")

        try:
            data = json.loads(content)
            if data.get("Exports") and len(data["Exports"]) > 0:
                data["Exports"][0]["ObjectName"] = new_fname
                if base_fname.startswith("AM_") and has_anims and custom_guid:
                    data["Exports"][0]["Extras"] = encode_guid_to_extras(custom_guid)

            sync_namemap(data)
            with open(json_path, "w", encoding="utf-8") as f_json:
                json.dump(data, f_json, indent=2)
        except Exception:
            with open(json_path, "w", encoding="utf-8") as f_json:
                f_json.write(content)

        dest_uasset = os.path.join(cooked_anims_dir, f"{new_fname}.uasset")
        # Overwrite whatever file is in cooked_anims_dir
        if os.path.exists(dest_uasset):
            try: os.remove(dest_uasset)
            except OSError: pass

        if compile_uasset(uasset_gui_exe, json_path, dest_uasset, usmap_path):
            log(f"  ✓ Retargeted & compiled pristine additive hit asset: {new_fname}.uasset", "success")

def patch_actor_blueprint(settings: dict, pal_id: str, template_id: str, pal_data: dict = None, log_callback=None, has_anims: bool = False, category: str = "Monster", base_pal: str = "", keep_temp: bool = False) -> bool:
    def log(msg, cat="standard"):
        if log_callback: log_callback(msg, cat)
        else: print(f"[Blueprint Patch] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui_exe = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    if not os.path.exists(uasset_gui_exe):
        log("Error: UAssetGUI.exe not found in deps/", "error")
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
    cat_sanitized = category.replace(" ", "_")

    cooked_base_content = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content")
    if is_variant:
        cooked_bp_dir = os.path.join(cooked_base_content, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", base_pal, pal_id)
    else:
        cooked_bp_dir = os.path.join(cooked_base_content, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", pal_id)

    # --- CLEANUP PREVIOUS BLUEPRINT ARTIFACTS ---
    # Wipe all previously cooked blueprint assets for this Pal to ensure 
    # disabled features (e.g. old Funnels or Weapons) are not incorrectly packed.
    if os.path.exists(cooked_bp_dir):
        shutil.rmtree(cooked_bp_dir, ignore_errors=True)
    os.makedirs(cooked_bp_dir, exist_ok=True)

    for sub in ["Character/Funnel", "Weapon"]:
        d = os.path.join(cooked_base_content, "Pal", "Blueprint", os.path.normpath(sub))
        if os.path.exists(d):
            for f in os.listdir(d):
                if pal_id.lower() in f.lower() and f.endswith((".uasset", ".uexp", ".ubulk")):
                    try: os.remove(os.path.join(d, f))
                    except OSError: pass

    temp_dir = os.path.join(repo_root, "temp_bp_extract")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # -----------------------------------------------------------------
        # STEP 1: Extract Parent Template Actor Blueprint & Variants
        # -----------------------------------------------------------------
        log(f"Extracting template blueprints and wazas for {template_id}...", "standard")
        bp_extract_patterns = [
            f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}*.uasset",
            f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BP_{template_id}*.uexp",
            f"Pal/Content/Pal/Blueprint/Action/Waza/{template_id}*"
        ]
        success, msg = extract_game_files(settings, bp_extract_patterns, temp_dir, format_type="raw")

        if not success:
            log(f"Failed to extract base blueprint: {msg}", "error")
            return False

        src_base_uasset = None
        other_variant_uassets = []
        for root, _, files in os.walk(temp_dir):
            for f in files:
                f_lower = f.lower()
                if f_lower == f"bp_{template_id.lower()}.uasset":
                    src_base_uasset = os.path.join(root, f)
                elif f_lower.startswith(f"bp_{template_id.lower()}_") and f_lower.endswith(".uasset"):
                    other_variant_uassets.append(os.path.join(root, f))

        if not src_base_uasset or not os.path.exists(src_base_uasset):
            log(f"Base blueprint BP_{template_id}.uasset missing from extracted files.", "error")
            return False

        temp_base_json = os.path.join(temp_dir, f"BP_{template_id}.json")
        if not decompile_uasset(uasset_gui_exe, src_base_uasset, temp_base_json, usmap_path):
            log(f"Failed to decompile base blueprint {src_base_uasset}", "error")
            return False

        with open(temp_base_json, "r", encoding="utf-8") as f:
            base_json_data = json.load(f)

        # -----------------------------------------------------------------
        # STEP 1b: Merge WazaActionDeclarationMap from all variants (_RAID, _BOSS)
        # -----------------------------------------------------------------
        COMBINE_ALL_VARIANT_WAZAS = True  # Set to False to disable merging variant wazas into base blueprint

        if COMBINE_ALL_VARIANT_WAZAS and other_variant_uassets:
            import copy

            def _is_waza_entry_populated(val_prop: dict) -> bool:
                if not val_prop or not isinstance(val_prop, dict):
                    return False
                val = val_prop.get("Value")
                if isinstance(val, dict):
                    asset_path = val.get("AssetPath")
                    if isinstance(asset_path, dict):
                        pkg = asset_path.get("PackageName", "")
                        return bool(pkg and pkg != "None" and pkg != "")
                    path_name = val.get("AssetPathName", "")
                    return bool(path_name and path_name != "None" and path_name != "")
                elif isinstance(val, str):
                    return bool(val and val != "None" and val != "")
                return False

            def _get_waza_map_from_ast(ast_data: dict) -> list | None:
                for exp in ast_data.get("Exports", []):
                    if exp.get("ObjectName") == "StaticCharacterParameterComponent":
                        for p in exp.get("Data", []):
                            if p.get("Name") == "WazaActionDeclarationMap" and isinstance(p.get("Value"), list):
                                return p["Value"]
                return None

            base_waza_map = _get_waza_map_from_ast(base_json_data)

            for var_uasset in other_variant_uassets:
                var_name = os.path.splitext(os.path.basename(var_uasset))[0]
                var_json = os.path.join(temp_dir, f"{var_name}.json")
                if decompile_uasset(uasset_gui_exe, var_uasset, var_json, usmap_path):
                    try:
                        with open(var_json, "r", encoding="utf-8") as f_var:
                            var_ast = json.load(f_var)
                        var_waza_map = _get_waza_map_from_ast(var_ast)

                        if var_waza_map and base_waza_map is not None:
                            for var_entry in var_waza_map:
                                if not isinstance(var_entry, list) or len(var_entry) < 2:
                                    continue
                                waza_key = var_entry[0].get("Value", "") if isinstance(var_entry[0], dict) else ""
                                if not waza_key:
                                    continue

                                if _is_waza_entry_populated(var_entry[1]):
                                    existing = next((
                                        e for e in base_waza_map 
                                        if isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and e[0].get("Value") == waza_key
                                    ), None)

                                    if existing:
                                        if not _is_waza_entry_populated(existing[1]):
                                            existing[1] = copy.deepcopy(var_entry[1])
                                            log(f"  [Waza Merge] Filled empty {waza_key} into base from {var_name}", "standard")
                                    else:
                                        base_waza_map.append(copy.deepcopy(var_entry))
                                        log(f"  [Waza Merge] Merged variant {waza_key} into base from {var_name}", "standard")
                    except Exception as e:
                        log(f"Warning merging wazas from {var_name}: {e}", "warning")

        base_json_str = json.dumps(base_json_data, indent=4)

        # -----------------------------------------------------------------
        # STEP 2: Extract Dynamic Dependencies (Actions, Modules, ABP, BS, AM)
        # -----------------------------------------------------------------
        # Support BP_Action_, BP_UniqueAction_, and any Action blueprint under Pal/Blueprint/Action/
        action_pattern = re.compile(rf'((?:/Game|Pal/Content)/Pal/Blueprint/Action/[\w/]*/(BP_[a-zA-Z0-9_]*Action[a-zA-Z0-9_]*))', re.IGNORECASE)
        
        combined_scanned_str = base_json_str
        for var_uasset in other_variant_uassets:
            v_json = var_uasset.replace(".uasset", ".json")
            if os.path.exists(v_json):
                try:
                    with open(v_json, "r", encoding="utf-8") as f_vj:
                        combined_scanned_str += "\n" + f_vj.read()
                except Exception: pass

        discovered_actions = sorted(list(set(action_pattern.findall(combined_scanned_str))))
        
        valid_actions = []
        for p_core, a_name in discovered_actions:
            norm_core = p_core.replace("/Game/", "Pal/Content/")
            if f"/{template_id}/" in norm_core or template_id.lower() in a_name.lower():
                if (norm_core, a_name) not in valid_actions:
                    valid_actions.append((norm_core, a_name))

        # Also automatically ingest all physical action blueprints extracted in Pal/Blueprint/Action/Waza/{template_id}/
        waza_disk_dir = os.path.join(temp_dir, "Pal", "Content", "Pal", "Blueprint", "Action", "Waza", template_id)
        if os.path.exists(waza_disk_dir):
            for root, _, files in os.walk(waza_disk_dir):
                for f in files:
                    if f.endswith(".uasset"):
                        a_name = os.path.splitext(f)[0]
                        rel_core = os.path.relpath(os.path.join(root, a_name), temp_dir).replace("\\", "/")
                        if (rel_core, a_name) not in valid_actions:
                            valid_actions.append((rel_core, a_name))
                            log(f"  [Waza Discovery] Found physical action blueprint: {a_name}", "standard")

        discovered_blendspaces = set()
        discovered_montages = set()
        discovered_abps = set()
        custom_anims = {}

        if has_anims:
            sidecar_candidates = [
                os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal, pal_id, f"{pal_id}_blend.json"),
                os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal, f"{pal_id}_blend.json"),
                os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, pal_id, f"{pal_id}_blend.json")
            ]
            sidecar_path = next((p for p in sidecar_candidates if os.path.exists(p)), "")

            if sidecar_path and os.path.exists(sidecar_path):
                try:
                    with open(sidecar_path, "r", encoding="utf-8") as f_sc:
                        sc_data = json.load(f_sc)
                        custom_anims = sc_data.get("custom_animations", {})
                        
                        for anim_key, anim_val in custom_anims.get("anims", {}).items():
                            m_asset = anim_val.get("montage_asset")
                            if m_asset:
                                template_am = m_asset.replace(pal_id, template_id)
                                discovered_montages.add(template_am)

                        for bs_key, bs_val in custom_anims.get("blend_spaces", {}).items():
                            bs_asset = bs_val.get("asset_name")
                            if bs_asset:
                                template_bs = bs_asset.replace(pal_id, template_id)
                                discovered_blendspaces.add(template_bs)
                except Exception as e:
                    log(f"Warning parsing sidecar for animation inventory: {e}", "warning")

            discovered_abps.add(f"ABP_{template_id}")

            dep_queue = [
                f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/ABP_{template_id}*.uasset",
                f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/ABP_{template_id}*.uexp",
                f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BS_*.uasset",
                f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BS_*.uexp",
                f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/AM_*.uasset",
                f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/AM_*.uexp",
                f"Pal/Content/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton.uasset",
                f"Pal/Content/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton.uexp"
            ]
        else:
            dep_queue = []

        # Queue Actions for extraction
        for path_core, a_name in valid_actions:
            dep_queue.extend([f"{path_core}.uasset", f"{path_core}.uexp", f"*{a_name}*"])

        if dep_queue:
            log(f"  Extracting animation stack & action dependencies from game paks...", "standard")
            extract_game_files(settings, dep_queue, temp_dir, format_type="raw")

        # -----------------------------------------------------------------
        # STEP 2b: Discover & Extract Unique Skill Modules from Actions
        # -----------------------------------------------------------------
        valid_modules = []
        module_queue = []

        for path_core, a_name in valid_actions:
            action_uasset = os.path.join(temp_dir, f"{path_core}.uasset")
            if os.path.exists(action_uasset):
                a_json = action_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, action_uasset, a_json, usmap_path)
                with open(a_json, "r", encoding="utf-8") as f_aj:
                    a_str = f_aj.read()
                
                module_pattern = re.compile(rf'((?:/Game|Pal/Content)/Pal/Blueprint/Action/[\w/]*/(BP_UniqueSkillModule_[a-zA-Z0-9_]+))', re.IGNORECASE)
                discovered_mods = set(module_pattern.findall(a_str))
                
                for m_path, m_name in discovered_mods:
                    norm_m_path = m_path.replace("/Game/", "Pal/Content/")
                    if f"/{template_id}/" in norm_m_path or template_id in m_name:
                        if (norm_m_path, m_name) not in valid_modules:
                            valid_modules.append((norm_m_path, m_name))
                            module_queue.extend([f"{norm_m_path}.uasset", f"{norm_m_path}.uexp"])

        if module_queue:
            log(f"  Extracting {len(valid_modules)} embedded Unique Skill Modules...", "standard")
            extract_game_files(settings, module_queue, temp_dir, format_type="raw")

        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith(".uasset"):
                    base_f = os.path.splitext(f)[0]
                    if base_f.startswith(f"ABP_{template_id}"):
                        discovered_abps.add(base_f)
                    elif base_f.startswith("BS_"):
                        discovered_blendspaces.add(base_f)
                    elif base_f.startswith(f"AM_{template_id}"):
                        discovered_montages.add(base_f)

        discovered_blendspaces = sorted(list(discovered_blendspaces))
        discovered_montages = sorted(list(discovered_montages))
        discovered_abps = sorted(list(discovered_abps))

        # -----------------------------------------------------------------
        # STEP 3: Retarget Package Paths & Global References
        # -----------------------------------------------------------------
        vanilla_guid = "BF21DEE0-4BCF0A09-60C97DA1-367595A0"
        custom_guid = "F3642458-43D36EB4-2B398F89-8DDC8313"

        if has_anims:
            v_skel = None
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if f.lower() == f"sk_{template_id.lower()}_skeleton.uasset":
                        v_skel = os.path.join(root, f)
                        break
                if v_skel: break
            if v_skel:
                sk_json = os.path.join(temp_dir, "vanilla_skel.json")
                decompile_uasset(uasset_gui_exe, v_skel, sk_json, usmap_path)
                vanilla_guid = find_skeleton_guid_in_json(sk_json) or vanilla_guid

        target_bp_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
        target_skel_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
        target_anims_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
        target_mesh_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id

        def global_patch(content: str) -> str:
            # 1. Base Mesh & Physics Asset
            content = content.replace(
                f"/Model/Character/{cat_sanitized}/{template_id}",
                f"/Model/Character/{cat_sanitized}/{target_mesh_folder}"
            )
            content = content.replace(f"SK_{template_id}", f"SK_{pal_id}")
            content = content.replace(f"PA_{template_id}", f"PA_{pal_id}")
            
            # 2. Retarget Actor Blueprint
            content = content.replace(f"/PalActorBP/{template_id}/BP_{template_id}", f"/PalActorBP/{target_bp_folder}/BP_{pal_id}")
            content = content.replace(f"ExecuteUbergraph_BP_{template_id}", f"ExecuteUbergraph_BP_{pal_id}")
            content = content.replace(f"BndEvt__BP_{template_id}_", f"BndEvt__BP_{pal_id}_")
            content = re.sub(rf"Default__BP_{template_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_C", content)
            content = re.sub(rf"Default__BP_{template_id}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}", content)
            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}_C(?![A-Za-z0-9_])", f"BP_{pal_id}_C", content)
            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}(?![A-Za-z0-9_])", f"BP_{pal_id}", content)

            # 3. Actions & Skill Modules
            for path_core, a_name in valid_actions + valid_modules:
                new_path_core = path_core.replace(template_id, pal_id)
                new_name = a_name.replace(template_id, pal_id)

                game_path_core = path_core.replace("Pal/Content/", "/Game/")
                game_new_path_core = new_path_core.replace("Pal/Content/", "/Game/")

                content = content.replace(f"{game_path_core}.{a_name}_C", f"{game_new_path_core}.{new_name}_C")
                content = content.replace(f"{game_path_core}", f"{game_new_path_core}")
                content = content.replace(path_core, new_path_core)
                
                content = content.replace(f"/{a_name}.{a_name}_C", f"/{new_name}.{new_name}_C")
                content = content.replace(f"/{a_name}", f"/{new_name}")

                content = content.replace(f"Default__{a_name}_C", f"Default__{new_name}_C")
                content = content.replace(f"Default__{a_name}", f"Default__{new_name}")
                content = content.replace(f"{a_name}_C", f"{new_name}_C")
                content = content.replace(f"ExecuteUbergraph_{a_name}", f"ExecuteUbergraph_{new_name}")
                content = re.sub(rf"(?<![A-Za-z0-9_]){a_name}(?![A-Za-z0-9_])", new_name, content)

            # 4. Custom Animations Retargeting
            if has_anims:
                content = content.replace(vanilla_guid, custom_guid)

                content = content.replace(f"/Model/Character/Skeleton/{template_id}/", f"/Model/Character/Skeleton/{target_skel_folder}/")
                content = content.replace(f"SK_{template_id}_Skeleton", f"SK_{pal_id}_Skeleton")
                content = content.replace(f"Animation/Character/{cat_sanitized}/{template_id}", f"Animation/Character/{cat_sanitized}/{target_anims_folder}")

                content = content.replace(f"AS_{template_id}_", f"AS_{pal_id}_")
                content = content.replace(f"AM_{template_id}_", f"AM_{pal_id}_")

                for abp in discovered_abps:
                    new_abp = abp.replace(template_id, pal_id)
                    content = content.replace(f"/PalActorBP/{template_id}/{abp}", f"/PalActorBP/{target_bp_folder}/{new_abp}")
                    content = content.replace(f"{abp}_C", f"{new_abp}_C")
                    content = content.replace(abp, new_abp)

                for bs in discovered_blendspaces:
                    new_bs = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{template_id}", rf"\1_{pal_id}", bs)
                    content = content.replace(f"/PalActorBP/{template_id}/{bs}", f"/PalActorBP/{target_bp_folder}/{new_bs}")
                    content = content.replace(bs, new_bs)

                for am in discovered_montages:
                    new_am = am.replace(template_id, pal_id)
                    content = content.replace(am, new_am)

            return content

        # -----------------------------------------------------------------
        # STEP 4: Retarget & Compile Action Blueprints & Modules
        # -----------------------------------------------------------------
        for path_core, a_name in valid_actions + valid_modules:
            action_uasset = os.path.normpath(os.path.join(temp_dir, f"{path_core}.uasset"))
            if not os.path.exists(action_uasset):
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        if f.lower() == f"{a_name.lower()}.uasset":
                            action_uasset = os.path.join(root, f)
                            break
                    if action_uasset and os.path.exists(action_uasset):
                        break

            if action_uasset and os.path.exists(action_uasset):
                a_json = action_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, action_uasset, a_json, usmap_path)
                with open(a_json, "r", encoding="utf-8") as f_aj:
                    a_str = global_patch(f_aj.read())
                try:
                    a_data = json.loads(a_str)
                    sync_namemap(a_data)
                    with open(a_json, "w", encoding="utf-8") as f_aj:
                        json.dump(a_data, f_aj, indent=4)
                except Exception:
                    with open(a_json, "w", encoding="utf-8") as f_aj:
                        f_aj.write(a_str)

                new_path_core = path_core.replace(template_id, pal_id)
                new_name = a_name.replace(template_id, pal_id)
                
                stripped_new_core = new_path_core.replace("Pal/Content/", "")
                action_dest_dir = os.path.join(cooked_base_content, os.path.dirname(stripped_new_core))
                os.makedirs(action_dest_dir, exist_ok=True)
                
                dest_action_uasset = os.path.join(action_dest_dir, f"{new_name}.uasset")
                compile_ok = compile_uasset(uasset_gui_exe, a_json, dest_action_uasset, usmap_path)
                if compile_ok and os.path.exists(dest_action_uasset):
                    log(f"  ✓ Retargeted blueprint logic: {new_name}", "success")
                else:
                    log(f"  ❌ Failed to compile action blueprint: {new_name}", "error")
            else:
                log(f"  ❌ Action blueprint '{a_name}' not found in extracted files. Skipping.", "error")

        # -----------------------------------------------------------------
        # STEP 4b: Retarget & Compile AnimBlueprints (ABP_)
        # -----------------------------------------------------------------
        for abp in discovered_abps:
            abp_uasset = None
            for root, _, files in os.walk(temp_dir):
                if f"{abp}.uasset" in files:
                    abp_uasset = os.path.join(root, f"{abp}.uasset")
                    break

            if abp_uasset and os.path.exists(abp_uasset):
                abp_json = abp_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, abp_uasset, abp_json, usmap_path)
                with open(abp_json, "r", encoding="utf-8") as f:
                    abp_str = global_patch(f.read())
                try:
                    abp_data = json.loads(abp_str)
                    sync_namemap(abp_data)
                    with open(abp_json, "w", encoding="utf-8") as f:
                        json.dump(abp_data, f, indent=4)
                except Exception:
                    with open(abp_json, "w", encoding="utf-8") as f:
                        f.write(abp_str)

                new_abp_name = abp.replace(template_id, pal_id)
                dest_abp_uasset = os.path.join(cooked_bp_dir, f"{new_abp_name}.uasset")
                compile_uasset(uasset_gui_exe, abp_json, dest_abp_uasset, usmap_path)
                log(f"  ✓ Compiled AnimBlueprint: {new_abp_name}.uasset")

        # -----------------------------------------------------------------
        # STEP 4c: Retarget & Compile Locomotion BlendSpaces (BS_)
        # -----------------------------------------------------------------
        for bs in discovered_blendspaces:
            bs_uasset = None
            for root, _, files in os.walk(temp_dir):
                if f"{bs}.uasset" in files:
                    bs_uasset = os.path.join(root, f"{bs}.uasset")
                    break

            if bs_uasset and os.path.exists(bs_uasset):
                bs_json = bs_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, bs_uasset, bs_json, usmap_path)
                with open(bs_json, "r", encoding="utf-8") as f:
                    bs_str = global_patch(f.read())
                try:
                    bs_data = json.loads(bs_str)
                    sync_namemap(bs_data)
                    with open(bs_json, "w", encoding="utf-8") as f:
                        json.dump(bs_data, f, indent=4)
                except Exception:
                    with open(bs_json, "w", encoding="utf-8") as f:
                        f.write(bs_str)

                new_bs_name = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{template_id}", rf"\1_{pal_id}", bs)
                dest_bs_uasset = os.path.join(cooked_bp_dir, f"{new_bs_name}.uasset")
                compile_uasset(uasset_gui_exe, bs_json, dest_bs_uasset, usmap_path)
                log(f"  ✓ Compiled BlendSpace: {new_bs_name}.uasset")

        # -----------------------------------------------------------------
        # STEP 4d: Retarget & Compile AnimMontages (AM_)
        # -----------------------------------------------------------------
        cooked_anims_dir = os.path.normpath(os.path.join(cooked_base_content, "Pal", "Animation", "Character", cat_sanitized, pal_id))
        if is_variant:
            cooked_anims_dir = os.path.normpath(os.path.join(cooked_base_content, "Pal", "Animation", "Character", cat_sanitized, base_pal, pal_id))
        os.makedirs(cooked_anims_dir, exist_ok=True)

        for am in discovered_montages:
            am_uasset = None
            for root, _, files in os.walk(temp_dir):
                if f"{am}.uasset" in files:
                    am_uasset = os.path.join(root, f"{am}.uasset")
                    break

            if am_uasset and os.path.exists(am_uasset):
                am_json = am_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, am_uasset, am_json, usmap_path)
                with open(am_json, "r", encoding="utf-8") as f:
                    am_str = global_patch(f.read())
                try:
                    am_data = json.loads(am_str)
                    sync_namemap(am_data)
                    with open(am_json, "w", encoding="utf-8") as f:
                        json.dump(am_data, f, indent=4)
                except Exception:
                    with open(am_json, "w", encoding="utf-8") as f:
                        f.write(am_str)

                new_am_name = am.replace(template_id, pal_id)
                dest_am_uasset = os.path.join(cooked_anims_dir, f"{new_am_name}.uasset")
                compile_uasset(uasset_gui_exe, am_json, dest_am_uasset, usmap_path)
                log(f"  ✓ Compiled AnimMontage: {new_am_name}.uasset")

        # -----------------------------------------------------------------
        # STEP 4e: Retarget Pristine Additive Hit Reaction Animations (AS_*_Hit & AM_*_Hit)
        # -----------------------------------------------------------------
        _retarget_additive_hit_animations(
            settings=settings,
            template_id=template_id,
            pal_id=pal_id,
            category=category,
            base_pal=base_pal,
            is_variant=is_variant,
            custom_guid=custom_guid,
            has_anims=has_anims,
            temp_dir=temp_dir,
            cooked_anims_dir=cooked_anims_dir,
            uasset_gui_exe=uasset_gui_exe,
            usmap_path=usmap_path,
            log=log
        )

        # -----------------------------------------------------------------
        # STEP 5: Ingest Features into Host Actor Blueprint via AST Manager
        # -----------------------------------------------------------------
        base_json_str = global_patch(base_json_str)
        base_json_data = json.loads(base_json_str)

        # Clean up any null OverrideMaterials that crash D3D11
        for exp in base_json_data.get("Exports", []):
            if exp.get("ObjectName") == "CharacterMesh0":
                props = exp.get("Data", [])
                clean_props = []
                for p in props:
                    if p.get("Name") == "OverrideMaterials":
                        mat_vals = p.get("Value", [])
                        if any(isinstance(v, dict) and v.get("Value", 0) != 0 for v in mat_vals):
                            clean_props.append(p)
                    else:
                        clean_props.append(p)
                exp["Data"] = clean_props

        if base_json_data:
            
            # ---> CRITICAL FIX: Only modify components if this is a Standalone Custom Pal!
            # Variants (even with custom animations) inherit their parent's exact layout.
            if is_custom_pal:
                mgr = BlueprintFeatureManager(base_json_data)
                features = pal_data.get("Features", {})

                # Active partner skills are mutually exclusive (Keybind 'F'):
                riding = features.get("Riding", {})
                coop_weapon = features.get("CoopWeapon", {})
                funnel = features.get("Funnel", {})

                is_riding_active = bool(riding.get("Enabled", False))
                is_weapon_active = bool(coop_weapon.get("Enabled", False))
                is_funnel_active = bool(funnel.get("Enabled", False))

                if is_riding_active:
                    is_weapon_active = False

                # 5a. Mounts & Riding
                if is_riding_active:
                    mgr.add_saddle(
                        marker_type=riding.get("MarkerType", "Saddle"),
                        ride_position_type=riding.get("RidePosition", "HorseRide"),
                        attach_socket=riding.get("AttachSocket", "pelvis"),
                        relative_rotation=riding.get("RelativeRotation", {"Pitch": 90.0, "Yaw": 0.0, "Roll": 0.0}),
                        relative_location=riding.get("RelativeLocation", {"X": 0.0, "Y": 0.0, "Z": 40.0}),
                        with_speed_collision=riding.get("WithSpeedCollision", False)
                    )
                    if riding.get("WithMountedShooter"):
                        mgr.add_mounted_shooter()

                    # --- SYNTHESIZE PHYSICAL BS_Move_<Pal>_Riding.uasset ---
                    new_bs_name = f"BS_Move_{pal_id}_Riding"
                    dest_bs_uasset = os.path.join(cooked_bp_dir, f"{new_bs_name}.uasset")

                    seed_bs_rel = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BS_Move_{template_id}_Riding.uasset"
                    extract_game_files(settings, [seed_bs_rel, seed_bs_rel.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
                    seed_bs_disk = os.path.join(temp_dir, seed_bs_rel)

                    if not os.path.exists(seed_bs_disk):
                        seed_bs_rel = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/BS_Move_{template_id}.uasset"
                        extract_game_files(settings, [seed_bs_rel, seed_bs_rel.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
                        seed_bs_disk = os.path.join(temp_dir, seed_bs_rel)

                    if not os.path.exists(seed_bs_disk):
                        seed_bs_rel = "Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/WeaselDragon/BS_Move_WeaselDragon_Riding.uasset"
                        extract_game_files(settings, [seed_bs_rel, seed_bs_rel.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
                        seed_bs_disk = os.path.join(temp_dir, seed_bs_rel)

                    # Dynamic recursive search if exact relative path had case discrepancies
                    if not os.path.exists(seed_bs_disk):
                        for root, _, files in os.walk(temp_dir):
                            for f in files:
                                if f.lower().startswith("bs_move_") and f.lower().endswith(".uasset"):
                                    seed_bs_disk = os.path.join(root, f)
                                    break
                            if seed_bs_disk and os.path.exists(seed_bs_disk):
                                break

                    bs_compiled_ok = False
                    if seed_bs_disk and os.path.exists(seed_bs_disk):
                        old_bs_name = os.path.splitext(os.path.basename(seed_bs_disk))[0]
                        temp_bs_json = os.path.join(temp_dir, f"{new_bs_name}.json")
                        if decompile_uasset(uasset_gui_exe, seed_bs_disk, temp_bs_json, usmap_path):
                            with open(temp_bs_json, "r", encoding="utf-8") as f_bs:
                                bs_str = f_bs.read()

                            seed_pal_id = template_id if template_id in old_bs_name else "WeaselDragon"

                            bs_str = bs_str.replace(f"/PalActorBP/{seed_pal_id}/{old_bs_name}", f"/PalActorBP/{target_bp_folder}/{new_bs_name}")
                            bs_str = bs_str.replace(f'"{old_bs_name}"', f'"{new_bs_name}"')
                            bs_str = bs_str.replace(f"'{old_bs_name}'", f"'{new_bs_name}'")
                            bs_str = bs_str.replace(f"/PalActorBP/{seed_pal_id}/", f"/PalActorBP/{target_bp_folder}/")

                            if has_anims:
                                bs_str = bs_str.replace(f"SK_{seed_pal_id}_Skeleton", f"SK_{pal_id}_Skeleton")
                                bs_str = bs_str.replace(f"AS_{seed_pal_id}_", f"AS_{pal_id}_")
                                bs_str = bs_str.replace(f"/Skeleton/{seed_pal_id}/", f"/Skeleton/{target_skel_folder}/")
                                bs_str = bs_str.replace(f"/Monster/{seed_pal_id}/", f"/Monster/{target_anims_folder}/")
                            else:
                                bs_str = bs_str.replace(f"SK_{seed_pal_id}_Skeleton", f"SK_{template_id}_Skeleton")
                                bs_str = bs_str.replace(f"/Skeleton/{seed_pal_id}/", f"/Skeleton/{template_id}/")
                                bs_str = bs_str.replace(f"AS_{seed_pal_id}_", f"AS_{template_id}_")
                                bs_str = bs_str.replace(f"/Monster/{seed_pal_id}/", f"/Monster/{template_id}/")

                            # Normalize any riding-specific sequence references to template's existing sequences
                            bs_str = bs_str.replace(f"AS_{seed_pal_id}_Run_Riding", f"AS_{template_id}_Run")
                            bs_str = bs_str.replace(f"AS_{seed_pal_id}_Walk_Riding", f"AS_{template_id}_Walk")
                            bs_str = bs_str.replace(f"AS_{template_id}_Run_Riding", f"AS_{template_id}_Run")
                            bs_str = bs_str.replace(f"AS_{template_id}_Walk_Riding", f"AS_{template_id}_Walk")

                            bs_data = json.loads(bs_str)
                            bs_data["FolderName"] = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{target_bp_folder}/{new_bs_name}"
                            if bs_data.get("Exports"):
                                bs_data["Exports"][0]["ObjectName"] = new_bs_name

                            sync_namemap(bs_data)
                            with open(temp_bs_json, "w", encoding="utf-8") as f_bs:
                                json.dump(bs_data, f_bs, indent=2)

                            if compile_uasset(uasset_gui_exe, temp_bs_json, dest_bs_uasset, usmap_path):
                                log(f"  ✓ Compiled standalone Riding BlendSpace: {dest_bs_uasset}", "success")
                                bs_compiled_ok = True

                    bs_pkg_path = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{target_bp_folder}/{new_bs_name}"
                    bs_import_idx = mgr.ensure_import_chain(bs_pkg_path, new_bs_name, class_type="BlendSpace1D")

                    comp = mgr.find_static_char_param_export()
                    if comp and isinstance(comp.get("Data"), list):
                        # --- CRITICAL FIX: Register Import in EDL Dependencies to satisfy FAsyncLoadingThread ---
                        comp_deps = comp.setdefault("CreateBeforeSerializationDependencies", [])
                        if bs_import_idx not in comp_deps:
                            comp_deps.append(bs_import_idx)

                        bs_map = next((p for p in comp["Data"] if isinstance(p, dict) and p.get("Name") == "GeneralBlendSpaceMap"), None)
                        if bs_map and isinstance(bs_map.get("Value"), list):
                            bs_map["Value"] = [
                                e for e in bs_map["Value"]
                                if not (isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and "RidingMove" in str(e[0].get("Value", "")))
                            ]
                            bs_map["Value"].append([
                                {
                                    "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                                    "EnumType": None,
                                    "InnerType": None,
                                    "Name": "GeneralBlendSpaceMap",
                                    "ArrayIndex": 0,
                                    "PropertyGuid": None,
                                    "IsZero": False,
                                    "PropertyTagFlags": "None",
                                    "PropertyTypeName": None,
                                    "PropertyTagExtensions": "NoExtension",
                                    "Value": "EPalGeneralBlendSpaceType::RidingMove"
                                },
                                {
                                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                                    "Name": "GeneralBlendSpaceMap",
                                    "ArrayIndex": 0,
                                    "PropertyGuid": None,
                                    "IsZero": False,
                                    "PropertyTagFlags": "None",
                                    "PropertyTypeName": None,
                                    "PropertyTagExtensions": "NoExtension",
                                    "Value": bs_import_idx
                                }
                            ])
                else:
                    mgr.remove_saddle()

                # 5b. Flight
                flight = features.get("Flight", {})
                if flight.get("Enabled"):
                    mgr.add_fly_height_controller()
                else:
                    mgr.remove_fly_height_controller()

                # 5c. Defensive Shield
                shield = features.get("Shield", {})
                if shield.get("Enabled"):
                    mgr.add_shield(
                        radius=shield.get("Radius", 90.0),
                        attach_socket=shield.get("AttachSocket", "lowerarm_l"),
                        relative_location=shield.get("RelativeLocation")
                    )
                else:
                    mgr.remove_component("Shield")
                    mgr.remove_component("BP_CoopParam_Sheild")

                # 5d. Utility Actions
                utility = features.get("CoopUtility", {})
                if utility.get("SkillType") and utility.get("SkillType") != "None":
                    mgr.set_coop_utility(utility["SkillType"])

                # 5e. Combat Evasion
                evasion = features.get("CombatEvasion", {})
                if evasion.get("SideMoveStyle") and evasion.get("SideMoveStyle") != "None":
                    mgr.set_evasion_style(evasion["SideMoveStyle"])
                if evasion.get("LeaveStyle") and evasion.get("LeaveStyle") != "None":
                    mgr.set_evasion_style(evasion["LeaveStyle"])

                # 5f. Night Point Light
                light = features.get("TimerPointLight", {})
                if light.get("Enabled"):
                    mgr.add_timer_point_light()

                # 5g. Permanent VFX Particles
                vfx_list = features.get("VFX", [])
                for vfx in vfx_list:
                    mgr.add_niagara_particle(
                        var_name=vfx.get("VarName", f"VFX_{vfx.get('AttachSocket')}"),
                        system_package=vfx.get("SystemPackage", "/Game/Pal/Effect/Common/Cooking/NS_CookingFlame"),
                        system_name=vfx.get("SystemName", "NS_CookingFlame"),
                        attach_socket=vfx.get("AttachSocket", "root")
                    )

                # 5h. Locomotion Leaning Calibration
                leaning = features.get("LocomotionLeaning", {})
                for mode, cfg in leaning.items():
                    mgr.set_locomotion_leaning(
                        mode=mode,
                        pitch_intensity=cfg.get("PitchIntensity", 0.0),
                        roll_intensity=cfg.get("RollIntensity", 0.0)
                    )

                # 5i. Co-op Partner Weapon Synthesis
                if is_weapon_active:
                    mode = coop_weapon.get("Mode", "Flamethrower")
                    wp_name = f"BP_{pal_id}_{mode}" if mode != "ThrowBomb" else f"BP_{pal_id}_ThrowElecBomb"
                    if mode == "Katana": wp_name = f"BP_{pal_id}_Katana"
                    if mode == "Launcher": wp_name = f"BP_{pal_id}_Launcher"

                    wp_pkg = f"/Game/Pal/Blueprint/Weapon/{wp_name}"
                    wp_cls = f"{wp_name}_C"

                    mgr.add_coop_weapon(
                        mode=mode,
                        weapon_class_package=wp_pkg,
                        weapon_class_name=wp_cls,
                        attach_socket=coop_weapon.get("AttachSocket", "Socket_Weapon_R"),
                        skill_magnification=coop_weapon.get("SkillMagnification"),
                        aim_blur_angles=coop_weapon.get("AimBlurAngles")
                    )
                    
                    # --- CRITICAL FIX: Trigger actual Synthesis of the Weapon Blueprint ---
                    from utils.blueprint_patcher.clone_weapons import clone_partner_weapons
                    # We pass the dummy vars down to trigger the clone sequence into the cooked folder
                    clone_partner_weapons({}, "", template_id, pal_id, settings, temp_dir, cooked_base_content, uasset_gui_exe, flags, log, pal_data=pal_data, usmap_path=usmap_path, has_anims=has_anims)
                else:
                    mgr.remove_component("BP_CoopParam_Weapon")
                    mgr.remove_component("BP_CoopParam_AssaultRifleMode")
                    mgr.remove_component("BP_CoopParam_ShotgunMode")
                    mgr.remove_component("BP_CoopParam_OnHeadShot")

                    for exp in base_json_data.get("Exports", []):
                        if "ComponentDelegateBinding" in str(exp.get("ObjectName", "")):
                            exp["Data"] = []

                # 5j. Satellite Minion Funnel Synthesis
                if is_funnel_active:
                    funnel_preset = funnel.get("Preset", "DreamDemon")
                    custom_waza = funnel.get("CustomWazaID", pal_data.get("FunnelWazaID", "EPalWazaID::Funnel_DreamDemon"))
                    custom_satellite_path = f"/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_{pal_id}.BP_FunnelCharacter_{pal_id}_C"

                    mgr.set_partner_funnel(
                        preset_name=funnel_preset,
                        custom_waza_id=custom_waza,
                        custom_character_class=custom_satellite_path
                    )

                    log(f"  [Action: Funnel] Synthesizing standalone Funnel Character BP_FunnelCharacter_{pal_id}...", "standard")
                    funnel_base = "RaijinDaughter" if ("RaijinDaughter" in custom_waza or funnel_preset == "Dazzi") else ("FlowerRabbit" if funnel_preset == "Flopie" else "DreamDemon")
                    source_funnel_name = f"BP_FunnelCharacter_{funnel_base}"

                    seed_funnel_rel = f"Pal/Content/Pal/Blueprint/Character/Funnel/{source_funnel_name}.uasset"
                    extract_game_files(settings, [seed_funnel_rel, seed_funnel_rel.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
                    seed_fn_uasset = os.path.join(temp_dir, seed_funnel_rel)
                    seed_fn_json = os.path.join(temp_dir, f"{source_funnel_name}.json")

                    funnel_cooked_dir = os.path.join(cooked_base_content, "Pal", "Blueprint", "Character", "Funnel")
                    os.makedirs(funnel_cooked_dir, exist_ok=True)

                    if decompile_uasset(uasset_gui_exe, seed_fn_uasset, seed_fn_json, usmap_path):
                        with open(seed_fn_json, "r", encoding="utf-8") as f_sfn:
                            seed_fn_data = json.load(f_sfn)

                        funnel_ast = synthesize_funnel_character_ast(
                            seed_funnel_data=seed_fn_data,
                            target_pal_id=pal_id,
                            template_pal_id=template_id,
                            targeting_action=funnel.get("TargetingAction", "ShadowBall")
                        )

                        out_fn_json = os.path.join(temp_dir, f"BP_FunnelCharacter_{pal_id}.json")
                        with open(out_fn_json, "w", encoding="utf-8") as f_out_fn:
                            json.dump(funnel_ast, f_out_fn, indent=2)

                        dest_fn_uasset = os.path.join(funnel_cooked_dir, f"BP_FunnelCharacter_{pal_id}.uasset")
                        compile_uasset(uasset_gui_exe, out_fn_json, dest_fn_uasset, usmap_path)
                        log(f"  ✓ Compiled standalone funnel blueprint: {dest_fn_uasset}", "success")

                    source_boss_name = f"{source_funnel_name}_BOSS2"
                    seed_boss_rel = f"Pal/Content/Pal/Blueprint/Character/Funnel/{source_boss_name}.uasset"
                    extract_game_files(settings, [seed_boss_rel, seed_boss_rel.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
                    seed_boss_uasset = os.path.join(temp_dir, seed_boss_rel)
                    seed_boss_json = os.path.join(temp_dir, f"{source_boss_name}.json")

                    if decompile_uasset(uasset_gui_exe, seed_boss_uasset, seed_boss_json, usmap_path):
                        with open(seed_boss_json, "r", encoding="utf-8") as f_sb:
                            boss_str = f_sb.read()

                        boss_str = boss_str.replace(source_boss_name, f"BP_FunnelCharacter_{pal_id}_BOSS")
                        boss_str = boss_str.replace(source_funnel_name, f"BP_FunnelCharacter_{pal_id}")
                        boss_str = boss_str.replace(f"SK_{funnel_base}", f"SK_{pal_id}")

                        boss_ast = json.loads(boss_str)
                        sync_namemap(boss_ast)

                        out_boss_json = os.path.join(temp_dir, f"BP_FunnelCharacter_{pal_id}_BOSS.json")
                        with open(out_boss_json, "w", encoding="utf-8") as f_out_boss:
                            json.dump(boss_ast, f_out_boss, indent=2)

                        dest_boss_uasset = os.path.join(funnel_cooked_dir, f"BP_FunnelCharacter_{pal_id}_BOSS.uasset")
                        compile_uasset(uasset_gui_exe, out_boss_json, dest_boss_uasset, usmap_path)
                        log(f"  ✓ Compiled standalone funnel boss blueprint: {dest_boss_uasset}", "success")
                else:
                    mgr.clear_partner_funnel()

                # 5k. Cooperation Action Cleanup & Guaranteed Binding
                has_coop = (
                    is_riding_active or
                    is_weapon_active or
                    is_funnel_active or
                    (utility.get("SkillType") and utility.get("SkillType") != "None")
                )
                if not has_coop:
                    mgr.remove_ai_action("EPalAIActionType::Cooperation")
                elif is_riding_active:
                    mgr.set_ai_action("EPalAIActionType::Cooperation", "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionRideCall.BP_AIActionRideCall_C")

            # --- CRITICAL FIX: Repair Corrupted AST Pointers (Runs for ALL pals and variants!) ---
            # UAssetAPI shifts import arrays during string replacements. We must explicitly
            # re-link the SkeletalMesh and AnimClass pointers to prevent D3D11 Buffer Crashes.
            skel_mesh_idx = None
            anim_class_idx = None
            
            for i, imp in enumerate(base_json_data.get("Imports", [])):
                if imp.get("ClassName") == "SkeletalMesh" and pal_id.lower() in imp.get("ObjectName", "").lower():
                    skel_mesh_idx = -(i + 1)
                elif imp.get("ClassName") == "AnimBlueprintGeneratedClass" and imp.get("ObjectName", "").endswith("_C") and pal_id.lower() in imp.get("ObjectName", "").lower():
                    anim_class_idx = -(i + 1)

            for exp in base_json_data.get("Exports", []):
                if exp.get("ObjectName") == "CharacterMesh0":
                    for p in exp.get("Data", []):
                        p_name = p.get("Name")
                        if p_name in ["SkeletalMesh", "SkinnedAsset"] and skel_mesh_idx:
                            p["Value"] = skel_mesh_idx
                        elif p_name == "AnimClass" and anim_class_idx:
                            p["Value"] = anim_class_idx

        # -----------------------------------------------------------------
        # STEP 6: Compile Host Actor Blueprint
        # -----------------------------------------------------------------
        sync_namemap(base_json_data)
        out_host_json = os.path.join(temp_dir, f"BP_{pal_id}.json")
        with open(out_host_json, "w", encoding="utf-8") as f:
            json.dump(base_json_data, f, indent=4)

        dest_base_uasset = os.path.join(cooked_bp_dir, f"BP_{pal_id}.uasset")
        if os.path.exists(dest_base_uasset):
            try:
                os.remove(dest_base_uasset)
            except OSError:
                pass

        compile_ok = compile_uasset(uasset_gui_exe, out_host_json, dest_base_uasset, usmap_path)
        if not compile_ok or not os.path.exists(dest_base_uasset):
            log(f"  ❌ Failed to compile Actor Blueprint: BP_{pal_id}.uasset", "error")
            return False
        log(f"  ✓ Compiled Actor Blueprint: BP_{pal_id}.uasset", "success")

        # -----------------------------------------------------------------
        # STEP 7: Build Variants (Boss & Predator)
        # -----------------------------------------------------------------
        base_json_str = json.dumps(base_json_data, indent=4)
        boss_scale = float(pal_data.get("BossScale", 1.4))
        generate_boss = pal_data.get("GenerateBoss", True) is not False
        generate_predator = bool(pal_data.get("GeneratePredator", False))

        if generate_boss:
            build_boss_variant(base_json_str, template_id, pal_id, boss_scale, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, usmap_path=usmap_path)
        if generate_predator:
            build_predator_variant(template_id, pal_id, generate_boss, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, usmap_path=usmap_path)
            
        # Automatically compile Raid Boss variant if template contains BP_{template_id}_RAID
        build_raid_variant(template_id, pal_id, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, usmap_path=usmap_path)

        # Retain temp folder if requested for debugging
        if not (keep_temp or "--keep-temp" in sys.argv):
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            log(f"  [Debug] Retaining temporary JSON and AST files at: {temp_dir}", "standard")
        return True

    except Exception as e:
        log(f"Fatal error during blueprint synthesis: {e}", "error")
        if not (keep_temp or "--keep-temp" in sys.argv):
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            log(f"  [Debug] Retaining temporary JSON and AST files after failure at: {temp_dir}", "standard")
        return False