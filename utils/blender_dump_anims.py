# utils/blender_dump_anims.py
import bpy
import os
import sys
import json
import addon_utils
import re

def ensure_addon_active():
    if hasattr(bpy.ops, "psa") or hasattr(bpy.ops.import_scene, "psa"): return True
    for mod in list(addon_utils.modules()):
        if "psk_psa" in mod.__name__:
            try:
                addon_utils.enable(mod.__name__, default_set=False)
                if hasattr(bpy.ops, "psa") or hasattr(bpy.ops.import_scene, "psa"): return True
            except Exception: pass
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        base_ext_dir = os.path.join(appdata, "Blender Foundation", "Blender")
        if os.path.exists(base_ext_dir):
            for ver_folder in os.listdir(base_ext_dir):
                for sub in ["user_default", "system", "blender_org"]:
                    ext_path = os.path.join(base_ext_dir, ver_folder, "extensions", sub)
                    if os.path.exists(ext_path) and ext_path not in sys.path: sys.path.append(ext_path)
    for cand in ["bl_ext.user_default.io_scene_psk_psa", "bl_ext.system.io_scene_psk_psa", "bl_ext.blender_org.io_scene_psk_psa", "io_scene_psk_psa"]:
        try:
            addon_utils.enable(cand, default_set=False)
            if hasattr(bpy.ops, "psa") or hasattr(bpy.ops.import_scene, "psa"): return True
        except Exception: pass
    return hasattr(bpy.ops, "psa") or hasattr(bpy.ops.import_scene, "psa")

def parse_args():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend_path, psa_dir, sidecar_path = None, None, None
    base_pal, mod_name = "", ""
    for i, arg in enumerate(args):
        if arg == "--blend" and i + 1 < len(args): blend_path = args[i + 1]
        elif arg == "--psa-dir" and i + 1 < len(args): psa_dir = args[i + 1]
        elif arg == "--sidecar" and i + 1 < len(args): sidecar_path = args[i + 1]
        elif arg == "--base-pal" and i + 1 < len(args): base_pal = args[i + 1]
        elif arg == "--mod-name" and i + 1 < len(args): mod_name = args[i + 1]
    return blend_path, psa_dir, sidecar_path, base_pal, mod_name

def extract_track_name_simple(filename: str, base_pal: str = "", mod_name: str = "") -> str:
    clean = filename.split("'")[-2] if "'" in filename else filename
    clean = clean.split("/")[-1].split(".")[0]
    m = re.match(r'^(?:AM|AS)_[a-zA-Z0-9]+?_(.+)$', clean)
    if m: clean = m.group(1)
    else:
        m = re.match(r'^BS_([a-zA-Z]+)_[a-zA-Z0-9]+(?:_(.+))?$', clean)
        if m: clean = f"{m.group(1)}_{m.group(2)}" if m.group(2) else m.group(1)
        elif clean.startswith("BS_"): clean = clean[3:]
        else:
            m = re.match(r'^(?:BP_Action_Unique|BP_UniqueAction)_[a-zA-Z0-9]+?_(.+)$', clean)
            if m: clean = m.group(1)

    prefixes = []
    if mod_name: prefixes.extend([f"AM_{mod_name}_", f"AS_{mod_name}_", f"{mod_name}_"])
    if base_pal: prefixes.extend([f"AM_{base_pal}_", f"AS_{base_pal}_", f"{base_pal}_"])
    prefixes.sort(key=len, reverse=True)

    changed = True
    while changed:
        changed = False
        for pfx in prefixes:
            if clean.lower().startswith(pfx.lower()):
                clean = clean[len(pfx):]
                changed = True
                break

    return clean

def import_single_psa(psa_path: str) -> bool:
    if hasattr(bpy.ops, "psa") and hasattr(bpy.ops.psa, "import_file"):
        try: bpy.ops.psa.import_file(filepath=psa_path); return True
        except Exception: pass
    if hasattr(bpy.ops, "import_scene") and hasattr(bpy.ops.import_scene, "psa"):
        try: bpy.ops.import_scene.psa(filepath=psa_path); return True
        except Exception: pass
    try:
        imp = getattr(bpy.ops, "import", None)
        if imp and hasattr(imp, "psa"): imp.psa(filepath=psa_path); return True
    except Exception: pass
    return False

def import_psas_to_nla(blend_path: str, psa_dir: str, sidecar_path: str, base_pal: str = "", mod_name: str = ""):
    if not ensure_addon_active():
        print("[PalBaker Anims] Fatal: Could not activate PSK/PSA importer.", flush=True)
        sys.exit(1)

    arm_obj = bpy.data.objects.get("Armature")
    if not arm_obj or arm_obj.type != 'ARMATURE':
        print("[PalBaker Anims] Error: No Armature found in .blend file.", flush=True)
        sys.exit(1)

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj

    if not arm_obj.animation_data:
        arm_obj.animation_data_create()

    sidecar_data = {}
    if os.path.exists(sidecar_path):
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                sidecar_data = json.load(f)
        except Exception: pass

    anims_dict = sidecar_data.setdefault("custom_animations", {}).setdefault("anims", {})

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(repo_root, "deps", "anim_mapping_cache.json")
    mapping_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f_c:
                mapping_cache = json.load(f_c)
        except Exception: pass

    # Only import AS_ sequence files into Blender (AM_ files are montages and must not be imported as actions)
    psa_files = [
        os.path.join(r, f) for r, _, fs in os.walk(psa_dir) 
        for f in fs 
        if f.lower().endswith(".psa") and not f.startswith("AM_") and not f.startswith("am_")
    ]
    imported_count = 0
    existing_track_names = {t.name for t in arm_obj.animation_data.nla_tracks}

    for psa_file in psa_files:
        filename = os.path.splitext(os.path.basename(psa_file))[0]
        track_name = extract_track_name_simple(filename, base_pal, mod_name)

        # 1. Update sidecar metadata
        target_entry = anims_dict.get(filename)
        if not target_entry:
            # Check for Rest{numbers} pattern
            is_rest_anim = bool(re.match(r'^Rest_?\d+$', track_name, re.IGNORECASE) or "rest0" in track_name.lower())
            
            if is_rest_anim:
                target_entry = {
                    "category": "RandomRest",
                    "enum_key": f"Rest_{track_name}",
                    "display_name": f"Idle/Rest: {track_name}",
                    "sequence_asset": filename if filename.startswith("AS_") else None,
                    "montage_asset": filename if filename.startswith("AM_") else None,
                    "nla_track_name": track_name,
                    "in_nla": True,
                    "is_modified": False,
                    "notifies": [],
                    "rest_props": {
                        "weight": 1.0,
                        "loop_min": 1,
                        "loop_max": 2,
                        "after_idle_time": 2.0
                    }
                }
            elif track_name in mapping_cache:
                meta = mapping_cache[track_name]
                target_entry = {
                    "category": meta.get("category", "GeneralMontage"),
                    "enum_key": meta.get("enum_key", track_name),
                    "display_name": meta.get("display_name", track_name),
                    "sequence_asset": filename if filename.startswith("AS_") else None,
                    "montage_asset": filename if filename.startswith("AM_") else None,
                    "nla_track_name": track_name,
                    "in_nla": True,
                    "is_modified": False,
                    "notifies": []
                }
            else:
                target_entry = {
                    "category": "LocomotionSequence" if filename.startswith("AS_") else "GeneralMontage",
                    "enum_key": track_name,
                    "display_name": track_name.replace("_", " "),
                    "sequence_asset": filename if filename.startswith("AS_") else None,
                    "montage_asset": filename if filename.startswith("AM_") else None,
                    "nla_track_name": track_name,
                    "in_nla": True,
                    "is_modified": False,
                    "notifies": []
                }
            anims_dict[filename] = target_entry
        else:
            target_entry["in_nla"] = True
            target_entry["nla_track_name"] = track_name

        if track_name in existing_track_names:
            imported_count += 1
            continue

        arm_obj.animation_data.action = None
        before_actions = set(bpy.data.actions.keys())

        if not import_single_psa(psa_file): continue

        after_actions = set(bpy.data.actions.keys())
        new_actions = after_actions - before_actions

        new_action = arm_obj.animation_data.action
        if not new_action and new_actions:
            new_action = bpy.data.actions[list(new_actions)[0]]
        if not new_action:
            new_action = bpy.data.actions.get(filename)

        if not new_action: continue
        new_action.name = filename

        nla_track = arm_obj.animation_data.nla_tracks.new()
        nla_track.name = track_name
        nla_track.strips.new(track_name, int(new_action.frame_range[0]), new_action)
        nla_track.mute = True

        existing_track_names.add(track_name)
        imported_count += 1

    arm_obj.animation_data.action = None
    sidecar_data["custom_animations"]["is_active"] = True

    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, indent=4)

    bpy.ops.wm.save_mainfile()
    print(f"[PalBaker Anims] Successfully imported {imported_count} NLA tracks into {os.path.basename(blend_path)}!", flush=True)

if __name__ == "__main__":
    b_path, p_dir, s_path, b_pal, m_name = parse_args()
    if b_path and p_dir and s_path:
        import_psas_to_nla(b_path, p_dir, s_path, b_pal, m_name)