# inspect_anims.py
import os
import sys
import json
import re

SETTINGS_FILE = "manager_settings.json"

def main():
    if not os.path.exists(SETTINGS_FILE):
        print("ERROR: manager_settings.json not found.")
        return

    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)

    fmodel_output = settings.get("fmodel_output", "")
    ue_root = settings.get("ue_root", "")
    uproject = settings.get("uproject", "")

    base_pal = "ThunderFluffyBird"
    mod_name = "AnthroThunderFluffyBird"

    print("=" * 70)
    print(f"=== PALBAKER ANIMATION DIAGNOSTIC INSPECTOR: {mod_name} ===")
    print("=" * 70)

    # 1. Inspect Sidecar JSON
    sidecar_path = os.path.normpath(os.path.join(
        fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", base_pal, mod_name, f"{mod_name}_blend.json"
    ))
    if not os.path.exists(sidecar_path):
        sidecar_path = os.path.normpath(os.path.join(
            fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", base_pal, f"{mod_name}_blend.json"
        ))

    if os.path.exists(sidecar_path):
        with open(sidecar_path, "r") as f:
            sidecar = json.load(f)
        anims = sidecar.get("custom_animations", {}).get("anims", {})
        print(f"\n1. SIDECAR STATUS ({os.path.basename(sidecar_path)}):")
        print(f"   - Total mapped entries: {len(anims)}")
        in_nla = [k for k, v in anims.items() if v.get("in_nla")]
        print(f"   - Tracks marked 'in_nla': {len(in_nla)}")
    else:
        print(f"\n1. SIDECAR STATUS: ❌ Sidecar not found at {sidecar_path}")

    # 2. Inspect Exported FBX Takes directly
    fbx_path = os.path.normpath(os.path.join(
        fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", base_pal, mod_name, f"{mod_name}.fbx"
    ))
    if not os.path.exists(fbx_path):
        fbx_path = os.path.normpath(os.path.join(
            fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", base_pal, f"{mod_name}.fbx"
        ))

    print(f"\n2. FBX EXPORT FILE:")
    if os.path.exists(fbx_path):
        size_mb = os.path.getsize(fbx_path) / (1024 * 1024)
        print(f"   - Path: {fbx_path}")
        print(f"   - Size: {size_mb:.2f} MB")

        try:
            with open(fbx_path, "rb") as f:
                fbx_bytes = f.read()

            takes_found = set()
            for m in re.findall(rb'([a-zA-Z0-9_]+)\x00\x01AnimStack', fbx_bytes):
                takes_found.add(m.decode('utf-8', errors='ignore'))
            for m in re.findall(rb'([a-zA-Z0-9_]+)\x00AnimStack', fbx_bytes):
                takes_found.add(m.decode('utf-8', errors='ignore'))
            for m in re.findall(rb'Take:\s*"([a-zA-Z0-9_]+)"', fbx_bytes):
                takes_found.add(m.decode('utf-8', errors='ignore'))

            print(f"   - Baked Animation Takes in FBX: {len(takes_found)}")
            for t in sorted(list(takes_found))[:10]:
                print(f"     -> Take: {t}")
            if len(takes_found) > 10:
                print(f"     -> ... and {len(takes_found) - 10} more.")
        except Exception as e:
            print(f"   - Could not parse FBX takes: {e}")
    else:
        print(f"   ❌ {os.path.basename(fbx_path)} does not exist on disk.")

    # 3. Query Active Unreal Engine Content
    print(f"\n3. UNREAL ENGINE CONTENT QUERY:")
    try:
        sys.path.append(os.path.join(ue_root, "Engine", "Plugins", "Experimental", "PythonScriptPlugin", "Content", "Python"))
        import remote_execution
        remote_exec = remote_execution.RemoteExecution()
        remote_exec.start()
        import time
        time.sleep(1.0)
        project_name = os.path.splitext(os.path.basename(uproject))[0]
        node = next((n for n in remote_exec.remote_nodes if n.get('project_name', '').lower() == project_name.lower()), None)
        
        if node:
            remote_exec.open_command_connection(node.get('node_id'))
            query_script = f"""
import unreal
ar = unreal.AssetRegistryHelpers.get_asset_registry()
path = "/Game/Pal/Animation/Character/Monster/{mod_name}"
assets = ar.get_assets_by_path(path, recursive=True)
print("=== ASSETS IN UNREAL ===")
if assets:
    for a in assets:
        print(f"{{a.asset_class_path.asset_name}} -> {{a.asset_name}}")
else:
    print("NO_ASSETS_FOUND")
"""
            res = remote_exec.run_command(query_script)
            remote_exec.stop()
            if res and res.get('output'):
                for line in res['output']:
                    print("  ", line.get('output', '').strip())
        else:
            print("   ⚠️ Could not connect to Unreal Editor.")
    except Exception as e:
        print(f"   ⚠️ Query failed: {e}")

    print("=" * 70)

if __name__ == "__main__":
    main()