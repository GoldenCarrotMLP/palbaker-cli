# utils/fmodel_helper.py
import os
import json
import shutil
import re
import glob

def normalize_ue_package_path(raw_path: str) -> str:
    """Normalizes any disk or package path into a clean /Game/... or /Engine/... package path."""
    if not raw_path:
        return ""
    clean = raw_path.replace("\\", "/").strip()
    if "." in clean and not clean.endswith((".png", ".tga", ".jpg")):
        clean = clean.split(".")[0]
    clean = clean.strip("/")
    if clean.startswith("Pal/Content/"):
        return "/Game/" + clean[len("Pal/Content/"):]
    elif clean.startswith("Game/"):
        return "/" + clean
    elif clean.startswith("Engine/"):
        return "/" + clean
    elif not clean.startswith("/"):
        return "/Game/" + clean
    return "/" + clean.lstrip("/")

def extract_clean_texture_name(val) -> str:
    """Safely extracts the bare texture asset name from any string, dict, or UObject reference."""
    if not val:
        return ""
    if isinstance(val, dict):
        obj_name = val.get("ObjectName") or val.get("ObjectPath") or ""
        return extract_clean_texture_name(obj_name)
    elif isinstance(val, str):
        clean = val.strip()
        if "'" in clean:
            parts = clean.split("'")
            clean = parts[-2] if len(parts) >= 2 and parts[-2] else parts[0]
        clean = clean.split("/")[-1].split(".")[0]
        return clean
    return ""

def parse_material_instance_json(json_path: str) -> dict | None:
    """Parses a UAssetGUI or FModel MaterialInstance JSON and returns normalized baseline settings."""
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:
        return None

    result = {
        "source_material": os.path.splitext(os.path.basename(json_path))[0],
        "parent_path": "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterBodyBase",
        "scalars": {},
        "vectors": {},
        "textures": {},
        "base_property_overrides": {},
        "subsurface_profile": None
    }

    # Format 1: UAssetGUI (Exports array)
    if isinstance(data, dict) and "Exports" in data:
        exports = data.get("Exports", [])
        imports = data.get("Imports", [])
        if not exports:
            return None
        exp = exports[0]
        props = exp.get("Data", [])

        def resolve_import_name(imp_idx):
            if isinstance(imp_idx, int) and imp_idx < 0 and (-imp_idx - 1) < len(imports):
                return imports[-imp_idx - 1].get("ObjectName", "")
            return ""

        def resolve_import_package(imp_idx):
            if isinstance(imp_idx, int) and imp_idx < 0 and (-imp_idx - 1) < len(imports):
                imp = imports[-imp_idx - 1]
                outer = imp.get("OuterIndex", 0)
                if outer < 0 and (-outer - 1) < len(imports):
                    pkg = imports[-outer - 1].get("ObjectName", "")
                    return pkg if pkg else imp.get("ObjectName", "")
                return imp.get("ObjectName", "")
            return ""

        for p in props:
            p_name = p.get("Name")
            if p_name == "Parent":
                pkg = resolve_import_package(p.get("Value"))
                if pkg: result["parent_path"] = normalize_ue_package_path(pkg)

            elif p_name == "SubsurfaceProfile":
                pkg = resolve_import_package(p.get("Value"))
                if pkg: result["subsurface_profile"] = normalize_ue_package_path(pkg)

            elif p_name == "ScalarParameterValues" and isinstance(p.get("Value"), list):
                for item in p["Value"]:
                    struct_vals = item.get("Value", [])
                    name_val = ""
                    num_val = 0.0
                    for inner in struct_vals:
                        if inner.get("Name") == "ParameterInfo":
                            for pi in inner.get("Value", []):
                                if pi.get("Name") == "Name":
                                    name_val = pi.get("Value")
                        elif inner.get("Name") == "ParameterValue":
                            num_val = float(inner.get("Value", 0.0))
                    if name_val:
                        result["scalars"][name_val] = num_val

            elif p_name == "VectorParameterValues" and isinstance(p.get("Value"), list):
                for item in p["Value"]:
                    struct_vals = item.get("Value", [])
                    name_val = ""
                    col_val = {}
                    for inner in struct_vals:
                        if inner.get("Name") == "ParameterInfo":
                            for pi in inner.get("Value", []):
                                if pi.get("Name") == "Name":
                                    name_val = pi.get("Value")
                        elif inner.get("Name") == "ParameterValue":
                            col = inner.get("Value", {})
                            if isinstance(col, dict):
                                col_val = {
                                    "R": float(col.get("R", 0.0)),
                                    "G": float(col.get("G", 0.0)),
                                    "B": float(col.get("B", 0.0)),
                                    "A": float(col.get("A", 1.0))
                                }
                    if name_val and col_val:
                        result["vectors"][name_val] = col_val

            elif p_name == "TextureParameterValues" and isinstance(p.get("Value"), list):
                for item in p["Value"]:
                    struct_vals = item.get("Value", [])
                    name_val = ""
                    tex_imp = 0
                    for inner in struct_vals:
                        if inner.get("Name") == "ParameterInfo":
                            for pi in inner.get("Value", []):
                                if pi.get("Name") == "Name":
                                    name_val = pi.get("Value")
                        elif inner.get("Name") == "ParameterValue":
                            tex_imp = inner.get("Value")
                    tex_raw = resolve_import_name(tex_imp)
                    tex_pkg = resolve_import_package(tex_imp)
                    tex_obj = extract_clean_texture_name(tex_raw)
                    if name_val and tex_obj and tex_obj != "None":
                        result["textures"][name_val] = tex_obj
                        if tex_pkg:
                            result.setdefault("texture_paths", {})[name_val] = normalize_ue_package_path(tex_pkg)

            elif p_name == "BasePropertyOverrides" and isinstance(p.get("Value"), list):
                for override in p["Value"]:
                    oname = override.get("Name")
                    oval = override.get("Value")
                    if oname:
                        result["base_property_overrides"][oname] = oval

        return result

    # Format 2: FModel / CUE4Parse flat list
    elif isinstance(data, list) and len(data) > 0:
        obj = data[0]
        props = obj.get("Properties", {})
        if not props: return None

        parent_obj = props.get("Parent", {})
        if isinstance(parent_obj, dict):
            p_path = parent_obj.get("ObjectPath", "").split(".")[0]
            if p_path:
                result["parent_path"] = normalize_ue_package_path(p_path)

        sp_obj = props.get("SubsurfaceProfile", {})
        if isinstance(sp_obj, dict):
            s_path = sp_obj.get("ObjectPath", "").split(".")[0]
            if s_path:
                result["subsurface_profile"] = normalize_ue_package_path(s_path)

        for item in props.get("ScalarParameterValues", []):
            p_info = item.get("ParameterInfo", {})
            name = p_info.get("Name") if isinstance(p_info, dict) else item.get("Name")
            val = item.get("ParameterValue")
            if name and val is not None:
                result["scalars"][name] = float(val)

        for item in props.get("VectorParameterValues", []):
            p_info = item.get("ParameterInfo", {})
            name = p_info.get("Name") if isinstance(p_info, dict) else item.get("Name")
            val = item.get("ParameterValue")
            if name and isinstance(val, dict):
                result["vectors"][name] = {
                    "R": float(val.get("R", 0.0)),
                    "G": float(val.get("G", 0.0)),
                    "B": float(val.get("B", 0.0)),
                    "A": float(val.get("A", 1.0))
                }

        for item in props.get("TextureParameterValues", []):
            p_info = item.get("ParameterInfo", {})
            name = p_info.get("Name") if isinstance(p_info, dict) else item.get("Name")
            tex_val = item.get("ParameterValue")
            tex_name = extract_clean_texture_name(tex_val)
            if name and tex_name and tex_name != "None":
                result["textures"][name] = tex_name
                # Save exact Unreal package path for effect and shared textures
                if isinstance(tex_val, dict) and tex_val.get("ObjectPath"):
                    raw_pkg = tex_val["ObjectPath"].split(".")[0]
                    result.setdefault("texture_paths", {})[name] = normalize_ue_package_path(raw_pkg)
                elif isinstance(tex_val, str) and "/" in tex_val:
                    raw_pkg = tex_val.split(".")[0]
                    result.setdefault("texture_paths", {})[name] = normalize_ue_package_path(raw_pkg)

        bpo = props.get("BasePropertyOverrides", {})
        if isinstance(bpo, dict):
            result["base_property_overrides"] = bpo

        return result

    # Format 3: FModel / CUE4Parse dictionary format (with "Textures" or "Parameters")
    elif isinstance(data, dict) and ("Textures" in data or "Parameters" in data):
        tex_dict = data.get("Textures", {})
        if isinstance(tex_dict, dict):
            for p_name, p_path in tex_dict.items():
                if isinstance(p_path, str):
                    clean_tex = extract_clean_texture_name(p_path)
                    # Filter out self-referential texture name entries generated by FModel
                    if clean_tex and clean_tex != "None" and p_name.lower() != clean_tex.lower():
                        result["textures"][p_name] = clean_tex
                        raw_pkg = p_path.split(".")[0]
                        result.setdefault("texture_paths", {})[p_name] = normalize_ue_package_path(raw_pkg)

        params = data.get("Parameters", {})
        if isinstance(params, dict):
            for s_name, s_val in params.get("Scalars", {}).items():
                try:
                    result["scalars"][s_name] = float(s_val)
                except (ValueError, TypeError):
                    pass

            for c_name, c_val in params.get("Colors", {}).items():
                if isinstance(c_val, dict):
                    result["vectors"][c_name] = {
                        "R": float(c_val.get("R", 0.0)),
                        "G": float(c_val.get("G", 0.0)),
                        "B": float(c_val.get("B", 0.0)),
                        "A": float(c_val.get("A", 1.0))
                    }

            props = params.get("Properties", {})
            bpo = props.get("BasePropertyOverrides", {})
            if isinstance(bpo, dict):
                result["base_property_overrides"] = bpo

            sp = props.get("SubsurfaceProfile", {})
            if isinstance(sp, dict) and sp.get("ObjectPath"):
                raw_sp = sp["ObjectPath"].split(".")[0]
                result["subsurface_profile"] = normalize_ue_package_path(raw_sp)

            parent_val = props.get("Parent") or data.get("parent_class")
            if parent_val:
                parent_path_str = parent_val.get("ObjectPath", "") if isinstance(parent_val, dict) else str(parent_val)
                if parent_path_str:
                    result["parent_path"] = normalize_ue_package_path(parent_path_str.split(".")[0])

        return result

    return None

def match_material_to_parent(slot_name: str, available_parent_jsons: list[str]) -> str | None:
    """Matches a child material slot name to the best parent MI JSON using keyword/token overlap."""
    if not available_parent_jsons:
        return None
        
    clean_slot = slot_name.lower().replace("mi_", "").replace("sk_", "").replace("m_", "")
    slot_tokens = set(re.split(r'[^a-zA-Z0-9]', clean_slot))
    
    exclusive_keywords = {"body", "eye", "mouth", "hair", "tail", "head", "horn", "wing", "fur", "cloth", "armor", "extra", "vfx", "effect", "mane"}
    slot_exclusives = slot_tokens.intersection(exclusive_keywords)

    best_match = None
    best_score = -1

    for json_path in available_parent_jsons:
        fname = os.path.splitext(os.path.basename(json_path))[0].lower()
        clean_parent = fname.replace("mi_", "").replace("sk_", "").replace("m_", "")
        parent_tokens = set(re.split(r'[^a-zA-Z0-9]', clean_parent))
        parent_exclusives = parent_tokens.intersection(exclusive_keywords)
        
        if slot_exclusives and parent_exclusives and not (slot_exclusives & parent_exclusives):
            continue
            
        score = len(slot_tokens & parent_tokens)
        if slot_exclusives and (slot_exclusives & parent_exclusives):
            score += 10

        if score > best_score:
            best_score = score
            best_match = json_path

    return best_match

def sync_sidecar_material_baselines(sidecar_path: str, base_pal: str, category: str, fmodel_root: str, settings: dict = None):
    """
    Inspects sidecar materials. If any slot lacks 'baseline_settings', queries parent material
    instances on disk (or game archives) and stores all settings/overrides directly into the sidecar.
    """
    from utils.sidecar_helper import load_sidecar, save_sidecar
    if not os.path.exists(sidecar_path):
        return

    sidecar_data = load_sidecar(sidecar_path)
    materials = sidecar_data.get("materials", {})
    if not materials:
        return

    needs_sync = any(
        "baseline_settings" not in mat_data or 
        not mat_data["baseline_settings"].get("textures") or 
        not mat_data["baseline_settings"].get("texture_paths") or
        "Content" in mat_data["baseline_settings"].get("parent_path", "")
        for mat_data in materials.values()
    )
    if not needs_sync:
        return

    print(f"[PalBaker Material Sync] Synchronizing baseline material settings for {os.path.basename(sidecar_path)}...", flush=True)

    parent_dir = os.path.normpath(os.path.join(fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal))
    parent_jsons = []
    if os.path.exists(parent_dir):
        parent_jsons = [os.path.join(parent_dir, f) for f in os.listdir(parent_dir) if f.startswith("MI_") and f.endswith(".json")]

    if not parent_jsons and settings:
        try:
            from utils.extractor.core import extract_game_files
            temp_extract = os.path.join(fmodel_root, ".temp_mat_extract")
            extract_game_files(settings, [f"Pal/Content/Pal/Model/Character/{category}/{base_pal}/MI_*"], temp_extract, format_type="json")
            for root, _, files in os.walk(temp_extract):
                for f in files:
                    if f.startswith("MI_") and f.endswith(".json"):
                        parent_jsons.append(os.path.join(root, f))
        except Exception:
            pass

    if not parent_jsons:
        print(f"[PalBaker Material Sync Warning] No parent material instances found for {base_pal}.", flush=True)
        return

    updated = False
    for mat_name, mat_data in materials.items():
        baseline_curr = mat_data.get("baseline_settings", {})
        if (
            "baseline_settings" not in mat_data or 
            not baseline_curr.get("textures") or 
            "Content" in baseline_curr.get("parent_path", "")
        ):
            matched_json = match_material_to_parent(mat_name, parent_jsons)
            if matched_json:
                parsed_baseline = parse_material_instance_json(matched_json)
                if parsed_baseline:
                    mat_data["baseline_settings"] = parsed_baseline
                    if not mat_data.get("parent_class") or "CharacterBodyBase" in mat_data.get("parent_class", ""):
                        mat_data["parent_class"] = parsed_baseline.get("parent_path", mat_data.get("parent_class"))
                    updated = True
                    print(f"  ✓ Synced baseline settings for '{mat_name}' <- '{parsed_baseline['source_material']}'", flush=True)

    if updated:
        save_sidecar(sidecar_path, sidecar_data)

def harvest_texture_references(json_data):
    """
    Yields tuples of (parameter_name, ue_path) from various FModel JSON formats.
    """
    if isinstance(json_data, dict):
        if "Textures" in json_data and isinstance(json_data["Textures"], dict):
            for param, path in json_data["Textures"].items():
                if isinstance(path, str):
                    yield param, path
        
        props = json_data.get("Properties", {})
        for tpv in props.get("TextureParameterValues", []):
            param_name = tpv.get("ParameterInfo", {}).get("Name")
            param_val = tpv.get("ParameterValue", {})
            if isinstance(param_val, dict):
                path = param_val.get("ObjectPath") or param_val.get("ObjectName")
                if param_name and path:
                    yield param_name, path
            elif isinstance(param_val, str):
                if param_name:
                    yield param_name, param_val

        params = json_data.get("Parameters", {})
        if isinstance(params, dict):
            if "Textures" in params and isinstance(params["Textures"], dict):
                for param, path in params["Textures"].items():
                    if isinstance(path, str):
                        yield param, path

    elif isinstance(json_data, list):
        for item in json_data:
            if isinstance(item, dict) and "Properties" in item:
                props = item["Properties"]
                for tpv in props.get("TextureParameterValues", []):
                    param_name = tpv.get("ParameterInfo", {}).get("Name")
                    param_val = tpv.get("ParameterValue", {})
                    if isinstance(param_val, dict):
                        path = param_val.get("ObjectPath") or param_val.get("ObjectName")
                        if param_name and path:
                            yield param_name, path
                    elif isinstance(param_val, str):
                        if param_name:
                            yield param_name, param_val


def clean_ue_path(ue_path: str) -> str:
    """
    Strips type-wrappers, quotes, package suffixes, and object index markers.
    """
    if "'" in ue_path:
        ue_path = ue_path.split("'")[1]
    
    if "." in ue_path:
        parts = ue_path.split(".")
        last_part = parts[-1]
        main_path = parts[0]
        if os.path.basename(main_path) == last_part or last_part.isdigit():
            ue_path = main_path
        else:
            ue_path = main_path
            
    ue_path = ue_path.replace("\\", "/").strip("/")
    return ue_path


def find_physical_texture(fmodel_root: str, ue_path: str) -> str | None:
    """
    Resolves virtual package paths to actual image files on disk.
    """
    cleaned = clean_ue_path(ue_path)
    rel_path = cleaned
    if rel_path.startswith("Pal/Content/"):
        rel_path = rel_path.replace("Pal/Content/", "Exports/Pal/Content/")
    elif rel_path.startswith("Game/"):
        rel_path = rel_path.replace("Game/", "Exports/Pal/Content/")
    elif rel_path.startswith("/Game/"):
        rel_path = rel_path.replace("/Game/", "Exports/Pal/Content/")
        
    candidates = []
    if "/" in rel_path or "\\" in rel_path:
        base_candidates = [rel_path]
        if "Monster" in rel_path and "Pending Monster" not in rel_path:
            base_candidates.append(rel_path.replace("/Monster/", "/Pending Monster/"))
        if "Pending Monster" in rel_path:
            base_candidates.append(rel_path.replace("/Pending Monster/", "/Monster/"))
            
        for bc in base_candidates:
            norm_bc = os.path.normpath(bc)
            candidates.append(os.path.join(fmodel_root, norm_bc))
            
    extensions = [".png", ".tga", ".jpg", ".jpeg"]
    for cand in candidates:
        for ext in extensions:
            full_path = cand + ext
            if os.path.exists(full_path):
                return full_path
                
    filename = os.path.basename(cleaned)
    if filename:
        search_dir = os.path.join(fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character")
        if os.path.exists(search_dir):
            for root, _, files in os.walk(search_dir):
                for f in files:
                    name_without_ext, ext = os.path.splitext(f)
                    if name_without_ext.lower() == filename.lower() and ext.lower() in extensions:
                        return os.path.join(root, f)
                        
    return None


def search_for_json(fmodel_root: str, filename: str) -> str | None:
    """
    Performs a recursive search starting from the Character base folder 
    for the specified filename.
    """
    search_dir = os.path.join(fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character")
    if not os.path.exists(search_dir):
        return None
        
    for root, _, files in os.walk(search_dir):
        for f in files:
            if f.lower() == filename.lower():
                return os.path.join(root, f)
    return None


def resolve_and_copy_material_json(material_name: str, fmodel_dir: str, fmodel_root: str) -> dict | None:
    """
    Finds a material JSON across fmodel output, extracts texture mappings, 
    copies missing files locally, and returns the constructed material mapping block.
    """
    target_file = f"{material_name}.json"
    local_path = os.path.join(fmodel_dir, target_file)
    
    # Check locally first, fallback to recursive search
    json_path = local_path if os.path.exists(local_path) else search_for_json(fmodel_root, target_file)
    
    if not json_path or not os.path.exists(json_path):
        print(f"  [Failure] Could not resolve JSON for material: {material_name}", flush=True)
        return None
        
    print(f"  [Resolved] Material JSON found at: {json_path}", flush=True)
    try:
        # FIXED: Use utf-8-sig encoding to safely strip FModel Byte Order Marks (BOM)
        with open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  Error reading resolved JSON: {e}", flush=True)
        return None

    parent_class = "CharacterBodyBase"
    if isinstance(data, dict):
        if "Properties" in data:
            props = data["Properties"]
            if "Parent" in props:
                parent_class = props["Parent"].get("ObjectName", "CharacterBodyBase")
        elif "Parameters" in data:
            props = data.get("Parameters", {}).get("Properties", {})
            if "Parent" in props:
                parent_class = props["Parent"].get("ObjectName", "CharacterBodyBase")
            elif "parent_class" in data:
                parent_class = data["parent_class"]
    elif isinstance(data, list) and len(data) > 0:
        props = data[0].get("Properties", {})
        if "Parent" in props:
            parent_class = props["Parent"].get("ObjectName", "CharacterBodyBase")

    if "Material'" in parent_class or "MaterialInstanceConstant'" in parent_class:
        parent_class = parent_class.split("'")[1]

    parameters = {}
    harvested = list(harvest_texture_references(data))
    
    for param_name, ue_path in harvested:
        cleaned = clean_ue_path(ue_path)
        tex_filename = os.path.basename(cleaned)
        parameters[param_name] = tex_filename

        # Perform the asset pulling and copy
        local_exists = any(os.path.exists(os.path.join(fmodel_dir, f"{tex_filename}{ext}")) for ext in [".png", ".tga", ".jpg", ".jpeg"])
        if not local_exists:
            physical_path = find_physical_texture(fmodel_root, ue_path)
            if physical_path and os.path.exists(physical_path):
                dest_path = os.path.join(fmodel_dir, f"{tex_filename}{os.path.splitext(physical_path)[1]}")
                print(f"  -> Copying missing dependency: {os.path.basename(physical_path)} -> {fmodel_dir}", flush=True)
                try:
                    shutil.copy2(physical_path, dest_path)
                except Exception as e:
                    print(f"  Failed copy: {e}", flush=True)
            else:
                print(f"  ⚠️ Shared asset path missing: {ue_path}", flush=True)

    return {
        "parent_class": parent_class,
        "parameters": parameters
    }
def preprocess_fmodel_textures(fmodel_dir: str, fmodel_root: str):
    """
    Preprocess existing local folder JSON configurations before running Blender.
    """
    if not os.path.exists(fmodel_dir):
        return

    print("Preprocessing existing local FModel materials...", flush=True)
    materials_metadata = {}

    for file in os.listdir(fmodel_dir):
        if not file.endswith(".json") or file in [".palbaker_state.json", "import_config.json", "materials_metadata.json", "bone_data.json"]:
            continue
            
        mat_name = os.path.splitext(file)[0]
        resolved = resolve_and_copy_material_json(mat_name, fmodel_dir, fmodel_root)
        if resolved:
            materials_metadata[mat_name] = resolved

    if materials_metadata:
        meta_path = os.path.join(fmodel_dir, "materials_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(materials_metadata, f, indent=4)