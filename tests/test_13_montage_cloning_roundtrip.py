# tests/test_13_montage_cloning_roundtrip.py
import os
import sys
import json
import shutil
import time

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.append(REPO_ROOT)

from utils.config import load_settings
from utils.extractor.core import extract_game_files
from utils.uasset_helper import (
    patch_montage_ast,
    decompile_uasset,
    compile_uasset,
    extract_notifies_from_ast,
    decode_extras_to_guid
)

def log(msg: str, category: str = "INFO"):
    print(f"[{category}] {msg}", flush=True)

TARGET_CATMAGE_MONTAGES = [
    "AM_CatMage_Architecture",
    "AM_CatMage_Carrying",
    "AM_CatMage_Carrying_Start",
    "AM_CatMage_CommonWork",
    "AM_CatMage_Cooking",
    "AM_CatMage_Damage",
    "AM_CatMage_Eat",
    "AM_CatMage_ElectricShock",
    "AM_CatMage_Encount",
    "AM_CatMage_FarSkill_Action",
    "AM_CatMage_FarSkill_ActionLoop",
    "AM_CatMage_FarSkill_End",
    "AM_CatMage_FarSkill_Start",
    "AM_CatMage_FarSkill_StartLoop",
    "AM_CatMage_FishPond",
    "AM_CatMage_GetUp_FrontDown",
    "AM_CatMage_Gunner",
    "AM_CatMage_Hit",
    "AM_CatMage_Petting",
    "AM_CatMage_Rest01",
    "AM_CatMage_Rest02",
    "AM_CatMage_Rest03",
    "AM_CatMage_SleepEnd",
    "AM_CatMage_SleepLoop",
    "AM_CatMage_SleepLoopTogether",
    "AM_CatMage_SleepStart",
    "AM_CatMage_Spa",
    "AM_CatMage_Walk"
]

def main():
    log("=== PalBaker AnimMontage Discovery & Mass-Cloning Roundtrip Test ===")
    settings = load_settings()

    uasset_gui = os.path.normpath(os.path.join(REPO_ROOT, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(REPO_ROOT, "deps", "Mappings.usmap"))
    seed_uasset = os.path.normpath(os.path.join(REPO_ROOT, "templates", "AM_Kitsunebi_Cooking.uasset"))

    assert os.path.exists(uasset_gui), f"UAssetGUI.exe missing at {uasset_gui}"
    assert os.path.exists(usmap_path), f"Mappings.usmap missing at {usmap_path}"
    assert os.path.exists(seed_uasset), f"Seed template missing at {seed_uasset}"

    temp_dir = os.path.join(TESTS_DIR, "temp_montage_mass_clone_test")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Step 1: Decompile Universal Seed Template
        log("1. Decompiling seed template (AM_Kitsunebi_Cooking)...")
        seed_json = os.path.join(temp_dir, "seed.json")
        assert decompile_uasset(uasset_gui, seed_uasset, seed_json, usmap_path), "Failed to decompile seed."

        with open(seed_json, "r", encoding="utf-8") as f_seed:
            seed_data = json.load(f_seed)

        seed_notifies = next((p for p in seed_data["Exports"][0]["Data"] if p.get("Name") == "Notifies"), None)
        assert seed_notifies and seed_notifies.get("Value"), "Seed does not contain a template notify struct."
        default_notify_template = seed_notifies["Value"][0]

        # Step 2: Extract CatMage Montages from Game Archives
        log("2. Extracting CatMage animation montages from game archives...")
        catmage_extract_dir = os.path.join(temp_dir, "catmage_extract")
        catmage_pattern = "Pal/Content/Pal/Animation/Character/Monster/CatMage/AM_CatMage_*"
        success, msg = extract_game_files(settings, [catmage_pattern], catmage_extract_dir, format_type="raw")
        assert success, f"Failed to extract CatMage montages: {msg}"

        catmage_uassets = []
        for root, _, files in os.walk(catmage_extract_dir):
            for f in files:
                if f.startswith("AM_CatMage_") and f.endswith(".uasset"):
                    catmage_uassets.append(os.path.join(root, f))
        catmage_uassets.sort()

        log(f"   Found {len(catmage_uassets)} extracted CatMage montages to test against.")
        assert len(catmage_uassets) > 0, "No CatMage montages were extracted."

        # Step 3: Iterate through every CatMage montage, clone template, inject notifies, serialize & round-trip verify
        log("\n3. Testing mass-synthesis, notify injection, serialization, and roundtrip verification...")
        TARGET_PAL_ID = "Katress_big_head"
        TEST_SKELETON_GUID = "D1E2F3A4-B5C6-7890-FEDC-BA9876543210"

        passed_count = 0
        total_notifies_tested = 0
        start_time = time.time()

        for idx, cm_uasset in enumerate(catmage_uassets, start=1):
            cm_filename = os.path.splitext(os.path.basename(cm_uasset))[0]
            anim_name = cm_filename.replace("AM_CatMage_", "")

            # 3a. Decompile CatMage source montage with Mappings
            cm_json = os.path.join(temp_dir, f"src_{cm_filename}.json")
            assert decompile_uasset(uasset_gui, cm_uasset, cm_json, usmap_path), f"Failed to decompile {cm_filename}"

            with open(cm_json, "r", encoding="utf-8") as f_cm:
                cm_ast = json.load(f_cm)

            # 3b. Read original SequenceLength & Notifies
            cm_props = cm_ast["Exports"][0].get("Data", [])
            seq_len_prop = next((p for p in cm_props if p.get("Name") == "SequenceLength"), None)
            duration = float(seq_len_prop["Value"]) if seq_len_prop else 2.0

            source_notifies = extract_notifies_from_ast(cm_ast)
            total_notifies_tested += len(source_notifies)

            # 3c. Clone & Mutate the seed template into a brand new standalone montage
            cloned_data = patch_montage_ast(
                seed_data,
                template_id="Kitsunebi",
                target_pal=TARGET_PAL_ID,
                anim_name=anim_name,
                duration=duration,
                skeleton_guid=TEST_SKELETON_GUID,
                notifies=source_notifies,
                template_notify=default_notify_template
            )

            cloned_json = os.path.join(temp_dir, f"AM_{TARGET_PAL_ID}_{anim_name}.json")
            with open(cloned_json, "w", encoding="utf-8") as f_cloned:
                json.dump(cloned_data, f_cloned, indent=2)

            # 3d. Compile to binary .uasset
            cloned_uasset = os.path.join(temp_dir, f"AM_{TARGET_PAL_ID}_{anim_name}.uasset")
            assert compile_uasset(uasset_gui, cloned_json, cloned_uasset, usmap_path), f"Failed to compile AM_{TARGET_PAL_ID}_{anim_name}"

            # 3e. Decompile the compiled binary back to JSON (Round-Trip)
            roundtrip_json = os.path.join(temp_dir, f"AM_{TARGET_PAL_ID}_{anim_name}_roundtrip.json")
            assert decompile_uasset(uasset_gui, cloned_uasset, roundtrip_json, usmap_path), f"Failed to round-trip decompile {anim_name}"

            with open(roundtrip_json, "r", encoding="utf-8") as f_rt:
                rt_ast = json.load(f_rt)

            # 3f. Strict Verification
            rt_export = rt_ast["Exports"][0]
            assert rt_export["ObjectName"] == f"AM_{TARGET_PAL_ID}_{anim_name}", f"[{anim_name}] ObjectName mismatch."
            assert decode_extras_to_guid(rt_export.get("Extras", "")) == TEST_SKELETON_GUID, f"[{anim_name}] Skeleton GUID mismatch."

            rt_props = rt_export.get("Data", [])
            rt_seq_len = next((p for p in rt_props if p.get("Name") == "SequenceLength"), None)
            assert rt_seq_len and abs(float(rt_seq_len["Value"]) - duration) < 0.001, f"[{anim_name}] SequenceLength mismatch."

            # Verify every notify matches the original CatMage notify
            rt_notifies = extract_notifies_from_ast(rt_ast)
            assert len(rt_notifies) == len(source_notifies), (
                f"[{anim_name}] Notify count mismatch: expected {len(source_notifies)}, got {len(rt_notifies)}"
            )

            for n_idx, (exp, act) in enumerate(zip(source_notifies, rt_notifies)):
                assert exp["Name"] == act["Name"], (
                    f"[{anim_name}] Notify #{n_idx} name mismatch: expected '{exp['Name']}', got '{act['Name']}'"
                )
                assert abs(exp["Time"] - act["Time"]) < 0.001, (
                    f"[{anim_name}] Notify #{n_idx} time mismatch: expected {exp['Time']}, got {act['Time']}"
                )
                assert abs(exp["Duration"] - act["Duration"]) < 0.001, (
                    f"[{anim_name}] Notify #{n_idx} duration mismatch: expected {exp['Duration']}, got {act['Duration']}"
                )

            passed_count += 1
            log(f"   [{idx:>2}/{len(catmage_uassets)}] ✓ {anim_name:<24} | Length: {duration:>6.2f}s | Notifies: {len(source_notifies):>2}")

        elapsed = time.time() - start_time
        log("\n" + "=" * 70)
        log(f"🎉 SUCCESS! Synthesized, compiled, and verified {passed_count}/{len(catmage_uassets)} montages.")
        log(f"Total AnimNotifies Roundtripped: {total_notifies_tested}")
        log(f"Elapsed Time: {elapsed:.2f}s")
        log("=" * 70)

        shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        log(f"❌ Test failed: {e}", "ERROR")
        raise

if __name__ == "__main__":
    main()