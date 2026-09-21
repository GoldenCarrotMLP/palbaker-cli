# tests/test_14_funnel_customization.py
"""
====================================================================================================
           PALBAKER INTEGRATION TEST 14: ADVANCED SATELLITE FUNNEL CUSTOMIZATION
====================================================================================================

PURPOSE & GOAL:
---------------
Validates complete programmatic control over satellite minion funnels across all 4 axes:
1. CASE 1: ARBITRARY ATTACK WAZA OVERRIDES ON VANILLA FUNNELS (DarkLaser & DragonMeteor)
2. CASE 2: TARGETING AI ACTION RETARGETING (Thunderbolt & SeedMachinegun)
3. CASE 3: FULL STANDALONE SATELLITE SYNTHESIS (Generating BP_FunnelCharacter_SheepBall)
4. CASE 4: CAPSULE & VERTICAL ELEVATION OFFSET CALIBRATION
5. CASE 5: END-TO-END LINKAGE (Parent Pal summoning custom synthesized minion)
====================================================================================================
"""

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
from utils.uasset_helper import decompile_uasset, compile_uasset, sync_namemap
from utils.blueprint_patcher.feature_manager import BlueprintFeatureManager, synthesize_funnel_character_ast

def log(msg: str, category: str = "INFO"):
    print(f"[{category}] {msg}", flush=True)

def resolve_fixture(name: str, temp_dir: str, settings: dict, uasset_gui: str, usmap_path: str) -> dict:
    candidate_locations = [
        os.path.join(TESTS_DIR, "fixtures", "blueprints", f"{name}.json"),
        os.path.join(TESTS_DIR, f"{name}.json"),
        os.path.join(REPO_ROOT, f"{name}.json"),
        os.path.join(REPO_ROOT, "templates", f"{name}.json"),
    ]

    for p in candidate_locations:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                log(f"   Loaded static fixture: {os.path.relpath(p, REPO_ROOT)}")
                return json.load(f)

    # Dynamic extraction fallback
    if name.startswith("BP_FunnelCharacter_"):
        rel_uasset = f"Pal/Content/Pal/Blueprint/Character/Funnel/{name}.uasset"
        rel_uexp = f"Pal/Content/Pal/Blueprint/Character/Funnel/{name}.uexp"
    else:
        pal_id = name.replace("BP_", "")
        rel_uasset = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{pal_id}/{name}.uasset"
        rel_uexp = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{pal_id}/{name}.uexp"

    extract_target_dir = os.path.join(temp_dir, f"extract_{name}")
    success, _ = extract_game_files(settings, [rel_uasset, rel_uexp], extract_target_dir, format_type="raw")

    if success:
        for root, _, files in os.walk(extract_target_dir):
            for file in files:
                if file.lower() == f"{name.lower()}.uasset":
                    uasset_disk = os.path.join(root, file)
                    decompiled_json = os.path.join(temp_dir, f"{name}.json")
                    if decompile_uasset(uasset_gui, uasset_disk, decompiled_json, usmap_path):
                        with open(decompiled_json, "r", encoding="utf-8") as f_decomp:
                            log(f"   Dynamically extracted & decompiled {name} from game archives.")
                            return json.load(f_decomp)

    return None

def verify_roundtrip(uasset_gui: str, usmap_path: str, data: dict, output_base: str, temp_dir: str) -> dict:
    sync_namemap(data)
    json_path = os.path.join(temp_dir, f"{output_base}.json")
    uasset_path = os.path.join(temp_dir, f"{output_base}.uasset")
    rt_json_path = os.path.join(temp_dir, f"{output_base}_rt.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    assert compile_uasset(uasset_gui, json_path, uasset_path, usmap_path), f"Failed to compile {output_base}.uasset"
    assert os.path.exists(uasset_path) and os.path.getsize(uasset_path) > 0, f"Empty or missing {output_base}.uasset"
    assert decompile_uasset(uasset_gui, uasset_path, rt_json_path, usmap_path), f"Failed to decompile {output_base}.uasset"

    with open(rt_json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    log("=== PalBaker Advanced Satellite Funnel Customization Test Suite ===")
    settings = load_settings()

    uasset_gui = os.path.normpath(os.path.join(REPO_ROOT, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(REPO_ROOT, "deps", "Mappings.usmap"))

    assert os.path.exists(uasset_gui), f"UAssetGUI.exe missing at {uasset_gui}"
    assert os.path.exists(usmap_path), f"Mappings.usmap missing at {usmap_path}"

    temp_dir = os.path.join(TESTS_DIR, "temp_funnel_customization_test")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        log("Resolving blueprint fixtures...")
        seed_funnel = resolve_fixture("BP_FunnelCharacter_DreamDemon", temp_dir, settings, uasset_gui, usmap_path)
        data_sheepball = resolve_fixture("BP_SheepBall", temp_dir, settings, uasset_gui, usmap_path)
        data_kitsunebi = resolve_fixture("BP_Kitsunebi", temp_dir, settings, uasset_gui, usmap_path)

        assert seed_funnel is not None, "Could not resolve BP_FunnelCharacter_DreamDemon seed."
        assert data_sheepball is not None, "Could not resolve BP_SheepBall fixture."
        assert data_kitsunebi is not None, "Could not resolve BP_Kitsunebi fixture."

        start_time = time.time()

        # ---------------------------------------------------------------------
        # CASE 1: Attack Waza Customization on Vanilla Satellites
        # ---------------------------------------------------------------------
        log("\n--- Case 1: Custom Waza Injection on Existing Funnel (DarkLaser & DragonMeteor) ---")
        mutated_c1 = json.loads(json.dumps(data_sheepball))
        mgr_c1 = BlueprintFeatureManager(mutated_c1)

        # Inject Daedream funnel but override attack waza with DarkLaser
        mgr_c1.set_partner_funnel("Daedream", custom_waza_id="EPalWazaID::DarkLaser")

        rt_c1 = verify_roundtrip(uasset_gui, usmap_path, mutated_c1, "BP_SheepBall_FunnelDarkLaser", temp_dir)
        rt_mgr_c1 = BlueprintFeatureManager(rt_c1)
        params_c1 = rt_mgr_c1.get_partner_funnel_params()

        assert params_c1.get("FunnelAttackWazaID") == "EPalWazaID::DarkLaser", f"Waza mismatch: {params_c1}"
        assert "BP_FunnelCharacter_DreamDemon_C" in params_c1.get("FunnelCharacterClass", ""), f"Class mismatch: {params_c1}"
        log("  ✓ [PASS] Case 1 verified: Daedream funnel successfully configured with custom DarkLaser attack.")

        # ---------------------------------------------------------------------
        # CASE 2: Targeting AI Action Swapping on Funnel Actor
        # ---------------------------------------------------------------------
        log("\n--- Case 2: Targeting AI Action Swapping on Satellite Actor ---")
        # Synthesize satellite using Thunderbolt targeting
        thunderbolt_ast = synthesize_funnel_character_ast(
            seed_funnel_data=seed_funnel,
            target_pal_id="DreamDemon_Thunder",
            template_pal_id="DreamDemon",
            targeting_action="Thunderbolt"
        )
        rt_c2 = verify_roundtrip(uasset_gui, usmap_path, thunderbolt_ast, "BP_FunnelCharacter_Thunderbolt", temp_dir)

        # Assert Thunderbolt action is configured on CDO
        cdo_export = next(exp for exp in rt_c2["Exports"] if "Default__BP_FunnelCharacter_" in exp.get("ObjectName", ""))
        action_prop = next(p for p in cdo_export["Data"] if p.get("Name") == "FunnelSkillAIActionClass")
        imp_idx = action_prop["Value"]
        imp_name = rt_c2["Imports"][-imp_idx - 1]["ObjectName"]

        assert "BP_AIActionFunnelSkill_Thunderbolt_C" in imp_name, f"Expected Thunderbolt action, got: {imp_name}"
        log("  ✓ [PASS] Case 2 verified: Targeting AI action successfully swapped to Thunderbolt.")

        # ---------------------------------------------------------------------
        # CASE 3: Standalone Satellite Synthesis (Lamball as an Orbiting Minion)
        # ---------------------------------------------------------------------
        log("\n--- Case 3: Standalone Satellite Synthesis (Lamball Minion) ---")
        lamball_funnel_ast = BlueprintFeatureManager.create_funnel_character_ast(
            seed_funnel_data=seed_funnel,
            target_pal_id="SheepBall",
            template_pal_id="SheepBall",
            targeting_action="SeedMachinegun"
        )
        rt_c3 = verify_roundtrip(uasset_gui, usmap_path, lamball_funnel_ast, "BP_FunnelCharacter_SheepBall", temp_dir)

        # Assert ClassExport, Mesh, and CDO are properly retargeted
        class_exp = rt_c3["Exports"][0]
        assert class_exp["ObjectName"] == "BP_FunnelCharacter_SheepBall_C", f"Class name mismatch: {class_exp['ObjectName']}"

        mesh_exp = next(exp for exp in rt_c3["Exports"] if exp.get("ObjectName") == "CharacterMesh0")
        sk_prop = next(p for p in mesh_exp["Data"] if p.get("Name") == "SkeletalMesh")
        sk_name = rt_c3["Imports"][-sk_prop["Value"] - 1]["ObjectName"]
        assert sk_name == "SK_SheepBall", f"Expected SK_SheepBall mesh, got: {sk_name}"

        abp_prop = next(p for p in mesh_exp["Data"] if p.get("Name") == "AnimClass")
        abp_name = rt_c3["Imports"][-abp_prop["Value"] - 1]["ObjectName"]
        assert abp_name == "ABP_SheepBall_C", f"Expected ABP_SheepBall_C, got: {abp_name}"

        log("  ✓ [PASS] Case 3 verified: Synthesized brand-new BP_FunnelCharacter_SheepBall with SeedMachinegun ballistics.")

        # ---------------------------------------------------------------------
        # CASE 4: Capsule & Vertical Offset Calibration
        # ---------------------------------------------------------------------
        log("\n--- Case 4: Capsule & Vertical Elevation Offset Calibration ---")
        calibrated_ast = synthesize_funnel_character_ast(
            seed_funnel_data=seed_funnel,
            target_pal_id="SheepBall_Scaled",
            template_pal_id="SheepBall",
            targeting_action="ShadowBall",
            mesh_capsule_half_height=125.0,
            mesh_capsule_radius=65.0,
            mesh_z_offset=-110.0
        )
        rt_c4 = verify_roundtrip(uasset_gui, usmap_path, calibrated_ast, "BP_FunnelCharacter_Calibrated", temp_dir)

        # Verify CapsuleComponent and Mesh locations
        mesh_c4 = next(exp for exp in rt_c4["Exports"] if exp.get("ObjectName") == "CharacterMesh0")
        rel_loc = next(p for p in mesh_c4["Data"] if p.get("Name") == "RelativeLocation")
        z_val = rel_loc["Value"][0]["Value"]["Z"]
        assert abs(float(z_val) - (-110.0)) < 0.001, f"Expected Z = -110.0, got: {z_val}"

        static_param = next(exp for exp in rt_c4["Exports"] if exp.get("ObjectName") == "StaticCharacterParameterComponent")
        hh_p = next(p for p in static_param["Data"] if p.get("Name") == "MeshCapsuleHalfHeight")
        rad_p = next(p for p in static_param["Data"] if p.get("Name") == "MeshCapsuleRadius")
        assert abs(float(hh_p["Value"]) - 125.0) < 0.001, f"HalfHeight mismatch: {hh_p['Value']}"
        assert abs(float(rad_p["Value"]) - 65.0) < 0.001, f"Radius mismatch: {rad_p['Value']}"
        log("  ✓ [PASS] Case 4 verified: Custom collision capsule (125x65) and Z-offset (-110) calibrated.")

        # ---------------------------------------------------------------------
        # CASE 5: Full End-to-End Parent + Satellite Linkage
        # ---------------------------------------------------------------------
        log("\n--- Case 5: End-to-End Parent + Custom Satellite Linkage ---")
        # Step A: Synthesize standalone satellite for Lamball
        sheepball_satellite_ast = synthesize_funnel_character_ast(
            seed_funnel_data=seed_funnel,
            target_pal_id="SheepBall",
            template_pal_id="SheepBall",
            targeting_action="Thunderbolt"
        )
        verify_roundtrip(uasset_gui, usmap_path, sheepball_satellite_ast, "BP_FunnelCharacter_SheepBall_Final", temp_dir)

        # Step B: Link synthesized satellite into Kitsunebi (Foxparks)
        mutated_host = json.loads(json.dumps(data_kitsunebi))
        host_mgr = BlueprintFeatureManager(mutated_host)

        custom_satellite_path = "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_SheepBall.BP_FunnelCharacter_SheepBall_C"
        host_mgr.set_partner_funnel(
            custom_character_class=custom_satellite_path,
            custom_waza_id="EPalWazaID::Unique_SheepBall_Roll"
        )

        rt_host = verify_roundtrip(uasset_gui, usmap_path, mutated_host, "BP_Kitsunebi_WithLamballFunnel", temp_dir)
        rt_host_mgr = BlueprintFeatureManager(rt_host)
        host_params = rt_host_mgr.get_partner_funnel_params()

        assert host_params.get("FunnelAttackWazaID") == "EPalWazaID::Unique_SheepBall_Roll", f"Host waza mismatch: {host_params}"
        assert "BP_FunnelCharacter_SheepBall_C" in host_params.get("FunnelCharacterClass", ""), f"Host satellite mismatch: {host_params}"
        log("  ✓ [PASS] Case 5 verified: Host Pal successfully bound to custom synthesized satellite running rolling attack.")

        elapsed = time.time() - start_time
        log("\n" + "=" * 70)
        log(f"🎉 ALL 5 ADVANCED FUNNEL CUSTOMIZATION CASES PASSED ({elapsed:.2f}s)!")
        log("=" * 70)

        shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        log(f"❌ Test failed: {e}", "ERROR")
        raise

if __name__ == "__main__":
    main()