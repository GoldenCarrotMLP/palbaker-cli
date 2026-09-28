# unreal_scripts/materials.py
import unreal  # type: ignore
import json
import os
import re

SPECIAL_PARENT_MATERIALS = {
    "m_pal_twinkle": "/Game/Pal/Model/Character/Monster/DreamDemon/M_Pal_Twinkle",
    "m_pal_dream": "/Game/Pal/Model/Character/Monster/DreamDemon/M_Pal_Dream",
    "m_pal_fire": "/Game/Pal/Model/Character/Monster/Kitsunebi/M_Pal_Fire",
    "m_pal_manticore_fire": "/Game/Pal/Model/Character/Monster/Manticore/M_Pal_Manticore_Fire",
    "m_nightlady": "/Game/Pal/Model/Character/Monster/NightLady/M_NightLady",
    "m_pallit_rainbow": "/Game/Pal/Model/Character/Monster/YakushimaMonster001_Rainbow/M_PalLit_Rainbow",
}

# FIXED: Removed the Python 3.10+ `-> str | None` hint so Unreal Engine 5.1's Python 3.9 can parse it!
def resolve_special_parent_material(mat_name: str):
    """Matches material slot names (including Blender .001 suffixes or MI_ prefixes) to special parent materials."""
    if not mat_name:
        return None
    clean = re.sub(r'\.\d+$', '', mat_name.strip()).lower()
    if clean in SPECIAL_PARENT_MATERIALS:
        return SPECIAL_PARENT_MATERIALS[clean]
    
    # Handle cases where user prefixed with MI_ instead of M_
    if clean.startswith("mi_"):
        alt_m = "m_" + clean[3:]
        if alt_m in SPECIAL_PARENT_MATERIALS:
            return SPECIAL_PARENT_MATERIALS[alt_m]
        alt_direct = clean[1:]  # e.g. mi_nightlady -> m_nightlady
        if alt_direct in SPECIAL_PARENT_MATERIALS:
            return SPECIAL_PARENT_MATERIALS[alt_direct]

    return None

def sanitize_asset_name(name):
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized.strip('_')

def find_best_texture_match(slot_name, textures, suffix):
    clean_slot = re.sub(r'^(?:t_mi_|mi_|m_|sk_)', '', slot_name.lower())
    slot_tokens = set(clean_slot.split("_"))
    
    best_match = None
    best_score = 0.0
    
    exclusive_keywords = {"body", "eye", "mouth", "hair", "tail", "head"}
    slot_exclusives = slot_tokens.intersection(exclusive_keywords)
    non_base_suffixes = ["_n", "_normal", "_m", "_s", "_specular", "_param", "_mrao", "_ao", "_em", "_rgn"]
    
    for tex in textures:
        tex_name = os.path.splitext(os.path.basename(tex))[0].lower()
        is_suffix_match = False
        
        if suffix == "B":
            if any(tex_name.endswith(s) for s in ["_b", "_d", "_albedo", "_basecolor"]):
                is_suffix_match = True
            elif not any(tex_name.endswith(s) for s in non_base_suffixes):
                is_suffix_match = True
        elif suffix == "N":
            if any(tex_name.endswith(s) for s in ["_n", "_normal"]):
                is_suffix_match = True
        elif suffix == "M":
            if any(tex_name.endswith(s) for s in ["_m", "_s", "_specular", "_param", "_mrao"]):
                is_suffix_match = True
                
        if not is_suffix_match:
            continue
            
        clean_tex_name = tex_name
        for s in non_base_suffixes + ["_b", "_d", "_albedo", "_basecolor"]:
            if clean_tex_name.endswith(s):
                clean_tex_name = clean_tex_name[:-len(s)]
                break
                
        clean_tex_name = re.sub(r'^(?:t_mi_|t_|mi_|m_)', '', clean_tex_name)
            
        tex_tokens = set(clean_tex_name.split("_"))
        
        tex_exclusives = tex_tokens.intersection(exclusive_keywords)
        if tex_exclusives and not tex_exclusives.issubset(slot_exclusives):
            continue
        
        intersection = len(slot_tokens.intersection(tex_tokens))
        union = len(slot_tokens.union(tex_tokens))
        score = intersection / union if union > 0 else 0
        
        if score > best_score:
            best_score = score
            best_match = tex
            
    return best_match if best_score > 0 else None

def build_materials_heuristically(ue_path, textures, material_slots, preserve_materials=False):
    print("No Material Metadata found. Running fallback heuristic suffix binder...")
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    mi_assets = []
    
    for slot_name in material_slots:
        sanitized_slot = sanitize_asset_name(slot_name)
        mi_path = f"{ue_path}/{sanitized_slot}"
        mi_asset = None
        
        if unreal.EditorAssetLibrary.does_asset_exist(mi_path):
            existing_asset = unreal.EditorAssetLibrary.load_asset(mi_path)
            
            if preserve_materials and existing_asset:
                print(f"  [Preserve] Preserving custom shaders for existing asset: {sanitized_slot}")
                tex_b = find_best_texture_match(sanitized_slot, textures, "B")
                if tex_b:
                    loaded_tex = unreal.EditorAssetLibrary.load_asset(f"{ue_path}/{os.path.splitext(os.path.basename(tex_b))[0]}")
                    if loaded_tex and isinstance(loaded_tex, unreal.Texture):
                        unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(existing_asset, unreal.Name("Base Texture"), loaded_tex)
                mi_assets.append((sanitized_slot.lower(), existing_asset))
                continue
                
            if existing_asset and isinstance(existing_asset, unreal.MaterialInstanceConstant):
                print(f"Loading existing material instance: {sanitized_slot}")
                mi_asset = existing_asset
            else:
                print(f"Asset '{sanitized_slot}' already exists but is not a MaterialInstanceConstant. Deleting...", flush=True)
                unreal.EditorAssetLibrary.delete_asset(mi_path)
                
        if not mi_asset:
            print(f"Creating new material instance: {sanitized_slot}")
            factory = unreal.MaterialInstanceConstantFactoryNew()
            created = asset_tools.create_asset(sanitized_slot, ue_path, unreal.MaterialInstanceConstant.static_class(), factory)
            if created:
                mi_asset = unreal.EditorAssetLibrary.load_asset(mi_path)
                
        if not mi_asset or not isinstance(mi_asset, unreal.MaterialInstanceConstant):
            continue
            
        lower_name = sanitized_slot.lower()
        special_parent = resolve_special_parent_material(sanitized_slot) or resolve_special_parent_material(slot_name)
        
        if special_parent:
            parent_path = special_parent
            print(f"  [Special Material] Matched '{sanitized_slot}' -> Parent: {parent_path}")
        elif "eye" in lower_name or "mouth" in lower_name:
            parent_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterEyeBase"
        elif "hair" in lower_name:
            parent_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterHairBase"
        else:
            parent_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterBodyBase"
            
        parent_mat = unreal.EditorAssetLibrary.load_asset(parent_path)
        if parent_mat:
            unreal.MaterialEditingLibrary.set_material_instance_parent(mi_asset, parent_mat)
            
        tex_b = find_best_texture_match(sanitized_slot, textures, "B")
        if tex_b:
            loaded_tex = unreal.EditorAssetLibrary.load_asset(f"{ue_path}/{os.path.splitext(os.path.basename(tex_b))[0]}")
            if loaded_tex and isinstance(loaded_tex, unreal.Texture):
                unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi_asset, unreal.Name("Base Texture"), loaded_tex)
                print(f"  Bound BaseColor: {os.path.basename(tex_b)}")
                
        tex_n = find_best_texture_match(sanitized_slot, textures, "N")
        if tex_n:
            loaded_tex = unreal.EditorAssetLibrary.load_asset(f"{ue_path}/{os.path.splitext(os.path.basename(tex_n))[0]}")
            if loaded_tex and isinstance(loaded_tex, unreal.Texture):
                unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi_asset, unreal.Name("Normal Map"), loaded_tex)
                print(f"  Bound Normal: {os.path.basename(tex_n)}")
                
        tex_m = find_best_texture_match(sanitized_slot, textures, "M")
        if tex_m:
            loaded_tex = unreal.EditorAssetLibrary.load_asset(f"{ue_path}/{os.path.splitext(os.path.basename(tex_m))[0]}")
            if loaded_tex and isinstance(loaded_tex, unreal.Texture):
                unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi_asset, unreal.Name("MetallicRoughnessOcclusionSpecularTexture"), loaded_tex)
                print(f"  Bound ParameterMap: {os.path.basename(tex_m)}")
                
        unreal.EditorAssetLibrary.save_loaded_asset(mi_asset)
        mi_assets.append((sanitized_slot.lower(), mi_asset))
        
    return mi_assets

def build_materials(ue_path, json_path, textures, target_asset_path, preserve_materials=False, base_pal="", category="Monster"):
    material_slots = []
    if target_asset_path:
        mesh = unreal.EditorAssetLibrary.load_asset(target_asset_path)
        if mesh:
            asset_class = mesh.get_class().get_name()
            if asset_class == "SkeletalMesh":
                for mat in mesh.materials:
                    material_slots.append(str(mat.material_slot_name))
            elif asset_class == "StaticMesh":
                for mat in getattr(mesh, "static_materials", []):
                    material_slots.append(str(mat.material_slot_name))

    materials_metadata = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            materials_metadata = data.get("materials", {})
        except Exception as e:
            print(f"Warning: Failed to parse {json_path}: {e}")

    if materials_metadata:
        print("Running Topological Material Binder with Baseline Settings...")
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        mi_assets = []
        
        # Pre-resolve texture validation across all materials to catch missing textures early
        local_tex_basenames = {os.path.splitext(os.path.basename(p))[0].lower() for p in textures}
        cat_sanitized = category.replace(" ", "_")
        parent_ue_dir = f"/Game/Pal/Model/Character/{cat_sanitized}/{base_pal}" if base_pal else ""

        for mat_name, data in materials_metadata.items():
            baseline_cfg = data.get("baseline_settings", {})
            baseline_textures = baseline_cfg.get("textures", {})
            baseline_paths = baseline_cfg.get("texture_paths", {})
            blender_textures = data.get("textures", {})

            # 1. Resolve replaced textures FIRST to avoid fake alerts
            active_textures = dict(baseline_textures)
            active_paths = dict(baseline_paths)
            for p_name, t_val in blender_textures.items():
                if not t_val:
                    continue

                # Strip accidental T_MI_ prefix
                if t_val.startswith("T_MI_") or t_val.startswith("t_mi_"):
                    t_val = "T_" + t_val[5:]

                # Prevent phantom Blender parameters on materials whose baseline shader doesn't use them
                if baseline_textures and p_name not in baseline_textures:
                    clean_check = t_val.split(".")[0].lower()
                    if clean_check not in local_tex_basenames:
                        continue

                active_textures[p_name] = t_val
                active_paths.pop(p_name, None)

            # 2. Validate all required textures exist in Unreal or local import queue
            missing_textures = []
            for p_name, t_name in active_textures.items():
                if not t_name or t_name == "None":
                    continue
                clean_t = t_name.split(".")[0]
                clean_t_lower = clean_t.lower()

                # Check known full package path from baseline first
                known_full_path = active_paths.get(p_name)
                if known_full_path and unreal.EditorAssetLibrary.does_asset_exist(known_full_path):
                    continue

                # Search candidate locations:
                # A) Local PNG import buffer
                if clean_t_lower in local_tex_basenames:
                    continue
                # B) Existing target UE path
                if unreal.EditorAssetLibrary.does_asset_exist(f"{ue_path}/{clean_t}"):
                    continue
                # C) Parent Pal's UE path
                if parent_ue_dir and unreal.EditorAssetLibrary.does_asset_exist(f"{parent_ue_dir}/{clean_t}"):
                    continue
                # D) Common texture library & Effect textures library
                if unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Pal/Texture/{clean_t}") or unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Pal/Texture/PalIcon/Normal/{clean_t}"):
                    continue
                if unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Pal/Effect/Textures/{clean_t}") or unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Pal/Effect/Common/{clean_t}"):
                    continue
                # D2) Shared Material default textures & Engine fallbacks
                if unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Pal/Material/{clean_t}") or unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Pal/Material/Character/Common/{clean_t}"):
                    continue
                if unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Pal/Texture/ModelCommon/FacialMask/{clean_t}") or unreal.EditorAssetLibrary.does_asset_exist(f"/Game/Mods/{clean_t}"):
                    continue
                if unreal.EditorAssetLibrary.does_asset_exist(f"/Engine/EngineResources/{clean_t}") or unreal.EditorAssetLibrary.does_asset_exist(f"/Engine/EngineMaterials/{clean_t}"):
                    continue
                # E) Full game path
                if "/" in clean_t and unreal.EditorAssetLibrary.does_asset_exist(clean_t):
                    continue

                missing_textures.append((p_name, clean_t))

            if missing_textures:
                print("\n" + "=" * 70, flush=True)
                print(f"❌ [PalBaker Material Error] Material '{mat_name}' validation failed!", flush=True)
                print("The following required textures were not found in Unreal or the workspace:", flush=True)
                for p_k, t_k in missing_textures:
                    print(f"  • Parameter '{p_k}': Missing texture '{t_k}'", flush=True)
                print("=" * 70 + "\n", flush=True)
                raise RuntimeError(f"Missing required textures for material '{mat_name}': {[t for _, t in missing_textures]}")

            sanitized_name = sanitize_asset_name(mat_name)
            mi_path = f"{ue_path}/{sanitized_name}"
            mi_asset = None
            
            if unreal.EditorAssetLibrary.does_asset_exist(mi_path):
                existing_asset = unreal.EditorAssetLibrary.load_asset(mi_path)
                
                if preserve_materials and existing_asset:
                    print(f"  [Preserve] Preserving custom shaders for existing asset: {sanitized_name}")
                    for param_name, tex_name in active_textures.items():
                        clean_tex = tex_name.split(".")[0]
                        loaded_tex = (
                            unreal.EditorAssetLibrary.load_asset(f"{ue_path}/{clean_tex}") or
                            (unreal.EditorAssetLibrary.load_asset(f"{parent_ue_dir}/{clean_tex}") if parent_ue_dir else None) or
                            unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Texture/{clean_tex}")
                        )
                        if loaded_tex and isinstance(loaded_tex, unreal.Texture):
                            unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(existing_asset, unreal.Name(param_name), loaded_tex)
                    mi_assets.append((sanitized_name.lower(), existing_asset))
                    continue
                    
                if existing_asset and isinstance(existing_asset, unreal.MaterialInstanceConstant):
                    print(f"Loading existing material instance: {sanitized_name}")
                    mi_asset = existing_asset
                else:
                    print(f"Asset '{sanitized_name}' already exists but is not a MaterialInstanceConstant. Deleting...", flush=True)
                    unreal.EditorAssetLibrary.delete_asset(mi_path)
            
            if not mi_asset:
                print(f"Creating new material instance: {sanitized_name}")
                factory = unreal.MaterialInstanceConstantFactoryNew()
                created = asset_tools.create_asset(sanitized_name, ue_path, unreal.MaterialInstanceConstant.static_class(), factory)
                if created:
                    mi_asset = unreal.EditorAssetLibrary.load_asset(mi_path)
                    
            if not mi_asset or not isinstance(mi_asset, unreal.MaterialInstanceConstant):
                continue
                
            # --- 1. SET PARENT MATERIAL (FLAT SIBLING COPY) ---
            parent_path = baseline_cfg.get("parent_path") or data.get("parent_class", "")
            special_parent = (
                resolve_special_parent_material(sanitized_name) or 
                resolve_special_parent_material(mat_name) or
                resolve_special_parent_material(parent_path)
            )

            if special_parent:
                parent_path = special_parent
                print(f"  [Special Material] Matched '{sanitized_name}' -> Parent: {parent_path}")
            elif not parent_path or not parent_path.startswith("/Game/"):
                parent_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterBodyBase"
                parent_class_lower = parent_path.lower()
                mat_name_lower = sanitized_name.lower()
                if "eye" in parent_class_lower or "mouth" in parent_class_lower or "eye" in mat_name_lower or "mouth" in mat_name_lower:
                    parent_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterEyeBase"
                elif "hair" in parent_class_lower or "hair" in mat_name_lower:
                    parent_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterHairBase"
                
            parent_mat = unreal.EditorAssetLibrary.load_asset(parent_path)
            if parent_mat:
                unreal.MaterialEditingLibrary.set_material_instance_parent(mi_asset, parent_mat)

            # --- 2. APPLY SUBSURFACE PROFILE ---
            sp_path = baseline_cfg.get("subsurface_profile")
            if sp_path:
                sp_asset = unreal.EditorAssetLibrary.load_asset(sp_path)
                if sp_asset:
                    try:
                        mi_asset.set_editor_property("subsurface_profile", sp_asset)
                        print(f"  [Baseline] Linked SubsurfaceProfile: {sp_asset.get_name()}")
                    except Exception as e:
                        print(f"  Warning setting SubsurfaceProfile: {e}")

            # --- 3. APPLY BASE PROPERTY OVERRIDES ---
            bpo = baseline_cfg.get("base_property_overrides", {})
            if bpo:
                try:
                    overrides = mi_asset.get_editor_property("base_property_overrides")
                    if bpo.get("bOverride_ShadingModel") or "ShadingModel" in bpo:
                        overrides.set_editor_property("override_shading_model", True)
                        sm_str = str(bpo.get("ShadingModel", ""))
                        if "Subsurface" in sm_str:
                            overrides.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SUBSURFACE)
                        elif "DefaultLit" in sm_str:
                            overrides.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
                        elif "Unlit" in sm_str:
                            overrides.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
                        elif "ClearCoat" in sm_str:
                            overrides.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_CLEAR_COAT)
                            
                    if bpo.get("bOverride_BlendMode") or "BlendMode" in bpo:
                        overrides.set_editor_property("override_blend_mode", True)
                        bm_str = str(bpo.get("BlendMode", ""))
                        if "Masked" in bm_str:
                            overrides.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
                        elif "Translucent" in bm_str:
                            overrides.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
                        elif "Opaque" in bm_str:
                            overrides.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
                        elif "Additive" in bm_str:
                            overrides.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
                            
                    if bpo.get("bOverride_TwoSided") or "TwoSided" in bpo:
                        overrides.set_editor_property("override_two_sided", True)
                        overrides.set_editor_property("two_sided", bool(bpo.get("TwoSided", True)))
                        
                    if bpo.get("bOverride_OpacityMaskClipValue") or "OpacityMaskClipValue" in bpo:
                        overrides.set_editor_property("override_opacity_mask_clip_value", True)
                        overrides.set_editor_property("opacity_mask_clip_value", float(bpo.get("OpacityMaskClipValue", 0.3333)))
                        
                    mi_asset.set_editor_property("base_property_overrides", overrides)
                except Exception as e:
                    print(f"  Warning setting BasePropertyOverrides: {e}")

            # --- 4. APPLY SCALAR PARAMETERS ---
            for s_name, s_val in baseline_cfg.get("scalars", {}).items():
                try:
                    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                        mi_asset, unreal.Name(s_name), float(s_val)
                    )
                except Exception: pass

            # --- 5. APPLY VECTOR PARAMETERS ---
            for v_name, v_val in baseline_cfg.get("vectors", {}).items():
                try:
                    linear_col = unreal.LinearColor(
                        float(v_val.get("R", 0.0)),
                        float(v_val.get("G", 0.0)),
                        float(v_val.get("B", 0.0)),
                        float(v_val.get("A", 1.0))
                    )
                    unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
                        mi_asset, unreal.Name(v_name), linear_col
                    )
                except Exception: pass

            # --- 6. APPLY RESOLVED TEXTURES (BASELINE + BLENDER OVERRIDES) ---
            for param_name, tex_name in active_textures.items():
                clean_tex = tex_name.split(".")[0]
                known_path = active_paths.get(param_name)
                
                loaded_tex = None
                if known_path and unreal.EditorAssetLibrary.does_asset_exist(known_path):
                    loaded_tex = unreal.EditorAssetLibrary.load_asset(known_path)
                
                if not loaded_tex:
                    loaded_tex = (
                        unreal.EditorAssetLibrary.load_asset(f"{ue_path}/{clean_tex}") or
                        (unreal.EditorAssetLibrary.load_asset(f"{parent_ue_dir}/{clean_tex}") if parent_ue_dir else None) or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Material/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Material/Character/Common/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Texture/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Texture/PalIcon/Normal/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Texture/ModelCommon/FacialMask/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Effect/Textures/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Pal/Effect/Common/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Game/Mods/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Engine/EngineResources/{clean_tex}") or
                        unreal.EditorAssetLibrary.load_asset(f"/Engine/EngineMaterials/{clean_tex}")
                    )
                    
                if loaded_tex and isinstance(loaded_tex, unreal.Texture):
                    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
                        mi_asset, unreal.Name(param_name), loaded_tex
                    )
                    print(f"  Bound {param_name}: {loaded_tex.get_name()}")
                    
            unreal.EditorAssetLibrary.save_loaded_asset(mi_asset)
            mi_assets.append((sanitized_name.lower(), mi_asset))
            
        return mi_assets
    else:
        return build_materials_heuristically(ue_path, textures, material_slots, preserve_materials)

def bind_materials_to_mesh(target_asset_path, target_phys_path, mi_assets, harvested_materials=None):
    if not target_asset_path:
        return
        
    mesh = unreal.EditorAssetLibrary.load_asset(target_asset_path)
    if not mesh:
        return

    asset_class = mesh.get_class().get_name()
    if asset_class != "SkeletalMesh":
        return

    print("Linking Materials and Physics Asset...")

    saved_phys = unreal.EditorAssetLibrary.load_asset(target_phys_path)
    if saved_phys:
        try:
            mesh.set_editor_property('physics_asset', saved_phys)
        except Exception:
            pass
    
    skel_materials = mesh.materials
    print(f"Skeletal mesh has {len(skel_materials)} material slots.")
    
    new_materials = []
    for i, skel_mat in enumerate(skel_materials):
        slot_name = str(skel_mat.material_slot_name).lower()
        print(f"Processing slot: {slot_name}")
        
        if harvested_materials:
            preserved_mat = harvested_materials.get(slot_name) or harvested_materials.get(str(i))
            if preserved_mat:
                skel_mat.material_interface = preserved_mat
                print(f"  [Safeguard] Preserved existing custom material -> {preserved_mat.get_name()}")
                new_materials.append(skel_mat)
                continue

        matched_mi = next((mi_asset for mi_name, mi_asset in mi_assets if mi_name == slot_name), None)
            
        if not matched_mi:
            for mi_name, mi_asset in mi_assets:
                if ("body" in mi_name and "body" in slot_name) or \
                   ("eye" in mi_name and "eye" in slot_name) or \
                   ("mouth" in mi_name and "mouth" in slot_name) or \
                   ("hair" in mi_name and "hair" in slot_name):
                    matched_mi = mi_asset
                    break
                    
        if matched_mi:
            skel_mat.material_interface = matched_mi
            print(f"  Linked slot {slot_name} -> {matched_mi.get_name()}")
        else:
            special_parent = resolve_special_parent_material(slot_name)
            if special_parent:
                fallback_path = special_parent
            elif "eye" in slot_name or "mouth" in slot_name:
                fallback_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterEyeBase"
            elif "hair" in slot_name:
                fallback_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterHairBase"
            else:
                fallback_path = "/Game/Pal/Material/Character/Common/MI_PalLit_CharacterBodyBase"
                
            fallback_mat = unreal.EditorAssetLibrary.load_asset(fallback_path)
            if fallback_mat:
                skel_mat.material_interface = fallback_mat
                print(f"  [Safeguard] Linked empty slot {slot_name} to Master: {fallback_mat.get_name()}")
                
        new_materials.append(skel_mat)
    
    mesh.materials = new_materials
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)