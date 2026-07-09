# controllers/altermatic/cloner.py
import os
import re
import shutil
import threading
from utils.altermatic_helper import sync_sidecar_metadata, get_blend_files_for_context

class AltermaticCloner:
    def __init__(self, controller):
        self.c = controller

    def show_add_dialog(self, mod_data: dict):
        current_char_id = mod_data["name"]
        fmodel_dir = mod_data.get("fmodel_path", "")
        
        # SELF-HEALING: Dynamically resolve directories on unextracted base cards
        if not fmodel_dir:
            category = mod_data.get("category", "Monster")
            fmodel_dir = os.path.normpath(os.path.join(
                self.c.settings.get("fmodel_output", ""),
                "Exports", "Pal", "Content", "Pal", "Model", "Character",
                category, current_char_id
            ))
            
        base_blend_path = os.path.join(fmodel_dir, f"{current_char_id}.blend")
        blend_files = get_blend_files_for_context(fmodel_dir, None)

        self.c.view.altermatic_add_dialog.show(
            current_char_id, 
            blend_files, 
            lambda label, custom, src: self._execute_clone_workflow(mod_data, label, custom, src, base_blend_path, fmodel_dir)
        )

    def _execute_clone_workflow(self, mod_data: dict, label_name: str, create_custom_mesh: bool, source_choice: str, base_blend_path: str, fmodel_target_dir: str, sync: bool = False):
        current_char_id = mod_data["name"]
        clean_label = re.sub(r'[^a-zA-Z0-9_]', '_', label_name)
        new_label = f"{current_char_id}_{clean_label}"

        self.c.view.write_log(f"Staging Altermatic variant '{clean_label}'...", "standard")

        def background_clone_worker():
            import time
            if not sync: time.sleep(0.1)
            
            try:
                manifest_path = self.c.manifest.get_manifest_path(current_char_id, fmodel_target_dir)
                manifest_data = self.c.manifest.load_manifest(manifest_path)

                if new_label in manifest_data["variants"]:
                    self.c.mc.view.show_snackbar(f"Error: A variant named '{clean_label}' already exists!", "#EF5350")
                    return

                target_blend_name = f"{current_char_id}_{clean_label}.blend"
                os.makedirs(fmodel_target_dir, exist_ok=True)
                target_blend_path = os.path.join(fmodel_target_dir, target_blend_name)

                base_sidecar = os.path.join(fmodel_target_dir, f"{current_char_id}_blend.json")
                if create_custom_mesh:
                    # Cloning geometry requires a valid source .blend file to exist
                    src_blend_file = base_blend_path if source_choice == "base" else os.path.join(fmodel_target_dir, source_choice)
                    if not os.path.exists(src_blend_file):
                        self.c.view.write_log(f"Error: Source .blend file not found for cloning: {os.path.basename(src_blend_file)}", "error")
                        return
                    
                    shutil.copy2(src_blend_file, target_blend_path)
                    
                    # Copy companion sidecar layout as well
                    src_sidecar = base_sidecar if source_choice == "base" else os.path.join(fmodel_target_dir, source_choice.replace(".blend", "_blend.json"))
                    target_sidecar = os.path.join(fmodel_target_dir, f"{current_char_id}_{clean_label}_blend.json")
                    if os.path.exists(src_sidecar):
                        shutil.copy2(src_sidecar, target_sidecar)

                manifest_data["variants"][new_label] = {
                    "label": clean_label,
                    "CharacterID": current_char_id,
                    "SkeletonSource": target_blend_name if create_custom_mesh else "base",
                    "Gender": "None",
                    "IsRarePal": False,
                    "SkinName": "",
                    "ReqTrait": [],
                    "PrefTrait": [],
                    "MatReplace": [],
                    "MorphTarget": [],
                    "is_base": False
                }

                self.c.manifest.save_manifest(manifest_path, manifest_data)
                self.c.view.write_log(f"Successfully generated variant: {clean_label}", "success")
                
                # Regenerate SwapJSON to deploy immediately
                self.c.compiler.deploy_to_game(current_char_id, fmodel_target_dir)
                
            except Exception as e:
                self.c.view.write_log(f"Failed to clone variant: {e}", "error")
                if sync: raise e

            # FIXED: Safely refresh Altermatic modifications list across both GUI and CLI scopes
            self.c.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)

        if sync: background_clone_worker()
        else: threading.Thread(target=background_clone_worker, daemon=True).start()