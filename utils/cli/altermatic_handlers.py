# utils/cli/altermatic_handlers.py
import os
import sys
import json
import shutil
import subprocess
from utils.config import validate_settings
from utils.cli.shared import json_print, error_print
from utils.altermatic import AltermaticController
from utils.altermatic_helper import (
    sync_sidecar_metadata, 
    get_blend_files_for_context, 
    get_available_materials_for_context
)

class CliAltermaticView:
    def write_log(self, text: str, category: str = "standard"):
        json_print({"type": "log", "level": category, "message": text})
    def show_snackbar(self, message: str, color: str = ""):
        json_print({"type": "log", "level": "error", "message": message})

class CliMasterController:
    def __init__(self, settings: dict):
        self.settings = settings
        self.view = CliAltermaticView()
        self.raw_mods = []
    def refresh_mods(self, scan_disk: bool = True, target_mod: str | None = None):
        from utils.scanner import get_mod_info
        self.raw_mods = get_mod_info(self.settings, target_mod)

def get_category_from_path(path: str | None) -> str:
    if not path: return "Monster"
    parts = path.replace("\\", "/").split("/")
    if "Character" in parts:
        idx = parts.index("Character")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "Monster"


def handle_altermatic_command(args, settings):
    subcommand = args.subcommand
    is_valid, err_msg = validate_settings(settings, ["fmodel_output"])
    if not is_valid:
        error_print(err_msg)
        sys.exit(1)

    base_pal = getattr(args, "base_pal", "")
    mod_name = getattr(args, "mod", "")
    data_str = getattr(args, "data", "")

    mc = CliMasterController(settings)

    if subcommand == "toggle":
        status = args.status
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
        controller = AltermaticController(mc)
        controller.toggle_altermatic(mc.raw_mods[0], status == "on")
        json_print({"status": "success", "message": f"Successfully toggled Altermatic {status} for {mod_name}."})

    elif subcommand == "list":
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
        json_print({"status": "success", "data": mc.raw_mods[0].get("altermatic_variants", [])})

    elif subcommand == "add":
        label = args.label
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
        custom_mesh = getattr(args, "custom", False)
        source_choice = getattr(args, "source", "base")
        fmodel_dir = mc.raw_mods[0]["fmodel_path"]
        base_blend_path = os.path.join(fmodel_dir, f"{mod_name}.blend")

        controller = AltermaticController(mc)
        controller.cloner._execute_clone_workflow(
            mc.raw_mods[0], label, custom_mesh, source_choice, base_blend_path, fmodel_dir, sync=True
        )
        json_print({"status": "success", "message": f"Added variant '{label}' successfully."})

    elif subcommand == "delete":
        index = args.index
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
            
        fmodel_dir = mc.raw_mods[0]["fmodel_path"]
        sidecar_to_clean = ""
        idx_int = int(index)
        variants = mc.raw_mods[0].get("altermatic_variants", [])
        
        if fmodel_dir and 0 <= idx_int < len(variants):
            v = variants[idx_int]
            if v.get("SkeletonSource") != "base":
                sidecar_name = v["SkeletonSource"].replace(".blend", "_blend.json")
                sidecar_to_clean = os.path.join(fmodel_dir, sidecar_name)

        controller = AltermaticController(mc)
        controller.delete_altermatic_variant(mc.raw_mods[0], idx_int, sync=True)
        
        if sidecar_to_clean and os.path.exists(sidecar_to_clean):
            try: os.remove(sidecar_to_clean)
            except OSError: pass

        json_print({"status": "success", "message": f"Deleted variant at index {index} successfully."})

    elif subcommand == "save":
        index = args.index
        try:
            variant_data = json.loads(data_str)
            current_char_id = variant_data["CharacterID"]
            mc.refresh_mods(target_mod=current_char_id)
            if not mc.raw_mods:
                error_print(f"Parent mod {current_char_id} not found on disk.")
                sys.exit(1)

            controller = AltermaticController(mc)
            variants = mc.raw_mods[0].get("altermatic_variants", [])
            idx_int = int(index)
            if 0 <= idx_int < len(variants):
                controller.original_editing_label = variants[idx_int]["label"]
                
            controller.save_altermatic_variant_callback(idx_int, variant_data, sync=True)
            json_print({"status": "success", "message": "Successfully saved variant parameters."})
        except Exception as e:
            error_print(f"Failed to save Altermatic variant: {str(e)}")
            sys.exit(1)

    elif subcommand == "sidecar":
        blend_name = args.blend_name
        if blend_name == "base":
            blend_name = f"{mod_name}.blend"

        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)

        # RECURSIVE DISCOVERY: Search children folders recursively to locate the target variant blend file
        fmodel_dir = mc.raw_mods[0].get("fmodel_path", "")
        blend_path = None
        if fmodel_dir:
            for root, _, files in os.walk(fmodel_dir):
                if blend_name in files:
                    blend_path = os.path.join(root, blend_name)
                    break

        if not blend_path:
            error_print(f"Skeletal blend file '{blend_name}' not found inside workspace.")
            sys.exit(1)

        try:
            synced_data = sync_sidecar_metadata(settings["blender"], blend_path)
            json_print({"status": "success", "data": synced_data})
        except Exception as e:
            error_print(f"Failed to sync sidecar metadata: {str(e)}")
            sys.exit(1)

    elif subcommand == "metadata":
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)

        mod_data = mc.raw_mods[0]
        category = get_category_from_path(mod_data["fmodel_path"])
        
        # Harvest recursively
        blend_files = get_blend_files_for_context(mod_data["fmodel_path"], None)
        available_mats = get_available_materials_for_context(settings["fmodel_output"], mod_data["fmodel_path"], mod_name, category)

        json_print({
            "status": "success",
            "blend_files": blend_files,
            "available_materials": available_mats,
            "category": category
        })

    elif subcommand == "open-blend":
        blend_name = getattr(args, "blend_name", "base")
        if blend_name == "base":
            blend_name = f"{mod_name}.blend"

        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)

        # RECURSIVE DISCOVERY: Walk through directories to find the physical model file to launch
        blend_path = None
        fmodel_dir = mc.raw_mods[0].get("fmodel_path", "")
        if fmodel_dir:
            for root, _, files in os.walk(fmodel_dir):
                if blend_name in files:
                    blend_path = os.path.join(root, blend_name)
                    break

        if not blend_path:
            error_print(f"Target blend file '{blend_name}' not found inside workspace.")
            sys.exit(1)

        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen([settings["blender"], blend_path], creationflags=creation_flags, close_fds=True, start_new_session=True if os.name != 'nt' else False)
            json_print({"status": "success", "message": "Blender launched successfully."})
        except Exception as e:
            error_print(f"Failed to launch Blender: {str(e)}")
            sys.exit(1)