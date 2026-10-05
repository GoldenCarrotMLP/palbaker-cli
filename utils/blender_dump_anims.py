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
    
    m = re.match(r'^BS_([a-zA-Z]+)_[a-zA-Z0-9]+(?:_(.+))?$', clean)
    if m: clean = f"{m.group(1)}_{m.group(2)}" if m.group(2) else m.group(1)
    elif clean.startswith("BS_"): clean = clean[3:]
    else:
        m = re.match(r'^(?:BP_Action_Unique|BP_UniqueAction)_[a-zA-Z0-9]+?_(.+)$', clean)
        if m: clean = m.group(1)

    prefixes = []
    if mod_name: prefixes.extend([f"AM_{mod_name}_", f"AS_{mod_name}_", f"{mod_name}_"])
    if base_pal: prefixes.extend([f"AM_{base_pal}_", f"AS_{base_pal}_", f"{base_pal}_"])
    prefixes.extend(["AM_", "AS_"])
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

def find_existing_action(target_seq_name: str, raw_name: str, base_seq_name: str, track_name: str, base_pal: str = "", mod_name: str = ""):
    """
    Checks if the animation already exists in Blender's action data 
    under any of its canonical sequence, raw, or clean track names.
    """
    # 1. Exact match on target sequence name (e.g. AS_Emberpup_Eat)
    act = bpy.data.actions.get(target_seq_name)
    if act:
        return act

    # 2. Exact match on raw imported file name (e.g. AS_BlackPuppy_Eat)
    if raw_name:
        act = bpy.data.actions.get(raw_name)
        if act:
            return act

    # 3. Match on base pal sequence name
    if base_seq_name:
        act = bpy.data.actions.get(base_seq_name)
        if act:
            return act

    # 4. Match on clean track name (e.g. Eat)
    if track_name:
        act = bpy.data.actions.get(track_name)
        if act:
            return act

    # 5. Check action names with Blender numerical duplicate suffixes (.001, .002, etc.)
    for candidate in [target_seq_name, raw_name, base_seq_name, track_name]:
        if not candidate: continue
        cand_lower = candidate.lower()
        for act in bpy.data.actions:
            clean_act_name = re.sub(r'\.\d+$', '', act.name)
            if clean_act_name.lower() == cand_lower:
                return act

    # 6. Deep check: match by cleaned track name across all actions
    if track_name:
        track_lower = track_name.lower()
        for act in bpy.data.actions:
            if act.name.startswith(".") or "[action stash]" in act.name.lower():
                continue
            act_track = extract_track_name_simple(act.name, base_pal, mod_name)
            if act_track.lower() == track_lower:
                return act

    return None

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
            with open(cache_path, "r", encoding="utf-8") as f:
                mapping_cache = json.load(f)
        except Exception: pass

    # STRICT FILTER: Only consider files whose basename starts with AS_
    psa_files = [
        os.path.join(r, f) for r, _, fs in os.walk(psa_dir) 
        for f in fs 
        if f.lower().endswith(".psa") and os.path.basename(f).upper().startswith("AS_")
    ]
    imported_count = 0
    existing_track_names = {t.name for t in arm_obj.animation_data.nla_tracks}

    for psa_file in psa_files:
        base_filename = os.path.basename(psa_file)
        if not base_filename.upper().startswith("AS_"):
            continue

        raw_name = os.path.splitext(base_filename)[0]
        track_name = extract_track_name_simple(raw_name, base_pal, mod_name)
        target_seq_name = f"AS_{mod_name}_{track_name}"
        target_montage_name = f"AM_{mod_name}_{track_name}"
        base_seq_name = f"AS_{base_pal}_{track_name}" if base_pal else ""

        # 1. Update sidecar metadata with automatic template duplicate purging
        target_entry = None
        matched_keys = []

        target_seq_lower = target_seq_name.lower()
        raw_name_lower = raw_name.lower()
        base_seq_lower = base_seq_name.lower() if base_seq_name else ""
        track_lower = track_name.lower()

        for k, v in list(anims_dict.items()):
            k_lower = k.lower()
            v_track = v.get("nla_track_name", "").lower() if isinstance(v, dict) else ""
            if k_lower in [target_seq_lower, raw_name_lower, base_seq_lower] or v_track == track_lower:
                if not target_entry:
                    target_entry = v
                matched_keys.append(k)

        # PURGE OLD DUPLICATE / TEMPLATE KEYS FROM SIDECAR
        for old_k in matched_keys:
            if old_k != target_seq_name:
                anims_dict.pop(old_k, None)

        is_rest_anim = bool(re.match(r'^Rest_?\d+$', track_name, re.IGNORECASE) or "rest0" in track_name.lower())

        if not target_entry:
            if is_rest_anim:
                target_entry = {
                    "category": "RandomRest",
                    "enum_key": f"Rest_{track_name}",
                    "display_name": f"Idle/Rest: {track_name}",
                    "sequence_asset": target_seq_name,
                    "montage_asset": target_montage_name,
                    "nla_track_name": track_name,
                    "in_nla": True,
                    "is_modified": False,
                    "notifies": [],
                    "enable_root_motion": False,
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
                    "sequence_asset": target_seq_name,
                    "montage_asset": target_montage_name,
                    "nla_track_name": track_name,
                    "in_nla": True,
                    "is_modified": False,
                    "notifies": [],
                    "enable_root_motion": False
                }
            else:
                target_entry = {
                    "category": "LocomotionSequence" if any(kw in track_name.lower() for kw in ["idle", "walk", "run", "swim"]) else "GeneralMontage",
                    "enum_key": track_name,
                    "display_name": track_name.replace("_", " "),
                    "sequence_asset": target_seq_name,
                    "montage_asset": target_montage_name,
                    "nla_track_name": track_name,
                    "in_nla": True,
                    "is_modified": False,
                    "notifies": [],
                    "enable_root_motion": False
                }
        else:
            target_entry["in_nla"] = True
            target_entry["nla_track_name"] = track_name
            target_entry["sequence_asset"] = target_seq_name
            target_entry["montage_asset"] = target_montage_name

        anims_dict[target_seq_name] = target_entry

        # 2. CHECK IF ANIMATION ACTION ALREADY EXISTS IN BLENDER BY NAME
        existing_action = find_existing_action(target_seq_name, raw_name, base_seq_name, track_name, base_pal, mod_name)

        if existing_action:
            if existing_action.name != target_seq_name and not existing_action.name.startswith("AS_"):
                existing_action.name = target_seq_name

            nla_track = arm_obj.animation_data.nla_tracks.get(track_name)
            if not nla_track:
                nla_track = arm_obj.animation_data.nla_tracks.new()
                nla_track.name = track_name

            has_strip = any(strip.action == existing_action for strip in nla_track.strips)
            if not has_strip:
                start_frame = int(existing_action.frame_range[0])
                nla_track.strips.new(track_name, start_frame, existing_action)

            nla_track.mute = True
            existing_track_names.add(track_name)
            imported_count += 1
            print(f"  • Animation '{target_seq_name}' already exists in Blender. Linked to track '{track_name}'.", flush=True)
            continue

        # 3. ANIMATION NOT FOUND: IMPORT FRESH FROM PSA
        arm_obj.animation_data.action = None
        before_actions = set(bpy.data.actions.keys())

        if not import_single_psa(psa_file): continue

        after_actions = set(bpy.data.actions.keys())
        new_actions = after_actions - before_actions

        new_action = arm_obj.animation_data.action
        if not new_action and new_actions:
            new_action = bpy.data.actions[list(new_actions)[0]]
        if not new_action:
            new_action = bpy.data.actions.get(raw_name)

        if not new_action: continue
        new_action.name = target_seq_name

        nla_track = arm_obj.animation_data.nla_tracks.get(track_name)
        if not nla_track:
            nla_track = arm_obj.animation_data.nla_tracks.new()
            nla_track.name = track_name

        if len(nla_track.strips) == 0:
            nla_track.strips.new(track_name, int(new_action.frame_range[0]), new_action)
        nla_track.mute = True

        existing_track_names.add(track_name)
        imported_count += 1

    # 4. FINAL PURGE: Retarget any stranded template entries left in anims_dict
    if base_pal and mod_name.lower() != base_pal.lower():
        for k in list(anims_dict.keys()):
            if k.lower().startswith(f"as_{base_pal.lower()}_") or k.lower().startswith(f"am_{base_pal.lower()}_"):
                v = anims_dict.pop(k)
                t_name = v.get("nla_track_name") or extract_track_name_simple(k, base_pal, mod_name)
                new_k = f"AS_{mod_name}_{t_name}"
                v["sequence_asset"] = new_k
                v["montage_asset"] = f"AM_{mod_name}_{t_name}"
                if new_k not in anims_dict:
                    anims_dict[new_k] = v

    # 5. RETARGET BLENDSPACES IN SIDECAR
    bs_dict = sidecar_data.get("custom_animations", {}).get("blend_spaces", {})
    if bs_dict and base_pal and mod_name.lower() != base_pal.lower():
        for bs_name, bs_obj in bs_dict.items():
            if base_pal in bs_obj.get("asset_name", ""):
                bs_obj["asset_name"] = bs_obj["asset_name"].replace(base_pal, mod_name)
            for smp in bs_obj.get("samples", []):
                anim_name = smp.get("animation", "")
                if base_pal in anim_name:
                    smp["animation"] = anim_name.replace(base_pal, mod_name)

    arm_obj.animation_data.action = None
    sidecar_data["custom_animations"]["is_active"] = True

    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, indent=4)

    bpy.ops.wm.save_mainfile()
    print(f"[PalBaker Anims] Successfully processed {imported_count} AS_ sequence tracks into {os.path.basename(blend_path)}!", flush=True)
if __name__ == "__main__":
    b_path, p_dir, s_path, b_pal, m_name = parse_args()
    if b_path and p_dir and s_path:
        import_psas_to_nla(b_path, p_dir, s_path, b_pal, m_name)