# tests/test_16_feature_validator.py
"""
====================================================================================================
           PALBAKER INTEGRATION TEST 16: FEATURE DEPENDENCY VALIDATOR
====================================================================================================

PURPOSE & GOAL:
---------------
Validates the universal `FeatureDependencyValidator` engine to ensure it correctly 
identifies missing animations and missing notifies based on user configurations.

SCENARIOS TESTED:
1. FULLY VALID:       Pal has Fire Suitability, Assault Rifle, and Anubis Punch. Sidecar has all anims/notifies.
2. MISSING NOTIFIES:  Anims exist, but the 'PalEffect' and 'OnShoot' notifies are missing.
3. MISSING ANIMATION: The Pal lacks the 'Fire_AssaultRifle' track entirely.
4. FUNNEL WAZA ROUTE: The Pal has 'Unique_SheepBall_Roll' assigned to a Funnel, missing 'Skill_Tackle'.
====================================================================================================
"""

import os
import sys
import json
import copy

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.append(REPO_ROOT)

from utils.validator import FeatureDependencyValidator

def log(msg: str, category: str = "INFO"):
    print(f"[{category}] {msg}", flush=True)

# --- MOCK PAL CREATOR DATA (The Modder's Configuration) ---
MOCK_PAL_DATA = {
    "CharacterID": "OmniPal",
    "WorkSuitability_EmitFlame": 1,
    "CoopWeapon": {
        "Enabled": True,
        "Mode": "AssaultRifle"
    },
    "Learnset": [
        {"Level": 1, "WazaID": "Unique_Anubis_GroundPunch"}
    ],
    "Funnel": {
        "Enabled": True,
        "CustomWazaID": "EPalWazaID::Unique_SheepBall_Roll"
    }
}

# --- MOCK BLENDER SIDECAR (Perfectly Valid State) ---
MOCK_SIDECAR_VALID = {
    "custom_animations": {
        "is_active": True,
        "anims": {
            "AS_OmniPal_Cooking": {
                "nla_track_name": "Cooking", "in_nla": True, "notifies": [{"Name": "PalEffect"}]
            },
            "AS_OmniPal_Fire_AssaultRifle": {
                "nla_track_name": "Fire_AssaultRifle", "in_nla": True, "notifies": [{"Name": "OnShoot"}]
            },
            "AS_OmniPal_Skill_JimenNaguri_Start": {
                "nla_track_name": "Skill_JimenNaguri_Start", "in_nla": True, "notifies": []
            },
            "AS_OmniPal_Skill_JimenNaguri_UpLoop": {
                "nla_track_name": "Skill_JimenNaguri_UpLoop", "in_nla": True, "notifies": []
            },
            "AS_OmniPal_Skill_JimenNaguri_DownLoop": {
                "nla_track_name": "Skill_JimenNaguri_DownLoop", "in_nla": True, "notifies": []
            },
            "AS_OmniPal_Skill_JimenNaguri_End": {
                "nla_track_name": "Skill_JimenNaguri_End", "in_nla": True, "notifies": []
            },
            "AS_OmniPal_Skill_Tackle": {
                "nla_track_name": "Skill_Tackle", "in_nla": True, "notifies": []
            }
        }
    }
}

def main():
    log("=== PalBaker Feature Dependency Validator Suite ===")
    
    # Initialize the validator (will use fallback schema if no json exists)
    validator = FeatureDependencyValidator(REPO_ROOT)

    # -------------------------------------------------------------------------
    # CASE 1: FULLY VALID CONFIGURATION
    # -------------------------------------------------------------------------
    log("\n--- Case 1: Fully Valid Dependencies ---")
    missing_c1 = validator.validate_dependencies(MOCK_PAL_DATA, MOCK_SIDECAR_VALID)
    assert len(missing_c1) == 0, f"Expected 0 missing dependencies, got: {missing_c1}"
    log("  ✓ [PASS] Valid configurations pass without error.")

    # -------------------------------------------------------------------------
    # CASE 2: MISSING NOTIFIES
    # -------------------------------------------------------------------------
    log("\n--- Case 2: Missing Required AnimNotifies ---")
    sidecar_c2 = copy.deepcopy(MOCK_SIDECAR_VALID)
    # Strip the notifies
    sidecar_c2["custom_animations"]["anims"]["AS_OmniPal_Cooking"]["notifies"] = []
    sidecar_c2["custom_animations"]["anims"]["AS_OmniPal_Fire_AssaultRifle"]["notifies"] = []

    missing_c2 = validator.validate_dependencies(MOCK_PAL_DATA, sidecar_c2)
    assert len(missing_c2) == 2, f"Expected 2 missing dependencies, got: {len(missing_c2)}"
    
    types = [m["missing_type"] for m in missing_c2]
    assert all(t == "notify" for t in types), "Expected missing_type to be 'notify'"
    
    missing_vals = [m["missing_value"] for m in missing_c2]
    assert "PalEffect" in missing_vals, "Failed to catch missing PalEffect notify."
    assert "OnShoot" in missing_vals, "Failed to catch missing OnShoot notify."
    log("  ✓ [PASS] Caught missing 'PalEffect' and 'OnShoot' notifies successfully.")

    # -------------------------------------------------------------------------
    # CASE 3: MISSING ANIMATION TRACK
    # -------------------------------------------------------------------------
    log("\n--- Case 3: Missing Required Animation Track ---")
    sidecar_c3 = copy.deepcopy(MOCK_SIDECAR_VALID)
    # Simulate modder deleting the track from Blender NLA
    del sidecar_c3["custom_animations"]["anims"]["AS_OmniPal_Fire_AssaultRifle"]

    missing_c3 = validator.validate_dependencies(MOCK_PAL_DATA, sidecar_c3)
    
    target_error = next((m for m in missing_c3 if m["missing_type"] == "animation" and m["target_anim"] == "Fire_AssaultRifle"), None)
    assert target_error is not None, "Failed to catch missing AssaultRifle animation."
    assert target_error["feature"] == "Partner Weapon: AssaultRifle"
    log("  ✓ [PASS] Caught missing 'Fire_AssaultRifle' track successfully.")

    # -------------------------------------------------------------------------
    # CASE 4: FUNNEL UNIQUE ATTACK ROUTING
    # -------------------------------------------------------------------------
    log("\n--- Case 4: Funnel Unique Attack Dependency Validation ---")
    sidecar_c4 = copy.deepcopy(MOCK_SIDECAR_VALID)
    # Modder enabled 'Unique_SheepBall_Roll' on the Funnel, but forgot 'Skill_Tackle' in Blender
    del sidecar_c4["custom_animations"]["anims"]["AS_OmniPal_Skill_Tackle"]

    missing_c4 = validator.validate_dependencies(MOCK_PAL_DATA, sidecar_c4)
    target_error = next((m for m in missing_c4 if m["target_anim"] == "Skill_Tackle"), None)
    
    assert target_error is not None, "Failed to catch missing Skill_Tackle from Funnel waza routing."
    assert target_error["feature"] == "Unique Attack: Unique_SheepBall_Roll"
    log("  ✓ [PASS] Caught missing dependencies routed from Funnel CustomWazaID.")

    # -------------------------------------------------------------------------
    # CASE 5: INVALID SADDLE ATTACHMENT (Non-existent PlayerRideMarker)
    # -------------------------------------------------------------------------
    log("\n--- Case 5: Invalid Saddle Attachment Validation ---")
    pal_data_c5 = copy.deepcopy(MOCK_PAL_DATA)
    pal_data_c5["TemplateID"] = "Kitsunebi" # Non-mountable template without PlayerRideMarker
    pal_data_c5["Features"] = {
        "Riding": {
            "Enabled": True,
            "AttachSocket": "PlayerRideMarker"
        }
    }
    missing_c5 = validator.validate_dependencies(pal_data_c5, MOCK_SIDECAR_VALID)
    assert len(missing_c5) > 0, "Failed to catch invalid PlayerRideMarker on non-mount."
    assert missing_c5[0]["missing_type"] == "attachment"
    log("  ✓ [PASS] Caught invalid 'PlayerRideMarker' socket on non-mount template.")

    # -------------------------------------------------------------------------
    # CASE 6: ATTACHMENT TO NON-EXISTENT BONE IN SKELETON
    # -------------------------------------------------------------------------
    log("\n--- Case 6: Non-Existent Skeleton Bone Validation ---")
    pal_data_c6 = copy.deepcopy(MOCK_PAL_DATA)
    pal_data_c6["Features"] = {
        "Shield": {
            "Enabled": True,
            "AttachSocket": "FakeNonExistentBone_123"
        }
    }
    sidecar_c6 = copy.deepcopy(MOCK_SIDECAR_VALID)
    sidecar_c6["all_bones"] = ["pelvis", "spine_01", "neck", "head", "hand_l", "hand_r"]

    missing_c6 = validator.validate_dependencies(pal_data_c6, sidecar_c6)
    assert len(missing_c6) > 0, "Failed to catch non-existent bone in skeleton."
    assert missing_c6[0]["target_socket"] == "FakeNonExistentBone_123"
    log("  ✓ [PASS] Caught non-existent bone attachment socket against sidecar bone list.")

    log("\n" + "=" * 70)
    log(f"🎉 ALL VALIDATION SCENARIOS PASSED!")
    log("=" * 70)

if __name__ == "__main__":
    main()