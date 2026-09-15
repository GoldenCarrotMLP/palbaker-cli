# tests/test_08_dynamic_pals.py
"""
PALBAKER CLI INTEGRATION TEST 08: DYNAMIC PALS LIFECYCLE
"""

import os
import sys
import json
import shutil
from test_helper import SettingsSandbox, run_cli_command, parse_cli_json, log

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SETTINGS_FILE = os.path.join(REPO_ROOT, "manager_settings.json")
CLI_ENTRY_POINT = os.path.join(REPO_ROOT, "palbaker_cli.py")

TARGET_PAL = "BadCatgirl"
VARIANT_LABEL = "testvar"
FULL_VARIANT_LABEL = f"{TARGET_PAL}_{VARIANT_LABEL}"

def main():
    log(f"=== PalBaker CLI Dynamic Pals Lifecycle: {TARGET_PAL} ===")
    sandbox = SettingsSandbox(REPO_ROOT)
    sandbox.backup()

    target_dyn_dir = None
    try:
        sandbox.apply_profile("real")
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)

        fmodel_output = settings.get("fmodel_output", "")
        target_dir = os.path.normpath(os.path.join(
            fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", TARGET_PAL
        ))
        target_dyn_dir = os.path.normpath(os.path.join(
            fmodel_output, "Exports", "Pal", "Content", "Palbaker", "Model", "Character", "Monster", TARGET_PAL
        ))

        # 1. Toggle ON
        log("Toggling Dynamic Pals framework ON...")
        exit_code, stdout, stderr = run_cli_command(["dynamic_pals", "toggle", TARGET_PAL, "on"], CLI_ENTRY_POINT)
        parsed = parse_cli_json(stdout)
        assert parsed and parsed.get("status") == "success", f"Toggle ON failed: {stdout}"

        manifest_path = os.path.normpath(os.path.join(target_dir, f"{TARGET_PAL}_dynamic_pals.json"))
        assert os.path.exists(manifest_path), f"Manifest not created: {manifest_path}"

        # 2. List
        log("Querying Dynamic Pals variants list...")
        exit_code, stdout, stderr = run_cli_command(["dynamic_pals", "list", TARGET_PAL], CLI_ENTRY_POINT)
        parsed = parse_cli_json(stdout)
        assert parsed and any(v.get("label") == "base" for v in parsed.get("data", [])), "Base variant missing."

        # 3. Add Custom Variant
        log(f"Adding variant '{VARIANT_LABEL}'...")
        exit_code, stdout, stderr = run_cli_command(["dynamic_pals", "add", TARGET_PAL, VARIANT_LABEL, "--custom", "--source", "base"], CLI_ENTRY_POINT)
        parsed = parse_cli_json(stdout)
        assert parsed and parsed.get("status") == "success", f"Add variant failed: {stdout}"

        # 4. Save Format V2 Variant
        log("Saving variant properties in Format V2...")
        v2_payload = {
            "label": VARIANT_LABEL,
            "CharacterID": TARGET_PAL,
            "SkeletonSource": f"{FULL_VARIANT_LABEL}.blend",
            "Gender": "Female",
            "LuckyStarReq": True,
            "SkinName": f"{TARGET_PAL}_Skin001",
            "SetNickname": "CoolNyafia",
            "MinLevel": 10,
            "MaxLevel": 50,
            "MinTrust": 0,
            "MaxTrust": 1000,
            "MinRank": 1,
            "MaxRank": 4,
            "MinSizeMultiplier": 0.8,
            "MaxSizeMultiplier": 1.2,
            "SpawnWeight": 5,
            "IsWildPal": True,
            "ReqSwap": [],
            "PassiveSkills": ["Artisan"],
            "PrefTrait": ["Swift"],
            "SkipTrait": ["Coward"],
            "SpecialMaterial": [],
            "ShapeKeys": [],
            "Extra": "{}",
            "is_base": False
        }
        exit_code, stdout, stderr = run_cli_command(["dynamic_pals", "save", "1", "--data", json.dumps(v2_payload)], CLI_ENTRY_POINT)
        parsed = parse_cli_json(stdout)
        assert parsed and parsed.get("status") == "success", f"Save variant failed: {stdout}"

        # Verify Manifest Serialization
        with open(manifest_path, "r", encoding="utf-8") as f_man:
            manifest_state = json.load(f_man)
        saved_v = manifest_state.get("variants", {}).get(FULL_VARIANT_LABEL, {})
        assert saved_v.get("LuckyStarReq") is True, "LuckyStarReq failed to serialize."
        assert saved_v.get("PassiveSkills") == ["Artisan"], "PassiveSkills failed to serialize."

        # 5. Delete Variant
        log("Deleting variant...")
        exit_code, stdout, stderr = run_cli_command(["dynamic_pals", "delete", TARGET_PAL, "1"], CLI_ENTRY_POINT)
        parsed = parse_cli_json(stdout)
        assert parsed and parsed.get("status") == "success", f"Delete variant failed: {stdout}"

        # 6. Toggle OFF
        log("Toggling Dynamic Pals framework OFF...")
        exit_code, stdout, stderr = run_cli_command(["dynamic_pals", "toggle", TARGET_PAL, "off"], CLI_ENTRY_POINT)
        parsed = parse_cli_json(stdout)
        assert parsed and parsed.get("status") == "success", f"Toggle OFF failed: {stdout}"

        log("\n✅ PASS: Dynamic Pals lifecycle verified.")

    finally:
        sandbox.restore()

if __name__ == "__main__":
    main()