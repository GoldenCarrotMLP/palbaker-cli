# pythoncli/ue_import.py
import sys
import os
import json
import unreal  # type: ignore

palbaker_root = globals().get('PALBAKER_ROOT', '')
if palbaker_root and palbaker_root not in sys.path:
    sys.path.append(palbaker_root)

for k in list(sys.modules.keys()):
    if k.startswith("unreal_scripts"):
        del sys.modules[k]

from unreal_scripts.importer import clear_cache, import_assets, harvest_materials
from unreal_scripts.materials import build_materials, bind_materials_to_mesh
from unreal_scripts.rigging import apply_rigging

def run_pipeline():
    working_dir = globals().get('TARGET_FOLDER', os.getcwd())
    config_path = os.path.join(working_dir, "import_config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    ue_path = config["ue_target_path"]
    folder_name = ue_path.split("/")[-1]
    
    base_pal = config.get("base_pal", folder_name)
    target_mesh_name = config.get("target_mesh_name", f"SK_{folder_name}")
    redirect_folder = config.get("redirect_folder", "")
    
    template_id = config.get("template_id")
    is_custom_pal = config.get("is_custom_pal", False)
    preserve_materials = config.get("preserve_materials", True)
    
    # Handle backward compatibility or single-mesh payloads gracefully
    models = config.get("models", [])
    if not models and config.get("fbx_file"):
        models = [{"fbx_file": config.get("fbx_file"), "bone_data_file": config.get("bone_data_file", "bone_data.json"), "import_name": target_mesh_name}]
        
    for i, model in enumerate(models):
        fbx_file = model["fbx_file"]
        bone_data_file = model["bone_data_file"]
        import_name = model.get("import_name", target_mesh_name)
        
        # HARVEST PHASE: Safely cache any custom shading work the user did!
        harvested_materials = {}
        if preserve_materials:
            harvested_materials = harvest_materials(ue_path, target_mesh_name)
        
        clear_cache(ue_path, fbx_file, target_mesh_name, is_custom_pal)
        
        # Resolve target material compilation folder
        material_target_ue_path = ue_path
        if redirect_folder:
            material_target_ue_path = f"/Game/Pal/Model/Character/Monster/{base_pal}/{redirect_folder}"

        # Import FBX mesh directly to base folder (SK_Alpaca)
        target_asset_path, target_phys_path = import_assets(
            ue_path, config["textures"], fbx_file, target_mesh_name, base_pal, template_id, is_custom_pal, import_tex=True
        )
        
        # But compile the materials inside the variant's folder to avoid duplication!
        sidecar_json_path = os.path.join(working_dir, bone_data_file)
        mi_assets = build_materials(material_target_ue_path, sidecar_json_path, config["textures"], target_asset_path, preserve_materials)
        
        # Link materials of SK_Alpaca to point to the MI assets in Alpaca/Girafarig/
        bind_materials_to_mesh(target_asset_path, target_phys_path, mi_assets, harvested_materials)
        
        # Resolve target AnimBP compilation folder
        rigging_target_ue_path = ue_path
        if redirect_folder:
            rigging_target_ue_path = f"/Game/Pal/Model/Character/Monster/{base_pal}/{redirect_folder}"
            # Re-map import name so rigging.py searches for Girafarig_BP instead of SK_Alpaca_BP
            import_name = redirect_folder
        else:
            import_name = folder_name

        apply_rigging(working_dir, rigging_target_ue_path, import_name, base_pal, target_asset_path, bone_data_file, template_id, is_custom_pal)

    # Process Icon once after all meshes
    icon_file = config.get("icon_file")
    if icon_file:
        from unreal_scripts.importer import import_icon
        import_icon(icon_file, "/Game/Pal/Texture/PalIcon/Normal")

    print("Flushing all generated assets to disk...")
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(save_map_packages=False, save_content_packages=True)
    print("--- IMPORT COMPLETE ---")

run_pipeline()