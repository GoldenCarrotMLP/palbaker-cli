import os
import re
import json
import shutil
from utils.extractor.core import extract_game_files
from utils.uasset_helper import decompile_uasset

KNOWN_UNIQUE_WAZAS = {
    "Unique_Anubis_GroundPunch": [
        {"montage_asset": "AM_Anubis_Skill_JimenNaguri_Start", "clean_track": "Skill_JimenNaguri_Start"},
        {"montage_asset": "AM_Anubis_Skill_JimenNaguri_UpLoop", "clean_track": "Skill_JimenNaguri_UpLoop"},
        {"montage_asset": "AM_Anubis_Skill_JimenNaguri_DownLoop", "clean_track": "Skill_JimenNaguri_DownLoop"},
        {"montage_asset": "AM_Anubis_Skill_JimenNaguri_End", "clean_track": "Skill_JimenNaguri_End"}
    ],
    "Unique_Anubis_Tackle": [
        {"montage_asset": "AM_Anubis_Skill_Tossin_Start", "clean_track": "Skill_Tossin_Start"},
        {"montage_asset": "AM_Anubis_Skill_Tossin_Loop", "clean_track": "Skill_Tossin_Loop"},
        {"montage_asset": "AM_Anubis_Skill_Tossin_End", "clean_track": "Skill_Tossin_End"}
    ],
    "Unique_Anubis_LowRoundKick": [
        {"montage_asset": "AM_Anubis_Skill_MawashiGeri", "clean_track": "Skill_MawashiGeri"}
    ],
    "Unique_BlackPuppy_Bite": [
        {"montage_asset": "AM_BlackPuppy_Kamitsuki", "clean_track": "Kamitsuki"}
    ],
    "Unique_BlackPuppy_BiteV2": [
        {"montage_asset": "AM_BlackPuppy_Kamitsuki_ver2", "clean_track": "Kamitsuki_ver2"}
    ],
    "Unique_SamuraiDog_Bite": [
        {"montage_asset": "AM_SamuraiDog_Kamitsuki", "clean_track": "Kamitsuki"}
    ],
    "Unique_SamuraiDog_BiteV2": [
        {"montage_asset": "AM_SamuraiDog_Kamitsuki_ver2", "clean_track": "Kamitsuki_ver2"}
    ],
    "Unique_SheepBall_Roll": [
        {"montage_asset": "AM_SheepBall_Korogaru_Start", "clean_track": "Korogaru_Start"},
        {"montage_asset": "AM_SheepBall_Korogaru_Loop", "clean_track": "Korogaru_Loop"},
        {"montage_asset": "AM_SheepBall_Korogaru_End", "clean_track": "Korogaru_End"}
    ],
    "Unique_Boar_Tackle": [
        {"montage_asset": "AM_Boar_Tossin_Start", "clean_track": "Tossin_Start"},
        {"montage_asset": "AM_Boar_Tossin_Loop", "clean_track": "Tossin_Loop"},
        {"montage_asset": "AM_Boar_Tossin_End", "clean_track": "Tossin_End"}
    ],
    "Unique_AmaterasuWolf_FireCharge": [
        {"montage_asset": "AM_AmaterasuWolf_FireCharge_Start", "clean_track": "FireCharge_Start"},
        {"montage_asset": "AM_AmaterasuWolf_FireCharge_Loop", "clean_track": "FireCharge_Loop"}
    ],
    "Unique_AmaterasuWolf_Bite": [
        {"montage_asset": "AM_AmaterasuWolf_Kamitsuki", "clean_track": "Kamitsuki"}
    ],
    "Unique_AmaterasuWolf_BiteV2": [
        {"montage_asset": "AM_AmaterasuWolf_Kamitsuki_ver2", "clean_track": "Kamitsuki_ver2"}
    ],
    "Unique_Garm_Bite": [
        {"montage_asset": "AM_Garm_Kamitsuki", "clean_track": "Kamitsuki"}
    ],
    "Unique_ThunderDog_Bite": [
        {"montage_asset": "AM_ThunderDog_Kamitsuki", "clean_track": "Kamitsuki"}
    ],
    "Unique_ThunderDog_BiteV2": [
        {"montage_asset": "AM_ThunderDog_Kamitsuki_ver2", "clean_track": "Kamitsuki_ver2"}
    ],
    "Unique_GrassPanda_MusclePunch": [
        {"montage_asset": "AM_GrassPanda_MusclePunch_Start", "clean_track": "MusclePunch_Start"},
        {"montage_asset": "AM_GrassPanda_MusclePunch_Loop", "clean_track": "MusclePunch_Loop"},
        {"montage_asset": "AM_GrassPanda_MusclePunch_End", "clean_track": "MusclePunch_End"}
    ],
    "Unique_Gorilla_GroundPunch": [
        {"montage_asset": "AM_Gorilla_Jimentataki_Action_01", "clean_track": "Jimentataki_Action_01"},
        {"montage_asset": "AM_Gorilla_Jimentataki_Action_02", "clean_track": "Jimentataki_Action_02"},
        {"montage_asset": "AM_Gorilla_Jimentataki_Action_03", "clean_track": "Jimentataki_Action_03"},
        {"montage_asset": "AM_Gorilla_Jimentataki_End", "clean_track": "Jimentataki_End"}
    ],
    "Unique_GrimGirl_BrutalMachete": [
        {"montage_asset": "AM_GrimGirl_BrutalMachete_Start", "clean_track": "BrutalMachete_Start"},
        {"montage_asset": "AM_GrimGirl_BrutalMachete_01", "clean_track": "BrutalMachete_01"},
        {"montage_asset": "AM_GrimGirl_BrutalMachete_End", "clean_track": "BrutalMachete_End"}
    ],
    "Unique_RobinHood_BowSnipe": [
        {"montage_asset": "AM_RobinHood_Snipe", "clean_track": "Snipe"}
    ],
    "Unique_DarkScorpion_Pierce": [
        {"montage_asset": "AM_DarkScorpion_Pierce_Start", "clean_track": "Pierce_Start"},
        {"montage_asset": "AM_DarkScorpion_Pierce_End", "clean_track": "Pierce_End"}
    ]
}

def scrape_waza_dependencies(settings: dict, waza_id: str, pal_id: str = "") -> dict:
    clean_waza = waza_id.replace("EPalWazaID::", "").strip()
    if not clean_waza.startswith("Unique_"):
        return {"deps": [], "available_sequences": []}

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cache_path = os.path.join(repo_root, "deps", "unique_waza_cache.json")
    
    # 1. Check persistent disk cache
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    results = []
    if clean_waza in cache and isinstance(cache[clean_waza], list):
        results = cache[clean_waza]
    elif clean_waza in KNOWN_UNIQUE_WAZAS:
        results = KNOWN_UNIQUE_WAZAS[clean_waza]
        cache[clean_waza] = results
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass
    else:
        # 2. Extract and scrape dynamically only if not pre-cached
        suffix = clean_waza.replace("Unique_", "")
        parts = suffix.split("_")
        search_suffix = suffix
        if len(parts) > 1:
            search_suffix = "_".join(parts[1:])

        temp_dir = os.path.join(repo_root, "temp_waza_scrape")
        uasset_gui = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
        usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))

        shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)

        extract_patterns = [
            f"Pal/Content/Pal/Blueprint/Action/*{search_suffix}*.uasset",
            f"Pal/Content/Pal/Blueprint/Action/*/*{search_suffix}*.uasset",
            f"Pal/Content/Pal/Blueprint/Action/*/*/*{search_suffix}*.uasset",
            f"*Action*{search_suffix}*.uasset"
        ]

        full_extract_queue = []
        for p in extract_patterns:
            full_extract_queue.append(p)
            full_extract_queue.append(p.replace(".uasset", ".uexp"))

        extract_game_files(settings, full_extract_queue, temp_dir, format_type="raw")

        target_uasset = None
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith(".uasset") and search_suffix.lower() in f.lower():
                    target_uasset = os.path.join(root, f)
                    break
            if target_uasset: break

        required_montages = set()
        if target_uasset:
            out_json = target_uasset.replace(".uasset", ".json")
            if decompile_uasset(uasset_gui, target_uasset, out_json, usmap_path):
                if os.path.exists(out_json):
                    with open(out_json, "r", encoding="utf-8-sig") as f:
                        content = f.read()
                        am_refs = re.findall(r'(AM_[a-zA-Z0-9_]+)', content)
                        for am in am_refs:
                            required_montages.add(am)

        shutil.rmtree(temp_dir, ignore_errors=True)

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

    # 3. Discover all physical AS_ sequences on disk for this Pal
    discovered_sequences = set()
    target_pals = [p for p in [pal_id, clean_waza.replace("Unique_", "").split("_")[0]] if p]

    # Unreal Content & Cooked directories
    uproject = settings.get("uproject", "")
    if uproject and os.path.exists(uproject):
        project_dir = os.path.dirname(uproject)
        project_name = os.path.splitext(os.path.basename(uproject))[0]
        for p_name in target_pals:
            for sub in ["Monster", "Pending Monster"]:
                d_raw = os.path.join(project_dir, "Content", "Pal", "Animation", "Character", sub, p_name)
                d_cooked = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Animation", "Character", sub, p_name)
                for d in [d_raw, d_cooked]:
                    if os.path.exists(d):
                        for f in os.listdir(d):
                            if f.startswith("AS_") and f.endswith(".uasset"):
                                discovered_sequences.add(os.path.splitext(f)[0])

    # FModel exports directory
    fmodel_output = settings.get("fmodel_output", "")
    if fmodel_output:
        for p_name in target_pals:
            for sub in ["Monster", "Pending Monster"]:
                d_fmodel = os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Animation", "Character", sub, p_name)
                if os.path.exists(d_fmodel):
                    for f in os.listdir(d_fmodel):
                        if f.startswith("AS_") and (f.endswith(".uasset") or f.endswith(".fbx") or f.endswith(".json")):
                            discovered_sequences.add(os.path.splitext(f)[0])

    return {
        "deps": results,
        "available_sequences": sorted(list(discovered_sequences))
    }

def autofill_stage_defaults(settings: dict, waza_id: str, clean_track: str, target_pal: str) -> dict:
    """
    Scrapes vanilla AnimNotifies (hitboxes, VFX, sound) from the original template Pal for a specific stage,
    caching results permanently to give the user a complete headstart.
    """
    clean_waza = waza_id.replace("EPalWazaID::", "").strip()
    suffix = clean_waza.replace("Unique_", "")
    parts = suffix.split("_")
    source_pal = parts[0] if parts else ""

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cache_path = os.path.join(repo_root, "deps", "unique_waza_cache.json")

    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    stage_cache_key = f"{clean_waza}::{clean_track}"
    if stage_cache_key in cache:
        res = dict(cache[stage_cache_key])
        res["suggested_sequence"] = f"AS_{target_pal}_{clean_track}"
        return res

    am_name = f"AM_{source_pal}_{clean_track}"
    as_name = f"AS_{source_pal}_{clean_track}"

    uasset_gui = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    temp_dir = os.path.join(repo_root, "temp_stage_autofill")

    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    extract_queue = [
        f"Pal/Content/Pal/Animation/Character/*/{source_pal}/{am_name}.uasset",
        f"Pal/Content/Pal/Animation/Character/*/{source_pal}/{am_name}.uexp",
        f"Pal/Content/Pal/Animation/Character/*/{source_pal}/{as_name}.uasset",
        f"Pal/Content/Pal/Animation/Character/*/{source_pal}/{as_name}.uexp",
        f"*{am_name}.uasset", f"*{am_name}.uexp",
        f"*{as_name}.uasset", f"*{as_name}.uexp"
    ]
    extract_game_files(settings, extract_queue, temp_dir, format_type="raw")

    from utils.anim_patcher.anim_discovery import scrape_notifies_from_json

    seq_notifies = []
    mont_notifies = []

    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"{am_name.lower()}.uasset":
                am_uasset = os.path.join(root, f)
                am_json = am_uasset.replace(".uasset", ".json")
                if decompile_uasset(uasset_gui, am_uasset, am_json, usmap_path):
                    mont_notifies = scrape_notifies_from_json(am_json, source="montage")
            elif f.lower() == f"{as_name.lower()}.uasset":
                as_uasset = os.path.join(root, f)
                as_json = as_uasset.replace(".uasset", ".json")
                if decompile_uasset(uasset_gui, as_uasset, as_json, usmap_path):
                    seq_notifies = scrape_notifies_from_json(as_json, source="sequence")

    shutil.rmtree(temp_dir, ignore_errors=True)

    stage_payload = {
        "clean_track": clean_track,
        "suggested_sequence": f"AS_{target_pal}_{clean_track}",
        "sequence_notifies": seq_notifies,
        "montage_notifies": mont_notifies
    }

    cache[stage_cache_key] = stage_payload
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

    return stage_payload
