# utils/builder/dependency_helper.py
import os
import json
import tempfile
from utils.builder.blacklist_helper import get_packaging_blacklist
from utils.builder.unreal_helper import run_remote_command

def run_dependency_crawler(workspace) -> list[str]:
    """Runs the remote asset dependency crawler in Unreal and returns external package paths."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    blacklist = get_packaging_blacklist(repo_root)

    # 1. Identify starting root packages
    root_packages = [
        f"{workspace.ue_virtual_path}/{workspace.target_mesh_name}",
        f"{workspace.ue_virtual_path}/SK_{workspace.mod_name}",
        f"{workspace.blueprint_virtual_path}/BP_{workspace.mod_name}",
        f"{workspace.skeleton_virtual_path}/{workspace.base_pal}_BP",
        f"{workspace.ue_virtual_path}/{workspace.mod_name}_BP"
    ]

    temp_dir = tempfile.gettempdir()
    cfg_path = os.path.join(temp_dir, "palbaker_crawler_config.json")
    out_path = os.path.join(temp_dir, "palbaker_crawler_result.json")

    # Clean previous results
    if os.path.exists(out_path):
        try: os.remove(out_path)
        except OSError: pass

    cfg_payload = {
        "root_packages": root_packages,
        "blacklist": sorted(list(blacklist)),
        "has_anims": workspace.has_anims
    }

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg_payload, f, indent=4)

    # 2. Execute dependency_crawler.py inside Unreal Editor
    crawler_script = os.path.join(repo_root, "unreal_scripts", "dependency_crawler.py").replace("\\", "/")
    cmd = f'f = open(r"{crawler_script}", encoding="utf-8"); exec(f.read()); f.close()'

    success, msg = run_remote_command(workspace.ue_root, workspace.target_project_name, cmd)
    if not success:
        print(f"[Dependency Crawler Warning] Remote execution failed: {msg}", flush=True)

    # 3. Read output JSON
    discovered = []
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                discovered = json.load(f)
        except Exception as e:
            print(f"[Dependency Crawler Error] Could not read results: {e}", flush=True)

    # Clean up temp config files
    for p in [cfg_path, out_path]:
        if os.path.exists(p):
            try: os.remove(p)
            except OSError: pass

    # Filter out assets that already live inside the mod's own folder (as they are packed by default)
    mod_vpath_lower = workspace.ue_virtual_path.lower()
    external_deps = [p for p in discovered if not p.lower().startswith(mod_vpath_lower)]

    return external_deps