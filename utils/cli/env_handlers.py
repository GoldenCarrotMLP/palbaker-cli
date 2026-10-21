# utils/cli/env_handlers.py
import os
import sys
import json
import shutil
import glob
import subprocess
from utils.config import validate_settings
from utils.cli.shared import json_print, error_print

def handle_env_command(args, settings):
    """Router for all system environment subcommands."""
    subcommand = args.subcommand

    # 1. Route validation strictly for compile/editor commands only (Exempting 'verify'!)
    if subcommand in ["install-plugin", "launch-unreal", "restart-unreal"]:
        is_valid, err_msg = validate_settings(settings, ["ue_root", "uproject"])
    elif subcommand in ["ue4ss-install", "extract-icons", "palschema-install"]:
        is_valid, err_msg = validate_settings(settings, ["palworld_exe", "fmodel_output"])
    elif subcommand == "enable-remote-exec":
        is_valid, err_msg = validate_settings(settings, ["uproject"])
    else:
        is_valid = True
        err_msg = ""

    if not is_valid:
        error_print(err_msg)
        sys.exit(1)

    # 2. Handle 'env verify' (Strong Path and Environment Verification)
    if subcommand == "verify":
        from utils.plugin_manager import check_project_requirements
        
        try:
            path_errors = []
            verified_paths = {
                "uproject": False,
                "ue_binaries": False,
                "blender": False,
                "palworld_exe": False,
                "fmodel_output": False
            }

            # 1. Verify .uproject file
            uproject = settings.get("uproject", "")
            if not uproject:
                path_errors.append("UProject path is not configured.")
            elif not os.path.exists(uproject):
                path_errors.append(f"UProject file does not exist on disk: '{uproject}'")
            elif not os.path.isfile(uproject) or not uproject.lower().endswith(".uproject"):
                path_errors.append(f"Configured UProject path is not a .uproject file: '{uproject}'")
            else:
                verified_paths["uproject"] = True

            # 2. Verify Unreal Engine Binaries (UnrealEditor.exe, UnrealEditor-Cmd.exe, UnrealPak.exe)
            ue_root = settings.get("ue_root", "")
            if not ue_root:
                path_errors.append("Unreal Engine Root is not configured.")
            elif not os.path.exists(ue_root) or not os.path.isdir(ue_root):
                path_errors.append(f"Unreal Engine Root directory does not exist: '{ue_root}'")
            else:
                bin_dir = os.path.join(ue_root, "Engine", "Binaries", "Win64")
                required_binaries = ["UnrealEditor.exe", "UnrealEditor-Cmd.exe", "UnrealPak.exe"]
                
                if os.name != 'nt':
                    bin_dir_posix = os.path.join(ue_root, "Engine", "Binaries", "Linux")
                    if os.path.exists(bin_dir_posix):
                        bin_dir = bin_dir_posix
                        required_binaries = ["UnrealEditor", "UnrealEditor-Cmd", "UnrealPak"]

                missing_binaries = [b for b in required_binaries if not os.path.exists(os.path.join(bin_dir, b))]
                if missing_binaries:
                    path_errors.append(
                        f"Unreal Engine Root is missing binaries in '{bin_dir}': {', '.join(missing_binaries)}"
                    )
                else:
                    verified_paths["ue_binaries"] = True

            # 3. Verify Blender Executable
            blender = settings.get("blender", "")
            if not blender:
                path_errors.append("Blender executable path is not configured.")
            else:
                # Check PATH fallback
                if not os.path.exists(blender) and shutil.which(blender):
                    blender = shutil.which(blender)

                if not os.path.exists(blender):
                    path_errors.append(f"Blender executable does not exist on disk: '{blender}'")
                elif not os.path.isfile(blender):
                    path_errors.append(f"Configured Blender path is a folder, not an executable: '{blender}'")
                else:
                    b_name = os.path.basename(blender).lower()
                    if os.name == 'nt' and not b_name.endswith(".exe"):
                        path_errors.append(f"Configured Blender path does not point to an .exe file: '{blender}'")
                    else:
                        verified_paths["blender"] = True

            # 4. Verify Palworld Executable
            pal_exe = settings.get("palworld_exe", "")
            if not pal_exe:
                path_errors.append("Palworld executable path is not configured.")
            elif not os.path.exists(pal_exe):
                path_errors.append(f"Palworld executable does not exist on disk: '{pal_exe}'")
            elif not os.path.isfile(pal_exe):
                path_errors.append(f"Configured Palworld path is a folder, not an executable: '{pal_exe}'")
            else:
                exe_name = os.path.basename(pal_exe).lower()
                valid_exe_names = {
                    "palworld.exe", "palworld-win64-shipping.exe",
                    "palserver.exe", "palserver-win64-shipping.exe"
                }
                if os.name == 'nt' and exe_name not in valid_exe_names:
                    path_errors.append(
                        f"Configured Palworld executable name '{exe_name}' is invalid (expected Palworld.exe or Palworld-Win64-Shipping.exe)."
                    )
                else:
                    verified_paths["palworld_exe"] = True

            # 5. Verify Workspace Folder
            fmodel_base = settings.get("fmodel_output", "")
            if not fmodel_base:
                path_errors.append("Workspace folder (fmodel_output) is not configured.")
            elif not os.path.exists(fmodel_base) or not os.path.isdir(fmodel_base):
                path_errors.append(f"Workspace folder does not exist on disk: '{fmodel_base}'")
            else:
                verified_paths["fmodel_output"] = True

            # Check database and cache JSON files
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            deps_dir = os.path.join(repo_root, "deps")

            EXPECTED_DB_FILES = [
                "pal_names_map.json",
                "resolved_sound_map.json",
                "active_skills_cache.json",
                "passive_skills_cache.json",
                "coop_passives_cache.json",
                "partner_skills_cache.json",
                "monster_parameter_cache.json",
                "waza_master_level_cache.json",
                "monster_spawners_cache.json",
                "monster_spawners_default_map.json",
                "camera_offsets_cache.json",
                "pal_drop_item_cache.json",
                "items_cache.json",
                "breeding_combi_cache.json",
                "cage_pals_cache.json",
                "partner_skill_params_cache.json",
                "boss_spawners_cache.json"
            ]

            missing_db_files = [
                f for f in EXPECTED_DB_FILES 
                if not os.path.exists(os.path.join(deps_dir, f)) or os.path.getsize(os.path.join(deps_dir, f)) == 0
            ]
            needs_db_build = len(missing_db_files) > 0

            has_icons = False
            if verified_paths["fmodel_output"]:
                icon_dir = os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Texture", "PalIcon", "Normal"))
                has_icons = os.path.exists(icon_dir) and len(glob.glob(os.path.join(icon_dir, "*.png"))) > 10
            needs_icon_extraction = not has_icons

            # Run ModKit checks if UE binaries and .uproject are valid
            if verified_paths["uproject"] and verified_paths["ue_binaries"]:
                reqs = check_project_requirements(settings.get("ue_root", ""), settings.get("uproject", ""))
                reqs["unreal_skipped"] = False
            else:
                reqs = {
                    "error": None,
                    "needs_plugin_sync": False,
                    "plugin_outdated": False,
                    "needs_compile": False,
                    "needs_remote_exec_enable": False,
                    "needs_cooking_setup": False,
                    "needs_icon_extraction": needs_icon_extraction,
                    "missing_assets": [],
                    "unreal_skipped": True
                }

            reqs["needs_db_build"] = needs_db_build
            reqs["missing_db_files"] = missing_db_files
            reqs["path_errors"] = path_errors
            reqs["verified_paths"] = verified_paths

            # If any path error was found, report error and exit
            if path_errors:
                reqs["error"] = "\n".join(path_errors)
                for err in path_errors:
                    json_print({"type": "log", "level": "error", "message": f"❌ {err}"})
                json_print({
                    "status": "error",
                    "data": reqs,
                    "message": f"Environment path verification failed with {len(path_errors)} error(s)."
                })
                sys.exit(1)

            if reqs.get("needs_plugin_sync"):
                project_dir = os.path.dirname(settings["uproject"])
                dest_plugin_dir = os.path.join(project_dir, "Plugins", "PalBakerEditorUtils")
                if os.path.exists(dest_plugin_dir):
                    json_print({"type": "log", "level": "warning", "message": "The C++ Editor Helper Plugin is outdated. If compiling, close Unreal Editor first."})
                else:
                    json_print({"type": "log", "level": "standard", "message": "Required C++ Editor Helper Plugin is missing."})

            if reqs.get("needs_db_build"):
                missing_count = len(reqs.get("missing_db_files", []))
                json_print({
                    "type": "log", 
                    "level": "warning", 
                    "message": f"Pal database is incomplete ({missing_count} cache files missing). Rebuild required."
                })

            json_print({"status": "success", "data": reqs, "message": "All paths and binaries verified successfully."})
            sys.exit(0)

        except Exception as e:
            error_print(f"Prerequisite verification crashed: {str(e)}")
            sys.exit(1)

    # 3. Handle 'env install-plugin'
    elif subcommand == "install-plugin":
        from utils.plugin_manager import install_and_compile_plugin, inject_missing_assets
        action = getattr(args, "action", "install")

        project_dir = os.path.dirname(settings["uproject"])
        installed_plugin_dir = os.path.join(project_dir, "Plugins", "PalBakerEditorUtils")

        if action == "uninstall":
            try:
                if os.path.exists(installed_plugin_dir):
                    shutil.rmtree(installed_plugin_dir)
                    json_print({"status": "success", "message": "Successfully uninstalled C++ editor plugin."})
                else:
                    json_print({"status": "success", "message": "C++ plugin is already uninstalled."})
            except Exception as e:
                error_print(f"Failed to uninstall plugin: {str(e)}")
                sys.exit(1)
        else:
            try:
                # Compile and install plugin
                success, msg = install_and_compile_plugin(
                    settings["ue_root"], 
                    settings["uproject"], 
                    verbose=False, 
                    force_recompile=False
                )
                if success:
                    # Ingest required material assets
                    inject_missing_assets(settings["uproject"], verbose=False)
                    json_print({"status": "success", "message": "C++ Plugin compiled and installed successfully."})
                else:
                    json_print({"status": "error", "message": f"Compilation failed: {msg}"})
                    sys.exit(1)
            except Exception as e:
                error_print(f"C++ Plugin setup crashed: {str(e)}")
                sys.exit(1)

    # 4. Handle 'env ue4ss-install'
    elif subcommand == "ue4ss-install":
        from utils.ue4ss_helper import download_and_extract_ue4ss, uninstall_ue4ss
        action = getattr(args, "action", "install-palworld")

        def log_callback(msg, is_error=False):
            json_print({"type": "log", "level": "error" if is_error else "standard", "message": msg})

        try:
            if action == "install-palworld":
                success = download_and_extract_ue4ss(settings["palworld_exe"], "Palworld-Experimental", log_callback)
            elif action == "install-latest":
                success = download_and_extract_ue4ss(settings["palworld_exe"], "Latest-Experimental", log_callback)
            elif action == "repair":
                from utils.ue4ss_helper import get_ue4ss_status
                status = get_ue4ss_status(settings["palworld_exe"])
                branch = status.get("branch", "Palworld-Experimental")
                if branch == "Unknown" or branch == "None":
                    branch = "Palworld-Experimental"
                success = download_and_extract_ue4ss(settings["palworld_exe"], branch, log_callback)
            elif action == "uninstall":
                success = uninstall_ue4ss(settings["palworld_exe"], log_callback)
            else:
                success = False
                log_callback(f"Unknown action: {action}", is_error=True)

            if success:
                json_print({"status": "success", "message": f"Successfully completed action: {action}"})
            else:
                json_print({"status": "error", "message": f"Action failed: {action}"})
                sys.exit(1)
        except Exception as e:
            error_print(f"UE4SS routine crashed: {str(e)}")
            sys.exit(1)

    # 4b. Handle 'env palschema-install'
    elif subcommand == "palschema-install":
        from utils.palschema_helper import download_and_extract_palschema, uninstall_palschema
        action = getattr(args, "action", "install")

        def log_callback(msg, is_error=False):
            json_print({"type": "log", "level": "error" if is_error else "standard", "message": msg})

        try:
            if action == "install":
                success = download_and_extract_palschema(settings["palworld_exe"], log_callback)
            elif action == "uninstall":
                success = uninstall_palschema(settings["palworld_exe"], log_callback)
            else:
                success = False
                log_callback(f"Unknown action: {action}", is_error=True)

            if success:
                json_print({"status": "success", "message": f"Successfully completed PalSchema action: {action}"})
            else:
                json_print({"status": "error", "message": f"PalSchema action failed: {action}"})
                sys.exit(1)
        except Exception as e:
            error_print(f"PalSchema routine crashed: {str(e)}")
            sys.exit(1)

    # 5. Handle 'env status'
    elif subcommand == "status":
        from utils.ue4ss_helper import get_ue4ss_status
        from utils.palschema_helper import get_palschema_status
        from utils.plugins.detector import check_remote_execution_settings
        from utils.plugins.installer import is_unreal_running

        try:
            pal_exe = settings.get("palworld_exe", "")
            uproject = settings.get("uproject", "")

            ue4ss_status = get_ue4ss_status(pal_exe) if pal_exe else {"status": "Not Installed", "branch": "None", "corrupted": False}
            palschema_status = get_palschema_status(pal_exe) if pal_exe else {"status": "Not Installed"}
            remote_exec_enabled = check_remote_execution_settings(uproject) if uproject else False
            unreal_running = is_unreal_running()

            # Check database cache readiness
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            deps_dir = os.path.join(repo_root, "deps")
            expected_db_files = [
                "pal_names_map.json", "resolved_sound_map.json", "active_skills_cache.json",
                "passive_skills_cache.json", "coop_passives_cache.json", "partner_skills_cache.json",
                "monster_parameter_cache.json", "waza_master_level_cache.json", "monster_spawners_cache.json",
                "monster_spawners_default_map.json", "camera_offsets_cache.json", "pal_drop_item_cache.json",
                "items_cache.json", "breeding_combi_cache.json", "cage_pals_cache.json",
                "partner_skill_params_cache.json", "boss_spawners_cache.json"
            ]
            missing_db_files = [
                f for f in expected_db_files 
                if not os.path.exists(os.path.join(deps_dir, f)) or os.path.getsize(os.path.join(deps_dir, f)) == 0
            ]

            json_print({
                "status": "success",
                "ue4ss": ue4ss_status,
                "palschema": palschema_status,
                "remote_exec_enabled": remote_exec_enabled,
                "unreal_running": unreal_running,
                "needs_db_build": len(missing_db_files) > 0,
                "missing_db_files": missing_db_files
            })
        except Exception as e:
            error_print(f"Failed to fetch integration status: {str(e)}")
            sys.exit(1)

    # 6. Handle 'env launch-unreal'
    elif subcommand == "launch-unreal":
        from utils.plugins.installer import launch_unreal_editor
        try:
            success, msg = launch_unreal_editor(settings["ue_root"], settings["uproject"])
            if success:
                json_print({"status": "success", "message": msg})
            else:
                json_print({"status": "error", "message": msg})
                sys.exit(1)
        except Exception as e:
            error_print(f"Failed to launch Unreal: {str(e)}")
            sys.exit(1)

    # 7. Handle 'env restart-unreal'
    elif subcommand == "restart-unreal":
        from utils.plugins.installer import restart_unreal_editor
        try:
            success, msg = restart_unreal_editor(settings["ue_root"], settings["uproject"])
            if success:
                json_print({"status": "success", "message": msg})
            else:
                json_print({"status": "error", "message": msg})
                sys.exit(1)
        except Exception as e:
            error_print(f"Failed to restart Unreal: {str(e)}")
            sys.exit(1)

    # 7b. Handle 'env enable-remote-exec'
    elif subcommand == "enable-remote-exec":
        from utils.plugins.installer import enable_remote_execution_settings, enable_cooking_settings
        try:
            success, msg = enable_remote_execution_settings(settings["uproject"])
            if success:
                enable_cooking_settings(settings["uproject"])
                json_print({"status": "success", "message": "Project environment and cooking configurations successfully enabled!"})
            else:
                json_print({"status": "error", "message": msg})
                sys.exit(1)
        except Exception as e:
            error_print(f"Failed to enable Remote Execution: {str(e)}")
            sys.exit(1)

    # 7b2. Handle 'env close-game'
    elif subcommand == "close-game":
        # Palworld.exe is a launcher; the game itself runs as Palworld-Win64-Shipping.exe
        killed = []
        for image in ["Palworld-Win64-Shipping.exe", "Palworld.exe"]:
            res = subprocess.run(["taskkill", "/F", "/T", "/IM", image], capture_output=True, text=True, creationflags=0x08000000)
            if res.returncode == 0:
                killed.append(image)
        if killed:
            json_print({"status": "success", "message": f"Closed Palworld ({', '.join(killed)})."})
        else:
            json_print({"status": "success", "message": "Palworld was not running."})

    # 7c. Handle 'env inject-assets'
    elif subcommand == "inject-assets":
        from utils.plugin_manager import inject_missing_assets
        try:
            inject_missing_assets(settings["uproject"], verbose=False)
            json_print({"status": "success", "message": "Successfully injected ModKit materials and template assets."})
        except Exception as e:
            error_print(f"Failed to inject assets: {str(e)}")
            sys.exit(1)

    # 7d. Handle 'env extract-icons'
    elif subcommand == "extract-icons":
        from utils.extractor.db_builder import extract_vanilla_icons
        def log_callback(msg, is_error=False):
            json_print({"type": "log", "level": "error" if is_error else "standard", "message": msg})
        try:
            success, msg = extract_vanilla_icons(settings, log_callback)
            if success:
                json_print({"status": "success", "message": msg})
            else:
                json_print({"status": "error", "message": msg})
                sys.exit(1)
        except Exception as e:
            error_print(f"Icon extraction crashed: {str(e)}")
            sys.exit(1)

    # 8. Handle 'env autodetect'
    elif subcommand == "autodetect":
        from utils.autofill_helper import detect_unreal_engine, detect_palworld_exe, find_blender_versions
        try:
            ue_root = detect_unreal_engine()
            pal_exe = detect_palworld_exe()
            blender_vers = find_blender_versions()
            json_print({
                "status": "success",
                "ue_root": ue_root,
                "palworld_exe": pal_exe,
                "blender_versions": blender_vers
            })
        except Exception as e:
            error_print(f"Path autodetection crashed: {str(e)}")
            sys.exit(1)

    else:
        error_print(f"Unknown env subcommand: {subcommand}")
        sys.exit(1)