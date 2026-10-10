# pythoncli/utils/cli/mod_handlers.py
import os
import sys
import json
import shutil
import subprocess
from utils.config import validate_settings
from utils.cli.shared import json_print, error_print, system_open_path
from utils.scanner import get_mod_info
from utils.audio_helper import apply_custom_audio_worker, clear_audio_worker

def resolve_source_template(mod_data: dict | None, settings: dict, base_pal: str, mod_name: str) -> tuple[str, bool]:
    """
    Determines the source Pal template to dump/clone animations from.
    For standalone custom Pals (e.g. Katress_big_head -> CatMage), returns ('CatMage', True).
    For standard variants (e.g. Delphox -> GrimGirl), returns (base_pal, False).
    """
    fmodel_path = mod_data.get("fmodel_path", "") if mod_data else ""
    
    # 1. Check import_config.json
    if fmodel_path and os.path.exists(fmodel_path):
        cfg_file = os.path.join(fmodel_path, "import_config.json")
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    t_id = cfg.get("template_id")
                    is_custom = cfg.get("is_custom_pal", False)
                    if is_custom and t_id:
                        return t_id, True
            except Exception: pass

    # 2. Check Pal Creator JSON
    fmodel_base = settings.get("fmodel_output", "")
    if fmodel_base:
        creator_json = os.path.normpath(os.path.join(
            fmodel_base, "Exports", "Pal", "Content", "Palbaker", "Creator", f"{mod_name}_creator.json"
        ))
        if os.path.exists(creator_json):
            try:
                with open(creator_json, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    t_id = cdata.get("TemplateID")
                    if t_id:
                        return t_id, True
            except Exception: pass

    return base_pal, False

def check_vanilla_collision(mods: list[dict], target_mod_data: dict) -> tuple[bool, str]:
    """Ensures multiple Vanilla mode mods targeting the same BasePal do not overwrite each other."""
    if target_mod_data.get("is_dynamic_pals_active", False):
        return True, ""
        
    base_pal = target_mod_data.get("base_pal")
    mod_name = target_mod_data.get("mod_name")
    
    for m in mods:
        if m.get("base_pal") == base_pal and m.get("mod_name") != mod_name:
            if not m.get("is_dynamic_pals_active", False) and m.get("has_ue", False):
                return False, f"Collision Lock: Mod '{m['mod_name']}' is already using Vanilla mode for base '{base_pal}' and is pushed to Unreal Engine. Please switch one of these mods to Dynamic Pals mode to prevent them from overwriting each other in the Editor."
    return True, ""

def get_category_from_path(path: str | None) -> str:
    if not path:
        return "Monster"
    parts = path.replace("\\", "/").split("/")
    if "Character" in parts:
        idx = parts.index("Character")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "Monster"

def verify_unreal_connection(settings: dict) -> tuple[bool, str, str]:
    from utils.plugins.installer import is_unreal_running
    if not is_unreal_running():
        return False, "UNREAL_CLOSED", "Unreal Editor is not running. Please launch the editor first."
        
    from utils.plugins.detector import check_remote_execution_settings
    uproject = settings.get("uproject", "")
    if uproject and not check_remote_execution_settings(uproject):
        return False, "REMOTE_EXEC_DISABLED", "Python Remote Execution is currently disabled in your project's settings."
        
    try:
        from utils.cli.ping_helper import run_unreal_ping
        res = run_unreal_ping(settings)
        if res.get("diagnostic_code") != "FULLY_CONNECTED":
            return False, res.get("diagnostic_code", "TIMEOUT"), f"UDP handshake with Unreal Editor failed: {res.get('message', 'Connection Timeout')}"
    except Exception as e:
        return False, "CRASH", f"Unreal remote connection check failed: {str(e)}"
        
    return True, "FULLY_CONNECTED", ""

def verify_project_integrity(settings: dict) -> tuple[bool, str]:
    from utils.plugin_manager import check_project_requirements
    reqs = check_project_requirements(settings.get("ue_root", ""), settings.get("uproject", ""))
    
    if reqs.get("error"):
        return False, f"Project Validation Failed: {reqs['error']}"
        
    if reqs.get("needs_compile") or reqs.get("needs_plugin_sync") or reqs.get("plugin_outdated"):
        return False, "The PalBaker C++ Editor Helper Plugin is missing or outdated. Please verify project requirements in Settings."
        
    if reqs.get("missing_assets"):
        return False, "Your Unreal project is missing crucial master materials. Please verify project requirements in Settings."
        
    return True, ""

def run_build_mod_and_stream(base_pal: str, mod_name: str, category: str, action: str, preserve_override: bool = None, settings: dict = None):
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        cmd = [sys.executable, "internal-build-mod", base_pal, mod_name, category, action]
    else:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        build_mod_path = os.path.join(repo_root, "build_mod.py")
        cmd = [sys.executable, "-u", build_mod_path, base_pal, mod_name, category, action]
        
    if preserve_override is True:
        cmd.append("--preserve-materials")
    elif preserve_override is False:
        cmd.append("--overwrite-materials")
    
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    error_context = []
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
            bufsize=1
        )
        
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                if not line: break
                line_clean = line.strip()
                if not line_clean: continue
                
                if line_clean.startswith("{") and line_clean.endswith("}"):
                    try:
                        json.loads(line_clean)
                        print(line_clean, flush=True)
                        continue
                    except json.JSONDecodeError:
                        pass
                
                percent = 0.0
                is_progress = False
                
                if "running headless blender" in line_clean.lower() or "exporting fbx" in line_clean.lower():
                    percent = 0.15; is_progress = True
                elif "connecting to open unreal engine" in line_clean.lower():
                    percent = 0.35; is_progress = True
                elif "importing texture:" in line_clean.lower() or "importing skeletal mesh:" in line_clean.lower():
                    percent = 0.55; is_progress = True
                elif "cooking target folders" in line_clean.lower():
                    percent = 0.75; is_progress = True
                elif "building final pak" in line_clean.lower():
                    percent = 0.95; is_progress = True
                    
                if is_progress:
                    json_print({"type": "progress", "percent": percent, "message": line_clean})
                    
                level = "error" if "error" in line_clean.lower() else ("warning" if "warning" in line_clean.lower() else "standard")
                
                if level == "error" and "0 error" not in line_clean.lower() and "warning/error summary" not in line_clean.lower():
                    error_context.append(line_clean)
                    
                json_print({"type": "log", "level": level, "message": line_clean})
                
        proc.wait()
        if proc.returncode == 0:
            json_print({"type": "result", "status": "success", "message": f"Successfully completed action: {action}"})
            if settings:
                from utils.notifications import trigger_action_complete
                trigger_action_complete(action, mod_name, settings, success=True)
        else:
                err_msg = f"Pipeline action {action} failed with exit code: {proc.returncode}"
                if error_context:
                    # Prioritize logs that specifically identify the broken asset or compiler failure
                    asset_errors = [
                        e for e in error_context 
                        if "[assetlog]" in e.lower() or ".uasset" in e.lower() or "[compiler]" in e.lower()
                    ]
                    if asset_errors:
                        err_msg += f"\n{asset_errors[-1]}"
                    else:
                        real_errors = [
                            e for e in error_context 
                            if "subprocess.calledprocesserror" not in e.lower() 
                            and "failed with exit code" not in e.lower() 
                            and "loginit: display: failure" not in e.lower()
                        ]
                        if real_errors:
                            err_msg += f"\n{real_errors[-1]}"
                        else:
                            err_msg += f"\n{error_context[-1]}"
                        
                json_print({"type": "result", "status": "error", "message": err_msg})
                sys.exit(proc.returncode)
            
    except Exception as e:
        json_print({"type": "result", "status": "error", "message": f"Pipeline execution crashed: {str(e)}"})
        sys.exit(1)


def handle_mod_command(args, settings):
    mod_data = None
    action = args.action
    base_pal = getattr(args, "base_pal", "")
    mod_name = args.mod
    
    preserve_override = None 
    if action == "push-preserve":
        action = "push"
        preserve_override = True
    elif action == "push-overwrite":
        action = "push"
        preserve_override = False
        
    if action == "extract":
        is_valid, err_msg = validate_settings(settings, ["fmodel_output", "palworld_exe"])
    elif action in ["create-blend", "set-icon", "open-source", "set-preserve-materials", "set-push-setting", "set-blacklist", "toggle-anims", "set-variant-pack"]:
        is_valid, err_msg = validate_settings(settings, ["fmodel_output"])
    elif action in ["open-ue", "open-pak"]:
        is_valid, err_msg = validate_settings(settings, ["uproject"])
    elif action in ["edit-anim", "save-notifies", "save-anims"]:
        anim_key = getattr(args, "key", "") or ""
        payload_data = getattr(args, "data", "") or getattr(args, "path", "") or "{}"
        handle_edit_anim(settings, mod_data, base_pal, mod_name, anim_key, payload_data)
    else:
        is_valid, err_msg = validate_settings(settings, ["fmodel_output", "ue_root", "uproject"])
        
    if not is_valid:
        error_print(err_msg)
        sys.exit(1)


    if action in ["push", "full", "decompile", "browse-ue", "recursive-cook", "push-anims"]:
        is_connected, err_code, err_msg = verify_unreal_connection(settings)
        if not is_connected:
            json_print({"status": "error", "error_code": err_code, "message": err_msg})
            sys.exit(1)

    if action in ["push", "full", "cook", "pack", "decompile"]:
        is_intact, integrity_msg = verify_project_integrity(settings)
        if not is_intact:
            json_print({"status": "error", "message": integrity_msg})
            sys.exit(1)

    mods = get_mod_info(settings, mod_name)
    
    # STRICT FILTERING: Prevent variant name collisions by matching base_pal if provided
    if base_pal:
        mods = [m for m in mods if m["base_pal"].lower() == base_pal.lower()]

    if not mods and action not in ["extract", "cancel-pipeline"]:
        error_print(f"Mod '{mod_name}' (Base: '{base_pal}') was not found on disk.")
        sys.exit(1)

    mod_data = mods[0] if mods else None

    # Vanilla Collision Lock Evaluator
    if action in ["push", "full", "cook", "pack"] and mod_data:
        is_safe, collision_msg = check_vanilla_collision(mods, mod_data)
        if not is_safe:
            error_print(collision_msg)
            sys.exit(1)

    if action == "extract":
        from utils.extractor import extract_pal_assets
        category = mod_data.get("category", "Monster") if mod_data else "Monster"
        success, msg = extract_pal_assets(settings, mod_name, category)
        json_print({"status": "success" if success else "error", "message": msg})
        if not success: sys.exit(1)

    elif action == "decompile":
        from utils.plugins.decompiler import run_decompile_pipeline
        category = mod_data.get("category") if (mod_data and mod_data.get("category")) else get_category_from_path(mod_data.get("fmodel_path") if mod_data else "")
        category_sanitized = category.replace(" ", "_")

        ue_path_disk = mod_data.get("ue_path", "") if mod_data else ""
        clean_ue = ue_path_disk.replace("\\", "/")

        if ue_path_disk and "Content/" in clean_ue:
            rel_content = clean_ue.split("Content/", 1)[1].rstrip("/")
            ue_virtual_path = f"/Game/{rel_content}"
            target_mesh_name = f"SK_{mod_name}"
        else:
            if mod_data and mod_data.get("is_variant", False):
                ue_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{base_pal}/{mod_name}"
                target_mesh_name = f"SK_{mod_name}"
            else:
                if mod_data and mod_data.get("is_dynamic_pals_active", False):
                    ue_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{base_pal}/{mod_name}"
                    target_mesh_name = f"SK_{mod_name}"
                else:
                    ue_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{base_pal}"
                    target_mesh_name = f"SK_{base_pal}"
                
        fmodel_path = mod_data.get("fmodel_path", "") if mod_data else ""
        if not fmodel_path:
            is_var = mod_data.get("is_variant", False) if mod_data else (base_pal != mod_name)
            if is_var:
                fmodel_path = os.path.normpath(os.path.join(
                    settings["fmodel_output"], 
                    "Exports", "Pal", "Content", "Pal", "Model", "Character", 
                    category, base_pal, mod_name
                ))
            else:
                fmodel_path = os.path.normpath(os.path.join(
                    settings["fmodel_output"], 
                    "Exports", "Pal", "Content", "Pal", "Model", "Character", 
                    category, base_pal
                ))
        
        success, msg = run_decompile_pipeline(
            settings["ue_root"],
            settings["uproject"],
            mod_name,
            fmodel_path,
            ue_virtual_path,
            settings["blender"],
            verbose=True,
            overwrite=getattr(args, "overwrite", False),
            target_mesh_name=target_mesh_name
        )
        if success: json_print({"status": "success", "message": msg})
        else:
            json_print({"status": "error", "message": msg})
            sys.exit(1)

    elif action == "set-icon":
        icon_path = getattr(args, "path", "")
        if not icon_path or not os.path.exists(icon_path):
            error_print("Source icon path was not provided or does not exist.")
            sys.exit(1)
        dest_icon = os.path.join(mod_data["fmodel_path"], f"T_{mod_name}_icon_normal.png")
        try:
            os.makedirs(os.path.dirname(dest_icon), exist_ok=True)
            shutil.copy2(icon_path, dest_icon)
            json_print({"status": "success", "message": f"Successfully imported custom icon to {dest_icon}"})
        except Exception as e:
            error_print(f"Failed to copy icon: {str(e)}")
            sys.exit(1)

    elif action == "toggle-anims":
        val_str = getattr(args, "path", "true")
        is_active = str(val_str).lower() in ["true", "on", "1"]
        sidecar_path = os.path.join(mod_data["fmodel_path"], f"{mod_name}_blend.json")
        if not os.path.exists(sidecar_path):
            error_print("Skeletal companion sidecar JSON file not found.")
            sys.exit(1)
        try:
            from utils.sidecar_helper import load_sidecar, save_sidecar
            sidecar_data = load_sidecar(sidecar_path)
            sidecar_data.setdefault("custom_animations", {})["is_active"] = is_active
            save_sidecar(sidecar_path, sidecar_data)
            json_print({"status": "success", "message": f"Custom animations {'enabled' if is_active else 'disabled'} for {mod_name}."})
        except Exception as e:
            error_print(f"Failed to toggle animation setting: {e}")
            sys.exit(1)

    elif action == "dump-anims":
        from utils.anim_patcher import harvest_pal_animation_inventory
        temp_dir = os.path.join(settings["fmodel_output"], ".temp_anim_harvest")
        shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)

        # Resolve whether this is a standalone custom Pal to harvest from parent template
        source_pal, is_custom = resolve_source_template(mod_data, settings, base_pal, mod_name)
        if is_custom:
            print(f"[PalBaker Anims] Standalone Custom Pal detected: Extracting parent template animations from '{source_pal}'...", flush=True)

        inventory, blend_spaces = harvest_pal_animation_inventory(settings, source_pal, temp_dir)
        sidecar_path = os.path.join(mod_data["fmodel_path"], f"{mod_name}_blend.json")

        # 1. RETARGET INVENTORY & BLENDSPACES IF CUSTOM PAL OR VARIANT
        if mod_name.lower() != source_pal.lower():
            print(f"[PalBaker Anims] Retargeting animation inventory '{source_pal}' -> '{mod_name}'...", flush=True)
            retargeted_inventory = {}
            for inv_k, inv_v in inventory.items():
                track = inv_v.get("nla_track_name", "")
                seq_name = f"AS_{mod_name}_{track}"
                mont_name = f"AM_{mod_name}_{track}"

                inv_v["sequence_asset"] = seq_name
                inv_v["montage_asset"] = mont_name
                if source_pal in inv_v.get("enum_key", ""):
                    inv_v["enum_key"] = inv_v["enum_key"].replace(source_pal, mod_name)
                if source_pal in inv_v.get("display_name", ""):
                    inv_v["display_name"] = inv_v["display_name"].replace(source_pal, mod_name)

                retargeted_inventory[seq_name] = inv_v
            inventory = retargeted_inventory

            retargeted_blend_spaces = {}
            for bs_k, bs_v in blend_spaces.items():
                new_bs = dict(bs_v)
                if source_pal in new_bs.get("asset_name", ""):
                    new_bs["asset_name"] = new_bs["asset_name"].replace(source_pal, mod_name)
                new_samples = []
                for smp in new_bs.get("samples", []):
                    smp_copy = dict(smp)
                    t_smp = smp_copy.get("clean_name", "")
                    smp_copy["animation"] = f"AS_{mod_name}_{t_smp}"
                    new_samples.append(smp_copy)
                new_bs["samples"] = new_samples
                retargeted_blend_spaces[bs_k] = new_bs
            blend_spaces = retargeted_blend_spaces

        # 2. DEDUPLICATING MERGE: Preserve user notifies & rest properties on matching tracks
        from utils.sidecar_helper import load_sidecar, save_sidecar
        sidecar_data = load_sidecar(sidecar_path)
        existing_anims = sidecar_data.get("custom_animations", {}).get("anims", {})

        for inv_k, inv_v in inventory.items():
            clean_t = (inv_v.get("nla_track_name") or "").lower()
            existing_match = None
            for ek, ev in existing_anims.items():
                if ek.lower() == inv_k.lower() or (isinstance(ev, dict) and (ev.get("nla_track_name") or "").lower() == clean_t):
                    existing_match = ev
                    break

            if existing_match:
                if existing_match.get("notifies"):
                    inv_v["notifies"] = existing_match["notifies"]
                if existing_match.get("sequence_notifies"):
                    inv_v["sequence_notifies"] = existing_match["sequence_notifies"]
                if existing_match.get("montage_notifies"):
                    inv_v["montage_notifies"] = existing_match["montage_notifies"]
                if "rest_props" in existing_match:
                    inv_v["rest_props"] = existing_match["rest_props"]
                if "in_nla" in existing_match:
                    inv_v["in_nla"] = existing_match["in_nla"]
                if existing_match.get("is_modified", False) and "enable_root_motion" in existing_match:
                    inv_v["enable_root_motion"] = existing_match["enable_root_motion"]

        sidecar_data.setdefault("custom_animations", {})["is_active"] = True
        sidecar_data["custom_animations"]["anims"] = inventory
        sidecar_data["custom_animations"]["blend_spaces"] = blend_spaces
        save_sidecar(sidecar_path, sidecar_data)

        # 3. Extract only AS_ .psa sequence files from the source Pal's archives
        psa_dir = os.path.join(temp_dir, "psa")
        os.makedirs(psa_dir, exist_ok=True)
        from utils.extractor.core import extract_game_files
        extract_game_files(settings, [f"*Animation/Character/*/{source_pal}/AS_*"], psa_dir, format_type="auto")

        # 4. Run headless Blender to import actions into NLA
        blend_file = os.path.join(mod_data["fmodel_path"], f"{mod_name}.blend")
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        importer_script = os.path.join(repo_root, "utils", "blender_dump_anims.py")

        from utils.builder.blender_helper import run_headless_blender
        result = run_headless_blender(
            settings["blender"],
            blend_file,
            importer_script,
            ["--blend", blend_file, "--psa-dir", psa_dir, "--sidecar", sidecar_path, "--base-pal", source_pal, "--mod-name", mod_name]
        )
        if result.stdout.strip():
            print(result.stdout, flush=True)

        shutil.rmtree(temp_dir, ignore_errors=True)

        # 5. Sync in_nla status back into blend_spaces samples
        final_sidecar = load_sidecar(sidecar_path)
        anims_state = final_sidecar.get("custom_animations", {})
        final_anims = anims_state.get("anims", {})

        has_any_nla = any(a.get("in_nla", False) for a in final_anims.values())
        anims_state["is_active"] = has_any_nla

        for bs_key, bs_data in anims_state.get("blend_spaces", {}).items():
            for sample in bs_data.get("samples", []):
                matching = final_anims.get(sample["animation"])
                if matching:
                    sample["in_nla"] = matching.get("in_nla", False)

        save_sidecar(sidecar_path, final_sidecar)
        total_mapped = len(final_anims)

        json_print({
            "status": "success",
            "message": f"Successfully dumped and retargeted {total_mapped} animations for {mod_name}!",
            "custom_animations": final_sidecar.get("custom_animations")
        })

    elif action == "save-anims":
        payload_str = getattr(args, "path", "{}")
        sidecar_path = os.path.join(mod_data["fmodel_path"], f"{mod_name}_blend.json")
        try:
            from utils.sidecar_helper import load_sidecar, save_sidecar
            sidecar_data = load_sidecar(sidecar_path)
            sidecar_data["custom_animations"] = json.loads(payload_str)
            save_sidecar(sidecar_path, sidecar_data)
            json_print({"status": "success", "message": "Saved animation parameters."})
        except Exception as e:
            error_print(f"Failed to save animation properties: {e}")
            sys.exit(1)

        
    elif action == "push-anims":
        blend_file = os.path.join(mod_data["fmodel_path"], f"{mod_name}.blend")
        export_anims_dir = os.path.join(mod_data["fmodel_path"], ".temp_export_anims")
        shutil.rmtree(export_anims_dir, ignore_errors=True)
        os.makedirs(export_anims_dir, exist_ok=True)

        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        exporter_script = os.path.join(repo_root, "utils", "blender_export_anims.py")
        
        # Step 1: Export individual FBXs
        cmd = [
            settings["blender"], "-b", blend_file,
            "--python", exporter_script, "--",
            "--output-dir", export_anims_dir,
            "--mod-name", mod_name,
            "--base-pal", base_pal
        ]
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        blender_res = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding="utf-8", 
            errors="replace", 
            creationflags=creation_flags
        )
        if blender_res.stdout and blender_res.stdout.strip():
            print(blender_res.stdout, flush=True)

        source_pal, is_custom = resolve_source_template(mod_data, settings, base_pal, mod_name)

        # Harvest Root Motion sequences from sidecar
        from utils.sidecar_helper import load_sidecar
        sidecar_path = os.path.join(mod_data["fmodel_path"], f"{mod_name}_blend.json")
        if not os.path.exists(sidecar_path):
            sidecar_path = os.path.join(mod_data["fmodel_path"], f"{base_pal}_blend.json")

        sidecar_data = load_sidecar(sidecar_path) if os.path.exists(sidecar_path) else {}
        anims_dict = sidecar_data.get("custom_animations", {}).get("anims", {})

        root_motion_sequences = []
        for anim_k, anim_v in anims_dict.items():
            if isinstance(anim_v, dict) and anim_v.get("enable_root_motion"):
                seq_name = anim_v.get("sequence_asset") or anim_k
                root_motion_sequences.append(seq_name)
                track = anim_v.get("nla_track_name")
                if track:
                    root_motion_sequences.append(track)
                    root_motion_sequences.append(f"AS_{mod_name}_{track}")
                    root_motion_sequences.append(f"AS_{base_pal}_{track}")

        # Step 2: Configure Unreal Batch Import
        import tempfile
        temp_dir = tempfile.gettempdir()
        cfg_path = os.path.join(temp_dir, "palbaker_anim_import_config.json")
        with open(cfg_path, "w", encoding="utf-8") as f_cfg:
            json.dump({
                "anims_dir": export_anims_dir,
                "mod_name": mod_name,
                "base_pal": base_pal,
                "template_id": source_pal,
                "is_custom_pal": is_custom,
                "category": mod_data.get("category", "Monster"),
                "root_motion_sequences": root_motion_sequences,
                "sidecar_path": sidecar_path
            }, f_cfg, indent=4)

        import_script = os.path.join(repo_root, "unreal_scripts", "import_anims.py").replace("\\", "/")
        target_project_name = os.path.splitext(os.path.basename(settings["uproject"]))[0]
        cmd_import = f'import warnings; warnings.filterwarnings("ignore"); f = open(r"{import_script}", encoding="utf-8"); exec(f.read()); f.close()'
        
        from utils.builder.unreal_helper import run_remote_command, focus_unreal_window
        success, ue_msg = run_remote_command(settings["ue_root"], target_project_name, cmd_import)
        if ue_msg.strip():
            print(ue_msg, flush=True)

        if not success:
            error_print("Failed to push animations to Unreal Editor.")
            sys.exit(1)

        # Clean temporary staging directory and config
        shutil.rmtree(export_anims_dir, ignore_errors=True)
        try: os.remove(cfg_path)
        except OSError: pass

        category_sanitized = mod_data.get('category', 'Monster').replace(' ', '_')
        is_var = (not is_custom and base_pal.lower() != mod_name.lower())
        anims_vpath = f"/Game/Pal/Animation/Character/{category_sanitized}/{base_pal}/{mod_name}" if is_var else f"/Game/Pal/Animation/Character/{category_sanitized}/{mod_name}"
        
        sync_cmd = f'import unreal; unreal.EditorUtilityLibrary.sync_browser_to_folders(["{anims_vpath}"]); unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["{anims_vpath}"], True)'
        run_remote_command(settings["ue_root"], target_project_name, sync_cmd)
        focus_unreal_window(target_project_name)

        json_print({
            "status": "success",
            "message": f"Successfully imported animations into Unreal! Montages will compile on Cook."
        })
        
        from utils.notifications import trigger_action_complete
        trigger_action_complete("push-anims", mod_name, settings, success=True)

    elif action == "set-preserve-materials":
        val_str = getattr(args, "path", "true")
        preserve_bool = str(val_str).lower() == "true"
        sidecar_path = os.path.join(mod_data["fmodel_path"], f"{mod_name}_blend.json")
        if not os.path.exists(sidecar_path):
            error_print("Skeletal companion sidecar JSON file not found. Generate the .blend file first!")
            sys.exit(1)
        try:
            from utils.sidecar_helper import update_sidecar_fields
            update_sidecar_fields(sidecar_path, preserve_materials=preserve_bool)
            json_print({"status": "success", "message": f"Successfully updated material preservation to {preserve_bool} for {mod_name}."})
        except Exception as e:
            error_print(f"Failed to save material preservation setting: {e}")
            sys.exit(1)

    elif action == "set-push-setting":
        setting_key = getattr(args, "key", "materials")
        val_str = getattr(args, "path", "true")
        bool_val = str(val_str).lower() == "true"
        sidecar_path = os.path.join(mod_data["fmodel_path"], f"{mod_name}_blend.json")
        if not os.path.exists(sidecar_path):
            error_print("Skeletal companion sidecar JSON file not found. Generate the .blend file first!")
            sys.exit(1)
        try:
            from utils.sidecar_helper import update_sidecar_fields
            full_key = f"push_{setting_key}"
            update_sidecar_fields(sidecar_path, **{full_key: bool_val})
            json_print({"status": "success", "message": f"Successfully updated {full_key} to {bool_val} for {mod_name}."})
        except Exception as e:
            error_print(f"Failed to save push setting: {e}")
            sys.exit(1)

    elif action == "set-blacklist":
        val_str = getattr(args, "path", "[]")
        try:
            blacklist_array = json.loads(val_str)
        except Exception:
            blacklist_array = []
        sidecar_path = os.path.join(mod_data["fmodel_path"], f"{mod_name}_blend.json")
        if not os.path.exists(sidecar_path):
            error_print("Skeletal companion sidecar JSON file not found. Generate the .blend file first!")
            sys.exit(1)
        try:
            from utils.sidecar_helper import update_sidecar_fields
            update_sidecar_fields(sidecar_path, custom_blacklist=blacklist_array)
            json_print({"status": "success", "message": f"Successfully updated custom packaging blacklist for {mod_name}."})
        except Exception as e:
            error_print(f"Failed to save blacklist setting: {e}")
            sys.exit(1)

    elif action == "set-variant-pack":
        val_str = getattr(args, "path", "true") or "true"
        include_bool = str(val_str).lower() in ["true", "1", "yes", "on"]

        fmodel_base = settings.get("fmodel_output", "")
        category = mod_data.get("category", "Monster") if mod_data else "Monster"
        parent_dir = os.path.normpath(os.path.join(
            fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal
        )) if fmodel_base else ""

        if not parent_dir or not os.path.exists(parent_dir):
            if mod_data and mod_data.get("fmodel_path"):
                parent_dir = os.path.dirname(mod_data["fmodel_path"]) if mod_data.get("is_variant") else mod_data["fmodel_path"]

        if not parent_dir or not os.path.exists(parent_dir):
            error_print(f"Parent directory for base pal '{base_pal}' not found on disk.")
            sys.exit(1)

        from utils.state import set_variant_pack_state
        state = set_variant_pack_state(parent_dir, mod_name, include_bool)
        json_print({
            "status": "success",
            "message": f"Updated packaging status for variant '{mod_name}' (include_in_pak: {include_bool}).",
            "skipped_variants": state.get("skipped_variants", [])
        })

    elif action == "browse-ue":
        ue_path_disk = mod_data.get("ue_path", "") if mod_data else ""
        clean_ue = ue_path_disk.replace("\\", "/")

        # 1. If it exists in Unreal, convert the physical Content path directly to /Game/...
        if ue_path_disk and "Content/" in clean_ue:
            rel_content = clean_ue.split("Content/", 1)[1].rstrip("/")
            ue_virtual_path = f"/Game/{rel_content}"
        else:
            # 2. Otherwise prioritize the scanner's category over fmodel_path
            category = mod_data.get("category") if (mod_data and mod_data.get("category")) else get_category_from_path(mod_data.get("fmodel_path") if mod_data else "")
            category_sanitized = category.replace(" ", "_")
            if mod_data and mod_data.get("is_variant"):
                ue_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{base_pal}/{mod_name}"
            else:
                ue_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{base_pal}"
            
        python_cmd = f'import unreal; unreal.EditorUtilityLibrary.sync_browser_to_folders(["{ue_virtual_path}"])'
        from utils.builder.unreal_helper import run_remote_command, focus_unreal_window
        target_project_name = os.path.splitext(os.path.basename(settings["uproject"]))[0]
        
        success, msg = run_remote_command(settings["ue_root"], target_project_name, python_cmd)
        if success:
            focus_unreal_window(target_project_name)
            json_print({"status": "success", "message": f"Focused Unreal Content Browser to: {ue_virtual_path}"})
        else:
            json_print({"status": "error", "message": f"Failed to focus Unreal: {msg}"})
            sys.exit(1)

    elif action in ["open-source", "open-ue", "open-pak"]:
        if action == "open-source":
            path = mod_data.get("fmodel_path", "") if mod_data else ""
            if not path or not os.path.exists(path):
                error_print(f"Source folder for {args.mod} does not exist on disk.")
                sys.exit(1)
            system_open_path(path)
        elif action == "open-ue":
            path = mod_data.get("ue_path", "") if mod_data else ""
            if not path or not os.path.exists(path):
                error_print(f"Unreal assets folder for {args.mod} does not exist on disk. Have you run 'Push to Unreal' yet?")
                sys.exit(1)
            system_open_path(path)
        elif action == "open-pak":
            path = mod_data.get("pak_path", "") if mod_data else ""
            if not path or not os.path.exists(path):
                error_print(f"Compiled PAK file for {args.mod} does not exist on disk. Have you cooked and packaged the mod yet?")
                sys.exit(1)
            system_open_path(path, is_file=True)
        json_print({"status": "success", "message": "Opened directory successfully."})

    elif action == "cancel-pipeline":
        from utils.plugins.installer import close_unreal_editor
        close_unreal_editor()
        if os.name == 'nt':
            subprocess.run(["taskkill", "/F", "/T", "/IM", "UnrealPak.exe"], capture_output=True, creationflags=0x08000000)
            subprocess.run(["taskkill", "/F", "/T", "/IM", "blender.exe"], capture_output=True, creationflags=0x08000000)
        json_print({"status": "success", "message": "Backend compilation pipeline forcibly cancelled."})

    else:
        category = mod_data.get("category") if (mod_data and mod_data.get("category")) else get_category_from_path(mod_data.get("fmodel_path") if mod_data else "")
        action_mapping = {
            "create-blend": "create_blend",
            "refresh-blend": "refresh_blend",
            "cook-only": "cook_only",
            "pack-only": "pack_only",
            "recursive-cook": "recursive_cook"
        }
        build_action = action_mapping.get(action, action)
        run_build_mod_and_stream(base_pal, mod_name, category, build_action, preserve_override, settings)

def handle_edit_anim(settings: dict, mod_data: dict | None, base_pal: str, mod_name: str, anim_key: str, data_payload: str):
    fmodel_path = mod_data.get("fmodel_path", "") if mod_data else ""
    
    # Self-healing path resolution if mod_data is empty
    if not fmodel_path or not os.path.exists(fmodel_path):
        fmodel_base = settings.get("fmodel_output", "")
        if fmodel_base:
            for cat in ["Monster", "Pending Monster", "Player", "NPC", "Palmi", "Normal", "RaidMonster", "RaidBoss"]:
                c1 = os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", cat, base_pal, mod_name))
                c2 = os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", cat, mod_name))
                c3 = os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", cat, base_pal))
                for c in [c1, c2, c3]:
                    if os.path.exists(c):
                        fmodel_path = c
                        break
                if fmodel_path:
                    break

    if not fmodel_path or not os.path.exists(fmodel_path):
        error_print(f"Workspace path for '{mod_name}' does not exist on disk.")
        sys.exit(1)

    # Locate sidecar case-insensitively (supports EmberPup_blend.json or Emberpup_blend.json)
    sidecar_path = None
    for f in os.listdir(fmodel_path):
        if f.lower() == f"{mod_name.lower()}_blend.json":
            sidecar_path = os.path.join(fmodel_path, f)
            break

    if not sidecar_path or not os.path.exists(sidecar_path):
        sidecar_path = os.path.join(fmodel_path, f"{mod_name}_blend.json")

    from utils.sidecar_helper import load_sidecar, save_sidecar
    sidecar_data = load_sidecar(sidecar_path)
    custom_anims = sidecar_data.setdefault("custom_animations", {})
    anims_dict = custom_anims.setdefault("anims", {})

    # Parse incoming payload
    try:
        payload = json.loads(data_payload) if isinstance(data_payload, str) and data_payload else (data_payload or {})
    except Exception as e:
        error_print(f"Failed to parse JSON payload for edit-anim: {e}")
        sys.exit(1)

    op = payload.get("op", "upsert")

    if not anim_key:
        anim_key = payload.get("key") or payload.get("anim_key") or payload.get("animation") or ""

    if not anim_key:
        error_print("Missing target animation key (--key <anim_key>).")
        sys.exit(1)

    from utils.blender_dump_anims import extract_track_name_simple
    clean_t = extract_track_name_simple(anim_key, base_pal, mod_name)
    canonical_seq_key = f"AS_{mod_name}_{clean_t}"

    # Resolve target entry case-insensitively
    target_key = None
    target_entry = None
    anim_key_lower = anim_key.lower().strip()

    for k, v in anims_dict.items():
        if k.lower() in [anim_key_lower, canonical_seq_key.lower()]:
            target_key = k
            target_entry = v
            break

    if not target_entry:
        for k, v in anims_dict.items():
            if isinstance(v, dict):
                v_track = (v.get("nla_track_name") or "").lower()
                v_seq = (v.get("sequence_asset") or "").lower()
                v_mont = (v.get("montage_asset") or "").lower()
                if clean_t.lower() in [v_track, v_seq, v_mont]:
                    target_key = k
                    target_entry = v
                    break

    # Always enforce canonical AS_ key for sidecar dictionary consistency
    if not target_key or target_key.startswith("AM_"):
        target_key = canonical_seq_key

    # 1. Action: Delete animation
    if op in ["delete_anim", "remove_anim"]:
        anims_dict.pop(target_key, None)
        save_sidecar(sidecar_path, sidecar_data)
        json_print({"status": "success", "message": f"Deleted animation '{target_key}' from sidecar."})
        return

    # 2. If not existing, create a fresh entry
    if not target_entry:
        from utils.blender_dump_anims import extract_track_name_simple
        clean_t = extract_track_name_simple(anim_key, base_pal, mod_name)
        target_entry = {
            "category": payload.get("category", "GeneralMontage"),
            "enum_key": payload.get("enum_key", clean_t),
            "display_name": payload.get("display_name", clean_t.replace("_", " ")),
            "sequence_asset": target_key,
            "montage_asset": f"AM_{mod_name}_{clean_t}",
            "nla_track_name": clean_t,
            "in_nla": payload.get("in_nla", True),
            "is_modified": True,
            "notifies": [],
            "enable_root_motion": bool(payload.get("enable_root_motion", False))
        }

    # 3. Apply Granular Operations or Property Patches
    if op == "set_root_motion":
        target_entry["enable_root_motion"] = bool(payload.get("enable_root_motion", True))
        target_entry["is_modified"] = True

    elif op == "add_notify":
        new_items = payload.get("notifies") or ([payload["notify"]] if "notify" in payload else [])
        target_entry.setdefault("notifies", []).extend(new_items)
        target_entry["is_modified"] = True

    elif op == "delete_notify":
        idx = payload.get("index")
        notifies = target_entry.get("notifies", [])
        if isinstance(idx, int) and 0 <= idx < len(notifies):
            notifies.pop(idx)
            target_entry["is_modified"] = True

    elif op == "update_notify":
        idx = payload.get("index")
        notify = payload.get("notify")
        notifies = target_entry.setdefault("notifies", [])
        if isinstance(idx, int) and 0 <= idx < len(notifies) and isinstance(notify, dict):
            notifies[idx] = notify
            target_entry["is_modified"] = True

    elif op == "set_notifies":
        target_entry["notifies"] = payload.get("notifies", [])
        target_entry["is_modified"] = True

    elif op == "set_rest":
        target_entry["rest_props"] = payload.get("rest_props", {})
        target_entry["category"] = "RandomRest"
        target_entry["is_modified"] = True

    else:
        # Standard upsert: merge provided fields (sequence_asset, notifies, etc.)
        fields = payload.get("patch") if "patch" in payload else payload
        for f_name, f_val in fields.items():
            if f_name in ["op", "key", "anim_key"]:
                continue
            if f_name == "enable_root_motion":
                target_entry[f_name] = bool(f_val)
            else:
                target_entry[f_name] = f_val
        target_entry["is_modified"] = True


    anims_dict[target_key] = target_entry
    custom_anims["is_active"] = True

    save_sidecar(sidecar_path, sidecar_data)
    json_print({
        "status": "success",
        "message": f"Successfully updated animation '{target_key}'.",
        "key": target_key,
        "entry": target_entry
    })
    sys.exit(0)

def handle_audio_command(args, settings):
    base_pal = args.base_pal
    mod_name = args.mod
    cry_name = args.cry
    path = getattr(args, "path", "")
    subcommand = args.subcommand
    
    is_valid, err_msg = validate_settings(settings, ["fmodel_output"])
    if not is_valid:
        error_print(err_msg)
        sys.exit(1)

    mods = get_mod_info(settings, mod_name)
    if base_pal:
        mods = [m for m in mods if m["base_pal"].lower() == base_pal.lower()]

    if not mods:
        error_print(f"Mod '{mod_name}' (Base: '{base_pal}') not found.")
        sys.exit(1)
        
    mod_data = mods[0]


    if subcommand == "set":
        success, msg = apply_custom_audio_worker(settings, mod_data, cry_name, path)
        if success: json_print({"status": "success", "message": msg})
        else:
            error_print(msg)
            sys.exit(1)

    elif subcommand == "clear":
        removed = clear_audio_worker(mod_data, cry_name)
        if removed: json_print({"status": "success", "message": f"Cleared audio for {cry_name}"})
        else:
            error_print(f"Failed to clear audio or no override found for {cry_name}")
            sys.exit(1)

    elif subcommand == "play":
        fmodel_path = mod_data.get("fmodel_path")
        audio_dir = os.path.join(fmodel_path, ".palbaker_audio", "sources") if fmodel_path else ""
        if audio_dir:
            for ext in [".wav", ".mp3", ".ogg"]:
                test_file = os.path.join(audio_dir, f"{cry_name}{ext}")
                if os.path.exists(test_file):
                    json_print({"status": "success", "message": "Playing custom preview.", "path": test_file})
                    sys.exit(0)
                    
        wem_rel = mod_data.get("sound_metadata", {}).get(cry_name, {}).get("wem_relative_path")
        if wem_rel:
            fmodel_root = settings.get("fmodel_output", "")
            wem_abs = os.path.normpath(os.path.join(fmodel_root, "Exports", wem_rel))
            
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            vgmstream_cli = os.path.join(repo_root, "deps", "vgmstream", "vgmstream-cli.exe")
            if not os.path.exists(vgmstream_cli):
                vgmstream_cli = os.path.join(repo_root, "deps", "vgmstream-cli.exe")
                
            if not os.path.exists(vgmstream_cli):
                error_print("Could not locate vgmstream-cli.exe to decode vanilla audio.")
                sys.exit(1)

            from utils.extractor.core import extract_single_file
            if not os.path.exists(wem_abs):
                export_root = os.path.join(fmodel_root, "Exports")
                success = extract_single_file(settings, wem_rel, export_root)
                if not success or not os.path.exists(wem_abs):
                    error_print(f"Failed to extract {wem_rel} from paks.")
                    sys.exit(1)

            if audio_dir:
                os.makedirs(audio_dir, exist_ok=True)
                temp_wav = os.path.join(audio_dir, f".temp_{cry_name}_preview.wav")
            else:
                import tempfile
                temp_wav = os.path.join(tempfile.gettempdir(), f"palbaker_{cry_name}_preview.wav")

            if os.path.exists(temp_wav):
                try: os.remove(temp_wav)
                except OSError: pass

            cmd_decode = [vgmstream_cli, "-o", temp_wav, wem_abs]
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            try:
                subprocess.run(cmd_decode, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
            except Exception as e:
                error_print(f"vgmstream failed to decode {wem_rel}: {e}")
                sys.exit(1)
            
            if os.path.exists(temp_wav):
                json_print({"status": "success", "message": "Playing vanilla preview.", "path": temp_wav})
                sys.exit(0)
            else:
                error_print("vgmstream executed but failed to save temporary preview wav.")
                sys.exit(1)
        else:
            error_print("No playable audio found.")
            sys.exit(1)