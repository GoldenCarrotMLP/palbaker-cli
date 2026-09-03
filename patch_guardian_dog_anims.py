import os
import sys
import json
import shutil
import subprocess
import re

# =============================================================
# CUSTOM CONFIGURATION
# =============================================================
TARGET_PAL = "DarkScorpion"
TARGET_OVERRIDE_FOLDER = f"{TARGET_PAL}_Override"

NEW_ANIM_FOLDER = "Pal/Content/Pal/Animation/Character/Monster/SexyDarkScorpion"

# The original vanilla skeleton and your new custom skeleton
OLD_SKELETON_PATH = "Pal/Content/Pal/Model/Character/Skeleton/DarkScorpion/SK_DarkScorpion_Skeleton"
NEW_SKELETON_PATH = "Pal/Content/Pal/Model/Character/Skeleton/SexyDarkScorpion/SK_DarkScorpion_Skeleton"

# The custom Skeletal Mesh
NEW_MESH_PATH = "Pal/Content/Pal/Model/Character/Monster/SexyDarkScorpion/SK_DarkScorpion"

# =============================================================
# EXPLICIT GUID OVERRIDES (Fallback if JSON parser fails)
# =============================================================
OLD_SKELETON_GUID = "BF21DEE0-4BCF0A09-60C97DA1-367595A0"
NEW_SKELETON_GUID = "F3642458-43D36EB4-2B398F89-8DDC8313"

OUTPUT_PAK_NAME = f"{TARGET_PAL}_AnimOverride_P.pak"
# =============================================================

# Resolve local repository directories
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(REPO_ROOT, "manager_settings.json")

def log(msg, category="INFO"):
    print(f"[{category}] {msg}", flush=True)

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        log("Error: manager_settings.json not found! Please configure your settings in PalBaker first.", "ERROR")
        sys.exit(1)
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def run_extraction(cue4parse_exe, paks_dir, usmap_path, temp_dir, relative_paths):
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    isolated_dir = os.path.join(paks_dir, ".temp_anim_isolate")
    shutil.rmtree(isolated_dir, ignore_errors=True)
    os.makedirs(isolated_dir, exist_ok=True)

    files_linked = 0
    for root, _, files in os.walk(paks_dir):
        if ".temp" in root:
            continue
        for file in files:
            if file.lower().endswith(".pak"):
                filepath = os.path.join(root, file)
                filename = os.path.basename(filepath)
                try:
                    if hasattr(os, "link"):
                        os.link(filepath, os.path.join(isolated_dir, filename))
                        files_linked += 1
                except Exception:
                    pass

    active_input_dir = isolated_dir if files_linked > 0 else paks_dir
    
    cmd_extract = [
        cue4parse_exe,
        "-i", active_input_dir,
        "-o", temp_dir,
        "-m", usmap_path,
        "-g", "GAME_UE5_1",
        "-f", "raw",
        "-y"
    ]
    for rel_path in relative_paths:
        cmd_extract.extend(["-p", rel_path])

    try:
        subprocess.run(cmd_extract, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
    finally:
        shutil.rmtree(isolated_dir, ignore_errors=True)

def find_skeleton_guid_in_json(json_path: str) -> str:
    if not json_path or not os.path.exists(json_path):
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    def search(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.lower() in ["skeletonguid", "virtualboneguid", "guid"] and isinstance(v, str) and len(v) >= 32:
                    return v
                res = search(v)
                if res: return res
        elif isinstance(node, list):
            for item in node:
                res = search(item)
                if res: return res
        return None
    return search(data)

def mutate_uasset_json(json_path: str, target_pal: str, override_folder: str, new_anim_folder: str, old_skel_path: str, new_skel_path: str, new_mesh_path: str, old_guid: str, new_guid: str, action_data: list):
    with open(json_path, "r", encoding="utf-8") as f:
        json_str = f.read()

    clean_target = target_pal.strip("/")
    clean_override = override_folder.strip("/")
    
    raw_new_anim = new_anim_folder.replace("\\", "/").strip("/")
    v_new_anim = raw_new_anim.replace("Pal/Content", "/Game") if raw_new_anim.startswith("Pal/Content") else f"/Game/{raw_new_anim}"

    raw_old_skel = old_skel_path.replace("\\", "/").strip("/")
    raw_new_skel = new_skel_path.replace("\\", "/").strip("/")
    v_old_skel = raw_old_skel.replace("Pal/Content", "/Game") if raw_old_skel.startswith("Pal/Content") else f"/Game/{raw_old_skel}"
    v_new_skel = raw_new_skel.replace("Pal/Content", "/Game") if raw_new_skel.startswith("Pal/Content") else f"/Game/{raw_new_skel}"
    old_skel_name = os.path.basename(raw_old_skel)
    new_skel_name = os.path.basename(raw_new_skel)

    raw_new_mesh = new_mesh_path.replace("\\", "/").strip("/")
    new_mesh_name = os.path.basename(raw_new_mesh)
    v_new_mesh = raw_new_mesh.replace("Pal/Content", "/Game") if raw_new_mesh.startswith("Pal/Content") else f"/Game/{raw_new_mesh}"

    replacements = {
        # Animations Paths
        f"Pal/Content/Pal/Animation/Character/Monster/{clean_target}": raw_new_anim,
        f"/Game/Pal/Animation/Character/Monster/{clean_target}": v_new_anim,
        
        # BP / ABP / BS Blueprint Paths
        f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{clean_target}": f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{clean_override}",
        f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{clean_target}": f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{clean_override}",
        
        # Skeleton
        raw_old_skel: raw_new_skel,
        v_old_skel: v_new_skel,
        f"Skeleton'{old_skel_name}'": f"Skeleton'{new_skel_name}'",
        f'"{old_skel_name}"': f'"{new_skel_name}"',
        
        # Mesh
        f"Pal/Content/Pal/Model/Character/Monster/{clean_target}/SK_{clean_target}": raw_new_mesh,
        f"/Game/Pal/Model/Character/Monster/{clean_target}/SK_{clean_target}": v_new_mesh,
        f"SkeletalMesh'SK_{clean_target}'": f"SkeletalMesh'{new_mesh_name}'",
        f'"SK_{clean_target}"': f'"{new_mesh_name}"'
    }

    # Inject dynamic Action BP overrides
    for action in action_data:
        old_name = action["old_name"]
        new_name = action["new_name"]
        old_path_core = action["old_path_core"]
        new_path_core = action["new_path_core"]
        
        replacements[f"/Game/{old_path_core}.{old_name}_C"] = f"/Game/{new_path_core}.{new_name}_C"
        replacements[f"/Game/{old_path_core}"] = f"/Game/{new_path_core}"
        replacements[f"Pal/Content/{old_path_core}"] = f"Pal/Content/{new_path_core}"
        replacements[old_path_core] = new_path_core
        
        # Safely replace the class name everywhere it occurs exactly
        json_str = re.sub(rf"(?<![A-Za-z0-9_]){old_name}(?![A-Za-z0-9_])", new_name, json_str)

    if old_guid and new_guid and old_guid != new_guid:
        replacements[old_guid] = new_guid

    log(f"Patching file: {os.path.basename(json_path)}", "PATCH")
    for old, new in replacements.items():
        if old in json_str:
            json_str = json_str.replace(old, new)

    old_bp = f"BP_{clean_target}"
    new_bp = f"BP_{clean_override}"

    # Only mutate the Actor Blueprint Class itself!
    if old_bp in json_str:
        json_str = re.sub(rf"(?<!A){old_bp}", new_bp, json_str)

    try:
        data = json.loads(json_str)
    except Exception as e:
        log(f"Error parsing patched JSON: {e}", "ERROR")
        return

    modified_structs = 0
    imports = data.get("Imports", [])
    for i, imp in enumerate(imports):
        
        if imp.get("ClassName") == "Package" and imp.get("ObjectName") == target_pal:
            if imp.get("Outer") == "PalActorBP":
                imp["ObjectName"] = override_folder
                modified_structs += 1
        
        if imp.get("ObjectName") == f"BP_{clean_target}":
            imp["ObjectName"] = f"BP_{clean_override}"
            modified_structs += 1
                
        if imp.get("ObjectName") == f"SK_{clean_target}":
            imp["ObjectName"] = new_mesh_name
            modified_structs += 1
            
        if imp.get("ObjectName") == old_skel_name:
            imp["ObjectName"] = new_skel_name
            modified_structs += 1

    if modified_structs > 0:
        log(f"  -> Applied {modified_structs} structural table corrections.\n", "PATCH")
    else:
        log("\n", "PATCH")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def main():
    log("=== Deep Animation & Action Redirector ===")
    settings = load_settings()

    palworld_exe = settings.get("palworld_exe", "")
    ue_root = settings.get("ue_root", "")

    if not palworld_exe or not ue_root:
        log("Error: Missing required paths in settings. Please run PalBaker and configure your paths.", "ERROR")
        sys.exit(1)

    paks_dir = ""
    if "binaries" in palworld_exe.lower():
        paks_dir = os.path.normpath(os.path.join(os.path.dirname(palworld_exe), "..", "..", "Content", "Paks"))
    else:
        paks_dir = os.path.normpath(os.path.join(os.path.dirname(palworld_exe), "Pal", "Content", "Paks"))

    unrealpak_exe = os.path.normpath(os.path.join(ue_root, "Engine", "Binaries", "Win64", "UnrealPak.exe"))
    uasset_gui_exe = os.path.normpath(os.path.join(REPO_ROOT, "deps", "UAssetGUI.exe"))
    cue4parse_exe = os.path.normpath(os.path.join(REPO_ROOT, "deps", "cue4parse.exe"))
    usmap_path = os.path.normpath(os.path.join(REPO_ROOT, "deps", "Mappings.usmap"))

    temp_dir = os.path.join(REPO_ROOT, "temp_anim_patch")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    # Pass 1: Extract Main BP
    log(f"Extracting base {TARGET_PAL} Actor Blueprint and AnimBlueprints...")
    bp_path_rel = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{TARGET_PAL}/BP_{TARGET_PAL}.uasset"
    bp_exp_path_rel = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{TARGET_PAL}/BP_{TARGET_PAL}.uexp"
    abp_pattern_rel = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{TARGET_PAL}/ABP_{TARGET_PAL}*"
    
    run_extraction(cue4parse_exe, paks_dir, usmap_path, temp_dir, [bp_path_rel, bp_exp_path_rel, abp_pattern_rel])

    extracted_bp = os.path.join(temp_dir, bp_path_rel)
    if not os.path.exists(extracted_bp):
        log("Extraction failed. BP uasset not found on disk.", "ERROR")
        sys.exit(1)

    log("Decompiling Actor Blueprint to search for Linked Actions...")
    temp_json = os.path.join(temp_dir, "blueprint.json")
    subprocess.run([uasset_gui_exe, "tojson", extracted_bp, temp_json, "VER_UE5_1"], check=True, creationflags=creation_flags)

    with open(temp_json, "r", encoding="utf-8") as f:
        bp_content = f.read()

    # Phase 2: Harvest Unique Actions
    # Look for any reference to a BP_Action that belongs to the Target Pal's folder or name
    action_pattern = re.compile(rf'(Pal/Blueprint/Action/[\w/]*{TARGET_PAL}[\w/]*/(BP_Action_[a-zA-Z0-9_]+))', re.IGNORECASE)
    discovered_actions = sorted(list(set(action_pattern.findall(bp_content))))
    
    action_json_data = []
    action_extraction_queue = []
    
    for path_core, name in discovered_actions:
        action_extraction_queue.append(f"Pal/Content/{path_core}.uasset")
        action_extraction_queue.append(f"Pal/Content/{path_core}.uexp")
        
    if action_extraction_queue:
        log(f"Discovered {len(discovered_actions)} Unique Actions: {[n for _, n in discovered_actions]}")
        run_extraction(cue4parse_exe, paks_dir, usmap_path, temp_dir, action_extraction_queue)
        
        # Decompile Actions
        for path_core, name in discovered_actions:
            action_uasset = os.path.join(temp_dir, f"Pal/Content/{path_core}.uasset")
            if os.path.exists(action_uasset):
                action_json = action_uasset.replace(".uasset", ".json")
                subprocess.run([uasset_gui_exe, "tojson", action_uasset, action_json, "VER_UE5_1"], check=True, creationflags=creation_flags)
                
                new_path_core = path_core.replace(TARGET_PAL, TARGET_OVERRIDE_FOLDER)
                new_name = name.replace(TARGET_PAL, TARGET_OVERRIDE_FOLDER)
                new_json_path = os.path.join(os.path.dirname(action_json), f"{new_name}.json")
                os.rename(action_json, new_json_path)
                
                action_json_data.append({
                    "json_path": new_json_path,
                    "old_path_core": path_core,
                    "new_path_core": new_path_core,
                    "old_name": name,
                    "new_name": new_name,
                    "new_rel_dir": os.path.dirname(new_path_core) # Correctly strips Pal/Content/
                })
                os.remove(action_uasset)
                try: os.remove(action_uasset.replace(".uasset", ".uexp"))
                except: pass
            else:
                log(f"Warning: Extracted action {name} not found at {action_uasset}", "WARNING")

    # Phase 3: Harvest Montages & BlendSpaces
    combined_content = bp_content
    for action in action_json_data:
        with open(action["json_path"], "r", encoding="utf-8") as f:
            combined_content += "\n" + f.read()

    blendspace_pattern = re.compile(rf'PalActorBP/{TARGET_PAL}/(BS_[a-zA-Z0-9_]+)', re.IGNORECASE)
    discovered_blendspaces = sorted(list(set(blendspace_pattern.findall(combined_content))))

    montage_pattern = re.compile(rf'Animation/Character/Monster/{TARGET_PAL}/(AM_[a-zA-Z0-9_]+)', re.IGNORECASE)
    discovered_montages = sorted(list(set(montage_pattern.findall(combined_content))))

    log(f"Discovered {len(discovered_blendspaces)} BlendSpaces.")
    log(f"Discovered {len(discovered_montages)} AnimMontages.")

    extraction_queue = []
    for bs in discovered_blendspaces:
        extraction_queue.append(f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{TARGET_PAL}/{bs}.uasset")
        extraction_queue.append(f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{TARGET_PAL}/{bs}.uexp")

    for am in discovered_montages:
        extraction_queue.append(f"Pal/Content/Pal/Animation/Character/Monster/{TARGET_PAL}/{am}.uasset")
        extraction_queue.append(f"Pal/Content/Pal/Animation/Character/Monster/{TARGET_PAL}/{am}.uexp")

    custom_skel_rel = NEW_SKELETON_PATH + ".uasset"
    vanilla_skel_rel = OLD_SKELETON_PATH + ".uasset"
    extraction_queue.extend([custom_skel_rel, NEW_SKELETON_PATH + ".uexp", vanilla_skel_rel, OLD_SKELETON_PATH + ".uexp"])

    if extraction_queue:
        log("Extracting discovered assets and Skeletons...")
        run_extraction(cue4parse_exe, paks_dir, usmap_path, temp_dir, extraction_queue)

    json_targets = []
    for action in action_json_data:
        json_targets.append(action["json_path"])

    custom_skel_json_path = None
    vanilla_skel_json_path = None

    for root, _, files in os.walk(temp_dir):
        for file in files:
            if file.endswith(".uasset"):
                uasset = os.path.join(root, file)
                base_asset_name = os.path.basename(uasset)
                
                json_path = uasset.replace(".uasset", ".json")
                subprocess.run([uasset_gui_exe, "tojson", uasset, json_path, "VER_UE5_1"], check=True, creationflags=creation_flags)
                
                if base_asset_name == os.path.basename(custom_skel_rel):
                    custom_skel_json_path = json_path
                elif base_asset_name == os.path.basename(vanilla_skel_rel):
                    vanilla_skel_json_path = json_path
                else:
                    json_targets.append(json_path)

                os.remove(uasset)
                try: os.remove(uasset.replace(".uasset", ".uexp"))
                except: pass

    if os.path.exists(temp_json):
        os.remove(temp_json)

    old_skeleton_guid = find_skeleton_guid_in_json(vanilla_skel_json_path) or OLD_SKELETON_GUID
    new_skeleton_guid = find_skeleton_guid_in_json(custom_skel_json_path) or NEW_SKELETON_GUID
    
    if custom_skel_json_path and os.path.exists(custom_skel_json_path): os.remove(custom_skel_json_path)
    if vanilla_skel_json_path and os.path.exists(vanilla_skel_json_path): os.remove(vanilla_skel_json_path)

    for json_path in list(json_targets):
        base_name = os.path.basename(json_path)
        if base_name == f"BP_{TARGET_PAL}.json":
            new_json_path = os.path.join(os.path.dirname(json_path), f"BP_{TARGET_OVERRIDE_FOLDER}.json")
            os.rename(json_path, new_json_path)
            json_targets.remove(json_path)
            json_targets.append(new_json_path)

    log("Redirecting animation, skeleton, mesh paths, and action blueprint references...")
    for json_path in json_targets:
        mutate_uasset_json(json_path, TARGET_PAL, TARGET_OVERRIDE_FOLDER, NEW_ANIM_FOLDER, OLD_SKELETON_PATH, NEW_SKELETON_PATH, NEW_MESH_PATH, old_skeleton_guid, new_skeleton_guid, action_json_data)

    log("Re-assembling and compiling patched JSON files...")
    cooked_root = os.path.join(temp_dir, "Cooked")
    
    for json_path in json_targets:
        filename = os.path.basename(json_path).replace(".json", ".uasset")
        
        action_match = next((x for x in action_json_data if x["new_name"] in filename), None)
        
        if action_match:
            cooked_dest_dir = os.path.join(cooked_root, action_match["new_rel_dir"])
            target_name = filename
        elif filename.startswith("BP_"):
            target_name = f"BP_{TARGET_OVERRIDE_FOLDER}.uasset"
            cooked_dest_dir = os.path.join(cooked_root, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", TARGET_OVERRIDE_FOLDER)
        elif filename.startswith("ABP_") or filename.startswith("BS_"):
            target_name = filename
            cooked_dest_dir = os.path.join(cooked_root, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", TARGET_OVERRIDE_FOLDER)
        elif filename.startswith("AM_"):
            target_name = filename
            rel_anim_path = NEW_ANIM_FOLDER.replace("Pal/Content/", "").replace("Pal/Content", "").strip("/")
            cooked_dest_dir = os.path.join(cooked_root, rel_anim_path)
        else:
            target_name = filename
            cooked_dest_dir = os.path.join(cooked_root, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", TARGET_OVERRIDE_FOLDER)

        os.makedirs(cooked_dest_dir, exist_ok=True)
        dest_uasset = os.path.join(cooked_dest_dir, target_name)

        cmd_compile = [uasset_gui_exe, "fromjson", json_path, dest_uasset]
        
        result = subprocess.run(cmd_compile, capture_output=True, text=True, creationflags=creation_flags)
        if result.returncode != 0:
            log(f"❌ COMPILER ERROR on {filename}!", "ERROR")
            log(result.stdout, "ERROR")
            log(result.stderr, "ERROR")
            sys.exit(1)
        else:
            log(f"  ✓ Successfully compiled: {filename}")

    log("Assembling UnrealPak manifest...")
    response_file = os.path.join(temp_dir, "response.txt")
    
    files_packed = 0
    with open(response_file, "w") as f_resp:
        for root, _, files in os.walk(cooked_root):
            for file in files:
                abs_file = os.path.join(root, file)
                rel_path = os.path.relpath(abs_file, cooked_root)
                pak_target = "../../../Pal/Content/" + rel_path.replace("\\", "/")
                
                f_resp.write(f'"{abs_file.replace(os.sep, "/")}" "{pak_target}"\n')
                files_packed += 1

    output_pak_path = os.path.join(REPO_ROOT, OUTPUT_PAK_NAME)
    log(f"Compiling final game archive: {OUTPUT_PAK_NAME} ({files_packed} assets)...")
    
    cmd_pack = [unrealpak_exe, output_pak_path, f"-Create={response_file.replace(os.sep, '/')}"]
    subprocess.run(cmd_pack, check=True, creationflags=creation_flags)

    shutil.rmtree(temp_dir, ignore_errors=True)
    
    log(f"\n🎉 SUCCESS! New standalone override archive written to:")
    log(f"  -> {output_pak_path} (Size: {os.path.getsize(output_pak_path)} bytes)")
    log(f"  -> Blueprint Class Name: BP_{TARGET_OVERRIDE_FOLDER}_C")
    
    mods_dest_dir = os.path.normpath(os.path.join(paks_dir, "~mods"))
    if os.path.exists(mods_dest_dir):
        shutil.copy2(output_pak_path, os.path.join(mods_dest_dir, OUTPUT_PAK_NAME))
        log(f"  -> Automatically deployed to your game ~mods folder: {mods_dest_dir}")

if __name__ == "__main__":
    main()