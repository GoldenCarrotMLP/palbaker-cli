# pythoncli/build_mod.py
import os
import sys
import glob
import json
import shutil
import subprocess
import re
from utils.builder.workspace import ModWorkspace
from utils.builder.config_helper import restore_palbaker_backup, GameIniCookContext
from utils.builder.blender_helper import run_headless_blender
from utils.builder.unreal_helper import run_remote_import
from utils.builder.cooker_helper import clean_cook_environment, resolve_packaging_manifest, run_and_stream, pack_cooked_assets, is_path_blacklisted
from utils.state import save_push_state
from utils.blueprint_patcher import patch_actor_blueprint
from utils.sidecar_helper import load_sidecar, save_sidecar

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding='utf-8')

def main():
    if len(sys.argv) < 5:
        print("ERROR: Missing arguments. Usage: build_mod.py <base_pal> <mod_name> <category> <action>")
        sys.exit(1)

    BASE_PAL = sys.argv[1]
    MOD_NAME = sys.argv[2]
    CATEGORY = sys.argv[3] 
    ACTION = sys.argv[4]   
    
    PRESERVE_MATS = "--preserve-materials" in sys.argv

    from utils.config import load_settings
    settings = load_settings()

    workspace = ModWorkspace(BASE_PAL, MOD_NAME, CATEGORY, settings)
    custom_blacklist = getattr(workspace, "custom_blacklist", [])

    # -------------------------------------------------------------
    # DETECT CUSTOM ANIMATIONS IN SIDECAR
    # -------------------------------------------------------------
    sidecar_path = os.path.join(workspace.fmodel_dir, f"{MOD_NAME}_blend.json")
    sidecar_data = load_sidecar(sidecar_path)
    
    is_anim_active = bool(sidecar_data.get("custom_animations", {}).get("is_active", False))
    workspace.has_anims = is_anim_active
    if is_anim_active:
        print(f"[PalBaker Anims] Custom animations are active for {MOD_NAME}: Safe skeleton stripping disabled & anim cooking enabled.", flush=True)
    else:
        print(f"[PalBaker] Custom animations inactive for {MOD_NAME}: Using shared vanilla skeleton.", flush=True)

    # 1. READ VANILLA REDIRECT OPTION
    redirect_folder = ""
    if not workspace.is_variant:
        base_sidecar_path = os.path.join(workspace.fmodel_dir, f"{workspace.base_pal}_blend.json")
        base_sidecar_data = load_sidecar(base_sidecar_path)
        redirect_folder = base_sidecar_data.get("active_vanilla_replacer", "")

    # If redirection is active, shift local files lookup directory to the variant folder!
    if redirect_folder:
        print(f"[Redirect] Base mesh SK_{BASE_PAL} will bake using {redirect_folder}'s .blend geometry...", flush=True)
        workspace.fmodel_dir = os.path.join(workspace.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", CATEGORY, BASE_PAL, redirect_folder)

    # -------------------------------------------------------------
    # PHASE 0: RAW FMODEL DECOMPILE (Create .blend file)
    # -------------------------------------------------------------
    if ACTION == "create_blend":
        psk_files = glob.glob(os.path.join(workspace.fmodel_dir, "*.psk"))
        if not psk_files:
            print("ERROR: No .psk skeletal mesh found in FModel directory.", flush=True)
            sys.exit(1)
            
        reconstructor_script = os.path.join(os.path.dirname(__file__), "utils", "blender_reconstruct.py")
        extractor_script = os.path.normpath(os.path.join(os.path.dirname(__file__), "utils", "blender_extractor.py"))
        
        from utils.fmodel_helper import preprocess_fmodel_textures
        preprocess_fmodel_textures(workspace.fmodel_dir, workspace.fmodel_root)
        
        psk_files.sort()
        processed_bases = set()
        
        target_psks = [p for p in psk_files if os.path.splitext(os.path.basename(p))[0].lower() in [f"sk_{MOD_NAME.lower()}", MOD_NAME.lower()]]
        if target_psks:
            psk_files = target_psks

        for psk_file in psk_files:
            psk_base = os.path.splitext(os.path.basename(psk_file))[0]
            if psk_base.lower().startswith("sk_"):
                psk_base = psk_base[3:]
                
            psk_base = re.sub(r'_LOD\d+$', '', psk_base, flags=re.IGNORECASE)
            if psk_base in processed_bases:
                continue
            processed_bases.add(psk_base)
                
            blend_file = os.path.join(workspace.fmodel_dir, f"{MOD_NAME}.blend")
            psk_file_clean = psk_file.replace("\\", "/")
            blend_file_clean = blend_file.replace("\\", "/")
            output_json = os.path.join(workspace.fmodel_dir, f"{MOD_NAME}_blend.json")

            # --- 1. SEED SIDECAR WITH REPLICATED ABP NODES BEFORE BLENDER RUNS ---
            from utils.abp_parser import identify_abp_json, parse_abp_nodes
            detected_abp = identify_abp_json(workspace.fmodel_dir)
            if detected_abp:
                abp_payload = parse_abp_nodes(detected_abp)
                sidecar_data = load_sidecar(output_json)
                sidecar_data.update(abp_payload)
                sidecar_data["has_replicated_abp"] = True
                save_sidecar(output_json, sidecar_data)
                print(
                    f"[PalBaker] Ingesting replicated AnimBlueprint ({len(abp_payload['jiggle_bones'])} springs, "
                    f"{len(abp_payload['lookat_bones'])} lookats, {len(abp_payload['copy_bones'])} copies)...",
                    flush=True
                )
            # ---------------------------------------------------------------------
            
            print(f"Launching headless Blender to reconstruct .blend workspace from {os.path.basename(psk_file)}...", flush=True)
            result = run_headless_blender(
                workspace.blender_path, 
                None, 
                reconstructor_script, 
                ["--fbx", psk_file_clean, "--output", blend_file_clean, "--sidecar", output_json.replace("\\", "/")]
            )
            
            # --- PRINT BLENDER'S INTERNAL LOGS TO UI CONSOLE ---
            if result.stdout.strip():
                print(result.stdout, flush=True)
            if result.stderr.strip():
                print(result.stderr, flush=True)
            # ----------------------------------------------------

            if os.path.exists(blend_file):
                print(f"SUCCESS! .blend file generated at: {blend_file}", flush=True)
                
                print(f"Generating companion sidecar layout for {MOD_NAME}...", flush=True)
                result_sidecar = run_headless_blender(
                    workspace.blender_path,
                    blend_file,
                    extractor_script,
                    ["--output", output_json]
                )
                
                if not os.path.exists(output_json):
                    print("❌ ERROR: Sidecar layout generation failed. Blender Terminal Traceback:", flush=True)
                    if result_sidecar.stdout.strip():
                        print(result_sidecar.stdout, flush=True)
                    if result_sidecar.stderr.strip():
                        print(result_sidecar.stderr, flush=True)
                    sys.exit(1)
            else:
                print(f"ERROR: Blender failed to save .blend file for {MOD_NAME}. Traceback:", flush=True)
                print(result.stdout, flush=True)
                sys.exit(1)

    # -------------------------------------------------------------
    # PHASE 1: IMPORT (Push to Unreal)
    # -------------------------------------------------------------
    if ACTION in ["push", "full"]:
        import_targets = []
        if os.path.exists(workspace.fmodel_dir):
            import_targets.append((workspace.fmodel_dir, workspace.ue_virtual_path))
            
        if not import_targets:
            print("ERROR: No raw model sources found in workspaces to push.", flush=True)
            sys.exit(1)

        # Ingest any detected AnimBlueprint JSON into the sidecars before pushing
        from utils.abp_parser import identify_abp_json, parse_abp_nodes
        detected_abp = identify_abp_json(workspace.fmodel_dir)
        if detected_abp:
            abp_payload = parse_abp_nodes(detected_abp)
            print(
                f"[PalBaker ABP] Ingesting AnimBlueprint ({os.path.basename(detected_abp)}): "
                f"{len(abp_payload['jiggle_bones'])} springs, {len(abp_payload['lookat_bones'])} lookats, "
                f"{len(abp_payload['copy_bones'])} copies, {len(abp_payload['offset_bones'])} offsets into sidecar...",
                flush=True
            )
            for target_dir, _ in import_targets:
                blend_files = glob.glob(os.path.join(target_dir, "*.blend"))
                for blend_file in blend_files:
                    base_name = os.path.splitext(os.path.basename(blend_file))[0]
                    output_json = os.path.normpath(os.path.join(target_dir, f"{base_name}_blend.json"))
                    sidecar_data = load_sidecar(output_json)
                    sidecar_data.update(abp_payload)
                    sidecar_data["has_replicated_abp"] = True
                    save_sidecar(output_json, sidecar_data)

        from utils.dynamic_pals_helper import sync_sidecar_metadata
        from utils.fmodel_helper import sync_sidecar_material_baselines

        for target_dir, _ in import_targets:
            blend_files = glob.glob(os.path.join(target_dir, "*.blend"))
            for blend_file in blend_files:
                base_name = os.path.splitext(os.path.basename(blend_file))[0]
                output_json = os.path.normpath(os.path.join(target_dir, f"{base_name}_blend.json"))
                sync_sidecar_material_baselines(output_json, workspace.base_pal, workspace.category, workspace.fmodel_root, settings)
                print(f"Pre-import synchronizing layout metadata for {os.path.basename(blend_file)}...", flush=True)
                sync_sidecar_metadata(workspace.blender_path, blend_file)

        for target_dir, virtual_path in import_targets:
            blend_files = glob.glob(os.path.join(target_dir, "*.blend"))
            
            for blend_file in blend_files:
                base_name = os.path.splitext(os.path.basename(blend_file))[0]
                fbx_file = os.path.join(target_dir, f"{base_name}.fbx")
                output_json = os.path.join(target_dir, f"{base_name}_blend.json")
                
                extractor_script = os.path.join(os.path.dirname(__file__), "utils", "blender_extractor.py")
                print(f"Running headless Blender (Exporting FBX for {base_name})...", flush=True)
                
                result = run_headless_blender(workspace.blender_path, blend_file, extractor_script, ["--output", output_json, "--fbx", fbx_file])
                
                if result.returncode != 0:
                    print(f"❌ ERROR: Headless Blender failed to export FBX for {base_name}. Traceback:", flush=True)
                    if result.stdout.strip():
                        print(result.stdout, flush=True)
                    if result.stderr.strip():
                        print(result.stderr, flush=True)
                    sys.exit(1)

            pngs = glob.glob(os.path.join(target_dir, "*.png"))
            jsons = glob.glob(os.path.join(target_dir, "MI_*.json"))
            fbx_files = glob.glob(os.path.join(target_dir, "*.fbx"))
            
            models = []
            for fbx in fbx_files:
                fbx_base = os.path.splitext(os.path.basename(fbx))[0]
                import_name = workspace.target_mesh_name if (fbx_base == MOD_NAME) else fbx_base
                
                models.append({
                    "fbx_file": fbx,
                    "bone_data_file": f"{fbx_base}_blend.json",
                    "import_name": import_name
                })

            sidecar_path = os.path.join(target_dir, f"{MOD_NAME}_blend.json")
            target_sidecar_data = load_sidecar(sidecar_path)
            preserve_materials = bool(target_sidecar_data.get("preserve_materials", True))
                    
            if "--preserve-materials" in sys.argv:
                preserve_materials = True
            elif "--overwrite-materials" in sys.argv:
                preserve_materials = False

            push_materials = bool(target_sidecar_data.get("push_materials", True))
            push_textures = bool(target_sidecar_data.get("push_textures", True))
            push_animbp = bool(target_sidecar_data.get("push_animbp", True))

            config = {
                "ue_target_path": virtual_path,
                "textures": pngs,
                "models": models,
                "mi_jsons": jsons,
                "icon_file": workspace.icon_fmodel_path if workspace.has_icon else None,
                "template_id": workspace.template_id,
                "is_custom_pal": workspace.is_custom_pal,
                "preserve_materials": preserve_materials,
                "push_materials": push_materials,
                "push_textures": push_textures,
                "push_animbp": push_animbp,
                "has_custom_anims": workspace.has_anims,
                "base_pal": BASE_PAL,
                "target_mesh_name": workspace.target_mesh_name,
                "redirect_folder": redirect_folder
            }
            config_path = os.path.join(target_dir, "import_config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

            print(f"Connecting to Open Unreal Engine (Target: {os.path.basename(target_dir)})...", flush=True)
            ue_import_script = os.path.join(os.path.dirname(__file__), "ue_import.py")
            success, log_msg = run_remote_import(workspace.ue_root, workspace.target_project_name, target_dir, ue_import_script)
            
            if log_msg.strip():
                print(log_msg.encode('utf-8', errors='replace').decode('utf-8'), flush=True)
                
            if not success:
                print(f"!!! ERROR INSIDE UNREAL ENGINE DURING {os.path.basename(target_dir)} IMPORT !!!", flush=True)
                sys.exit(1)

        ue_abs_path = os.path.join(workspace.project_dir, "Content", workspace.ue_virtual_path.replace("/Game/", ""))
        save_push_state(workspace.fmodel_dir, ue_abs_path)

    # -------------------------------------------------------------
    # PHASE 1.5: REFRESH BLEND (Sync layouts on the spot)
    # -------------------------------------------------------------
    if ACTION == "refresh_blend":
        blend_files = []
        if os.path.exists(workspace.fmodel_dir):
            blend_files.extend(glob.glob(os.path.join(workspace.fmodel_dir, "*.blend")))

        if not blend_files:
            print("ERROR: No .blend files found in workspace to refresh.", flush=True)
            sys.exit(1)

        # Ingest any detected AnimBlueprint JSON into the sidecars before extracting
        from utils.abp_parser import identify_abp_json, parse_abp_nodes
        detected_abp = identify_abp_json(workspace.fmodel_dir)
        if detected_abp:
            abp_payload = parse_abp_nodes(detected_abp)
            print(
                f"[PalBaker ABP] Ingesting AnimBlueprint ({os.path.basename(detected_abp)}): "
                f"{len(abp_payload['jiggle_bones'])} springs, {len(abp_payload['lookat_bones'])} lookats, "
                f"{len(abp_payload['copy_bones'])} copies, {len(abp_payload['offset_bones'])} offsets into sidecar...",
                flush=True
            )
            for blend_file in blend_files:
                parent_dir = os.path.dirname(blend_file)
                base_name = os.path.splitext(os.path.basename(blend_file))[0]
                output_json = os.path.normpath(os.path.join(parent_dir, f"{base_name}_blend.json"))
                sidecar_data = load_sidecar(output_json)
                sidecar_data.update(abp_payload)
                sidecar_data["has_replicated_abp"] = True
                save_sidecar(output_json, sidecar_data)

        # Sync missing baseline material settings from parent material instances
        from utils.fmodel_helper import sync_sidecar_material_baselines
        for blend_file in blend_files:
            parent_dir = os.path.dirname(blend_file)
            base_name = os.path.splitext(os.path.basename(blend_file))[0]
            output_json = os.path.normpath(os.path.join(parent_dir, f"{base_name}_blend.json"))
            sync_sidecar_material_baselines(output_json, workspace.base_pal, workspace.category, workspace.fmodel_root, settings)

        extractor_script = os.path.normpath(os.path.join(os.path.dirname(__file__), "utils", "blender_extractor.py"))
        for blend_file in blend_files:
            parent_dir = os.path.dirname(blend_file)
            base_name = os.path.splitext(os.path.basename(blend_file))[0]
            output_json = os.path.normpath(os.path.join(parent_dir, f"{base_name}_blend.json"))
            
            print(f"Synchronizing sidecar layout metadata for {os.path.basename(blend_file)}...", flush=True)
            
            result = run_headless_blender(
                workspace.blender_path,
                blend_file,
                extractor_script,
                ["--output", output_json]
            )
            
            if result.stdout.strip():
                print(result.stdout.encode('utf-8', errors='replace').decode('utf-8'), flush=True)
            if result.stderr.strip():
                print(result.stderr.encode('utf-8', errors='replace').decode('utf-8'), flush=True)
            
        print("SUCCESS! Staged layout sync completed.", flush=True)

    # -------------------------------------------------------------
    # PHASE 2: COOK (Compile only)
    # -------------------------------------------------------------
    external_dependency_packages = []
    if ACTION in ["cook", "full", "cook_only", "recursive_cook"]:
        from utils.builder.cooker_helper import verify_cooking_memory_limit
        
        is_safe, err_msg = verify_cooking_memory_limit(threshold_gb=2.5)
        if not is_safe:
            print(f"ERROR: {err_msg}", flush=True)
            sys.exit(1)

        restore_palbaker_backup(workspace.uproject_path)
        from utils.builder.cooker_helper import clean_cook_environment
        clean_cook_environment(workspace)

        category_sanitized = workspace.category.replace(" ", "_").replace("\\", "/")
        cat_parts = workspace.category.replace("/", os.sep)
        extra_cook_paths = []

        # Automatically discover variant subfolders directly from the Unreal Project Content folder
        ue_char_dir = os.path.normpath(os.path.join(
            workspace.project_dir, "Content", "Pal", "Model", "Character", 
            cat_parts, workspace.base_pal
        )) if workspace.project_dir else ""
        if os.path.exists(ue_char_dir):
            for sub in os.listdir(ue_char_dir):
                if hasattr(workspace, "skipped_variants") and sub in workspace.skipped_variants:
                    print(f"  [Cook Queue] Skipping variant directory to cook: {sub} (in skipped_variants)", flush=True)
                    continue
                sub_p = os.path.join(ue_char_dir, sub)
                if os.path.isdir(sub_p) and not sub.startswith(".") and sub.lower() not in ["sources", ".palbaker_audio"]:
                    variant_vpath = f"/Game/Pal/Model/Character/{category_sanitized}/{workspace.base_pal}/{sub}"
                    if variant_vpath not in extra_cook_paths:
                        extra_cook_paths.append(variant_vpath)
                        print(f"  [Cook Queue] Added variant directory to cook: {variant_vpath}", flush=True)

        # Ensure custom animations, skeletons, and unique attack actions are cooked
        if workspace.has_anims:
            if workspace.anims_virtual_path not in extra_cook_paths:
                extra_cook_paths.append(workspace.anims_virtual_path)
            if workspace.skeleton_virtual_path not in extra_cook_paths:
                extra_cook_paths.append(workspace.skeleton_virtual_path)
            waza_virtual_dir = f"/Game/Pal/Blueprint/Action/Waza/{MOD_NAME}"
            if waza_virtual_dir not in extra_cook_paths:
                extra_cook_paths.append(waza_virtual_dir)

        if workspace.has_custom_shader and not is_path_blacklisted("/Game/CartoonCelShader/Materials/CelShader", workspace.custom_blacklist):
            extra_cook_paths.append("/Game/CartoonCelShader/Materials/CelShader")
        if workspace.has_icon and not is_path_blacklisted(workspace.icon_virtual_path, workspace.custom_blacklist):
            extra_cook_paths.append(workspace.icon_virtual_path)

        if ACTION == "recursive_cook":
            print("[Recursive Cook] Discovering deep asset dependencies in Unreal Editor...", flush=True)
            from utils.builder.dependency_helper import run_dependency_crawler
            raw_dependency_packages = run_dependency_crawler(workspace)
            print(f"[Recursive Cook] Discovered {len(raw_dependency_packages)} external dependency package(s).", flush=True)
            
            external_dependency_packages = []
            for pkg in raw_dependency_packages:
                if is_path_blacklisted(pkg, workspace.custom_blacklist):
                    print(f"  [Recursive Cook] Blacklisted dependency excluded: {pkg}", flush=True)
                else:
                    external_dependency_packages.append(pkg)
                    folder = pkg.rsplit("/", 1)[0]
                    if folder not in extra_cook_paths:
                        extra_cook_paths.append(folder)
                        print(f"  [Recursive Cook] Queued external dependency folder: {folder}", flush=True)
            
        with GameIniCookContext(workspace, extra_paths=extra_cook_paths):
            print("Cooking Target Folders...", flush=True)
            from utils.builder.cooker_helper import run_and_stream
            
            cook_cmd = [
                workspace.ue_cmd_path, 
                workspace.uproject_path, 
                "-run=cook", 
                "-targetplatform=Windows", 
                "-unversioned", 
                "-NoUI", 
                "-Map=/Engine/Maps/Entry"
            ]
            had_cook_issues = run_and_stream(cook_cmd)
            if had_cook_issues:
                print("COOK FAILED: Errors encountered during compile.", flush=True)
                sys.exit(1)
            else:
                print("COOK SUCCESS: Compilation completed successfully.", flush=True)

    # -------------------------------------------------------------
    # PHASE 3: PACK (Package only)
    # -------------------------------------------------------------
    if ACTION in ["cook", "full", "pack", "pack_only", "recursive_cook"]:
        # Single Unified Blueprint Orchestration (Actor BP, AnimBP, BlendSpaces, Weapons, Bosses)
        if workspace.is_custom_pal or workspace.has_anims:
            print(f"[PalBaker Blueprints] Auto-generating unified blueprint stack (Actor BP, AnimBP, BlendSpaces)...", flush=True)
            from utils.blueprint_patcher import patch_actor_blueprint
            source_template = workspace.template_id if workspace.is_custom_pal else workspace.base_pal
            patch_actor_blueprint(
                settings,
                MOD_NAME,
                source_template,
                has_anims=workspace.has_anims,
                category=CATEGORY,
                base_pal=BASE_PAL,
                keep_temp=True 
            )

        final_pak_path = workspace.output_pak_clean
        print(f"Preparing Pak (Target: {os.path.basename(final_pak_path)})...", flush=True)
        
        response_dir = os.path.join(workspace.project_dir, "Intermediate") if workspace.project_dir else os.path.dirname(__file__)
        response_file = os.path.normpath(os.path.join(response_dir, "response.txt"))

        folders_to_pack = resolve_packaging_manifest(workspace, workspace.has_anims, extra_packages=external_dependency_packages)

        print("Building final PAK...", flush=True)
        files_found = pack_cooked_assets(
            workspace.unrealpak_path, 
            response_file, 
            final_pak_path, 
            folders_to_pack, 
            workspace.has_anims,
            custom_blacklist,
            is_custom_pal=workspace.is_custom_pal
        )
        
        if files_found == 0:
            has_other_outputs = bool(workspace.is_dynamic_pals_active or (hasattr(workspace, 'has_icon') and workspace.has_icon))
            if not has_other_outputs:
                from utils.builder.cooker_helper import get_staged_audio_overrides
                if get_staged_audio_overrides(workspace):
                    has_other_outputs = True
            
            if not has_other_outputs:
                print("ERROR: No files found to pack. Cook process might have failed.", flush=True)
                sys.exit(1)
            else:
                print("WARNING: No compiled uassets found to pack. Staging non-uasset files (Dynamic Pals configs/audio/icon) separately.", flush=True)

        swap_json_dir = ""
        if workspace.palworld_exe and os.path.exists(workspace.palworld_exe):
            swap_json_dir = os.path.join(os.path.dirname(workspace.palworld_exe), "Pal", "Content", "Paks", "~Mods", "SwapJSON")
        
        if swap_json_dir:
            base_fmodel_dir = os.path.normpath(os.path.join(
                workspace.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", 
                workspace.category, workspace.base_pal
            ))
            manifest_path = os.path.join(base_fmodel_dir, f"{workspace.base_pal}_dynamic_pals.json")

            custom_name = ""
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        custom_name = json.load(f).get("custom_json_name", "")
                except Exception:
                    pass

            from utils.dynamic_pals_helper import sanitize_json_filename, compile_unified_dynamic_pals_json
            final_filename = sanitize_json_filename(custom_name, f"palbaker-{workspace.base_pal}")
            target_deployed_json = os.path.join(swap_json_dir, f"{final_filename}.json")

            if not workspace.is_dynamic_pals_active:
                for p in [target_deployed_json, os.path.join(swap_json_dir, f"palbaker-{workspace.base_pal}.json")]:
                    if os.path.exists(p):
                        try: os.remove(p)
                        except OSError: pass
            else:
                if os.path.exists(manifest_path):
                    success, msg = compile_unified_dynamic_pals_json(workspace.base_pal, base_fmodel_dir, swap_json_dir)
                    print(msg, flush=True)

if __name__ == "__main__":
    main()