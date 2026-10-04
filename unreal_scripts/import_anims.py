# unreal_scripts/import_anims.py
import unreal  # type: ignore
import os
import json
import tempfile
import warnings

# Suppress all RuntimeWarning and AssetTools noise from flooding the remote execution socket
warnings.filterwarnings("ignore")

def run_animation_import():
    temp_dir = tempfile.gettempdir()
    cfg_path = os.path.join(temp_dir, "palbaker_anim_import_config.json")

    if not os.path.exists(cfg_path):
        print(f"[PalBaker Anims] Config missing at: {cfg_path}", flush=True)
        return

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    anims_dir = cfg["anims_dir"].replace("\\", "/")
    mod_name = cfg["mod_name"]
    base_pal = cfg.get("base_pal", mod_name)
    template_id = cfg.get("template_id", base_pal)
    is_custom_pal = cfg.get("is_custom_pal", False)
    category = cfg.get("category", "Monster")
    
    # 1. Harvest target root motion sequences
    root_motion_sequences = set(s.lower() for s in cfg.get("root_motion_sequences", []))
    sidecar_path = cfg.get("sidecar_path", "")
    if sidecar_path and os.path.exists(sidecar_path):
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f_sc:
                sc_data = json.load(f_sc)
            for k, v in sc_data.get("custom_animations", {}).get("anims", {}).items():
                if isinstance(v, dict) and v.get("enable_root_motion"):
                    root_motion_sequences.add(k.lower())
                    seq = v.get("sequence_asset")
                    if seq:
                        root_motion_sequences.add(seq.lower())
                    track = v.get("nla_track_name")
                    if track:
                        root_motion_sequences.add(track.lower())
                        root_motion_sequences.add(f"as_{mod_name.lower()}_{track.lower()}")
                        root_motion_sequences.add(f"as_{base_pal.lower()}_{track.lower()}")
        except Exception:
            pass

    is_variant = (not is_custom_pal and base_pal.lower() != mod_name.lower())
    if is_variant:
        destination_path = f"/Game/Pal/Animation/Character/{category}/{base_pal}/{mod_name}"
    else:
        destination_path = f"/Game/Pal/Animation/Character/{category}/{mod_name}"

    if not os.path.exists(anims_dir):
        print(f"[PalBaker Anims] Error: Animation staging directory not found: {anims_dir}", flush=True)
        return

    # Locate Skeleton
    skel_candidates = [
        f"/Game/Pal/Model/Character/Skeleton/{base_pal}/{mod_name}/SK_{mod_name}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{mod_name}/SK_{mod_name}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{base_pal}/SK_{mod_name}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton",
        f"/Game/Pal/Model/Character/Skeleton/{base_pal}/SK_{base_pal}_Skeleton"
    ]
    
    skel_asset = None
    for cand in skel_candidates:
        if unreal.EditorAssetLibrary.does_asset_exist(cand):
            skel_asset = unreal.EditorAssetLibrary.load_asset(cand)
            print(f"[PalBaker Anims] Bound Skeleton for Animation Import: {cand}", flush=True)
            break

    if not skel_asset:
        print(f"[PalBaker Anims Error] Target skeleton not found for {mod_name}. You must push the skeletal mesh first!", flush=True)
        return

    unreal.EditorAssetLibrary.make_directory(destination_path)

    # 2. Gather all individual animation FBX files
    fbx_files = [os.path.join(anims_dir, f).replace("\\", "/") for f in os.listdir(anims_dir) if f.endswith(".fbx")]
    print(f"[PalBaker Anims] Ingesting {len(fbx_files)} individual animation files into {destination_path}...", flush=True)

    import_tasks = []
    for fbx_file in fbx_files:
        asset_name = os.path.splitext(os.path.basename(fbx_file))[0]

        task = unreal.AssetImportTask()
        task.set_editor_property('filename', fbx_file)
        task.set_editor_property('destination_path', destination_path)
        task.set_editor_property('destination_name', asset_name)
        task.set_editor_property('replace_existing', True)
        task.set_editor_property('replace_existing_settings', True)
        task.set_editor_property('automated', True)
        task.set_editor_property('save', True)

        import_ui = unreal.FbxImportUI()
        import_ui.set_editor_property('automated_import_should_detect_type', False)
        import_ui.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_ANIMATION)
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
        import_tasks.append(task)

    # Execute import with warnings strictly suppressed to prevent buffer overflow
    if import_tasks:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(import_tasks)
        print(f"[PalBaker Anims] AssetTools successfully imported {len(import_tasks)} AnimSequences.", flush=True)

    # 3. Post-Import: Enable Root Motion on marked sequences
    root_motion_applied_count = 0
    applied_names = []
    for fbx_file in fbx_files:
        asset_name = os.path.splitext(os.path.basename(fbx_file))[0]
        clean_track = asset_name
        for pfx in [f"AS_{mod_name}_", f"AS_{base_pal}_", "AS_"]:
            if clean_track.startswith(pfx):
                clean_track = clean_track[len(pfx):]
                break

        is_root_motion = (
            asset_name.lower() in root_motion_sequences or
            clean_track.lower() in root_motion_sequences or
            f"as_{mod_name.lower()}_{clean_track.lower()}" in root_motion_sequences or
            f"as_{base_pal.lower()}_{clean_track.lower()}" in root_motion_sequences
        )

        if is_root_motion:
            asset_path = f"{destination_path}/{asset_name}"
            if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
                anim_seq = unreal.EditorAssetLibrary.load_asset(asset_path)
                if anim_seq:
                    applied = False
                    for prop_name in ["enable_root_motion", "b_enable_root_motion", "bEnableRootMotion"]:
                        try:
                            anim_seq.set_editor_property(prop_name, True)
                            applied = True
                            break
                        except Exception:
                            pass
                    if applied:
                        root_motion_applied_count += 1
                        applied_names.append(asset_name)

    if root_motion_applied_count > 0:
        print(f"[PalBaker Anims] Enabled Root Motion on {root_motion_applied_count} sequence(s): {', '.join(applied_names)}", flush=True)

    # Force synchronous scan and save dirty packages
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    ar.scan_paths_synchronous([destination_path], True)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(save_map_packages=False, save_content_packages=True)
    print(f"[PalBaker Anims] All AnimSequences successfully imported and saved to disk!", flush=True)

run_animation_import()