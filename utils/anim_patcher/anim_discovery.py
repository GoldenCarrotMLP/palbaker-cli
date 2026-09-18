# utils/anim_patcher/anim_discovery.py
import os
import json
import re
import shutil
import subprocess
from utils.extractor.core import extract_game_files

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

    # 3. Unique Waza
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

def harvest_pal_animation_inventory(settings: dict, base_pal: str, temp_dir: str, log_cb=None) -> tuple[dict, dict]:
    def log(msg, lvl="standard"):
        if log_cb: log_cb(msg, lvl)
        else: print(f"[PalBaker Anims] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui_exe = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    cache_path = os.path.join(repo_root, "deps", "anim_mapping_cache.json")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    mapping_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f_c:
                mapping_cache = json.load(f_c)
        except Exception: pass

    log(f"Extracting Blueprint and animation metadata for {base_pal}...", "standard")
    extract_game_files(settings, [f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}/*"], temp_dir, format_type="raw")

    bp_disk = None
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"bp_{base_pal.lower()}.uasset":
                bp_disk = os.path.join(root, f)
                break
        if bp_disk: break

    inventory = {}
    blend_spaces = {}

    if not bp_disk or not os.path.exists(bp_disk):
        return inventory, blend_spaces

    bp_json = os.path.join(temp_dir, f"BP_{base_pal}.json")
    try:
        subprocess.run([uasset_gui_exe, "tojson", bp_disk, bp_json, "VER_UE5_1"], check=True, creationflags=creation_flags)
        with open(bp_json, "r", encoding="utf-8") as f:
            raw_json = json.load(f)

        imports = raw_json.get("Imports", [])

        # Harvest RandomRestMontageInfos properties if present
        rest_map = find_key_globally(raw_json, "RandomRestMontageInfos") or []
        rest_infos_by_montage = {}
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

        # 1. Harvest all BlendSpaces
        bs_assets = [imp.get("ObjectName", "") for imp in imports if imp.get("ClassName") in ["BlendSpace1D", "BlendSpace"]]
        
        for bs_asset_name in bs_assets:
            if not bs_asset_name: continue
            
            bs_disk = None
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if f.lower() == f"{bs_asset_name.lower()}.uasset":
                        bs_disk = os.path.join(root, f)
                        break
                if bs_disk: break

            if not bs_disk or not os.path.exists(bs_disk): continue

            samples_list = []
            axis_name = "Speed"
            max_speed = 1000.0

            bs_json = os.path.join(temp_dir, f"{bs_asset_name}.json")
            try:
                subprocess.run([uasset_gui_exe, "tojson", bs_disk, bs_json, "VER_UE5_1"], check=True, creationflags=creation_flags)
                with open(bs_json, "r", encoding="utf-8") as f_bs:
                    bs_raw = json.load(f_bs)

                bs_imports = bs_raw.get("Imports", [])
                anim_seqs = [imp.get("ObjectName", "") for imp in bs_imports if imp.get("ClassName") == "AnimSequence"]

                speed_step = (max_speed / max(1, len(anim_seqs) - 1)) if len(anim_seqs) > 1 else 0.0
                for idx, seq_name in enumerate(anim_seqs):
                    clean_track = extract_track_name(seq_name)
                    calc_speed = round(float(idx * speed_step), 1)

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
                        "notifies": []
                    }
            except Exception: pass

            clean_bs_key = extract_track_name(bs_asset_name)
            enum_key = mapping_cache.get(clean_bs_key, {}).get("enum_key", f"EPalGeneralBlendSpaceType::{clean_bs_key}")

            blend_spaces[clean_bs_key] = {
                "enum_key": enum_key,
                "asset_name": bs_asset_name,
                "axis_name": axis_name,
                "max_speed": max_speed,
                "samples": samples_list
            }

        # 2. Harvest all Montages & Sequences
        for imp in imports:
            c_name = imp.get("ClassName", "")
            o_name = imp.get("ObjectName", "")
            if not o_name or o_name in inventory: continue

            clean_track = extract_track_name(o_name)

            if c_name == "AnimMontage":
                # =============================================================
                # PATTERN CHECK: Detect any Rest{numbers} (e.g. Rest01, Rest02, Rest1, Rest_04)
                # =============================================================
                is_rest_animation = bool(re.match(r'^Rest_?\d+$', clean_track, re.IGNORECASE) or "rest0" in clean_track.lower())

                if is_rest_animation:
                    category = "RandomRest"
                    enum_key = f"Rest_{clean_track}"
                    display_name = f"Idle/Rest: {clean_track}"
                    rest_props = rest_infos_by_montage.get(o_name, {
                        "weight": 1.0,
                        "loop_min": 1,
                        "loop_max": 2,
                        "after_idle_time": 2.0
                    })
                elif clean_track in mapping_cache:
                    meta = mapping_cache[clean_track]
                    category = meta.get("category", "GeneralMontage")
                    enum_key = meta.get("enum_key", f"EPalGeneralMontageType::{clean_track}")
                    display_name = meta.get("display_name", f"Montage: {clean_track}")
                    rest_props = None
                else:
                    if "machete" in clean_track.lower() or "unique" in o_name.lower():
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
                    "sequence_asset": o_name.replace("AM_", "AS_"),
                    "nla_track_name": clean_track,
                    "in_nla": False,
                    "is_modified": False,
                    "notifies": []
                }
                if rest_props:
                    anim_entry["rest_props"] = rest_props

                inventory[o_name] = anim_entry

            elif c_name == "AnimSequence" and o_name not in inventory:
                if clean_track in mapping_cache:
                    meta = mapping_cache[clean_track]
                    category = meta.get("category", "LocomotionSequence")
                    enum_key = meta.get("enum_key", f"EPalGeneralAnimSequenceType::{clean_track}")
                    display_name = meta.get("display_name", f"Sequence: {clean_track}")
                else:
                    category = "LocomotionSequence"
                    enum_key = f"EPalGeneralAnimSequenceType::{clean_track}"
                    display_name = f"Sequence: {clean_track.replace('_', ' ')}"

                inventory[o_name] = {
                    "category": category,
                    "enum_key": enum_key,
                    "display_name": display_name,
                    "sequence_asset": o_name,
                    "montage_asset": None,
                    "nla_track_name": clean_track,
                    "in_nla": False,
                    "is_modified": False,
                    "notifies": []
                }

    except Exception as e:
        log(f"Warning during blueprint harvest: {e}", "warning")

    return inventory, blend_spaces