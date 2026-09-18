import os
import sys
import json
import shutil
import subprocess
import glob

def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    settings_file = os.path.join(repo_root, "manager_settings.json")
    
    report = {
        "environment": {},
        "extraction_test": {},
        "decompilation_test": {},
        "mutation_test": {},
        "recompilation_test": {},
        "cooked_filesystem_audit": {}
    }

    if not os.path.exists(settings_file):
        print(json.dumps({"error": "manager_settings.json not found"}, indent=2))
        return

    with open(settings_file, "r", encoding="utf-8") as f:
        settings = json.load(f)

    uproject = settings.get("uproject", "")
    project_dir = os.path.dirname(uproject) if uproject else ""
    project_name = os.path.splitext(os.path.basename(uproject))[0] if uproject else ""
    fmodel_output = settings.get("fmodel_output", "")

    uasset_gui_exe = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))

    report["environment"] = {
        "repo_root": repo_root,
        "project_dir": project_dir,
        "project_name": project_name,
        "fmodel_output": fmodel_output,
        "uasset_gui_exists": os.path.exists(uasset_gui_exe),
        "usmap_exists": os.path.exists(usmap_path)
    }

    sys.path.append(repo_root)
    from utils.extractor.core import extract_game_files

    temp_dir = os.path.join(repo_root, "temp_diag_test")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    template_pal = "CatMage"
    target_pal = "Katress_big_head"

    # --- Phase 1: Test Extracting a Single Montage ---
    test_am_rel = f"Pal/Content/Pal/Animation/Character/Monster/{template_pal}/AM_{template_pal}_Eat.uasset"
    test_am_uexp = f"Pal/Content/Pal/Animation/Character/Monster/{template_pal}/AM_{template_pal}_Eat.uexp"

    success, msg = extract_game_files(settings, [test_am_rel, test_am_uexp], temp_dir, format_type="raw")
    extracted_am = None
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"am_{template_pal.lower()}_eat.uasset":
                extracted_am = os.path.join(root, f)
                break
        if extracted_am: break

    report["extraction_test"] = {
        "success": success,
        "message": msg,
        "extracted_file": extracted_am,
        "file_exists": os.path.exists(extracted_am) if extracted_am else False
    }

    if not extracted_am or not os.path.exists(extracted_am):
        print(json.dumps(report, indent=2))
        return

    # --- Phase 2: Test Decompilation with Mappings ---
    temp_json = os.path.join(temp_dir, "AM_CatMage_Eat.json")
    decompile_proc = subprocess.run(
        [uasset_gui_exe, "tojson", extracted_am, temp_json, "VER_UE5_1", usmap_path],
        capture_output=True,
        text=True,
        creationflags=flags
    )

    report["decompilation_test"] = {
        "returncode": decompile_proc.returncode,
        "stdout": decompile_proc.stdout.strip(),
        "stderr": decompile_proc.stderr.strip(),
        "json_created": os.path.exists(temp_json),
        "json_size": os.path.getsize(temp_json) if os.path.exists(temp_json) else 0
    }

    if not os.path.exists(temp_json):
        print(json.dumps(report, indent=2))
        return

    # --- Phase 3: Test JSON Mutation & String Patching ---
    with open(temp_json, "r", encoding="utf-8") as f:
        json_str = f.read()

    # Apply the exact patch rules
    patched_str = json_str.replace(f"AM_{template_pal}_", f"AM_{target_pal}_")
    patched_str = patched_str.replace(f"AS_{template_pal}_", f"AS_{target_pal}_")
    patched_str = patched_str.replace(f"/Monster/{template_pal}", f"/Monster/{target_pal}")
    patched_str = patched_str.replace(f"SK_{template_pal}_Skeleton", f"SK_{target_pal}_Skeleton")

    patched_json_path = os.path.join(temp_dir, "AM_Katress_big_head_Eat.json")
    with open(patched_json_path, "w", encoding="utf-8") as f:
        f.write(patched_str)

    report["mutation_test"] = {
        "target_json": patched_json_path,
        "target_json_size": os.path.getsize(patched_json_path)
    }

    # --- Phase 4: Test Recompilation to Saved/Cooked Destination ---
    target_cooked_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Animation", "Character", "Monster", target_pal)
    os.makedirs(target_cooked_dir, exist_ok=True)
    target_uasset_path = os.path.join(target_cooked_dir, f"AM_{target_pal}_Eat.uasset")

    recompile_proc = subprocess.run(
        [uasset_gui_exe, "fromjson", patched_json_path, target_uasset_path],
        capture_output=True,
        text=True,
        creationflags=flags
    )

    report["recompilation_test"] = {
        "target_path": target_uasset_path,
        "returncode": recompile_proc.returncode,
        "stdout": recompile_proc.stdout.strip(),
        "stderr": recompile_proc.stderr.strip(),
        "uasset_created": os.path.exists(target_uasset_path),
        "uasset_size": os.path.getsize(target_uasset_path) if os.path.exists(target_uasset_path) else 0
    }

    # --- Phase 5: Deep Scan of Entire Saved/Cooked Folder ---
    cooked_root = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content")
    discovered_files = {}
    if os.path.exists(cooked_root):
        for root, _, files in os.walk(cooked_root):
            for f in files:
                rel_p = os.path.relpath(os.path.join(root, f), cooked_root).replace("\\", "/")
                # Record matching assets
                for prefix in ["AM_", "AS_", "BS_", "ABP_", "BP_", "SK_", "PA_"]:
                    if prefix in f:
                        discovered_files[rel_p] = os.path.getsize(os.path.join(root, f))
                        break

    report["cooked_filesystem_audit"] = {
        "cooked_root": cooked_root,
        "total_tracked_assets": len(discovered_files),
        "assets_map": discovered_files
    }

    shutil.rmtree(temp_dir, ignore_errors=True)

    # Save to disk and print to STDOUT
    out_report_file = os.path.join(repo_root, "diag_result.json")
    with open(out_report_file, "w", encoding="utf-8") as f_rep:
        json.dump(report, f_rep, indent=2)

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()