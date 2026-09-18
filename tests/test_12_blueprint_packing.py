# tests/test_12_blueprint_packing.py
import os
import sys
import json
from test_helper import SettingsSandbox, log

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)

TARGET_PAL = "Katress_big_head"
TEMPLATE_PAL = "CatMage"

def main():
    log(f"=== PalBaker CLI Blueprint Engine Direct Test: {TARGET_PAL} ===")
    sandbox = SettingsSandbox(REPO_ROOT)
    sandbox.apply_profile("real")
    
    with open(os.path.join(REPO_ROOT, "manager_settings.json"), "r") as f:
        settings = json.load(f)

    sys.path.append(REPO_ROOT)
    from utils.blueprint_patcher import patch_actor_blueprint

    logs = []
    def log_cb(msg, cat="standard"):
        logs.append(f"[{cat.upper()}] {msg}")
        print(f"[{cat.upper()}] {msg}")

    success = patch_actor_blueprint(
        settings=settings,
        pal_id=TARGET_PAL,
        template_id=TEMPLATE_PAL,
        has_anims=True,
        category="Monster",
        base_pal=TARGET_PAL,
        log_callback=log_cb
    )

    if not success:
        raise AssertionError(f"Blueprint Patcher failed internally:\n" + "\n".join(logs))

    project_dir = os.path.dirname(settings["uproject"])
    project_name = os.path.splitext(os.path.basename(settings["uproject"]))[0]
    
    cooked_base = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal")
    
    log(f"Deep Scanning Cooked Base: {cooked_base}")
    found_files = []
    for root, _, files in os.walk(cooked_base):
        for f in files:
            found_files.append(os.path.join(root, f))
            
    log(f"Total Files Found in Cooked/Pal: {len(found_files)}")
    
    missing = []
    bp_found = any("BP_Katress_big_head.uasset" in f for f in found_files)
    abp_found = any("ABP_Katress_big_head.uasset" in f for f in found_files)
    bs_found = any("BS_" in f for f in found_files)
    am_found = any("AM_" in f for f in found_files)

    if not bp_found: missing.append("Actor Blueprint")
    if not abp_found: missing.append("AnimBlueprint")
    if not bs_found: missing.append("BlendSpaces")
    if not am_found: missing.append("AnimMontages")

    # Print out EXACTLY where the AM_ files went if they exist
    am_files_list = [f for f in found_files if "AM_" in os.path.basename(f)]
    if am_files_list:
        log(f"Found {len(am_files_list)} AM_ files!")
        log(f"Example AM_ path: {am_files_list[0]}")

    if missing:
        raise AssertionError(f"Missing expected blueprint elements: {missing}")

    log("✅ PASS: Unified Blueprint Patcher extracted, retargeted, and compiled all stack elements successfully.")
    sandbox.restore()

if __name__ == "__main__":
    main()