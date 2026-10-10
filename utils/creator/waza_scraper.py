import os
import re
import json
import shutil
from utils.extractor.core import extract_game_files
from utils.uasset_helper import decompile_uasset

def resolve_donor_pals(waza_id: str) -> list[str]:
    """Accurately resolves candidate donor Pals for a given unique waza."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    primary = resolve_donor_pal_from_waza(waza_id, repo_root)
    if not primary:
        return []
    candidates = [primary]
    for sfx in ["_Dark", "_Ice", "_Fire", "_Water", "_Electric", "_Grass", "_Ground"]:
        candidates.append(f"{primary}{sfx}")
    return candidates

def resolve_donor_pals(waza_id: str) -> list[str]:
    """Accurately resolves candidate donor Pals for a given unique waza."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    primary = resolve_donor_pal_from_waza(waza_id, repo_root)
    if not primary:
        return []
    candidates = [primary]
    for sfx in ["_Dark", "_Ice", "_Fire", "_Water", "_Electric", "_Grass", "_Ground"]:
        candidates.append(f"{primary}{sfx}")
    return candidates

def resolve_donor_pal_from_waza(waza_id: str, repo_root: str) -> str:
    """Accurately extracts the donor Pal name from the waza ID by matching against known Pal IDs."""
    clean = waza_id.replace("EPalWazaID::", "").replace("Unique_", "").strip()
    
    known_pals = set()
    for cache_name in ["monster_parameter_cache.json", "pal_names_map.json"]:
        cp = os.path.join(repo_root, "deps", cache_name)
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        if "Rows" in data:
                            known_pals.update(data["Rows"].keys())
                        else:
                            known_pals.update(data.keys())
            except Exception:
                pass

    # Sort descending by length so compound names match first (e.g. FireKirin_Dark before FireKirin)
    for pal in sorted(list(known_pals), key=len, reverse=True):
        if clean.lower().startswith(pal.lower() + "_") or clean.lower() == pal.lower():
            return pal

    return clean.split("_")[0]

def find_action_path_in_bp_ast(bp_data: dict, target_waza_enum: str) -> str | None:
    clean_target = target_waza_enum.split("::")[-1].lower()

    # Format A: UAssetGUI NormalExport
    for exp in bp_data.get("Exports", []):
        obj_name = str(exp.get("ObjectName", ""))
        if "StaticCharacterParameterComponent" in obj_name or "CharacterParameter" in obj_name:
            for prop in exp.get("Data", []):
                if prop.get("Name") == "WazaActionDeclarationMap":
                    entries = prop.get("Value", [])
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, list) and len(entry) >= 2:
                                k_obj, v_obj = entry[0], entry[1]
                                k_val = str(k_obj.get("Value", "")).split("::")[-1].lower()
                                if k_val == clean_target:
                                    v_val = v_obj.get("Value", {})
                                    if isinstance(v_val, dict):
                                        asset_path = v_val.get("AssetPath", {})
                                        pkg = asset_path.get("PackageName") or v_val.get("AssetPathName")
                                        cls = asset_path.get("AssetName")
                                        if pkg:
                                            return f"{pkg}.{cls}" if cls and not pkg.endswith(cls) else pkg
                                    elif isinstance(v_val, str):
                                        return v_val

    # Format B: CUE4Parse Flat List or Dict
    objects = bp_data if isinstance(bp_data, list) else [bp_data]
    for obj in objects:
        props = obj.get("Properties", {}) if isinstance(obj, dict) else {}
        waza_map = props.get("WazaActionDeclarationMap", [])
        if isinstance(waza_map, list):
            for entry in waza_map:
                if isinstance(entry, dict):
                    k_val = str(entry.get("Key", "")).split("::")[-1].lower()
                    if k_val == clean_target:
                        v_val = entry.get("Value", {})
                        if isinstance(v_val, dict):
                            return v_val.get("AssetPathName") or v_val.get("PackageName")
                        elif isinstance(v_val, str):
                            return v_val
    return None

def scrape_waza_dependencies(settings: dict, waza_id: str, pal_id: str = "") -> dict:
    clean_waza = waza_id.replace("EPalWazaID::", "").strip()
    if not clean_waza.startswith("Unique_"):
        return {"deps": [], "available_sequences": []}

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cache_path = os.path.join(repo_root, "deps", "unique_waza_cache.json")
    
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    if clean_waza in cache and isinstance(cache[clean_waza], list) and len(cache[clean_waza]) > 0:
        return {"deps": cache[clean_waza], "available_sequences": _discover_available_sequences(settings, pal_id, clean_waza)}

    temp_dir = os.path.join(repo_root, "temp_waza_dynamic_scrape")
    uasset_gui = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))

    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    donor_pal = resolve_donor_pal_from_waza(clean_waza, repo_root)

    # 1. DECOMPILE DONOR ACTOR BLUEPRINT (Must extract .uasset AND .uexp)
    bp_rel = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{donor_pal}/BP_{donor_pal}.uasset"
    extract_game_files(settings, [bp_rel, bp_rel.replace(".uasset", ".uexp"), f"*{donor_pal}*BP_{donor_pal}*.uasset", f"*{donor_pal}*BP_{donor_pal}*.uexp"], temp_dir, format_type="raw")

    donor_bp_disk = None
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"bp_{donor_pal.lower()}.uasset":
                donor_bp_disk = os.path.join(root, f)
                break
        if donor_bp_disk: break

    action_asset_path = None
    if donor_bp_disk and os.path.exists(donor_bp_disk):
        bp_json = donor_bp_disk.replace(".uasset", ".json")
        if decompile_uasset(uasset_gui, donor_bp_disk, bp_json, usmap_path):
            with open(bp_json, "r", encoding="utf-8-sig") as f_bp:
                bp_ast = json.load(f_bp)
            action_asset_path = find_action_path_in_bp_ast(bp_ast, clean_waza)

    # 2. DECOMPILE ACTION BLUEPRINT AND FOLLOW SKILL MODULES
    required_montages = set()
    if action_asset_path:
        clean_action_pkg = action_asset_path.split(".")[0].replace("/Game/", "Pal/Content/")
        act_rel = f"{clean_action_pkg}.uasset"
        extract_game_files(settings, [act_rel, act_rel.replace(".uasset", ".uexp")], temp_dir, format_type="raw")

        act_uasset = os.path.join(temp_dir, act_rel)
        if not os.path.exists(act_uasset):
            for r, _, fs in os.walk(temp_dir):
                if os.path.basename(act_rel).lower() in [f.lower() for f in fs]:
                    act_uasset = os.path.join(r, os.path.basename(act_rel))
                    break

        if act_uasset and os.path.exists(act_uasset):
            act_json = act_uasset.replace(".uasset", ".json")
            if decompile_uasset(uasset_gui, act_uasset, act_json, usmap_path):
                with open(act_json, "r", encoding="utf-8-sig") as f_act:
                    action_content = f_act.read()

                for am in re.findall(r'(AM_[a-zA-Z0-9_]+)', action_content):
                    required_montages.add(am)

                # Follow Skill Modules
                module_matches = set(re.findall(r'(BP_UniqueSkillModule_[a-zA-Z0-9_]+)', action_content))
                for mod_name in module_matches:
                    clean_mod = mod_name.replace("_C", "")
                    extract_game_files(settings, [f"*{clean_mod}*.uasset", f"*{clean_mod}*.uexp"], temp_dir, format_type="raw")
                    
                    mod_uasset = None
                    for r, _, fs in os.walk(temp_dir):
                        for f in fs:
                            if f.lower() == f"{clean_mod.lower()}.uasset":
                                mod_uasset = os.path.join(r, f)
                                break
                        if mod_uasset: break

                    if mod_uasset and os.path.exists(mod_uasset):
                        mod_json = mod_uasset.replace(".uasset", ".json")
                        if decompile_uasset(uasset_gui, mod_uasset, mod_json, usmap_path):
                            with open(mod_json, "r", encoding="utf-8-sig") as f_mod:
                                mod_content = f_mod.read()
                                for m_am in re.findall(r'(AM_[a-zA-Z0-9_]+)', mod_content):
                                    required_montages.add(m_am)

    shutil.rmtree(temp_dir, ignore_errors=True)

    results = []
    if required_montages:
        for am in sorted(list(required_montages)):
            clean_track = re.sub(r'^AM_[a-zA-Z0-9]+?_', '', am)
            results.append({
                "montage_asset": am,
                "clean_track": clean_track
            })
        cache[clean_waza] = results
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass

    return {
        "deps": results,
        "available_sequences": _discover_available_sequences(settings, pal_id, clean_waza)
    }

def _discover_available_sequences(settings: dict, pal_id: str, clean_waza: str) -> list[str]:
    discovered = set()
    target_pals = [p for p in [pal_id, clean_waza.replace("Unique_", "").split("_")[0]] if p]
    uproject = settings.get("uproject", "")
    if uproject and os.path.exists(uproject):
        project_dir = os.path.dirname(uproject)
        project_name = os.path.splitext(os.path.basename(uproject))[0]
        for p_name in target_pals:
            for sub in ["Monster", "Pending Monster"]:
                for d in [
                    os.path.join(project_dir, "Content", "Pal", "Animation", "Character", sub, p_name),
                    os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Animation", "Character", sub, p_name)
                ]:
                    if os.path.exists(d):
                        for f in os.listdir(d):
                            if f.startswith("AS_") and f.endswith(".uasset"):
                                discovered.add(os.path.splitext(f)[0])
    return sorted(list(discovered))

def autofill_stage_defaults(settings: dict, waza_id: str, clean_track: str, target_pal: str) -> dict:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    clean_waza = waza_id.replace("EPalWazaID::", "").strip()
    
    # 1. Resolve exact donor Pal
    donor_pal = resolve_donor_pal_from_waza(clean_waza, repo_root)

    # 2. Get scraped dependencies to find the real montage name
    deps_info = scrape_waza_dependencies(settings, clean_waza, target_pal)
    deps = deps_info.get("deps", [])
    matched = next((d for d in deps if d.get("clean_track", "").lower() == clean_track.lower()), None)

    am_name = matched["montage_asset"] if matched else f"AM_{donor_pal}_{clean_track}"
    as_name = am_name.replace("AM_", "AS_")

    uasset_gui = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    temp_dir = os.path.join(repo_root, "temp_stage_autofill")

    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    # 3. EXTRACT BOTH .uasset AND .uexp
    extract_queue = [
        f"Pal/Content/Pal/Animation/Character/*/{donor_pal}/{am_name}.uasset",
        f"Pal/Content/Pal/Animation/Character/*/{donor_pal}/{am_name}.uexp",
        f"Pal/Content/Pal/Animation/Character/*/{donor_pal}/{as_name}.uasset",
        f"Pal/Content/Pal/Animation/Character/*/{donor_pal}/{as_name}.uexp",
        f"*{am_name}.uasset",
        f"*{am_name}.uexp",
        f"*{as_name}.uasset",
        f"*{as_name}.uexp"
    ]
    extract_game_files(settings, extract_queue, temp_dir, format_type="raw")

    from utils.anim_patcher.anim_discovery import scrape_notifies_from_json

    seq_notifies = []
    mont_notifies = []
    donor_duration = 0.0

    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"{am_name.lower()}.uasset":
                am_uasset = os.path.join(root, f)
                am_json = am_uasset.replace(".uasset", ".json")
                if decompile_uasset(uasset_gui, am_uasset, am_json, usmap_path):
                    mont_notifies = scrape_notifies_from_json(am_json, source="montage")
                    try:
                        with open(am_json, "r", encoding="utf-8-sig") as f_am:
                            am_ast = json.load(f_am)
                        for p in am_ast.get("Exports", [{}])[0].get("Data", []):
                            if p.get("Name") == "SequenceLength":
                                donor_duration = round(float(p.get("Value", 0.0)), 4)
                                break
                    except Exception: pass
            elif f.lower() == f"{as_name.lower()}.uasset":
                as_uasset = os.path.join(root, f)
                as_json = as_uasset.replace(".uasset", ".json")
                if decompile_uasset(uasset_gui, as_uasset, as_json, usmap_path):
                    seq_notifies = scrape_notifies_from_json(as_json, source="sequence")

    shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "clean_track": clean_track,
        "suggested_sequence": f"AS_{target_pal}_{clean_track}",
        "sequence_notifies": seq_notifies,
        "montage_notifies": mont_notifies,
        "required_duration": donor_duration,
        "required_frames": int(round(donor_duration * 30))
    }