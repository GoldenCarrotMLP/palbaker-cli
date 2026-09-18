# utils/anim_patcher/montage_generator.py
import os
import json
import struct

CUSTOM_VERSIONS = [
    ((0x601D1886, 0xAC644F84, 0xAA16D3DE, 0x0DEAC7D6), 80),
    ((0x697DD581, 0xE64F41AB, 0xAA4A51EC, 0xBEB7B628), 20),
    ((0xAF43A65D, 0x7FD34947, 0x98733E8E, 0xD9C1BB05), 15),
    ((0xCFFC743F, 0x43B04480, 0x939114DF, 0x171D2073), 37),
    ((0xE4B068ED, 0xF49442E9, 0xA231DA0B, 0x2E46BB41), 40),
]

class UAssetWriter:
    def __init__(self):
        self.data = bytearray()
        self.names = []
        self.imports = []
        self.exports = []
        self.depends = []

    def write_uint8(self, val):  self.data.extend(struct.pack('<B', val))
    def write_uint16(self, val): self.data.extend(struct.pack('<H', val))
    def write_int16(self, val):  self.data.extend(struct.pack('<h', val))
    def write_int32(self, val):  self.data.extend(struct.pack('<i', val))
    def write_uint32(self, val): self.data.extend(struct.pack('<I', val))
    def write_int64(self, val):  self.data.extend(struct.pack('<q', val))
    def write_float(self, val):  self.data.extend(struct.pack('<f', val))

    def write_fstring(self, s):
        if not s:
            self.write_int32(0)
            return
        s_bytes = s.encode('utf-8')
        self.write_int32(len(s_bytes) + 1)
        self.data.extend(s_bytes)
        self.write_uint8(0)

    def write_engine_version(self, major=5, minor=1, patch=0, changelist=0, branch="++UE5+Release-5.1"):
        self.write_uint16(major)
        self.write_uint16(minor)
        self.write_uint16(patch)
        self.write_uint32(changelist)
        self.write_fstring(branch)

    def write_bit_array(self, num_bits):
        self.write_int32(num_bits)
        if num_bits > 0:
            num_words = (num_bits + 31) // 32
            for _ in range(num_words):
                self.write_uint32(0)

    def add_name(self, name):
        if not name: name = "None"
        if name not in self.names: self.names.append(name)
        return self.names.index(name)

    def write_fname(self, name):
        idx = self.add_name(name if name else "None")
        self.write_int32(idx)
        self.write_int32(0)

    def add_import(self, class_package, class_name, outer_index, object_name, package_name="None"):
        self.add_name(class_package)
        self.add_name(class_name)
        self.add_name(object_name)
        self.add_name(package_name)
        entry = {
            "ClassPackage": class_package, "ClassName": class_name,
            "OuterIndex": outer_index, "ObjectName": object_name, "PackageName": package_name
        }
        for idx, imp in enumerate(self.imports):
            if imp == entry: return -(idx + 1)
        self.imports.append(entry)
        return -len(self.imports)

    def normalize_package_path(self, raw_path):
        clean_path = raw_path.replace("\\", "/").strip("/")
        if clean_path.startswith("Pal/Content/"): return "/Game/" + clean_path[len("Pal/Content/"):]
        elif clean_path.startswith("Game/"): return "/" + clean_path
        elif not clean_path.startswith("/"): return "/" + clean_path
        return clean_path

    def parse_path_to_import(self, full_path, class_name, class_package="/Script/Engine"):
        if not full_path: return 0
        clean_path = full_path.replace("'", "").strip()
        if "." in clean_path:
            pkg_path = clean_path.split(".")[0]
            obj_name = clean_path.split(".")[-1]
            if obj_name.isdigit(): obj_name = pkg_path.rsplit("/", 1)[-1]
        else:
            pkg_path = clean_path
            obj_name = clean_path.rsplit("/", 1)[-1]

        pkg_path = self.normalize_package_path(pkg_path)
        pkg_idx = self.add_import("/Script/CoreUObject", "Package", 0, pkg_path, "None")
        return self.add_import(class_package, class_name, pkg_idx, obj_name, "None")

    def parse_object_ref(self, obj_ref):
        if not obj_ref: return 0
        obj_name_full = obj_ref.get("ObjectName", "")
        obj_path = obj_ref.get("ObjectPath", "")

        for i, exp in enumerate(self.exports):
            if exp.get("Name") and exp["Name"] in obj_name_full:
                return i + 1

        if "'" in obj_name_full:
            class_type, obj_name = obj_name_full.split("'", 1)
            obj_name = obj_name.rstrip("'")
            clean_pkg = self.normalize_package_path(obj_path.split(".")[0])
            pkg_idx = self.add_import("/Script/CoreUObject", "Package", 0, clean_pkg, "None")
            return self.add_import("/Script/Engine", class_type, pkg_idx, obj_name, "None")
        return 0

    def write_fproperty_tag(self, name, prop_type, size, array_idx, extra_type_info=None):
        tag_start = len(self.data)
        self.write_fname(name)
        if name == "None": return tag_start, -1
        self.write_fname(prop_type)
        size_offset = len(self.data)
        self.write_int32(size)
        self.write_int32(array_idx)

        if prop_type == "StructProperty":
            self.write_fname(extra_type_info)
            self.data.extend(b'\x00' * 16)
        elif prop_type == "BoolProperty":
            self.write_uint8(1 if extra_type_info else 0)
        elif prop_type in ["ByteProperty", "EnumProperty", "ArrayProperty", "SetProperty", "OptionalProperty"]:
            self.write_fname(extra_type_info)
        elif prop_type == "MapProperty":
            self.write_fname(extra_type_info[0])
            self.write_fname(extra_type_info[1])

        self.write_uint8(0)
        return tag_start, size_offset

    def get_inner_struct_name(self, array_name):
        if array_name == "CompositeSections": return "CompositeSection"
        elif array_name == "SlotAnimTracks": return "SlotAnimationTrack"
        elif array_name == "AnimSegments": return "AnimSegment"
        elif array_name == "Notifies": return "AnimNotifyEvent"
        return "AnimNotifyEvent"

    def infer_type(self, key, val):
        if val is None: return "ObjectProperty", None
        if isinstance(val, bool): return "BoolProperty", val
        if isinstance(val, float): return "FloatProperty", None
        if isinstance(val, int): return "IntProperty", None
        if isinstance(val, str):
            if "::" in val: return "EnumProperty", val.split("::")[0]
            return "NameProperty", None
        if isinstance(val, dict):
            if "ObjectPath" in val or "ObjectName" in val: return "ObjectProperty", None
            if "BlendOption" in val: return "StructProperty", "AlphaBlend"
            if "SlotIndex" in val and "SegmentBeginTime" in val: return "StructProperty", "AnimLinkableElement"
            if "AnimSegments" in val: return "StructProperty", "AnimTrack"
            return "StructProperty", key
        if isinstance(val, list):
            if key == "Metadata": return "ArrayProperty", "ObjectProperty"
            return "ArrayProperty", "StructProperty"
        return "ObjectProperty", None

    def serialize_property(self, name, prop_type, val, extra_type_info=None):
        tag_start, size_offset = self.write_fproperty_tag(name, prop_type, 0, 0, extra_type_info)
        data_start = len(self.data)

        if prop_type == "FloatProperty": self.write_float(0.0 if val is None else float(val))
        elif prop_type == "IntProperty": self.write_int32(0 if val is None else int(val))
        elif prop_type == "NameProperty": self.write_fname("None" if val is None else str(val))
        elif prop_type == "ObjectProperty": self.write_int32(self.parse_object_ref(val))
        elif prop_type in ["EnumProperty", "ByteProperty"]: self.write_fname("None" if val is None else str(val))
        elif prop_type == "BoolProperty": pass
        elif prop_type == "StructProperty":
            if isinstance(val, dict):
                for k, v in val.items():
                    inner_type, inner_extra = self.infer_type(k, v)
                    self.serialize_property(k, inner_type, v, inner_extra)
            self.write_fname("None")
        elif prop_type == "ArrayProperty":
            self.write_int32(len(val))
            if extra_type_info == "StructProperty":
                inner_struct_name = self.get_inner_struct_name(name)
                _, inner_size_offset = self.write_fproperty_tag(name, "StructProperty", 0, 0, inner_struct_name)
                inner_data_start = len(self.data)

                for item in val:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            item_type, item_extra = self.infer_type(k, v)
                            self.serialize_property(k, item_type, v, item_extra)
                    self.write_fname("None")

                inner_data_len = len(self.data) - inner_data_start
                struct.pack_into('<i', self.data, inner_size_offset, inner_data_len)
            elif extra_type_info == "ObjectProperty":
                for item in val: self.write_int32(self.parse_object_ref(item))

        data_len = len(self.data) - data_start
        struct.pack_into('<i', self.data, size_offset, data_len)

def build_uasset(json_data, output_filepath):
    writer = UAssetWriter()
    writer.add_name("None")
    
    for obj in json_data:
        writer.exports.append(obj)
        writer.add_name(obj.get("Name", "None"))

    resolved_export_links = []
    for exp in writer.exports:
        class_str = exp.get("Class", "")
        if "UScriptClass'AnimMontage'" in class_str or exp.get("Type") == "AnimMontage":
            engine_pkg_idx = writer.add_import("/Script/CoreUObject", "Package", 0, "/Script/Engine", "None")
            class_idx = writer.add_import("/Script/CoreUObject", "Class", engine_pkg_idx, "AnimMontage", "None")
        elif "BlueprintGeneratedClass" in class_str:
            class_path = class_str.split("'", 1)[1].rstrip("'")
            class_idx = writer.parse_path_to_import(class_path, "BlueprintGeneratedClass", "/Script/Engine")
        else:
            class_idx = 0

        template_idx = writer.parse_object_ref(exp["Template"]) if "Template" in exp else 0
        outer_idx = writer.parse_object_ref(exp["Outer"]) if "Outer" in exp else 0
        resolved_export_links.append((class_idx, template_idx, outer_idx))

    export_metadata = []
    for obj in json_data:
        obj_writer = UAssetWriter()
        obj_writer.names = writer.names
        obj_writer.imports = writer.imports
        obj_writer.exports = writer.exports

        for prop_name, prop_val in obj.get("Properties", {}).items():
            prop_type, extra = obj_writer.infer_type(prop_name, prop_val)
            obj_writer.serialize_property(prop_name, prop_type, prop_val, extra)
        
        obj_writer.write_fname("None")
        obj_writer.write_uint32(0) # bHasObjectGuid = False

        if "SkeletonGuid" in obj:
            guid_str = obj["SkeletonGuid"].replace("-", "")
            for i in range(0, 32, 8):
                obj_writer.write_uint32(int(guid_str[i:i+8], 16))

        export_metadata.append({"Size": len(obj_writer.data), "Data": obj_writer.data})

    # Summary header
    writer.write_uint32(0x9E2A83C1)
    writer.write_int32(-8)
    writer.write_int32(864)
    writer.write_int32(522)
    writer.write_int32(1008)
    writer.write_int32(0)

    writer.write_int32(len(CUSTOM_VERSIONS))
    for guid, ver in CUSTOM_VERSIONS:
        for g in guid: writer.write_uint32(g)
        writer.write_int32(ver)

    total_header_size_pos = len(writer.data)
    writer.write_int32(0)

    pkg_raw_path = json_data[0].get("Package", "") if len(json_data) > 0 else ""
    package_name = writer.normalize_package_path(pkg_raw_path) if pkg_raw_path else "/Game/Unknown"
    writer.write_fstring(package_name)
    writer.write_uint32(0)
    
    name_count_pos = len(writer.data)
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_fstring("")
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_int32(len(writer.exports))
    export_offset_pos = len(writer.data)
    writer.write_int32(0)
    import_count_pos = len(writer.data)
    writer.write_int32(0)
    writer.write_int32(0)
    depends_offset_pos = len(writer.data)
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_int32(0)
    
    writer.data.extend(b'\x00' * 32)
    writer.write_int32(1)
    writer.write_int32(len(writer.exports))
    gen_name_count_pos = len(writer.data)
    writer.write_int32(0)

    writer.write_engine_version(5, 1, 0, 0, "++UE5+Release-5.1")
    writer.write_engine_version(5, 1, 0, 0, "++UE5+Release-5.1")
    writer.write_uint32(0)
    writer.write_int32(0)
    writer.write_uint32(0)
    writer.write_int32(0)
    
    asset_registry_pos = len(writer.data)
    writer.write_int32(0)
    writer.write_int64(0)
    writer.write_int32(0)
    writer.write_int32(0)
    writer.write_int32(-1)
    writer.write_int32(0)
    names_ref_from_exports_pos = len(writer.data)
    writer.write_int32(0)
    writer.write_int64(-1)
    writer.write_int32(-1)

    # Name map
    name_offset = len(writer.data)
    for name in writer.names:
        writer.write_fstring(name)
        writer.write_uint16(0)
        writer.write_uint16(0)
    
    struct.pack_into('<i', writer.data, name_count_pos, len(writer.names))
    struct.pack_into('<i', writer.data, name_count_pos + 4, name_offset)
    struct.pack_into('<i', writer.data, gen_name_count_pos, len(writer.names))
    struct.pack_into('<i', writer.data, names_ref_from_exports_pos, len(writer.names))
    
    # Import map
    import_offset = len(writer.data)
    struct.pack_into('<i', writer.data, import_count_pos, len(writer.imports))
    struct.pack_into('<i', writer.data, import_count_pos + 4, import_offset)

    for imp in writer.imports:
        writer.write_fname(imp["ClassPackage"])
        writer.write_fname(imp["ClassName"])
        writer.write_int32(imp["OuterIndex"])
        writer.write_fname(imp["ObjectName"])
        writer.write_fname(imp["PackageName"])
        writer.write_uint32(0)

    # Export map
    export_offset = len(writer.data)
    struct.pack_into('<i', writer.data, export_offset_pos, export_offset)

    serial_offset_positions = []
    for i, exp in enumerate(writer.exports):
        class_idx, template_idx, outer_idx = resolved_export_links[i]
        writer.write_int32(class_idx)
        writer.write_int32(0)
        writer.write_int32(template_idx)
        writer.write_int32(outer_idx)
        writer.write_fname(exp.get("Name", "None"))
        writer.write_uint32(0x00200008 if i == 0 else 0x00000008)
        writer.write_int64(export_metadata[i]["Size"])
        serial_offset_positions.append(len(writer.data))
        writer.write_int64(0)
        writer.write_uint32(0)
        writer.write_uint32(0)
        writer.write_uint32(0)
        writer.write_uint32(0)
        writer.write_uint32(0)
        writer.write_uint32(1)
        writer.write_uint32(1 if i == 0 else 0)
        writer.write_uint32(0)
        writer.write_int32(-1)
        writer.write_int32(0)
        writer.write_int32(0)
        writer.write_int32(0)
        writer.write_int32(0)

    depends_offset = len(writer.data)
    struct.pack_into('<i', writer.data, depends_offset_pos, depends_offset)
    for _ in writer.exports: writer.write_int32(0)

    # Asset registry
    asset_registry_offset = len(writer.data)
    struct.pack_into('<i', writer.data, asset_registry_pos, asset_registry_offset)
    dep_data_offset_pos = len(writer.data)
    writer.write_int64(0)
    writer.write_int32(1)

    main_asset_name = writer.exports[0].get("Name", "AnimMontage")
    writer.write_fstring(main_asset_name)
    writer.write_fstring("/Script/Engine.AnimMontage")

    tags = []
    skel_ref = writer.exports[0].get("Properties", {}).get("Skeleton")
    if skel_ref and "ObjectPath" in skel_ref:
        skel_path = writer.normalize_package_path(skel_ref["ObjectPath"].split(".")[0])
        skel_name = skel_ref.get("ObjectName", "").split("'")[-1].rstrip("'")
        tags.append(("Skeleton", f"/Script/Engine.Skeleton'{skel_path}.{skel_name}'"))

    writer.write_int32(len(tags))
    for k, v in tags:
        writer.write_fstring(k)
        writer.write_fstring(v)

    dep_data_offset = len(writer.data)
    struct.pack_into('<q', writer.data, dep_data_offset_pos, dep_data_offset)
    writer.write_bit_array(len(writer.imports))
    writer.write_bit_array(0)

    header_end = len(writer.data)
    struct.pack_into('<i', writer.data, total_header_size_pos, header_end)

    for i, exp_meta in enumerate(export_metadata):
        struct.pack_into('<q', writer.data, serial_offset_positions[i], len(writer.data))
        writer.data.extend(exp_meta["Data"])

    writer.write_uint32(0x9E2A83C1)
    os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)
    with open(output_filepath, 'wb') as f:
        f.write(writer.data)


def create_dynamic_montage_payload(montage_name: str, sequence_name: str, base_pal: str, mod_name: str, skeleton_guid: str, notifies: list = None, anim_length: float = 2.0, category: str = "Monster", is_custom_pal: bool = False) -> list:
    if notifies is None:
        notifies = []

    clean_guid = skeleton_guid.replace("-", "").upper()
    if len(clean_guid) != 32:
        clean_guid = "F364245843D36EB42B398F898DDC8313"

    formatted_guid = f"{clean_guid[0:8]}-{clean_guid[8:12]}-{clean_guid[12:16]}-{clean_guid[16:20]}-{clean_guid[20:32]}"
    
    is_var = (not is_custom_pal and base_pal.lower() != mod_name.lower())
    cat_sanitized = category.replace(" ", "_")
    
    # Standalone custom pals and base pals stay in their root folders. Only true variants nest.
    if is_var:
        skel_pkg = f"/Game/Pal/Model/Character/Skeleton/{base_pal}/{mod_name}/SK_{mod_name}_Skeleton"
        seq_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{base_pal}/{mod_name}/{sequence_name}"
        montage_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{base_pal}/{mod_name}/{montage_name}"
    else:
        skel_pkg = f"/Game/Pal/Model/Character/Skeleton/{mod_name}/SK_{mod_name}_Skeleton"
        seq_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{mod_name}/{sequence_name}"
        montage_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{mod_name}/{montage_name}"


    # Build AnimNotifyEvent array
    serialized_notifies = []
    for idx, n in enumerate(notifies):
        serialized_notifies.append({
            "TriggerTimeOffset": 0.0,
            "DisplayTime": float(n.get("Time", 0.0)),
            "NotifyName": n.get("Name", "PalCustomNotify"),
            "Notify": None
        })

    payload = [
        {
            "Type": "AnimMontage",
            "Name": montage_name,
            "Flags": "RF_Public | RF_Standalone | RF_Transactional",
            "Class": "UScriptClass'AnimMontage'",
            "Package": montage_pkg,
            "Properties": {
                "BlendIn": {
                    "BlendOption": "EAlphaBlendOption::Cubic"
                },
                "BlendOut": {
                    "BlendTime": 0.2,
                    "BlendOption": "EAlphaBlendOption::Cubic"
                },
                "CompositeSections": [
                    {
                        "SectionName": "Default",
                        "NextSectionName": "Default" if "Loop" in montage_name else "None",
                        "Metadata": [],
                        "LinkedMontage": {
                            "ObjectName": f"AnimMontage'{montage_name}'",
                            "ObjectPath": f"{montage_pkg}.0"
                        },
                        "SlotIndex": 0,
                        "SegmentIndex": 0,
                        "LinkMethod": "EAnimLinkMethod::Absolute",
                        "CachedLinkMethod": "EAnimLinkMethod::Absolute",
                        "SegmentBeginTime": 0.0,
                        "SegmentLength": float(anim_length),
                        "LinkValue": 0.0,
                        "LinkedSequence": {
                            "ObjectName": f"AnimSequence'{sequence_name}'",
                            "ObjectPath": f"{seq_pkg}.0"
                        }
                    }
                ],
                "SlotAnimTracks": [
                    {
                        "SlotName": "DefaultSlot",
                        "AnimTrack": {
                            "AnimSegments": [
                                {
                                    "AnimReference": {
                                        "ObjectName": f"AnimSequence'{sequence_name}'",
                                        "ObjectPath": f"{seq_pkg}.0"
                                    },
                                    "StartPos": 0.0,
                                    "AnimStartTime": 0.0,
                                    "AnimEndTime": float(anim_length),
                                    "AnimPlayRate": 1.0,
                                    "LoopingCount": 1
                                }
                            ]
                        }
                    }
                ],
                "Notifies": serialized_notifies,
                "SequenceLength": float(anim_length),
                "Skeleton": {
                    "ObjectName": f"Skeleton'SK_{mod_name}_Skeleton'",
                    "ObjectPath": f"{skel_pkg}.0"
                }
            },
            "SkeletonGuid": formatted_guid
        }
    ]
    return payload