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

def check_vanilla_collision(mods: list[dict], target_mod_data: dict) -> tuple[bool, str]:
    """Ensures multiple Vanilla mode mods targeting the same BasePal do not overwrite each other."""
    if target_mod_data.get("is_altermatic_active", False):
        return True, ""
        
    base_pal = target_mod_data.get("base_pal")
    mod_name = target_mod_data.get("mod_name")
    
    for m in mods:
        if m.get("base_pal") == base_pal and m.get("mod_name") != mod_name:
            if not m.get("is_altermatic_active", False) and m.get("has_ue", False):
                return False, f"Collision Lock: Mod '{m['mod_name']}' is already using Vanilla mode for base '{base_pal}' and is pushed to Unreal Engine. Please switch one of these mods to Altermatic mode to prevent them from overwriting each other in the Editor."
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

def run_build_mod_and_stream(base_pal: str, mod_name: str, category: str, action: str, preserve_override: bool | None = None):
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
                json_print({"type": "log", "level": level, "message": line_clean})
                
        proc.wait()
        if proc.returncode == 0:
            json_print({"type": "result", "status": "success", "message": f"Successfully completed action: {action}"})
        else:
            json_print({"type": "result", "status": "error", "message": f"Pipeline action {action} failed with exit code: {proc.returncode}"})
            sys.exit(proc.returncode)
            
    except Exception as e:
        json_print({"type": "result", "status": "error", "message": f"Pipeline execution crashed: {str(e)}"})
        sys.exit(1)


def handle_mod_command(args, settings):
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
    elif action in ["create-blend", "set-icon", "open-source", "set-preserve-materials"]:
        is_valid, err_msg = validate_settings(settings, ["fmodel_output"])
    elif action in ["open-ue", "open-pak"]:
        is_valid, err_msg = validate_settings(settings, ["uproject"])
    else:
        is_valid, err_msg = validate_settings(settings, ["fmodel_output", "ue_root", "uproject"])
        
    if not is_valid:
        error_print(err_msg)
        sys.exit(1)

    if action in ["push", "full", "decompile", "browse-ue"]:
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
    if not mods and action not in ["extract", "cancel-pipeline"]:
        error_print(f"Mod {mod_name} was not found on disk.")
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
        category = get_category_from_path(mod_data["fmodel_path"] if mod_data else "")
        
        if mod_data and mod_data.get("is_variant", False):
            ue_virtual_path = f"/Game/Pal/Model/Character/{category}/{base_pal}/{mod_name}"
            target_mesh_name = f"SK_{mod_name}"
        else:
            if mod_data and mod_data.get("is_altermatic_active", False):
                ue_virtual_path = f"/Game/Pal/Model/Character/{category}/{base_pal}/{mod_name}"
                target_mesh_name = f"SK_{mod_name}"
            else:
                ue_virtual_path = f"/Game/Pal/Model/Character/{category}/{base_pal}"
                target_mesh_name = f"SK_{base_pal}"
                
        fmodel_path = mod_data.get("fmodel_path", "") if mod_data else ""
        if not fmodel_path:
            fmodel_path = os.path.normpath(os.path.join(
                settings["fmodel_output"], 
                "Exports", "Pal", "Content", "Pal", "Model", "Character", 
                category, base_pal, mod_name
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

    elif action == "browse-ue":
        category = get_category_from_path(mod_data["fmodel_path"])
        category_sanitized = category.replace(" ", "_")
        
        if mod_data["is_variant"]:
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

    # --- REFACTOR: KEYERROR GUARD AND EXPLICIT DIRECTORY VALIDATIONS ---
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
        category = get_category_from_path(mod_data["fmodel_path"] if mod_data else "")
        action_mapping = {
            "create-blend": "create_blend",
            "refresh-blend": "refresh_blend",
            "cook-only": "cook_only",
            "pack-only": "pack_only"
        }
        build_action = action_mapping.get(action, action)
        run_build_mod_and_stream(base_pal, mod_name, category, build_action, preserve_override)


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
    if not mods:
        error_print(f"Mod {mod_name} not found.")
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
