# unreal_scripts/rigging.py
import unreal  # type: ignore
import os
import json

def apply_rigging(working_dir, ue_path, import_name, folder_name, target_asset_path, bone_data_file="bone_data.json", template_id=None, is_custom_pal=False):
    json_path = os.path.join(working_dir, bone_data_file)
    if not os.path.exists(json_path):
        print(f"[PalBaker Error] Bone data file missing at: {json_path}")
        return

    # Check for procedural LookAt/SpringBone chain and notify
    try:
        with open(json_path, "r", encoding="utf-8") as f_meta:
            meta_data = json.load(f_meta)
        if meta_data.get("lookat_bones") and meta_data.get("copy_bones"):
            print(f"[PalBaker] Detected procedural Spring-to-LookAt physics chain for {import_name}. Generating complex AnimGraph...", flush=True)
    except Exception:
        pass

    print(f"Checking for Animation Blueprint to apply advanced rigging to: {target_asset_path}")
    anim_bp = None
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    
    # 1. Target AnimBP naming and directory
    bp_name = f"{import_name}_BP"
    target_bp_dir = ue_path
    target_bp_path = f"{target_bp_dir}/{bp_name}"

    # 2. Resolve skeletal mesh and exact bound skeleton
    loaded_mesh = unreal.EditorAssetLibrary.load_asset(target_asset_path)
    if not loaded_mesh:
        print(f"[PalBaker Rigging Error] Skeletal Mesh missing at: {target_asset_path}")
        return

    # Read skeleton directly from mesh asset
    skel = loaded_mesh.get_editor_property('skeleton')

    # Fallback search if pointer is empty
    if not skel:
        parts = ue_path.replace("\\", "/").split("/")
        category = "Monster"
        if "Character" in parts:
            idx = parts.index("Character")
            if idx + 1 < len(parts):
                category = parts[idx + 1]

        target_skeleton_name = template_id if (is_custom_pal and template_id) else folder_name
        clean_skel_name = target_skeleton_name[3:] if target_skeleton_name.startswith("SK_") else target_skeleton_name

        is_humanoid = (
            "npc" in category.lower() or 
            "player" in category.lower() or 
            folder_name.lower().startswith("sk_npc") or 
            folder_name.lower().startswith("sk_player") or
            "human" in folder_name.lower()
        )

        if is_humanoid:
            candidate_skeletons = [
                "/Game/Pal/Model/Character/Skeleton/Human/SK_PalHuman_Skeleton",
                "/Game/Pal/Model/Character/Skeleton/Human/SK_PalHuman_Female_Skeleton",
                "/Game/Pal/Model/Character/Skeleton/Human/SK_PalHuman_Male_Skeleton",
                "/Game/Pal/Model/Character/Skeleton/Player/SK_PalHuman_Skeleton"
            ]
        else:
            candidate_skeletons = [
                f"/Game/Pal/Model/Character/Skeleton/{folder_name}/{import_name}/SK_{import_name}_Skeleton",
                f"/Game/Pal/Model/Character/Skeleton/{folder_name}/SK_{import_name}_Skeleton",
                f"/Game/Pal/Model/Character/Skeleton/{clean_skel_name}/SK_{clean_skel_name}_Skeleton"
            ]

        for cand in candidate_skeletons:
            if unreal.EditorAssetLibrary.does_asset_exist(cand):
                skel = unreal.EditorAssetLibrary.load_asset(cand)
                break

    if not skel:
        print(f"ERROR: Cannot create Animation Blueprint because skeleton for {target_asset_path} could not be resolved.")
        return

    print(f"[PalBaker Rigging] Using Skeleton for AnimBP: {skel.get_path_name()}")

    # 3. Clean old AnimBP before recreation
    if unreal.EditorAssetLibrary.does_asset_exist(target_bp_path):
        print(f"Cleaning old Animation Blueprint for fresh rebuild: {target_bp_path}")
        try:
            unreal.EditorAssetLibrary.delete_asset(target_bp_path)
        except Exception as e:
            print(f"Warning: Failed to delete old AnimBP: {e}")
            
    print(f"Generating new custom Animation Blueprint: {target_bp_path}")
    factory = unreal.AnimBlueprintFactory()
    factory.set_editor_property('target_skeleton', skel)
    unreal.EditorAssetLibrary.make_directory(target_bp_dir)
    anim_bp = asset_tools.create_asset(bp_name, target_bp_dir, unreal.AnimBlueprint.static_class(), factory)
    
    if not anim_bp:
        print(f"ERROR: Failed to instantiate Animation Blueprint asset: {target_bp_path}")
        return

    print(f"Successfully generated new Animation Blueprint: {bp_name}")

    # 4. Apply PalBaker node graph via C++ plugin
    print(f"Applying PalBaker rigging setup to: {anim_bp.get_name()}")
    try:
        success = unreal.AnimScriptingLibrary.apply_pal_baker_rigging(anim_bp, json_path)
        if success:
            print("Rigging applied and compiled successfully.")
            
            # 5. Bind generated AnimBP class to Post-Process slot of the Skeletal Mesh
            bp_path_name = anim_bp.get_path_name().split(".")[0]
            class_path = f"{bp_path_name}.{bp_name}_C"
            
            gen_class = unreal.load_class(None, class_path)
            if gen_class and loaded_mesh:
                loaded_mesh.set_editor_property('post_process_anim_blueprint', gen_class)
                unreal.EditorAssetLibrary.save_loaded_asset(loaded_mesh)
                print(f"Successfully bound {class_path} to Post-Process slot on {target_asset_path}!")
            else:
                print("Failed to load generated blueprint class or skeletal mesh target.")
        else:
            print(f"[PalBaker Error] apply_pal_baker_rigging returned false for {anim_bp.get_name()}.")
    except Exception as e:
        print(f"Failed to execute rigging setup: {e}")