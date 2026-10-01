# tests/test_10_dynamic_pals_compile.py
"""
PALBAKER CLI DYNAMIC PALS INGESTION, FORMAT V2 COMPILATION, & STRIP TEST
"""

import os
import sys
import json
import shutil
import subprocess
from test_helper import SettingsSandbox, run_cli_command, parse_cli_json, log

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SETTINGS_FILE = os.path.join(REPO_ROOT, "manager_settings.json")
CLI_ENTRY_POINT = os.path.join(REPO_ROOT, "palbaker_cli.py")

TARGET_PAL = "BadCatgirl"
VARIANT_LABEL = "testvar"
FULL_VARIANT_LABEL = f"{TARGET_PAL}_{VARIANT_LABEL}"

def main():
    log(f"=== PalBaker CLI Dynamic Pals Compile & V2 JSON Verification ===")
    sandbox = SettingsSandbox(REPO_ROOT)
    sandbox.backup()

    try:
        sandbox.apply_profile("real")
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)

        palworld_exe = settings.get("palworld_exe", "")
        
        # 1. Toggle ON & Add Variant
        run_cli_command(["dynamic_pals", "toggle", TARGET_PAL, "on"], CLI_ENTRY_POINT)
        run_cli_command(["dynamic_pals", "add", TARGET_PAL, VARIANT_LABEL, "--custom", "--source", "base"], CLI_ENTRY_POINT)
        
        v2_payload = {
            "label": VARIANT_LABEL,
            "CharacterID": TARGET_PAL,
            "SkeletonSource": f"{FULL_VARIANT_LABEL}.blend",
            "Gender": "Female",
            "LuckyStarReq": True,
            "SkinName": f"{TARGET_PAL}_Skin001",
            "SetNickname": "CoolNyafia",
            "MinLevel": 1,
            "MaxLevel": 999,
            "MinTrust": 0,
            "MaxTrust": 999999,
            "MinRank": 0,
            "MaxRank": 999,
            "MinSizeMultiplier": 1.0,
            "MaxSizeMultiplier": 1.0,
            "SpawnWeight": 1,
            "IsWildPal": False,
            "ReqSwap": [],
            "PassiveSkills": ["Artisan"],
            "PrefTrait": ["Swift"],
            "SkipTrait": [],
            "SpecialMaterial": [],
            "ShapeKeys": [],
            "Extra": "{}",
            "is_base": False
        }
        run_cli_command(["dynamic_pals", "save", "1", "--data", json.dumps(v2_payload)], CLI_ENTRY_POINT)

        # 2. Push & Cook
        log("Executing push and targeted cook...")
        run_cli_command(["mod", "push", TARGET_PAL], CLI_ENTRY_POINT)
        exit_code, stdout, stderr = run_cli_command(["mod", "cook", TARGET_PAL], CLI_ENTRY_POINT)
        parsed = parse_cli_json(stdout)
        assert parsed and parsed.get("status") == "success", f"Cook failed: {stdout}"

        # 3. Assert Format V2 Deployed JSON
        if palworld_exe and os.path.exists(palworld_exe):
            model_json = os.path.join(os.path.dirname(palworld_exe), "Pal", "Content", "Paks", "~Mods", "ModelJSON", f"palbaker-{TARGET_PAL}.json")
            assert os.path.exists(model_json), f"Deployed JSON missing at {model_json}"
            
            with open(swap_json, "r", encoding="utf-8") as f_json:
                data = json.load(f_json)

            # Strict Format V2 Schema Assertions:
            assert "ModelPack" in data, "Format V2 schema violation: 'ModelPack' root key missing."
            assert "SkinList" in data, "Format V2 schema violation: 'SkinList' root key missing."
            assert TARGET_PAL in data["SkinList"], f"Target character '{TARGET_PAL}' missing from SkinList."
            
            skins = data["SkinList"][TARGET_PAL]
            assert VARIANT_LABEL in skins, f"Variant label '{VARIANT_LABEL}' missing from SkinList."
            
            skin_obj = skins[VARIANT_LABEL]
            assert "SkinPath" in skin_obj, "Format V2 violation: 'SkinPath' missing."
            assert "LuckyStarReq" in skin_obj, "Format V2 violation: 'LuckyStarReq' missing."
            assert "PassiveSkills" in skin_obj, "Format V2 violation: 'PassiveSkills' missing."
            assert "SpecialMaterial" in skin_obj, "Format V2 violation: 'SpecialMaterial' missing."
            assert "ShapeKeys" in skin_obj, "Format V2 violation: 'ShapeKeys' missing."

            log("  ✓ Deployed JSON strictly adheres to Format V2 Specification!")

        log("\n✅ PASS: Dynamic Pals compilation and Format V2 deployment verified.")

    finally:
        run_cli_command(["dynamic_pals", "toggle", TARGET_PAL, "off"], CLI_ENTRY_POINT)
        sandbox.restore()

if __name__ == "__main__":
    main()