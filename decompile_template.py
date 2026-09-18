import os
import sys
import subprocess
import json

def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    
    uasset_gui = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    input_uasset = os.path.normpath(os.path.join(repo_root, "templates", "AM_Kitsunebi_Cooking.uasset"))
    output_json = os.path.normpath(os.path.join(repo_root, "templates", "Test_Mapped_Output.json"))

    if not os.path.exists(uasset_gui):
        print(f"[-] Error: UAssetGUI.exe not found at: {uasset_gui}")
        sys.exit(1)

    if not os.path.exists(usmap_path):
        print(f"[-] Error: Mappings.usmap not found at: {usmap_path}")
        sys.exit(1)

    # Note the 4th argument here: passing the .usmap directly to the CLI
    cmd = [
        uasset_gui,
        "tojson",
        input_uasset,
        output_json,
        "VER_UE5_1",
        usmap_path
    ]

    print(f"[*] Running UAssetGUI v1.1.1 CLI with Mappings...")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)

    if result.returncode != 0:
        print("[-] CLI Failed:")
        print(result.stderr or result.stdout)
        sys.exit(1)

    if not os.path.exists(output_json):
        print("[-] Error: JSON not generated.")
        sys.exit(1)

    # Verify the output schema
    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    exports = data.get("Exports", [])
    if not exports:
        print("[-] Error: No exports found in generated JSON.")
        sys.exit(1)
        
    export_type = exports[0].get("$type", "")
    
    if "NormalExport" in export_type:
        print("\n[+] SUCCESS! CLI successfully used the .usmap!")
        print("    -> Export generated as 'NormalExport'.")
        print("    -> We can now safely rip out the Base64 byte-patching everywhere! 🎉")
    else:
        print(f"\n[-] FAILED: CLI still output '{export_type}'.")
        print("    UAssetGUI ignored the mapping file from the command line.")

if __name__ == "__main__":
    main()