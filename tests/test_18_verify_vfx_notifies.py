import os
import sys
import json

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)

from utils.anim_patcher.anim_discovery import scrape_notifies_from_json
from utils.uasset_helper import inject_sequence_notifies

def log(msg, cat="INFO"):
    print(f"[{cat}] {msg}", flush=True)

def main():
    log("=== PalBaker VFX Notify & Spatial Offset Verification Test ===")

    # Mock sidecar notifies scraped from Garm Kamitsuki
    sample_notifies = [
        {
            "Name": "PalEffect",
            "Time": 0.6783,
            "Duration": 0.7,
            "Track": 1,
            "Source": "sequence",
            "NiagaraSystem": "NS_UniqueSkill_Kamitsuki_trail",
            "NiagaraPackage": "/Game/Pal/Effect/Skill/Kamitsuki/NS_UniqueSkill_Kamitsuki_trail",
            "AttachBone": "spine_02",
            "LocationOffset": {"X": -20.0, "Y": 0.0, "Z": 0.0}
        },
        {
            "Name": "PalEffect",
            "Time": 0.7565,
            "Duration": 0.5425,
            "Track": 0,
            "Source": "sequence",
            "NiagaraSystem": "NS_UniqueSkill_Kamitsuki",
            "NiagaraPackage": "/Game/Pal/Effect/Skill/Kamitsuki/NS_UniqueSkill_Kamitsuki",
            "LocationOffset": {"X": 0.0, "Y": -50.0, "Z": 80.0}
        },
        {
            "Name": "PalAttackCollision",
            "Time": 1.0097,
            "Duration": 0.484,
            "Track": 2,
            "Source": "sequence",
            "AttachBone": "Socket_Mouth",
            "WazaID": "Unique_Garm_Bite",
            "SphereRadius": 100.0,
            "RelativeLocation": {"X": 0.0, "Y": 0.0, "Z": 20.0}
        },
        {
            "Name": "PalEffect",
            "Time": 1.0921,
            "Duration": 0.3171,
            "Track": 4,
            "Source": "sequence",
            "NiagaraSystem": "NS_UniqueSkill_Kamitsuki_Bite",
            "NiagaraPackage": "/Game/Pal/Effect/Skill/Kamitsuki/NS_UniqueSkill_Kamitsuki_Bite",
            "AttachBone": "Socket_Mouth",
            "LocationOffset": {"X": 0.0, "Y": 10.0, "Z": 20.0}
        },
        {
            "Name": "PalEffect",
            "Time": 1.1134,
            "Duration": 0.3171,
            "Track": 3,
            "Source": "sequence",
            "NiagaraSystem": "NS_UniqueSkill_Kamitsuki_dust",
            "NiagaraPackage": "/Game/Pal/Effect/Skill/Kamitsuki/NS_UniqueSkill_Kamitsuki_dust",
            "LocationOffset": {"X": 0.0, "Y": 200.0, "Z": -15.0}
        }
    ]

    base_dummy_ast = {
        "$type": "UAssetAPI.UAsset, UAssetAPI",
        "Exports": [
            {
                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                "ObjectName": "AS_Test_Kamitsuki",
                "OuterIndex": 0,
                "ClassIndex": 0,
                "TemplateIndex": 0,
                "Data": [
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SequenceLength", "Value": 2.875}
                ]
            }
        ],
        "Imports": []
    }

    log("Injecting notifies into clean AST...")
    result_ast = inject_sequence_notifies(base_dummy_ast, sample_notifies, "AS_Test_Kamitsuki")

    exports = result_ast["Exports"]
    imports = result_ast["Imports"]

    # 1. Assert all 4 Niagara states exist
    effect_exports = [e for e in exports if "PalAnimNotifyState_Effect" in e.get("ObjectName", "")]
    assert len(effect_exports) == 4, f"Expected 4 PalAnimNotifyState_Effect exports, got {len(effect_exports)}"
    log("  ✓ All 4 PalAnimNotifyState_Effect exports created.")

    # 2. Check Package Paths in Imports (NO fake Kamitsuki_dust or Kamitsuki_Bite folders)
    for imp in imports:
        pkg = imp.get("ObjectName", "")
        if "NS_UniqueSkill_Kamitsuki" in pkg and pkg.startswith("/Game/"):
            folder_part = pkg.rsplit("/", 1)[0]
            assert not folder_part.endswith("_trail"), f"Broken subfolder detected: {pkg}"
            assert not folder_part.endswith("_dust"), f"Broken subfolder detected: {pkg}"
            assert not folder_part.endswith("_Bite"), f"Broken subfolder detected: {pkg}"
            assert "/Effect/Skill/Kamitsuki" in folder_part, f"Invalid skill directory: {pkg}"
    log("  ✓ All Niagara System import packages verified clean and valid.")

    # 3. Assert SocketName and LocationOffsets are present
    has_mouth_socket = False
    has_dust_offset = False

    for exp in effect_exports:
        props = exp.get("Data", [])
        for p in props:
            if p.get("Name") == "SocketName" and p.get("Value") == "Socket_Mouth":
                has_mouth_socket = True
            elif p.get("Name") == "LocationOffset":
                vec = p.get("Value", [{}])[0].get("Value", {})
                if vec.get("Y") == 200.0 and vec.get("Z") == -15.0:
                    has_dust_offset = True

    assert has_mouth_socket, "Bite effect is missing 'SocketName: Socket_Mouth'!"
    assert has_dust_offset, "Dust effect is missing 'LocationOffset: Y=200, Z=-15'!"
    log("  ✓ SocketName and LocationOffset structs validated on effect sub-objects.")

    log("\n" + "=" * 60)
    log("🎉 ALL VFX NOTIFY VERIFICATION CHECKS PASSED!", "SUCCESS")
    log("=" * 60)

if __name__ == "__main__":
    main()