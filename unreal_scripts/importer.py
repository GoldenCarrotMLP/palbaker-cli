import unreal  # type: ignore
import os

def _safe_float(val, default=0.0):
    if val is None or val == "" or val == "+0" or val == "-0":
        return float(default)
    try:
        return float(val)
    except (ValueError, TypeError):
        return float(default)

def _extract_struct_value(prop):
    if not prop or not isinstance(prop, dict):
        return {}
    val = prop.get("Value")
    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
        inner = val[0].get("Value")
        if isinstance(inner, dict):
            return inner
    elif isinstance(val, dict):
        return val
    return {}

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

def inject_vanilla_skeleton_metadata(palbaker_root, custom_skel_path, template_id, sidecar_path=""):
    """Extracts vanilla skeleton JSON offline, parses Sockets/VBs/Slots, and injects them natively into Unreal."""
    import os
    import json
    import tempfile
    import shutil
    import sys
    import unreal # type: ignore

    settings_path = os.path.join(palbaker_root, "manager_settings.json")
    if not os.path.exists(settings_path):
        parent_candidate = os.path.join(os.path.dirname(palbaker_root), "manager_settings.json")
        if os.path.exists(parent_candidate):
            settings_path = parent_candidate
    if not os.path.exists(settings_path): 
        return
    
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
        
    if palbaker_root not in sys.path:
        sys.path.append(palbaker_root)
        
    from utils.extractor.core import extract_game_files
    from utils.uasset_helper import decompile_uasset

    temp_dir = os.path.join(tempfile.gettempdir(), "palbaker_skel_meta")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    clean_template = template_id[3:] if template_id.startswith("SK_") else template_id
    skel_rel = f"Pal/Content/Pal/Model/Character/Skeleton/{clean_template}/SK_{clean_template}_Skeleton"
    
    print(f"[PalBaker] Extracting metadata from vanilla skeleton: {skel_rel}...")
    success, _ = extract_game_files(settings, [f"{skel_rel}.uasset", f"{skel_rel}.uexp"], temp_dir, format_type="raw")
    if not success: return

    uasset_disk = os.path.join(temp_dir, f"{skel_rel}.uasset")
    json_path = os.path.join(temp_dir, "vanilla_skel.json")
    uasset_gui = os.path.normpath(os.path.join(palbaker_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(palbaker_root, "deps", "Mappings.usmap"))

    if not decompile_uasset(uasset_gui, uasset_disk, json_path, usmap_path): return

    with open(json_path, "r", encoding="utf-8-sig") as f:
        skel_data = json.load(f)

    sockets_data, vb_sources, vb_targets, slot_names, slot_groups = [], [], [], [], []
    exports = skel_data.get("Exports", [])
    skel_exp = next((e for e in exports if e.get("ObjectName", "").endswith("Skeleton")), None)
    if not skel_exp: return

    # 1. Parse Sockets
    sockets_prop = next((p for p in skel_exp.get("Data", []) if p.get("Name") == "Sockets"), None)
    if sockets_prop and isinstance(sockets_prop.get("Value"), list):
        for s_ref in sockets_prop["Value"]:
            exp_idx = s_ref.get("Value")
            if isinstance(exp_idx, int) and 0 < exp_idx <= len(exports):
                sock_exp = exports[exp_idx - 1]
                sock_info = {}
                for p in sock_exp.get("Data", []):
                    p_name = p.get("Name")
                    if p_name == "SocketName": 
                        sock_info["SocketName"] = str(p.get("Value", ""))
                    elif p_name == "BoneName": 
                        sock_info["BoneName"] = str(p.get("Value", ""))
                    elif p_name == "RelativeLocation":
                        vec = _extract_struct_value(p)
                        sock_info["Loc"] = (
                            _safe_float(vec.get("X", 0.0), 0.0),
                            _safe_float(vec.get("Y", 0.0), 0.0),
                            _safe_float(vec.get("Z", 0.0), 0.0)
                        )
                    elif p_name == "RelativeRotation":
                        rot = _extract_struct_value(p)
                        sock_info["Rot"] = (
                            _safe_float(rot.get("Roll", 0.0), 0.0),
                            _safe_float(rot.get("Pitch", 0.0), 0.0),
                            _safe_float(rot.get("Yaw", 0.0), 0.0)
                        )
                    elif p_name == "RelativeScale":
                        scale = _extract_struct_value(p)
                        sock_info["Scale"] = (
                            _safe_float(scale.get("X", 1.0), 1.0),
                            _safe_float(scale.get("Y", 1.0), 1.0),
                            _safe_float(scale.get("Z", 1.0), 1.0)
                        )
                if "SocketName" in sock_info and "BoneName" in sock_info:
                    sockets_data.append(sock_info)

    # 2. Parse VirtualBones
    vb_prop = next((p for p in skel_exp.get("Data", []) if p.get("Name") == "VirtualBones"), None)
    if vb_prop and isinstance(vb_prop.get("Value"), list):
        for vb in vb_prop["Value"]:
            src = next((p.get("Value") for p in vb.get("Value", []) if p.get("Name") == "SourceBoneName"), None)
            tgt = next((p.get("Value") for p in vb.get("Value", []) if p.get("Name") == "TargetBoneName"), None)
            if src and tgt:
                vb_sources.append(src)
                vb_targets.append(tgt)

    # 3. Parse SlotGroups
    sg_prop = next((p for p in skel_exp.get("Data", []) if p.get("Name") == "SlotGroups"), None)
    if sg_prop and isinstance(sg_prop.get("Value"), list):
        for sg in sg_prop["Value"]:
            grp_name = next((p.get("Value") for p in sg.get("Value", []) if p.get("Name") == "GroupName"), None)
            slots_arr = next((p.get("Value") for p in sg.get("Value", []) if p.get("Name") == "SlotNames"), [])
            if grp_name and isinstance(slots_arr, list):
                for slot in slots_arr:
                    if slot.get("Value"):
                        slot_names.append(slot.get("Value"))
                        slot_groups.append(grp_name)

    # Re-express template socket offsets in the custom rig's bone frames (e.g. a head bone rolled 180 deg)
    bone_rest_ue = {}
    if sidecar_path and os.path.exists(sidecar_path):
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                bone_rest_ue = json.load(f).get("bone_rest_ue") or {}
        except Exception as e:
            print(f"[PalBaker] Warning reading bone_rest_ue from sidecar: {e}")
    if sockets_data and bone_rest_ue:
        from utils.bone_frames import frames_from_sidecar, load_template_frames, bone_delta, remap_vector, remap_rotator
        template_frames = load_template_frames(settings, clean_template, temp_dir)
        custom_frames = frames_from_sidecar({"bone_rest_ue": bone_rest_ue})
        for s_data in sockets_data:
            delta = bone_delta(s_data["BoneName"], template_frames, custom_frames)
            if not delta:
                continue
            s_data["Loc"] = remap_vector(s_data.get("Loc", (0.0, 0.0, 0.0)), delta)
            s_data["Rot"] = remap_rotator(*s_data.get("Rot", (0.0, 0.0, 0.0)), delta)
            print(f"[PalBaker] Socket {s_data['SocketName']} remapped to custom '{s_data['BoneName']}' frame: loc={s_data['Loc']} rot={s_data['Rot']}")
    elif sockets_data:
        print("[PalBaker] Warning: sidecar has no bone_rest_ue (refresh the blend); sockets copied in template bone frames.")

    # --- INJECT NATIVELY INTO UNREAL ---
    custom_skel = unreal.EditorAssetLibrary.load_asset(custom_skel_path)
    if not custom_skel: return

    # Inject Sockets via C++ API (bypassing protected property limits)
    socket_names = []
    bone_names = []
    locs = []
    rots = []
    scales = []

    for s_data in sockets_data:
        s_name = s_data.get("SocketName")
        b_name = s_data.get("BoneName")
        if not s_name or not b_name:
            continue

        socket_names.append(str(s_name))
        bone_names.append(str(b_name))
        
        lx, ly, lz = s_data.get("Loc", (0.0, 0.0, 0.0))
        locs.append(unreal.Vector(_safe_float(lx, 0.0), _safe_float(ly, 0.0), _safe_float(lz, 0.0)))
        
        r, p, yaw = s_data.get("Rot", (0.0, 0.0, 0.0))
        rots.append(unreal.Rotator(roll=_safe_float(r, 0.0), pitch=_safe_float(p, 0.0), yaw=_safe_float(yaw, 0.0)))
        
        sx, sy, sz = s_data.get("Scale", (1.0, 1.0, 1.0))
        scales.append(unreal.Vector(_safe_float(sx, 1.0), _safe_float(sy, 1.0), _safe_float(sz, 1.0)))

    if socket_names:
        report_socks = unreal.AnimScriptingLibrary.inject_sockets(
            custom_skel, socket_names, bone_names, locs, rots, scales
        )
        if report_socks.strip():
            print(report_socks, flush=True)

    # Inject VBs and Slots via C++ API
    report = unreal.AnimScriptingLibrary.inject_virtual_bones_and_slots(custom_skel, vb_sources, vb_targets, slot_names, slot_groups)
    if report.strip():
        print(report, flush=True)
    
    unreal.EditorAssetLibrary.save_loaded_asset(custom_skel)
    shutil.rmtree(temp_dir, ignore_errors=True)

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

def import_assets(ue_path, textures, fbx_file, target_mesh_name, base_pal, template_id=None, is_custom_pal=False, import_tex=True, has_custom_anims=False, palbaker_root="", sidecar_path=""):
    # Pre-calculate shared baseline textures to avoid redundant imports
    shared_textures = set()
    if sidecar_path and os.path.exists(sidecar_path):
        try:
            import json
            with open(sidecar_path, "r", encoding="utf-8") as f:
                sc_data = json.load(f)
                for mat_data in sc_data.get("materials", {}).values():
                    baseline = mat_data.get("baseline_settings", {})
                    for param_name, tex_pkg in baseline.get("texture_paths", {}).items():
                        if tex_pkg and not tex_pkg.lower().startswith(ue_path.lower()):
                            # Only treat as shared if the vanilla asset is actually present in this project;
                            # otherwise materials.py falls back to {ue_path}/{tex}, which must be imported.
                            if unreal.EditorAssetLibrary.does_asset_exist(tex_pkg.split(".")[0]):
                                tex_asset_name = tex_pkg.split("/")[-1].lower()
                                shared_textures.add(tex_asset_name)
        except Exception as e:
            print(f"[PalBaker] Warning reading sidecar for shared textures: {e}")

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

                if tex_name.lower() in shared_textures:
                    print(f"[PalBaker] Skipping local import of shared texture: {tex_name} (Using existing game asset). Rename your file if you want a custom override.", flush=True)
                    continue

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

        if not phys_exists and is_custom_pal and template_id:
            template_pa_path = f"/Game/Pal/Model/Character/{category}/{template_id}/PA_{template_id}_PhysicsAsset"
            if unreal.EditorAssetLibrary.does_asset_exist(template_pa_path):
                print(f"[PalBaker] Custom Pal detected without PhysicsAsset. Duplicating from template: {template_pa_path} -> {shared_phys_path}")
                unreal.EditorAssetLibrary.duplicate_asset(template_pa_path, shared_phys_path)
                phys_exists = True
            else:
                ar = unreal.AssetRegistryHelpers.get_asset_registry()
                assets = ar.get_assets_by_path(f"/Game/Pal/Model/Character/{category}", recursive=True)
                for a in assets:
                    if str(a.asset_class_path.asset_name) == "PhysicsAsset" and f"PA_{template_id}" in str(a.asset_name):
                        template_pa_path = str(a.package_name)
                        print(f"[PalBaker] Found fallback template PA: {template_pa_path}")
                        unreal.EditorAssetLibrary.duplicate_asset(template_pa_path, shared_phys_path)
                        phys_exists = True
                        break

        if phys_exists:
            print(f"[PalBaker] Using shared parent PhysicsAsset: {shared_phys_path}")
        else:
            print(f"[PalBaker] No parent PhysicsAsset found. Will generate and move to: {shared_phys_path}")

        task = unreal.AssetImportTask()
        task.set_editor_property('filename', fbx_file.replace("\\", "/"))
        task.set_editor_property('destination_path', ue_path)
        task.set_editor_property('destination_name', target_mesh_name)
        task.set_editor_property('replace_existing', True)
        task.set_editor_property('replace_existing_settings', True)
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
        skel_data.set_editor_property('use_t0_as_ref_pose', False)
        skel_data.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        # FbxImportUI inherits the last manual dialog values from EditorPerProjectUserSettings.ini; never trust them
        skel_data.set_editor_property('import_uniform_scale', 1.0)
        
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

        # 3. Native Skeleton Metadata Injection
        if has_custom_anims:
            target_skeleton_name = template_id if (is_custom_pal and template_id) else base_pal
            inject_vanilla_skeleton_metadata(palbaker_root, expected_skeleton_path, target_skeleton_name, sidecar_path)

        return target_asset_path, shared_phys_path

def import_vanilla_textures(entries):
    """Imports on-demand extracted vanilla textures (e.g. /Game/Pal/Effect/Textures) at their original game paths."""
    import_tasks = []
    for entry in entries or []:
        png = entry.get("png", "")
        dest_path = entry.get("destination_path", "")
        name = entry.get("name", "")
        if not (png and dest_path and name and os.path.exists(png)):
            continue
        if unreal.EditorAssetLibrary.does_asset_exist(f"{dest_path}/{name}"):
            continue

        task = unreal.AssetImportTask()
        task.set_editor_property('filename', os.path.normpath(png).replace("\\", "/"))
        task.set_editor_property('destination_path', dest_path)
        task.set_editor_property('destination_name', name)
        task.set_editor_property('replace_existing', True)
        task.set_editor_property('automated', True)
        task.set_editor_property('save', True)
        task.set_editor_property('factory', unreal.TextureFactory())
        import_tasks.append(task)

    if import_tasks:
        print(f"[PalBaker] Importing {len(import_tasks)} vanilla VFX texture(s) (editor-only, never packaged)...", flush=True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(import_tasks)

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