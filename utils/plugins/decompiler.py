# utils/plugins/decompiler.py
import os
import sys
import time
import glob
import subprocess
import json
import tempfile

def run_decompile_pipeline(ue_root: str, uproject_path: str, mod_name: str, fmodel_dir: str, ue_virtual_path: str, blender_path: str, verbose: bool = False, overwrite: bool = False, target_mesh_name: str = ""):
    """Orchestrates the decompile process: remote UE export -> headless blender .blend generation."""
    project_name = os.path.splitext(os.path.basename(uproject_path))[0]
    
    # 1. Write the export configuration to the shared system temp directory
    temp_dir = tempfile.gettempdir()
    config_path = os.path.join(temp_dir, "palbaker_export_config.json")
    
    config_data = {
        "target_folder": fmodel_dir,
        "ue_path": ue_virtual_path,
        "overwrite_all": overwrite,
        "mod_name": mod_name,
        "target_mesh_name": target_mesh_name
    }
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        return False, f"Failed to write export configuration to system temp: {e}"

    sys.path.append(os.path.join(ue_root, "Engine", "Plugins", "Experimental", "PythonScriptPlugin", "Content", "Python"))
    try:
        import remote_execution  # type: ignore
    except ImportError:
        return False, "Could not locate remote_execution.py."

    remote_exec = remote_execution.RemoteExecution()
    remote_exec.start()
    
    node = None
    timeout = 10.0
    elapsed = 0.0
    while elapsed < timeout:
        node = next((n for n in remote_exec.remote_nodes if n.get('project_name', '').lower() == project_name.lower()), None)
        if node:
            break
        time.sleep(0.5)
        elapsed += 0.5
        
    if not node:
        remote_exec.stop()
        return False, "Unreal Editor is not running. Please open your project first."
        
    remote_exec.open_command_connection(node.get('node_id'))
    
    ue_export_script = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ue_export.py")).replace("\\", "/")
    
    # 2. Execute the untouched Python file using our safe single-line syntax
    cmd = f'f = open(r"{ue_export_script}", encoding="utf-8"); exec(f.read()); f.close()'
    
    print("Injecting decompiler command into Unreal Editor...")
    response = remote_exec.run_command(cmd)
    remote_exec.stop()

    # Teardown: Clean up the system configuration file
    try: os.remove(config_path)
    except OSError: pass

    if response is not None and not response.get('success'):
        return False, f"Export failed inside Unreal: {response.get('result')}"

    # Verify physical file outputs
    fbx_files = glob.glob(os.path.join(fmodel_dir, "*.fbx"))
    if not fbx_files:
        return False, "No FBX assets were exported by Unreal. Decompile aborted."

    reconstructor_script = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "utils", "blender_reconstruct.py"))
    
    for fbx_file in fbx_files:
        base_name = os.path.splitext(os.path.basename(fbx_file))[0]
        blend_file = os.path.join(fmodel_dir, f"{base_name}.blend")

        if not overwrite and os.path.exists(blend_file):
            print(f"Blend file {os.path.basename(blend_file)} already exists. Skipping reconstruction.")
            continue

        print(f"Launching headless Blender to reconstruct {os.path.basename(blend_file)}...")
        cmd_args = [
            blender_path,
            "-b",
            "--python", reconstructor_script,
            "--",
            "--fbx", fbx_file,
            "--output", blend_file
        ]
        
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(
                cmd_args, 
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='replace',
                creationflags=creation_flags
            )
            
            if not os.path.exists(blend_file):
                error_details = result.stdout + "\n" + result.stderr
                return False, f"Blender executed but failed to save {blend_file}. Traceback:\n{error_details}"
        except Exception as e:
            return False, f"Failed to execute Blender process: {e}"

    return True, "Sources successfully reconstructed from compiled project assets!"