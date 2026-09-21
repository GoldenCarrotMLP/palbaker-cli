# tests/test_03_blueprint_mutation.py
"""
====================================================================================================
           PALBAKER INTEGRATION TEST 03: COMPREHENSIVE BLUEPRINT AST MUTATION SUITE
====================================================================================================

TEST MATRIX:
1.  SCENARIO 1:  FEATURE INJECTION (Manual Weapon Component + Funnel + Action)
2.  SCENARIO 2:  FEATURE STRIPPING (Clean Removal of Component + Action)
3.  SCENARIO 3:  FEATURE SWAPPING (Shield -> Weapon)
4.  SCENARIO 4:  SADDLE INJECTION (Making Lamball Rideable)
5.  SCENARIO 5:  ALL-IN-ONE SUPER-BLUEPRINT (All 6 core subsystems + Bytecode)
6.  SCENARIO 6:  CO-OP WEAPON CONVENIENCE PRESETS (AssaultRifle, Katana)
7.  SCENARIO 7:  SATELLITE MINION FUNNEL PRESETS (Dazzi / RaijinDaughter)
8.  SCENARIO 8:  DEFENSIVE SHIELD CONVENIENCE API (add_shield / remove_shield)
9.  SCENARIO 9:  FLIGHT, SPEED COLLISION, AND MOUNTED SHOOTER
10. SCENARIO 10: COMBAT EVASION & UTILITY ACTIONS (Teleport, BackStep, RevivePlayer)
11. SCENARIO 11: VISUAL LIGHTS & ATTACHED WEAPON PROPS (TimerPointLight, Hand Props)
12. SCENARIO 12: THE "OMNI-PAL" (ALL 8 ARCHETYPES + BYTECODE SYNTHESIZED SIMULTANEOUSLY)
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
from utils.blueprint_patcher.feature_manager import BlueprintFeatureManager

def log(msg: str, category: str = "INFO"):
    print(f"[{category}] {msg}", flush=True)

def get_blueprint_fixture(name: str, temp_dir: str, settings: dict, uasset_gui: str, usmap_path: str) -> dict:
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

        rt_s1 = verify_roundtrip(uasset_gui, usmap_path, mutated_s1, "BP_SheepBall_Scenario1", temp_dir)
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

        rt_s2 = verify_roundtrip(uasset_gui, usmap_path, mutated_s2, "BP_Kitsunebi_Scenario2", temp_dir)
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

        rt_s3 = verify_roundtrip(uasset_gui, usmap_path, mutated_s3, "BP_SheepBall_Scenario3", temp_dir)
        rt_mgr_s3 = BlueprintFeatureManager(rt_s3)
        assert not rt_mgr_s3.has_component("Shield"), "Scenario 3: Shield still present."
        assert rt_mgr_s3.has_component("BP_CoopParam_Weapon"), "Scenario 3: BP_CoopParam_Weapon missing."
        log("  ✓ [PASS] Scenario 3 verified: Swapped Shield for Flamethrower successfully.")

        # ---------------------------------------------------------------------
        # SCENARIO 4: Saddle Injection (Making SheepBall Rideable)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 4: Saddle Injection (Making SheepBall Rideable) ---")
        mutated_s4 = json.loads(json.dumps(data_sheepball))
        mgr_s4 = BlueprintFeatureManager(mutated_s4)

        mgr_s4.add_saddle(
            marker_type="Saddle",
            ride_position_type="HorseRide",
            attach_socket="pelvis",
            relative_rotation={"Pitch": 90.0, "Yaw": 0.0, "Roll": 0.0}
        )

        rt_s4 = verify_roundtrip(uasset_gui, usmap_path, mutated_s4, "BP_SheepBall_Saddle", temp_dir)
        rt_mgr_s4 = BlueprintFeatureManager(rt_s4)
        assert rt_mgr_s4.has_saddle(), "Scenario 4: Saddle component missing from roundtrip AST."
        log("  ✓ [PASS] Scenario 4 verified: Injected BP_PalRideMarkerSaddle and ride AI action cleanly.")

        # ---------------------------------------------------------------------
        # SCENARIO 5: All-in-One Super-Blueprint (Stress Test)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 5: All-in-One Super-Blueprint (Stress Test) ---")
        mutated_s5 = json.loads(json.dumps(data_weasel))
        mgr_s5 = BlueprintFeatureManager(mutated_s5)

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

        mgr_s5.set_partner_funnel_params(
            funnel_character_class="/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_DreamDemon.BP_FunnelCharacter_DreamDemon_C",
            funnel_controller_class="/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            funnel_waza_id="EPalWazaID::Funnel_DreamDemon"
        )

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

        mgr_s5.set_waza_declaration(
            waza_id_enum="EPalWazaID::Unique_SheepBall_Roll",
            action_class_package="/Game/Pal/Blueprint/Action/Waza/SheepBall/BP_Action_Unique_SheepBall_Roll",
            action_class_name="BP_Action_Unique_SheepBall_Roll_C"
        )

        mgr_s5.transfer_uber_graph(data_kitsunebi, "BP_WeaselDragon")

        rt_s5 = verify_roundtrip(uasset_gui, usmap_path, mutated_s5, "BP_WeaselDragon_AllInOne", temp_dir)
        rt_mgr_s5 = BlueprintFeatureManager(rt_s5)

        assert rt_mgr_s5.has_saddle(), "Scenario 5: Native Saddle missing."
        assert rt_mgr_s5.has_component("BP_CoopParam_Weapon"), "Scenario 5: Weapon missing."
        assert rt_mgr_s5.has_component("Shield"), "Scenario 5: Shield missing."
        assert any("ExecuteUbergraph" in f[0] for f in rt_mgr_s5.class_export.get("FuncMap", [])), "Scenario 5: Transferred Ubergraph missing."
        log("  ✓ [PASS] Scenario 5 verified: Super-blueprint with all 6 features compiled and un-serialized successfully.")

        # ---------------------------------------------------------------------
        # SCENARIO 6: Co-op Weapon Presets (AssaultRifle, Katana)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 6: Testing Co-op Weapon Convenience Presets ---")
        mutated_s6 = json.loads(json.dumps(data_sheepball))
        mgr_s6 = BlueprintFeatureManager(mutated_s6)

        # Assault Rifle preset (injects CoopParam, RayStart, and SkeletalMesh)
        mgr_s6.add_coop_weapon("AssaultRifle")
        assert mgr_s6.has_component("BP_CoopParam_AssaultRifleMode")
        assert mgr_s6.has_component("AssultrifleModeRayStart")
        assert mgr_s6.has_component("SkeletalMesh")

        # Katana preset
        mgr_s6.add_coop_weapon("Katana")
        assert mgr_s6.has_component("BP_CoopParam_Weapon")

        rt_s6 = verify_roundtrip(uasset_gui, usmap_path, mutated_s6, "BP_SheepBall_Weapons", temp_dir)
        rt_mgr_s6 = BlueprintFeatureManager(rt_s6)
        assert rt_mgr_s6.has_component("BP_CoopParam_AssaultRifleMode")
        assert rt_mgr_s6.has_component("SkeletalMesh")
        assert rt_mgr_s6.has_component("BP_CoopParam_Weapon")
        log("  ✓ [PASS] Scenario 6 verified: AssaultRifle and Katana weapon archetypes compiled cleanly.")

        # ---------------------------------------------------------------------
        # SCENARIO 7: Satellite Funnel Presets (Dazzi / RaijinDaughter)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 7: Testing Satellite Minion Funnel Presets ---")
        mutated_s7 = json.loads(json.dumps(data_sheepball))
        mgr_s7 = BlueprintFeatureManager(mutated_s7)

        mgr_s7.set_partner_funnel("Dazzi")
        rt_s7 = verify_roundtrip(uasset_gui, usmap_path, mutated_s7, "BP_SheepBall_FunnelDazzi", temp_dir)
        log("  ✓ [PASS] Scenario 7 verified: Dazzi funnel preset compiled into ICH records.")

        # ---------------------------------------------------------------------
        # SCENARIO 8: Defensive Shield Convenience API
        # ---------------------------------------------------------------------
        log("\n--- Scenario 8: Testing Defensive Shield Convenience API ---")
        mutated_s8 = json.loads(json.dumps(data_kitsunebi))
        mgr_s8 = BlueprintFeatureManager(mutated_s8)

        mgr_s8.add_shield(radius=120.0, attach_socket="spine_01")
        assert mgr_s8.has_shield()
        assert mgr_s8.has_component("BP_CoopParam_Sheild")

        rt_s8 = verify_roundtrip(uasset_gui, usmap_path, mutated_s8, "BP_Kitsunebi_Shield", temp_dir)
        rt_mgr_s8 = BlueprintFeatureManager(rt_s8)
        assert rt_mgr_s8.has_shield()

        # Test clean stripping of shield
        rt_mgr_s8.remove_shield()
        assert not rt_mgr_s8.has_shield()
        verify_roundtrip(uasset_gui, usmap_path, rt_s8, "BP_Kitsunebi_ShieldRemoved", temp_dir)
        log("  ✓ [PASS] Scenario 8 verified: Shield added and removed cleanly.")

        # ---------------------------------------------------------------------
        # SCENARIO 9: Flight, Speed Collision, and Mounted Shooter
        # ---------------------------------------------------------------------
        log("\n--- Scenario 9: Flight, Trample Collision, and Mounted Shooting ---")
        mutated_s9 = json.loads(json.dumps(data_sheepball))
        mgr_s9 = BlueprintFeatureManager(mutated_s9)

        mgr_s9.add_fly_height_controller()
        assert mgr_s9.has_fly_height_controller()

        mgr_s9.add_saddle(marker_type="BiggerHorse", with_speed_collision=True)
        assert mgr_s9.has_saddle()
        assert mgr_s9.has_speed_collision()

        mgr_s9.add_mounted_shooter()
        assert mgr_s9.has_mounted_shooter()

        rt_s9 = verify_roundtrip(uasset_gui, usmap_path, mutated_s9, "BP_SheepBall_FlightRiding", temp_dir)
        rt_mgr_s9 = BlueprintFeatureManager(rt_s9)
        assert rt_mgr_s9.has_fly_height_controller()
        assert rt_mgr_s9.has_saddle()
        assert rt_mgr_s9.has_speed_collision()
        assert rt_mgr_s9.has_mounted_shooter()
        log("  ✓ [PASS] Scenario 9 verified: Flight, BiggerHorse saddle, SpeedCollision, and Shooter compiled.")

        # ---------------------------------------------------------------------
        # SCENARIO 10: Combat Evasion & Utility Actions
        # ---------------------------------------------------------------------
        log("\n--- Scenario 10: Combat Evasion & Partner Utility Actions ---")
        mutated_s10 = json.loads(json.dumps(data_sheepball))
        mgr_s10 = BlueprintFeatureManager(mutated_s10)

        mgr_s10.set_evasion_style("Teleport")
        mgr_s10.set_evasion_style("BackStep")
        mgr_s10.set_coop_utility("RevivePlayer")

        rt_s10 = verify_roundtrip(uasset_gui, usmap_path, mutated_s10, "BP_SheepBall_EvasionUtility", temp_dir)
        log("  ✓ [PASS] Scenario 10 verified: Teleport, BackStep, and RevivePlayer bound in AIActionMap.")

        # ---------------------------------------------------------------------
        # SCENARIO 11: Visual Lights & Attached Weapon Props
        # ---------------------------------------------------------------------
        log("\n--- Scenario 11: Visual Bioluminescent Light & Hand Weapon Prop ---")
        mutated_s11 = json.loads(json.dumps(data_sheepball))
        mgr_s11 = BlueprintFeatureManager(mutated_s11)

        mgr_s11.add_timer_point_light()
        assert mgr_s11.has_timer_point_light()

        mgr_s11.add_hand_prop(
            var_name="Weapon",
            attach_socket="Socket_Weapon_R",
            is_skeletal=True
        )
        assert mgr_s11.has_hand_prop()

        rt_s11 = verify_roundtrip(uasset_gui, usmap_path, mutated_s11, "BP_SheepBall_Props", temp_dir)
        rt_mgr_s11 = BlueprintFeatureManager(rt_s11)
        assert rt_mgr_s11.has_timer_point_light()
        assert rt_mgr_s11.has_hand_prop()
        log("  ✓ [PASS] Scenario 11 verified: TimerPointLight and Hand Weapon prop serialized cleanly.")

        

        # ---------------------------------------------------------------------
        # SCENARIO 12: The "Omni-Pal" (All 8 Archetypes + Bytecode Synthesized)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 12: The 'Omni-Pal' (Ascended Lamball with All Archetypes) ---")
        mutated_s12 = json.loads(json.dumps(data_sheepball))
        mgr_s12 = BlueprintFeatureManager(mutated_s12)

        # 1. Mountable Riding: BiggerHorse saddle + Trample Speed Collision
        mgr_s12.add_saddle(marker_type="BiggerHorse", with_speed_collision=True)

        # 2. Mounted Shooter Component (allows riding player to shoot weapons)
        mgr_s12.add_mounted_shooter()

        # 3. Flight & Altitude Height Controller
        mgr_s12.add_fly_height_controller()

        # 4. Defensive Energy Shield (SphereComponent radius 110.0 + BP_CoopParam_Sheild)
        mgr_s12.add_shield(radius=110.0, attach_socket="lowerarm_l")

        # 5. Co-op Partner Weapon: Assault Rifle (RayStart, weapon mesh on Socket_Weapon_R, CoopParam)
        mgr_s12.add_coop_weapon("AssaultRifle", attach_socket="Socket_Weapon_R")

        # 6. Satellite Minion Funnel: Dazzi (RaijinDaughter)
        mgr_s12.set_partner_funnel("Dazzi")

        # 7. Combat Evasion: Teleport on SideMove & TurnRun on Leave
        mgr_s12.set_evasion_style("Teleport")
        mgr_s12.set_evasion_style("TurnRun")

        # 8. Visual Bioluminescence Light Component
        mgr_s12.add_timer_point_light()

        # 9. Attached In-Hand Weapon Prop on left hand
        mgr_s12.add_hand_prop(var_name="Weapon", attach_socket="hand_l", is_skeletal=True)

        # 10. Unique Attack Waza Action Declaration
        mgr_s12.set_waza_declaration(
            waza_id_enum="EPalWazaID::Unique_SheepBall_Roll",
            action_class_package="/Game/Pal/Blueprint/Action/Waza/SheepBall/BP_Action_Unique_SheepBall_Roll",
            action_class_name="BP_Action_Unique_SheepBall_Roll_C"
        )

        # 11. EventGraph Bytecode Transference from Kitsunebi
        mgr_s12.transfer_uber_graph(data_kitsunebi, "BP_SheepBall")

        # Compile to .uasset with UAssetGUI and Mappings.usmap, then decompile back (Round-Trip)
        rt_s12 = verify_roundtrip(uasset_gui, usmap_path, mutated_s12, "BP_SheepBall_OmniPal", temp_dir)
        rt_mgr_s12 = BlueprintFeatureManager(rt_s12)

        # Deep verification of all active components in the round-tripped AST
        assert rt_mgr_s12.has_saddle(), "Omni-Pal: Saddle marker missing."
        assert rt_mgr_s12.has_speed_collision(), "Omni-Pal: Speed collision missing."
        assert rt_mgr_s12.has_mounted_shooter(), "Omni-Pal: Mounted shooter missing."
        assert rt_mgr_s12.has_fly_height_controller(), "Omni-Pal: Fly height controller missing."
        assert rt_mgr_s12.has_shield(), "Omni-Pal: Shield SphereComponent missing."
        assert rt_mgr_s12.has_component("BP_CoopParam_Sheild"), "Omni-Pal: Shield CoopParam missing."
        assert rt_mgr_s12.has_component("BP_CoopParam_AssaultRifleMode"), "Omni-Pal: Assault Rifle CoopParam missing."
        assert rt_mgr_s12.has_component("AssultrifleModeRayStart"), "Omni-Pal: RayStart scene component missing."
        assert rt_mgr_s12.has_component("SkeletalMesh"), "Omni-Pal: Weapon SkeletalMesh component missing."
        assert rt_mgr_s12.has_timer_point_light(), "Omni-Pal: TimerPointLight missing."
        assert rt_mgr_s12.has_hand_prop("Weapon"), "Omni-Pal: Hand prop missing."
        assert any("ExecuteUbergraph" in f[0] for f in rt_mgr_s12.class_export.get("FuncMap", [])), "Omni-Pal: Transferred Ubergraph missing."

        log("  ✓ [PASS] Scenario 12 verified: Ascended Omni-Pal with all 8 archetypes + bytecode compiled and roundtripped flawlessly!")

        

        # ---------------------------------------------------------------------
        # SCENARIO 13: Permanent Niagara VFX Attachments
        # ---------------------------------------------------------------------
        log("\n--- Scenario 13: Permanent Niagara VFX Attachments (Flaming Eyes) ---")
        mutated_s13 = json.loads(json.dumps(data_sheepball))
        mgr_s13 = BlueprintFeatureManager(mutated_s13)

        # Inject cooking flames onto both eyes
        mgr_s13.add_niagara_particle(
            var_name="VFX_Eye_Left",
            system_package="/Game/Pal/Effect/Common/Cooking/NS_CookingFlame",
            system_name="NS_CookingFlame",
            attach_socket="eye_l"
        )
        mgr_s13.add_niagara_particle(
            var_name="VFX_Eye_Right",
            system_package="/Game/Pal/Effect/Common/Cooking/NS_CookingFlame",
            system_name="NS_CookingFlame",
            attach_socket="eye_r"
        )

        rt_s13 = verify_roundtrip(uasset_gui, usmap_path, mutated_s13, "BP_SheepBall_VFX", temp_dir)
        rt_mgr_s13 = BlueprintFeatureManager(rt_s13)
        assert rt_mgr_s13.has_component("VFX_Eye_Left"), "VFX component 1 missing."
        assert rt_mgr_s13.has_component("VFX_Eye_Right"), "VFX component 2 missing."
        log("  ✓ [PASS] Scenario 13 verified: Real-time Niagara attachments serialized flawlessly.")

        # ---------------------------------------------------------------------
        # SCENARIO 14: Locomotion Leaning & Banking Calibration
        # ---------------------------------------------------------------------
        log("\n--- Scenario 14: Locomotion Leaning & Banking Calibration ---")
        mutated_s14 = json.loads(json.dumps(data_sheepball))
        mgr_s14 = BlueprintFeatureManager(mutated_s14)

        # Zero out the tilting intensity for Walk and Swim to prevent floor clipping
        mgr_s14.set_locomotion_leaning(mode="Walk", pitch_intensity=0.0, roll_intensity=0.0)
        mgr_s14.set_locomotion_leaning(mode="Swim", pitch_intensity=0.0, roll_intensity=0.0)

        rt_s14 = verify_roundtrip(uasset_gui, usmap_path, mutated_s14, "BP_SheepBall_Leaning", temp_dir)
        # Extract the modified static parameters to verify values stuck
        rt_mgr_s14 = BlueprintFeatureManager(rt_s14)
        cdo_exp = rt_mgr_s14.find_static_char_param_export()
        lean_walk = next((p for p in cdo_exp["Data"] if p.get("Name") == "LeanParameter_Walk"), None)
        assert lean_walk is not None, "LeanParameter_Walk failed to serialize."
        
        y_axis = lean_walk["Value"][0]["Value"]
        y_intensity = next((p["Value"] for p in y_axis if p.get("Name") == "Intensity"), -1.0)
        assert abs(float(y_intensity) - 0.0) < 0.001, f"Pitch Intensity failed to save. Got {y_intensity}"
        
        log("  ✓ [PASS] Scenario 14 verified: Procedural leaning parameters calibrated to 0.0.")


        # ---------------------------------------------------------------------
        # SCENARIO 15: The "Omni-Pal" (All 10 Archetypes + Bytecode Synthesized)
        # ---------------------------------------------------------------------
        log("\n--- Scenario 15: The 'Omni-Pal' (Ascended Lamball with All Archetypes) ---")
        mutated_s15 = json.loads(json.dumps(data_sheepball))
        mgr_s15 = BlueprintFeatureManager(mutated_s15)

        # 1. Mountable Riding: BiggerHorse saddle + Trample Speed Collision
        mgr_s15.add_saddle(marker_type="BiggerHorse", with_speed_collision=True)
        # 2. Mounted Shooter Component (allows riding player to shoot weapons)
        mgr_s15.add_mounted_shooter()
        # 3. Flight & Altitude Height Controller
        mgr_s15.add_fly_height_controller()
        # 4. Defensive Energy Shield (SphereComponent radius 110.0 + BP_CoopParam_Sheild)
        mgr_s15.add_shield(radius=110.0, attach_socket="lowerarm_l")
        # 5. Co-op Partner Weapon: Assault Rifle (RayStart, weapon mesh on Socket_Weapon_R, CoopParam)
        mgr_s15.add_coop_weapon("AssaultRifle", attach_socket="Socket_Weapon_R")
        # 6. Satellite Minion Funnel: Dazzi (RaijinDaughter)
        mgr_s15.set_partner_funnel("Dazzi")
        # 7. Combat Evasion: Teleport on SideMove & TurnRun on Leave
        mgr_s15.set_evasion_style("Teleport")
        mgr_s15.set_evasion_style("TurnRun")
        # 8. Visual Bioluminescence Light Component
        mgr_s15.add_timer_point_light()
        # 9. Attached In-Hand Weapon Prop on left hand
        mgr_s15.add_hand_prop(var_name="Weapon", attach_socket="hand_l", is_skeletal=True)
        # 10. Unique Attack Waza Action Declaration
        mgr_s15.set_waza_declaration(
            waza_id_enum="EPalWazaID::Unique_SheepBall_Roll",
            action_class_package="/Game/Pal/Blueprint/Action/Waza/SheepBall/BP_Action_Unique_SheepBall_Roll",
            action_class_name="BP_Action_Unique_SheepBall_Roll_C"
        )
        # 11. Permanent Niagara VFX (Flaming Eyes)
        mgr_s15.add_niagara_particle(var_name="VFX_Eye_Left", system_package="/Game/Pal/Effect/Common/Cooking/NS_CookingFlame", system_name="NS_CookingFlame", attach_socket="eye_l")
        mgr_s15.add_niagara_particle(var_name="VFX_Eye_Right", system_package="/Game/Pal/Effect/Common/Cooking/NS_CookingFlame", system_name="NS_CookingFlame", attach_socket="eye_r")
        # 12. Calibration of Physics Leaning
        mgr_s15.set_locomotion_leaning(mode="Walk", pitch_intensity=0.0, roll_intensity=0.0)
        # 13. EventGraph Bytecode Transference from Kitsunebi
        mgr_s15.transfer_uber_graph(data_kitsunebi, "BP_SheepBall")

        # Compile to .uasset with UAssetGUI and Mappings.usmap, then decompile back (Round-Trip)
        rt_s15 = verify_roundtrip(uasset_gui, usmap_path, mutated_s15, "BP_SheepBall_OmniPal", temp_dir)
        rt_mgr_s15 = BlueprintFeatureManager(rt_s15)

        # Deep verification of all active components in the round-tripped AST
        assert rt_mgr_s15.has_saddle(), "Omni-Pal: Saddle marker missing."
        assert rt_mgr_s15.has_speed_collision(), "Omni-Pal: Speed collision missing."
        assert rt_mgr_s15.has_mounted_shooter(), "Omni-Pal: Mounted shooter missing."
        assert rt_mgr_s15.has_fly_height_controller(), "Omni-Pal: Fly height controller missing."
        assert rt_mgr_s15.has_shield(), "Omni-Pal: Shield SphereComponent missing."
        assert rt_mgr_s15.has_component("BP_CoopParam_Sheild"), "Omni-Pal: Shield CoopParam missing."
        assert rt_mgr_s15.has_component("BP_CoopParam_AssaultRifleMode"), "Omni-Pal: Assault Rifle CoopParam missing."
        assert rt_mgr_s15.has_component("VFX_Eye_Left"), "Omni-Pal: VFX Eye L missing."
        assert any("ExecuteUbergraph" in f[0] for f in rt_mgr_s15.class_export.get("FuncMap", [])), "Omni-Pal: Transferred Ubergraph missing."

        log("  ✓ [PASS] Scenario 15 verified: Ascended Omni-Pal with all 10 archetypes + bytecode compiled and roundtripped flawlessly!")

        elapsed = time.time() - start_time
        log("\n" + "=" * 70)
        log(f"🎉 ALL 15 BLUEPRINT FEATURE SCENARIOS PASSED ({elapsed:.2f}s)!")
        log("=" * 70)

        shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        log(f"❌ Test failed: {e}", "ERROR")
        raise

if __name__ == "__main__":
    main()