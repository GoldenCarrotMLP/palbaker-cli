import os
import sys
import json
import math
import random

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)

from utils.bone_frames import (
    blender_rest_to_ue, frames_from_sidecar, frames_from_reference_skeleton, bone_delta,
    remap_axis, remap_vector, remap_rotator, rotator_to_quat, quat_to_rotator, quat_to_mat, mat_mul, mat_vec,
)

def log(msg, cat="INFO"):
    print(f"[{cat}] {msg}", flush=True)

def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))

def main():
    """Bone frame remapping. Optional calibration against a real rig:
    python test_19_bone_frames.py <sidecar *_blend.json> <CUE4Parse JSON of the same pal's cooked skeleton>
    """
    log("=== PalBaker Bone Frame Remapping Test ===")
    failures = 0

    # A vanilla-style head (local +Y forward, +X up) and a custom head rolled 180 deg about its up axis.
    template = {"head": ((0, 0, -1), (0, 1, 0), (1, 0, 0))}   # columns: localX->+Z(up), localY->+Y, localZ->-X
    custom = {"head": ((0, 0, 1), (0, -1, 0), (1, 0, 0))}     # columns: localX->+Z(up), localY->-Y, localZ->+X
    delta = bone_delta("head", template, custom)

    if remap_axis((0, 1, 0), delta) != (0.0, -1.0, 0.0):
        log("LookAt axis was not flipped for a 180-deg rolled head", "FAIL"); failures += 1
    if remap_axis((1, 0, 0), delta) != (1.0, 0.0, 0.0):
        log("LookUp axis should be unchanged (shared up axis)", "FAIL"); failures += 1

    loc, rot = (-8.476198, 26.719135, 0.0), (-90.0, 0.0, 90.0)
    new_loc, new_rot = remap_vector(loc, delta), remap_rotator(*rot, delta)
    if not close(mat_vec(template["head"], loc), mat_vec(custom["head"], new_loc)):
        log("Socket offset does not keep its mesh-space position", "FAIL"); failures += 1
    mt = mat_mul(template["head"], quat_to_mat(rotator_to_quat(*rot)))
    mc = mat_mul(custom["head"], quat_to_mat(rotator_to_quat(*new_rot)))
    if not close(sum(mt, ()), sum(mc, ())):
        log("Socket rotation does not keep its mesh-space orientation", "FAIL"); failures += 1

    if bone_delta("head", template, template) is not None or bone_delta("missing", template, custom) is not None:
        log("Identical or unknown bones must not be remapped", "FAIL"); failures += 1
    if bone_delta("Head", template, {"head": custom["head"]}) is None:
        log("Bone names should match across separator/case differences", "FAIL"); failures += 1

    rnd = random.Random(19)
    for _ in range(2000):
        r = (rnd.uniform(-180, 180), rnd.uniform(-89, 89), rnd.uniform(-180, 180))
        if not close(sum(quat_to_mat(rotator_to_quat(*r)), ()), sum(quat_to_mat(rotator_to_quat(*quat_to_rotator(rotator_to_quat(*r)))), ()), 1e-6):
            log(f"Rotator round trip failed for {r}", "FAIL"); failures += 1
            break

    # Optional: prove the Blender->UE convention against a cooked skeleton
    if len(sys.argv) == 3:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            side = frames_from_sidecar(json.load(f))
        with open(sys.argv[2], "r", encoding="utf-8-sig") as f:
            ref = next(o for o in json.load(f) if o.get("Type") == "Skeleton")["ReferenceSkeleton"]
        cooked = frames_from_reference_skeleton(ref)
        common = set(side) & set(cooked)
        worst = max((max(abs(side[k][i][j] - cooked[k][i][j]) for i in range(3) for j in range(3)), k) for k in common)
        log(f"Calibration: {len(common)} bones compared, worst element error {worst[0]:.4f} ({worst[1]})")
        if not common or worst[0] > 0.05:
            log("Sidecar bone_rest_ue does not match the cooked skeleton (Blender->UE convention changed?)", "FAIL"); failures += 1

    if failures:
        log(f"{failures} check(s) failed", "FAIL")
        sys.exit(1)
    log("All bone frame checks passed", "PASS")

if __name__ == "__main__":
    main()
