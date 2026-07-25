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
        # 1. Gather all SkeletalMesh assets inside the target virtual path
        sk_assets = []
        for asset in assets:
            asset_class = str(asset.asset_class_path.asset_name)
            if asset_class == "SkeletalMesh" or "SkeletalMesh" in asset_class:
                try:
                    loaded = unreal.EditorAssetLibrary.load_asset(asset.package_name)
                    if loaded:
                        sk_assets.append(loaded)
                except Exception as e:
                    print(f"Warning: Skipping unloadable skeletal mesh {asset.package_name}: {e}")

        # 2. Flexible Target Selection:
        # First try exact match with target_mesh_name.
        # If not found, prioritize meshes located directly inside ue_path, then fallback to any found SkeletalMesh.
        target_sk_mesh = None
        if sk_assets:
            if target_mesh_name:
                target_sk_mesh = next((m for m in sk_assets if m.get_name().lower() == target_mesh_name.lower()), None)
            
            if not target_sk_mesh:
                # Filter for meshes directly inside the target directory
                direct_meshes = [
                    m for m in sk_assets 
                    if m.get_outermost().get_name().rsplit('/', 1)[0].lower() == ue_path.lower()
                ]
                target_sk_mesh = direct_meshes[0] if direct_meshes else sk_assets[0]
                print(f"[Decompiler] Target mesh '{target_mesh_name}' not found by exact name. Selected folder SkeletalMesh: '{target_sk_mesh.get_name()}'")

        for asset in assets:
            asset_class = str(asset.asset_class_path.asset_name)
            
            if asset_class not in ["SkeletalMesh", "Texture2D", "MaterialInstanceConstant"] and "SkeletalMesh" not in asset_class:
                continue

            try:
                loaded_asset = unreal.EditorAssetLibrary.load_asset(asset.package_name)
            except Exception as e:
                print(f"Warning: Skipping corrupted/unloadable asset {asset.package_name}: {e}")
                continue

            if not loaded_asset:
                continue

            if asset_class == "SkeletalMesh" or "SkeletalMesh" in asset_class:
                # If we resolved a target mesh, ensure we only export that designated mesh
                if target_sk_mesh and loaded_asset != target_sk_mesh:
                    print(f"Skipping secondary/mismatched mesh: {loaded_asset.get_name()}")
                    continue
                
                base_name = mod_name if mod_name else loaded_asset.get_name().replace("SK_", "")
                fbx_path = f"{working_dir}/{base_name}.fbx"
                
                if not overwrite and os.path.exists(fbx_path):
                    print(f"Skipping existing FBX: {os.path.basename(fbx_path)}")
                else:
                    print(f"Exporting SkeletalMesh '{loaded_asset.get_name()}' to: {fbx_path}")
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