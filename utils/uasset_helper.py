# utils/uasset_helper.py
import os
import json
import struct
import base64
import subprocess

def encode_guid_to_extras(guid_str: str) -> str:
    """Encodes a 32-hex GUID string into the 16-byte little-endian DWORD base64 string expected in NormalExport Extras."""
    clean = guid_str.replace("-", "").upper()
    if len(clean) != 32:
        raise ValueError(f"Invalid GUID length: {guid_str}")
    p1 = int(clean[0:8], 16)
    p2 = int(clean[8:16], 16)
    p3 = int(clean[16:24], 16)
    p4 = int(clean[24:32], 16)
    raw_bytes = struct.pack('<IIII', p1, p2, p3, p4)
    return base64.b64encode(raw_bytes).decode('utf-8')

def decode_extras_to_guid(extras_b64: str) -> str:
    """Decodes the 16-byte base64 Extras string back to a formatted GUID."""
    if not extras_b64:
        return ""
    try:
        raw_bytes = base64.b64decode(extras_b64)
        if len(raw_bytes) != 16:
            return ""
        p1, p2, p3, p4 = struct.unpack('<IIII', raw_bytes)
        raw_hex = f"{p1:08X}{p2:08X}{p3:08X}{p4:08X}"
        return f"{raw_hex[0:8]}-{raw_hex[8:12]}-{raw_hex[12:16]}-{raw_hex[16:20]}-{raw_hex[20:32]}"
    except Exception:
        return ""

def fix_untyped_arrays(node):
    """Recursively resolves missing ArrayType and DummyStruct metadata on empty arrays."""
    if isinstance(node, dict):
        if node.get("$type", "").endswith("ArrayPropertyData, UAssetAPI"):
            if node.get("ArrayType") is None:
                if node.get("Name") == "ChangedPropertyList":
                    node["ArrayType"] = "StructProperty"
                    node["DummyStruct"] = {
                        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                        "StructType": "BlueprintComponentChangedPropertyInfo",
                        "Name": "ChangedPropertyList",
                        "Value": []
                    }
                elif node.get("Name") == "Metadata":
                    node["ArrayType"] = "ObjectProperty"
                elif node.get("DummyStruct"):
                    node["ArrayType"] = "StructProperty"
                elif node.get("Value") and len(node["Value"]) > 0:
                    first_item = node["Value"][0]
                    if isinstance(first_item, dict):
                        item_type = first_item.get("$type", "")
                        if "StructPropertyData" in item_type:
                            node["ArrayType"] = "StructProperty"
                        elif "ObjectPropertyData" in item_type:
                            node["ArrayType"] = "ObjectProperty"
                        elif "NamePropertyData" in item_type:
                            node["ArrayType"] = "NameProperty"
                else:
                    node["ArrayType"] = "StructProperty"
        for v in node.values():
            fix_untyped_arrays(v)
    elif isinstance(node, list):
        for item in node:
            fix_untyped_arrays(item)

def sync_namemap(data: dict):
    """
    Recursively scans the AST for any FNames (NamePropertyData, ObjectName, SerializedType, etc.)
    and ensures they exist in data['NameMap'], reconciles DependsMap length, and updates Generation counts.
    """
    fix_untyped_arrays(data)
    name_map = data.setdefault("NameMap", [])
    existing = set(name_map)

    def add_name(val):
        if isinstance(val, str) and val and val not in existing:
            name_map.append(val)
            existing.add(val)

    # Pre-seed standard Unreal Engine property types so UAssetAPI never attempts
    # to register missing type names during serialization (preventing InvalidOperationException)
    STANDARD_UE_TYPES = [
        "ByteProperty", "BoolProperty", "IntProperty", "FloatProperty", "ObjectProperty",
        "NameProperty", "DelegateProperty", "DoubleProperty", "ArrayProperty", "StructProperty",
        "StrProperty", "TextProperty", "InterfaceProperty", "MulticastDelegateProperty",
        "WeakObjectProperty", "LazyObjectProperty", "AssetObjectProperty", "SoftObjectProperty",
        "UInt64Property", "UInt32Property", "UInt16Property", "Int64Property", "Int16Property",
        "Int8Property", "MapProperty", "SetProperty", "EnumProperty", "FieldPathProperty",
        "OptionalProperty", "Utf8StrProperty", "AnsiStrProperty",
        # Pre-seed common implicit inner struct types to prevent serialization lock crashes
        "BlueprintComponentChangedPropertyInfo", "Guid", "Vector", "Rotator", "Vector2D", 
        "Transform", "LinearColor", "Color", "Quat", "SoftObjectPath"
    ]
    for t in STANDARD_UE_TYPES:
        add_name(t)

    # Keys in UAssetAPI JSON that strictly hold FName strings
    fname_keys = {
        "Name", "ObjectName", "ClassName", "ClassPackage", "PackageName",
        "StructType", "EnumType", "InnerType", "ArrayType", "PropertyTypeName",
        "SerializedType", "ClassConfigName", "RepNotifyFunc", "AssetName",
        "VirtualFunctionName", "DelegateName", "KeyType", "ValueType",
        "PropertyType", "SubPathString", "ClassWithin", "DummyStruct"
    }
    def scan(node):
        if isinstance(node, dict):
            typ = node.get("$type", "")
            
            # 1. Property values representing FNames
            if "NamePropertyData" in typ or "EnumPropertyData" in typ:
                val = node.get("Value")
                if isinstance(val, str):
                    add_name(val)
            
            # 2. Bytecode FFieldPath (array of FName strings in 'Path')
            if "FFieldPath" in typ:
                for p_name in node.get("Path", []):
                    if isinstance(p_name, str):
                        add_name(p_name)

            # 3. Bytecode EX_NameConst
            if "EX_NameConst" in typ:
                val = node.get("Value")
                if isinstance(val, str):
                    add_name(val)

            # 4. ClassExport FuncMap: [[func_name_str, export_idx], ...]
            if "FuncMap" in node and isinstance(node["FuncMap"], list):
                for entry in node["FuncMap"]:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 1 and isinstance(entry[0], str):
                        add_name(entry[0])

            # 5. Scan known FName keys
            for k, v in node.items():
                if k in fname_keys and isinstance(v, str):
                    add_name(v)
                elif isinstance(v, (dict, list)):
                    scan(v)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(data.get("Exports", []))
    scan(data.get("Imports", []))

    # Reconcile DependsMap to match Exports count exactly
    exports = data.get("Exports", [])
    depends_map = data.setdefault("DependsMap", [])
    while len(depends_map) < len(exports):
        depends_map.append([])
    if len(depends_map) > len(exports):
        del depends_map[len(exports):]

    # Reconcile Generation counts
    generations = data.get("Generations", [])
    if generations and isinstance(generations, list):
        generations[0]["ExportCount"] = len(exports)
        generations[0]["NameCount"] = len(name_map)

def compile_uasset(uasset_gui: str, src_json: str, dest_uasset: str, usmap_path: str = None) -> bool:
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    cmd = [uasset_gui, "fromjson", src_json, dest_uasset]
    if usmap_path and os.path.exists(usmap_path):
        cmd.append(usmap_path)
    os.makedirs(os.path.dirname(dest_uasset), exist_ok=True)
    res = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    if res.returncode != 0:
        if res.stdout.strip():
            print(f"[UAssetGUI fromjson STDOUT] {res.stdout.strip()}", flush=True)
        if res.stderr.strip():
            print(f"[UAssetGUI fromjson STDERR] {res.stderr.strip()}", flush=True)
    return res.returncode == 0 and os.path.exists(dest_uasset)

def extract_notifies_from_ast(data: dict) -> list[dict]:
    """Extracts a normalized list of AnimNotifies (Name, Time, Duration) from any montage AST."""
    notifies = []
    for exp in data.get("Exports", []):
        for prop in exp.get("Data", []):
            if prop.get("Name") == "Notifies" and isinstance(prop.get("Value"), list):
                for item in prop["Value"]:
                    struct_vals = item.get("Value", [])
                    n_name = next((p["Value"] for p in struct_vals if p.get("Name") == "NotifyName"), "")
                    n_time = next((float(p["Value"]) for p in struct_vals if p.get("Name") == "LinkValue"), 0.0)
                    n_dur = next((float(p["Value"]) for p in struct_vals if p.get("Name") == "Duration"), 0.0)
                    notifies.append({
                        "Name": str(n_name),
                        "Time": round(float(n_time), 4),
                        "Duration": round(float(n_dur), 4)
                    })
                return notifies
    return notifies

def create_notify_struct_node(index_str: str, time_val: float, name_val: str, duration_val: float = 0.0, template_struct: dict = None) -> dict:
    """Clones a schema-compliant AnimNotifyEvent struct from template and mutates only timing and name fields."""
    if template_struct:
        node = json.loads(json.dumps(template_struct))
        node["Name"] = str(index_str)
        for p in node.get("Value", []):
            p_name = p.get("Name")
            if p_name == "NotifyName":
                p["Value"] = name_val
            elif p_name in ["LinkValue", "SegmentBeginTime"]:
                p["Value"] = float(time_val)
            elif p_name == "Duration":
                p["Value"] = float(duration_val)
            elif p_name == "NotifyStateClass":
                if duration_val <= 0.0:
                    p["Value"] = 0
                    p["IsZero"] = True
            elif p_name == "EndLink" and isinstance(p.get("Value"), list):
                for end_p in p["Value"]:
                    if end_p.get("Name") in ["LinkValue", "SegmentBeginTime"]:
                        end_p["Value"] = float(time_val + duration_val)
                    elif end_p.get("Name") == "SegmentLength":
                        end_p["Value"] = float(duration_val)
        return node

    # Schema fallback
    node_value = [
        { "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "Value": 0.0001 },
        { "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "Value": -0.0001 },
        { "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 0.00001 },
        { "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": name_val },
        { "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "Value": 0, "IsZero": True },
        { "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": float(time_val) }
    ]
    if duration_val > 0.0:
        node_value.append({ "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": float(duration_val) })

    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "AnimNotifyEvent",
        "SerializeNone": True,
        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
        "SerializationControl": "NoExtension",
        "Operation": "None",
        "Name": str(index_str),
        "ArrayIndex": 0,
        "PropertyGuid": None,
        "IsZero": False,
        "PropertyTagFlags": "None",
        "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": node_value
    }

def patch_montage_ast(
    data: dict,
    template_id: str,
    target_pal: str,
    anim_name: str | None = None,
    duration: float | None = None,
    skeleton_guid: str | None = None,
    notifies: list[dict] | None = None,
    template_notify: dict | None = None
) -> dict:
    """Clones a seed montage AST and synthesizes an arbitrary valid montage with target notifies and duration."""
    raw_str = json.dumps(data)
    if anim_name:
        raw_str = raw_str.replace(f"AS_{template_id}_CookingStart", f"AS_{target_pal}_{anim_name}")
        raw_str = raw_str.replace(f"AS_{template_id}_CookingLoop", f"AS_{target_pal}_{anim_name}")
        raw_str = raw_str.replace(f"AM_{template_id}_Cooking", f"AM_{target_pal}_{anim_name}")
        raw_str = raw_str.replace("Cooking", anim_name)
    raw_str = raw_str.replace(template_id, target_pal)

    mutated = json.loads(raw_str)
    main_export = mutated["Exports"][0]

    if skeleton_guid:
        main_export["Extras"] = encode_guid_to_extras(skeleton_guid)

    props = main_export.get("Data", [])

    if duration is not None:
        dur_float = float(duration)
        seq_len = next((p for p in props if p.get("Name") == "SequenceLength"), None)
        if seq_len:
            seq_len["Value"] = dur_float

        comp_sections = next((p for p in props if p.get("Name") == "CompositeSections"), None)
        if comp_sections and comp_sections.get("Value"):
            for sec in comp_sections["Value"]:
                for p in sec.get("Value", []):
                    if p.get("Name") == "SegmentLength":
                        p["Value"] = dur_float

        slot_tracks = next((p for p in props if p.get("Name") == "SlotAnimTracks"), None)
        if slot_tracks and slot_tracks.get("Value"):
            for track in slot_tracks["Value"]:
                for p in track.get("Value", []):
                    if p.get("Name") == "AnimTrack":
                        for inner in p.get("Value", []):
                            if inner.get("Name") == "AnimSegments" and inner.get("Value"):
                                for seg in inner["Value"]:
                                    for seg_p in seg.get("Value", []):
                                        if seg_p.get("Name") == "AnimEndTime":
                                            seg_p["Value"] = dur_float

    if notifies is not None:
        notifies_prop = next((p for p in props if p.get("Name") == "Notifies"), None)
        if not notifies_prop:
            notifies_prop = {
                "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                "ArrayType": "StructProperty",
                "Name": "Notifies",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": []
            }
            props.append(notifies_prop)

        tmpl = template_notify or (notifies_prop["Value"][0] if notifies_prop.get("Value") else None)

        notifies_prop["Value"] = [
            create_notify_struct_node(
                str(i),
                float(n.get("Time", 0.0)),
                n.get("Name", "PalCustomNotify"),
                float(n.get("Duration", 0.0)),
                template_struct=tmpl
            )
            for i, n in enumerate(notifies)
        ]

    sync_namemap(mutated)
    return mutated

def decompile_uasset(uasset_gui: str, src_uasset: str, dest_json: str, usmap_path: str = None) -> bool:
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    cmd = [uasset_gui, "tojson", src_uasset, dest_json, "VER_UE5_1"]
    if usmap_path and os.path.exists(usmap_path):
        cmd.append(usmap_path)
    res = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    return res.returncode == 0 and os.path.exists(dest_json)
