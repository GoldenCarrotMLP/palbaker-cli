# unreal_scripts/import_anims.py
import unreal  # type: ignore
import os
import json
import tempfile

def clean_to_track_name(asset_name: str, base_pal: str, mod_name: str, template_id: str = "") -> str:
    """Aggressively strips all engine, FBX, armature, Pal, and template prefixes."""
    clean = asset_name
    prefixes = [
        f"{mod_name}_Anims_Armature_{base_pal}_",
        f"{mod_name}_Anims_Armature_{mod_name}_",
        f"{mod_name}_Anims_Armature_",
        f"{mod_name}_Armature_{base_pal}_",
        f"{mod_name}_Armature_{mod_name}_",
        f"{mod_name}_Armature_",
        f"{base_pal}_Anims_Armature_{base_pal}_",
        f"{base_pal}_Anims_Armature_",
        f"{base_pal}_Armature_{base_pal}_",
        f"{base_pal}_Armature_",
        f"{mod_name}_Anims_",
        f"{base_pal}_Anims_",
        f"AS_{mod_name}_{base_pal}_",
        f"AM_{mod_name}_{base_pal}_",
        f"AS_{mod_name}_",
        f"AM_{mod_name}_",
        f"AS_{base_pal}_",
        f"AM_{base_pal}_",
        "Armature_",
        "Anim_Armature_",
        f"{mod_name}_",
        f"{base_pal}_",
        "AM_",
        "AS_"
    ]
    if template_id and template_id.lower() not in [base_pal.lower(), mod_name.lower()]:
        prefixes.extend([
            f"{mod_name}_Anims_Armature_{template_id}_",
            f"{mod_name}_Armature_{template_id}_",
            f"{template_id}_Anims_Armature_{template_id}_",
            f"{template_id}_Anims_Armature_",
            f"{template_id}_Armature_{template_id}_",
            f"{template_id}_Armature_",
            f"AS_{mod_name}_{template_id}_",
            f"AM_{mod_name}_{template_id}_",
            f"AS_{template_id}_",
            f"AM_{template_id}_",
            f"{template_id}_Anims_",
            f"{template_id}_"
        ])
    prefixes = sorted(list(set(prefixes)), key=len, reverse=True)

    # Strip any stacked or doubled prefixes in a loop until clean
    changed = True
    while changed:
        changed = False
        for pfx in prefixes:
            if clean.lower().startswith(pfx.lower()):
                clean = clean[len(pfx):]
                changed = True
                break
    
    return clean

def run_animation_import():
    temp_dir = tempfile.gettempdir()
    cfg_path = os.path.join(temp_dir, "palbaker_anim_import_config.json")

    if not os.path.exists(cfg_path):
        print(f"[PalBaker Anims] Config missing at: {cfg_path}")
        return

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    fbx_file = cfg["fbx_file"].replace("\\", "/")
    mod_name = cfg["mod_name"]
    base_pal = cfg.get("base_pal", mod_name)
    template_id = cfg.get("template_id", base_pal)
    is_custom_pal = cfg.get("is_custom_pal", False)
    category = cfg.get("category", "Monster")
    
    # Standalone Custom Pals stay in their own folder. Only true variants nest inside base_pal.
    is_variant = (not is_custom_pal and base_pal.lower() != mod_name.lower())
    if is_variant:
        destination_path = f"/Game/Pal/Animation/Character/{category}/{base_pal}/{mod_name}"
    else:
        destination_path = f"/Game/Pal/Animation/Character/{category}/{mod_name}"

    if not os.path.exists(fbx_file):
        print(f"[PalBaker Anims] FBX file not found: {fbx_file}")
        return

    # Locate Custom Skeleton
    skel_candidates = [
        f"/Game/Pal/Model/Character/Skeleton/{mod_name}/SK_{mod_name}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{base_pal}/{mod_name}/SK_{mod_name}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{base_pal}/SK_{mod_name}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{base_pal}/SK_{base_pal}_Skeleton"
    ]
    
    skel_asset = None
    for cand in skel_candidates:
        if unreal.EditorAssetLibrary.does_asset_exist(cand):
            skel_asset = unreal.EditorAssetLibrary.load_asset(cand)
            break

    if not skel_asset:
        print(f"[PalBaker Anims Error] Custom skeleton not found for {mod_name}. Push model mesh first!")
        return

    unreal.EditorAssetLibrary.make_directory(destination_path)

    # 1. Ingest animation takes
    print(f"[PalBaker Anims] Ingesting FBX Animation Takes: {os.path.basename(fbx_file)} -> {destination_path}...")
    task = unreal.AssetImportTask()
    task.set_editor_property('filename', fbx_file)
    task.set_editor_property('destination_path', destination_path)
    task.set_editor_property('replace_existing', True)
    task.set_editor_property('automated', True)
    task.set_editor_property('save', True)

    import_ui = unreal.FbxImportUI()
    import_ui.set_editor_property('import_mesh', False)
    import_ui.set_editor_property('import_as_skeletal', True)
    import_ui.set_editor_property('import_materials', False)
    import_ui.set_editor_property('import_textures', False)
    import_ui.set_editor_property('import_animations', True)
    import_ui.set_editor_property('skeleton', skel_asset)

    anim_data = import_ui.anim_sequence_import_data
    anim_data.set_editor_property('import_custom_attribute', True)
    anim_data.set_editor_property('snap_to_closest_frame_boundary', True)
    anim_data.set_editor_property('animation_length', unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)

    task.set_editor_property('options', import_ui)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    # 2. Aggressive Folder Scan to Standardize Names & Clean Junk
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = ar.get_assets_by_path(destination_path, recursive=False)
    
    standardized_count = 0
    seen_target_paths = set()

    for a in assets:
        asset_class = str(a.asset_class_path.asset_name)
        imp_path = str(a.package_name)

        # Delete stray meshes or physics assets generated by the FBX importer
        if asset_class in ["SkeletalMesh", "StaticMesh", "PhysicsAsset", "Skeleton"]:
            unreal.EditorAssetLibrary.delete_asset(imp_path)
            continue

        if asset_class == "AnimSequence":
            raw_name = str(a.asset_name)
            clean_track = clean_to_track_name(raw_name, base_pal, mod_name, template_id)
            
            target_name = f"AS_{mod_name}_{clean_track}"
            target_path = f"{destination_path}/{target_name}"

            # Deduplicate multiple takes resolving to the same name
            if target_path in seen_target_paths:
                if imp_path != target_path:
                    unreal.EditorAssetLibrary.delete_asset(imp_path)
                continue

            seen_target_paths.add(target_path)

            if imp_path != target_path:
                if unreal.EditorAssetLibrary.does_asset_exist(target_path):
                    unreal.EditorAssetLibrary.delete_asset(target_path)
                unreal.EditorAssetLibrary.rename_asset(imp_path, target_path)
                print(f"  ✓ Standardized: {target_name}")
                standardized_count += 1
            else:
                standardized_count += 1

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(save_map_packages=False, save_content_packages=True)
    print(f"[PalBaker Anims] Standardized {standardized_count} AnimSequences in {destination_path}!")

run_animation_import()