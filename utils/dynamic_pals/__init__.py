# utils/dynamic_pals/__init__.py
import os
import threading
from utils.dynamic_pals_helper import (
    sync_sidecar_metadata, 
    get_blend_files_for_context, 
    get_available_materials_for_context
)
from .manifest_manager import ManifestManager
from .cloner import DynamicPalsCloner
from .compiler import DynamicPalsCompiler

class DynamicPalsController:
    def __init__(self, master_controller):
        self.mc = master_controller
        self.settings = master_controller.settings
        self.view = master_controller.view
        self.manifest = ManifestManager(self)
        self.cloner = DynamicPalsCloner(self)
        self.compiler = DynamicPalsCompiler(self)
        self.original_editing_label = ""

    def get_category_from_path(self, path: str | None) -> str:
        if not path: return "Monster"
        parts = path.replace("\\", "/").split("/")
        if "Character" in parts:
            idx = parts.index("Character")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "Monster"

    def toggle_dynamic_pals(self, mod_data: dict, is_active: bool):
        current_char_id = mod_data["name"]
        fmodel_dir = mod_data.get("fmodel_path", "")
        
        if not fmodel_dir:
            category = mod_data.get("category", "Monster")
            fmodel_dir = os.path.normpath(os.path.join(
                self.settings.get("fmodel_output", ""),
                "Exports", "Pal", "Content", "Pal", "Model", "Character",
                category, current_char_id
            ))

        os.makedirs(fmodel_dir, exist_ok=True)
        manifest_path = self.manifest.get_manifest_path(current_char_id, fmodel_dir)
        manifest_data = self.manifest.load_manifest(manifest_path)
        manifest_data["is_dynamic_pals_active"] = is_active

        if is_active:
            has_base = any(k == "base" for k in manifest_data["variants"].keys())
            if not has_base:
                base_blend_path = os.path.join(fmodel_dir, f"{current_char_id}.blend")
                default_skeleton_source = f"{current_char_id}.blend" if os.path.exists(base_blend_path) else "base"
                
                manifest_data["variants"]["base"] = {
                    "label": "base",
                    "CharacterID": current_char_id,
                    "SkeletonSource": default_skeleton_source,
                    "Gender": "None",
                    "LuckyStarReq": False,
                    "SkinName": "",
                    "SetNickname": "",
                    "MinLevel": 1,
                    "MaxLevel": 999,
                    "MinTrust": 0,
                    "MaxTrust": 999999,
                    "MinRank": 0,
                    "MaxRank": 999,
                    "SpawnWeight": 1,
                    "IsWildPal": False,
                    "MinSizeMultiplier": 1.0,
                    "MaxSizeMultiplier": 1.0,
                    "ReqSwap": [],
                    "PassiveSkills": [],
                    "PrefTrait": [],
                    "SkipTrait": [],
                    "SpecialMaterial": [],
                    "ShapeKeys": [],
                    "Extra": "{}",
                    "is_base": True
                }

        self.manifest.save_manifest(manifest_path, manifest_data)
        self.view.write_log(f"Dynamic Pals framework toggled {'ON' if is_active else 'OFF'}.", "success")
        
        if is_active:
            self.compiler.deploy_to_game(current_char_id, fmodel_dir)
        else:
            palworld_exe = self.settings.get("palworld_exe", "")
            if palworld_exe and os.path.exists(palworld_exe):
                from utils.dynamic_pals_helper import get_model_json_dirs, sanitize_json_filename
                model_json_dir, legacy_swap_json_dir = get_model_json_dirs(palworld_exe)

                custom_name = manifest_data.get("custom_json_name", "")
                final_filename = sanitize_json_filename(custom_name, f"palbaker-{current_char_id}")

                for d in [model_json_dir, legacy_swap_json_dir]:
                    if d and os.path.exists(d):
                        for fn in [f"{final_filename}.json", f"palbaker-{current_char_id}.json"]:
                            target_json = os.path.join(d, fn)
                            if os.path.exists(target_json):
                                try:
                                    os.remove(target_json)
                                    self.view.write_log(f"Purged disabled Dynamic Pals config from game: {os.path.basename(target_json)}", "standard")
                                except OSError:
                                    pass
            
        self.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)

    def delete_dynamic_pal_variant(self, mod_data: dict, index: int, sync: bool = False):
        variants = mod_data.get("dynamic_pal_variants", [])
        if index < 0 or index >= len(variants): return
        
        v = variants[index]
        current_char_id = mod_data["name"]
        fmodel_dir = mod_data.get("fmodel_path")

        def background_worker():
            import time
            if not sync: time.sleep(0.1)
            
            if not fmodel_dir: return
            manifest_path = self.manifest.get_manifest_path(current_char_id, fmodel_dir)
            manifest_data = self.manifest.load_manifest(manifest_path)

            manifest_data["variants"].pop(v["label"], None)
            self.manifest.save_manifest(manifest_path, manifest_data)

            is_material_only_reskin = (v.get("SkeletonSource", "base") == "base" or v.get("SkeletonSource") == f"{current_char_id}.blend")
            if not is_material_only_reskin:
                blend_file = os.path.join(fmodel_dir, v["SkeletonSource"])
                if os.path.exists(blend_file):
                    try: os.remove(blend_file)
                    except OSError: pass

            self.view.write_log(f"Deleted variant: {v['label']}", "warning")
            self.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)

        if sync: background_worker()
        else: threading.Thread(target=background_worker, daemon=True).start()

    def save_dynamic_pal_variant_callback(self, index: int, variant_data: dict, sync: bool = False):
        old_label = self.original_editing_label if (index != -1 and hasattr(self, "original_editing_label")) else ""
        
        def background_worker():
            import time
            if not sync: time.sleep(0.1)
            
            is_base = variant_data.get("is_base", False)
            current_char_id = variant_data["CharacterID"]

            mod_data = next((m for m in self.mc.raw_mods if m["name"] == current_char_id), None)
            fmodel_target_dir = mod_data.get("fmodel_path") if mod_data else ""
            if not fmodel_target_dir: return
            
            manifest_path = self.manifest.get_manifest_path(current_char_id, fmodel_target_dir)
            manifest_data = self.manifest.load_manifest(manifest_path)

            new_label = f"{current_char_id}_{variant_data['label']}" if not is_base else "base"

            for label_key in manifest_data["variants"].keys():
                if label_key != old_label and label_key == new_label:
                    self.view.write_log(f"Error: A variant named '{variant_data['label']}' already exists!", "error")
                    self.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)
                    return

            if 0 <= index < len(manifest_data["variants"]):
                if old_label and old_label != new_label and not is_base:
                    old_sidecar = os.path.join(fmodel_target_dir, f"{old_label}_blend.json")
                    new_sidecar = os.path.join(fmodel_target_dir, f"{new_label}_blend.json")
                    if os.path.exists(old_sidecar):
                        try: os.rename(old_sidecar, new_sidecar)
                        except OSError: pass

                    if old_label in manifest_data["variants"] and manifest_data["variants"][old_label].get("SkeletonSource") not in ["base", f"{current_char_id}.blend"]:
                        old_blend_file = os.path.join(fmodel_target_dir, manifest_data["variants"][old_label]["SkeletonSource"])
                        new_blend_name = f"{new_label}.blend"
                        new_blend_file = os.path.join(fmodel_target_dir, new_blend_name)
                        if os.path.exists(old_blend_file):
                            try: os.rename(old_blend_file, new_blend_file)
                            except OSError: pass
                        variant_data["SkeletonSource"] = new_blend_name

                manifest_data["variants"].pop(old_label, None)

            # Construct Format V2 Property Structure
            save_block = {
                "SkeletonSource": variant_data.get("SkeletonSource", "base"),
                "label": variant_data.get("label", ""),
                "is_base": is_base
            }

            if variant_data.get("AnimTarget"):
                save_block["AnimTarget"] = variant_data["AnimTarget"]
            
            if variant_data.get("Gender") and variant_data["Gender"] != "None":
                save_block["Gender"] = variant_data["Gender"]
            if variant_data.get("LuckyStarReq"):
                save_block["LuckyStarReq"] = True
            if variant_data.get("IsWildPal"):
                save_block["IsWildPal"] = True
            if variant_data.get("SkinName"):
                save_block["SkinName"] = variant_data["SkinName"]
            if variant_data.get("SetNickname"):
                save_block["SetNickname"] = variant_data["SetNickname"]
            if variant_data.get("SpawnWeight") is not None and variant_data.get("SpawnWeight") != 1:
                sw = float(variant_data["SpawnWeight"])
                save_block["SpawnWeight"] = int(sw) if sw.is_integer() else sw

            # On/Off Switched Range Constraints
            if variant_data.get("enableLevelRange"):
                save_block["enableLevelRange"] = True
                save_block["MinLevel"] = int(variant_data.get("MinLevel", 5))
                save_block["MaxLevel"] = int(variant_data.get("MaxLevel", 20))

            if variant_data.get("enableTrustRange"):
                save_block["enableTrustRange"] = True
                save_block["MinTrust"] = int(variant_data.get("MinTrust", 2))
                save_block["MaxTrust"] = int(variant_data.get("MaxTrust", 40))

            if variant_data.get("enableRankRange"):
                save_block["enableRankRange"] = True
                save_block["MinRank"] = int(variant_data.get("MinRank", 50))
                save_block["MaxRank"] = int(variant_data.get("MaxRank", 200))

            if variant_data.get("enableSizeRange"):
                save_block["enableSizeRange"] = True
                save_block["MinSizeMultiplier"] = float(variant_data.get("MinSizeMultiplier", 0.7))
                save_block["MaxSizeMultiplier"] = float(variant_data.get("MaxSizeMultiplier", 2.0))

            # Array collections (omit if empty)
            if variant_data.get("ReqSwap"):                               
                save_block["ReqSwap"] = variant_data["ReqSwap"]           
            if variant_data.get("PassiveSkills"):
                save_block["PassiveSkills"] = variant_data["PassiveSkills"]
            if variant_data.get("PrefTrait"):
                save_block["PrefTrait"] = variant_data["PrefTrait"]
            if variant_data.get("SkipTrait"):
                save_block["SkipTrait"] = variant_data["SkipTrait"]
            if variant_data.get("SpecialMaterial"):
                save_block["SpecialMaterial"] = variant_data["SpecialMaterial"]
            if variant_data.get("ShapeKeys"):
                save_block["ShapeKeys"] = variant_data["ShapeKeys"]
            if variant_data.get("Extra") and variant_data["Extra"] != "{}":
                save_block["Extra"] = variant_data["Extra"]

            manifest_data["variants"][new_label] = save_block


            if self.manifest.save_manifest(manifest_path, manifest_data):
                self.view.write_log(f"Successfully saved Dynamic Pals variant manifest: {os.path.basename(manifest_path)}", "success")
                self.compiler.deploy_to_game(current_char_id, fmodel_target_dir)

            self.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)

        if sync:
            background_worker()
        else:
            threading.Thread(target=background_worker, daemon=True).start()