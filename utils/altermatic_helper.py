# utils/altermatic_helper.py
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
    "print('ALTERMATIC_METADATA_START' + json.dumps({'slots': slots, 'morphs': morphs}) + 'ALTERMATIC_METADATA_END')"
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
    """Recursively walks through base and child folders to discover all available skeletal meshes."""
    blend_files = []
    if not fmodel_dir or not os.path.exists(fmodel_dir):
        return blend_files
        
    for root, dirs, files in os.walk(fmodel_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith(".blend") and not f.endswith(".blend1"):
                blend_files.append(f)
                
    return sorted(list(set(blend_files)))

def get_available_materials_for_context(fmodel_root: str, fmodel_dir: str | None, character_id: str, category: str = "Monster") -> list[str]:
    """Recursively searches all sibling and nested folders to harvest compiled material instances."""
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
                    except Exception: pass

    if not materials:
        materials = [
            f"MI_{character_id}_Body_Latex",
            f"MI_{character_id}_Body_Shiny",
            f"MI_{character_id}_Body_Gold"
        ]

    return sorted(materials)

def extract_blend_metadata(blender_path: str, blend_file_path: str) -> dict:
    if not blender_path or not os.path.exists(blender_path):
        return {"slots": [], "morphs": []}
    if not blend_file_path or not os.path.exists(blend_file_path):
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
        
        match = re.search(r"ALTERMATIC_METADATA_START(.*?)ALTERMATIC_METADATA_END", result.stdout)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        print(f"Error extracting metadata from Blender: {e}")

    return {"slots": [], "morphs": []}

def delta_merge_sidecar(existing_data: dict, fresh_slots: list[str], fresh_morphs: list[str]) -> dict:
    synced = dict(existing_data)
    
    synced.setdefault("Gender", "None")
    synced.setdefault("IsRarePal", False)
    synced.setdefault("SkinName", "")
    synced.setdefault("ReqTrait", [])
    synced.setdefault("PrefTrait", [])
    
    old_overrides = existing_data.get("MaterialOverrides", {})
    new_overrides = {}
    for slot_name in fresh_slots:
        if slot_name in old_overrides:
            new_overrides[slot_name] = old_overrides[slot_name]
    synced["MaterialOverrides"] = new_overrides

    old_morphs = {m["Target"]: m for m in existing_data.get("MorphTarget", []) if "Target" in m}
    new_morphs = []
    for morph_name in fresh_morphs:
        if morph_name in old_morphs:
            new_morphs.append(old_morphs[morph_name])
        else:
            new_morphs.append({
                "Target": morph_name,
                "Type": "None"
            })
    synced["MorphTarget"] = new_morphs

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

def compile_unified_altermatic_json(monster_name: str, altermatic_staging_dir: str, swap_json_dir: str) -> tuple[bool, str]:
    manifest_name = f"{monster_name}_altermatic.json"
    manifest_path = os.path.join(altermatic_staging_dir, manifest_name)

    if not os.path.exists(manifest_path):
        return True, "No Altermatic variants manifest detected to compile."

    try:
        with open(manifest_path, "r", encoding="utf-8") as f_man:
            manifest_data = json.load(f_man)
        variants_data = manifest_data.get("variants", {})
        
        variants_list = []
        if isinstance(variants_data, dict):
            for k, v in variants_data.items():
                v["label"] = k
                variants_list.append(v)
        elif isinstance(variants_data, list):
            variants_list = variants_data
            
    except Exception as e:
        return False, f"Failed to read Altermatic manifest: {e}"

    category = "Monster"
    parts = altermatic_staging_dir.replace("\\", "/").split("/")
    if "Character" in parts:
        idx = parts.index("Character")
        if idx + 1 < len(parts):
            category = parts[idx + 1]

    swaps_array = []

    fmodel_root = ""
    if "Exports" in parts:
        exp_idx = parts.index("Exports")
        fmodel_root = "/".join(parts[:exp_idx+1])
    else:
        fmodel_root = os.path.normpath(os.path.join(altermatic_staging_dir, "..", "..", "..", "..", "..", ".."))

    creator_json = os.path.join(fmodel_root, "Pal", "Content", "Palbaker", "Creator", f"{monster_name}_creator.json")
    is_custom_pal = os.path.exists(creator_json)
    final_character_id = f"MOD_{monster_name}" if is_custom_pal else monster_name

    material_to_virtual_dir = {}
    vanilla_dir = os.path.normpath(os.path.join(fmodel_root, "Pal", "Content", "Pal", "Model", "Character", category, monster_name))
    
    vanilla_sidecar_path = os.path.join(vanilla_dir, f"{monster_name}_blend.json")
    if os.path.exists(vanilla_sidecar_path):
        vanilla_vdir = get_virtual_path_for_file(vanilla_sidecar_path)
        try:
            with open(vanilla_sidecar_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for mat_name in data.get("materials", {}).keys():
                    material_to_virtual_dir[mat_name] = vanilla_vdir
        except Exception: pass
        
    if os.path.exists(altermatic_staging_dir):
        for root, _, files in os.walk(altermatic_staging_dir):
            for f in files:
                if f.endswith("_blend.json"):
                    alt_sidecar_path = os.path.join(root, f)
                    alt_vdir = get_virtual_path_for_file(alt_sidecar_path)
                    try:
                        with open(alt_sidecar_path, "r", encoding="utf-8") as file_in:
                            data = json.load(file_in)
                            for mat_name in data.get("materials", {}).keys():
                                material_to_virtual_dir[mat_name] = alt_vdir
                    except Exception: pass

    for v in variants_list:
        if v.get("is_base") and not is_custom_pal:
            continue

        try:
            mat_replace_list = []
            slots_order = []
            
            if v.get("is_base") and is_custom_pal:
                cat_sanitized = category.replace(" ", "_")
                mesh_resolved_path = f"/Game/Pal/Model/Character/{cat_sanitized}/{monster_name}/SK_{monster_name}"
                sidecar_path = os.path.join(vanilla_dir, f"{monster_name}_blend.json")
            else:
                blend_base_name = os.path.splitext(v.get("SkeletonSource", "base"))[0]
                if blend_base_name == "base":
                    blend_base_name = monster_name

                blend_file_path = None
                sidecar_path = None
                
                for root, _, files in os.walk(altermatic_staging_dir):
                    if f"{blend_base_name}.blend" in files:
                        blend_file_path = os.path.join(root, f"{blend_base_name}.blend")
                    if f"{blend_base_name}_blend.json" in files:
                        sidecar_path = os.path.join(root, f"{blend_base_name}_blend.json")

                if not blend_file_path or not sidecar_path:
                    for root, _, files in os.walk(vanilla_dir):
                        if not blend_file_path and f"{blend_base_name}.blend" in files:
                            blend_file_path = os.path.join(root, f"{blend_base_name}.blend")
                        if not sidecar_path and f"{blend_base_name}_blend.json" in files:
                            sidecar_path = os.path.join(root, f"{blend_base_name}_blend.json")

                # FIXED: Skip file resolution and fallback to standard unmodded path if base blend is missing
                if blend_file_path:
                    clean_path = blend_file_path.replace("\\", "/")
                    marker = "Pal/Content/"
                    if marker in clean_path:
                        relative_part = clean_path.split(marker, 1)[1]
                        sk_name = blend_base_name if blend_base_name.startswith("SK_") else f"SK_{blend_base_name}"
                        relative_virtual_dir = "/".join(relative_part.split("/")[:-1]).replace(" ", "_")
                        mesh_resolved_path = f"/Game/{relative_virtual_dir}/{sk_name}"
                    else:
                        cat_sanitized = category.replace(" ", "_")
                        mesh_resolved_path = f"/Game/Pal/Model/Character/{cat_sanitized}/{monster_name}/{blend_base_name}/SK_{blend_base_name}"
                else:
                    cat_sanitized = category.replace(" ", "_")
                    mesh_resolved_path = f"/Game/Pal/Model/Character/{cat_sanitized}/{monster_name}/SK_{monster_name}"

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

            material_overrides = v.get("MaterialOverrides", {})
            for slot_name, mat_override_name in material_overrides.items():
                slot_name_lower = slot_name.lower()
                if slot_name_lower in slots_order_lower and mat_override_name:
                    idx = slots_order_lower.index(slot_name_lower)
                    mat_resolved_dir = material_to_virtual_dir.get(mat_override_name)
                    if not  mat_resolved_dir:
                        mat_resolved_dir = get_virtual_path_for_file(sidecar_path) if sidecar_path else f"/Game/Pal/Model/Character/{category.replace(' ', '_')}/{monster_name}"
                        
                    resolved_mat_path = f"{mat_resolved_dir}/{mat_override_name}"
                    mat_replace_list.append({
                        "Index": str(idx),
                        "MatPath": resolved_mat_path
                    })

            compiled_swap = {
                "CharacterID": final_character_id,
                "SwapLabel": v.get("label", ""),
                "SkelMeshPath": mesh_resolved_path,
                "Gender": v.get("Gender", "None")
            }

            if v.get("IsRarePal"):
                compiled_swap["IsRarePal"] = "True"
            if v.get("SkinName"):
                compiled_swap["SkinName"] = v["SkinName"]
            if v.get("ReqTrait"):
                compiled_swap["ReqTrait"] = v["ReqTrait"]
            if v.get("PrefTrait"):
                compiled_swap["PrefTrait"] = v["PrefTrait"]
            if mat_replace_list:
                compiled_swap["MatReplace"] = mat_replace_list

            compiled_morphs = []
            for m in v.get("MorphTarget", []):
                if m.get("Type") == "Static" and "Set" in m:
                    compiled_morphs.append({"Target": m["Target"], "Set": m["Set"]})
                elif m.get("Type") == "Random":
                    compiled_morphs.append({"Target": m["Target"], "Min": m.get("Min", 0.0), "Max": m.get("Max", 1.0), "Type": m.get("TypeVal", "Free")})
            
            if compiled_morphs:
                compiled_swap["MorphTarget"] = compiled_morphs

            swaps_array.append(compiled_swap)
        except Exception as e:
            print(f"Altermatic Mod Builder Warning: Skipping variant compilation: {e}", flush=True)

    output_structure = {
        "PackName": f"PalBaker-{monster_name} Replacer Pack",
        "SkelMeshSwap": swaps_array
    }

    os.makedirs(swap_json_dir, exist_ok=True)
    target_path = os.path.join(swap_json_dir, f"palbaker-{monster_name}.json")

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(output_structure, f, indent=4)
        return True, f"SUCCESS: Compiled and deployed Altermatic config to {target_path}"
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
        except Exception: pass
    return {}