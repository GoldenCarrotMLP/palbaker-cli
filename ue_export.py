# ue_export.py
import unreal  # type: ignore
import os
import json
import tempfile

def run_export():
    # 1. Load configuration from the shared system temporary folder
    temp_dir = tempfile.gettempdir()
    config_path = os.path.join(temp_dir, "palbaker_export_config.json")
    
    if not os.path.exists(config_path):
        print("ERROR: export_config.json path not provided or file missing.")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    working_dir = config["target_folder"].replace("\\", "/")
    ue_path = config["ue_path"]
    overwrite = config["overwrite_all"]
    mod_name = config["mod_name"]
    target_mesh_name = config["target_mesh_name"]

    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = ar.get_assets_by_path(ue_path, recursive=True)

    os.makedirs(working_dir, exist_ok=True)
    materials_metadata = {}

    if assets is not None:
        for asset in assets:
            asset_class = str(asset.asset_class_path.asset_name)
            
            if asset_class not in ["SkeletalMesh", "Texture2D", "MaterialInstanceConstant"]:
                continue

            try:
                loaded_asset = unreal.EditorAssetLibrary.load_asset(asset.package_name)
            except Exception as e:
                print(f"Warning: Skipping corrupted/unloadable asset {asset.package_name}: {e}")
                continue

            if not loaded_asset:
                continue

            if asset_class == "SkeletalMesh":
                asset_name = loaded_asset.get_name()
                
                # COLLISION LOCK: If a target mesh name is passed, ignore other meshes inside the base directory
                if target_mesh_name and asset_name != target_mesh_name:
                    print(f"Skipping mismatched mesh: {asset_name}")
                    continue
                
                base_name = mod_name if mod_name else asset_name.replace("SK_", "")
                fbx_path = f"{working_dir}/{base_name}.fbx"
                
                if not overwrite and os.path.exists(fbx_path):
                    print(f"Skipping existing FBX: {os.path.basename(fbx_path)}")
                else:
                    print(f"Exporting SkeletalMesh to: {fbx_path}")
                    task = unreal.AssetExportTask()
                    task.set_editor_property('object', loaded_asset)
                    task.set_editor_property('filename', fbx_path)
                    task.set_editor_property('automated', True)
                    task.set_editor_property('prompt', False)
                    task.set_editor_property('replace_identical', True)
                    
                    options = unreal.FbxExportOption()
                    task.set_editor_property('options', options)
                    unreal.Exporter.run_asset_export_task(task)

            elif asset_class == "Texture2D":
                png_path = f"{working_dir}/{loaded_asset.get_name()}.png"
                
                if not overwrite and os.path.exists(png_path):
                    print(f"Skipping existing Texture: {os.path.basename(png_path)}")
                else:
                    print(f"Exporting Texture2D to: {png_path}")
                    task = unreal.AssetExportTask()
                    task.set_editor_property('object', loaded_asset)
                    task.set_editor_property('filename', png_path)
                    task.set_editor_property('automated', True)
                    task.set_editor_property('prompt', False)
                    task.set_editor_property('replace_identical', True)
                    
                    unreal.Exporter.run_asset_export_task(task)

            elif asset_class == "MaterialInstanceConstant":
                mat_name = loaded_asset.get_name()
                
                parent_name = "MI_PalLit_CharacterBodyBase"
                parent_mat = loaded_asset.get_editor_property('parent')
                if parent_mat:
                    parent_name = parent_mat.get_name()
                
                params = {}
                tex_params = loaded_asset.get_editor_property('texture_parameter_values')
                for tex_param in tex_params:
                    param_name = str(tex_param.parameter_info.name)
                    if tex_param.parameter_value:
                        params[param_name] = tex_param.parameter_value.get_name()
                        
                materials_metadata[mat_name] = {
                    "parent_class": parent_name,
                    "parameters": params
                }

    if materials_metadata:
        meta_path = os.path.join(working_dir, "materials_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(materials_metadata, f, indent=4)
        print(f"Exported True Material Topology Metadata to: {meta_path}")

run_export()