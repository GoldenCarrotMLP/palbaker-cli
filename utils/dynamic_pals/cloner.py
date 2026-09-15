# utils/dynamic_pals/cloner.py
import os
import re
import shutil
import threading
from utils.dynamic_pals_helper import sync_sidecar_metadata, get_blend_files_for_context

class DynamicPalsCloner:
    def __init__(self, controller):
        self.c = controller

    def _execute_clone_workflow(self, mod_data: dict, label_name: str, clone_custom_mesh: bool, source_choice: str, anim_target: str, base_blend_path: str, fmodel_target_dir: str, sync: bool = False):
        current_char_id = mod_data["name"]
        clean_label = re.sub(r'[^a-zA-Z0-9_]', '_', label_name)
        new_label = f"{current_char_id}_{clean_label}"


        self.c.view.write_log(f"Staging Dynamic Pal variant '{clean_label}'...", "standard")

        def background_clone_worker():
            import time
            if not sync: time.sleep(0.1)
            
            try:
                manifest_path = self.c.manifest.get_manifest_path(current_char_id, fmodel_target_dir)
                manifest_data = self.c.manifest.load_manifest(manifest_path)

                if new_label in manifest_data["variants"]:
                    self.c.mc.view.show_snackbar(f"Error: A variant named '{clean_label}' already exists!", "#EF5350")
                    return

                os.makedirs(fmodel_target_dir, exist_ok=True)
                
                # By default, point directly to the pre-selected source file without cloning
                target_blend_name = source_choice

                # Only duplicate files if explicitly requested
                if clone_custom_mesh:
                    cloned_blend_name = f"{current_char_id}_{clean_label}.blend"
                    target_blend_path = os.path.join(fmodel_target_dir, cloned_blend_name)

                    src_blend_file = base_blend_path if source_choice == "base" else os.path.join(fmodel_target_dir, source_choice)
                    if not os.path.exists(src_blend_file):
                        self.c.view.write_log(f"Error: Source .blend file not found for cloning: {os.path.basename(src_blend_file)}", "error")
                        return
                    
                    shutil.copy2(src_blend_file, target_blend_path)
                    
                    base_sidecar = os.path.join(fmodel_target_dir, f"{current_char_id}_blend.json")
                    src_sidecar = base_sidecar if source_choice == "base" else os.path.join(fmodel_target_dir, source_choice.replace(".blend", "_blend.json"))
                    target_sidecar = os.path.join(fmodel_target_dir, f"{current_char_id}_{clean_label}_blend.json")
                    if os.path.exists(src_sidecar):
                        shutil.copy2(src_sidecar, target_sidecar)

                    target_blend_name = cloned_blend_name

                manifest_data["variants"][new_label] = {
                    "label": clean_label,
                    "CharacterID": current_char_id,
                    "SkeletonSource": target_blend_name,
                    "AnimTarget": anim_target,
                    "Gender": "None",
                    "LuckyStarReq": False,
                    "SkinName": "",
                    "SetNickname": "",
                    "is_base": False
                }

                self.c.manifest.save_manifest(manifest_path, manifest_data)
                self.c.view.write_log(f"Successfully generated Dynamic Pal variant: {clean_label} (Model: {target_blend_name})", "success")
                
                self.c.compiler.deploy_to_game(current_char_id, fmodel_target_dir)
                
            except Exception as e:
                self.c.view.write_log(f"Failed to stage variant: {e}", "error")
                if sync: raise e

            self.c.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)

        if sync: background_clone_worker()
        else: threading.Thread(target=background_clone_worker, daemon=True).start()