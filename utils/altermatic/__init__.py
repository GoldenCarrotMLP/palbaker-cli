# utils/altermatic/__init__.py
import os
import threading
from utils.altermatic_helper import sync_sidecar_metadata, get_blend_files_for_context, get_available_materials_for_context
from .manifest_manager import ManifestManager
from .cloner import AltermaticCloner
from .compiler import AltermaticCompiler

class AltermaticController:
    def __init__(self, master_controller):
        self.mc = master_controller
        self.settings = master_controller.settings
        self.view = master_controller.view
        self.manifest = ManifestManager(self)
        self.cloner = AltermaticCloner(self)
        self.compiler = AltermaticCompiler(self)
        self.original_editing_label = ""

    def get_category_from_path(self, path: str | None) -> str:
        if not path: return "Monster"
        parts = path.replace("\\", "/").split("/")
        if "Character" in parts:
            idx = parts.index("Character")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "Monster"

    def toggle_altermatic(self, mod_data: dict, is_active: bool):
        current_char_id = mod_data["name"]
        fmodel_dir = mod_data.get("fmodel_path", "")
        
        # SELF-HEALING: If the parent is currently unextracted, resolve its target local workspace folder
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
        manifest_data["is_altermatic_active"] = is_active

        if is_active:
            has_base = any(k == "base" for k in manifest_data["variants"].keys())
            if not has_base:
                base_blend_path = os.path.join(fmodel_dir, f"{current_char_id}.blend")
                # Fallback to the unmodded game mesh ("base") if no root .blend exists
                default_skeleton_source = f"{current_char_id}.blend" if os.path.exists(base_blend_path) else "base"
                
                manifest_data["variants"]["base"] = {
                    "label": "base",
                    "CharacterID": current_char_id,
                    "SkeletonSource": default_skeleton_source,
                    "Gender": "None",
                    "IsRarePal": False,
                    "SkinName": "",
                    "ReqTrait": [],
                    "PrefTrait": [],
                    "MatReplace": [],
                    "MorphTarget": [],
                    "is_base": True
                }

        self.manifest.save_manifest(manifest_path, manifest_data)
        self.view.write_log(f"Altermatic framework toggled {'ON' if is_active else 'OFF'}.", "success")
        
        if is_active:
            self.compiler.deploy_to_game(current_char_id, fmodel_dir)
            
        self.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)

    def delete_altermatic_variant(self, mod_data: dict, index: int, sync: bool = False):
        variants = mod_data.get("altermatic_variants", [])
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

    def save_altermatic_variant_callback(self, index: int, variant_data: dict, sync: bool = False):
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

            for label_key, other_var in manifest_data["variants"].items():
                if label_key != old_label and label_key == new_label:
                    self.view.write_log(f"Error: A variant named '{variant_data['label']}' already exists!", "error")
                    self.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)
                    return

            if index >= 0 and index < len(manifest_data["variants"]):
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

            mat_replace_map = {}
            for item in variant_data.get("MatReplace", []):
                if "SlotName" in item:
                    mat_replace_map[item["SlotName"]] = item["MatPath"].split("/")[-1]

            sidecar_structure = {
                "Gender": variant_data["Gender"],
                "IsRarePal": variant_data["IsRarePal"],
                "SkinName": variant_data["SkinName"],
                "ReqTrait": variant_data["ReqTrait"],
                "PrefTrait": variant_data["PrefTrait"],
                "MaterialOverrides": mat_replace_map,
                "MorphTarget": []
            }

            for m in variant_data.get("MorphTarget", []):
                if "Set" in m:
                    sidecar_structure["MorphTarget"].append({"Target": m["Target"], "Type": "Static", "Set": m["Set"]})
                else:
                    sidecar_structure["MorphTarget"].append({"Target": m["Target"], "Type": "Random", "Min": m.get("Min", 0.0), "Max": m.get("Max", 1.0), "TypeVal": m.get("TypeVal", "Free")})

            if is_base:
                base_type = "custom" if variant_data["SkeletonSource"] not in ["base", f"{current_char_id}.blend"] else "vanilla"
            else:
                base_skel = manifest_data["variants"].get("base", {}).get("SkeletonSource", "base")
                base_type = "custom" if base_skel not in ["base", f"{current_char_id}.blend"] else "vanilla"

            save_block = {
                "SkeletonSource": variant_data["SkeletonSource"]
            }

            if sidecar_structure["Gender"] != "None": save_block["Gender"] = sidecar_structure["Gender"]
            if sidecar_structure["IsRarePal"]: save_block["IsRarePal"] = sidecar_structure["IsRarePal"]
            if sidecar_structure["SkinName"]: save_block["SkinName"] = sidecar_structure["SkinName"]
            if sidecar_structure["ReqTrait"]: save_block["ReqTrait"] = variant_data["ReqTrait"]
            if sidecar_structure["PrefTrait"]: save_block["PrefTrait"] = variant_data["PrefTrait"]
            if sidecar_structure["MaterialOverrides"]: save_block["MaterialOverrides"] = sidecar_structure["MaterialOverrides"]
            if sidecar_structure["MorphTarget"]: save_block["MorphTarget"] = sidecar_structure["MorphTarget"]

            save_block["is_base"] = is_base
            save_block["base_type"] = base_type

            manifest_data["variants"][new_label] = save_block

            if self.manifest.save_manifest(manifest_path, manifest_data):
                self.view.write_log(f"Successfully saved Altermatic variant manifest: {os.path.basename(manifest_path)}", "success")
                self.compiler.deploy_to_game(current_char_id, fmodel_target_dir)

            self.mc.refresh_mods(scan_disk=True, target_mod=current_char_id)

        if sync:
            background_worker()
        else:
            threading.Thread(target=background_worker, daemon=True).start()