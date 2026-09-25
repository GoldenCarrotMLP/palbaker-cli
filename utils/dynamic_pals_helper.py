# utils/dynamic_pals_helper.py
import os
import json
import re
import subprocess
from .sidecar_helper import load_sidecar, update_sidecar_fields, save_sidecar

BLENDER_EXTRACTOR_SCRIPT = (
    "import bpy, json; "
    "mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH']; "
    "slots = list(set(slot.name for obj in mesh_objs for slot in obj.material_slots if slot.name)); "
    "morphs = list(set(kb.name for obj in mesh_objs if obj.data.shape_keys for kb in obj.data.shape_keys.key_blocks if kb.name != 'Basis')); "
    "print('DYNAMIC_PALS_METADATA_START' + json.dumps({'slots': slots, 'morphs': morphs}) + 'DYNAMIC_PALS_METADATA_END')"
)

def get_virtual_path_for_file(absolute_path: str) -> str:
    clean_path = absolute_path.replace("\\", "/")
    marker = "Pal/Content/"
    if marker in clean_path:
        relative_part = clean_path.split(marker, 1)[1]
        folder_part = "/".join(relative_part.split("/")[:-1]).replace(" ", "_")
        return f"/Game/{folder_part}"
    return ""

def get_blend_files_for_context(fmodel_dir: str | None, unused: None = None) -> list[str]:
    blend_files = []
    if not fmodel_dir or not os.path.exists(fmodel_dir):
        return blend_files
        
    for root, dirs, files in os.walk(fmodel_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith(".blend") and not f.endswith(".blend1"):
                blend_files.append(f)
                
    return sorted(list(set(blend_files)))

def get_all_blend_files_for_workspace(fmodel_root: str, category: str = "Monster") -> dict:
    """Scans all character directories across the workspace to populate cross-pal AnimTarget selections."""
    result = {}
    if not fmodel_root or not os.path.exists(fmodel_root):
        return result
    
    # Search both Vanilla (Pal) and Modded (Palbaker) character trees
    for prefix in ["Pal", "Palbaker"]:
        char_dir = os.path.normpath(os.path.join(fmodel_root, "Exports", "Pal", "Content", prefix, "Model", "Character"))
        if not os.path.exists(char_dir):
            continue
        
        for root, dirs, files in os.walk(char_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.endswith(".blend") and not f.endswith(".blend1"):
                    # Calculate path relative to the Character root (e.g. "Monster/GrimGirl/Braixen")
                    rel_path = os.path.relpath(root, char_dir).replace("\\", "/")
                    parts = rel_path.split("/")
                    
                    if len(parts) >= 2:
                        cat = parts[0]
                        base_pal = parts[1]
                        
                        if base_pal not in result:
                            result[base_pal] = []
                        
                        base_pal_folder = os.path.join(char_dir, cat, base_pal)
                        blend_rel = os.path.relpath(os.path.join(root, f), base_pal_folder).replace("\\", "/")
                        
                        if blend_rel not in result[base_pal]:
                            result[base_pal].append(blend_rel)
                                
    # Sort keys and lists alphabetically
    return {k: sorted(result[k]) for k in sorted(result.keys())}

def sanitize_json_filename(name: str, default_name: str) -> str:
    """Cleans user input to be a safe, valid Windows filename without redundant .json extension."""
    if not name or not name.strip():
        return default_name
    clean = name.strip()
    if clean.lower().endswith(".json"):
        clean = clean[:-5]
    clean = re.sub(r'[\\/*?:"<>|]', '_', clean).strip()
    return clean or default_name


def get_available_materials_for_context(fmodel_root: str, fmodel_dir: str | None, character_id: str, category: str = "Monster") -> list[str]:
    materials = []
    paths_to_check = []

    if fmodel_root:
        base_dir = os.path.join(fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, character_id)
        if os.path.exists(base_dir):
            paths_to_check.append(base_dir)

    if fmodel_dir and os.path.exists(fmodel_dir):
        paths_to_check.append(fmodel_dir)

    for directory in paths_to_check:
        for root, _, files in os.walk(directory):
            for f in files:
                if f.endswith("_blend.json"):
                    sidecar_path = os.path.join(root, f)
                    try:
                        with open(sidecar_path, "r", encoding="utf-8") as f_var:
                            data = json.load(f_var)
                            mats = data.get("materials", {})
                            for mat_name in mats.keys():
                                if mat_name and mat_name not in materials:
                                    materials.append(mat_name)
                    except Exception:
                        pass

    if not materials:
        materials = [
            f"MI_{character_id}_Body_Latex",
            f"MI_{character_id}_Body_Shiny",
            f"MI_{character_id}_Body_Gold"
        ]

    return sorted(materials)

def extract_blend_metadata(blender_path: str, blend_file_path: str) -> dict:
    if not blender_path or not os.path.exists(blender_path) or not blend_file_path or not os.path.exists(blend_file_path):
        return {"slots": [], "morphs": []}

    cmd = [
        blender_path,
        "-b",
        blend_file_path,
        "--python-expr",
        BLENDER_EXTRACTOR_SCRIPT
    ]

    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=creation_flags
        )
        
        match = re.search(r"DYNAMIC_PALS_METADATA_START(.*?)DYNAMIC_PALS_METADATA_END", result.stdout)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        print(f"Error extracting metadata from Blender: {e}")

    return {"slots": [], "morphs": []}

def delta_merge_sidecar(existing_data: dict, fresh_slots: list[str], fresh_morphs: list[str]) -> dict:
    synced = dict(existing_data)
    
    old_overrides = existing_data.get("MaterialOverrides", {})
    new_overrides = {}
    for slot_name in fresh_slots:
        if slot_name in old_overrides:
            new_overrides[slot_name] = old_overrides[slot_name]
    synced["MaterialOverrides"] = new_overrides

    old_morphs = {m.get("Name", m.get("Target")): m for m in existing_data.get("ShapeKeys", existing_data.get("MorphTarget", [])) if m.get("Name") or m.get("Target")}
    new_morphs = []
    for morph_name in fresh_morphs:
        if morph_name in old_morphs:
            new_morphs.append(old_morphs[morph_name])
        else:
            new_morphs.append({
                "Name": morph_name,
                "Mode": "Free",
                "Min": 0.0,
                "Max": 1.0
            })
    synced["ShapeKeys"] = new_morphs

    return synced

def sync_sidecar_metadata(blender_path: str, blend_file_path: str) -> dict:
    root_dir = os.path.dirname(blend_file_path)
    base_name = os.path.splitext(os.path.basename(blend_file_path))[0]
    sidecar_path = os.path.join(root_dir, f"{base_name}_blend.json")

    existing_data = load_sidecar(sidecar_path)
    fresh_metadata = extract_blend_metadata(blender_path, blend_file_path)
    synced_data = delta_merge_sidecar(
        existing_data, 
        fresh_metadata.get("slots", []), 
        fresh_metadata.get("morphs", [])
    )

    save_sidecar(sidecar_path, synced_data)
    return synced_data

def compile_unified_dynamic_pals_json(monster_name: str, dynamic_pals_staging_dir: str, swap_json_dir: str) -> tuple[bool, str]:
    """Compiles local variant manifests into clean, clutter-free Dynamic Pals Format V2 JSON."""
    manifest_name = f"{monster_name}_dynamic_pals.json"
    manifest_path = os.path.join(dynamic_pals_staging_dir, manifest_name)

    if not os.path.exists(manifest_path):
        return True, "No Dynamic Pals variants manifest detected to compile."

    try:
        with open(manifest_path, "r", encoding="utf-8") as f_man:
            manifest_data = json.load(f_man)

        if not manifest_data.get("is_dynamic_pals_active", True):
            target_path = os.path.join(swap_json_dir, f"palbaker-{monster_name}.json")
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except OSError:
                    pass
            return True, f"Dynamic Pals is disabled for {monster_name}. Deployed config removed from game."

        variants_data = manifest_data.get("variants", {})
        variants_list = []
        if isinstance(variants_data, dict):
            for k, v in variants_data.items():
                # Preserve the clean user label instead of overwriting with the full key
                if "label" not in v or not v["label"]:
                    v["label"] = k
                variants_list.append(v)
        elif isinstance(variants_data, list):
            variants_list = variants_data
            
    except Exception as e:
        return False, f"Failed to read Dynamic Pals manifest: {e}"

    category = "Monster"
    parts = dynamic_pals_staging_dir.replace("\\", "/").split("/")
    if "Character" in parts:
        idx = parts.index("Character")
        if monster_name in parts:
            m_idx = parts.index(monster_name)
            if m_idx > idx + 1:
                category = "/".join(parts[idx + 1:m_idx])
            else:
                category = parts[idx + 1]
        elif idx + 1 < len(parts):
            category = parts[idx + 1]

    fmodel_root = ""
    if "Exports" in parts:
        exp_idx = parts.index("Exports")
        # FIXED: Slice UP TO the "Exports" keyword, preventing double /Exports/Exports/ folder queries!
        fmodel_root = "/".join(parts[:exp_idx])
    else:
        fmodel_root = os.path.normpath(os.path.join(dynamic_pals_staging_dir, "..", "..", "..", "..", "..", ".."))


    creator_json = os.path.join(fmodel_root, "Pal", "Content", "Palbaker", "Creator", f"{monster_name}_creator.json")
    is_custom_pal = os.path.exists(creator_json)
    final_character_id = f"MOD_{monster_name}" if is_custom_pal else monster_name

    material_to_virtual_dir = {}
    vanilla_dir = os.path.normpath(os.path.join(fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, monster_name))
    
    vanilla_sidecar_path = os.path.join(vanilla_dir, f"{monster_name}_blend.json")
    if os.path.exists(vanilla_sidecar_path):
        vanilla_vdir = get_virtual_path_for_file(vanilla_sidecar_path)
        try:
            with open(vanilla_sidecar_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for mat_name in data.get("materials", {}).keys():
                    material_to_virtual_dir[mat_name] = vanilla_vdir
        except Exception:
            pass
        
    if os.path.exists(dynamic_pals_staging_dir):
        for root, _, files in os.walk(dynamic_pals_staging_dir):
            for f in files:
                if f.endswith("_blend.json"):
                    sidecar_f_path = os.path.join(root, f)
                    dyn_vdir = get_virtual_path_for_file(sidecar_f_path)
                    try:
                        with open(sidecar_f_path, "r", encoding="utf-8") as file_in:
                            data = json.load(file_in)
                            for mat_name in data.get("materials", {}).keys():
                                material_to_virtual_dir[mat_name] = dyn_vdir
                    except Exception:
                        pass

    skin_map = {}
    manifest_dirty = False

    for v in variants_list:
        if v.get("is_base") and not is_custom_pal:
            continue

        try:
            slots_order = []
            
            # --- Respect AnimTarget for cross-pal path resolution ---
            anim_target = v.get("AnimTarget", "")
            target_base_pal = monster_name
            # Only use anim_target as target_base_pal if it's a bare Pal name (not an Actor Blueprint virtual path)
            if anim_target and not anim_target.startswith("/") and "/" not in anim_target and "\\" not in anim_target:
                target_base_pal = anim_target
            
            dynamic_pals_staging_dir_target = os.path.normpath(os.path.join(fmodel_root, "Exports", "Pal", "Content", "Palbaker", "Model", "Character", category, target_base_pal))
            vanilla_dir_target = os.path.normpath(os.path.join(fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, target_base_pal))

            raw_label = v.get("label", "Default")
            if raw_label.startswith(f"{monster_name}_"):
                skin_label = raw_label[len(monster_name) + 1:]
            elif raw_label == "base":
                skin_label = "Default"
            else:
                skin_label = raw_label

            if v.get("is_base") and is_custom_pal:
                cat_sanitized = category.replace(" ", "_")
                mesh_resolved_path = f"/Game/Pal/Model/Character/{cat_sanitized}/{monster_name}/SK_{monster_name}"
                sidecar_path = os.path.join(vanilla_dir, f"{monster_name}_blend.json")
                blend_base_name = monster_name
                blend_file_path = None
            else:
                blend_base_name = os.path.splitext(v.get("SkeletonSource", "base"))[0]
                if blend_base_name == "base":
                    blend_base_name = target_base_pal

                blend_file_path = None
                sidecar_path = None

                # Search across all potential workspace staging and vanilla directories
                search_roots = [
                    dynamic_pals_staging_dir,
                    dynamic_pals_staging_dir_target,
                    vanilla_dir_target,
                    vanilla_dir
                ]
                search_roots = [os.path.normpath(p) for p in set(search_roots) if p and os.path.exists(p)]

                candidate_names = []
                if blend_base_name and blend_base_name != "base":
                    candidate_names.append(os.path.basename(blend_base_name))
                if skin_label and skin_label != "Default":
                    candidate_names.append(skin_label)
                if raw_label and raw_label not in candidate_names:
                    candidate_names.append(raw_label)
                if target_base_pal and target_base_pal not in candidate_names:
                    candidate_names.append(target_base_pal)

                for search_root in search_roots:
                    for root, _, files in os.walk(search_root):
                        for cname in candidate_names:
                            if not blend_file_path and f"{cname}.blend" in files:
                                blend_file_path = os.path.join(root, f"{cname}.blend")
                            if not sidecar_path and f"{cname}_blend.json" in files:
                                sidecar_path = os.path.join(root, f"{cname}_blend.json")

                        # Subfolder match check (e.g. Boar/SexyRushroarNude/*_blend.json)
                        if not sidecar_path and os.path.basename(root).lower() in [c.lower() for c in candidate_names if c]:
                            for f in files:
                                if f.endswith("_blend.json") and not f.startswith("."):
                                    sidecar_path = os.path.join(root, f)
                                    break

                if blend_file_path:
                    clean_path = blend_file_path.replace("\\", "/")
                    marker = "Pal/Content/"
                    if marker in clean_path:
                        relative_part = clean_path.split(marker, 1)[1]
                        sk_name = os.path.basename(blend_base_name)
                        sk_name = sk_name if sk_name.startswith("SK_") else f"SK_{sk_name}"
                        relative_virtual_dir = "/".join(relative_part.split("/")[:-1]).replace(" ", "_")
                        mesh_resolved_path = f"/Game/{relative_virtual_dir}/{sk_name}"
                    else:
                        cat_sanitized = category.replace(" ", "_")
                        mesh_resolved_path = f"/Game/Pal/Model/Character/{cat_sanitized}/{target_base_pal}/{blend_base_name}/SK_{os.path.basename(blend_base_name)}"
                else:
                    cat_sanitized = category.replace(" ", "_")
                    mesh_resolved_path = f"/Game/Pal/Model/Character/{cat_sanitized}/{monster_name}/SK_{monster_name}"

            sidecar_data = {}
            if sidecar_path and os.path.exists(sidecar_path):
                try:
                    with open(sidecar_path, "r", encoding="utf-8") as f_side:
                        sidecar_data = json.load(f_side)
                        slots_order = list(sidecar_data.get("materials", {}).keys())
                except Exception:
                    pass

            if not slots_order:
                slots_order = ["mi_body", "mi_eye", "mi_mouth"]

            slots_order_lower = [s.lower() for s in slots_order]

            # Detect if custom animations are active in sidecar or variant payload
            custom_anims = sidecar_data.get("custom_animations", {})
            has_custom_anims = bool(custom_anims.get("is_active", False))
            if not has_custom_anims and isinstance(v.get("custom_animations"), dict):
                has_custom_anims = bool(v["custom_animations"].get("is_active", False))

            # Resolve expected Actor Blueprint location for custom animations
            variant_mod_name = ""
            if sidecar_path and os.path.exists(sidecar_path):
                s_base = os.path.splitext(os.path.basename(sidecar_path))[0]
                if s_base.endswith("_blend"):
                    variant_mod_name = s_base[:-6]
            if not variant_mod_name and blend_file_path and os.path.exists(blend_file_path):
                variant_mod_name = os.path.splitext(os.path.basename(blend_file_path))[0]
            if not variant_mod_name:
                if v.get("SkeletonSource") and v.get("SkeletonSource") != "base":
                    variant_mod_name = os.path.splitext(os.path.basename(v["SkeletonSource"]))[0]
            if not variant_mod_name:
                variant_mod_name = skin_label if skin_label != "Default" else monster_name

            is_var = (variant_mod_name.lower() != monster_name.lower() and not (v.get("is_base") and is_custom_pal))
            cat_sanitized = category.replace(" ", "_")

            if "npc" in category.lower():
                bp_virtual_dir = f"/Game/Pal/Blueprint/Character/NPC/{monster_name}/{variant_mod_name}" if is_var else f"/Game/Pal/Blueprint/Character/NPC/{variant_mod_name}"
            elif "player" in category.lower():
                bp_virtual_dir = f"/Game/Pal/Blueprint/Character/Player/{monster_name}/{variant_mod_name}" if is_var else f"/Game/Pal/Blueprint/Character/Player/{variant_mod_name}"
            else:
                bp_virtual_dir = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{monster_name}/{variant_mod_name}" if is_var else f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{variant_mod_name}"

            expected_bp_location = f"{bp_virtual_dir}/BP_{variant_mod_name}"

            # Special Materials
            special_materials = []
            material_overrides = v.get("MaterialOverrides", {})
            for slot_name, mat_override_name in material_overrides.items():
                slot_name_lower = slot_name.lower()
                if slot_name_lower in slots_order_lower and mat_override_name:
                    idx = slots_order_lower.index(slot_name_lower)
                    mat_resolved_dir = material_to_virtual_dir.get(mat_override_name)
                    if not mat_resolved_dir:
                        mat_resolved_dir = get_virtual_path_for_file(sidecar_path) if sidecar_path else f"/Game/Pal/Model/Character/{category.replace(' ', '_')}/{monster_name}"
                        
                    resolved_mat_path = f"{mat_resolved_dir}/{mat_override_name}"
                    special_materials.append({
                        "MaterialAsset": resolved_mat_path,
                        "RandomHue": False,
                        "Index": str(idx)
                    })

            if not special_materials and v.get("SpecialMaterial"):
                for sm in v["SpecialMaterial"]:
                    special_materials.append({
                        "MaterialAsset": sm.get("MaterialAsset", ""),
                        "RandomHue": bool(sm.get("RandomHue", False)),
                        "Index": str(sm.get("Index", "0"))
                    })

            # Shape Keys
            shape_keys = []
            morph_source = v.get("ShapeKeys", v.get("MorphTarget", []))
            for m in morph_source:
                name = m.get("Name", m.get("Target"))
                if not name:
                    continue
                mode = m.get("Mode", m.get("TypeVal", "Free"))
                sk_entry = {
                    "Name": name,
                    "Mode": mode,
                    "Min": float(m.get("Min", 0.0)),
                    "Max": float(m.get("Max", 1.0))
                }
                if "Set" in m:
                    sk_entry["Set"] = float(m["Set"])
                elif m.get("Type") == "Static":
                    sk_entry["Set"] = float(m.get("Set", 0.5))
                shape_keys.append(sk_entry)

            # Construct strictly specified V2 Skin Object (omitting unconfigured fields!)
            skin_obj = {
                "SkinPath": mesh_resolved_path
            }

            if has_custom_anims:
                skin_obj["AnimTarget"] = expected_bp_location
                if v.get("AnimTarget") != expected_bp_location:
                    v["AnimTarget"] = expected_bp_location
                    manifest_dirty = True
            elif anim_target:
                skin_obj["AnimTarget"] = anim_target
            elif v.get("AnimTarget") and v["AnimTarget"].startswith("/Game/Pal/Blueprint/"):
                v.pop("AnimTarget", None)
                manifest_dirty = True

            # Dynamic Pal Icon Resolver
            icon_name = f"T_{os.path.basename(blend_base_name)}_icon_normal"
            if os.path.exists(os.path.join(fmodel_root, "Exports", "Pal", "Content", "Pal", "Texture", "PalIcon", "Normal", f"{icon_name}.png")):
                skin_obj["IconAssetPath"] = f"/Game/Pal/Texture/PalIcon/Normal/{icon_name}"

            if v.get("SetNickname"):
                skin_obj["SetNickname"] = v["SetNickname"]


            if v.get("Gender") and v["Gender"] != "None":
                skin_obj["Gender"] = v["Gender"]

            if v.get("SkinName"):
                skin_obj["SkinName"] = v["SkinName"]

            # 1. Level Range (Only if enabled)
            if v.get("enableLevelRange"):
                skin_obj["MinLevel"] = int(v.get("MinLevel", 5))
                skin_obj["MaxLevel"] = int(v.get("MaxLevel", 20))

            # 2. Trust Range (Only if enabled)
            if v.get("enableTrustRange"):
                skin_obj["MinTrust"] = int(v.get("MinTrust", 2))
                skin_obj["MaxTrust"] = int(v.get("MaxTrust", 40))

            # 3. Rank Range (Only if enabled)
            if v.get("enableRankRange"):
                skin_obj["MinRank"] = int(v.get("MinRank", 50))
                skin_obj["MaxRank"] = int(v.get("MaxRank", 200))

            # 4. Size Multiplier Range (Only if enabled)
            if v.get("enableSizeRange"):
                skin_obj["MinSizeMultiplier"] = float(v.get("MinSizeMultiplier", 0.7))
                skin_obj["MaxSizeMultiplier"] = float(v.get("MaxSizeMultiplier", 2.0))

            # Spawn weight (allows float decimals like 0.1)
            if v.get("SpawnWeight") is not None and v.get("SpawnWeight") != 1:
                sw = float(v["SpawnWeight"])
                skin_obj["SpawnWeight"] = int(sw) if sw.is_integer() else sw

            # Lucky Star
            if v.get("LuckyStarReq") is True:
                skin_obj["LuckyStarReq"] = True

            # Wild Pal Only
            if v.get("IsWildPal") is True:
                skin_obj["IsWildPal"] = True

            # Trait Arrays (Only if populated)
            if v.get("ReqSwap") and len(v["ReqSwap"]) > 0:
                skin_obj["ReqSwap"] = v["ReqSwap"]

            passive_skills = v.get("PassiveSkills", v.get("ReqTrait", []))
            if passive_skills and len(passive_skills) > 0:
                skin_obj["PassiveSkills"] = passive_skills

            if v.get("ReqSwap") and len(v["ReqSwap"]) > 0:
                skin_obj["ReqSwap"] = v["ReqSwap"]
            
            if v.get("PrefTrait") and len(v["PrefTrait"]) > 0:
                skin_obj["PrefTrait"] = v["PrefTrait"]

            if v.get("SkipTrait") and len(v["SkipTrait"]) > 0:
                skin_obj["SkipTrait"] = v["SkipTrait"]

            # Materials & ShapeKeys (Only if populated)
            if special_materials:
                skin_obj["SpecialMaterial"] = special_materials

            if shape_keys:
                skin_obj["ShapeKeys"] = shape_keys

            if v.get("Extra") and v["Extra"] != "{}":
                skin_obj["Extra"] = v["Extra"]

            skin_map[skin_label] = skin_obj

        except Exception as e:
            print(f"Dynamic Pals Mod Builder Warning: Skipping variant compilation: {e}", flush=True)

    default_filename = f"palbaker-{monster_name}"
    custom_name = manifest_data.get("custom_json_name", "")
    final_filename = sanitize_json_filename(custom_name, default_filename)

    output_structure = {
        "ModelPack": manifest_data.get("model_pack_name", f"PalBaker-{monster_name} Replacer Pack"),
        "SkinList": {
            final_character_id: skin_map
        }
    }

    os.makedirs(swap_json_dir, exist_ok=True)
    target_path = os.path.join(swap_json_dir, f"{final_filename}.json")

    if manifest_dirty and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "w", encoding="utf-8") as f_man:
                json.dump(manifest_data, f_man, indent=4)
        except Exception:
            pass

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(output_structure, f, indent=4)
        return True, f"SUCCESS: Compiled and deployed Dynamic Pals V2 config to {os.path.basename(target_path)}"
    except Exception as e:
        return False, f"Failed to write deployment JSON: {e}"


def load_traits_database() -> dict:
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = os.path.normpath(os.path.join(root_dir, "deps", "passive_skills_cache.json"))
    if not os.path.exists(target_path):
        fallback_path = os.path.normpath(os.path.join(root_dir, "traits_db.json"))
        if os.path.exists(fallback_path):
            target_path = fallback_path
            
    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}