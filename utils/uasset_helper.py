# utils/uasset_helper.py
import os
import sys
import json
import re
import struct
import base64
import copy
import subprocess

# =============================================================================
# 1. UASSETGUI CLI ENGINE WRAPPERS
# =============================================================================

def decompile_uasset(uasset_gui_exe: str, uasset_path: str, json_path: str, usmap_path: str = None) -> bool:
    if not uasset_gui_exe or not os.path.exists(uasset_gui_exe) or not uasset_path or not os.path.exists(uasset_path):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
    cmd = [uasset_gui_exe, "tojson", uasset_path, json_path, "VER_UE5_1"]
    if usmap_path and os.path.exists(usmap_path):
        cmd.append(usmap_path)
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
        return res.returncode == 0 and os.path.exists(json_path) and os.path.getsize(json_path) > 0
    except Exception:
        return False

def compile_uasset(uasset_gui_exe: str, json_path: str, uasset_path: str, usmap_path: str = None) -> bool:
    if not uasset_gui_exe or not os.path.exists(uasset_gui_exe) or not json_path or not os.path.exists(json_path):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(uasset_path)), exist_ok=True)
    cmd = [uasset_gui_exe, "fromjson", json_path, uasset_path]
    if usmap_path and os.path.exists(usmap_path):
        cmd.append(usmap_path)
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
        return res.returncode == 0 and os.path.exists(uasset_path) and os.path.getsize(uasset_path) > 0
    except Exception:
        return False

def sync_namemap(data: dict) -> None:
    if not isinstance(data, dict):
        return
    name_map = data.setdefault("NameMap", [])
    existing = set(name_map)

    def add_name(n):
        if isinstance(n, str) and n and n not in existing:
            if not n.startswith("{") and not n.startswith("[") and len(n) < 512:
                name_map.append(n)
                existing.add(n)

    standard_types = [
        "None", "ObjectProperty", "StructProperty", "FloatProperty", "IntProperty",
        "BoolProperty", "ByteProperty", "EnumProperty", "NameProperty", "ArrayProperty",
        "DoubleProperty", "Int8Property", "Int16Property", "Int64Property", "UInt16Property",
        "UInt32Property", "UInt64Property", "StrProperty", "TextProperty", "SoftObjectProperty",
        "DelegateProperty", "MulticastDelegateProperty", "MulticastInlineDelegateProperty",
        "MapProperty", "SetProperty"
    ]
    for st in standard_types:
        add_name(st)

    def collect(node):
        if isinstance(node, dict):
            t = node.get("$type", "")
            if "PropertyData" in t:
                match = re.search(r'([A-Za-z0-9_]+)PropertyData', t)
                if match:
                    add_name(f"{match.group(1)}Property")

            for k, v in node.items():
                if k in ("Name", "ObjectName", "ClassName", "ClassPackage", "PackageName",
                         "StructType", "EnumType", "InnerType", "PropertyTypeName", "EnumValue",
                         "NotifyName", "SocketName", "attachBoneName"):
                    add_name(v)
                elif k == "Value" and isinstance(v, str):
                    add_name(v)
                collect(v)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(data.get("Imports", []))
    collect(data.get("Exports", []))

    if "Generations" in data and isinstance(data["Generations"], list) and len(data["Generations"]) > 0:
        data["Generations"][0]["NameCount"] = len(name_map)
        data["Generations"][0]["ExportCount"] = len(data.get("Exports", []))

# =============================================================================
# 2. SKELETON GUID SERIALIZATION (BASE64)
# =============================================================================

def encode_guid_to_extras(guid_str: str) -> str:
    clean = re.sub(r'[^0-9A-Fa-f]', '', guid_str or "")
    if len(clean) != 32:
        return ""
    raw_bytes = struct.pack(
        '<IIII',
        int(clean[0:8], 16),
        int(clean[8:16], 16),
        int(clean[16:24], 16),
        int(clean[24:32], 16)
    )
    return base64.b64encode(raw_bytes).decode('ascii')

def decode_extras_to_guid(extras) -> str:
    if not extras:
        return ""
    if isinstance(extras, str):
        clean = extras.strip().upper()
        if re.match(r'^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$', clean):
            return clean
        try:
            raw_bytes = base64.b64decode(extras)
            if len(raw_bytes) == 16:
                a, b, c, d = struct.unpack('<IIII', raw_bytes)
                h = f"{a:08X}{b:08X}{c:08X}{d:08X}"
                return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
        except Exception:
            pass
        h = re.sub(r'[^0-9A-Fa-f]', '', clean)
        if len(h) == 32:
            return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
        return clean
    elif isinstance(extras, (list, bytes, bytearray)):
        raw_bytes = bytes(extras)
        if len(raw_bytes) == 16:
            a, b, c, d = struct.unpack('<IIII', raw_bytes)
            h = f"{a:08X}{b:08X}{c:08X}{d:08X}"
            return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    return ""

def extract_notifies_from_ast(ast: dict) -> list[dict]:
    notifies_list = []
    if not isinstance(ast, dict):
        return notifies_list

    exports = ast.get("Exports", [])
    if not exports:
        return notifies_list

    anim_exp = next(
        (e for e in exports if e.get("Type") in ["AnimMontage", "AnimSequence"] or any(p.get("Name") == "Notifies" for p in e.get("Data", []))),
        exports[0]
    )

    notifies_prop = next((p for p in anim_exp.get("Data", []) if p.get("Name") == "Notifies"), None)
    if not notifies_prop or not isinstance(notifies_prop.get("Value"), list):
        return notifies_list

    for struct_item in notifies_prop["Value"]:
        inner_vals = struct_item.get("Value", [])
        notify_name = "PalCustomNotify"
        notify_time = 0.0
        notify_duration = 0.0
        track_index = 0

        for p in inner_vals:
            p_name = p.get("Name")
            p_val = p.get("Value")
            if p_name == "NotifyName":
                notify_name = str(p_val)
            elif p_name in ["LinkValue", "DisplayTime"]:
                try: notify_time = float(p_val)
                except (ValueError, TypeError): pass
            elif p_name == "Duration":
                try: notify_duration = float(p_val)
                except (ValueError, TypeError): pass
            elif p_name == "TrackIndex":
                try: track_index = int(p_val)
                except (ValueError, TypeError): pass

        notifies_list.append({
            "Name": notify_name,
            "Time": round(notify_time, 4),
            "Duration": round(notify_duration, 4),
            "Track": track_index
        })

    return notifies_list

# =============================================================================
# 3. IMPORT HELPERS
# =============================================================================

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

# =============================================================================
# 4. AST SANITIZATION & SUB-OBJECT INJECTION
# =============================================================================

def _sanitize_notifies_property_array(notifies_arr: list) -> None:
    target_enums = {
        "LinkMethod": ("EAnimLinkMethod", "EAnimLinkMethod::Absolute"),
        "CachedLinkMethod": ("EAnimLinkMethod", "EAnimLinkMethod::Absolute"),
        "MontageTickType": ("EMontageNotifyTickType", "EMontageNotifyTickType::Queued"),
        "NotifyFilterType": ("ENotifyFilterType", "ENotifyFilterType::NoFiltering")
    }
    for item in notifies_arr:
        if not isinstance(item, dict):
            continue
        vals = item.get("Value", [])
        if isinstance(vals, list):
            for p in vals:
                if not isinstance(p, dict):
                    continue
                p_name = p.get("Name", "")
                if p_name in target_enums:
                    enum_type, default_enum_val = target_enums[p_name]
                    val_str = str(p.get("EnumValue") or p.get("Value") or default_enum_val)
                    if "::" not in val_str:
                        val_str = f"{enum_type}::{val_str}"

                    p["$type"] = "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI"
                    p["ByteType"] = "FName"
                    p["EnumType"] = enum_type
                    p["EnumValue"] = val_str
                    p["IsZero"] = False
                    p.pop("Value", None)

def _sanitize_notify_dict(notify: dict) -> dict:
    if not isinstance(notify, dict):
        return notify
    banned = {
        "BodyInstance", "ResponseArray", "CollisionProfileName", 
        "CollisionResponses", "CollisionEnabled", "CanCharacterStepUpOn", 
        "WalkableSlopeOverride"
    }
    for k in list(notify.keys()):
        if k in banned:
            del notify[k]
    return notify

def _sanitize_ast_dict(data: dict) -> dict:
    if not isinstance(data, dict):
        return data

    data["HasUnversionedProperties"] = False

    pkg_flags = data.get("PackageFlags")
    if isinstance(pkg_flags, str):
        flags = [f.strip() for f in pkg_flags.split(",") if f.strip() and f.strip() != "PKG_UnversionedProperties"]
        data["PackageFlags"] = ", ".join(flags)
    elif isinstance(pkg_flags, int):
        data["PackageFlags"] &= ~0x00002000

    banned_props = {
        "BodyInstance", "ResponseArray", "CollisionProfileName", 
        "CollisionResponses", "CollisionEnabled", "CanCharacterStepUpOn", 
        "WalkableSlopeOverride"
    }

    exports = data.get("Exports", [])
    for idx, exp in enumerate(exports):
        exp_idx = idx + 1
        obj_name = exp.get("ObjectName", "")

        is_shape_comp = any(shape in obj_name for shape in ["CapsuleComponent", "SphereComponent", "BoxComponent"])
        if is_shape_comp:
            prop_data = exp.get("Data", [])
            if isinstance(prop_data, list):
                exp["Data"] = [
                    p for p in prop_data 
                    if isinstance(p, dict) and p.get("Name") not in banned_props
                ]

        is_anim = (
            exp.get("Type") in ["AnimSequence", "AnimMontage"] 
            or obj_name.startswith(("AS_", "AM_"))
            or any(isinstance(p, dict) and p.get("Name") == "Notifies" for p in exp.get("Data", []))
        )
        if is_anim:
            prop_data = exp.get("Data", [])
            if isinstance(prop_data, list):
                # Clean invalid empty Notifies properties (prevents DummyStruct is null error)
                clean_props = []
                for p in prop_data:
                    if isinstance(p, dict) and p.get("Name") == "Notifies":
                        notifies_arr = p.get("Value", [])
                        if not notifies_arr:
                            # Drop empty Notifies property completely
                            continue
                        _sanitize_notifies_property_array(notifies_arr)
                    clean_props.append(p)
                exp["Data"] = clean_props

        cbcd = exp.get("CreateBeforeCreateDependencies", [])
        if isinstance(cbcd, list) and exp_idx in cbcd:
            exp["CreateBeforeCreateDependencies"] = [i for i in cbcd if i != exp_idx]

    sync_namemap(data)
    return data

def sanitize_anim_sequence_notifies(target, *args, **kwargs):
    if isinstance(target, str):
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                sanitized = _sanitize_ast_dict(data)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(sanitized, f, indent=2)
                return sanitized
            except Exception as e:
                print(f"[PalBaker Safety Warning] Could not sanitize file {target}: {e}", flush=True)
                return target
        else:
            try:
                data = json.loads(target)
                return _sanitize_ast_dict(data) if isinstance(data, dict) else data
            except Exception:
                return target

    elif isinstance(target, dict):
        if "Exports" in target:
            return _sanitize_ast_dict(target)
        else:
            return _sanitize_notify_dict(target)

    elif isinstance(target, list):
        return [_sanitize_notify_dict(item) if isinstance(item, dict) else item for item in target]

    return target

def inject_sequence_notifies(base_ast: dict, notifies_list: list, sequence_name: str) -> dict:
    """Injects sub-objects (PalEffect, PalAttackCollision) and creates the Notifies array."""
    ast = copy.deepcopy(base_ast)
    
    # 1. Reset exports to ONLY the root AnimSequence export (purges previous sub-exports)
    raw_exports = ast.setdefault("Exports", [])
    main_exp = next((e for e in raw_exports if e.get("OuterIndex") == 0), raw_exports[0])
    main_exp["OuterIndex"] = 0
    ast["Exports"] = [main_exp]
    exports = ast["Exports"]
    main_exp_idx = 1

    imports = ast.setdefault("Imports", [])

    # READ TRUE SEQUENCE LENGTH FOR OUT-OF-BOUNDS PREVENTION
    seq_length = 2.875
    for p in main_exp.get("Data", []):
        if isinstance(p, dict) and p.get("Name") == "SequenceLength":
            try:
                seq_length = float(p.get("Value", 2.875))
            except (ValueError, TypeError):
                pass
            break

    ast["HasUnversionedProperties"] = False
    pkg_flags = ast.get("PackageFlags", "")
    if isinstance(pkg_flags, str):
        cleaned_flags = [f.strip() for f in pkg_flags.split(",") if f.strip() and f.strip() != "PKG_UnversionedProperties"]
        ast["PackageFlags"] = ", ".join(cleaned_flags)
    elif isinstance(pkg_flags, int):
        ast["PackageFlags"] &= ~0x00002000

    if not notifies_list:
        main_props = main_exp.get("Data", [])
        if isinstance(main_props, list):
            main_exp["Data"] = [p for p in main_props if isinstance(p, dict) and p.get("Name") != "Notifies"]
        sync_namemap(ast)
        return ast

    engine_pkg = find_or_add_import(imports, "/Script/Engine", "Package", "/Script/CoreUObject", 0)
    pal_pkg = find_or_add_import(imports, "/Script/Pal", "Package", "/Script/CoreUObject", 0)
    niagara_notifies_pkg = find_or_add_import(imports, "/Script/NiagaraAnimNotifies", "Package", "/Script/CoreUObject", 0)

    niagara_notify_class = find_or_add_import(imports, "AnimNotify_PlayNiagaraEffect", "Class", "/Script/CoreUObject", niagara_notifies_pkg)
    niagara_notify_default = find_or_add_import(imports, "Default__AnimNotify_PlayNiagaraEffect", "AnimNotify_PlayNiagaraEffect", "/Script/NiagaraAnimNotifies", niagara_notifies_pkg)

    pal_effect_state_class = find_or_add_import(imports, "PalAnimNotifyState_Effect", "Class", "/Script/CoreUObject", pal_pkg)
    pal_effect_state_default = find_or_add_import(imports, "Default__PalAnimNotifyState_Effect", "PalAnimNotifyState_Effect", "/Script/Pal", pal_pkg)

    pal_attack_class = find_or_add_import(imports, "PalAnimNotifyState_AttackCollision", "Class", "/Script/CoreUObject", pal_pkg)
    pal_attack_default = find_or_add_import(imports, "Default__PalAnimNotifyState_AttackCollision", "PalAnimNotifyState_AttackCollision", "/Script/Pal", pal_pkg)

    pal_filter_class = find_or_add_import(imports, "PalAttackFilter", "Class", "/Script/CoreUObject", pal_pkg)
    pal_filter_default = find_or_add_import(imports, "Default__PalAttackFilter", "PalAttackFilter", "/Script/Pal", pal_pkg)

    hit_loc_calc_class = find_or_add_import(imports, "PalHitLocationCalculator", "Class", "/Script/CoreUObject", pal_pkg)

    capsule_class = find_or_add_import(imports, "CapsuleComponent", "Class", "/Script/CoreUObject", engine_pkg)
    capsule_default = find_or_add_import(imports, "Default__CapsuleComponent", "CapsuleComponent", "/Script/Engine", engine_pkg)

    sphere_class = find_or_add_import(imports, "SphereComponent", "Class", "/Script/CoreUObject", engine_pkg)
    sphere_default = find_or_add_import(imports, "Default__SphereComponent", "SphereComponent", "/Script/Engine", engine_pkg)

    serialized_notifies = []
    created_sub_indices = []

    effect_state_counter = 0
    niagara_instant_counter = 0
    attack_counter = 0

    for n in notifies_list:
        notify_name = n.get("Name", "")
        time_val = float(n.get("Time", 0.0))
        dur_val = float(n.get("Duration", 0.0))
        track_idx = int(n.get("Track", 0))

        # ---------------------------------------------------------------------
        # Case A: PalEffect / Niagara
        # ---------------------------------------------------------------------
        if notify_name in ["PalEffect", "PlayNiagaraEffect"]:
            system_name = n.get("NiagaraSystem", "NS_UniqueSkill_Kamitsuki_dust")
            
            # Prefer recorded package path from scraper; fallback to skill root folder (NOT sub-suffixes)
            system_pkg = n.get("NiagaraPackage")
            if not system_pkg:
                folder_cand = system_name.replace("NS_UniqueSkill_", "").replace("NS_CommonSkill_", "").replace("NS_", "")
                for sfx in ["_trail", "_dust", "_Bite", "_Impact", "_hit", "_start", "_loop", "_end"]:
                    if folder_cand.lower().endswith(sfx.lower()):
                        folder_cand = folder_cand[:-len(sfx)]
                        break
                system_pkg = f"/Game/Pal/Effect/Skill/{folder_cand}/{system_name}"

            system_import = ensure_package_and_class_import(imports, system_pkg, system_name, "NiagaraSystem", "/Script/Niagara")

            if dur_val > 0.0:
                exp_name = f"PalAnimNotifyState_Effect_{effect_state_counter}"
                effect_state_counter += 1

                sub_data = [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                        "Name": "Template",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": system_import
                    }
                ]

                # Re-inject bone socket attachment if present
                sock_name = n.get("SocketName") or n.get("AttachBone")
                if sock_name and sock_name not in ["None", "root"]:
                    sub_data.append({
                        "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                        "Name": "SocketName",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": sock_name
                    })

                # Re-inject 3D LocationOffset struct
                loc = n.get("LocationOffset")
                if loc and isinstance(loc, dict) and any(float(loc.get(k, 0.0)) != 0.0 for k in ["X", "Y", "Z"]):
                    sub_data.append({
                        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                        "StructType": "Vector",
                        "SerializeNone": True,
                        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                        "Name": "LocationOffset",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": [
                            {
                                "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                                "Name": "LocationOffset",
                                "ArrayIndex": 0,
                                "IsZero": False,
                                "Value": {
                                    "X": float(loc.get("X", 0.0)),
                                    "Y": float(loc.get("Y", 0.0)),
                                    "Z": float(loc.get("Z", 0.0))
                                }
                            }
                        ]
                    })

                # Re-inject 3D RotationOffset struct
                rot = n.get("RotationOffset")
                if rot and isinstance(rot, dict) and any(float(rot.get(k, 0.0)) != 0.0 for k in ["Pitch", "Yaw", "Roll"]):
                    sub_data.append({
                        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                        "StructType": "Rotator",
                        "SerializeNone": True,
                        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                        "Name": "RotationOffset",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": [
                            {
                                "$type": "UAssetAPI.PropertyTypes.Structs.RotatorPropertyData, UAssetAPI",
                                "Name": "RotationOffset",
                                "ArrayIndex": 0,
                                "IsZero": False,
                                "Value": {
                                    "Pitch": float(rot.get("Pitch", 0.0)),
                                    "Yaw": float(rot.get("Yaw", 0.0)),
                                    "Roll": float(rot.get("Roll", 0.0))
                                }
                            }
                        ]
                    })

                sub_export = {
                    "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                    "ObjectName": exp_name,
                    "OuterIndex": main_exp_idx,
                    "ClassIndex": pal_effect_state_class,
                    "TemplateIndex": pal_effect_state_default,
                    "ObjectFlags": "RF_Transactional",
                    "Data": sub_data,
                    "SerializationBeforeSerializationDependencies": [],
                    "CreateBeforeSerializationDependencies": [system_import],
                    "SerializationBeforeCreateDependencies": [pal_effect_state_class, pal_effect_state_default],
                    "CreateBeforeCreateDependencies": [main_exp_idx],
                    "Extras": ""
                }
                exports.append(sub_export)
                sub_exp_idx = len(exports)
                created_sub_indices.append(sub_exp_idx)

                serialized_notifies.append({
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "StructType": "AnimNotifyEvent",
                    "Name": str(len(serialized_notifies)),
                    "Value": [
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "Value": 0.0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "Value": 0.0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 1e-05},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": "PalEffect"},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "Value": 0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "NotifyStateClass", "Value": sub_exp_idx},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": dur_val},
                        {
                            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                            "StructType": "AnimLinkableElement",
                            "Name": "EndLink",
                            "Value": [
                                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedMontage", "Value": 0},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SlotIndex", "Value": 0},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SegmentIndex", "Value": 0},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentBeginTime", "Value": 0.0},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentLength", "Value": seq_length},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": time_val + dur_val},
                                {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedSequence", "Value": main_exp_idx}
                            ]
                        },
                        {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "TrackIndex", "Value": track_idx},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": time_val},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "MontageTickType", "ByteType": "FName", "EnumType": "EMontageNotifyTickType", "EnumValue": "EMontageNotifyTickType::Queued", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "NotifyFilterType", "ByteType": "FName", "EnumType": "ENotifyFilterType", "EnumValue": "ENotifyFilterType::NoFiltering", "IsZero": False}
                    ]
                })
            else:
                exp_name = f"AnimNotify_PlayNiagaraEffect_{niagara_instant_counter}"
                niagara_instant_counter += 1

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
                    "Name": str(len(serialized_notifies)),
                    "Value": [
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "Value": 0.0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "Value": 0.0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 1e-05},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": "PlayNiagaraEffect"},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "Value": sub_exp_idx},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "NotifyStateClass", "Value": 0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": 0.0},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "TrackIndex", "Value": track_idx},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": time_val},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "MontageTickType", "ByteType": "FName", "EnumType": "EMontageNotifyTickType", "EnumValue": "EMontageNotifyTickType::Queued", "IsZero": False},
                        {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "NotifyFilterType", "ByteType": "FName", "EnumType": "ENotifyFilterType", "EnumValue": "ENotifyFilterType::NoFiltering", "IsZero": False}
                    ]
                })

        # ---------------------------------------------------------------------
        # Case B: PalAttackCollision (Hitbox Spawn)
        # ---------------------------------------------------------------------
        elif notify_name == "PalAttackCollision":
            idx_state = len(exports) + 1
            idx_filter = len(exports) + 2
            idx_shape = len(exports) + 3

            state_exp_name = f"PalAnimNotifyState_AttackCollision_{attack_counter}"
            filter_exp_name = f"PalAttackFilter_{attack_counter}"
            
            has_explicit_capsule = "CapsuleRadius" in n and "CapsuleHalfHeight" in n and n.get("CapsuleHalfHeight") != n.get("CapsuleRadius")
            shape_exp_name = f"CapsuleComponent_{attack_counter}" if has_explicit_capsule else f"SphereComponent_{attack_counter}"
            attack_counter += 1

            # Attach to Socket_Mouth if available, or directly to bone 'jaw' / 'head'
            attach_target = n.get("AttachBone", "Socket_Mouth")

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
                        "Value": attach_target
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
                    },
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                        "Name": "HitLocationCalculator",
                        "ArrayIndex": 0,
                        "IsZero": False,
                        "Value": hit_loc_calc_class
                    }
                ],
                "SerializationBeforeSerializationDependencies": [],
                "CreateBeforeSerializationDependencies": [hit_loc_calc_class],
                "SerializationBeforeCreateDependencies": [pal_filter_class, pal_filter_default],
                "CreateBeforeCreateDependencies": [idx_state],
                "Extras": ""
            }

            shape_data = []
            if has_explicit_capsule:
                shape_data.append({"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "CapsuleRadius", "Value": float(n.get("CapsuleRadius", 65.0))})
                shape_data.append({"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "CapsuleHalfHeight", "Value": float(n.get("CapsuleHalfHeight", 80.0))})
                shape_class_idx = capsule_class
                shape_default_idx = capsule_default
            else:
                radius_val = float(n.get("SphereRadius", n.get("CapsuleRadius", 100.0)))
                shape_data.append({"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SphereRadius", "Value": radius_val})
                shape_class_idx = sphere_class
                shape_default_idx = sphere_default

            rel_loc = n.get("RelativeLocation") or n.get("LocationOffset")
            if rel_loc and isinstance(rel_loc, dict) and any(float(rel_loc.get(k, 0.0)) != 0.0 for k in ["X", "Y", "Z"]):
                shape_data.append({
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "StructType": "Vector",
                    "SerializeNone": True,
                    "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                    "Name": "RelativeLocation",
                    "ArrayIndex": 0,
                    "IsZero": False,
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                            "Name": "RelativeLocation",
                            "ArrayIndex": 0,
                            "IsZero": False,
                            "Value": {
                                "X": float(rel_loc.get("X", 0.0)),
                                "Y": float(rel_loc.get("Y", 0.0)),
                                "Z": float(rel_loc.get("Z", 0.0))
                            }
                        }
                    ]
                })

            rel_rot = n.get("RelativeRotation") or n.get("RotationOffset")
            if rel_rot and isinstance(rel_rot, dict) and any(float(rel_rot.get(k, 0.0)) != 0.0 for k in ["Pitch", "Yaw", "Roll"]):
                shape_data.append({
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "StructType": "Rotator",
                    "SerializeNone": True,
                    "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                    "Name": "RelativeRotation",
                    "ArrayIndex": 0,
                    "IsZero": False,
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Structs.RotatorPropertyData, UAssetAPI",
                            "Name": "RelativeRotation",
                            "ArrayIndex": 0,
                            "IsZero": False,
                            "Value": {
                                "Pitch": float(rel_rot.get("Pitch", 0.0)),
                                "Yaw": float(rel_rot.get("Yaw", 0.0)),
                                "Roll": float(rel_rot.get("Roll", 0.0))
                            }
                        }
                    ]
                })

            shape_export = {                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
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
                "Name": str(len(serialized_notifies)),
                "Value": [
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "Value": 0.0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "Value": 0.0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 1e-05},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": "PalAttackCollision"},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "Value": 0},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "NotifyStateClass", "Value": idx_state},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": dur_val},
                    {
                        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                        "StructType": "AnimLinkableElement",
                        "Name": "EndLink",
                        "Value": [
                            {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedMontage", "Value": 0},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SlotIndex", "Value": 0},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "SegmentIndex", "Value": 0},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentBeginTime", "Value": 0.0},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "SegmentLength", "Value": seq_length},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": time_val + dur_val},
                            {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "LinkedSequence", "Value": main_exp_idx}
                        ]
                    },
                    {"$type": "UAssetAPI.PropertyTypes.Objects.IntPropertyData, UAssetAPI", "Name": "TrackIndex", "Value": track_idx},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": time_val},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "LinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "CachedLinkMethod", "ByteType": "FName", "EnumType": "EAnimLinkMethod", "EnumValue": "EAnimLinkMethod::Absolute", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "MontageTickType", "ByteType": "FName", "EnumType": "EMontageNotifyTickType", "EnumValue": "EMontageNotifyTickType::Queued", "IsZero": False},
                    {"$type": "UAssetAPI.PropertyTypes.Objects.BytePropertyData, UAssetAPI", "Name": "NotifyFilterType", "ByteType": "FName", "EnumType": "ENotifyFilterType", "EnumValue": "ENotifyFilterType::NoFiltering", "IsZero": False}
                ]
            })

    main_props = main_exp.setdefault("Data", [])
    main_exp["Data"] = [p for p in main_props if isinstance(p, dict) and p.get("Name") != "Notifies"]

    if serialized_notifies:
        main_exp["Data"].append({
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

    main_exp["CreateBeforeSerializationDependencies"] = list(set(main_exp.get("CreateBeforeSerializationDependencies", []) + created_sub_indices))
    ast["DependsMap"] = [[] for _ in range(len(exports))]
    sync_namemap(ast)
    return ast

# =============================================================================
# 5. AST RETARGETING: MONTAGES, SEQUENCES & BLENDSPACES
# =============================================================================

def patch_montage_ast(
    seed_data: dict,
    template_id: str,
    target_pal: str,
    anim_name: str = None,
    duration: float = None,
    skeleton_guid: str = None,
    notifies: list = None,
    template_notify: dict = None,
    *args,
    **kwargs
) -> dict:
    if isinstance(seed_data, str):
        if os.path.exists(seed_data):
            with open(seed_data, "r", encoding="utf-8-sig") as f:
                seed_data = json.load(f)
        else:
            seed_data = json.loads(seed_data)

    raw_str = json.dumps(seed_data)
    if template_id and target_pal:
        raw_str = raw_str.replace(f"AM_{template_id}_", f"AM_{target_pal}_")
        raw_str = raw_str.replace(f"AS_{template_id}_", f"AS_{target_pal}_")
        raw_str = raw_str.replace(f"/Monster/{template_id}/", f"/Monster/{target_pal}/")
        raw_str = raw_str.replace(f"/Skeleton/{template_id}/", f"/Skeleton/{target_pal}/")
        raw_str = raw_str.replace(f"SK_{template_id}_Skeleton", f"SK_{target_pal}_Skeleton")

    data = json.loads(raw_str)
    main_exp = data["Exports"][0]

    if anim_name:
        clean = anim_name if anim_name.startswith("AM_") else f"AM_{target_pal}_{anim_name}"
        main_exp["ObjectName"] = clean

    if duration is not None:
        for p in main_exp.get("Data", []):
            if p.get("Name") == "SequenceLength":
                p["Value"] = float(duration)
            elif p.get("Name") == "CompositeSections":
                for sec in p.get("Value", []):
                    for sp in sec.get("Value", []):
                        if sp.get("Name") == "SegmentLength":
                            sp["Value"] = float(duration)
            elif p.get("Name") == "SlotAnimTracks":
                for track in p.get("Value", []):
                    for tp in track.get("Value", []):
                        if tp.get("Name") == "AnimTrack":
                            for seg in tp.get("Value", []):
                                for s in seg.get("Value", []):
                                    for sp in s.get("Value", []):
                                        if sp.get("Name") == "AnimEndTime":
                                            sp["Value"] = float(duration)

    if skeleton_guid:
        main_exp["Extras"] = encode_guid_to_extras(skeleton_guid)

    if notifies is not None:
        notifies_prop = next((p for p in main_exp.get("Data", []) if p.get("Name") == "Notifies"), None)
        if notifies_prop:
            serialized_notifies = []
            proto = template_notify
            if not proto and notifies_prop.get("Value"):
                proto = notifies_prop["Value"][0]

            for n in notifies:
                if proto:
                    item = json.loads(json.dumps(proto))
                    for p in item.get("Value", []):
                        if p.get("Name") == "NotifyName":
                            p["Value"] = n.get("Name", "PalCustomNotify")
                        elif p.get("Name") in ["LinkValue", "DisplayTime"]:
                            p["Value"] = float(n.get("Time", 0.0))
                        elif p.get("Name") == "Duration":
                            p["Value"] = float(n.get("Duration", 0.0))
                        elif p.get("Name") == "TrackIndex":
                            p["Value"] = int(n.get("Track", 0))
                    serialized_notifies.append(item)
            notifies_prop["Value"] = serialized_notifies

    sync_namemap(data)
    return data

def patch_anim_sequence_ast(
    seed_data,
    template_id: str = "",
    target_pal: str = "",
    anim_name: str = None,
    duration: float = None,
    skeleton_guid: str = None,
    notifies: list = None,
    *args,
    **kwargs
) -> dict:
    if isinstance(seed_data, str):
        if os.path.exists(seed_data):
            with open(seed_data, "r", encoding="utf-8-sig") as f:
                seed_data = json.load(f)
        else:
            seed_data = json.loads(seed_data)

    raw_str = json.dumps(seed_data)
    if template_id and target_pal:
        raw_str = raw_str.replace(f"AS_{template_id}_", f"AS_{target_pal}_")
        raw_str = raw_str.replace(f"AM_{template_id}_", f"AM_{target_pal}_")
        raw_str = raw_str.replace(f"/Monster/{template_id}/", f"/Monster/{target_pal}/")
        raw_str = raw_str.replace(f"/Skeleton/{template_id}/", f"/Skeleton/{target_pal}/")
        raw_str = raw_str.replace(f"SK_{template_id}_Skeleton", f"SK_{target_pal}_Skeleton")
        raw_str = raw_str.replace(f"SK_{template_id}", f"SK_{target_pal}")

    data = json.loads(raw_str)
    if not data.get("Exports"):
        return data

    main_exp = data["Exports"][0]
    if anim_name:
        clean_name = anim_name if anim_name.startswith("AS_") else (f"AS_{target_pal}_{anim_name}" if target_pal else anim_name)
        main_exp["ObjectName"] = clean_name
        if "Package" in main_exp and isinstance(main_exp["Package"], str):
            pkg = main_exp["Package"]
            pkg_dir = pkg.rsplit("/", 1)[0]
            main_exp["Package"] = f"{pkg_dir}/{clean_name}"

    if duration is not None:
        for p in main_exp.get("Data", []):
            if isinstance(p, dict) and p.get("Name") == "SequenceLength":
                p["Value"] = float(duration)

    if skeleton_guid:
        main_exp["Extras"] = encode_guid_to_extras(skeleton_guid)

    if notifies:
        data = inject_sequence_notifies(data, notifies, main_exp["ObjectName"])
    else:
        data = sanitize_anim_sequence_notifies(data)

    sync_namemap(data)
    return data

def patch_blendspace_ast(
    seed_data,
    template_id: str = "",
    target_pal: str = "",
    bs_name: str = None,
    max_speed: float = None,
    *args,
    **kwargs
) -> dict:
    if isinstance(seed_data, str):
        if os.path.exists(seed_data):
            with open(seed_data, "r", encoding="utf-8-sig") as f:
                seed_data = json.load(f)
        else:
            seed_data = json.loads(seed_data)

    raw_str = json.dumps(seed_data)
    if template_id and target_pal:
        raw_str = raw_str.replace(f"BS_Move_{template_id}", f"BS_Move_{target_pal}")
        raw_str = raw_str.replace(f"AS_{template_id}_", f"AS_{target_pal}_")
        raw_str = raw_str.replace(f"/Monster/{template_id}/", f"/Monster/{target_pal}/")
        raw_str = raw_str.replace(f"SK_{template_id}_Skeleton", f"SK_{target_pal}_Skeleton")

    data = json.loads(raw_str)
    if bs_name and data.get("Exports"):
        data["Exports"][0]["ObjectName"] = bs_name

    if max_speed is not None and data.get("Exports"):
        for prop in data["Exports"][0].get("Data", []):
            if prop.get("Name") == "BlendParameters":
                for bp in prop.get("Value", []):
                    if bp.get("Name") == "Max":
                        bp["Value"] = float(max_speed)

    sync_namemap(data)
    return data

patch_sequence_ast = patch_anim_sequence_ast
patch_anim_montage_ast = patch_montage_ast
sanitize_uasset_ast = sanitize_anim_sequence_notifies
sanitize_notifies = sanitize_anim_sequence_notifies
clean_anim_sequence_ast = sanitize_anim_sequence_notifies

# =============================================================================
# 6. POST-COOK SEQUENCE PROCESSOR (ONLY PROCESSES FILES WITH NOTIFIES)
# =============================================================================

def process_cooked_anim_sequences(
    cooked_anims_dir: str, 
    sidecar_data: dict, 
    uasset_gui_exe: str, 
    usmap_path: str, 
    mod_name: str
) -> int:
    """
    Decompiles and patches ONLY the AnimSequences that have sequence-level notifies
    in the sidecar. Preserves all other cooked Unreal assets untouched.
    """
    if not os.path.exists(cooked_anims_dir):
        return 0

    uassets = [
        os.path.join(cooked_anims_dir, f) 
        for f in os.listdir(cooked_anims_dir) 
        if f.startswith("AS_") and f.endswith(".uasset")
    ]
    if not uassets:
        return 0

    processed_count = 0
    anims_meta = sidecar_data.get("custom_animations", {}).get("anims", {}) if isinstance(sidecar_data, dict) else {}
    target_guid = sidecar_data.get("custom_skeleton_guid")

    for uasset_path in uassets:
        base_name = os.path.splitext(os.path.basename(uasset_path))[0]

        # 1. Match against sidecar entries
        anim_entry = (
            anims_meta.get(base_name) or
            anims_meta.get(base_name.lower()) or
            next((v for k, v in anims_meta.items() if isinstance(v, dict) and v.get("sequence_asset") == base_name), None)
        )

        sequence_notifies = []
        if anim_entry and isinstance(anim_entry, dict):
            sequence_notifies = anim_entry.get("sequence_notifies", [])
            if not sequence_notifies:
                sequence_notifies = [
                    n for n in anim_entry.get("notifies", []) 
                    if n.get("Source") == "sequence"
                ]

        # 2. IF 0 SEQUENCE NOTIFIES, SKIP! Leave the freshly cooked Unreal binary untouched!
        if not sequence_notifies:
            continue

        json_path = uasset_path.replace(".uasset", ".json")

        # 3. Decompile only this specific asset
        if not decompile_uasset(uasset_gui_exe, uasset_path, json_path, usmap_path):
            continue

        try:
            with open(json_path, "r", encoding="utf-8-sig") as f:
                ast = json.load(f)

            # 4. Inject notifies and sub-objects (leaves root motion untouched)
            ast = inject_sequence_notifies(ast, sequence_notifies, base_name)

            if target_guid and ast.get("Exports"):
                ast["Exports"][0]["Extras"] = encode_guid_to_extras(target_guid)

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(ast, f, indent=2)

            # 5. Recompile binary in-place
            if compile_uasset(uasset_gui_exe, json_path, uasset_path, usmap_path):
                processed_count += 1
                print(f"  [PalBaker Anims] ✓ Injected {len(sequence_notifies)} notifies & sub-objects into {base_name}.uasset", flush=True)
        except Exception as e:
            print(f"  [PalBaker Anims Warning] Failed to process {base_name}: {e}", flush=True)
        finally:
            if os.path.exists(json_path):
                try:
                    os.remove(json_path)
                except OSError:
                    pass

    return processed_count

__all__ = [
    "decompile_uasset",
    "compile_uasset",
    "sync_namemap",
    "patch_montage_ast",
    "patch_anim_sequence_ast",
    "patch_sequence_ast",
    "patch_anim_montage_ast",
    "patch_blendspace_ast",
    "extract_notifies_from_ast",
    "decode_extras_to_guid",
    "encode_guid_to_extras",
    "process_cooked_anim_sequences",
    "sanitize_anim_sequence_notifies",
    "sanitize_uasset_ast",
    "sanitize_notifies",
    "clean_anim_sequence_ast",
    "inject_sequence_notifies",
]