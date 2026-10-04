# utils/anim_patcher/anim_discovery.py
import os
import json
import re
import shutil
import subprocess
from utils.extractor.core import extract_game_files
from utils.uasset_helper import decompile_uasset

def extract_track_name(asset_name: str) -> str:
    clean = asset_name.split("'")[-2] if "'" in asset_name else asset_name
    clean = clean.split("/")[-1].split(".")[0]

    # 1. Montages & Sequences
    m = re.match(r'^(?:AM|AS)_[a-zA-Z0-9]+?_(.+)$', clean)
    if m: return m.group(1)

    # 2. BlendSpaces
    m = re.match(r'^BS_([a-zA-Z]+)_[a-zA-Z0-9]+(?:_(.+))?$', clean)
    if m:
        return f"{m.group(1)}_{m.group(2)}" if m.group(2) else m.group(1)

    if clean.startswith("BS_"): return clean[3:]

    # 3. Unique Waza Actions
    m = re.match(r'^(?:BP_Action_Unique|BP_UniqueAction)_[a-zA-Z0-9]+?_(.+)$', clean)
    if m: return m.group(1)

    return clean

def find_key_globally(node, target_key):
    if isinstance(node, dict):
        if target_key in node:
            return node[target_key]
        if node.get("Name") == target_key and "Value" in node:
            return node["Value"]
        for v in node.values():
            res = find_key_globally(v, target_key)
            if res is not None:
                return res
    elif isinstance(node, list):
        for item in node:
            res = find_key_globally(item, target_key)
            if res is not None:
                return res
    return None

def parse_float_safe(val, default: float = 0.0) -> float:
    if val is None or val == "" or val == "+0" or val == "-0":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def check_sequence_root_motion(as_uasset_path: str, uasset_gui_exe: str, usmap_path: str) -> bool:
    """
    Decompiles an AnimSequence (.uasset) using UAssetGUI and Mappings.usmap to check
    if bEnableRootMotion is set to True.
    """
    if not as_uasset_path or not os.path.exists(as_uasset_path):
        return False

    as_json = as_uasset_path.replace(".uasset", ".json")
    try:
        # 1. Decompile with UAssetGUI and Mappings.usmap if json does not already exist
        if not os.path.exists(as_json):
            success = decompile_uasset(uasset_gui_exe, as_uasset_path, as_json, usmap_path)
            if not success or not os.path.exists(as_json):
                return False

        # 2. Inspect the unversioned schema output
        with open(as_json, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        # Format 1: UAssetGUI NormalExport format (Exports array)
        for exp in data.get("Exports", []):
            for prop in exp.get("Data", []):
                if isinstance(prop, dict) and prop.get("Name") in ["bEnableRootMotion", "enable_root_motion"]:
                    val = prop.get("Value")
                    if isinstance(val, bool):
                        return val
                    if isinstance(val, (int, float)):
                        return bool(val)
                    if isinstance(val, str):
                        return val.lower() in ["true", "1"]

        # Format 2: FModel / CUE4Parse flat list or dictionary
        objects = data if isinstance(data, list) else [data]
        for obj in objects:
            if isinstance(obj, dict):
                props = obj.get("Properties", {})
                if "bEnableRootMotion" in props:
                    return bool(props["bEnableRootMotion"])
                if "enable_root_motion" in props:
                    return bool(props["enable_root_motion"])
    except Exception as e:
        print(f"[PalBaker Anims Warning] Failed to inspect root motion for {os.path.basename(as_uasset_path)}: {e}", flush=True)

    return False

def resolve_sub_export_details(export_idx: int, exports: list, imports: list) -> dict:
    if not isinstance(export_idx, int) or export_idx <= 0 or export_idx > len(exports):
        return {}

    exp = exports[export_idx - 1]
    exp_name = exp.get("ObjectName", "")
    details = {"SubExport": exp_name}

    for p in exp.get("Data", []):
        p_name = p.get("Name")
        p_val = p.get("Value")

        if p_name in ["NotifyName", "EyeType", "Waza", "attachBoneName", "CollisionProfileName"]:
            details[p_name] = str(p_val)
        elif p_name in ["Event", "Template", "Asset"]:
            if isinstance(p_val, int) and p_val < 0 and (-p_val - 1) < len(imports):
                details[p_name] = imports[-p_val - 1].get("ObjectName", "")
        elif p_name in ["CapsuleRadius", "CapsuleHalfHeight"]:
            details[p_name] = parse_float_safe(p_val)
        elif p_name == "NativeBlowVelocity":
            if isinstance(p_val, list) and len(p_val) > 0:
                vec = p_val[0].get("Value", {})
                details["BlowVelocity"] = [
                    parse_float_safe(vec.get("X")),
                    parse_float_safe(vec.get("Y")),
                    parse_float_safe(vec.get("Z"))
                ]
        elif p_name in ["ShapeComponents", "AttackFilter"]:
            if isinstance(p_val, int) and 0 < p_val <= len(exports):
                details[p_name] = resolve_sub_export_details(p_val, exports, imports)
            elif isinstance(p_val, list):
                details[p_name] = [
                    resolve_sub_export_details(item, exports, imports)
                    for item in p_val if isinstance(item, int) and 0 < item <= len(exports)
                ]

    return details

def scrape_notifies_from_json(uasset_json_path: str) -> list[dict]:
    notifies_list = []
    if not os.path.exists(uasset_json_path):
        return notifies_list

    try:
        with open(uasset_json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        exports = data.get("Exports", [])
        imports = data.get("Imports", [])

        if not exports:
            if isinstance(data, list) and len(data) > 0:
                props = data[0].get("Properties", {})
                notifies_val = props.get("Notifies", [])
                for n in notifies_val:
                    notifies_list.append({
                        "Name": str(n.get("NotifyName", "PalCustomNotify")),
                        "Time": round(parse_float_safe(n.get("LinkValue", n.get("DisplayTime"))), 4),
                        "Duration": round(parse_float_safe(n.get("Duration")), 4)
                    })
            return notifies_list

        montage_export = next(
            (exp for exp in exports if exp.get("Type") == "AnimMontage" or exp.get("ObjectName", "").startswith("AM_")),
            exports[0]
        )

        props = montage_export.get("Data", [])
        notifies_prop = next((p for p in props if p.get("Name") == "Notifies"), None)
        if not notifies_prop or not isinstance(notifies_prop.get("Value"), list):
            return notifies_list

        for idx, struct_item in enumerate(notifies_prop["Value"]):
            inner_vals = struct_item.get("Value", [])
            notify_name = "PalCustomNotify"
            notify_time = 0.0
            notify_duration = 0.0
            notify_obj_idx = 0
            notify_state_idx = 0
            track_index = 0

            for p in inner_vals:
                p_name = p.get("Name")
                p_val = p.get("Value")

                if p_name == "NotifyName":
                    notify_name = str(p_val)
                elif p_name == "LinkValue":
                    notify_time = parse_float_safe(p_val, notify_time)
                elif p_name == "Duration":
                    notify_duration = parse_float_safe(p_val, notify_duration)
                elif p_name == "Notify":
                    notify_obj_idx = p_val if isinstance(p_val, int) else 0
                elif p_name == "NotifyStateClass":
                    notify_state_idx = p_val if isinstance(p_val, int) else 0
                elif p_name == "TrackIndex":
                    track_index = int(p_val) if isinstance(p_val, (int, float)) else 0

            deep_details = {}
            if notify_obj_idx > 0:
                deep_details = resolve_sub_export_details(notify_obj_idx, exports, imports)
            elif notify_state_idx > 0:
                deep_details = resolve_sub_export_details(notify_state_idx, exports, imports)

            notify_record = {
                "Name": notify_name,
                "Time": round(notify_time, 4),
                "Duration": round(notify_duration, 4),
                "Track": track_index
            }

            if "NotifyName" in deep_details and deep_details["NotifyName"] != notify_name:
                notify_record["EventName"] = deep_details["NotifyName"]
            if "EyeType" in deep_details:
                notify_record["EyeType"] = deep_details["EyeType"]
            if "Event" in deep_details:
                notify_record["AudioEvent"] = deep_details["Event"]
            if "Template" in deep_details:
                notify_record["NiagaraSystem"] = deep_details["Template"]
            if "Waza" in deep_details:
                notify_record["WazaID"] = deep_details["Waza"]
            if "attachBoneName" in deep_details:
                notify_record["AttachBone"] = deep_details["attachBoneName"]
            if "BlowVelocity" in deep_details:
                notify_record["BlowVelocity"] = deep_details["BlowVelocity"]

            notifies_list.append(notify_record)

    except Exception as e:
        print(f"[Scraper Warning] Failed to parse notifies: {e}", flush=True)

    return notifies_list

def harvest_pal_animation_inventory(settings: dict, base_pal: str, temp_dir: str, log_cb=None) -> tuple[dict, dict]:
    def log(msg, lvl="standard"):
        if log_cb: log_cb(msg, lvl)
        else: print(f"[PalBaker Anims] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui_exe = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    cache_path = os.path.join(repo_root, "deps", "anim_mapping_cache.json")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    mapping_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f_c:
                mapping_cache = json.load(f_c)
        except Exception: pass

    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    # 1. Full Package Extraction
    log(f"Extracting all Blueprints, Montages, and BlendSpaces for {base_pal} from game archives...", "standard")
    extract_targets = [
        f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}/*",
        f"Pal/Content/Pal/Animation/Character/Monster/{base_pal}/*",
        f"Pal/Content/Pal/Animation/Character/Pending Monster/{base_pal}/*",
        f"*Animation/Character/*/{base_pal}/*"
    ]
    extract_game_files(settings, extract_targets, temp_dir, format_type="raw")

    # Map all extracted AnimSequence (.uasset) files by sequence name, lowercase name, and clean track name
    as_uasset_map = {}
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.startswith("AS_") and f.endswith(".uasset"):
                seq_base = os.path.splitext(f)[0]
                uasset_path = os.path.join(root, f)
                as_uasset_map[seq_base] = uasset_path
                as_uasset_map[seq_base.lower()] = uasset_path

                clean_t = extract_track_name(seq_base)
                if clean_t:
                    as_uasset_map[clean_t] = uasset_path
                    as_uasset_map[clean_t.lower()] = uasset_path

    root_motion_cache = {}
    def get_root_motion(seq_key_name: str, clean_track_name: str = "") -> bool:
        if not seq_key_name:
            return False
        clean_key = seq_key_name.split(".")[0]
        if clean_key in root_motion_cache:
            return root_motion_cache[clean_key]
        if clean_key.lower() in root_motion_cache:
            return root_motion_cache[clean_key.lower()]
        if clean_track_name and clean_track_name.lower() in root_motion_cache:
            return root_motion_cache[clean_track_name.lower()]

        uasset_file = (
            as_uasset_map.get(clean_key) or 
            as_uasset_map.get(clean_key.lower()) or
            as_uasset_map.get(clean_track_name) or
            as_uasset_map.get(clean_track_name.lower())
        )

        if not uasset_file and clean_track_name:
            for k, p in as_uasset_map.items():
                if k.lower().endswith(f"_{clean_track_name.lower()}"):
                    uasset_file = p
                    break

        res = check_sequence_root_motion(uasset_file, uasset_gui_exe, usmap_path) if uasset_file else False
        root_motion_cache[clean_key] = res
        root_motion_cache[clean_key.lower()] = res
        if clean_track_name:
            root_motion_cache[clean_track_name.lower()] = res
        return res

    inventory = {}
    blend_spaces = {}
    rest_infos_by_montage = {}

    # 2. Parse Parent Actor Blueprint for Idle/Rest Configuration
    bp_disk = None
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"bp_{base_pal.lower()}.uasset":
                bp_disk = os.path.join(root, f)
                break
        if bp_disk: break

    if bp_disk and os.path.exists(bp_disk):
        bp_json = os.path.join(temp_dir, f"BP_{base_pal}.json")
        try:
            subprocess.run([uasset_gui_exe, "tojson", bp_disk, bp_json, "VER_UE5_1", usmap_path], check=True, creationflags=creation_flags)
            with open(bp_json, "r", encoding="utf-8") as f:
                raw_bp = json.load(f)

            rest_map = find_key_globally(raw_bp, "RandomRestMontageInfos") or []
            for rest in rest_map:
                asset = rest.get("RandomRestMontage", {}).get("ObjectName", "")
                clean_asset = asset.split("'")[-2] if "'" in asset else asset
                if clean_asset:
                    rest_infos_by_montage[clean_asset] = {
                        "weight": float(rest.get("Weight", 1.0)),
                        "loop_min": int(rest.get("LoopNum_Min", 1)),
                        "loop_max": int(rest.get("LoopNum_Max", 1)),
                        "after_idle_time": float(rest.get("AfterIdleTime", 2.0))
                    }
        except Exception as e:
            log(f"Warning parsing Actor Blueprint: {e}", "warning")

    # 3. Harvest All BlendSpaces (*.uasset)
    bs_uassets = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.startswith("BS_") and f.endswith(".uasset"):
                bs_uassets.append(os.path.join(root, f))

    for bs_path in bs_uassets:
        bs_asset_name = os.path.splitext(os.path.basename(bs_path))[0]
        bs_json = bs_path.replace(".uasset", ".json")

        try:
            subprocess.run([uasset_gui_exe, "tojson", bs_path, bs_json, "VER_UE5_1", usmap_path], check=True, creationflags=creation_flags)
            with open(bs_json, "r", encoding="utf-8") as f_bs:
                bs_raw = json.load(f_bs)

            bs_imports = bs_raw.get("Imports", [])
            anim_seqs = [imp.get("ObjectName", "") for imp in bs_imports if imp.get("ClassName") == "AnimSequence"]

            max_speed = 1000.0
            speed_step = (max_speed / max(1, len(anim_seqs) - 1)) if len(anim_seqs) > 1 else 0.0
            samples_list = []

            for idx, seq_name in enumerate(anim_seqs):
                clean_track = extract_track_name(seq_name)
                calc_speed = round(float(idx * speed_step), 1)
                rm_enabled = get_root_motion(seq_name, clean_track)

                samples_list.append({
                    "animation": seq_name,
                    "clean_name": clean_track,
                    "speed": calc_speed,
                    "rate_scale": 1.0,
                    "in_nla": False
                })

                inventory[seq_name] = {
                    "category": "BlendSpaceSample",
                    "enum_key": f"{bs_asset_name}_{clean_track}",
                    "display_name": f"{bs_asset_name}: {clean_track} ({calc_speed} u/s)",
                    "sequence_asset": seq_name,
                    "montage_asset": None,
                    "nla_track_name": clean_track,
                    "in_nla": False,
                    "is_modified": False,
                    "notifies": [],
                    "enable_root_motion": rm_enabled
                }

            clean_bs_key = extract_track_name(bs_asset_name)
            enum_key = mapping_cache.get(clean_bs_key, {}).get("enum_key", f"EPalGeneralBlendSpaceType::{clean_bs_key}")

            blend_spaces[clean_bs_key] = {
                "enum_key": enum_key,
                "asset_name": bs_asset_name,
                "axis_name": "Speed",
                "max_speed": max_speed,
                "samples": samples_list
            }
        except Exception: pass

    # 4. Harvest All AnimMontages (*.uasset) with Deep Notify & Root Motion Extraction
    am_uassets = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.startswith("AM_") and f.endswith(".uasset"):
                am_uassets.append(os.path.join(root, f))

    log(f"Decompiling and scraping notifies from {len(am_uassets)} AnimMontages...", "standard")

    for am_path in am_uassets:
        o_name = os.path.splitext(os.path.basename(am_path))[0]
        clean_track = extract_track_name(o_name)
        if clean_track.lower() in ["hit", "damageadditive"]:
            continue
        am_json = am_path.replace(".uasset", ".json")

        scraped_notifies = []
        try:
            subprocess.run([uasset_gui_exe, "tojson", am_path, am_json, "VER_UE5_1", usmap_path], check=True, creationflags=creation_flags)
            scraped_notifies = scrape_notifies_from_json(am_json)
        except Exception: pass

        seq_key = o_name.replace("AM_", "AS_")
        rm_enabled = get_root_motion(seq_key, clean_track)

        is_rest_animation = bool(re.match(r'^Rest_?\d+$', clean_track, re.IGNORECASE) or "rest0" in clean_track.lower())

        if is_rest_animation:
            category = "RandomRest"
            enum_key = f"Rest_{clean_track}"
            display_name = f"Idle/Rest: {clean_track}"
            rest_props = rest_infos_by_montage.get(o_name, {
                "weight": 1.0, "loop_min": 1, "loop_max": 2, "after_idle_time": 2.0
            })
        elif clean_track in mapping_cache:
            meta = mapping_cache[clean_track]
            category = meta.get("category", "GeneralMontage")
            enum_key = meta.get("enum_key", f"EPalGeneralMontageType::{clean_track}")
            display_name = meta.get("display_name", f"Montage: {clean_track}")
            rest_props = None
        else:
            if any(kw in clean_track.lower() for kw in ["tossin", "unique", "skill", "machete", "punch"]):
                category = "UniqueAttack"
                enum_key = f"EPalWazaID::Unique_{base_pal}_{clean_track}"
                display_name = f"Unique: {clean_track.replace('_', ' ')}"
            else:
                category = "GeneralMontage"
                enum_key = f"EPalGeneralMontageType::{clean_track}"
                display_name = f"Montage: {clean_track.replace('_', ' ')}"
            rest_props = None

        anim_entry = {
            "category": category,
            "enum_key": enum_key,
            "display_name": display_name,
            "montage_asset": o_name,
            "sequence_asset": seq_key,
            "nla_track_name": clean_track,
            "in_nla": False,
            "is_modified": False,
            "notifies": scraped_notifies,
            "enable_root_motion": rm_enabled
        }
        if rest_props:
            anim_entry["rest_props"] = rest_props

        inventory[seq_key] = anim_entry

    # 5. Harvest Standalone AnimSequences (*.uasset)
    as_uassets = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.startswith("AS_") and f.endswith(".uasset"):
                as_uassets.append(os.path.join(root, f))

    for as_path in as_uassets:
        seq_name = os.path.splitext(os.path.basename(as_path))[0]
        if seq_name in inventory: continue

        clean_track = extract_track_name(seq_name)
        if clean_track.lower() in ["hit", "damageadditive"]:
            continue

        rm_enabled = get_root_motion(seq_name, clean_track)

        if clean_track in mapping_cache:
            meta = mapping_cache[clean_track]
            category = meta.get("category", "LocomotionSequence")
            enum_key = meta.get("enum_key", f"EPalGeneralAnimSequenceType::{clean_track}")
            display_name = meta.get("display_name", f"Sequence: {clean_track}")
        else:
            category = "LocomotionSequence"
            enum_key = f"EPalGeneralAnimSequenceType::{clean_track}"
            display_name = f"Sequence: {clean_track.replace('_', ' ')}"

        inventory[seq_name] = {
            "category": category,
            "enum_key": enum_key,
            "display_name": display_name,
            "sequence_asset": seq_name,
            "montage_asset": None,
            "nla_track_name": clean_track,
            "in_nla": False,
            "is_modified": False,
            "notifies": [],
            "enable_root_motion": rm_enabled
        }

    rm_count = sum(1 for v in inventory.values() if v.get("enable_root_motion"))
    log(f"Extracted {len(inventory)} total animations ({rm_count} with Root Motion) and {len(blend_spaces)} blendspaces.", "success")
    return inventory, blend_spaces