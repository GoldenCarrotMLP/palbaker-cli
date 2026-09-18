import unreal  # type: ignore
import os

def harvest_materials(ue_path, target_mesh_name):
    harvested = {}
    path = f"{ue_path}/{target_mesh_name}"
    
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        if mesh and mesh.get_class().get_name() == "SkeletalMesh":
            print(f"[PalBaker] Harvesting existing custom materials from {path}...")
            for i, mat in enumerate(mesh.materials):
                slot_name = str(mat.material_slot_name).lower()
                if mat.material_interface:
                    harvested[slot_name] = mat.material_interface
                    harvested[str(i)] = mat.material_interface
    return harvested

def clear_cache(ue_path, fbx_file, target_mesh_name, is_custom_pal=False, has_custom_anims=False, base_pal="", mod_name="", category="Monster"):
    if fbx_file and os.path.exists(fbx_file):
        clean_mesh_name = target_mesh_name.replace("SK_", "")
        paths_to_delete = [
            f"{ue_path}/PA_{target_mesh_name}_PhysicsAsset",
            f"{ue_path}/PA_{clean_mesh_name}_PhysicsAsset",
            f"{ue_path}/{target_mesh_name}_PhysicsAsset"
        ]
        
        for path in paths_to_delete:
            if unreal.EditorAssetLibrary.does_asset_exist(path):
                print(f"[PalBaker] Clearing old physics asset from cache to prevent ghost collisions: {path}")
                try: unreal.EditorAssetLibrary.delete_asset(path)
                except Exception as e: print(f"[PalBaker] Warning: Failed to delete physics asset: {e}")

        # Only clear rogue custom skeleton if custom animations are NOT active!
        if is_custom_pal and not has_custom_anims:
            rogue_skeleton = f"/Game/Pal/Model/Character/Skeleton/{target_mesh_name}/SK_{target_mesh_name}_Skeleton"
            if unreal.EditorAssetLibrary.does_asset_exist(rogue_skeleton):
                print(f"[PalBaker] Custom anims inactive: Clearing rogue custom skeleton: {rogue_skeleton}")
                try: unreal.EditorAssetLibrary.delete_asset(rogue_skeleton)
                except Exception: pass

        # If custom animations are disabled, strictly scrub out orphaned variant skeletons and animation BPs!
        if not has_custom_anims and base_pal and mod_name and base_pal.lower() != mod_name.lower():
            cat_sanitized = category.replace(" ", "_")
            folders_to_scrub = [
                f"/Game/Pal/Model/Character/Skeleton/{base_pal}/{mod_name}",
                f"/Game/Pal/Animation/Character/{cat_sanitized}/{base_pal}/{mod_name}",
                f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}/{mod_name}"
            ]
            for folder in folders_to_scrub:
                if unreal.EditorAssetLibrary.does_directory_exist(folder):
                    print(f"[PalBaker] Custom anims inactive: Cleaning up orphaned folder {folder}...")
                    try: unreal.EditorAssetLibrary.delete_directory(folder)
                    except Exception as e: print(f"[PalBaker] Warning: Failed to delete {folder}: {e}")

def import_assets(ue_path, textures, fbx_file, target_mesh_name, base_pal, template_id=None, is_custom_pal=False, import_tex=True, has_custom_anims=False):
    # 1. Textures Import (Forced Overwrite)
    if import_tex and textures:
        print(f"[PalBaker] Importing {len(textures)} textures with forced overwrite...", flush=True)
        import_tasks = []
        for png in textures:
            if os.path.exists(png):
                clean_png = os.path.normpath(png).replace("\\", "/")
                tex_name = os.path.basename(clean_png)
                while "." in tex_name:
                    tex_name = os.path.splitext(tex_name)[0]
                tex_name = tex_name.replace(" ", "_")
                tex_asset_path = f"{ue_path}/{tex_name}"

                try:
                    loaded = unreal.EditorAssetLibrary.load_asset(tex_asset_path)
                    if loaded:
                        unreal.EditorAssetLibrary.delete_asset(tex_asset_path)
                except Exception:
                    pass

                task = unreal.AssetImportTask()
                task.set_editor_property('filename', clean_png)
                task.set_editor_property('destination_path', ue_path)
                task.set_editor_property('destination_name', tex_name)
                task.set_editor_property('replace_existing', True)
                task.set_editor_property('replace_existing_settings', True)
                task.set_editor_property('automated', True)
                task.set_editor_property('save', True)
                task.set_editor_property('factory', unreal.TextureFactory())
                import_tasks.append(task)
                
        if import_tasks:
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(import_tasks)
            print(f"[PalBaker] Texture buffer processing complete.", flush=True)

    # 2. Skeletal Mesh FBX Import
    target_asset_path = ""
    target_phys_path = ""
    
    if fbx_file and os.path.exists(fbx_file):
        fbx_filename = os.path.basename(fbx_file)
        print(f"[PalBaker] Importing Skeletal FBX: {fbx_filename}")
        
        target_asset_path = f"{ue_path}/{target_mesh_name}"
        clean_mesh_name = target_mesh_name.replace("SK_", "")
        
        parts = ue_path.replace("\\", "/").split("/")
        category = "Monster"
        if "Character" in parts:
            idx = parts.index("Character")
            if idx + 1 < len(parts):
                category = parts[idx + 1]

        base_ue_path = f"/Game/Pal/Model/Character/{category}/{base_pal}"
        shared_phys_path = f"{base_ue_path}/PA_{base_pal}_PhysicsAsset"
        phys_exists = unreal.EditorAssetLibrary.does_asset_exist(shared_phys_path)

        if phys_exists:
            print(f"[PalBaker] Using shared parent PhysicsAsset: {shared_phys_path}")
        else:
            print(f"[PalBaker] No parent PhysicsAsset found. Will generate and move to: {shared_phys_path}")

        task = unreal.AssetImportTask()
        task.set_editor_property('filename', fbx_file.replace("\\", "/"))
        task.set_editor_property('destination_path', ue_path)
        task.set_editor_property('destination_name', target_mesh_name)
        task.set_editor_property('replace_existing', True)
        task.set_editor_property('automated', True)
        task.set_editor_property('save', True)
        
        import_ui = unreal.FbxImportUI()
        import_ui.set_editor_property('import_mesh', True)
        import_ui.set_editor_property('import_as_skeletal', True)
        import_ui.set_editor_property('import_materials', False)
        import_ui.set_editor_property('import_textures', False)
        import_ui.set_editor_property('import_animations', False)
        import_ui.set_editor_property('create_physics_asset', not phys_exists)
        
        skel_data = import_ui.skeletal_mesh_import_data
        skel_data.set_editor_property('import_mesh_lo_ds', False)
        skel_data.set_editor_property('import_morph_targets', True)
        skel_data.set_editor_property('use_t0_as_ref_pose', True)
        skel_data.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        
        # Skeleton routing: nest variant skeleton inside base pal folder
        skel_folder = f"{base_pal}/{clean_mesh_name}" if (has_custom_anims and base_pal.lower() != clean_mesh_name.lower()) else base_pal
        if has_custom_anims:
            expected_skeleton_path = f"/Game/Pal/Model/Character/Skeleton/{skel_folder}/SK_{clean_mesh_name}_Skeleton"
            print(f"[PalBaker] Custom Animations Active: Targeting dedicated nested skeleton at {expected_skeleton_path}")
            existing_skeleton = unreal.EditorAssetLibrary.load_asset(expected_skeleton_path)
            if existing_skeleton:
                import_ui.set_editor_property('skeleton', existing_skeleton)
            else:
                import_ui.set_editor_property('skeleton', None)
        else:
            target_skeleton_name = template_id if (is_custom_pal and template_id) else base_pal
            clean_skel_name = target_skeleton_name[3:] if target_skeleton_name.startswith("SK_") else target_skeleton_name
            expected_skeleton_path = f"/Game/Pal/Model/Character/Skeleton/{clean_skel_name}/SK_{clean_skel_name}_Skeleton"
            existing_skeleton = unreal.EditorAssetLibrary.load_asset(expected_skeleton_path)
            if existing_skeleton:
                import_ui.set_editor_property('skeleton', existing_skeleton)

        task.set_editor_property('options', import_ui)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        
        imported_paths = list(task.get_editor_property('imported_object_paths'))

        # 1. PhysicsAsset Relocation & Deduplication
        for imp_path in imported_paths:
            asset = unreal.EditorAssetLibrary.load_asset(imp_path)
            if not asset: continue
            if asset.get_class().get_name() == "PhysicsAsset":
                if phys_exists:
                    # Parent already has a shared PhysicsAsset; delete the local duplicate from the variant folder
                    print(f"[PalBaker] Removing redundant duplicate PhysicsAsset from variant folder: {imp_path}")
                    unreal.EditorAssetLibrary.delete_asset(imp_path)
                else:
                    # Move & rename the generated PhysicsAsset to the parent root directory
                    unreal.EditorAssetLibrary.make_directory(base_ue_path)
                    if imp_path != shared_phys_path:
                        print(f"[PalBaker] Relocating generated PhysicsAsset to root parent: {shared_phys_path}")
                        unreal.EditorAssetLibrary.rename_asset(imp_path, shared_phys_path)
                    phys_exists = True

        # Fallback check if Unreal named the physics asset outside imported_object_paths
        if not phys_exists:
            for cand in [
                f"{ue_path}/{target_mesh_name}_PhysicsAsset",
                f"{ue_path}/{clean_mesh_name}_PhysicsAsset",
                f"{ue_path}/PA_{target_mesh_name}_PhysicsAsset",
                f"{ue_path}/PA_{clean_mesh_name}_PhysicsAsset"
            ]:
                if unreal.EditorAssetLibrary.does_asset_exist(cand):
                    unreal.EditorAssetLibrary.make_directory(base_ue_path)
                    print(f"[PalBaker] Relocating fallback PhysicsAsset to root parent: {shared_phys_path}")
                    unreal.EditorAssetLibrary.rename_asset(cand, shared_phys_path)
                    phys_exists = True
                    break

        # 2. Skeleton routing
        skeleton_relocated = False
        for imported_path in imported_paths:
            asset = unreal.EditorAssetLibrary.load_asset(imported_path)
            if not asset: continue
            if asset.get_class().get_name() == "Skeleton":
                if imported_path != expected_skeleton_path:
                    unreal.EditorAssetLibrary.make_directory(f"/Game/Pal/Model/Character/Skeleton/{skel_folder}")
                    unreal.EditorAssetLibrary.rename_asset(imported_path, expected_skeleton_path)
                skeleton_relocated = True

        if not skeleton_relocated:
            generated_skeleton_path = f"{ue_path}/{target_mesh_name}_Skeleton"
            if unreal.EditorAssetLibrary.does_asset_exist(generated_skeleton_path) and generated_skeleton_path != expected_skeleton_path:
                unreal.EditorAssetLibrary.make_directory(f"/Game/Pal/Model/Character/Skeleton/{skel_folder}")
                unreal.EditorAssetLibrary.rename_asset(generated_skeleton_path, expected_skeleton_path)

        return target_asset_path, shared_phys_path

def import_icon(icon_file, destination_path):
    if icon_file and os.path.exists(icon_file):
        clean_icon = os.path.normpath(icon_file).replace("\\", "/")
        icon_name = os.path.basename(clean_icon)
        while "." in icon_name:
            icon_name = os.path.splitext(icon_name)[0]
            
        icon_asset_path = f"{destination_path}/{icon_name}"

        try:
            loaded = unreal.EditorAssetLibrary.load_asset(icon_asset_path)
            if loaded:
                print(f"[PalBaker] Clearing old UI icon to force replace: {icon_asset_path}")
                unreal.EditorAssetLibrary.delete_asset(icon_asset_path)
        except Exception:
            pass

        print(f"[PalBaker] Importing UI Icon: {os.path.basename(icon_file)} -> {destination_path}")
        task = unreal.AssetImportTask()
        task.set_editor_property('filename', clean_icon)
        task.set_editor_property('destination_path', destination_path)
        task.set_editor_property('destination_name', icon_name)
        task.set_editor_property('replace_existing', True)
        task.set_editor_property('replace_existing_settings', True)
        task.set_editor_property('automated', True)
        task.set_editor_property('save', True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])