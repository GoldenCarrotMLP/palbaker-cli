# tests/test_18_anim_sequence_notify_injection.py
import os
import sys
import json
import copy

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from utils.uasset_safety_validator import UAssetSafetyValidator
from utils.uasset_helper import sync_namemap, compile_uasset

def log(msg: str, category: str = "INFO"):
    print(f"[{category}] {msg}", flush=True)

def find_or_add_import(imports: list, object_name: str, class_name: str, class_package: str, outer_index: int = 0) -> int:
    for idx, imp in enumerate(imports):
        if imp.get("ObjectName") == object_name and imp.get("OuterIndex") == outer_index:
            return -(idx + 1)
    new_imp = {
        "$type": "UAssetAPI.Import, UAssetAPI",
        "ObjectName": object_name,
        "OuterIndex": outer_index,
        "ClassPackage": class_package,
        "ClassName": class_name,
        "PackageName": None,
        "bImportOptional": False
    }
    imports.append(new_imp)
    return -len(imports)

def ensure_package_and_class_import(imports: list, package_name: str, object_name: str, class_type: str = "Class", class_pkg: str = "/Script/CoreUObject") -> int:
    pkg_idx = find_or_add_import(imports, package_name, "Package", "/Script/CoreUObject", 0)
    return find_or_add_import(imports, object_name, class_type, class_pkg, pkg_idx)

def inject_sequence_notifies(base_ast: dict, notifies_list: list, sequence_name: str) -> dict:
    ast = copy.deepcopy(base_ast)
    exports = ast.setdefault("Exports", [])
    imports = ast.setdefault("Imports", [])

    main_exp = next((e for e in exports if e.get("ObjectName") == sequence_name), exports[0])
    main_exp_idx = exports.index(main_exp) + 1

    # 1. Tagged Serialization Enforcement
    ast["HasUnversionedProperties"] = False
    pkg_flags = ast.get("PackageFlags", "")
    if isinstance(pkg_flags, str):
        cleaned_flags = [f.strip() for f in pkg_flags.split(",") if f.strip() and f.strip() != "PKG_UnversionedProperties"]
        ast["PackageFlags"] = ", ".join(cleaned_flags)
    elif isinstance(pkg_flags, int):
        ast["PackageFlags"] &= ~0x00002000

    # Ensure required engine packages and classes exist
    engine_pkg = find_or_add_import(imports, "/Script/Engine", "Package", "/Script/CoreUObject", 0)
    pal_pkg = find_or_add_import(imports, "/Script/Pal", "Package", "/Script/CoreUObject", 0)
    niagara_notifies_pkg = find_or_add_import(imports, "/Script/NiagaraAnimNotifies", "Package", "/Script/CoreUObject", 0)

    niagara_notify_class = find_or_add_import(imports, "AnimNotify_PlayNiagaraEffect", "Class", "/Script/CoreUObject", niagara_notifies_pkg)
    niagara_notify_default = find_or_add_import(imports, "Default__AnimNotify_PlayNiagaraEffect", "AnimNotify_PlayNiagaraEffect", "/Script/NiagaraAnimNotifies", niagara_notifies_pkg)

    pal_attack_class = find_or_add_import(imports, "PalAnimNotifyState_AttackCollision", "Class", "/Script/CoreUObject", pal_pkg)
    pal_attack_default = find_or_add_import(imports, "Default__PalAnimNotifyState_AttackCollision", "PalAnimNotifyState_AttackCollision", "/Script/Pal", pal_pkg)

    pal_filter_class = find_or_add_import(imports, "PalAttackFilter", "Class", "/Script/CoreUObject", pal_pkg)
    pal_filter_default = find_or_add_import(imports, "Default__PalAttackFilter", "PalAttackFilter", "/Script/Pal", pal_pkg)

    capsule_class = find_or_add_import(imports, "CapsuleComponent", "Class", "/Script/CoreUObject", engine_pkg)
    capsule_default = find_or_add_import(imports, "Default__CapsuleComponent", "CapsuleComponent", "/Script/Engine", engine_pkg)

    sphere_class = find_or_add_import(imports, "SphereComponent", "Class", "/Script/CoreUObject", engine_pkg)
    sphere_default = find_or_add_import(imports, "Default__SphereComponent", "SphereComponent", "/Script/Engine", engine_pkg)

    serialized_notifies = []
    created_sub_indices = []

    niagara_counter = 0
    attack_counter = 0

    for n in notifies_list:
        notify_name = n.get("Name", "")
        time_val = float(n.get("Time", 0.0))
        dur_val = float(n.get("Duration", 0.0))
        track_idx = int(n.get("Track", 0))

        # Niagara Notify
        if notify_name == "PalEffect":
            system_name = n.get("NiagaraSystem", "NS_UniqueSkill_Kamitsuki")
            system_pkg = f"/Game/Pal/Effect/Skill/{system_name.replace('NS_UniqueSkill_', '')}/{system_name}"
            system_import = ensure_package_and_class_import(imports, system_pkg, system_name, "NiagaraSystem", "/Script/Niagara")

            exp_name = f"AnimNotify_PlayNiagaraEffect_{niagara_counter}"
            niagara_counter += 1

            sub_export = {
                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                "ObjectName": exp_name,
                "OuterIndex": main_exp_idx,
                "ClassIndex": niagara_notify_class,
                "TemplateIndex": niagara_notify_default,
                "ObjectFlags": "RF_Transactional",
                "Data": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                        "Name": "Template",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": system_import
                    },
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                        "Name": "SocketName",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": n.get("AttachBone", "Socket_Mouth")
                    }
                ],
                "SerializationBeforeSerializationDependencies": [],
                "CreateBeforeSerializationDependencies": [system_import],
                "SerializationBeforeCreateDependencies": [niagara_notify_class, niagara_notify_default],
                "CreateBeforeCreateDependencies": [main_exp_idx],
                "Extras": ""
            }
            exports.append(sub_export)
            sub_exp_idx = len(exports)
            created_sub_indices.append(sub_exp_idx)

            serialized_notifies.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "AnimNotifyEvent",
                "Name": "Notifies",
                "Value": [
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "Value": 0.0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "Value": 0.0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 1e-05},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": "PlayNiagaraEffect"},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "Value": sub_exp_idx},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "NotifyStateClass", "Value": 0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": dur_val},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "TrackIndex", "Value": track_idx},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": time_val},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "MontageTickType", "ByteType": "FName", "EnumType": "EMontageNotifyTickType", "EnumValue": "EMontageNotifyTickType::Queued", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "NotifyFilterType", "ByteType": "FName", "EnumType": "ENotifyFilterType", "EnumValue": "ENotifyFilterType::NoFiltering", "IsZero": False}
                ]
            })

        # Attack Collision NotifyState
        elif notify_name == "PalAttackCollision":
            idx_state = len(exports) + 1
            idx_filter = len(exports) + 2
            idx_shape = len(exports) + 3

            state_exp_name = f"PalAnimNotifyState_AttackCollision_{attack_counter}"
            filter_exp_name = f"PalAttackFilter_{attack_counter}"
            has_capsule = "CapsuleRadius" in n or "CapsuleHalfHeight" in n
            shape_exp_name = f"CapsuleComponent_{attack_counter}" if has_capsule else f"SphereComponent_{attack_counter}"
            attack_counter += 1

            state_export = {
                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                "ObjectName": state_exp_name,
                "OuterIndex": main_exp_idx,
                "ClassIndex": pal_attack_class,
                "TemplateIndex": pal_attack_default,
                "ObjectFlags": "RF_Transactional",
                "Data": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                        "Name": "attachBoneName",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": n.get("AttachBone", "Socket_Mouth")
                    },
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                        "Name": "AttackFilter",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": idx_filter
                    },
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                        "Name": "ShapeComponent",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": idx_shape
                    }
                ],
                "SerializationBeforeSerializationDependencies": [],
                "CreateBeforeSerializationDependencies": [idx_filter, idx_shape],
                "SerializationBeforeCreateDependencies": [pal_attack_class, pal_attack_default],
                "CreateBeforeCreateDependencies": [main_exp_idx],
                "Extras": ""
            }

            waza_enum = n.get("WazaID", "Unique_Garm_Bite")
            if not waza_enum.startswith("EPalWazaID::"):
                waza_enum = f"EPalWazaID::{waza_enum}"

            filter_export = {
                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                "ObjectName": filter_exp_name,
                "OuterIndex": idx_state,
                "ClassIndex": pal_filter_class,
                "TemplateIndex": pal_filter_default,
                "ObjectFlags": "RF_Transactional",
                "Data": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                        "EnumType": "EPalWazaID",
                        "InnerType": "EPalWazaID",
                        "Name": "Waza",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": waza_enum
                    }
                ],
                "SerializationBeforeSerializationDependencies": [],
                "CreateBeforeSerializationDependencies": [],
                "SerializationBeforeCreateDependencies": [pal_filter_class, pal_filter_default],
                "CreateBeforeCreateDependencies": [idx_state],
                "Extras": ""
            }

            shape_data = []
            if has_capsule:
                shape_data.append({"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "CapsuleRadius", "Value": float(n.get("CapsuleRadius", 65.0))})
                shape_data.append({"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "CapsuleHalfHeight", "Value": float(n.get("CapsuleHalfHeight", 65.0))})
                shape_class_idx = capsule_class
                shape_default_idx = capsule_default
            else:
                shape_data.append({"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SphereRadius", "Value": float(n.get("SphereRadius", 100.0))})
                shape_class_idx = sphere_class
                shape_default_idx = sphere_default

            shape_export = {
                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                "ObjectName": shape_exp_name,
                "OuterIndex": idx_state,
                "ClassIndex": shape_class_idx,
                "TemplateIndex": shape_default_idx,
                "ObjectFlags": "RF_Transactional",
                "Data": shape_data,
                "SerializationBeforeSerializationDependencies": [],
                "CreateBeforeSerializationDependencies": [],
                "SerializationBeforeCreateDependencies": [shape_class_idx, shape_default_idx],
                "CreateBeforeCreateDependencies": [idx_state],
                "Extras": "AAAAAA=="
            }

            exports.extend([state_export, filter_export, shape_export])
            created_sub_indices.extend([idx_state, idx_filter, idx_shape])

            serialized_notifies.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "AnimNotifyEvent",
                "Name": "Notifies",
                "Value": [
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "Value": 0.0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "Value": 0.0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 1e-05},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": "PalAttackCollision"},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "Value": 0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "NotifyStateClass", "Value": idx_state},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": dur_val},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "TrackIndex", "Value": track_idx},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": time_val},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "MontageTickType", "ByteType": "FName", "EnumType": "EMontageNotifyTickType", "EnumValue": "EMontageNotifyTickType::Queued", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "NotifyFilterType", "ByteType": "FName", "EnumType": "ENotifyFilterType", "EnumValue": "ENotifyFilterType::NoFiltering", "IsZero": False}
                ]
            })

    main_props = main_exp.setdefault("Data", [])
    notifies_prop = next((p for p in main_props if isinstance(p, dict) and p.get("Name") == "Notifies"), None)
    if not notifies_prop:
        notifies_prop = {
            "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
            "ArrayType": "StructProperty",
            "Name": "Notifies",
            "Value": []
        }
        main_props.append(notifies_prop)

    notifies_prop["Value"] = serialized_notifies
    main_exp["CreateBeforeSerializationDependencies"] = list(set(main_exp.get("CreateBeforeSerializationDependencies", []) + created_sub_indices))

    ast["DependsMap"] = [[] for _ in range(len(exports))]

    # Fully synchronize NameMap (including all Property types) and update Generations NameCount
    sync_namemap(ast)
    return ast

def main():
    log("=== PalBaker Integration Test 18: Sequence Notify Injection ===")

    target_sidecar_path = r"F:\Users\ander\Documents\Unreal Projects\DeltemePls\Output\Exports\Pal\Content\Pal\Model\Character\Monster\Garm\SexyDirehowl\SexyDirehowl_blend.json"
    sidecar_data = None

    if os.path.exists(target_sidecar_path):
        log(f"Loading active sidecar: {target_sidecar_path}")
        with open(target_sidecar_path, "r", encoding="utf-8") as f:
            sidecar_data = json.load(f)
    else:
        fallback_path = os.path.join(REPO_ROOT, "templates", "SexyDirehowl_blend.json")
        if os.path.exists(fallback_path):
            log(f"Loading fallback sidecar: {fallback_path}")
            with open(fallback_path, "r", encoding="utf-8") as f:
                sidecar_data = json.load(f)

    assert sidecar_data is not None, f"Could not find SexyDirehowl_blend.json at '{target_sidecar_path}'"

    # Extract notifies
    anims_table = sidecar_data.get("custom_animations", {}).get("anims", {})
    kamitsuki_entry = anims_table.get("AS_SexyDirehowl_Kamitsuki", {})
    sequence_notifies = kamitsuki_entry.get("sequence_notifies", [])
    if not sequence_notifies:
        sequence_notifies = [n for n in kamitsuki_entry.get("notifies", []) if n.get("Source") == "sequence"]

    log(f"Found {len(sequence_notifies)} sequence notifies for AS_SexyDirehowl_Kamitsuki:")
    for n in sequence_notifies:
        log(f"  • [{n.get('Name')}] Time: {n.get('Time')}s | Bone: {n.get('AttachBone', 'None')}")

    assert len(sequence_notifies) > 0, "No sequence notifies found in sidecar."

    # Load empty template
    empty_template_file = os.path.join(REPO_ROOT, "templates", "AS_SexyDirehowl_Kamitsuki_Empty.json")
    with open(empty_template_file, "r", encoding="utf-8") as f:
        empty_ast = json.load(f)

    # Perform Injection
    log("\nInjecting notifies, creating sub-object exports, and synchronizing NameMap...")
    output_ast = inject_sequence_notifies(
        base_ast=empty_ast,
        notifies_list=sequence_notifies,
        sequence_name="AS_SexyDirehowl_Kamitsuki"
    )

    # Save output file (Preserved permanently on disk)
    output_file = os.path.join(REPO_ROOT, "templates", "AS_SexyDirehowl_Kamitsuki_Output.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_ast, f, indent=2)

    log(f"✓ Saved output AST: {output_file}")
    log(f"  -> Total NameMap entries: {len(output_ast['NameMap'])}")
    log(f"  -> Total Exports:         {len(output_ast['Exports'])}")

    # 1. Run through Safety Validator
    log("\nRunning output through UAssetSafetyValidator...")
    validator = UAssetSafetyValidator(output_ast)
    report = validator.validate()

    log(f"Safety Report: is_safe = {report['is_safe']}")
    if report["errors"]:
        for e in report["errors"]:
            log(f"  ❌ {e}", "ERROR")
    assert report["is_safe"] is True, f"Safety validation failed: {report['errors']}"

    # 2. Binary Compilation Test with UAssetGUI
    uasset_gui_exe = os.path.normpath(os.path.join(REPO_ROOT, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(REPO_ROOT, "deps", "Mappings.usmap"))

    if os.path.exists(uasset_gui_exe) and os.path.exists(usmap_path):
        log("\nCompiling JSON to binary .uasset with UAssetGUI CLI...")
        test_uasset_path = os.path.join(REPO_ROOT, "templates", "AS_SexyDirehowl_Kamitsuki_Output.uasset")
        compiled = compile_uasset(uasset_gui_exe, output_file, test_uasset_path, usmap_path)
        assert compiled and os.path.exists(test_uasset_path), "UAssetGUI failed to compile output JSON!"
        log(f"🎉 SUCCESS! Compiled binary without serialization errors: {test_uasset_path} ({os.path.getsize(test_uasset_path)} bytes)")

    log("\n" + "=" * 70)
    log("🎉 TEST 18 COMPLETE! Output file preserved for examination:")
    log(f"  -> {output_file}")
    log("=" * 70)

if __name__ == "__main__":
    main()