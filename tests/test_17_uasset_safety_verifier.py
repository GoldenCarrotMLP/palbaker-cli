import os
import sys
import json

# 1. RESOLVE AND INJECT THE REPOSITORY ROOT INTO THE SYSTEM PATH BEFORE IMPORTING UTILS!
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# 2. NOW WE CAN SAFELY IMPORT PALBAKER UTILS
from utils.uasset_safety_validator import UAssetSafetyValidator

def log(msg: str, category: str = "INFO"):
    print(f"[{category}] {msg}", flush=True)

def main():
    log("=== PalBaker UAsset Structural Safety Verifier ===")

    # Target the exact file that caused the crash
    target_file = os.path.join(REPO_ROOT, "templates", "AS_SexyDirehowl_Kamitsuki_Broken.json")

    if not os.path.exists(target_file):
        log(f"❌ Could not find {target_file}", "ERROR")
        log("Please make sure the file is placed at 'templates/AS_SexyDirehowl_Kamitsuki_Broken.json'.", "ERROR")
        sys.exit(1)

    log(f"\n--- Scanning Physical File: {os.path.basename(target_file)} ---")
    
    validator = UAssetSafetyValidator(target_file)
    report = validator.validate()
    
    log(f"Scan complete. Is Safe? {report['is_safe']}")
    
    if report["errors"]:
        log(f"Caught {len(report['errors'])} Fatal Errors:")
        for err in report["errors"]:
            log(f"  ❌ {err}", "ERROR")
            
    if report["warnings"]:
        log(f"Caught {len(report['warnings'])} Warnings:")
        for warn in report["warnings"]:
            log(f"  ⚠️ {warn}", "WARNING")

    # The file is KNOWN to cause crashes, so if the validator says it's safe, the validator failed.
    assert not report["is_safe"], "❌ VALIDATOR FAILED: It flagged the crashing file as 'safe'!"
    
    # Specific assertions to ensure we caught the exact reasons for the Array.cpp crash
    err_str = " ".join(report["errors"])
    assert "Unversioned Serialization is ENABLED" in err_str, "Did not detect UnversionedProperties leak."
    
    # The crash was caused by BodyInstance / ResponseArray unversioned deserialization misalignment
    assert "BodyInstance" in err_str or "ResponseArray" in err_str, "Did not detect the fatal BodyInstance/ResponseArray inclusion."

    log("\n" + "=" * 70)
    log("🎉 UASSET SAFETY VERIFIER TEST PASSED!")
    log("The validator successfully caught the exact memory corruption vectors")
    log("in the physical AS_SexyDirehowl_Kamitsuki_Broken.json file.")
    log("=" * 70)

if __name__ == "__main__":
    main()
