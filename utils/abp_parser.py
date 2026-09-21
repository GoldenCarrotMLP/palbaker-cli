# utils/abp_parser.py
import os
import json

def identify_abp_json(workspace_dir: str) -> str | None:
    """
    Scans the workspace directory for any JSON file whose internal content
    matches an Unreal Engine Animation Blueprint signature.
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

    for root, _, files in os.walk(workspace_dir):
        for f in files:
            if not f.endswith(".json") or f in ignored_files or f.startswith("."):
                continue
            if f.endswith("_dynamic_pals.json") or f.endswith("_blend.json") or f.startswith("MI_"):
                continue

            full_path = os.path.join(root, f)
            try:
                # Read initial segment for fast signature verification
                with open(full_path, "r", encoding="utf-8-sig", errors="ignore") as file_in:
                    sample = file_in.read(16384)

                # Signature 1: FModel format
                is_fmodel_abp = (
                    "Class'AnimInstance'" in sample and 
                    "AnimBlueprintGeneratedClass" in sample
                )

                # Signature 2: UAssetGUI format
                is_uassetgui_abp = (
                    "AnimBlueprintGeneratedClass" in sample and 
                    ("AnimGraphNode_" in sample or "AnimNode_" in sample)
                )

                if is_fmodel_abp or is_uassetgui_abp:
                    print(f"[PalBaker ABP] Detected AnimBlueprint by content signature: {os.path.basename(full_path)}", flush=True)
                    return full_path

            except Exception:
                continue

    return None


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
    
    # Determine format and normalize to FModel-style flat dictionary
    if isinstance(raw, list) and len(raw) > 0:
        # FModel format
        props = raw[0].get("Properties", {})
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

    for key, val in props.items():
        if not isinstance(val, dict):
            continue

        # --- 1. SPRING BONE ---
        if key.startswith("AnimGraphNode_SpringBone"):
            bone_name = val.get("SpringBone", {}).get("BoneName", "")
            if bone_name:
                parsed["jiggle_bones"].append({
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
                })

        # --- 2. LOOK AT ---
        elif key.startswith("AnimGraphNode_LookAt"):
            bone_name = val.get("BoneToModify", {}).get("BoneName", "")
            target_bone = val.get("LookAtTarget", {}).get("BoneReference", {}).get("BoneName", "")
            
            if bone_name and target_bone:
                look_axis = val.get("LookAt_Axis", {}).get("Axis", {"X": 0.0, "Y": -1.0, "Z": 0.0})
                up_axis = val.get("LookUp_Axis", {}).get("Axis", {"X": 1.0, "Y": 0.0, "Z": 0.0})
                parsed["lookat_bones"].append({
                    "bone_name": bone_name,
                    "target_bone": target_bone,
                    "clamp": float(val.get("LookAtClamp", 50.0)),
                    "alpha": float(val.get("Alpha", 1.0)),
                    "look_at_axis": look_axis,
                    "look_up_axis": up_axis,
                    "abp_replicated": True
                })

        # --- 3. COPY BONE ---
        elif key.startswith("AnimGraphNode_CopyBone"):
            source_bone = val.get("SourceBone", {}).get("BoneName", "")
            target_bone = val.get("TargetBone", {}).get("BoneName", "")
            if source_bone and target_bone:
                parsed["copy_bones"].append({
                    "source_bone": source_bone,
                    "target_bone": target_bone,
                    "copy_translation": bool(val.get("bCopyTranslation", False)),
                    "copy_rotation": bool(val.get("bCopyRotation", False)),
                    "copy_scale": bool(val.get("bCopyScale", False)),
                    "alpha": float(val.get("Alpha", 1.0)),
                    "abp_replicated": True
                })

        # --- 4. MODIFY BONE ---
        elif key.startswith("AnimGraphNode_ModifyBone"):
            bone_name = val.get("BoneToModify", {}).get("BoneName", "")
            if bone_name:
                trans = val.get("Translation", {})
                rot = val.get("Rotation", {})
                scale = val.get("Scale", {})
                parsed["offset_bones"].append({
                    "bone_name": bone_name,
                    "translation": [float(trans.get("X", 0.0)), float(trans.get("Y", 0.0)), float(trans.get("Z", 0.0))],
                    "rotation": [float(rot.get("Roll", 0.0)), float(rot.get("Pitch", 0.0)), float(rot.get("Yaw", 0.0))],
                    "scale": [float(scale.get("X", 1.0)), float(scale.get("Y", 1.0)), float(scale.get("Z", 1.0))],
                    "abp_replicated": True
                })

    return parsed