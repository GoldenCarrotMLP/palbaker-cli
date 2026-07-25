import os
import sys
import json
import shutil
import subprocess
import base64
import struct

# =============================================================
# PATH CONFIGURATION & REPO STRUCTURE
# =============================================================
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(REPO_ROOT, "manager_settings.json")

OUTPUT_PAK_NAME = "BP_Glider_AnimOverrides_P.pak"

# Add any additional gliders you want to patch to this list!
GLIDERS = [
    {
        "dir": "Pal/Content/Pal/Blueprint/Equipment/Glider/Eagle",
        "name": "BP_Glider_EagleBase",
        "var_name": "EagleMesh_GEN_VARIABLE",
        "patch_rotation": True  # Only rotate the Eagle
    },
    {
        "dir": "Pal/Content/Pal/Blueprint/Equipment/Glider/FlyingManta",
        "name": "BP_Glider_FlyingMantaBase",
        "var_name": "SK_FlyingManta_GEN_VARIABLE",
        "patch_rotation": False
    },
    {
        "dir": "Pal/Content/Pal/Blueprint/Equipment/Glider",
        "name": "BP_Glider_Item_Base",
        "var_name": "SkeletalMesh_GEN_VARIABLE",
        "patch_rotation": False
    }
]

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
    isolated_dir = os.path.join(paks_dir, ".temp_glider_isolate")
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
    log(f"Linked {files_linked} game paks for extraction processing.")
    
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

def mutate_blueprint_json(json_path: str, target_var_name: str, patch_rotation: bool):
    """Loads, inspects, and patches the target SkeletalMeshComponent variables using a Base64 binary mutator."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    modified = False
    exports = data.get("Exports", [])

    for export in exports:
        if export.get("ObjectName") == target_var_name:
            export_data = export.get("Data")
            
            # Case 1: RawExport (Base64 String) - Native unversioned parsing
            if isinstance(export_data, str):
                try:
                    b_data = bytearray(base64.b64decode(export_data))
                    
                    # 1. MUTATE BOOLEANS
                    target_seq = b'\x02\x01\x01\x01'
                    new_seq    = b'\x02\x00\x00\x00'
                    
                    if target_seq in b_data:
                        b_data = b_data.replace(target_seq, new_seq)
                        log(f"Successfully patched unversioned binary flags (Booleans -> False) for {target_var_name}!")
                        modified = True

                    # 2. MUTATE RELATIVE ROTATION (Pitch, Yaw, Roll as 64-bit doubles) if requested
                    if patch_rotation:
                        orig_rot = struct.pack('<ddd', 0.0, 0.0, -90.0)
                        new_rot  = struct.pack('<ddd', 0.0, 0.0, -90.0)
                        
                        if orig_rot in b_data:
                            b_data = b_data.replace(orig_rot, new_rot)
                            log(f"Successfully patched unversioned RelativeRotation (Roll: -90.0 -> 180.0) for {target_var_name}!")
                            modified = True

                    if modified:
                        export["Data"] = base64.b64encode(b_data).decode('utf-8')
                        
                except Exception as e:
                    log(f"Error during Base64 mutation: {e}", "ERROR")

            # Case 2: NormalExport (Parsed List) - In case UAssetGUI CLI gets updated
            elif isinstance(export_data, list):
                for prop in export_data:
                    if isinstance(prop, dict):
                        prop_name = prop.get("Name")
                        if prop_name in ["bDisablePostProcessBlueprint", "bPauseAnims", "bNoSkeletonUpdate"]:
                            log(f"  * Mutating {prop_name}: {prop.get('Value')} -> False")
                            prop["Value"] = False
                            modified = True
                        elif patch_rotation and prop_name == "RelativeRotation":
                            val = prop.get("Value", {})
                            if val.get("Roll") == -90.0:
                                log(f"  * Mutating RelativeRotation Roll: -90.0 -> 180.0")
                                val["Roll"] = 180.0
                                modified = True
                if modified:
                    log(f"Successfully patched parsed JSON properties for {target_var_name}!")

    if not modified:
        log(f"Warning: Could not locate '{target_var_name}' properties to mutate.", "WARNING")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def main():
    log("=== Standalone Glider Animation & Physics Post-Process Patcher ===")
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

    for tool, name in [
        (unrealpak_exe, "UnrealPak.exe"),
        (uasset_gui_exe, "UAssetGUI.exe"),
        (cue4parse_exe, "cue4parse.exe"),
        (usmap_path, "Mappings.usmap")
    ]:
        if not os.path.exists(tool):
            log(f"Fatal: Required dependency '{name}' is missing at: {tool}", "ERROR")
            sys.exit(1)

    temp_dir = os.path.join(REPO_ROOT, "temp_glider_patch")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    # 1. Gather all extraction paths
    extraction_queue = []
    for glider in GLIDERS:
        extraction_queue.append(f"{glider['dir']}/{glider['name']}.uasset")
        extraction_queue.append(f"{glider['dir']}/{glider['name']}.uexp")

    log(f"Extracting base Blueprint assets for {len(GLIDERS)} gliders...")
    run_extraction(cue4parse_exe, paks_dir, usmap_path, temp_dir, extraction_queue)

    cooked_root = os.path.join(temp_dir, "Cooked")

    # 2. Process each glider sequentially
    for glider in GLIDERS:
        log(f"\n--- Processing {glider['name']} ---")
        
        extracted_uasset = os.path.join(temp_dir, f"{glider['dir']}/{glider['name']}.uasset")
        if not os.path.exists(extracted_uasset):
            log(f"Extraction failed. {glider['name']} uasset not found on disk.", "ERROR")
            continue

        log("Decompiling blueprint asset to JSON...")
        temp_json = os.path.join(temp_dir, f"{glider['name']}.json")
        
        cmd_to_json = [uasset_gui_exe, "tojson", extracted_uasset, temp_json, "VER_UE5_1"]
        subprocess.run(cmd_to_json, check=True, creationflags=creation_flags)

        log("Patching components variables and flags...")
        mutate_blueprint_json(temp_json, glider['var_name'], glider['patch_rotation'])

        log("Compiling patched JSON back to binary .uasset...")
        cooked_dest_dir = os.path.join(cooked_root, os.path.normpath(glider['dir']))
        os.makedirs(cooked_dest_dir, exist_ok=True)
        
        compiled_uasset = os.path.join(cooked_dest_dir, f"{glider['name']}.uasset")
        
        cmd_from_json = [uasset_gui_exe, "fromjson", temp_json, compiled_uasset, "VER_UE5_1"]
        
        result = subprocess.run(cmd_from_json, capture_output=True, text=True, creationflags=creation_flags)
        if result.returncode != 0:
            log(f"❌ COMPILER ERROR on {glider['name']}!", "ERROR")
            log(result.stdout, "ERROR")
            log(result.stderr, "ERROR")
        else:
            log("✓ Successfully compiled back into cooked binary structure.")

    # 3. Assemble and Pack
    log("\nAssembling UnrealPak manifest...")
    response_file = os.path.join(temp_dir, "response.txt")
    
    files_packed = 0
    with open(response_file, "w") as f_resp:
        for root, _, files in os.walk(cooked_root):
            for file in files:
                abs_file = os.path.join(root, file)
                rel_path = os.path.relpath(abs_file, cooked_root)
                pak_target = "../../../" + rel_path.replace("\\", "/")
                
                f_resp.write(f'"{abs_file.replace(os.sep, "/")}" "{pak_target}"\n')
                files_packed += 1

    if files_packed > 0:
        output_pak_path = os.path.join(REPO_ROOT, OUTPUT_PAK_NAME)
        log(f"Compiling final game archive: {OUTPUT_PAK_NAME} ({files_packed} files)...")
        
        cmd_pack = [unrealpak_exe, output_pak_path, f"-Create={response_file.replace(os.sep, '/')}"]
        subprocess.run(cmd_pack, check=True, creationflags=creation_flags)

        log(f"\n🎉 SUCCESS! Unified animation overrides written to:")
        log(f"  -> {output_pak_path} (Size: {os.path.getsize(output_pak_path)} bytes)")
        
        mods_dest_dir = os.path.normpath(os.path.join(paks_dir, "~mods"))
        if os.path.exists(mods_dest_dir):
            shutil.copy2(output_pak_path, os.path.join(mods_dest_dir, OUTPUT_PAK_NAME))
            log(f"  -> Automatically deployed to your game ~mods folder: {mods_dest_dir}")
    else:
        log("No files were successfully processed to pack.", "ERROR")

    shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()