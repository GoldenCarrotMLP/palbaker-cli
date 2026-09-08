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

def clear_cache(ue_path, fbx_file, target_mesh_name, is_custom_pal=False):
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

        if is_custom_pal:
            rogue_skeleton = f"/Game/Pal/Model/Character/Skeleton/{target_mesh_name}/SK_{target_mesh_name}_Skeleton"
            if unreal.EditorAssetLibrary.does_asset_exist(rogue_skeleton):
                print(f"[PalBaker] Clearing rogue custom skeleton: {rogue_skeleton}")
                try: unreal.EditorAssetLibrary.delete_asset(rogue_skeleton)
                except Exception: pass

def import_assets(ue_path, textures, fbx_file, target_mesh_name, base_pal, template_id=None, is_custom_pal=False, import_tex=True):
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
                # Sanitize spaces to prevent invalid asset path errors
                tex_name = tex_name.replace(" ", "_")
                    
                tex_asset_path = f"{ue_path}/{tex_name}"

                # Silently delete existing asset to prevent memory locking
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
        
        parts = ue_path.replace("\\", "/").split("/")
        category = "Monster"
        if "Character" in parts:
            idx = parts.index("Character")
            if idx + 1 < len(parts):
                category = parts[idx + 1]

        base_ue_path = f"/Game/Pal/Model/Character/{category}/{base_pal}"
        shared_phys_path = f"{base_ue_path}/PA_{base_pal}_PhysicsAsset"
        
        phys_exists = unreal.EditorAssetLibrary.does_asset_exist(shared_phys_path)

        clean_mesh_name = target_mesh_name.replace("SK_", "")
        candidate_phys_paths = [
            f"{ue_path}/{target_mesh_name}_PhysicsAsset",
            f"{ue_path}/PA_{clean_mesh_name}_PhysicsAsset",
            f"{ue_path}/PA_{target_mesh_name}_PhysicsAsset",
            f"{ue_path}/{clean_mesh_name}_PhysicsAsset"
        ]

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
        
        if phys_exists:
            print(f"[PalBaker] Centralized physics asset detected at {shared_phys_path}. Skipping automatic compilation and binding mesh to it.")
            import_ui.set_editor_property('create_physics_asset', False)
        else:
            print(f"[PalBaker] Centralized physics asset missing. Enabling automatic compilation to generate base asset...")
            import_ui.set_editor_property('create_physics_asset', True)
        
        skel_data = import_ui.skeletal_mesh_import_data
        skel_data.set_editor_property('import_mesh_lo_ds', False)
        skel_data.set_editor_property('import_morph_targets', True)
        skel_data.set_editor_property('use_t0_as_ref_pose', True)
        # Preserve Blender custom split/weighted normals instead of recomputing
        skel_data.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        
        target_skeleton_name = template_id if (is_custom_pal and template_id) else base_pal
        skeleton_path = f"/Game/Pal/Model/Character/Skeleton/{target_skeleton_name}/SK_{target_skeleton_name}_Skeleton"
        
        existing_skeleton = unreal.EditorAssetLibrary.load_asset(skeleton_path)
        if existing_skeleton:
            print(f"[PalBaker] Existing skeleton found at {skeleton_path}. Merging and updating bone container...")
            import_ui.set_editor_property('skeleton', existing_skeleton)
        else:
            print(f"[PalBaker] No existing skeleton found at {skeleton_path}. Unreal will generate a new skeleton.")

        task.set_editor_property('options', import_ui)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        
        imported_asset = unreal.EditorAssetLibrary.load_asset(target_asset_path)
        if imported_asset:
            asset_class = imported_asset.get_class().get_name()
            if asset_class == "StaticMesh":
                raise Exception(
                    f"\n[!] FATAL ERROR: Unreal Engine imported '{fbx_filename}' as a StaticMesh instead of a SkeletalMesh!\n"
                    f"Please open your .blend file, ensure your mesh is parented to the 'Armature' object, and try again."
                )

        print(f"[PalBaker] Successfully imported skeletal mesh to: {target_asset_path}")

        expected_skeleton_path = skeleton_path
        skeleton_relocated = False

        imported_paths = list(task.get_editor_property('imported_object_paths'))
        for imported_path in imported_paths:
            asset = unreal.EditorAssetLibrary.load_asset(imported_path)
            if not asset: continue
            
            asset_class = asset.get_class().get_name()
            if asset_class == "Skeleton":
                if imported_path != expected_skeleton_path:
                    unreal.EditorAssetLibrary.make_directory(f"/Game/Pal/Model/Character/Skeleton/{target_skeleton_name}")
                    unreal.EditorAssetLibrary.rename_asset(imported_path, expected_skeleton_path)
                skeleton_relocated = True

        if not skeleton_relocated:
            generated_skeleton_path = f"{ue_path}/{target_mesh_name}_Skeleton"
            if unreal.EditorAssetLibrary.does_asset_exist(generated_skeleton_path) and generated_skeleton_path != expected_skeleton_path:
                unreal.EditorAssetLibrary.make_directory(f"/Game/Pal/Model/Character/Skeleton/{target_skeleton_name}")
                unreal.EditorAssetLibrary.rename_asset(generated_skeleton_path, expected_skeleton_path)

        if not phys_exists:
            found_generated = False
            for cand in candidate_phys_paths:
                if unreal.EditorAssetLibrary.does_asset_exist(cand):
                    print(f"[PalBaker] Discovered auto-generated physics asset at: '{cand}'. Relocating to base folder shared path: '{shared_phys_path}'")
                    unreal.EditorAssetLibrary.make_directory(base_ue_path)
                    if unreal.EditorAssetLibrary.rename_asset(cand, shared_phys_path):
                        print("[PalBaker] Centralization successfully completed!")
                        found_generated = True
                        break
            if not found_generated:
                print("[PalBaker Warning] Physics asset generation was enabled, but no candidate auto-generated files could be mapped.")

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