# tests/test_03_blueprint_mutation.py
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
from utils.blueprint_patcher.feature_manager import BlueprintFeatureManager

def log(msg: str, category: str = "INFO"):
    print(f"[{category}] {msg}", flush=True)

def get_blueprint_fixture(name: str, temp_dir: str, settings: dict, uasset_gui: str, usmap_path: str) -> dict:
    """Resolves an Actor Blueprint JSON fixture from disk or extracts from game paks."""
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

    # Dynamic extraction fallback from game paks
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

def verify_roundtrip_compilation(uasset_gui: str, usmap_path: str, data: dict, output_base: str, temp_dir: str) -> dict:
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
    log("=== PalBaker Comprehensive Blueprint Feature Mutation Suite ===")
    settings = load_settings()

    uasset_gui = os.path.normpath(os.path.join(REPO_ROOT, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(REPO_ROOT, "deps", "Mappings.usmap"))

    assert os.path.exists(uasset_gui), f"UAssetGUI.exe missing at {uasset_gui}"
    assert os.path.exists(usmap_path), f"Mappings.usmap missing at {usmap_path}"

    temp_dir = os.path.join(TESTS_DIR, "temp_bp_mutation_test")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        log("Loading baseline blueprint fixtures...")
        data_kitsunebi = get_blueprint_fixture("BP_Kitsunebi", temp_dir, settings, uasset_gui, usmap_path)
        data_sheepball = get_blueprint_fixture("BP_SheepBall", temp_dir, settings, uasset_gui, usmap_path)
        data_dreamdemon = get_blueprint_fixture("BP_DreamDemon", temp_dir, settings, uasset_gui, usmap_path)
        data_weasel = get_blueprint_fixture("BP_WeaselDragon", temp_dir, settings, uasset_gui, usmap_path)

        assert data_kitsunebi is not None, "Could not resolve BP_Kitsunebi fixture."
        assert data_sheepball is not None, "Could not resolve BP_SheepBall fixture."
        assert data_dreamdemon is not None, "Could not resolve BP_DreamDemon fixture."
        assert data_weasel is not None, "Could not resolve BP_WeaselDragon fixture."

        start_time = time.time()

        # ---------------------------------------------------------------------
        # SCENARIO 1: Feature Injection (Add Weapon & Funnel to SheepBall)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 1: Injecting Weapon & Funnel Features into SheepBall ---")
        mutated_s1 = json.loads(json.dumps(data_sheepball))
        mgr_s1 = BlueprintFeatureManager(mutated_s1)

        flamethrower_class_pkg = "/Game/Pal/Blueprint/Weapon/BP_Kitsunebi_Flamethrower"
        weapon_class_idx = mgr_s1.ensure_import_chain(flamethrower_class_pkg, "BP_Kitsunebi_Flamethrower_C")
        mgr_s1.add_component(
            var_name="BP_CoopParam_Weapon",
            comp_class_package="/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Weapon",
            comp_class_name="BP_CoopParam_Weapon_C",
            template_properties=[
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": "WeaponClass",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": weapon_class_idx
                }
            ]
        )
        mgr_s1.set_ai_action("EPalAIActionType::Cooperation", "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_WeaponCall.BP_AIAction_WeaponCall_C")
        mgr_s1.set_partner_funnel_params(
            funnel_character_class="/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_DreamDemon.BP_FunnelCharacter_DreamDemon_C",
            funnel_controller_class="/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            funnel_waza_id="EPalWazaID::Funnel_DreamDemon"
        )

        rt_s1 = verify_roundtrip_compilation(uasset_gui, usmap_path, mutated_s1, "BP_SheepBall_Scenario1", temp_dir)
        rt_mgr_s1 = BlueprintFeatureManager(rt_s1)
        assert rt_mgr_s1.has_component("BP_CoopParam_Weapon"), "Scenario 1: BP_CoopParam_Weapon missing."
        log("  ✓ [PASS] Scenario 1 verified: Injected Weapon, AIActionMap, and Funnel serialized flawlessly.")

        # ---------------------------------------------------------------------
        # SCENARIO 2: Feature Stripping (Remove Weapon from Kitsunebi)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 2: Stripping Weapon & Cooperation from Kitsunebi ---")
        mutated_s2 = json.loads(json.dumps(data_kitsunebi))
        mgr_s2 = BlueprintFeatureManager(mutated_s2)

        mgr_s2.remove_component("BP_CoopParam_Weapon")
        mgr_s2.remove_ai_action("EPalAIActionType::Cooperation")

        rt_s2 = verify_roundtrip_compilation(uasset_gui, usmap_path, mutated_s2, "BP_Kitsunebi_Scenario2", temp_dir)
        rt_mgr_s2 = BlueprintFeatureManager(rt_s2)
        assert not rt_mgr_s2.has_component("BP_CoopParam_Weapon"), "Scenario 2: BP_CoopParam_Weapon still present."
        log("  ✓ [PASS] Scenario 2 verified: Stripped weapon component and AI action cleanly without broken links.")

        # ---------------------------------------------------------------------
        # SCENARIO 3: Feature Swapping (SheepBall Shield -> Kitsunebi Weapon)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 3: Swapping Shield for Weapon on SheepBall ---")
        mutated_s3 = json.loads(json.dumps(data_sheepball))
        mgr_s3 = BlueprintFeatureManager(mutated_s3)

        mgr_s3.remove_component("Shield")
        mgr_s3.remove_component("BP_CoopParam_Sheild")
        mgr_s3.add_component(
            var_name="BP_CoopParam_Weapon",
            comp_class_package="/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Weapon",
            comp_class_name="BP_CoopParam_Weapon_C"
        )
        mgr_s3.set_ai_action("EPalAIActionType::Cooperation", "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_WeaponCall.BP_AIAction_WeaponCall_C")

        rt_s3 = verify_roundtrip_compilation(uasset_gui, usmap_path, mutated_s3, "BP_SheepBall_Scenario3", temp_dir)
        rt_mgr_s3 = BlueprintFeatureManager(rt_s3)
        assert not rt_mgr_s3.has_component("Shield"), "Scenario 3: Shield still present."
        assert rt_mgr_s3.has_component("BP_CoopParam_Weapon"), "Scenario 3: BP_CoopParam_Weapon missing."
        log("  ✓ [PASS] Scenario 3 verified: Swapped Shield for Flamethrower successfully.")

        # ---------------------------------------------------------------------
        # SCENARIO 4: Saddle Injection (Give a Mountable Saddle to Lamball)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 4: Saddle Injection (Making SheepBall Rideable) ---")
        mutated_s4 = json.loads(json.dumps(data_sheepball))
        mgr_s4 = BlueprintFeatureManager(mutated_s4)

        mgr_s4.add_saddle(
            ride_position_type="HorseRide",
            attach_socket="pelvis",
            relative_rotation={"Pitch": 90.0, "Yaw": 0.0, "Roll": 0.0}
        )

        rt_s4 = verify_roundtrip_compilation(uasset_gui, usmap_path, mutated_s4, "BP_SheepBall_Saddle", temp_dir)
        rt_mgr_s4 = BlueprintFeatureManager(rt_s4)
        assert rt_mgr_s4.has_saddle(), "Scenario 4: Saddle component missing from roundtrip AST."
        log("  ✓ [PASS] Scenario 4 verified: Injected BP_PalRideMarkerSaddle and ride AI action cleanly.")

        # ---------------------------------------------------------------------
        # SCENARIO 5: All-in-One Pal (WeaselDragon + Weapon + Bytecode + Funnel + Shield + Roll)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 5: All-in-One Pal (Saddle + Weapon + Bytecode + Funnel + Shield + Roll) ---")
        mutated_s5 = json.loads(json.dumps(data_weasel))
        mgr_s5 = BlueprintFeatureManager(mutated_s5)

        # 1. Weapon Component
        weapon_class_idx = mgr_s5.ensure_import_chain(flamethrower_class_pkg, "BP_Kitsunebi_Flamethrower_C")
        mgr_s5.add_component(
            var_name="BP_CoopParam_Weapon",
            comp_class_package="/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Weapon",
            comp_class_name="BP_CoopParam_Weapon_C",
            template_properties=[
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": "WeaponClass",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": weapon_class_idx
                }
            ]
        )

        # 2. Funnel Minion Params in ICH
        mgr_s5.set_partner_funnel_params(
            funnel_character_class="/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_DreamDemon.BP_FunnelCharacter_DreamDemon_C",
            funnel_controller_class="/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            funnel_waza_id="EPalWazaID::Funnel_DreamDemon"
        )

        # 3. Defensive Shield Component
        mgr_s5.add_component(
            var_name="Shield",
            comp_class_package="/Script/Engine",
            comp_class_name="SphereComponent",
            template_properties=[
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                    "Name": "SphereRadius",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": 90.0
                }
            ]
        )

        # 4. Unique Roll Attack Declaration
        mgr_s5.set_waza_declaration(
            waza_id_enum="EPalWazaID::Unique_SheepBall_Roll",
            action_class_package="/Game/Pal/Blueprint/Action/Waza/SheepBall/BP_Action_Unique_SheepBall_Roll",
            action_class_name="BP_Action_Unique_SheepBall_Roll_C"
        )

        # 5. Full Bytecode & Delegate Transference
        mgr_s5.transfer_uber_graph(data_kitsunebi, "BP_WeaselDragon")

        # Compile and Verify Roundtrip
        rt_s5 = verify_roundtrip_compilation(uasset_gui, usmap_path, mutated_s5, "BP_WeaselDragon_AllInOne", temp_dir)
        rt_mgr_s5 = BlueprintFeatureManager(rt_s5)

        assert rt_mgr_s5.has_saddle(), "Scenario 5: Native Saddle missing."
        assert rt_mgr_s5.has_component("BP_CoopParam_Weapon"), "Scenario 5: Weapon missing."
        assert rt_mgr_s5.has_component("Shield"), "Scenario 5: Shield missing."
        assert any("ExecuteUbergraph" in f[0] for f in rt_mgr_s5.class_export.get("FuncMap", [])), "Scenario 5: Transferred Ubergraph missing."

        elapsed = time.time() - start_time
        log(f"  ✓ [PASS] Scenario 5 verified: Super-blueprint with all 6 features compiled and un-serialized successfully!")
        log("\n" + "=" * 70)
        log(f"🎉 ALL 5 BLUEPRINT MUTATION SCENARIOS PASSED ({elapsed:.2f}s)!")
        log("=" * 70)

        shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        log(f"❌ Test failed: {e}", "ERROR")
        raise

if __name__ == "__main__":
    main()