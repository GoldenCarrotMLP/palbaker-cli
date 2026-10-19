# utils/blender_extractor.py
import sys
import os
import json
import re
import bpy

SPECIAL_PARENT_MATERIALS = {
    "m_pal_twinkle": "/Game/Pal/Model/Character/Monster/DreamDemon/M_Pal_Twinkle",
    "m_pal_dream": "/Game/Pal/Model/Character/Monster/DreamDemon/M_Pal_Dream",
    "m_pal_fire": "/Game/Pal/Model/Character/Monster/Kitsunebi/M_Pal_Fire",
    "m_pal_manticore_fire": "/Game/Pal/Model/Character/Monster/Manticore/M_Pal_Manticore_Fire",
    "m_nightlady": "/Game/Pal/Model/Character/Monster/NightLady/M_NightLady",
    "m_pallit_rainbow": "/Game/Pal/Model/Character/Monster/YakushimaMonster001_Rainbow/M_PalLit_Rainbow",
}

current_dir = os.path.abspath(os.path.dirname(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from blender_utils import translator
    from sidecar_helper import load_sidecar, save_sidecar
    from bone_frames import blender_rest_to_ue
except Exception as e:
    import traceback
    print("\n❌ CRITICAL: ImportError inside Blender's python runtime!", flush=True)
    traceback.print_exc()
    sys.exit(1)

def parse_args():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    output_json = "sidecar_blend.json"
    output_fbx = None
    for i, arg in enumerate(args):
        if arg == "--output" and i + 1 < len(args):
            output_json = args[i + 1]
            if not output_json.endswith(".json"):
                for next_arg in args[i+1:]:
                    if next_arg.endswith(".json"):
                        output_json = next_arg
                        break
        elif arg == "--fbx" and i + 1 < len(args):
            output_fbx = args[i + 1]
    return output_json, output_fbx

def resolve_special_parent_material(mat_name: str):
    if not mat_name: return None
    clean = re.sub(r'\.\d+$', '', mat_name.strip()).lower()
    if clean in SPECIAL_PARENT_MATERIALS:
        return SPECIAL_PARENT_MATERIALS[clean]
    if clean.startswith("mi_"):
        alt_m = "m_" + clean[3:]
        if alt_m in SPECIAL_PARENT_MATERIALS:
            return SPECIAL_PARENT_MATERIALS[alt_m]
        alt_direct = clean[1:]
        if alt_direct in SPECIAL_PARENT_MATERIALS:
            return SPECIAL_PARENT_MATERIALS[alt_direct]
    return None

def clean_track_name_simple(name: str, base_pal: str = "", mod_name: str = "") -> str:
    clean = name.split("'")[-2] if "'" in name else name
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
    prefixes.extend(["Armature_", "Anim_Armature_", "AM_", "AS_"])
    prefixes.sort(key=len, reverse=True)

    changed = True
    while changed:
        changed = False
        for pfx in prefixes:
            if clean.lower().startswith(pfx.lower()):
                clean = clean[len(pfx):]
                changed = True
                break

    # Strip donor Pal prefixes if imported from another species (e.g. AS_FireKirin_Tossin_Start -> Tossin_Start)
    m_donor = re.match(r'^(?:AM|AS)_[a-zA-Z0-9]+?_(.+)$', clean)
    if m_donor:
        clean = m_donor.group(1)

    return clean

def find_action_in_blender(track_name: str, seq_asset: str = "", base_pal: str = "", mod_name: str = ""):
    """Finds an Action object in bpy.data.actions strictly matching names beginning with AS_."""
    if not track_name and not seq_asset:
        return None

    # Only look for candidate action names that begin with AS_
    candidates = [c for c in [seq_asset, f"AS_{mod_name}_{track_name}", f"AS_{base_pal}_{track_name}"] if c and c.upper().startswith("AS_")]
    for c in candidates:
        act = bpy.data.actions.get(c)
        if act and act.name.upper().startswith("AS_"):
            return act

    cand_lowers = [c.lower() for c in candidates]
    for act in bpy.data.actions:
        if not act.name.upper().startswith("AS_"):
            continue
        clean_name = re.sub(r'\.\d+$', '', act.name)
        if clean_name.lower() in cand_lowers or act.name.lower() in cand_lowers:
            return act

    track_lower = track_name.lower()
    for act in bpy.data.actions:
        if act.name.startswith(".") or "[action stash]" in act.name.lower() or not act.name.upper().startswith("AS_"):
            continue
        if clean_track_name_simple(act.name, base_pal, mod_name).lower() == track_lower:
            return act
        if act.name.lower().endswith(f"_{track_lower}"):
            return act

    return None

def is_action_empty(act) -> bool:
    """Version-safe checker that works across Blender 3.x, 4.x, and 5.x Slotted Actions."""
    if not act:
        return True
    if hasattr(act, "is_empty"):
        try:
            if act.is_empty:
                return True
        except Exception:
            pass
    # Blender < 5.0 Legacy Action API
    if hasattr(act, "fcurves"):
        try:
            return len(act.fcurves) == 0
        except Exception:
            pass
    # Blender 5.0+ Slotted / Layered Action API
    if hasattr(act, "layers"):
        try:
            has_curves = False
            for layer in getattr(act, "layers", []):
                for strip in getattr(layer, "strips", []):
                    for cb in getattr(strip, "channelbags", []):
                        if hasattr(cb, "fcurves") and len(cb.fcurves) > 0:
                            has_curves = True
                            break
            if not has_curves and hasattr(act, "slots") and len(act.slots) == 0:
                return True
        except Exception:
            pass
    return False

def harvest_nla_animations(arm_obj, mod_name: str, existing_sidecar_data: dict, base_pal: str = "") -> dict | None:
    existing_custom = existing_sidecar_data.get("custom_animations", {})
    was_active = existing_custom.get("is_active", False)

    # Fallback search if Armature object is named differently
    if not arm_obj or arm_obj.type != 'ARMATURE':
        arm_obj = next((obj for obj in bpy.data.objects if obj.type == 'ARMATURE'), None)

    # 0. Synchronize all standalone and active actions into muted NLA tracks so nothing gets orphaned
    tracks_modified = False
    if arm_obj:
        if not arm_obj.animation_data:
            arm_obj.animation_data_create()

        # If an active action is currently assigned on the armature, stash it to an NLA track ONLY if it starts with AS_
        if arm_obj.animation_data.action:
            active_act = arm_obj.animation_data.action
            if (
                not active_act.name.startswith(".")
                and "[action stash]" not in active_act.name.lower()
                and active_act.name.upper().startswith("AS_")
            ):
                act_track = clean_track_name_simple(active_act.name, base_pal, mod_name)
                if act_track:
                    nla_track = arm_obj.animation_data.nla_tracks.get(act_track)
                    if not nla_track:
                        nla_track = arm_obj.animation_data.nla_tracks.new()
                        nla_track.name = act_track
                        tracks_modified = True
                    act_strip = next((s for s in nla_track.strips if s.action == active_act), None)
                    if not act_strip:
                        for old_strip in list(nla_track.strips):
                            nla_track.strips.remove(old_strip)
                        start_f = int(round(active_act.frame_range[0]))
                        try:
                            nla_track.strips.new(act_track, start_f, active_act)
                            tracks_modified = True
                        except Exception as e:
                            print(f"[PalBaker Extractor] Warning creating NLA strip for active action {act_track}: {e}", flush=True)
                    nla_track.mute = True

        # Check all actions in bpy.data.actions and ensure they have an NLA track (STRICTLY ONLY actions starting with AS_)
        for act in bpy.data.actions:
            if (
                not act
                or act.name.startswith(".")
                or "[action stash]" in act.name.lower()
                or not act.name.upper().startswith("AS_")
            ):
                continue
            if is_action_empty(act):
                continue

            clean_t = clean_track_name_simple(act.name, base_pal, mod_name)
            if not clean_t:
                continue

            nla_track = None
            for t in arm_obj.animation_data.nla_tracks:
                if t.name == clean_t or clean_track_name_simple(t.name, base_pal, mod_name).lower() == clean_t.lower():
                    nla_track = t
                    break
                if any(strip.action == act for strip in t.strips):
                    nla_track = t
                    break

            if not nla_track:
                try:
                    nla_track = arm_obj.animation_data.nla_tracks.new()
                    nla_track.name = clean_t
                    tracks_modified = True
                except Exception:
                    pass

            if nla_track:
                act_strip = next((s for s in nla_track.strips if s.action == act), None)
                if not act_strip:
                    try:
                        for old_strip in list(nla_track.strips):
                            nla_track.strips.remove(old_strip)
                        start_f = int(round(act.frame_range[0]))
                        nla_track.strips.new(clean_t, start_f, act)
                        tracks_modified = True
                    except Exception as e:
                        print(f"[PalBaker Extractor] Warning creating NLA strip for {clean_t}: {e}", flush=True)
                nla_track.mute = True

        # Unassign active action so NLA evaluation runs cleanly
        arm_obj.animation_data.action = None

        if tracks_modified and bpy.data.filepath and os.path.exists(bpy.data.filepath):
            try:
                bpy.ops.wm.save_mainfile()
                print(f"[PalBaker Extractor] Synchronized new NLA tracks into {os.path.basename(bpy.data.filepath)}.", flush=True)
            except Exception:
                pass

    # Filter out Blender internal stash / dummy tracks AND any rogue AM_ tracks
    valid_tracks = []
    if arm_obj and arm_obj.animation_data:
        for t in arm_obj.animation_data.nla_tracks:
            t_name = t.name.strip()
            if not t_name or t_name.startswith(".") or "[action stash]" in t_name.lower():
                continue
            if t_name.upper().startswith("AM_"):
                print(f"[PalBaker Extractor] Skipping non-sequence track in NLA: '{t_name}'", flush=True)
                continue
            valid_tracks.append(t)

    if not valid_tracks and not existing_custom.get("anims") and len(bpy.data.actions) == 0:
        return {
            "is_active": False,
            "anims": {},
            "blend_spaces": {}
        }

    if not was_active:
        return {
            "is_active": False,
            "anims": existing_custom.get("anims", {}),
            "blend_spaces": existing_custom.get("blend_spaces", {})
        }

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(repo_root, "deps", "anim_mapping_cache.json")
    mapping_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f_c:
                mapping_cache = json.load(f_c)
        except Exception:
            pass

    existing_anims = existing_custom.get("anims", {})
    existing_blend_spaces = existing_custom.get("blend_spaces", {})

    new_anims = {}
    blend_spaces = dict(existing_blend_spaces)

    print(f"[PalBaker Extractor] Scanning {len(valid_tracks)} valid AS_ sequence tracks on Armature...", flush=True)

    for track in valid_tracks:
        raw_track_name = track.name.strip()
        clean_track = clean_track_name_simple(raw_track_name, base_pal, mod_name)
        
        default_sequence_asset = f"AS_{mod_name}_{clean_track}"
        montage_asset = f"AM_{mod_name}_{clean_track}"
        asset_key = default_sequence_asset

        prev_entry = (
            existing_anims.get(default_sequence_asset) or 
            existing_anims.get(montage_asset) or 
            existing_anims.get(clean_track)
        )
        if not prev_entry:
            for k, v in existing_anims.items():
                if isinstance(v, dict):
                    v_track = (v.get("nla_track_name") or "").lower()
                    v_seq = (v.get("sequence_asset") or "").lower()
                    v_mont = (v.get("montage_asset") or "").lower()
                    if clean_track.lower() in [v_track, v_seq, v_mont] or k.lower() == clean_track.lower():
                        prev_entry = v
                        break
        prev_entry = prev_entry or {}

        saved_notifies = prev_entry.get("notifies", [])
        saved_seq_notifies = prev_entry.get("sequence_notifies", [n for n in saved_notifies if n.get("Source") == "sequence"])
        saved_montage_notifies = prev_entry.get("montage_notifies", [n for n in saved_notifies if n.get("Source") == "montage"])
        saved_rest_props = prev_entry.get("rest_props")
        saved_sequence = prev_entry.get("sequence_asset")
        final_sequence_asset = saved_sequence if (saved_sequence and saved_sequence.strip()) else default_sequence_asset
        saved_is_modified = prev_entry.get("is_modified", False)
        saved_root_motion = prev_entry.get("enable_root_motion", False)

        # -------------------------------------------------------------
        # EXACT BLENDER KEYFRAME DURATION EXTRACTION
        # -------------------------------------------------------------
        track_duration = 0.0
        track_frames = 0
        scene_fps = bpy.context.scene.render.fps / (bpy.context.scene.render.fps_base or 1.0) or 30.0

        target_act = None
        if track.strips:
            strip = track.strips[0]
            target_act = strip.action
            if not target_act:
                track_frames = max(1, int(round(strip.frame_end - strip.frame_start)))
                track_duration = round(float(track_frames / scene_fps), 4)

        if not target_act:
            target_act = find_action_in_blender(clean_track, default_sequence_asset, base_pal, mod_name)

        if target_act:
            f_start = target_act.frame_range[0]
            f_end = target_act.frame_range[1]
            track_frames = max(1, int(round(f_end - f_start)))
            track_duration = round(float(track_frames / scene_fps), 4)

        # Fallback to existing saved values if action cannot be measured
        final_duration = track_duration if track_duration > 0.0 else float(prev_entry.get("duration", 0.0) or prev_entry.get("required_duration", 0.0))
        final_frames = track_frames if track_frames > 0 else int(prev_entry.get("frame_count", 0) or prev_entry.get("required_frames", 0))

        # Preserve user-assigned category, enum_key, display_name if already set
        category = prev_entry.get("category")
        enum_key = prev_entry.get("enum_key")
        display_name = prev_entry.get("display_name")
        action_bp = prev_entry.get("action_bp")

        if not category or not enum_key:
            # 1. Pattern: Random Rests
            if re.match(r'^Rest_?\d+$', clean_track, re.IGNORECASE) or "rest0" in clean_track.lower():
                category = "RandomRest"
                enum_key = f"Rest_{clean_track}"
                display_name = f"Idle/Rest: {clean_track}"
            # 2. Pattern: BlendSpace Samples
            elif clean_track.lower() in ["idle", "walk", "run", "idle_swim", "transport", "move", "swim"]:
                category = "BlendSpaceSample"
                enum_key = f"BS_Move_{clean_track}"
                display_name = f"BlendSpace: {clean_track}"
            # 3. Pattern: Canonical Map Lookup
            elif clean_track in mapping_cache:
                meta = mapping_cache[clean_track]
                category = meta.get("category", "GeneralMontage")
                enum_key = meta.get("enum_key", f"EPalGeneralMontageType::{clean_track}")
                display_name = meta.get("display_name", f"Montage: {clean_track}")
            # 4. Pattern: Unique Attack Waza Skills (includes tossin/charge/tackle)
            elif any(kw in clean_track.lower() for kw in ["unique", "skill", "attack", "waza", "machete", "tackle", "punch", "kick", "tossin", "charge", "dash", "bite", "strike"]):
                category = "UniqueAttack"
                enum_key = f"EPalWazaID::Unique_{mod_name}_{clean_track}"
                display_name = f"Unique: {clean_track.replace('_', ' ')}"
            # 5. Fallback: General Montage
            else:
                category = "GeneralMontage"
                enum_key = f"EPalGeneralMontageType::{clean_track}"
                display_name = f"Montage: {clean_track.replace('_', ' ')}"

        entry_data = {
            "category": category,
            "enum_key": enum_key,
            "display_name": display_name or clean_track.replace('_', ' '),
            "montage_asset": prev_entry.get("montage_asset") or montage_asset,
            "sequence_asset": final_sequence_asset,
            "nla_track_name": clean_track,
            "in_nla": True,
            "is_modified": saved_is_modified,
            "notifies": saved_notifies,
            "sequence_notifies": saved_seq_notifies,
            "montage_notifies": saved_montage_notifies,
            "enable_root_motion": saved_root_motion,
            "duration": final_duration,
            "frame_count": final_frames
        }

        if category == "RandomRest":
            entry_data["rest_props"] = saved_rest_props or {
                "weight": 1.0, "loop_min": 1, "loop_max": 2, "after_idle_time": 2.0
            }
        elif category == "UniqueAttack":
            entry_data["action_bp"] = action_bp or f"BP_Action_Unique_{mod_name}_{clean_track}"
        elif category == "BlendSpaceSample":
            entry_data["montage_asset"] = None
            if "Move" not in blend_spaces:
                blend_spaces["Move"] = {
                    "enum_key": "EPalGeneralBlendSpaceType::GeneralMove",
                    "asset_name": f"BS_Move_{mod_name}",
                    "axis_name": "Speed",
                    "max_speed": 1000.0,
                    "samples": []
                }
            existing_sample = next((s for s in blend_spaces["Move"]["samples"] if s["clean_name"] == clean_track), None)
            if not existing_sample:
                default_speed = 0.0 if clean_track.lower() == "idle" else (500.0 if clean_track.lower() == "walk" else 1000.0)
                blend_spaces["Move"]["samples"].append({
                    "animation": final_sequence_asset,
                    "clean_name": clean_track,
                    "speed": default_speed,
                    "rate_scale": 1.0,
                    "in_nla": True
                })
                blend_spaces["Move"]["samples"].sort(key=lambda x: x["speed"])
            else:
                existing_sample["in_nla"] = True
                existing_sample["animation"] = final_sequence_asset

        new_anims[asset_key] = entry_data

    # PRESERVE USER-MODIFIED ENTRIES & HARVEST ANY UNMAPPED BLENDER ACTIONS
    for old_k, old_v in existing_anims.items():
        if not isinstance(old_v, dict):
            continue
        old_track = old_v.get("nla_track_name") or clean_track_name_simple(old_k, base_pal, mod_name)
        as_key = f"AS_{mod_name}_{old_track}" if old_track else old_k
        if as_key not in new_anims and old_k not in new_anims:
            preserved = dict(old_v)
            
            # Resolve duration from any matching Blender action (whether pushed to NLA or not)
            matched_act = find_action_in_blender(old_track, old_v.get("sequence_asset", as_key), base_pal, mod_name)
            if matched_act:
                scene_fps = bpy.context.scene.render.fps / (bpy.context.scene.render.fps_base or 1.0) or 30.0
                f_start = matched_act.frame_range[0]
                f_end = matched_act.frame_range[1]
                act_frames = max(1, int(round(f_end - f_start)))
                act_dur = round(float(act_frames / scene_fps), 4)
                preserved["duration"] = act_dur
                preserved["frame_count"] = act_frames
                preserved["in_nla"] = True
                print(f"[PalBaker Extractor] Resolved duration from Blender action '{matched_act.name}' for '{as_key}': {act_dur}s ({act_frames} frames)", flush=True)
            else:
                preserved["in_nla"] = False
                if not preserved.get("duration") and preserved.get("required_duration"):
                    preserved["duration"] = float(preserved["required_duration"])
                    preserved["frame_count"] = int(preserved.get("required_frames", round(preserved["duration"] * 30)))

            new_anims[as_key] = preserved

    # HARVEST ANY REMAINING ACTIONS IN BLENDER (STRICTLY ONLY actions starting with AS_)
    scene_fps = bpy.context.scene.render.fps / (bpy.context.scene.render.fps_base or 1.0) or 30.0
    for act in bpy.data.actions:
        if (
            not act
            or act.name.startswith(".")
            or "[action stash]" in act.name.lower()
            or not act.name.upper().startswith("AS_")
        ):
            continue
        if is_action_empty(act):
            continue
        clean_t = clean_track_name_simple(act.name, base_pal, mod_name)
        as_key = f"AS_{mod_name}_{clean_t}"
        if as_key not in new_anims and clean_t not in [v.get("nla_track_name") for v in new_anims.values() if isinstance(v, dict)]:
            f_start = act.frame_range[0]
            f_end = act.frame_range[1]
            act_frames = max(1, int(round(f_end - f_start)))
            act_dur = round(float(act_frames / scene_fps), 4)
            new_anims[as_key] = {
                "category": "GeneralMontage",
                "enum_key": f"EPalGeneralMontageType::{clean_t}",
                "display_name": f"Montage: {clean_t.replace('_', ' ')}",
                "montage_asset": f"AM_{mod_name}_{clean_t}",
                "sequence_asset": as_key,
                "nla_track_name": clean_t,
                "in_nla": True,
                "is_modified": True,
                "notifies": [],
                "sequence_notifies": [],
                "montage_notifies": [],
                "enable_root_motion": False,
                "duration": act_dur,
                "frame_count": act_frames
            }
            print(f"[PalBaker Extractor] Discovered standalone Blender action '{act.name}' -> added '{as_key}' ({act_dur}s)", flush=True)

    has_valid_tracks = len(new_anims) > 0
    final_is_active = was_active and has_valid_tracks

    return {
        "is_active": final_is_active,
        "anims": new_anims,
        "blend_spaces": blend_spaces
    }
    
def extract_metadata(output_path: str, fbx_path: str = None):
    print(f"\n[PalBaker Extractor] Starting metadata extraction for {os.path.basename(output_path)}...", flush=True)
    working_dir = os.path.dirname(output_path)
    base_name = os.path.splitext(os.path.basename(output_path))[0].replace("_blend", "")
    
    # 1. Base bones and transforms
    bones_info = translator.get_pose_bones_info("Armature")
    all_bones = [b["bone_name"] for b in bones_info]
    
    jiggle_bones = []
    offset_bones = []

    for bone in bones_info:
        if bone["is_physics"]:
            jiggle_bones.append({"bone_name": bone["bone_name"], **bone["physics_config"]})
        if bone["transform_data"]:
            offset_bones.append({"bone_name": bone["bone_name"], **bone["transform_data"]})

    # 2. Harvest Constraints from Pose Bones
    arm_obj = bpy.data.objects.get("Armature")
    copy_bones = []
    lookat_bones = []

    if arm_obj and arm_obj.type == 'ARMATURE' and arm_obj.pose:
        copy_map = {}
        for p_bone in arm_obj.pose.bones:
            target_name = p_bone.name.replace('.', '_')
            for c in p_bone.constraints:
                if getattr(c, "mute", False): continue

                if c.type in ['COPY_LOCATION', 'COPY_ROTATION', 'COPY_SCALE']:
                    source_subtarget = getattr(c, "subtarget", "").strip()
                    if not source_subtarget or (c.target and c.target != arm_obj): continue
                    source_name = source_subtarget.replace('.', '_')
                    key = (target_name, source_name)
                    if key not in copy_map:
                        copy_map[key] = {
                            "target_bone": target_name, "source_bone": source_name,
                            "copy_translation": False, "copy_rotation": False, "copy_scale": False,
                            "alpha": float(getattr(c, "influence", 1.0))
                        }
                    if c.type == 'COPY_LOCATION': copy_map[key]["copy_translation"] = True
                    elif c.type == 'COPY_ROTATION': copy_map[key]["copy_rotation"] = True
                    elif c.type == 'COPY_SCALE': copy_map[key]["copy_scale"] = True

                elif c.type in ['DAMPED_TRACK', 'TRACK_TO']:
                    source_subtarget = getattr(c, "subtarget", "").strip()
                    if source_subtarget and (not c.target or c.target == arm_obj):
                        source_name = source_subtarget.replace('.', '_')
                        lookat_bones.append({
                            "bone_name": target_name,
                            "target_bone": source_name,
                            "clamp": 50.0,
                            "alpha": float(getattr(c, "influence", 1.0)),
                            "look_at_axis": {"X": 0.0, "Y": -1.0, "Z": 0.0},
                            "look_up_axis": {"X": 1.0, "Y": 0.0, "Z": 0.0}
                        })

        copy_bones = list(copy_map.values())

    # 2b. Rest frames in UE convention, used to carry template bone-local values (LookAt axes, sockets)
    # onto this rig when its bones are oriented differently (see utils/bone_frames.py).
    bone_rest_ue = {}
    if arm_obj and arm_obj.type == 'ARMATURE':
        world = arm_obj.matrix_world
        for bone in arm_obj.data.bones:
            m = world @ bone.matrix_local
            rot = m.to_3x3().normalized()
            bone_rest_ue[bone.name] = blender_rest_to_ue(
                tuple(tuple(rot[i][j] for j in range(3)) for i in range(3)), tuple(m.translation)
            )

    # 3. Material Harvesting
    slots_in_order = translator.get_skeletal_mesh_material_slots()
    materials_compile = {}

    for mat_name in slots_in_order:
        k_lower = mat_name.lower()
        if "dots stroke" in k_lower or mat_name.startswith("."): continue
        extracted_textures = translator.get_material_textures(mat_name)
        special_parent = resolve_special_parent_material(mat_name)
        if special_parent:
            parent_class = special_parent
        else:
            parent_class = "MI_PalLit_CharacterEyeBase"
            has_complex = any(k in extracted_textures for k in ["Normal Map", "MetallicRoughnessOcclusionSpecularTexture", "Emissive Texture"])
            if has_complex or "body" in k_lower: parent_class = "MI_PalLit_CharacterBodyBase"
            elif "hair" in k_lower: parent_class = "MI_PalLit_CharacterHairBase"
            
        materials_compile[mat_name] = { "parent_class": parent_class, "textures": extracted_textures }

    # 4. Load Existing Sidecar for Merging
    existing_data = load_sidecar(output_path)
    old_materials = existing_data.get("materials", {})
    merged_materials = {}
    STANDARD_BASES = {"MI_PalLit_CharacterBodyBase", "MI_PalLit_CharacterEyeBase", "MI_PalLit_CharacterHairBase"}

    for k, v in materials_compile.items():
        if k in old_materials:
            old_val = old_materials[k]
            textures = v.get("textures", {}) or old_val.get("textures", {})
            parent_class = old_val.get("parent_class", v.get("parent_class"))
            if parent_class not in STANDARD_BASES:
                parent_class = old_val.get("parent_class")
            merged_entry = { "parent_class": parent_class, "textures": textures }
            if "baseline_settings" in old_val:
                merged_entry["baseline_settings"] = old_val["baseline_settings"]
            merged_materials[k] = merged_entry
        else:
            merged_materials[k] = v

    # 5. Protected Per-Bone Delta Merging for ABP Nodes
    merged_jiggle_bones = []
    merged_lookat_bones = []
    merged_copy_bones = []
    merged_offset_bones = []

    existing_jiggle_map = {b["bone_name"]: b for b in existing_data.get("jiggle_bones", [])}
    existing_lookat_map = {b["bone_name"]: b for b in existing_data.get("lookat_bones", [])}
    existing_copy_map   = {(b["target_bone"], b["source_bone"]): b for b in existing_data.get("copy_bones", [])}
    existing_offset_map = {b["bone_name"]: b for b in existing_data.get("offset_bones", [])}

    for fresh_bone in jiggle_bones:
        b_name = fresh_bone["bone_name"]
        if b_name in existing_jiggle_map and existing_jiggle_map[b_name].get("abp_replicated"):
            merged_jiggle_bones.append(existing_jiggle_map[b_name])
        else:
            merged_jiggle_bones.append(fresh_bone)

    for b_name, old_bone in existing_jiggle_map.items():
        if old_bone.get("abp_replicated") and not any(b["bone_name"] == b_name for b in merged_jiggle_bones):
            if b_name in all_bones:
                merged_jiggle_bones.append(old_bone)

    for fresh_offset in offset_bones:
        b_name = fresh_offset["bone_name"]
        if b_name in existing_offset_map and existing_offset_map[b_name].get("abp_replicated"):
            merged_offset_bones.append(existing_offset_map[b_name])
        else:
            merged_offset_bones.append(fresh_offset)

    for b_name, old_offset in existing_offset_map.items():
        if old_offset.get("abp_replicated") and not any(b["bone_name"] == b_name for b in merged_offset_bones):
            if b_name in all_bones:
                merged_offset_bones.append(old_offset)


    for fresh_look in lookat_bones:
        b_name = fresh_look["bone_name"]
        if b_name in existing_lookat_map and existing_lookat_map[b_name].get("abp_replicated"):
            merged_lookat_bones.append(existing_lookat_map[b_name])
        else:
            merged_lookat_bones.append(fresh_look)

    for b_name, old_look in existing_lookat_map.items():
        if old_look.get("abp_replicated") and not any(b["bone_name"] == b_name for b in merged_lookat_bones):
            if b_name in all_bones:
                merged_lookat_bones.append(old_look)

    for fresh_copy in copy_bones:
        key = (fresh_copy["target_bone"], fresh_copy["source_bone"])
        if key in existing_copy_map and existing_copy_map[key].get("abp_replicated"):
            merged_copy_bones.append(existing_copy_map[key])
        else:
            merged_copy_bones.append(fresh_copy)

    for key, old_copy in existing_copy_map.items():
        if old_copy.get("abp_replicated") and not any((b["target_bone"], b["source_bone"]) == key for b in merged_copy_bones):
            if key[0] in all_bones and key[1] in all_bones:
                merged_copy_bones.append(old_copy)

    # 6. Default ShapeKeys
    default_shapekeys = []
    for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
        if obj.data and getattr(obj.data, "shape_keys", None) and obj.data.shape_keys.key_blocks:
            for kb in obj.data.shape_keys.key_blocks:
                if kb.name != "Basis" and kb.name.lower().startswith("default") and kb.name not in default_shapekeys:
                    default_shapekeys.append(kb.name)

    # 7. Animation Extraction
    parts = output_path.replace("\\", "/").split("/")
    detected_base_pal = base_name
    if "Character" in parts:
        c_idx = parts.index("Character")
        if c_idx + 2 < len(parts):
            detected_base_pal = parts[c_idx + 2]

    custom_anims_data = harvest_nla_animations(arm_obj, base_name, existing_data, detected_base_pal)

    # 8. Assemble Final Layout
    layout_data = {
        "all_bones": all_bones,
        "jiggle_bones": merged_jiggle_bones,
        "lookat_bones": merged_lookat_bones,
        "copy_bones": merged_copy_bones,
        "offset_bones": merged_offset_bones,
        "bone_rest_ue": bone_rest_ue,
        "materials": merged_materials,
        "morph_targets": [],
        "default_shapekeys": default_shapekeys,
        "has_replicated_abp": existing_data.get("has_replicated_abp", False)
    }

    if custom_anims_data:
        layout_data["custom_animations"] = custom_anims_data

    for k in ["Gender", "IsRarePal", "SkinName", "ReqTrait", "PrefTrait", "MaterialOverrides", "MorphTarget", "ShapeKeys", "preserve_materials", "push_materials", "push_textures", "push_animbp", "active_vanilla_replacer", "custom_blacklist"]:
        if k in existing_data and k not in layout_data:
            layout_data[k] = existing_data[k]

    print(f"[PalBaker Extractor] Writing updated sidecar to: {os.path.basename(output_path)}", flush=True)
    save_sidecar(output_path, layout_data)

    if fbx_path:
        print(f"[PalBaker Extractor] Exporting FBX payload to: {os.path.basename(fbx_path)}", flush=True)
        translator.export_fbx(fbx_path, "Armature")
        
    print("[PalBaker Extractor] Extraction routine complete!\n", flush=True)

if __name__ == "__main__":
    try:
        out_json, fbx_out = parse_args()
        extract_metadata(out_json, fbx_out)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)