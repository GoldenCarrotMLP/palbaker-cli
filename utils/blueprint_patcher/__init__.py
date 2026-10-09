# utils/blueprint_patcher/__init__.py
import os
import sys
import re
import json
import shutil
import glob
import subprocess

from utils.extractor.core import extract_game_files
from .build_variants import build_boss_variant, build_predator_variant, build_raid_variant
from .feature_manager import (
    BlueprintFeatureManager,
    synthesize_funnel_character_ast,
    synthesize_flamethrower_cluster
)
from utils.anim_patcher.anim_discovery import extract_track_name

from utils.uasset_helper import (
    decompile_uasset, 
    compile_uasset, 
    sync_namemap, 
    patch_montage_ast, 
    sanitize_anim_sequence_notifies,
    patch_anim_sequence_ast,
    encode_guid_to_extras
)


def _collect_and_sync_namemap(data: dict):
    if not isinstance(data, dict):
        return

    name_map = data.setdefault("NameMap", [])
    existing_names = set(name_map)

    def add_name(val):
        if isinstance(val, str) and val and val not in existing_names:
            name_map.append(val)
            existing_names.add(val)

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("Name", "ObjectName", "ClassName", "ClassPackage", "PackageName", 
                         "AssetName", "StructType", "EnumType", "InnerType", "ArrayType"):
                    add_name(v)
                elif k == "Value":
                    if isinstance(v, str):
                        add_name(v)
                    elif isinstance(v, (list, dict)):
                        walk(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data.get("Exports", []))
    walk(data.get("Imports", []))
    sync_namemap(data)


def find_skeleton_guid_in_json(json_path: str) -> str:
    if not json_path or not os.path.exists(json_path):
        return ""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def search(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.lower() in ["skeletonguid", "virtualboneguid"] and isinstance(v, str) and len(v) >= 32:
                        return v
                    res = search(v)
                    if res:
                        return res
            elif isinstance(node, list):
                for item in node:
                    res = search(item)
                    if res:
                        return res
            return None

        found = search(data)
        if found:
            return found

        for exp in data.get("Exports", []):
            if isinstance(exp, dict) and "Skeleton" in str(exp.get("ObjectName", "")):
                extras_guid = decode_extras_to_guid(exp.get("Extras", ""))
                if extras_guid:
                    return extras_guid
        return ""
    except Exception:
        return ""


def _inject_waza_declaration(base_json_data: dict, waza_id_enum: str, action_class_package: str, action_class_name: str):
    comp = None
    for exp in base_json_data.get("Exports", []):
        if exp.get("ObjectName") == "StaticCharacterParameterComponent":
            comp = exp
            break

    if not comp:
        return

    comp_data = comp.setdefault("Data", [])
    waza_prop = next((p for p in comp_data if isinstance(p, dict) and p.get("Name") == "WazaActionDeclarationMap"), None)
    if not waza_prop:
        waza_prop = {
            "$type": "UAssetAPI.PropertyTypes.Objects.MapPropertyData, UAssetAPI",
            "Name": "WazaActionDeclarationMap",
            "Value": [],
            "KeysToRemove": []
        }
        comp_data.append(waza_prop)

    clean_waza_key = waza_id_enum if "::" in waza_id_enum else f"EPalWazaID::{waza_id_enum}"

    map_val = waza_prop.setdefault("Value", [])
    waza_prop["Value"] = [
        e for e in map_val
        if not (isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and e[0].get("Value") == clean_waza_key)
    ]
    map_val = waza_prop["Value"]

    map_val.append([
        {
            "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
            "EnumType": None,
            "InnerType": None,
            "Name": "WazaActionDeclarationMap",
            "ArrayIndex": 0,
            "PropertyGuid": None,
            "IsZero": False,
            "PropertyTagFlags": "None",
            "PropertyTypeName": None,
            "PropertyTagExtensions": "NoExtension",
            "Value": clean_waza_key
        },
        {
            "$type": "UAssetAPI.PropertyTypes.Objects.SoftObjectPropertyData, UAssetAPI",
            "Name": "WazaActionDeclarationMap",
            "ArrayIndex": 0,
            "PropertyGuid": None,
            "IsZero": False,
            "PropertyTagFlags": "None",
            "PropertyTypeName": None,
            "PropertyTagExtensions": "NoExtension",
            "Value": {
                "$type": "UAssetAPI.PropertyTypes.Objects.FSoftObjectPath, UAssetAPI",
                "AssetPath": {
                    "$type": "UAssetAPI.PropertyTypes.Objects.FTopLevelAssetPath, UAssetAPI",
                    "PackageName": action_class_package,
                    "AssetName": action_class_name
                },
                "SubPathString": None
            }
        }
    ])

    name_map = base_json_data.setdefault("NameMap", [])
    for s in [clean_waza_key, action_class_package, action_class_name, "WazaActionDeclarationMap", "AssetPath", "PackageName", "AssetName"]:
        if s and s not in name_map:
            name_map.append(s)

    _collect_and_sync_namemap(base_json_data)

def _synthesize_montage_from_seed(
    repo_root: str,
    pal_id: str,
    montage_name: str,
    sequence_name: str,
    track_name: str,
    duration: float,
    skeleton_guid: str,
    notifies: list,
    cat_sanitized: str,
    target_anims_folder: str,
    cooked_anims_dir: str,
    temp_dir: str,
    uasset_gui_exe: str,
    usmap_path: str,
    log
) -> bool:
    seed_uasset = os.path.normpath(os.path.join(repo_root, "templates", "AM_Kitsunebi_Cooking.uasset"))
    if not os.path.exists(seed_uasset):
        log(f"  ❌ Seed template missing at {seed_uasset}", "error")
        return False

    seed_json = os.path.join(temp_dir, "universal_seed_montage.json")
    if not os.path.exists(seed_json):
        if not decompile_uasset(uasset_gui_exe, seed_uasset, seed_json, usmap_path):
            log(f"  ❌ Failed to decompile seed montage template", "error")
            return False

    with open(seed_json, "r", encoding="utf-8") as f_seed:
        seed_data = json.load(f_seed)

    # =========================================================================
    # REPAIR MISSING HEADER CUSTOM VERSIONS
    # =========================================================================
    if not seed_data.get("CustomVersionContainer"):
        seed_data["CustomVersionContainer"] = [
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{375EC13C-06E4-48FB-B500-84F0262A717E}", "FriendlyName": "FCoreObjectVersion", "Version": 4, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{E4B068ED-F494-42E9-A231-DA0B2E46BB41}", "FriendlyName": "FEditorObjectVersion", "Version": 40, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{CFFC743F-43B0-4480-9391-14DF171D2073}", "FriendlyName": "FFrameworkObjectVersion", "Version": 37, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{7B5AE74C-D270-4C10-A958-57980B212A5A}", "FriendlyName": "FSequencerObjectVersion", "Version": 13, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{29E575DD-E0A3-4627-9D10-D276232CDCEA}", "FriendlyName": "FAnimPhysObjectVersion", "Version": 17, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{601D1886-AC64-4F84-AA16-D3DE0DEAC7D6}", "FriendlyName": "FFortniteMainBranchObjectVersion", "Version": 80, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{F2AED0AC-9AFE-416F-8664-AA7FFA26D6FC}", "FriendlyName": "FNiagaraObjectVersion", "Version": 1, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{717F9EE7-E9B0-493A-88B3-91321B388107}", "FriendlyName": "FAssetRegistryVersion", "Version": 17, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{9C54D522-A826-4FBE-9421-074661B482D0}", "FriendlyName": "FReleaseObjectVersion", "Version": 44, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{E7086368-6B23-4C58-8439-1B7016265E91}", "FriendlyName": "FFortniteReleaseBranchCustomObjectVersion", "Version": 4, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{D89B5E42-24BD-4D46-8412-ACA8DF641779}", "FriendlyName": "FUE5ReleaseStreamObjectVersion", "Version": 41, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{FCF57AFA-5076-4283-B9A9-E658FFA02D32}", "FriendlyName": "FNiagaraCustomVersion", "Version": 76, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{59DA5D52-1232-4948-B878-597870B8E98B}", "FriendlyName": "FUE5SpecialProjectStreamObjectVersion", "Version": 8, "IsSerialized": False},
            {"$type": "UAssetAPI.CustomVersion, UAssetAPI", "Key": "{E21E1CAA-AF47-425E-89BF-6AD44C44A8BB}", "FriendlyName": "FInstancedStructCustomVersion", "Version": 1, "IsSerialized": False}
        ]

    # 1. PURGE TEMPLATE EXPORTS: Keep ONLY Exports[0]
    seed_data["Exports"] = [seed_data["Exports"][0]]
    montage_export = seed_data["Exports"][0]
    montage_export["ObjectName"] = montage_name
    if "FolderName" in seed_data:
        seed_data["FolderName"] = f"/Game/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}/{montage_name}"

    # 2. BUILD CLEAN, EXPLICIT IMPORTS TABLE
    skel_pkg = f"/Game/Pal/Model/Character/Skeleton/{target_anims_folder}/SK_{pal_id}_Skeleton"
    skel_name = f"SK_{pal_id}_Skeleton"
    seq_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}/{sequence_name}"

    clean_imports = []
    def add_imp(obj_name, class_name, class_pkg, outer_idx):
        new_imp = {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": obj_name,
            "OuterIndex": outer_idx,
            "ClassPackage": class_pkg,
            "ClassName": class_name,
            "PackageName": None,
            "bImportOptional": False
        }
        clean_imports.append(new_imp)
        return -len(clean_imports)

    core_pkg_idx = add_imp("/Script/CoreUObject", "Package", "/Script/CoreUObject", 0)
    engine_pkg_idx = add_imp("/Script/Engine", "Package", "/Script/CoreUObject", 0)

    montage_class_idx = add_imp("AnimMontage", "Class", "/Script/CoreUObject", engine_pkg_idx)
    default_montage_idx = add_imp("Default__AnimMontage", "AnimMontage", "/Script/Engine", engine_pkg_idx)

    skel_pkg_idx = add_imp(skel_pkg, "Package", "/Script/CoreUObject", 0)
    skel_obj_idx = add_imp(skel_name, "Skeleton", "/Script/Engine", skel_pkg_idx)

    seq_pkg_idx = add_imp(seq_pkg, "Package", "/Script/CoreUObject", 0)
    seq_obj_idx = add_imp(sequence_name, "AnimSequence", "/Script/Engine", seq_pkg_idx)

    seed_data["Imports"] = clean_imports

    # 3. DIRECTLY BIND EXPORT CLASS & TEMPLATE POINTERS
    montage_export["ClassIndex"] = montage_class_idx
    montage_export["TemplateIndex"] = default_montage_idx
    montage_export["OuterIndex"] = 0
    montage_export["SuperIndex"] = 0

    is_looping = any(k in track_name.lower() or k in montage_name.lower() for k in ["loop", "petting", "eating", "spa"])

    # 4. CONSTRUCT CLEAN COMPOSITE SECTIONS & TRACKS
    composite_sections = [
        {
            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
            "StructType": "CompositeSection",
            "SerializeNone": True,
            "StructGUID": "{00000000-0000-0000-0000-000000000000}",
            "Name": "0",
            "Value": [
                {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "SectionName", "Value": "Default"},
                {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NextSectionName", "Value": "Default" if is_looping else "None"},
                {"$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI", "Name": "Metadata", "IsZero": True, "Value": []},
                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedMontage", "Value": 1},
                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SlotIndex", "IsZero": True, "Value": 0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SegmentIndex", "IsZero": True, "Value": 0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI", "EnumType": "EAnimLinkMethod", "InnerType": "ByteProperty", "Name": "LinkMethod", "IsZero": True, "Value": "Absolute"},
                {"$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI", "EnumType": "EAnimLinkMethod", "InnerType": "ByteProperty", "Name": "CachedLinkMethod", "IsZero": True, "Value": "Absolute"},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentBeginTime", "IsZero": True, "Value": "+0"},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentLength", "Value": float(duration)},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "IsZero": True, "Value": "+0"},
                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedSequence", "Value": seq_obj_idx}
            ]
        }
    ]

    slot_anim_tracks = [
        {
            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
            "StructType": "SlotAnimationTrack",
            "SerializeNone": True,
            "StructGUID": "{00000000-0000-0000-0000-000000000000}",
            "Name": "0",
            "Value": [
                {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "SlotName", "Value": "DefaultSlot"},
                {
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "StructType": "AnimTrack",
                    "Name": "AnimTrack",
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                            "ArrayType": "StructProperty",
                            "Name": "AnimSegments",
                            "Value": [
                                {
                                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                                    "StructType": "AnimSegment",
                                    "SerializeNone": True,
                                    "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                                    "Name": "0",
                                    "Value": [
                                        {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "AnimReference", "Value": seq_obj_idx},
                                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "StartPos", "IsZero": True, "Value": "+0"},
                                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "AnimStartTime", "IsZero": True, "Value": "+0"},
                                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "AnimEndTime", "Value": float(duration)},
                                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "AnimPlayRate", "Value": 1.0},
                                        {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "LoopingCount", "Value": 1}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    # 5. SERIALIZE NOTIFIES (Or provide safe DummyStruct for empty lists)
    serialized_notifies = []
    for idx, n in enumerate(notifies):
        n_name = n.get("Name", "PalCustomNotify")
        n_time = float(n.get("Time", 0.0))
        n_dur = float(n.get("Duration", 0.0))
        n_track = int(n.get("Track", 0))

        serialized_notifies.append({
            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
            "StructType": "AnimNotifyEvent",
            "Name": str(idx),
            "Value": [
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "IsZero": True, "Value": 0.0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "IsZero": True, "Value": 0.0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 1e-05},
                {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": n_name},
                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "IsZero": True, "Value": 0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "NotifyStateClass", "IsZero": True, "Value": 0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": n_dur},
                {
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "StructType": "AnimLinkableElement",
                    "Name": "EndLink",
                    "Value": [
                        {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedMontage", "IsZero": True, "Value": 0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SlotIndex", "IsZero": True, "Value": 0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SegmentIndex", "Value": -1},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentBeginTime", "IsZero": True, "Value": "+0"},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentLength", "IsZero": True, "Value": "+0"},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "IsZero": True, "Value": "+0"},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedSequence", "IsZero": True, "Value": 0}
                    ]
                },
                {"$type": "UAssetAPI.PropertyTypes.Objects.BoolPropertyData, UAssetAPI", "Name": "bConvertedFromBranchingPoint", "IsZero": True, "Value": False},
                {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "MontageTickType", "ByteType": "FName", "EnumType": "EMontageNotifyTickType", "EnumValue": "EMontageNotifyTickType::Queued", "IsZero": False},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "NotifyTriggerChance", "Value": 1.0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "NotifyFilterType", "ByteType": "FName", "EnumType": "ENotifyFilterType", "EnumValue": "ENotifyFilterType::NoFiltering", "IsZero": False},
                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "NotifyFilterLOD", "IsZero": True, "Value": 0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.BoolPropertyData, UAssetAPI", "Name": "bTriggerOnDedicatedServer", "Value": True},
                {"$type": "UAssetAPI.PropertyTypes.Objects.BoolPropertyData, UAssetAPI", "Name": "bTriggerOnFollower", "IsZero": True, "Value": False},
                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "TrackIndex", "Value": n_track},
                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedMontage", "Value": 1},
                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SlotIndex", "IsZero": True, "Value": 0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SegmentIndex", "IsZero": True, "Value": 0},
                {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentBeginTime", "IsZero": True, "Value": "+0"},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentLength", "Value": float(duration)},
                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": n_time},
                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedSequence", "Value": seq_obj_idx}
            ]
        })

    new_montage_data = [
        {
            "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
            "ArrayType": "StructProperty",
            "Name": "CompositeSections",
            "Value": composite_sections
        },
        {
            "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
            "ArrayType": "StructProperty",
            "Name": "SlotAnimTracks",
            "Value": slot_anim_tracks
        },
        {
            "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
            "Name": "SequenceLength",
            "Value": float(duration)
        },
        {
            "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
            "Name": "Skeleton",
            "Value": skel_obj_idx
        }
    ]

    if serialized_notifies:
        new_montage_data.append({
            "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
            "ArrayType": "StructProperty",
            "DummyStruct": {
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "AnimNotifyEvent",
                "Name": "Notifies",
                "Value": []
            },
            "Name": "Notifies",
            "Value": serialized_notifies
        })

    montage_export["Data"] = new_montage_data
    montage_export["CreateBeforeSerializationDependencies"] = [seq_obj_idx, skel_obj_idx]
    montage_export["SerializationBeforeCreateDependencies"] = [montage_class_idx, default_montage_idx]
    montage_export["CreateBeforeCreateDependencies"] = []
    montage_export["SerializationBeforeSerializationDependencies"] = []
    seed_data["DependsMap"] = [[]]

    # Enforcement of Tagged Serialization (prevents unversioned schema lookup failure)
    seed_data["HasUnversionedProperties"] = False
    seed_data["IsUnversioned"] = False

    pkg_flags = seed_data.get("PackageFlags", "")
    if isinstance(pkg_flags, str):
        cleaned_flags = [f.strip() for f in pkg_flags.split(",") if f.strip() and f.strip() != "PKG_UnversionedProperties"]
        seed_data["PackageFlags"] = ", ".join(cleaned_flags)
    elif isinstance(pkg_flags, int):
        seed_data["PackageFlags"] &= ~0x00002000

    if skeleton_guid:
        montage_export["Extras"] = encode_guid_to_extras(skeleton_guid)

    temp_montage_json = os.path.join(temp_dir, f"{montage_name}_synth.json")
    _collect_and_sync_namemap(seed_data)
    with open(temp_montage_json, "w", encoding="utf-8") as f_out:
        json.dump(seed_data, f_out, indent=4)

    dest_am_uasset = os.path.join(cooked_anims_dir, f"{montage_name}.uasset")
    if compile_uasset(uasset_gui_exe, temp_montage_json, dest_am_uasset, usmap_path):
        log(f"  ✓ Synthesized AnimMontage: {montage_name}.uasset ({len(notifies)} notifies, {duration:.2f}s)", "success")
        return True
    else:
        log(f"  ❌ Failed to compile synthesized montage: {montage_name}.uasset", "error")
        return False


def _process_unique_waza_actions(
    settings: dict,
    pal_id: str,
    template_id: str,
    pal_data: dict,
    custom_anims: dict,
    has_anims: bool,
    category: str,
    base_pal: str,
    is_variant: bool,
    temp_dir: str,
    cooked_base_content: str,
    cooked_anims_dir: str,
    uasset_gui_exe: str,
    usmap_path: str,
    custom_guid: str,
    vanilla_guid: str,
    base_json_data: dict,
    log
) -> bool:
    anims_dict = custom_anims.get("anims", {}) if isinstance(custom_anims, dict) else {}

    assigned_wazas = []
    for entry in pal_data.get("Learnset", []):
        if isinstance(entry, dict):
            wid = entry.get("WazaID", "")
            if wid and isinstance(wid, str) and wid.startswith("Unique_") and wid not in assigned_wazas:
                assigned_wazas.append(wid)

    funnel_waza = pal_data.get("Features", {}).get("Funnel", {}).get("CustomWazaID", "")
    if isinstance(funnel_waza, str) and funnel_waza.startswith("EPalWazaID::Unique_"):
        clean_fw = funnel_waza.replace("EPalWazaID::", "")
        if clean_fw not in assigned_wazas:
            assigned_wazas.append(clean_fw)

    if not assigned_wazas:
        return True

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cat_sanitized = category.replace(" ", "_")
    target_anims_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
    target_skel_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
    v_new_anim_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}"

    action_dest_dir = os.path.join(cooked_base_content, "Pal", "Blueprint", "Action", "Waza", pal_id)
    os.makedirs(action_dest_dir, exist_ok=True)

    log(f"  [Unique Attacks] Evaluating {len(assigned_wazas)} assigned unique attack(s)...", "standard")

    waza_declarations_to_add = {}

    for waza in assigned_wazas:
        clean_waza = str(waza).replace("EPalWazaID::", "").strip()
        suffix = clean_waza.replace("Unique_", "")
        parts = suffix.split("_")
        donor_pal = parts[0] if parts else ""
        skill_name = "_".join(parts[1:]) if len(parts) > 1 else suffix

        if (donor_pal and donor_pal.lower() == pal_id.lower()) or not donor_pal:
            donor_pal = template_id

        skill_name_lower = (skill_name or "").lower()
        donor_pal_lower = (donor_pal or "").lower()
        clean_waza_lower = (clean_waza or "").lower()
        waza_full = f"EPalWazaID::{clean_waza}"

        has_matching_montage = False

        for ak, av in anims_dict.items():
            if not isinstance(av, dict):
                continue
            if av.get("enum_key") in (clean_waza, waza_full):
                has_matching_montage = True
                break

            t_name = str(av.get("nla_track_name") or "").lower()
            m_name = str(av.get("montage_asset") or "").lower()

            if (skill_name_lower and skill_name_lower in t_name) or (skill_name_lower and skill_name_lower in m_name):
                has_matching_montage = True
                break

            for notif in av.get("montage_notifies") or []:
                if isinstance(notif, dict) and notif.get("WazaID") in (clean_waza, waza_full):
                    has_matching_montage = True
                    break
            if has_matching_montage:
                break

        if not has_matching_montage:
            if donor_pal_lower == (template_id or "").lower() and not has_anims:
                has_matching_montage = True
            else:
                log(f"  ❌ Error: Unique attack '{clean_waza}' in learnset has no animation montages configured in animations/sidecar for '{pal_id}'.", "error")
                return False

        donor_extract_patterns = [
            f"Pal/Content/Pal/Blueprint/Action/Waza/{donor_pal}/*{skill_name}*",
            f"Pal/Content/Pal/Blueprint/Action/Waza/{donor_pal}/*",
            f"Pal/Content/Pal/Blueprint/Action/*{donor_pal}*{skill_name}*",
            f"Pal/Content/Pal/Animation/Character/*/{donor_pal}/*{skill_name}*"
        ]
        extract_game_files(settings, donor_extract_patterns, temp_dir, format_type="raw")

        donor_action_uasset = None
        for root, _, files in os.walk(temp_dir):
            root_clean = root.lower().replace("\\", "/")
            for f in files:
                f_low = (f or "").lower()
                if f_low.endswith(".uasset") and ("action" in f_low or "waza" in f_low):
                    if skill_name_lower in f_low and (donor_pal_lower in f_low or f"/{donor_pal_lower}/" in root_clean):
                        donor_action_uasset = os.path.join(root, f)
                        break
            if donor_action_uasset:
                break

        if not donor_action_uasset:
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    f_low = (f or "").lower()
                    if f_low.endswith(".uasset") and ("action" in f_low or "waza" in f_low):
                        if skill_name_lower in f_low:
                            donor_action_uasset = os.path.join(root, f)
                            break
                if donor_action_uasset:
                    break

        if not donor_action_uasset or not os.path.exists(donor_action_uasset):
            log(f"  ❌ Error: Could not locate Action Blueprint for waza '{clean_waza}' (Donor: {donor_pal}).", "error")
            return False

        donor_action_name = os.path.splitext(os.path.basename(donor_action_uasset))[0]
        donor_action_json = donor_action_uasset.replace(".uasset", ".json")

        if not decompile_uasset(uasset_gui_exe, donor_action_uasset, donor_action_json, usmap_path):
            log(f"  ❌ Failed to decompile Action Blueprint: {donor_action_name}", "error")
            return False

        with open(donor_action_json, "r", encoding="utf-8") as f_daj:
            action_content = f_daj.read()

        module_pattern = re.compile(rf'((?:/Game|Pal/Content)/Pal/Blueprint/Action/[\w/]*/(BP_UniqueSkillModule_[a-zA-Z0-9_]+))', re.IGNORECASE)
        found_modules = set(module_pattern.findall(action_content))
        for m_path, m_name in found_modules:
            norm_m_path = m_path.replace("/Game/", "Pal/Content/")
            extract_game_files(settings, [f"{norm_m_path}.uasset", f"{norm_m_path}.uexp"], temp_dir, format_type="raw")
            mod_uasset = os.path.join(temp_dir, f"{norm_m_path}.uasset")
            if os.path.exists(mod_uasset):
                mod_json = mod_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, mod_uasset, mod_json, usmap_path)
                with open(mod_json, "r", encoding="utf-8") as f_mj:
                    m_content = f_mj.read()

                new_mod_name = m_name.replace(donor_pal, pal_id)
                new_mod_path_core = norm_m_path.replace(donor_pal, pal_id)

                m_content = m_content.replace(donor_pal, pal_id)
                m_content = m_content.replace(m_name, new_mod_name)

                try:
                    m_data = json.loads(m_content)
                    if "FolderName" in m_data:
                        m_data["FolderName"] = new_mod_path_core.replace("Pal/Content/", "/Game/")
                    _collect_and_sync_namemap(m_data)
                    with open(mod_json, "w", encoding="utf-8") as f_mj:
                        json.dump(m_data, f_mj, indent=4)
                except Exception:
                    with open(mod_json, "w", encoding="utf-8") as f_mj:
                        f_mj.write(m_content)

                mod_dest_dir = os.path.join(cooked_base_content, os.path.dirname(new_mod_path_core.replace("Pal/Content/", "")))
                os.makedirs(mod_dest_dir, exist_ok=True)
                compile_uasset(uasset_gui_exe, mod_json, os.path.join(mod_dest_dir, f"{new_mod_name}.uasset"), usmap_path)
                log(f"  ✓ Compiled Unique Skill Module: {new_mod_name}", "standard")

        montage_remap = {}
        montage_refs = re.findall(rf'AM_{donor_pal}_[a-zA-Z0-9_]+', action_content)

        if montage_refs:
            extract_patterns = []
            for m in set(montage_refs):
                extract_patterns.append(f"Pal/Content/Pal/Animation/Character/*/{donor_pal}/{m}.uasset")
                extract_patterns.append(f"Pal/Content/Pal/Animation/Character/*/{donor_pal}/{m}.uexp")
            extract_game_files(settings, extract_patterns, temp_dir, format_type="raw")

        for d_am in set(montage_refs):
            m_track = d_am.replace(f"AM_{donor_pal}_", "")
            target_am_name = f"AM_{pal_id}_{m_track}"

            user_am_entry = None
            for ak, av in anims_dict.items():
                if isinstance(av, dict):
                    user_m = av.get("montage_asset")
                    user_t = av.get("nla_track_name")
                    if user_m and str(user_m).lower() == target_am_name.lower():
                        user_am_entry = av
                        break
                    if user_t and str(user_t).lower() == m_track.lower():
                        user_am_entry = av
                        break
                    if av.get("enum_key") in (clean_waza, waza_full):
                        user_m_str = str(user_m).lower() if user_m else ""
                        user_t_str = str(user_t).lower() if user_t else ""
                        if (m_track and m_track.lower() in user_m_str) or (m_track and m_track.lower() in user_t_str):
                            user_am_entry = av
                            break

            if user_am_entry:
                if user_am_entry.get("montage_asset"):
                    target_am_name = user_am_entry["montage_asset"]

            donor_am_uasset = None
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if f.lower() == f"{d_am.lower()}.uasset":
                        donor_am_uasset = os.path.join(root, f)
                        break
                if donor_am_uasset: break
            
            if donor_am_uasset:
                d_json = donor_am_uasset.replace(".uasset", ".json")
                if decompile_uasset(uasset_gui_exe, donor_am_uasset, d_json, usmap_path):
                    
                    patched_ast = patch_montage_ast(
                        seed_data=d_json,
                        template_id=donor_pal,
                        target_pal=pal_id,
                        anim_name=target_am_name,
                        skeleton_guid=custom_guid if has_anims else vanilla_guid,
                        notifies=None
                    )
                    
                    if "FolderName" in patched_ast:
                        patched_ast["FolderName"] = f"{v_new_anim_pkg}/{target_am_name}"
                        
                    _collect_and_sync_namemap(patched_ast)
                    
                    out_am_json = os.path.join(temp_dir, f"{target_am_name}_cloned.json")
                    with open(out_am_json, "w", encoding="utf-8") as f:
                        json.dump(patched_ast, f, indent=2)
                        
                    dest_am = os.path.join(cooked_anims_dir, f"{target_am_name}.uasset")
                    if compile_uasset(uasset_gui_exe, out_am_json, dest_am, usmap_path):
                        log(f"  ✓ Cloned & Retargeted Donor Montage: {target_am_name}", "success")
                        if user_am_entry:
                            user_am_entry["_is_cloned"] = True
                    else:
                        log(f"  ❌ Failed to compile Cloned Montage: {target_am_name}", "error")
            else:
                log(f"  ⚠️ Warning: Donor montage {d_am} not found on disk! It will be synthesized from scratch.", "warning")

            montage_remap[d_am] = target_am_name

        new_action_name = donor_action_name.replace(donor_pal, pal_id)
        new_action_pkg = f"/Game/Pal/Blueprint/Action/Waza/{pal_id}/{new_action_name}"
        new_action_class = f"{new_action_name}_C"

        donor_action_pkg = f"/Game/Pal/Blueprint/Action/Waza/{donor_pal}/{donor_action_name}"
        action_content = action_content.replace(donor_action_pkg, new_action_pkg)

        action_content = action_content.replace(f"Default__{donor_action_name}_C", f"Default__{new_action_name}_C")
        action_content = action_content.replace(f"Default__{donor_action_name}", f"Default__{new_action_name}")
        action_content = action_content.replace(f"ExecuteUbergraph_{donor_action_name}", f"ExecuteUbergraph_{new_action_name}")
        action_content = action_content.replace(f"{donor_action_name}_C", f"{new_action_class}")
        action_content = re.sub(rf"(?<![A-Za-z0-9_]){donor_action_name}(?![A-Za-z0-9_])", new_action_name, action_content)

        for d_am, target_am_name in montage_remap.items():
            action_content = action_content.replace(f'"{d_am}"', f'"{target_am_name}"')
            action_content = action_content.replace(f"'{d_am}'", f"'{target_am_name}'")
            action_content = action_content.replace(
                f"/Game/Pal/Animation/Character/Monster/{donor_pal}/{d_am}",
                f"{v_new_anim_pkg}/{target_am_name}"
            )
            action_content = action_content.replace(
                f"Pal/Content/Pal/Animation/Character/Monster/{donor_pal}/{d_am}",
                f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}/{target_am_name}"
            )
            action_content = re.sub(rf"(?<![A-Za-z0-9_]){d_am}(?![A-Za-z0-9_])", target_am_name, action_content)

        for m_path, m_name in found_modules:
            new_mod_name = m_name.replace(donor_pal, pal_id)
            new_mod_pkg = m_path.replace("/Game/", "").replace("Pal/Content/", "").replace(donor_pal, pal_id)
            action_content = action_content.replace(m_name, new_mod_name)
            action_content = action_content.replace(m_path, f"/Game/{new_mod_pkg}")

        try:
            act_data = json.loads(action_content)
            if "FolderName" in act_data:
                act_data["FolderName"] = new_action_pkg
            _collect_and_sync_namemap(act_data)
            with open(donor_action_json, "w", encoding="utf-8") as f_daj:
                json.dump(act_data, f_daj, indent=4)
        except Exception:
            with open(donor_action_json, "w", encoding="utf-8") as f_daj:
                f_daj.write(action_content)

        dest_action_uasset = os.path.join(action_dest_dir, f"{new_action_name}.uasset")
        compile_ok = compile_uasset(uasset_gui_exe, donor_action_json, dest_action_uasset, usmap_path)
        if compile_ok and os.path.exists(dest_action_uasset):
            log(f"  ✓ Compiled Action Blueprint: {new_action_name}.uasset", "success")
            waza_declarations_to_add[clean_waza] = (new_action_pkg, new_action_class)
        else:
            log(f"  ❌ Failed to compile Action Blueprint: {new_action_name}", "error")
            return False

    for waza_name, (act_pkg, act_cls) in waza_declarations_to_add.items():
        waza_enum = f"EPalWazaID::{waza_name}"
        _inject_waza_declaration(base_json_data, waza_enum, act_pkg, act_cls)
        log(f"  ✓ Bound {waza_enum} in WazaActionDeclarationMap -> {act_cls}", "standard")

    return True

def _patch_cooked_animation_sequences(
    settings: dict,
    template_id: str,
    pal_id: str,
    category: str,
    base_pal: str,
    is_variant: bool,
    custom_guid: str,
    has_anims: bool,
    temp_dir: str,
    cooked_anims_dir: str,
    uasset_gui_exe: str,
    usmap_path: str,
    custom_anims: dict,
    log
):
    anims_dict = custom_anims.get("anims", {}) if isinstance(custom_anims, dict) else {}
    if not anims_dict:
        return

    cat_sanitized = category.replace(" ", "_")
    target_anims_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id

    template_as_files = {}
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.startswith("AS_") and f.endswith(".uasset"):
                template_as_files[f.lower()] = os.path.join(root, f)

    log(f"  [Sequence Patching] Syncing root motion & sequence notifies for {len(anims_dict)} tracks...", "standard")

    patched_count = 0
    for anim_key, anim_meta in anims_dict.items():
        if not isinstance(anim_meta, dict):
            continue

        seq_name = anim_meta.get("sequence_asset")
        track_name = anim_meta.get("nla_track_name") or ""
        if not seq_name and track_name:
            seq_name = f"AS_{pal_id}_{track_name}"
        if not seq_name:
            seq_name = anim_key

        if seq_name and str(seq_name).lower().endswith("_hit"):
            continue

        enable_rm = bool(anim_meta.get("enable_root_motion", False))
        seq_notifies = anim_meta.get("sequence_notifies")
        if seq_notifies is None:
            seq_notifies = [n for n in anim_meta.get("notifies", []) if n.get("Source") == "sequence"]

        dest_as_uasset = os.path.join(cooked_anims_dir, f"{seq_name}.uasset")
        template_seq_name = f"AS_{template_id}_{track_name}" if track_name else seq_name.replace(pal_id, template_id)
        tmpl_uasset = template_as_files.get(template_seq_name.lower()) if template_seq_name else None

        target_base_uasset = None
        template_ast = None

        if os.path.exists(dest_as_uasset):
            target_base_uasset = dest_as_uasset
            if tmpl_uasset and os.path.exists(tmpl_uasset):
                tmpl_json = os.path.join(temp_dir, f"tmpl_{os.path.basename(tmpl_uasset)}.json")
                if decompile_uasset(uasset_gui_exe, tmpl_uasset, tmpl_json, usmap_path):
                    with open(tmpl_json, "r", encoding="utf-8") as f_tmpl:
                        template_ast = json.load(f_tmpl)
        elif tmpl_uasset and os.path.exists(tmpl_uasset):
            target_base_uasset = tmpl_uasset

        if not target_base_uasset or not os.path.exists(target_base_uasset):
            continue

        temp_as_json = os.path.join(temp_dir, f"patch_{seq_name}.json")
        if not decompile_uasset(uasset_gui_exe, target_base_uasset, temp_as_json, usmap_path):
            continue

        with open(temp_as_json, "r", encoding="utf-8") as f_in:
            base_data = json.load(f_in)

        patched_ast = patch_anim_sequence_ast(
            data=base_data,
            template_id=template_id,
            target_pal=pal_id,
            anim_name=track_name,
            skeleton_guid=custom_guid if has_anims else None,
            enable_root_motion=enable_rm,
            sequence_notifies=seq_notifies,
            template_as_data=template_ast
        )

        with open(temp_as_json, "w", encoding="utf-8") as f_out:
            json.dump(patched_ast, f_out, indent=2)

        if compile_uasset(uasset_gui_exe, temp_as_json, dest_as_uasset, usmap_path):
            patched_count += 1
            rm_label = "Enabled" if enable_rm else "Disabled"
            not_count = len(seq_notifies) if seq_notifies else 0
            log(f"  ✓ Processed AnimSequence: {seq_name}.uasset (Root Motion: {rm_label}, Notifies: {not_count})", "standard")

    log(f"  ✓ Successfully applied changes to {patched_count} AnimSequence assets.", "success")


def _retarget_additive_hit_animations(
    settings: dict,
    template_id: str,
    pal_id: str,
    category: str,
    base_pal: str,
    is_variant: bool,
    custom_guid: str,
    has_anims: bool,
    temp_dir: str,
    cooked_anims_dir: str,
    uasset_gui_exe: str,
    usmap_path: str,
    log
):
    cat_sanitized = category.replace(" ", "_")
    target_skel_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
    target_anims_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id

    v_new_anim_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}"
    v_new_skel_pkg = f"/Game/Pal/Model/Character/Skeleton/{target_skel_folder}"

    extract_patterns = [
        f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/*Hit*",
        f"Pal/Content/Pal/Animation/Character/Monster/{template_id}/*Hit*",
        f"Pal/Content/Pal/Animation/Character/Pending_Monster/{template_id}/*Hit*",
        f"Pal/Content/Pal/Animation/Character/Pending Monster/{template_id}/*Hit*"
    ]
    extract_game_files(settings, extract_patterns, temp_dir, format_type="raw")

    hit_uassets = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            f_lower = str(f or "").lower()
            if (f_lower.startswith(f"as_{template_id.lower()}_hit") or f_lower.startswith(f"am_{template_id.lower()}_hit")) and f_lower.endswith(".uasset"):
                hit_uassets.append(os.path.join(root, f))

    if not hit_uassets:
        return

    log(f"  [Hit Retargeting] Discovered {len(hit_uassets)} parent Hit asset(s) to retarget...", "standard")

    for uasset_path in hit_uassets:
        base_fname = os.path.splitext(os.path.basename(uasset_path))[0]
        new_fname = base_fname.replace(template_id, pal_id)
        json_path = os.path.join(temp_dir, f"{base_fname}_retarget.json")

        if not decompile_uasset(uasset_gui_exe, uasset_path, json_path, usmap_path):
            continue

        with open(json_path, "r", encoding="utf-8") as f_json:
            content = f_json.read()

        content = content.replace(f"AS_{template_id}_", f"AS_{pal_id}_")
        content = content.replace(f"AM_{template_id}_", f"AM_{pal_id}_")

        content = content.replace(
            f"/Game/Pal/Animation/Character/{cat_sanitized}/{template_id}/",
            f"{v_new_anim_pkg}/"
        )
        content = content.replace(
            f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/",
            f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{target_anims_folder}/"
        )

        if has_anims:
            content = content.replace(
                f"/Game/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton",
                f"{v_new_skel_pkg}/SK_{pal_id}_Skeleton"
            )
            content = content.replace(f"SK_{template_id}_Skeleton", f"SK_{pal_id}_Skeleton")

        try:
            data = json.loads(content)
            if "FolderName" in data:
                data["FolderName"] = f"{v_new_anim_pkg}/{new_fname}"
            if data.get("Exports") and len(data["Exports"]) > 0:
                data["Exports"][0]["ObjectName"] = new_fname
                if base_fname.startswith("AM_") and has_anims and custom_guid:
                    data["Exports"][0]["Extras"] = encode_guid_to_extras(custom_guid)

            _collect_and_sync_namemap(data)
            with open(json_path, "w", encoding="utf-8") as f_json:
                json.dump(data, f_json, indent=2)
        except Exception:
            with open(json_path, "w", encoding="utf-8") as f_json:
                f_json.write(content)

        dest_uasset = os.path.join(cooked_anims_dir, f"{new_fname}.uasset")
        if os.path.exists(dest_uasset):
            try: os.remove(dest_uasset)
            except OSError: pass

        if compile_uasset(uasset_gui_exe, json_path, dest_uasset, usmap_path):
            log(f"  ✓ Retargeted & compiled pristine additive hit asset: {new_fname}.uasset", "success")


def patch_actor_blueprint(settings: dict, pal_id: str, template_id: str, pal_data: dict = None, log_callback=None, has_anims: bool = False, category: str = "Monster", base_pal: str = "", keep_temp: bool = False) -> bool:
    def log(msg, cat="standard"):
        if log_callback: log_callback(msg, cat)
        else: print(f"[Blueprint Patch] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui_exe = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    if not os.path.exists(uasset_gui_exe):
        log("Error: UAssetGUI.exe not found in deps/", "error")
        return False

    uproject = settings.get("uproject", "")
    project_dir = os.path.dirname(uproject) if uproject else ""
    project_name = os.path.splitext(os.path.basename(uproject))[0] if uproject else ""

    fmodel_output = settings.get("fmodel_output", "")
    if pal_data is None and fmodel_output:
        creator_json = os.path.normpath(os.path.join(fmodel_output, "Exports", "Pal", "Content", "Palbaker", "Creator", f"{pal_id}_creator.json"))
        if os.path.exists(creator_json):
            try:
                with open(creator_json, "r", encoding="utf-8") as f:
                    pal_data = json.load(f)
            except Exception: pal_data = {}
        else: pal_data = {}
    elif pal_data is None: pal_data = {}

    is_custom_pal = bool(pal_data and pal_data.get("CharacterID") == pal_id)
    is_variant = (not is_custom_pal and base_pal and base_pal.lower() != pal_id.lower())
    cat_sanitized = category.replace(" ", "_")

    cooked_base_content = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content")
    if is_variant:
        cooked_bp_dir = os.path.join(cooked_base_content, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", base_pal, pal_id)
    else:
        cooked_bp_dir = os.path.join(cooked_base_content, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", pal_id)

    if os.path.exists(cooked_bp_dir):
        shutil.rmtree(cooked_bp_dir, ignore_errors=True)
    os.makedirs(cooked_bp_dir, exist_ok=True)

    for sub in ["Character/Funnel", "Weapon"]:
        d = os.path.join(cooked_base_content, "Pal", "Blueprint", os.path.normpath(sub))
        if os.path.exists(d):
            for f in os.listdir(d):
                if pal_id.lower() in f.lower() and f.endswith((".uasset", ".uexp", ".ubulk")):
                    try: os.remove(os.path.join(d, f))
                    except OSError: pass

    temp_dir = os.path.join(repo_root, "temp_bp_extract")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # -----------------------------------------------------------------
        # STEP 1: Extract Parent Template Actor Blueprint & Variants
        # -----------------------------------------------------------------
        log(f"Extracting template blueprints and wazas for {template_id}...", "standard")
        bp_extract_patterns = [
            f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{template_id}/*",
            f"Pal/Content/Pal/Blueprint/Action/Waza/{template_id}/*"
        ]
        success, msg = extract_game_files(settings, bp_extract_patterns, temp_dir, format_type="raw")

        if not success:
            log(f"Failed to extract base blueprint: {msg}", "error")
            return False

        src_base_uasset = None
        other_variant_uassets = []
        for root, _, files in os.walk(temp_dir):
            for f in files:
                f_lower = (f or "").lower()
                if f_lower == f"bp_{template_id.lower()}.uasset":
                    src_base_uasset = os.path.join(root, f)
                elif f_lower.startswith(f"bp_{template_id.lower()}_") and f_lower.endswith(".uasset"):
                    other_variant_uassets.append(os.path.join(root, f))

        if not src_base_uasset or not os.path.exists(src_base_uasset):
            log(f"Base blueprint BP_{template_id}.uasset missing from extracted files.", "error")
            return False

        temp_base_json = os.path.join(temp_dir, f"BP_{template_id}.json")
        if not decompile_uasset(uasset_gui_exe, src_base_uasset, temp_base_json, usmap_path):
            log(f"Failed to decompile base blueprint {src_base_uasset}", "error")
            return False

        with open(temp_base_json, "r", encoding="utf-8") as f:
            base_json_data = json.load(f)

        # -----------------------------------------------------------------
        # STEP 1b: Merge WazaActionDeclarationMap from all variants (_RAID, _BOSS)
        # -----------------------------------------------------------------
        if other_variant_uassets:
            import copy

            def _is_waza_entry_populated(val_prop: dict) -> bool:
                if not val_prop or not isinstance(val_prop, dict):
                    return False
                val = val_prop.get("Value")
                if isinstance(val, dict):
                    asset_path = val.get("AssetPath")
                    if isinstance(asset_path, dict):
                        pkg = asset_path.get("PackageName", "")
                        return bool(pkg and pkg != "None" and pkg != "")
                    path_name = val.get("AssetPathName", "")
                    return bool(path_name and path_name != "None" and path_name != "")
                elif isinstance(val, str):
                    return bool(val and val != "None" and val != "")
                return False

            def _get_waza_map_from_ast(ast_data: dict) -> list | None:
                for exp in ast_data.get("Exports", []):
                    if exp.get("ObjectName") == "StaticCharacterParameterComponent":
                        for p in exp.get("Data", []):
                            if p.get("Name") == "WazaActionDeclarationMap" and isinstance(p.get("Value"), list):
                                return p["Value"]
                return None

            base_waza_map = _get_waza_map_from_ast(base_json_data)

            for var_uasset in other_variant_uassets:
                var_name = os.path.splitext(os.path.basename(var_uasset))[0]
                var_json = os.path.join(temp_dir, f"{var_name}.json")
                if decompile_uasset(uasset_gui_exe, var_uasset, var_json, usmap_path):
                    try:
                        with open(var_json, "r", encoding="utf-8") as f_var:
                            var_ast = json.load(f_var)
                        var_waza_map = _get_waza_map_from_ast(var_ast)

                        if var_waza_map and base_waza_map is not None:
                            for var_entry in var_waza_map:
                                if not isinstance(var_entry, list) or len(var_entry) < 2:
                                    continue
                                waza_key = var_entry[0].get("Value", "") if isinstance(var_entry[0], dict) else ""
                                if not waza_key:
                                    continue

                                if _is_waza_entry_populated(var_entry[1]):
                                    existing = next((
                                        e for e in base_waza_map 
                                        if isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and e[0].get("Value") == waza_key
                                    ), None)

                                    if existing:
                                        if not _is_waza_entry_populated(existing[1]):
                                            existing[1] = copy.deepcopy(var_entry[1])
                                            log(f"  [Waza Merge] Filled empty {waza_key} into base from {var_name}", "standard")
                                    else:
                                        base_waza_map.append(copy.deepcopy(var_entry))
                                        log(f"  [Waza Merge] Merged variant {waza_key} into base from {var_name}", "standard")
                    except Exception as e:
                        log(f"Warning merging wazas from {var_name}: {e}", "warning")

        base_json_str = json.dumps(base_json_data, indent=4)

        # -----------------------------------------------------------------
        # STEP 2: Extract Dynamic Dependencies (Actions, Modules, ABP, BS, AM)
        # -----------------------------------------------------------------
        action_pattern = re.compile(rf'((?:/Game|Pal/Content)/Pal/Blueprint/Action/[\w/]*/(BP_[a-zA-Z0-9_]*Action[a-zA-Z0-9_]*))', re.IGNORECASE)
        
        combined_scanned_str = base_json_str
        for var_uasset in other_variant_uassets:
            v_json = var_uasset.replace(".uasset", ".json")
            if os.path.exists(v_json):
                try:
                    with open(v_json, "r", encoding="utf-8") as f_vj:
                        combined_scanned_str += "\n" + f_vj.read()
                except Exception: pass

        discovered_actions = sorted(list(set(action_pattern.findall(combined_scanned_str))))
        
        valid_actions = []
        for p_core, a_name in discovered_actions:
            norm_core = p_core.replace("/Game/", "Pal/Content/")
            if f"/{template_id}/" in norm_core or template_id.lower() in a_name.lower():
                if (norm_core, a_name) not in valid_actions:
                    valid_actions.append((norm_core, a_name))

        waza_disk_dir = os.path.join(temp_dir, "Pal", "Content", "Pal", "Blueprint", "Action", "Waza", template_id)
        if os.path.exists(waza_disk_dir):
            for root, _, files in os.walk(waza_disk_dir):
                for f in files:
                    if f.endswith(".uasset"):
                        a_name = os.path.splitext(f)[0]
                        rel_core = os.path.relpath(os.path.join(root, a_name), temp_dir).replace("\\", "/")
                        if (rel_core, a_name) not in valid_actions:
                            valid_actions.append((rel_core, a_name))
                            log(f"  [Waza Discovery] Found physical action blueprint: {a_name}", "standard")

        discovered_blendspaces = set()
        discovered_abps = set()
        custom_anims = {}

        sidecar_candidates = [
            os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal, pal_id, f"{pal_id}_blend.json"),
            os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal, f"{pal_id}_blend.json"),
            os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, pal_id, f"{pal_id}_blend.json")
        ]
        sidecar_path = next((p for p in sidecar_candidates if os.path.exists(p)), "")

        if sidecar_path and os.path.exists(sidecar_path):
            try:
                with open(sidecar_path, "r", encoding="utf-8") as f_sc:
                    sc_data = json.load(f_sc)
                    custom_anims = sc_data.get("custom_animations", {})
                    
                    for bs_key, bs_val in custom_anims.get("blend_spaces", {}).items():
                        bs_asset = bs_val.get("asset_name")
                        if bs_asset:
                            template_bs = bs_asset.replace(pal_id, template_id)
                            discovered_blendspaces.add(template_bs)
            except Exception as e:
                log(f"Warning parsing sidecar for animation inventory: {e}", "warning")

        if has_anims:
            discovered_abps.add(f"ABP_{template_id}")
            dep_queue = [
                f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{template_id}/*",
                f"Pal/Content/Pal/Model/Character/Skeleton/{template_id}/*"
            ]
        else:
            dep_queue = []

        for path_core, a_name in valid_actions:
            dep_queue.extend([f"{path_core}.uasset", f"{path_core}.uexp", f"*{a_name}*"])

        if dep_queue:
            log(f"  Extracting animation stack & action dependencies from game paks...", "standard")
            extract_game_files(settings, dep_queue, temp_dir, format_type="raw")

        # -----------------------------------------------------------------
        # STEP 2b: Discover & Extract Unique Skill Modules from Actions
        # -----------------------------------------------------------------
        valid_modules = []
        module_queue = []

        for path_core, a_name in valid_actions:
            action_uasset = os.path.join(temp_dir, f"{path_core}.uasset")
            if os.path.exists(action_uasset):
                a_json = action_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, action_uasset, a_json, usmap_path)
                with open(a_json, "r", encoding="utf-8") as f_aj:
                    a_str = f_aj.read()
                
                module_pattern = re.compile(rf'((?:/Game|Pal/Content)/Pal/Blueprint/Action/[\w/]*/(BP_UniqueSkillModule_[a-zA-Z0-9_]+))', re.IGNORECASE)
                discovered_mods = set(module_pattern.findall(a_str))
                
                for m_path, m_name in discovered_mods:
                    norm_m_path = m_path.replace("/Game/", "Pal/Content/")
                    if f"/{template_id}/" in norm_m_path or template_id in m_name:
                        if (norm_m_path, m_name) not in valid_modules:
                            valid_modules.append((norm_m_path, m_name))
                            module_queue.extend([f"{norm_m_path}.uasset", f"{norm_m_path}.uexp"])

        if module_queue:
            log(f"  Extracting {len(valid_modules)} embedded Unique Skill Modules...", "standard")
            extract_game_files(settings, module_queue, temp_dir, format_type="raw")

        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith(".uasset"):
                    base_f = os.path.splitext(f)[0]
                    if base_f.startswith(f"ABP_{template_id}"):
                        discovered_abps.add(base_f)
                    elif base_f.startswith("BS_"):
                        discovered_blendspaces.add(base_f)

        discovered_blendspaces = sorted(list(discovered_blendspaces))
        discovered_abps = sorted(list(discovered_abps))

        # -----------------------------------------------------------------
        # STEP 3: Retarget Package Paths & Global References
        # -----------------------------------------------------------------
        vanilla_guid = "BF21DEE0-4BCF0A09-60C97DA1-367595A0"
        custom_guid = "F3642458-43D36EB4-2B398F89-8DDC8313"

        target_bp_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
        target_skel_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
        target_anims_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id
        target_mesh_folder = f"{base_pal}/{pal_id}" if is_variant else pal_id

        if has_anims:
            v_skel = None
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if f.lower() == f"sk_{template_id.lower()}_skeleton.uasset":
                        v_skel = os.path.join(root, f)
                        break
                if v_skel: break
            if v_skel:
                sk_json = os.path.join(temp_dir, "vanilla_skel.json")
                decompile_uasset(uasset_gui_exe, v_skel, sk_json, usmap_path)
                vanilla_guid = find_skeleton_guid_in_json(sk_json) or vanilla_guid

            custom_skel_candidates = [
                os.path.normpath(os.path.join(project_dir, "Content", "Pal", "Model", "Character", "Skeleton", target_skel_folder, f"SK_{pal_id}_Skeleton.uasset")),
                os.path.normpath(os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Model", "Character", "Skeleton", target_skel_folder, f"SK_{pal_id}_Skeleton.uasset")),
                os.path.normpath(os.path.join(project_dir, "Content", "Pal", "Model", "Character", "Skeleton", base_pal, f"SK_{pal_id}_Skeleton.uasset")),
                os.path.normpath(os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Model", "Character", "Skeleton", base_pal, f"SK_{pal_id}_Skeleton.uasset"))
            ]
            
            c_skel = next((p for p in custom_skel_candidates if os.path.exists(p)), None)
            if c_skel:
                c_skel_json = os.path.join(temp_dir, "custom_skel.json")
                if decompile_uasset(uasset_gui_exe, c_skel, c_skel_json, usmap_path):
                    found_guid = find_skeleton_guid_in_json(c_skel_json)
                    if found_guid:
                        custom_guid = found_guid
                        log(f"  [Skeleton Sync] Extracted custom skeleton GUID: {custom_guid}", "standard")
                    try: os.remove(c_skel_json)
                    except OSError: pass
            else:
                log(f"  [Skeleton Sync Warning] Custom skeleton not found on disk. Falling back to default GUID.", "warning")

        cooked_anims_dir = os.path.normpath(os.path.join(cooked_base_content, "Pal", "Animation", "Character", cat_sanitized, pal_id))
        if is_variant:
            cooked_anims_dir = os.path.normpath(os.path.join(cooked_base_content, "Pal", "Animation", "Character", cat_sanitized, base_pal, pal_id))
        os.makedirs(cooked_anims_dir, exist_ok=True)

        def global_patch(content: str) -> str:
            content = content.replace(
                f"/Model/Character/{cat_sanitized}/{template_id}",
                f"/Model/Character/{cat_sanitized}/{target_mesh_folder}"
            )
            content = content.replace(f"SK_{template_id}", f"SK_{pal_id}")
            content = content.replace(f"PA_{template_id}", f"PA_{pal_id}")
            
            content = content.replace(f"/PalActorBP/{template_id}/BP_{template_id}", f"/PalActorBP/{target_bp_folder}/BP_{pal_id}")
            content = content.replace(f"ExecuteUbergraph_BP_{template_id}", f"ExecuteUbergraph_BP_{pal_id}")
            content = content.replace(f"BndEvt__BP_{template_id}_", f"BndEvt__BP_{pal_id}_")
            content = re.sub(rf"Default__BP_{template_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_C", content)
            content = re.sub(rf"Default__BP_{template_id}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}", content)
            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}_C(?![A-Za-z0-9_])", f"BP_{pal_id}_C", content)
            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}(?![A-Za-z0-9_])", f"BP_{pal_id}", content)

            for path_core, a_name in valid_actions + valid_modules:
                new_path_core = path_core.replace(template_id, pal_id)
                new_name = a_name.replace(template_id, pal_id)

                game_path_core = path_core.replace("Pal/Content/", "/Game/")
                game_new_path_core = new_path_core.replace("Pal/Content/", "/Game/")

                content = content.replace(f"{game_path_core}.{a_name}_C", f"{game_new_path_core}.{new_name}_C")
                content = content.replace(f"{game_path_core}", f"{game_new_path_core}")
                content = content.replace(path_core, new_path_core)
                
                content = content.replace(f"/{a_name}.{a_name}_C", f"/{new_name}.{new_name}_C")
                content = content.replace(f"/{a_name}", f"/{new_name}")

                content = content.replace(f"Default__{a_name}_C", f"Default__{new_name}_C")
                content = content.replace(f"Default__{a_name}", f"Default__{new_name}")
                content = content.replace(f"{a_name}_C", f"{new_name}_C")
                content = content.replace(f"ExecuteUbergraph_{a_name}", f"ExecuteUbergraph_{new_name}")
                content = re.sub(rf"(?<![A-Za-z0-9_]){a_name}(?![A-Za-z0-9_])", new_name, content)

            if has_anims:
                content = content.replace(vanilla_guid, custom_guid)

                content = content.replace(f"/Model/Character/Skeleton/{template_id}/", f"/Model/Character/Skeleton/{target_skel_folder}/")
                content = content.replace(f"SK_{template_id}_Skeleton", f"SK_{pal_id}_Skeleton")
                content = content.replace(f"Animation/Character/{cat_sanitized}/{template_id}", f"Animation/Character/{cat_sanitized}/{target_anims_folder}")

                content = content.replace(f"AS_{template_id}_", f"AS_{pal_id}_")
                content = content.replace(f"AM_{template_id}_", f"AM_{pal_id}_")

                for abp in discovered_abps:
                    new_abp = abp.replace(template_id, pal_id)
                    content = content.replace(f"/PalActorBP/{template_id}/{abp}", f"/PalActorBP/{target_bp_folder}/{new_abp}")
                    content = content.replace(f"{abp}_C", f"{new_abp}_C")
                    content = content.replace(abp, new_abp)

                for bs in discovered_blendspaces:
                    new_bs = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{template_id}", rf"\1_{pal_id}", bs)
                    content = content.replace(f"/PalActorBP/{template_id}/{bs}", f"/PalActorBP/{target_bp_folder}/{new_bs}")
                    content = content.replace(bs, new_bs)

            return content


        # -----------------------------------------------------------------
        # STEP 4: Synthesize ALL AnimMontages (AM_) from Sidecar 100%
        # -----------------------------------------------------------------
        if has_anims:
            for anim_key, anim_meta in custom_anims.get("anims", {}).items():
                if not isinstance(anim_meta, dict): continue
                if anim_meta.get("_is_cloned"): continue # SKIP! Already cloned in Step 2.
                
                m_asset = anim_meta.get("montage_asset")
                if not m_asset: continue
                
                if not anim_meta.get("in_nla") and not anim_meta.get("is_modified"):
                    continue
                
                t_name = anim_meta.get("nla_track_name") or extract_track_name(m_asset)
                s_asset = anim_meta.get("sequence_asset") or f"AS_{pal_id}_{t_name}"
                
                notifies = anim_meta.get("montage_notifies") or anim_meta.get("notifies") or []
                duration = float(anim_meta.get("duration", 0.0))
                if duration <= 0.0:
                    max_time = max([float(n.get("Time", 0.0)) + float(n.get("Duration", 0.0)) for n in notifies], default=1.5)
                    duration = max(2.0, max_time + 0.5)
                    
                _synthesize_montage_from_seed(
                    repo_root=repo_root,
                    pal_id=pal_id,
                    montage_name=m_asset,
                    sequence_name=s_asset,
                    track_name=t_name,
                    duration=duration,
                    skeleton_guid=custom_guid if has_anims else vanilla_guid,
                    notifies=notifies,
                    cat_sanitized=cat_sanitized,
                    target_anims_folder=target_anims_folder,
                    cooked_anims_dir=cooked_anims_dir,
                    temp_dir=temp_dir,
                    uasset_gui_exe=uasset_gui_exe,
                    usmap_path=usmap_path,
                    log=log
                )

        # -----------------------------------------------------------------
        # STEP 4.5: Retarget & Compile Action Blueprints & Modules
        # -----------------------------------------------------------------
        for path_core, a_name in valid_actions + valid_modules:
            action_uasset = os.path.normpath(os.path.join(temp_dir, f"{path_core}.uasset"))
            if not os.path.exists(action_uasset):
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        if f.lower() == f"{a_name.lower()}.uasset":
                            action_uasset = os.path.join(root, f)
                            break
                    if action_uasset and os.path.exists(action_uasset):
                        break

            if action_uasset and os.path.exists(action_uasset):
                a_json = action_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, action_uasset, a_json, usmap_path)
                with open(a_json, "r", encoding="utf-8") as f_aj:
                    a_str = global_patch(f_aj.read())

                new_path_core = path_core.replace(template_id, pal_id)
                new_name = a_name.replace(template_id, pal_id)
                
                try:
                    a_data = json.loads(a_str)
                    if "FolderName" in a_data:
                        a_data["FolderName"] = new_path_core.replace("Pal/Content/", "/Game/")
                    _collect_and_sync_namemap(a_data)
                    with open(a_json, "w", encoding="utf-8") as f_aj:
                        json.dump(a_data, f_aj, indent=4)
                except Exception:
                    with open(a_json, "w", encoding="utf-8") as f_aj:
                        f_aj.write(a_str)

                stripped_new_core = new_path_core.replace("Pal/Content/", "")
                action_dest_dir = os.path.join(cooked_base_content, os.path.dirname(stripped_new_core))
                os.makedirs(action_dest_dir, exist_ok=True)
                
                dest_action_uasset = os.path.join(action_dest_dir, f"{new_name}.uasset")
                compile_ok = compile_uasset(uasset_gui_exe, a_json, dest_action_uasset, usmap_path)
                if compile_ok and os.path.exists(dest_action_uasset):
                    log(f"  ✓ Retargeted blueprint logic: {new_name}", "success")
                else:
                    log(f"  ❌ Failed to compile action blueprint: {new_name}", "error")

        # -----------------------------------------------------------------
        # STEP 4b: Retarget & Compile AnimBlueprints (ABP_)
        # -----------------------------------------------------------------
        for abp in discovered_abps:
            abp_uasset = None
            for root, _, files in os.walk(temp_dir):
                if f"{abp}.uasset" in files:
                    abp_uasset = os.path.join(root, f"{abp}.uasset")
                    break

            if abp_uasset and os.path.exists(abp_uasset):
                abp_json = abp_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, abp_uasset, abp_json, usmap_path)
                with open(abp_json, "r", encoding="utf-8") as f:
                    abp_str = global_patch(f.read())
                new_abp_name = abp.replace(template_id, pal_id)
                
                try:
                    abp_data = json.loads(abp_str)
                    if "FolderName" in abp_data:
                        abp_data["FolderName"] = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{target_bp_folder}/{new_abp_name}"
                    _collect_and_sync_namemap(abp_data)
                    with open(abp_json, "w", encoding="utf-8") as f:
                        json.dump(abp_data, f, indent=4)
                except Exception:
                    with open(abp_json, "w", encoding="utf-8") as f:
                        f.write(abp_str)
                dest_abp_uasset = os.path.join(cooked_bp_dir, f"{new_abp_name}.uasset")
                compile_uasset(uasset_gui_exe, abp_json, dest_abp_uasset, usmap_path)
                log(f"  ✓ Compiled AnimBlueprint: {new_abp_name}.uasset")

        # -----------------------------------------------------------------
        # STEP 4c: Retarget & Compile Locomotion BlendSpaces (BS_)
        # -----------------------------------------------------------------
        for bs in discovered_blendspaces:
            bs_uasset = None
            for root, _, files in os.walk(temp_dir):
                if f"{bs}.uasset" in files:
                    bs_uasset = os.path.join(root, f"{bs}.uasset")
                    break

            if bs_uasset and os.path.exists(bs_uasset):
                bs_json = bs_uasset.replace(".uasset", ".json")
                decompile_uasset(uasset_gui_exe, bs_uasset, bs_json, usmap_path)
                with open(bs_json, "r", encoding="utf-8") as f:
                    bs_str = global_patch(f.read())
                new_bs_name = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{template_id}", rf"\1_{pal_id}", bs)
                
                try:
                    bs_data = json.loads(bs_str)
                    if "FolderName" in bs_data:
                        bs_data["FolderName"] = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{target_bp_folder}/{new_bs_name}"
                    
                    if custom_guid:
                        bs_exports = bs_data.get("Exports", []) if isinstance(bs_data, dict) else bs_data
                        for exp in bs_exports:
                            if isinstance(exp, dict) and "SkeletonGuid" in exp:
                                exp["SkeletonGuid"] = custom_guid

                    _collect_and_sync_namemap(bs_data)
                    with open(bs_json, "w", encoding="utf-8") as f:
                        json.dump(bs_data, f, indent=4)
                except Exception:
                    with open(bs_json, "w", encoding="utf-8") as f:
                        f.write(bs_str)
                dest_bs_uasset = os.path.join(cooked_bp_dir, f"{new_bs_name}.uasset")
                compile_uasset(uasset_gui_exe, bs_json, dest_bs_uasset, usmap_path)
                log(f"  ✓ Compiled BlendSpace: {new_bs_name}.uasset")

        # -----------------------------------------------------------------
        # STEP 4e: Retarget Pristine Additive Hit Reaction Animations
        # -----------------------------------------------------------------
        _retarget_additive_hit_animations(
            settings=settings,
            template_id=template_id,
            pal_id=pal_id,
            category=category,
            base_pal=base_pal,
            is_variant=is_variant,
            custom_guid=custom_guid,
            has_anims=has_anims,
            temp_dir=temp_dir,
            cooked_anims_dir=cooked_anims_dir,
            uasset_gui_exe=uasset_gui_exe,
            usmap_path=usmap_path,
            log=log
        )

        # -----------------------------------------------------------------
        # STEP 5: Ingest Features into Host Actor Blueprint via AST Manager
        # -----------------------------------------------------------------
        base_json_str = global_patch(base_json_str)
        base_json_data = json.loads(base_json_str)

        
        # Ensure JumpStart and Ragdoll overrides are stripped out so unique GroundPunch attacks aren't interrupted mid-air
        for exp in base_json_data.get("Exports", []):
            if exp.get("ObjectName") == "StaticCharacterParameterComponent":
                for p in exp.get("Data", []):
                    if p.get("Name") == "GeneralMontageMap":
                        keys_to_remove = p.setdefault("KeysToRemove", [])
                        for jump_key in ["EPalGeneralMontageType::JumpStart", "EPalGeneralMontageType::Ragdoll"]:
                            exists = any(isinstance(k, dict) and k.get("Value") == jump_key for k in keys_to_remove)
                            if not exists:
                                keys_to_remove.append({
                                    "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                                    "EnumType": None,
                                    "InnerType": None,
                                    "Name": "GeneralMontageMap",
                                    "ArrayIndex": 0,
                                    "PropertyGuid": None,
                                    "IsZero": False,
                                    "PropertyTagFlags": "None",
                                    "PropertyTypeName": None,
                                    "PropertyTagExtensions": "NoExtension",
                                    "Value": jump_key
                                })
                        break

        if "spine_03" not in base_json_str and "spine_02" in base_json_str:
            base_json_str = base_json_str.replace('"spine_03"', '"spine_02"')

        base_json_str = base_json_str.replace('"weapon_r"', '"head"')

        for exp in base_json_data.get("Exports", []):
            if exp.get("ObjectName") == "CharacterMesh0":
                props = exp.get("Data", [])
                clean_props = []
                for p in props:
                    if p.get("Name") == "OverrideMaterials":
                        mat_vals = p.get("Value", [])
                        if any(isinstance(v, dict) and v.get("Value", 0) != 0 for v in mat_vals):
                            clean_props.append(p)
                    else:
                        clean_props.append(p)
                exp["Data"] = clean_props

        if base_json_data:
            if is_custom_pal:
                features = pal_data.get("Features", {})
                custom_features_enabled = bool(features.get("CustomFeaturesEnabled", False))

                if not custom_features_enabled:
                    log("  [Blueprint] Custom features switch is OFF: Preserving template's original components (applying vital renames only).", "standard")
                else:
                    log("  [Blueprint] Custom features switch is ON: Injecting customized feature components...", "standard")
                    mgr = BlueprintFeatureManager(base_json_data)

                    riding = features.get("Riding", {})
                    coop_weapon = features.get("CoopWeapon", {})
                    funnel = features.get("Funnel", {})

                    is_riding_active = bool(riding.get("Enabled", False))
                    is_weapon_active = bool(coop_weapon.get("Enabled", False))
                    is_funnel_active = bool(funnel.get("Enabled", False))

                    if is_riding_active:
                        is_weapon_active = False

                    # 5a. Mounts & Riding
                    if is_riding_active:
                        mgr.add_saddle(
                            marker_type=riding.get("MarkerType", "Saddle"),
                            ride_position_type=riding.get("RidePosition", "HorseRide"),
                            attach_socket=riding.get("AttachSocket", "pelvis"),
                            relative_rotation=riding.get("RelativeRotation", {"Pitch": 90.0, "Yaw": 0.0, "Roll": 0.0}),
                            relative_location=riding.get("RelativeLocation", {"X": 0.0, "Y": 0.0, "Z": 40.0}),
                            with_speed_collision=riding.get("WithSpeedCollision", False)
                        )
                        if riding.get("WithMountedShooter"):
                            mgr.add_mounted_shooter()

                        comp = mgr.find_static_char_param_export()
                        if comp and isinstance(comp.get("Data"), list):
                            bs_map = next((p for p in comp["Data"] if isinstance(p, dict) and p.get("Name") == "GeneralBlendSpaceMap"), None)
                            if bs_map and isinstance(bs_map.get("Value"), list):
                                gen_move_entry = next(
                                    (e for e in bs_map["Value"] if isinstance(e, list) and len(e) >= 2 and isinstance(e[0], dict) and "GeneralMove" in str(e[0].get("Value", ""))),
                                    None
                                )
                                if gen_move_entry and isinstance(gen_move_entry[1], dict):
                                    bs_map["Value"] = [
                                        e for e in bs_map["Value"]
                                        if not (isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and "RidingMove" in str(e[0].get("Value", "")))
                                    ]
                                    bs_map["Value"].append([
                                        {
                                            "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                                            "EnumType": None,
                                            "InnerType": None,
                                            "Name": "GeneralBlendSpaceMap",
                                            "ArrayIndex": 0,
                                            "PropertyGuid": None,
                                            "IsZero": False,
                                            "PropertyTagFlags": "None",
                                            "PropertyTypeName": None,
                                            "PropertyTagExtensions": "NoExtension",
                                            "Value": "EPalGeneralBlendSpaceType::RidingMove"
                                        },
                                        {
                                            "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                                            "Name": "GeneralBlendSpaceMap",
                                            "ArrayIndex": 0,
                                            "PropertyGuid": None,
                                            "IsZero": False,
                                            "PropertyTagFlags": "None",
                                            "PropertyTypeName": None,
                                            "PropertyTagExtensions": "NoExtension",
                                            "Value": gen_move_entry[1].get("Value")
                                        }
                                    ])
                    else:
                        mgr.remove_saddle()

                    # 5b. Flight
                    flight = features.get("Flight", {})
                    if flight.get("Enabled"):
                        mgr.add_fly_height_controller()
                    else:
                        mgr.remove_fly_height_controller()

                    # 5c. Defensive Shield
                    shield = features.get("Shield", {})
                    if shield.get("Enabled"):
                        mgr.add_shield(
                            radius=shield.get("Radius", 90.0),
                            attach_socket=shield.get("AttachSocket", "lowerarm_l"),
                            relative_location=shield.get("RelativeLocation")
                        )
                    else:
                        mgr.remove_component("Shield")
                        mgr.remove_component("BP_CoopParam_Sheild")

                    # 5d. Utility Actions
                    utility = features.get("CoopUtility", {})
                    if utility.get("SkillType") and utility.get("SkillType") != "None":
                        mgr.set_coop_utility(utility["SkillType"])

                    # 5e. Combat Evasion
                    evasion = features.get("CombatEvasion", {})
                    if evasion.get("SideMoveStyle") and evasion.get("SideMoveStyle") != "None":
                        mgr.set_evasion_style(evasion["SideMoveStyle"])
                    if evasion.get("LeaveStyle") and evasion.get("LeaveStyle") != "None":
                        mgr.set_evasion_style(evasion["LeaveStyle"])

                    # 5f. Night Point Light
                    light = features.get("TimerPointLight", {})
                    if light.get("Enabled"):
                        mgr.add_timer_point_light()

                    # 5g. Permanent VFX Particles
                    vfx_list = features.get("VFX", [])
                    for vfx in vfx_list:
                        mgr.add_niagara_particle(
                            var_name=vfx.get("VarName", f"VFX_{vfx.get('AttachSocket')}"),
                            system_package=vfx.get("SystemPackage", "/Game/Pal/Effect/Common/Cooking/NS_CookingFlame"),
                            system_name=vfx.get("SystemName", "NS_CookingFlame"),
                            attach_socket=vfx.get("AttachSocket", "root")
                        )

                    # 5h. Locomotion Leaning Calibration
                    leaning = features.get("LocomotionLeaning", {})
                    for mode, cfg in leaning.items():
                        mgr.set_locomotion_leaning(
                            mode=mode,
                            pitch_intensity=cfg.get("PitchIntensity", 0.0),
                            roll_intensity=cfg.get("RollIntensity", 0.0)
                        )

                    # 5i. Co-op Partner Weapon Synthesis
                    if is_weapon_active:
                        mode = coop_weapon.get("Mode", "Flamethrower")
                        wp_name = f"BP_{pal_id}_{mode}" if mode != "ThrowBomb" else f"BP_{pal_id}_ThrowElecBomb"
                        if mode == "Katana": wp_name = f"BP_{pal_id}_Katana"
                        if mode == "Launcher": wp_name = f"BP_{pal_id}_Launcher"

                        wp_pkg = f"/Game/Pal/Blueprint/Weapon/{wp_name}"
                        wp_cls = f"{wp_name}_C"

                        mgr.add_coop_weapon(
                            mode=mode,
                            weapon_class_package=wp_pkg,
                            weapon_class_name=wp_cls,
                            attach_socket=coop_weapon.get("AttachSocket", "Socket_Weapon_R"),
                            skill_magnification=coop_weapon.get("SkillMagnification"),
                            aim_blur_angles=coop_weapon.get("AimBlurAngles")
                        )
                        
                        from utils.blueprint_patcher.clone_weapons import clone_partner_weapons
                        clone_partner_weapons({}, "", template_id, pal_id, settings, temp_dir, cooked_base_content, uasset_gui_exe, flags, log, pal_data=pal_data, usmap_path=usmap_path, has_anims=has_anims)
                    else:
                        mgr.remove_component("BP_CoopParam_Weapon")
                        mgr.remove_component("BP_CoopParam_AssaultRifleMode")
                        mgr.remove_component("BP_CoopParam_ShotgunMode")
                        mgr.remove_component("BP_CoopParam_OnHeadShot")

                        for exp in base_json_data.get("Exports", []):
                            if "ComponentDelegateBinding" in str(exp.get("ObjectName", "")):
                                exp["Data"] = []

                    # 5j. Satellite Minion Funnel Synthesis
                    if is_funnel_active:
                        funnel_preset = funnel.get("Preset", "DreamDemon")
                        custom_waza = funnel.get("CustomWazaID", pal_data.get("FunnelWazaID", "EPalWazaID::Funnel_DreamDemon"))
                        custom_satellite_path = f"/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_{pal_id}.BP_FunnelCharacter_{pal_id}_C"

                        mgr.set_partner_funnel(
                            preset_name=funnel_preset,
                            custom_waza_id=custom_waza,
                            custom_character_class=custom_satellite_path
                        )

                        log(f"  [Action: Funnel] Synthesizing standalone Funnel Character BP_FunnelCharacter_{pal_id}...", "standard")
                        funnel_base = "RaijinDaughter" if ("RaijinDaughter" in custom_waza or funnel_preset == "Dazzi") else ("FlowerRabbit" if funnel_preset == "Flopie" else "DreamDemon")
                        source_funnel_name = f"BP_FunnelCharacter_{funnel_base}"

                        seed_funnel_rel = f"Pal/Content/Pal/Blueprint/Character/Funnel/{source_funnel_name}.uasset"
                        extract_game_files(settings, [seed_funnel_rel, seed_funnel_rel.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
                        seed_fn_uasset = os.path.join(temp_dir, seed_funnel_rel)
                        seed_fn_json = os.path.join(temp_dir, f"{source_funnel_name}.json")

                        funnel_cooked_dir = os.path.join(cooked_base_content, "Pal", "Blueprint", "Character", "Funnel")
                        os.makedirs(funnel_cooked_dir, exist_ok=True)

                        if decompile_uasset(uasset_gui_exe, seed_fn_uasset, seed_fn_json, usmap_path):
                            with open(seed_fn_json, "r", encoding="utf-8") as f_sfn:
                                seed_fn_data = json.load(f_sfn)

                            funnel_ast = synthesize_funnel_character_ast(
                                seed_funnel_data=seed_fn_data,
                                target_pal_id=pal_id,
                                template_pal_id=template_id,
                                targeting_action=funnel.get("TargetingAction", "ShadowBall")
                            )

                            out_fn_json = os.path.join(temp_dir, f"BP_FunnelCharacter_{pal_id}.json")
                            with open(out_fn_json, "w", encoding="utf-8") as f_out_fn:
                                json.dump(funnel_ast, f_out_fn, indent=2)

                            dest_fn_uasset = os.path.join(funnel_cooked_dir, f"BP_FunnelCharacter_{pal_id}.uasset")
                            compile_uasset(uasset_gui_exe, out_fn_json, dest_fn_uasset, usmap_path)
                            log(f"  ✓ Compiled standalone funnel blueprint: {dest_fn_uasset}", "success")

                        source_boss_name = f"{source_funnel_name}_BOSS2"
                        seed_boss_rel = f"Pal/Content/Pal/Blueprint/Character/Funnel/{source_boss_name}.uasset"
                        extract_game_files(settings, [seed_boss_rel, seed_boss_rel.replace('.uasset', '.uexp')], temp_dir, format_type="raw")
                        seed_boss_uasset = os.path.join(temp_dir, seed_boss_rel)
                        seed_boss_json = os.path.join(temp_dir, f"{source_boss_name}.json")

                        if decompile_uasset(uasset_gui_exe, seed_boss_uasset, seed_boss_json, usmap_path):
                            with open(seed_boss_json, "r", encoding="utf-8") as f_sb:
                                boss_str = f_sb.read()

                            boss_str = boss_str.replace(source_boss_name, f"BP_FunnelCharacter_{pal_id}_BOSS")
                            boss_str = boss_str.replace(source_funnel_name, f"BP_FunnelCharacter_{pal_id}")
                            boss_str = boss_str.replace(f"SK_{funnel_base}", f"SK_{pal_id}")

                            boss_ast = json.loads(boss_str)
                            _collect_and_sync_namemap(boss_ast)

                            out_boss_json = os.path.join(temp_dir, f"BP_FunnelCharacter_{pal_id}_BOSS.json")
                            with open(out_boss_json, "w", encoding="utf-8") as f_out_boss:
                                json.dump(boss_ast, f_out_boss, indent=2)

                            dest_boss_uasset = os.path.join(funnel_cooked_dir, f"BP_FunnelCharacter_{pal_id}_BOSS.uasset")
                            compile_uasset(uasset_gui_exe, out_boss_json, dest_boss_uasset, usmap_path)
                            log(f"  ✓ Compiled standalone funnel boss blueprint: {dest_boss_uasset}", "success")
                    else:
                        mgr.clear_partner_funnel()

                    has_coop = (
                        is_riding_active or
                        is_weapon_active or
                        is_funnel_active or
                        (utility.get("SkillType") and utility.get("SkillType") != "None")
                    )
                    if not has_coop:
                        mgr.remove_ai_action("EPalAIActionType::Cooperation")
                    elif is_riding_active:
                        mgr.set_ai_action("EPalAIActionType::Cooperation", "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionRideCall.BP_AIActionRideCall_C")

            # -----------------------------------------------------------------
            # STEP 5b: Process Assigned Unique Wazas & Inject into WazaActionDeclarationMap
            # -----------------------------------------------------------------
            waza_ok = _process_unique_waza_actions(
                settings=settings,
                pal_id=pal_id,
                template_id=template_id,
                pal_data=pal_data,
                custom_anims=custom_anims,
                has_anims=has_anims,
                category=category,
                base_pal=base_pal,
                is_variant=is_variant,
                temp_dir=temp_dir,
                cooked_base_content=cooked_base_content,
                cooked_anims_dir=cooked_anims_dir,
                uasset_gui_exe=uasset_gui_exe,
                usmap_path=usmap_path,
                custom_guid=custom_guid,
                vanilla_guid=vanilla_guid,
                base_json_data=base_json_data,
                log=log
            )
            if not waza_ok:
                return False

            skel_mesh_idx = None
            anim_class_idx = None
            
            for i, imp in enumerate(base_json_data.get("Imports", [])):
                if not isinstance(imp, dict):
                    continue
                obj_name = str(imp.get("ObjectName") or "")
                cls_name = str(imp.get("ClassName") or "")
                if cls_name == "SkeletalMesh" and pal_id.lower() in obj_name.lower():
                    skel_mesh_idx = -(i + 1)
                elif cls_name == "AnimBlueprintGeneratedClass" and obj_name.endswith("_C") and pal_id.lower() in obj_name.lower():
                    anim_class_idx = -(i + 1)

            for exp in base_json_data.get("Exports", []):
                if exp.get("ObjectName") == "CharacterMesh0":
                    for p in exp.get("Data", []):
                        p_name = p.get("Name")
                        if p_name in ["SkeletalMesh", "SkinnedAsset"] and skel_mesh_idx:
                            p["Value"] = skel_mesh_idx
                        elif p_name == "AnimClass" and anim_class_idx:
                            p["Value"] = anim_class_idx

        
        # -----------------------------------------------------------------
        # STEP 6: Compile Host Actor Blueprint
        # -----------------------------------------------------------------
        if "FolderName" in base_json_data:
            base_json_data["FolderName"] = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{target_bp_folder}/BP_{pal_id}"
            
        _collect_and_sync_namemap(base_json_data)
        out_host_json = os.path.join(temp_dir, f"BP_{pal_id}.json")
        with open(out_host_json, "w", encoding="utf-8") as f:
            json.dump(base_json_data, f, indent=4)

        dest_base_uasset = os.path.join(cooked_bp_dir, f"BP_{pal_id}.uasset")
        if os.path.exists(dest_base_uasset):
            try:
                os.remove(dest_base_uasset)
            except OSError:
                pass

        compile_ok = compile_uasset(uasset_gui_exe, out_host_json, dest_base_uasset, usmap_path)
        if not compile_ok or not os.path.exists(dest_base_uasset):
            log(f"  ❌ Failed to compile Actor Blueprint: BP_{pal_id}.uasset", "error")
            return False
        log(f"  ✓ Compiled Actor Blueprint: BP_{pal_id}.uasset", "success")

        # -----------------------------------------------------------------
        # STEP 7: Build Variants (Boss & Predator)
        # -----------------------------------------------------------------
        base_json_str = json.dumps(base_json_data, indent=4)
        boss_scale = float(pal_data.get("BossScale", 1.4))
        generate_boss = pal_data.get("GenerateBoss", True) is not False
        generate_predator = bool(pal_data.get("GeneratePredator", False))

        if generate_boss:
            build_boss_variant(base_json_str, template_id, pal_id, boss_scale, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, usmap_path=usmap_path)
        if generate_predator:
            build_predator_variant(template_id, pal_id, generate_boss, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, usmap_path=usmap_path)
            
        build_raid_variant(template_id, pal_id, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, usmap_path=usmap_path)

        if not (keep_temp or "--keep-temp" in sys.argv):
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            log(f"  [Debug] Retaining temporary JSON and AST files at: {temp_dir}", "standard")
        return True

    except Exception as e:
        log(f"Fatal error during blueprint synthesis: {e}", "error")
        if not (keep_temp or "--keep-temp" in sys.argv):
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            log(f"  [Debug] Retaining temporary JSON and AST files after failure at: {temp_dir}", "standard")
        return False