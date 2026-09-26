# utils/state.py
import os
import json
import glob

def get_max_mtime(directory, extension):
    """Finds the newest modification time of a specific file type in a directory."""
    if not os.path.exists(directory):
        return 0.0
    
    files = glob.glob(os.path.join(directory, f"*{extension}"))
    if not files:
        return 0.0
    
    return max(os.path.getmtime(f) for f in files)

def get_max_source_mtime(directory):
    """Finds the newest modification time of source files (.blend, .png, .fbx, .json)."""
    if not os.path.exists(directory):
        return 0.0
    
    max_time = 0.0
    source_extensions = ('.blend', '.fbx', '.png', '.json')
    
    for root, dirs, files in os.walk(directory):
        # In-place modify dirs to prune/ignore hidden directories (starting with .)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith(source_extensions) and not file.startswith('.'):
                if file in ["import_config.json", ".palbaker_state.json", "response.txt"]:
                    continue
                file_path = os.path.join(root, file)
                max_time = max(max_time, os.path.getmtime(file_path))
    return max_time

def load_palbaker_state(fmodel_dir: str) -> dict:
    """Safely loads .palbaker_state.json from directory."""
    if not fmodel_dir or not os.path.exists(fmodel_dir):
        return {}
    state_file = os.path.join(fmodel_dir, ".palbaker_state.json")
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def save_palbaker_state(fmodel_dir: str, data: dict):
    """Safely writes .palbaker_state.json to directory."""
    if not fmodel_dir or not os.path.exists(fmodel_dir):
        return
    state_file = os.path.join(fmodel_dir, ".palbaker_state.json")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save state to {state_file}: {e}")

def get_skipped_variants(fmodel_dir: str) -> list[str]:
    """Returns the list of variant names marked as excluded from packaging."""
    state = load_palbaker_state(fmodel_dir)
    return state.get("skipped_variants", [])

def set_variant_pack_state(fmodel_dir: str, variant_name: str, include_in_pak: bool) -> dict:
    """Updates the skipped_variants list in .palbaker_state.json."""
    state = load_palbaker_state(fmodel_dir)
    skipped = set(state.get("skipped_variants", []))
    if include_in_pak:
        skipped.discard(variant_name)
    else:
        skipped.add(variant_name)
    state["skipped_variants"] = sorted(list(skipped))
    save_palbaker_state(fmodel_dir, state)
    return state

def save_push_state(fmodel_dir, ue_dir):
    """Records the timestamp of both UE assets and Source assets immediately after an import without wiping existing state."""
    if not os.path.exists(fmodel_dir):
        return
    
    ue_mtime = get_max_mtime(ue_dir, ".uasset")
    source_mtime = get_max_source_mtime(fmodel_dir)
    
    data = load_palbaker_state(fmodel_dir)
    data["last_ue_mtime"] = ue_mtime
    data["last_source_mtime"] = source_mtime
    save_palbaker_state(fmodel_dir, data)

def is_ue_modified(fmodel_dir, ue_dir):
    """Returns a list of specific UE assets modified since the last Push."""
    if not os.path.exists(fmodel_dir):
        return []
        
    state_file = os.path.join(fmodel_dir, ".palbaker_state.json")
    current_ue_mtime = get_max_mtime(ue_dir, ".uasset")
    current_source_mtime = get_max_source_mtime(fmodel_dir)
    
    if not os.path.exists(state_file):
        if current_ue_mtime > 0.0 or current_source_mtime > 0.0:
            save_push_state(fmodel_dir, ue_dir)
        return []
        
    try:
        with open(state_file, "r") as f:
            data = json.load(f)
            saved_mtime = data.get("last_ue_mtime", 0.0)
            
        modified_files = []
        files = glob.glob(os.path.join(ue_dir, "*.uasset"))
        for file in files:
            if os.path.getmtime(file) > saved_mtime:
                modified_files.append(os.path.basename(file))
                
        return modified_files
    except json.JSONDecodeError as e:
        print(f"State file corrupted ({state_file}): {e}. Assuming un-modified.")
        return []
    except Exception as e:
        print(f"Error reading state file ({state_file}): {e}")
        return []

def is_source_modified(fmodel_dir):
    """Returns True if FModel source files have changed since the last Push."""
    if not os.path.exists(fmodel_dir):
        return False
        
    state_file = os.path.join(fmodel_dir, ".palbaker_state.json")
    if not os.path.exists(state_file):
        return False
        
    try:
        with open(state_file, "r") as f:
            data = json.load(f)
            saved_mtime = data.get("last_source_mtime", 0.0)
            
        current_source_mtime = get_max_source_mtime(fmodel_dir)
        return current_source_mtime > saved_mtime
    except json.JSONDecodeError as e:
        print(f"State file corrupted ({state_file}): {e}. Assuming un-modified.")
        return False
    except Exception as e:
        print(f"Error reading state file ({state_file}): {e}")
        return False