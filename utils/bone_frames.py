# utils/bone_frames.py
"""Bone reference-frame math for carrying bone-local values from a template skeleton to a custom one.

Values copied from a template (LookAt axes, socket offsets, ...) are expressed in the template bone's
local frame. When the custom rig orients that bone differently (e.g. a 180 deg bone roll), the value must
be re-expressed in the custom bone's frame:  v_custom = R_custom^T * R_template * v_template,
with R = the bone's component-space rest rotation.

Frames are always in Unreal's convention. Pure Python: importable from Blender, Unreal and the CLI.
"""
import json
import math
import os
import re

# Blender -> UE: PalBaker's FBX export (axis_forward='-Z', axis_up='Y', default bone axes) plus the UE
# FBX importer mirror Y on both the global and the bone-local side. Verified against a cooked skeleton
# (59/59 bones): R_ue = F * R_blender * F,  pos_ue = F * pos_blender.
_F = ((1, 0, 0), (0, -1, 0), (0, 0, 1))
_IDENTITY_EPS = 1e-4


def norm_bone(name: str) -> str:
    """Bone names change separators between Blender and UE ('bone l mouth', 'bone_l_mouth', 'bone-l-mouth')."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


# --- matrix / quaternion helpers (3x3 row-major, quats as (x, y, z, w)) ------------------------------

def mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mat_t(a):
    return tuple(tuple(a[j][i] for j in range(3)) for i in range(3))


def mat_vec(a, v):
    return tuple(sum(a[i][k] * v[k] for k in range(3)) for i in range(3))


def quat_to_mat(q):
    x, y, z, w = q
    return ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
            (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
            (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))


def mat_to_quat(m):
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        q = (0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        q = ((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        q = ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s)
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def rotator_to_quat(roll, pitch, yaw):
    """FRotator::Quaternion (degrees)."""
    r, p, y = (math.radians(a) / 2 for a in (roll, pitch, yaw))
    sr, cr, sp, cp, sy, cy = math.sin(r), math.cos(r), math.sin(p), math.cos(p), math.sin(y), math.cos(y)
    return (cr * sp * sy - sr * cp * cy, -cr * sp * cy - sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def quat_to_rotator(q):
    """FQuat::Rotator -> (roll, pitch, yaw) in degrees."""
    x, y, z, w = q
    sing = z * x - w * y
    yaw = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
    if sing < -0.4999995:
        pitch = -90.0
        roll = -yaw - math.degrees(2 * math.atan2(x, w))
    elif sing > 0.4999995:
        pitch = 90.0
        roll = yaw - math.degrees(2 * math.atan2(x, w))
    else:
        pitch = math.degrees(math.asin(2 * sing))
        roll = math.degrees(math.atan2(-2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
    roll = (roll + 180.0) % 360.0 - 180.0
    return roll, pitch, yaw


# --- frame sources --------------------------------------------------------------------------------

def blender_rest_to_ue(world_rot3x3, world_pos):
    """Blender armature-space rest (matrix_world @ bone.matrix_local, scale stripped) -> UE component frame."""
    rot = mat_mul(mat_mul(_F, world_rot3x3), _F)
    return {"rot": list(mat_to_quat(rot)), "pos": list(mat_vec(_F, world_pos))}


def frames_from_reference_skeleton(ref: dict) -> dict:
    """CUE4Parse `ReferenceSkeleton` -> {norm_name: 3x3 component-space rotation}."""
    info, pose = ref["FinalRefBoneInfo"], ref["FinalRefBonePose"]
    quats, frames = [], {}
    for i, b in enumerate(info):
        r = pose[i]["Rotation"]
        q = (r["X"], r["Y"], r["Z"], r["W"])
        p = b["ParentIndex"]
        quats.append(q if p < 0 else quat_mul(quats[p], q))
        frames[norm_bone(b["Name"])] = quat_to_mat(quats[-1])
    return frames


def frames_from_sidecar(sidecar: dict) -> dict:
    """Sidecar `bone_rest_ue` -> {norm_name: 3x3 component-space rotation}."""
    return {norm_bone(n): quat_to_mat(tuple(v["rot"])) for n, v in (sidecar.get("bone_rest_ue") or {}).items()}


def load_template_frames(settings: dict, template_id: str, temp_dir: str) -> dict:
    """Extracts the vanilla template skeleton (CUE4Parse JSON) and returns its bone frames, or {}."""
    from utils.extractor.core import extract_game_files

    rel = f"Pal/Content/Pal/Model/Character/Skeleton/{template_id}/SK_{template_id}_Skeleton"
    out_dir = os.path.join(temp_dir, "template_skeleton_json")
    ok, _ = extract_game_files(settings, [f"{rel}.uasset"], out_dir, format_type="json")
    json_path = os.path.join(out_dir, *rel.split("/")) + ".json"
    if not ok or not os.path.exists(json_path):
        return {}
    with open(json_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    skel = next((o for o in data if o.get("Type") == "Skeleton"), None)
    return frames_from_reference_skeleton(skel["ReferenceSkeleton"]) if skel else {}


# --- remapping ------------------------------------------------------------------------------------

def bone_delta(bone: str, template_frames: dict, custom_frames: dict):
    """R_custom^T * R_template for `bone`, or None when either frame is unknown or they already agree."""
    key = norm_bone(bone)
    if key not in template_frames or key not in custom_frames:
        return None
    delta = mat_mul(mat_t(custom_frames[key]), template_frames[key])
    if all(abs(delta[i][j] - (1.0 if i == j else 0.0)) < _IDENTITY_EPS for i in range(3) for j in range(3)):
        return None
    return delta


def remap_vector(vec, delta):
    """Re-expresses a bone-local direction/offset (x, y, z) in the custom bone's frame."""
    out = mat_vec(delta, vec)
    return tuple(0.0 if abs(c) < 1e-6 else round(c, 6) for c in out)


def remap_axis(axis, delta):
    """Like remap_vector for unit axes: renormalizes and snaps rig float noise to clean axis values."""
    out = mat_vec(delta, axis)
    n = math.sqrt(sum(c * c for c in out)) or 1.0
    snapped = []
    for c in out:
        c /= n
        for target in (-1.0, 0.0, 1.0):
            if abs(c - target) < 1e-2:
                c = target
        snapped.append(c + 0.0)
    return tuple(snapped)


def remap_rotator(roll, pitch, yaw, delta):
    """Re-expresses a bone-local FRotator in the custom bone's frame. Returns (roll, pitch, yaw)."""
    rot = mat_mul(delta, quat_to_mat(rotator_to_quat(roll, pitch, yaw)))
    return tuple(round(a, 4) + 0.0 for a in quat_to_rotator(mat_to_quat(rot)))
