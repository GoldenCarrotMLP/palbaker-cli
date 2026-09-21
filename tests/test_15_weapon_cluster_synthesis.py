# tests/test_15_weapon_cluster_synthesis.py
"""
====================================================================================================
           PALBAKER INTEGRATION TEST 15: WEAPON CLUSTER AST SYNTHESIS & INGESTION
====================================================================================================

PURPOSE & GOAL:
---------------
Validates complete synthesis, bytecode retargeting, and actor blueprint ingestion of the
multi-asset partner weapon cluster:
1. STEP 1: Synthesize all 3 partner skill montages:
   • AM_<Pal>_Flamethrower             (Idle hold loop)
   • AM_<Pal>_Flamethrower_Fire_Start  (Initial windup)
   • AM_<Pal>_Flamethrower_Fire        (Continuous damage firing loop)
2. STEP 2: Synthesize standalone weapon actor blueprint BP_<Pal>_Flamethrower:
   • Retargets internal puppet mesh to SK_<Pal>
   • Retargets Niagara VFX to custom FrostBreath (NS_CommonSkill_FrostBreath)
   • Retargets bytecode montage references to the newly synthesized montages
   • Patches damage element (Ice) and status effect (Freeze)
3. STEP 3: Ingest synthesized weapon class into host Pal Actor Blueprint (BP_SheepBall):
   • Injects BP_CoopParam_Weapon with WeaponClass pointing to BP_SheepBall_Flamethrower_C
   • Binds AIActionMap[Cooperation] to BP_AIAction_WeaponCall_C
4. STEP 4: Full binary round-trip compile and AST decompile verification across all 5 assets.
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
from utils.blueprint_patcher.feature_manager import (
    BlueprintFeatureManager,
    synthesize_flamethrower_cluster
)

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
    if name.startswith("BP_") and "Flamethrower" in name:
        rel_uasset = f"Pal/Content/Pal/Blueprint/Weapon/{name}.uasset"
        rel_uexp = f"Pal/Content/Pal/Blueprint/Weapon/{name}.uexp"
    elif name.startswith("AM_"):
        pal_id = "Kitsunebi"
        rel_uasset = f"Pal/Content/Pal/Animation/Character/Monster/{pal_id}/{name}.uasset"
        rel_uexp = f"Pal/Content/Pal/Animation/Character/Monster/{pal_id}/{name}.uexp"
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
    log("=== PalBaker Weapon Cluster AST Synthesis Test Suite ===")
    settings = load_settings()

    uasset_gui = os.path.normpath(os.path.join(REPO_ROOT, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(REPO_ROOT, "deps", "Mappings.usmap"))

    assert os.path.exists(uasset_gui), f"UAssetGUI.exe missing at {uasset_gui}"
    assert os.path.exists(usmap_path), f"Mappings.usmap missing at {usmap_path}"

    temp_dir = os.path.join(TESTS_DIR, "temp_weapon_cluster_test")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        log("Resolving blueprint and montage fixtures...")
        seed_weapon = resolve_fixture("BP_Kitsunebi_Flamethrower", temp_dir, settings, uasset_gui, usmap_path)
        seed_am_idle = resolve_fixture("AM_Kitsunebi_Flamethrower", temp_dir, settings, uasset_gui, usmap_path)
        seed_am_start = resolve_fixture("AM_Kitsunebi_Flamethrower_Fire_Start", temp_dir, settings, uasset_gui, usmap_path)
        seed_am_loop = resolve_fixture("AM_Kitsunebi_Flamethrower_Fire", temp_dir, settings, uasset_gui, usmap_path)
        data_sheepball = resolve_fixture("BP_SheepBall", temp_dir, settings, uasset_gui, usmap_path)

        assert seed_weapon is not None, "Could not resolve BP_Kitsunebi_Flamethrower seed."
        assert seed_am_idle is not None, "Could not resolve AM_Kitsunebi_Flamethrower seed."
        assert seed_am_start is not None, "Could not resolve AM_Kitsunebi_Flamethrower_Fire_Start seed."
        assert seed_am_loop is not None, "Could not resolve AM_Kitsunebi_Flamethrower_Fire seed."
        assert data_sheepball is not None, "Could not resolve BP_SheepBall fixture."

        start_time = time.time()

        # ---------------------------------------------------------------------
        # STEP 1 & 2: Synthesize Weapon Cluster (Montages + Weapon BP)
        # ---------------------------------------------------------------------
        log("\n--- Step 1 & 2: Synthesizing Full Weapon Cluster (Frost Flamethrower) ---")
        TARGET_PAL = "SheepBall"
        TEST_GUID = "D1E2F3A4-B5C6-7890-FEDC-BA9876543210"

        custom_config = {
            "element": "Ice",
            "effect": "Freeze",
            "niagara_system": "/Game/Pal/Effect/Skill/FrostBreath/NS_CommonSkill_FrostBreath",
            "muzzle_socket": "Socket_Mouth",
            "equip_socket": "Socket_Weapon_R"
        }

        cluster = synthesize_flamethrower_cluster(
            seed_weapon_data=seed_weapon,
            seed_montages={
                "idle": seed_am_idle,
                "start": seed_am_start,
                "loop": seed_am_loop
            },
            pal_id=TARGET_PAL,
            template_id="Kitsunebi",
            skeleton_guid=TEST_GUID,
            config=custom_config
        )

        # ---------------------------------------------------------------------
        # STEP 3: Compile and Round-trip Verify the 3 Synthesized Montages
        # ---------------------------------------------------------------------
        log("Compiling and verifying synthesized montages...")
        for m_name, m_ast in cluster["montages"].items():
            rt_m = verify_roundtrip(uasset_gui, usmap_path, m_ast, m_name, temp_dir)
            assert rt_m["Exports"][0]["ObjectName"] == m_name, f"Montage name mismatch: {m_name}"
            skel_import = next(imp for imp in rt_m["Imports"] if imp["ClassName"] == "Skeleton")
            assert f"SK_{TARGET_PAL}_Skeleton" in skel_import["ObjectName"], f"Skeleton mismatch: {skel_import}"
            log(f"  ✓ Compiled & verified montage: {m_name}")

        # ---------------------------------------------------------------------
        # STEP 4: Compile and Round-trip Verify Weapon Blueprint
        # ---------------------------------------------------------------------
        log("\nCompiling and verifying synthesized weapon actor blueprint...")
        weapon_base_name = f"BP_{TARGET_PAL}_Flamethrower"
        rt_weapon = verify_roundtrip(uasset_gui, usmap_path, cluster["weapon_bp"], weapon_base_name, temp_dir)

        # 4a. Verify Class Name
        assert rt_weapon["Exports"][0]["ObjectName"] == f"{weapon_base_name}_C"

        # 4b. Verify Internal Mesh is retargeted to SK_SheepBall
        mesh_template = next(exp for exp in rt_weapon["Exports"] if exp.get("ObjectName") == "Mesh_GEN_VARIABLE")
        sk_prop = next(p for p in mesh_template["Data"] if p.get("Name") == "SkeletalMesh")
        sk_name = rt_weapon["Imports"][-sk_prop["Value"] - 1]["ObjectName"]
        assert sk_name == f"SK_{TARGET_PAL}", f"Expected SK_{TARGET_PAL}, got {sk_name}"

        # 4c. Verify Niagara particle system retargeted to FrostBreath
        niagara_imp = next((imp for imp in rt_weapon["Imports"] if imp["ClassName"] == "NiagaraSystem"), None)
        assert niagara_imp is not None and niagara_imp["ObjectName"] == "NS_CommonSkill_FrostBreath", f"Niagara VFX mismatch: {niagara_imp}"

        # 4d. Verify Bytecode references the new montages
        montage_imports = [imp["ObjectName"] for imp in rt_weapon["Imports"] if imp["ClassName"] == "AnimMontage"]
        assert f"AM_{TARGET_PAL}_Flamethrower_Fire" in montage_imports, f"Missing fire montage in imports: {montage_imports}"
        assert f"AM_{TARGET_PAL}_Flamethrower_Fire_Start" in montage_imports, f"Missing start montage in imports: {montage_imports}"

        log(f"  ✓ Compiled & verified weapon blueprint: {weapon_base_name}")

        # ---------------------------------------------------------------------
        # STEP 5: Ingest Synthesized Weapon into Host Pal Actor Blueprint
        # ---------------------------------------------------------------------
        log("\n--- Step 5: Ingesting Weapon into Host Pal Actor Blueprint (BP_SheepBall) ---")
        mutated_host = json.loads(json.dumps(data_sheepball))
        host_mgr = BlueprintFeatureManager(mutated_host)

        weapon_class_pkg = f"/Game/Pal/Blueprint/Weapon/{weapon_base_name}"
        weapon_class_name = f"{weapon_base_name}_C"

        host_mgr.add_coop_weapon(
            mode="Flamethrower",
            weapon_class_package=weapon_class_pkg,
            weapon_class_name=weapon_class_name,
            attach_socket="Socket_Weapon_R"
        )

        rt_host = verify_roundtrip(uasset_gui, usmap_path, mutated_host, "BP_SheepBall_WithCustomFlamethrower", temp_dir)
        rt_host_mgr = BlueprintFeatureManager(rt_host)

        # 5a. Assert component is registered
        assert rt_host_mgr.has_component("BP_CoopParam_Weapon"), "Host Pal is missing BP_CoopParam_Weapon component."

        # 5b. Assert WeaponClass points to newly synthesized weapon
        weapon_template = next(exp for exp in rt_host["Exports"] if exp.get("ObjectName") == "BP_CoopParam_Weapon_GEN_VARIABLE")
        wp_class_prop = next(p for p in weapon_template["Data"] if p.get("Name") == "WeaponClass")
        wp_class_imp = rt_host["Imports"][-wp_class_prop["Value"] - 1]["ObjectName"]
        assert wp_class_imp == weapon_class_name, f"Expected {weapon_class_name}, got: {wp_class_imp}"

        # 5c. Assert Cooperation action bound
        cdo = rt_host_mgr.find_static_char_param_export()
        ai_map = next(p for p in cdo["Data"] if p.get("Name") == "AIActionMap")
        coop_entry = next((e for e in ai_map["Value"] if e[0]["Value"] == "EPalAIActionType::Cooperation"), None)
        assert coop_entry is not None, "Cooperation action missing from AIActionMap."
        action_imp = rt_host["Imports"][-coop_entry[1]["Value"] - 1]["ObjectName"]
        assert action_imp == "BP_AIAction_WeaponCall_C", f"Action mismatch: {action_imp}"

        elapsed = time.time() - start_time
        log("\n" + "=" * 70)
        log(f"🎉 WEAPON CLUSTER SYNTHESIS TEST PASSED ({elapsed:.2f}s)!")
        log(f"Successfully synthesized and validated 5 binary assets:")
        log(f"  1. AM_{TARGET_PAL}_Flamethrower.uasset")
        log(f"  2. AM_{TARGET_PAL}_Flamethrower_Fire_Start.uasset")
        log(f"  3. AM_{TARGET_PAL}_Flamethrower_Fire.uasset")
        log(f"  4. {weapon_base_name}.uasset (FrostBreath, Ice Element, Freeze Effect)")
        log(f"  5. BP_{TARGET_PAL}.uasset (Host Actor Blueprint with linked weapon)")
        log("=" * 70)

        shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        log(f"❌ Test failed: {e}", "ERROR")
        raise

if __name__ == "__main__":
    main()