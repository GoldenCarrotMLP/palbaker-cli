# utils/abp_parser.py
import os
import json

def identify_abp_json(workspace_dir: str) -> str | None:
    """
    Scans the workspace directory (and immediate parent character directory if this is a variant)
    for any JSON file whose internal content matches an Unreal Engine Animation Blueprint signature.
    Prioritizes rich ABP source definitions over auto-generated output files.
    """
    if not workspace_dir or not os.path.exists(workspace_dir):
        return None

    # Exclude known non-ABP metadata files
    ignored_files = {
        "import_config.json",
        ".palbaker_state.json",
        "materials_metadata.json",
        "bone_data.json"
    }

    candidates = []

    def scan_file(full_path: str, filename: str):
        if not filename.endswith(".json") or filename in ignored_files or filename.startswith("."):
            return
        if filename.endswith("_dynamic_pals.json") or filename.endswith("_blend.json") or filename.startswith("MI_"):
            return

        try:
            with open(full_path, "r", encoding="utf-8-sig", errors="ignore") as file_in:
                sample = file_in.read(32768)

            is_abp = (
                "AnimBlueprintGeneratedClass" in sample and
                ("AnimGraphNode_" in sample or "AnimNode_" in sample or "Class'AnimInstance'" in sample)
            )
            if not is_abp:
                return

            score = sample.count("AnimGraphNode_")
            if "AnimGraphNode_CopyBone" in sample:
                score += 15
            if "AnimGraphNode_ModifyBone" in sample:
                score += 15
            if filename.startswith("ABP_") or "JigglePhysics" in filename:
                score += 10
            if filename.endswith("_BP.json"):
                score -= 5

            candidates.append((score, full_path))
        except Exception:
            pass

    # 1. Search active workspace directory recursively (strictly within this pal's directory)
    for root, _, files in os.walk(workspace_dir):
        for f in files:
            scan_file(os.path.join(root, f), f)

    # 2. Only check the parent directory if workspace_dir is a nested child variant (e.g., Monster/BasePal/Variant).
    # Never check if the parent is the category directory (e.g., Monster/), as that would scan all other Pals!
    norm_path = os.path.normpath(workspace_dir).replace("\\", "/")
    parts = norm_path.split("/")
    if "Character" in parts:
        char_idx = parts.index("Character")
        # Structure: Character (idx) / Category (idx+1) / BasePal (idx+2) / Variant (idx+3+)
        if len(parts) > char_idx + 3:
            parent = os.path.dirname(workspace_dir)
            category_names = {"monster", "pending monster", "player", "npc", "boss", "palmi", "normal", "raidmonster", "raidboss"}
            if parent and os.path.exists(parent) and os.path.basename(parent).lower() not in category_names:
                for f in os.listdir(parent):
                    full_p = os.path.join(parent, f)
                    if os.path.isfile(full_p):
                        scan_file(full_p, f)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def _normalize_uassetgui_value(val):
    """Recursively unwraps UAssetAPI list-of-structs into clean FModel-style dictionaries."""
    if isinstance(val, list):
        if len(val) > 0 and all(isinstance(x, dict) and "Name" in x for x in val):
            res = {}
            for item in val:
                name = item["Name"]
                inner_val = item.get("Value")
                
                # Unwrap double-nested structs (e.g. Axis -> [Axis -> {X, Y, Z}])
                if isinstance(inner_val, list) and len(inner_val) == 1 and isinstance(inner_val[0], dict) and inner_val[0].get("Name") == name:
                    inner_val = inner_val[0].get("Value")
                    
                res[name] = _normalize_uassetgui_value(inner_val)
            return res
        else:
            return [_normalize_uassetgui_value(x) for x in val]
    elif isinstance(val, dict):
        res = {}
        for k, v in val.items():
            if k == "$type": continue  # Strip UAssetAPI metadata
            res[k] = _normalize_uassetgui_value(v)
        return res
    elif isinstance(val, str):
        if val in ["+0", "-0"]: 
            return 0.0
    return val


def parse_abp_nodes(json_path: str) -> dict:
    """
    Extracts SpringBone, LookAt, CopyBone, and ModifyBone parameters from
    either FModel or UAssetGUI JSON structures.
    """
    with open(json_path, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)

    props = {}
    
    # Determine format and normalize to flat dictionary
    if isinstance(raw, list):
        # FModel format: scan ALL exported objects (especially the CDO Default__... where nodes live)
        for obj in raw:
            if isinstance(obj, dict):
                obj_props = obj.get("Properties", {})
                if isinstance(obj_props, dict):
                    for k, v in obj_props.items():
                        if k.startswith("AnimGraphNode_"):
                            props[k] = v
    elif isinstance(raw, dict):
        if "Properties" in raw:
            # FModel format (single object)
            props = raw["Properties"]
        elif "Exports" in raw:
            # UAssetGUI format
            for exp in raw["Exports"]:
                for prop in exp.get("Data", []):
                    p_name = prop.get("Name", "")
                    if p_name.startswith("AnimGraphNode_"):
                        # Normalize UAssetGUI's array of dicts into a clean dict
                        props[p_name] = _normalize_uassetgui_value(prop.get("Value", []))

    parsed = {
        "jiggle_bones": [],
        "lookat_bones": [],
        "copy_bones": [],
        "offset_bones": []
    }

    def _parse_clamp(val_dict):
        clamp_raw = val_dict.get("AlphaScaleBiasClamp")
        if not isinstance(clamp_raw, dict):
            return None
        in_range = clamp_raw.get("InRange", {})
        out_range = clamp_raw.get("OutRange", {})
        return {
            "b_map_range": bool(clamp_raw.get("bMapRange", False)),
            "b_clamp_result": bool(clamp_raw.get("bClampResult", False)),
            "b_interp_result": bool(clamp_raw.get("bInterpResult", False)),
            "scale": float(clamp_raw.get("Scale", 1.0)),
            "bias": float(clamp_raw.get("Bias", 0.0)),
            "clamp_min": float(clamp_raw.get("ClampMin", 0.0)),
            "clamp_max": float(clamp_raw.get("ClampMax", 1.0)),
            "interp_speed_increasing": float(clamp_raw.get("InterpSpeedIncreasing", 10.0)),
            "interp_speed_decreasing": float(clamp_raw.get("InterpSpeedDecreasing", 10.0)),
            "in_range": {
                "min": float(in_range.get("Min", 0.0)),
                "max": float(in_range.get("Max", 1.0))
            },
            "out_range": {
                "min": float(out_range.get("Min", 0.0)),
                "max": float(out_range.get("Max", 1.0))
            }
        }

    for key, val in props.items():
        if not isinstance(val, dict):
            continue

        # --- 1. SPRING BONE ---
        if key.startswith("AnimGraphNode_SpringBone"):
            bone_name = val.get("SpringBone", {}).get("BoneName", "")
            if bone_name:
                clamp_data = _parse_clamp(val)
                bone_entry = {
                    "bone_name": bone_name,
                    "spring_stiffness": float(val.get("SpringStiffness", 200.0)),
                    "spring_damping": float(val.get("SpringDamping", 8.0)),
                    "max_displacement": float(val.get("MaxDisplacement", 0.0)),
                    "error_reset_thresh": float(val.get("ErrorResetThresh", 256.0)),
                    "limit_displacement": bool(val.get("bLimitDisplacement", False)),
                    "translate_x": bool(val.get("bTranslateX", True)),
                    "translate_y": bool(val.get("bTranslateY", True)),
                    "translate_z": bool(val.get("bTranslateZ", True)),
                    "rotate_x": bool(val.get("bRotateX", False)),
                    "rotate_y": bool(val.get("bRotateY", False)),
                    "rotate_z": bool(val.get("bRotateZ", False)),
                    "alpha": float(val.get("Alpha", 1.0)),
                    "abp_replicated": True
                }
                if clamp_data:
                    bone_entry["alpha_scale_bias_clamp"] = clamp_data
                parsed["jiggle_bones"].append(bone_entry)

        # --- 2. LOOK AT ---
        elif key.startswith("AnimGraphNode_LookAt"):
            bone_name = val.get("BoneToModify", {}).get("BoneName", "")
            target_bone = val.get("LookAtTarget", {}).get("BoneReference", {}).get("BoneName", "")
            
            if bone_name and target_bone:
                look_axis = val.get("LookAt_Axis", {}).get("Axis", {"X": 0.0, "Y": -1.0, "Z": 0.0})
                up_axis = val.get("LookUp_Axis", {}).get("Axis", {"X": 1.0, "Y": 0.0, "Z": 0.0})
                clamp_data = _parse_clamp(val)
                bone_entry = {
                    "bone_name": bone_name,
                    "target_bone": target_bone,
                    "clamp": float(val.get("LookAtClamp", 50.0)),
                    "alpha": float(val.get("Alpha", 1.0)),
                    "look_at_axis": look_axis,
                    "look_up_axis": up_axis,
                    "abp_replicated": True
                }
                if clamp_data:
                    bone_entry["alpha_scale_bias_clamp"] = clamp_data
                parsed["lookat_bones"].append(bone_entry)

        # --- 3. COPY BONE ---
        elif key.startswith("AnimGraphNode_CopyBone"):
            source_bone = val.get("SourceBone", {}).get("BoneName", "")
            target_bone = val.get("TargetBone", {}).get("BoneName", "")
            if source_bone and target_bone:
                clamp_data = _parse_clamp(val)
                bone_entry = {
                    "source_bone": source_bone,
                    "target_bone": target_bone,
                    "copy_translation": bool(val.get("bCopyTranslation", False)),
                    "copy_rotation": bool(val.get("bCopyRotation", False)),
                    "copy_scale": bool(val.get("bCopyScale", False)),
                    "control_space": str(val.get("ControlSpace", "BCS_ComponentSpace")),
                    "alpha": float(val.get("Alpha", 1.0)),
                    "abp_replicated": True
                }
                if clamp_data:
                    bone_entry["alpha_scale_bias_clamp"] = clamp_data
                parsed["copy_bones"].append(bone_entry)

        # --- 4. MODIFY BONE ---
        elif key.startswith("AnimGraphNode_ModifyBone"):
            bone_name = val.get("BoneToModify", {}).get("BoneName", "")
            if bone_name:
                trans = val.get("Translation", {})
                rot = val.get("Rotation", {})
                scale = val.get("Scale", {})
                clamp_data = _parse_clamp(val)

                bone_entry = {
                    "bone_name": bone_name,
                    "translation": [float(trans.get("X", 0.0)), float(trans.get("Y", 0.0)), float(trans.get("Z", 0.0))],
                    "rotation": [float(rot.get("Roll", 0.0)), float(rot.get("Pitch", 0.0)), float(rot.get("Yaw", 0.0))],
                    "scale": [float(scale.get("X", 1.0)), float(scale.get("Y", 1.0)), float(scale.get("Z", 1.0))],
                    "translation_mode": str(val.get("TranslationMode", "BMM_Additive")),
                    "rotation_mode": str(val.get("RotationMode", "BMM_Ignore")),
                    "scale_mode": str(val.get("ScaleMode", "BMM_Ignore")),
                    "translation_space": str(val.get("TranslationSpace", "BCS_ComponentSpace")),
                    "rotation_space": str(val.get("RotationSpace", "BCS_ComponentSpace")),
                    "scale_space": str(val.get("ScaleSpace", "BCS_ComponentSpace")),
                    "alpha": float(val.get("Alpha", 1.0)),
                    "abp_replicated": True
                }
                if clamp_data:
                    bone_entry["alpha_scale_bias_clamp"] = clamp_data
                parsed["offset_bones"].append(bone_entry)

    return parsed