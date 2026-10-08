# utils/cli/dynamic_pals_handlers.py
import os
import sys
import json
import shutil
import subprocess
from utils.config import validate_settings
from utils.cli.shared import json_print, error_print
from utils.dynamic_pals import DynamicPalsController
from utils.dynamic_pals_helper import (
    sync_sidecar_metadata, 
    get_blend_files_for_context, 
    get_available_materials_for_context
)

class CliDynamicPalsView:
    def write_log(self, text: str, category: str = "standard"):
        json_print({"type": "log", "level": category, "message": text})
    def show_snackbar(self, message: str, color: str = ""):
        json_print({"type": "log", "level": "error", "message": message})

class CliMasterController:
    def __init__(self, settings: dict):
        self.settings = settings
        self.view = CliDynamicPalsView()
        self.raw_mods = []
        
    def refresh_mods(self, scan_disk: bool = True, target_mod: str = None, base_pal: str = None):
        from utils.scanner import get_mod_info
        mods = get_mod_info(self.settings, target_mod)
        if base_pal:
            mods = [m for m in mods if m["base_pal"].lower() == base_pal.lower()]
        self.raw_mods = mods


def get_category_from_path(path: str | None) -> str:
    if not path: return "Monster"
    parts = path.replace("\\", "/").split("/")
    if "Character" in parts:
        idx = parts.index("Character")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "Monster"

def handle_dynamic_pals_command(args, settings):
    subcommand = args.subcommand
    is_valid, err_msg = validate_settings(settings, ["fmodel_output"])
    if not is_valid:
        error_print(err_msg)
        sys.exit(1)

    mod_name = getattr(args, "mod", "")
    base_pal = getattr(args, "base_pal", "")
    data_str = getattr(args, "data", "")

    mc = CliMasterController(settings)

    if subcommand == "toggle":
        status = args.status
        mc.refresh_mods(target_mod=mod_name, base_pal=base_pal)
        if not mc.raw_mods:

            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
        controller = DynamicPalsController(mc)
        controller.toggle_dynamic_pals(mc.raw_mods[0], status == "on")
        json_print({"status": "success", "message": f"Successfully toggled Dynamic Pals {status} for {mod_name}."})

    elif subcommand == "list":
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
        json_print({"status": "success", "data": mc.raw_mods[0].get("dynamic_pal_variants", [])})

    elif subcommand == "add":
        label = args.label
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
            
        custom_mesh = getattr(args, "custom", False)
        source_choice = getattr(args, "source", "base")
        anim_target = getattr(args, "anim_target", "")  # <-- NEW: Fetch from CLI args

        fmodel_dir = mc.raw_mods[0]["fmodel_path"]
        base_blend_path = os.path.join(fmodel_dir, f"{mod_name}.blend")

        controller = DynamicPalsController(mc)
        controller.cloner._execute_clone_workflow(
            # FIXED: Added anim_target to the parameter sequence
            mc.raw_mods[0], label, custom_mesh, source_choice, anim_target, base_blend_path, fmodel_dir, sync=True
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
        variants = mc.raw_mods[0].get("dynamic_pal_variants", [])
        
        if fmodel_dir and 0 <= idx_int < len(variants):
            v = variants[idx_int]
            if v.get("SkeletonSource") != "base":
                sidecar_name = v["SkeletonSource"].replace(".blend", "_blend.json")
                sidecar_to_clean = os.path.join(fmodel_dir, sidecar_name)

        controller = DynamicPalsController(mc)
        controller.delete_dynamic_pal_variant(mc.raw_mods[0], idx_int, sync=True)
        
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

            controller = DynamicPalsController(mc)
            variants = mc.raw_mods[0].get("dynamic_pal_variants", [])
            idx_int = int(index)
            if 0 <= idx_int < len(variants):
                controller.original_editing_label = variants[idx_int]["label"]
                
            controller.save_dynamic_pal_variant_callback(idx_int, variant_data, sync=True)
            json_print({"status": "success", "message": "Successfully saved variant parameters."})
        except Exception as e:
            error_print(f"Failed to save Dynamic Pal variant: {str(e)}")
            sys.exit(1)

    
    elif subcommand == "set-json-name":
        custom_name = getattr(args, "name", "").strip()
        mc.refresh_mods(target_mod=mod_name, base_pal=base_pal)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)
            
        fmodel_dir = mc.raw_mods[0]["fmodel_path"]
        controller = DynamicPalsController(mc)
        manifest_path = controller.manifest.get_manifest_path(base_pal, fmodel_dir)
        manifest_data = controller.manifest.load_manifest(manifest_path)

        old_custom_name = manifest_data.get("custom_json_name", "")
        manifest_data["custom_json_name"] = custom_name
        controller.manifest.save_manifest(manifest_path, manifest_data)

        # REDIRECTOR / CLEANUP: Clean up previous file if name changed!
        palworld_exe = settings.get("palworld_exe", "")
        if palworld_exe and os.path.exists(palworld_exe):
            from utils.dynamic_pals_helper import (
                get_model_json_dirs, sanitize_json_filename, compile_unified_dynamic_pals_json
            )
            model_json_dir, legacy_swap_json_dir = get_model_json_dirs(palworld_exe)
            old_filename = sanitize_json_filename(old_custom_name, f"palbaker-{base_pal}")

            for d in [model_json_dir, legacy_swap_json_dir]:
                if d and os.path.exists(d):
                    old_path = os.path.join(d, f"{old_filename}.json")
                    if os.path.exists(old_path):
                        try: os.remove(old_path)
                        except OSError: pass

            compile_unified_dynamic_pals_json(base_pal, fmodel_dir, model_json_dir, legacy_swap_json_dir)
        json_print({"status": "success", "message": f"Updated deployed JSON name to '{custom_name or f'palbaker-{base_pal}'}.json'"})

    elif subcommand == "sidecar":
        blend_name = args.blend_name
        if blend_name == "base":
            blend_name = f"{mod_name}.blend"

        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)

        fmodel_dir = mc.raw_mods[0].get("fmodel_path", "")
        blend_path = None
        if fmodel_dir:
            blend_lower = blend_name.lower()
            for root, _, files in os.walk(fmodel_dir):
                match = next((f for f in files if f.lower() == blend_lower), None)
                if match:
                    blend_path = os.path.join(root, match)
                    break

        if not blend_path:
            # Fallback directly to the sidecar JSON if the .blend file is missing or renamed
            from utils.sidecar_helper import load_sidecar
            sidecar_candidates = [
                os.path.join(fmodel_dir, f"{mod_name}_blend.json"),
                os.path.join(fmodel_dir, f"{base_pal}_blend.json")
            ]
            sidecar_path = next((p for p in sidecar_candidates if os.path.exists(p)), None)
            if not sidecar_path and fmodel_dir:
                sidecar_lower = f"{mod_name.lower()}_blend.json"
                for root, _, files in os.walk(fmodel_dir):
                    match = next((f for f in files if f.lower() == sidecar_lower or f.lower().endswith("_blend.json")), None)
                    if match:
                        sidecar_path = os.path.join(root, match)
                        break

            if sidecar_path and os.path.exists(sidecar_path):
                data = load_sidecar(sidecar_path)
                json_print({"status": "success", "data": data})
                return

            error_print(f"Skeletal blend file '{blend_name}' not found inside workspace.")
            sys.exit(1)

        try:
            synced_data = sync_sidecar_metadata(settings["blender"], blend_path)
            json_print({"status": "success", "data": synced_data})
        except Exception as e:
            # Fallback to existing sidecar on disk if Blender sync throws
            from utils.sidecar_helper import load_sidecar
            sidecar_path = os.path.join(fmodel_dir, f"{mod_name}_blend.json")
            if os.path.exists(sidecar_path):
                data = load_sidecar(sidecar_path)
                json_print({"status": "success", "data": data})
            else:
                error_print(f"Failed to sync sidecar metadata: {str(e)}")
                sys.exit(1)

    elif subcommand == "metadata":
        mc.refresh_mods(target_mod=mod_name)
        if not mc.raw_mods:
            error_print(f"Mod {mod_name} was not found on disk.")
            sys.exit(1)

        mod_data = mc.raw_mods[0]
        category = get_category_from_path(mod_data["fmodel_path"])
        
        blend_files = get_blend_files_for_context(mod_data["fmodel_path"], None)
        available_mats = get_available_materials_for_context(settings["fmodel_output"], mod_data["fmodel_path"], mod_name, category)
        
        # --- NEW: Fetch global workspace blend files ---
        from utils.dynamic_pals_helper import get_all_blend_files_for_workspace
        all_blend_files = get_all_blend_files_for_workspace(settings["fmodel_output"], category)

        json_print({
            "status": "success",
            "blend_files": blend_files,
            "all_blend_files": all_blend_files,
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

        blend_path = None
        fmodel_dir = mc.raw_mods[0].get("fmodel_path", "")
        if fmodel_dir:
            blend_lower = blend_name.lower()
            for root, _, files in os.walk(fmodel_dir):
                match = next((f for f in files if f.lower() == blend_lower), None)
                if match:
                    blend_path = os.path.join(root, match)
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