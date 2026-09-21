# utils/blender_reconstruct.py
import sys
import os
import json
import bpy
from mathutils import Matrix, Euler

current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from blender_utils import translator
import node_builder
from fmodel_helper import resolve_and_copy_material_json

def parse_args():
    args = []
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
    
    fbx_path = None
    blend_path = None
    sidecar_path = None
    for i, arg in enumerate(args):
        if arg == "--fbx" and i + 1 < len(args):
            fbx_path = args[i + 1]
        elif arg == "--output" and i + 1 < len(args):
            blend_path = args[i + 1]
        elif arg == "--sidecar" and i + 1 < len(args):
            sidecar_path = args[i + 1]
    return fbx_path, blend_path, sidecar_path

def reconstruct_materials(working_dir):
    """
    Constructs materials loaded into Blender. If materials are missing configurations 
    locally, it performs a search across FModel folders to resolve dependencies dynamically.
    """
    fmodel_root = working_dir
    parts = os.path.normpath(working_dir).replace("\\", "/").split("/")
    
    if "Exports" in parts:
        exp_idx = parts.index("Exports")
        fmodel_root = "/".join(parts[:exp_idx])
    
    meta_path = os.path.join(working_dir, "materials_metadata.json")
    
    metadata = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load local materials_metadata: {e}")

    active_materials = translator.get_skeletal_mesh_material_slots()
    print(f"Discovered active mesh materials in Blender: {active_materials}")

    updated_meta = False

    for mat_name in active_materials:
        if mat_name.lower() == "material":
            continue
            
        clean_name = mat_name.split(".")[0]
        
        if clean_name not in metadata:
            print(f"Missing local configuration for '{clean_name}'. Executing dynamic search...", flush=True)
            resolved = resolve_and_copy_material_json(clean_name, working_dir, fmodel_root)
            if resolved:
                metadata[clean_name] = resolved
                updated_meta = True

    if updated_meta:
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
        except Exception as e:
            print(f"Warning: Failed to write updated materials_metadata: {e}")

    if metadata:
        for mat_name in active_materials:
            if mat_name.lower() == "material":
                continue
                
            clean_name = mat_name.split(".")[0]
            data = metadata.get(clean_name)
            if data:
                parent_class = data.get("parent_class", "")
                params = data.get("parameters", {})
                node_builder.build_material(mat_name, parent_class, params, working_dir)
            else:
                print(f"Warning: No mapping resolved for '{mat_name}', running suffix fallback...")
                textures = [os.path.join(working_dir, f).replace("\\", "/") for f in os.listdir(working_dir) if f.endswith(".png")]
                tex_base = node_builder.find_best_texture_match(mat_name, textures, "B")
                tex_norm = node_builder.find_best_texture_match(mat_name, textures, "N")
                tex_mrao = node_builder.find_best_texture_match(mat_name, textures, "M")
                tex_em = node_builder.find_best_texture_match(mat_name, textures, "EM")
                
                params = {}
                if tex_base: params["Base Texture"] = tex_base
                if tex_norm: params["Normal Map"] = tex_norm
                if tex_mrao: params["MetallicRoughnessOcclusionSpecularTexture"] = tex_mrao
                if tex_em: params["Emissive Texture"] = tex_em
                
                node_builder.build_material(mat_name, mat_name, params, working_dir)
    else:
        node_builder.build_materials_heuristically(working_dir)

def apply_replicated_constraints(sidecar_path: str, armature_name: str = "Armature"):
    """
    Applies Damped Track, Copy Location, and Copy Rotation constraints
    with verbose diagnostic logging per constraint type.
    """
    print(f"\n[Blender Constraints] Scanning sidecar for replicated constraints: {sidecar_path}", flush=True)
    
    if not os.path.exists(sidecar_path):
        print(f"[Blender Constraints] ❌ Aborted: Sidecar file does not exist at {sidecar_path}", flush=True)
        return

    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Blender Constraints] ❌ Error reading sidecar JSON: {e}", flush=True)
        return

    if not data.get("has_replicated_abp"):
        print(f"[Blender Constraints] ℹ️ Notice: 'has_replicated_abp' is False or missing. Skipping constraint generation.", flush=True)
        return

    arm_obj = bpy.data.objects.get(armature_name)
    if not arm_obj or arm_obj.type != 'ARMATURE':
        print(f"[Blender Constraints] ❌ Error: Armature '{armature_name}' not found in active scene.", flush=True)
        return

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='POSE')
    pose_bones = arm_obj.pose.bones

    # Case-insensitive map to prevent casing mismatches (e.g. Breast vs breast)
    pose_bones_ci = {b.name.lower(): b for b in pose_bones}

    counts = {
        "damped_track": 0,
        "copy_location": 0,
        "copy_rotation": 0,
        "copy_scale": 0,
        "jiggle_tagged": 0,
        "skipped_missing_bones": 0
    }

    # 1. Apply LookAt Constraints (Damped Track)
    lookat_list = data.get("lookat_bones", [])
    print(f"[Blender Constraints] Processing {len(lookat_list)} LookAt bone targets...", flush=True)
    
    for entry in lookat_list:
        b_name = entry.get("bone_name", "")
        t_name = entry.get("target_bone", "")

        p_bone = pose_bones.get(b_name) or pose_bones_ci.get(b_name.lower())
        t_bone = pose_bones.get(t_name) or pose_bones_ci.get(t_name.lower())

        if p_bone and t_bone:
            c = p_bone.constraints.get("PalBaker_LookAt") or p_bone.constraints.new('DAMPED_TRACK')
            c.name = "PalBaker_LookAt"
            c.target = arm_obj
            c.subtarget = t_bone.name
            c.track_axis = 'TRACK_Y'
            c.influence = float(entry.get("alpha", 1.0))
            p_bone["abp_replicated"] = True
            counts["damped_track"] += 1
            print(f"  ✓ Added Damped Track: {p_bone.name} -> {t_bone.name} (Influence: {c.influence})", flush=True)
        else:
            counts["skipped_missing_bones"] += 1
            missing = []
            if not p_bone: missing.append(f"Source '{b_name}'")
            if not t_bone: missing.append(f"Target '{t_name}'")
            print(f"  ⚠️ Skipped LookAt: {', '.join(missing)} not found in armature.", flush=True)

    # 2. Apply Copy Constraints (Location / Rotation / Scale)
    copy_list = data.get("copy_bones", [])
    print(f"[Blender Constraints] Processing {len(copy_list)} CopyBone targets...", flush=True)
    
    for entry in copy_list:
        t_name = entry.get("target_bone", "")
        s_name = entry.get("source_bone", "")

        t_bone = pose_bones.get(t_name) or pose_bones_ci.get(t_name.lower())
        s_bone = pose_bones.get(s_name) or pose_bones_ci.get(s_name.lower())

        if t_bone and s_bone:
            alpha_val = float(entry.get("alpha", 1.0))

            if entry.get("copy_translation"):
                c_loc = t_bone.constraints.get("PalBaker_CopyLocation") or t_bone.constraints.new('COPY_LOCATION')
                c_loc.name = "PalBaker_CopyLocation"
                c_loc.target = arm_obj
                c_loc.subtarget = s_bone.name
                c_loc.target_space = 'POSE'
                c_loc.owner_space = 'POSE'
                c_loc.influence = alpha_val
                counts["copy_location"] += 1
                print(f"  ✓ Added Copy Location: {t_bone.name} <- {s_bone.name}", flush=True)

            if entry.get("copy_rotation"):
                c_rot = t_bone.constraints.get("PalBaker_CopyRotation") or t_bone.constraints.new('COPY_ROTATION')
                c_rot.name = "PalBaker_CopyRotation"
                c_rot.target = arm_obj
                c_rot.subtarget = s_bone.name
                c_rot.target_space = 'POSE'
                c_rot.owner_space = 'POSE'
                c_rot.influence = alpha_val
                counts["copy_rotation"] += 1
                print(f"  ✓ Added Copy Rotation: {t_bone.name} <- {s_bone.name}", flush=True)

            if entry.get("copy_scale"):
                c_scale = t_bone.constraints.get("PalBaker_CopyScale") or t_bone.constraints.new('COPY_SCALE')
                c_scale.name = "PalBaker_CopyScale"
                c_scale.target = arm_obj
                c_scale.subtarget = s_bone.name
                c_scale.target_space = 'POSE'
                c_scale.owner_space = 'POSE'
                c_scale.influence = alpha_val
                counts["copy_scale"] += 1
                print(f"  ✓ Added Copy Scale: {t_bone.name} <- {s_bone.name}", flush=True)

            t_bone["abp_replicated"] = True
        else:
            counts["skipped_missing_bones"] += 1
            missing = []
            if not t_bone: missing.append(f"Target '{t_name}'")
            if not s_bone: missing.append(f"Source '{s_name}'")
            print(f"  ⚠️ Skipped CopyBone: {', '.join(missing)} not found in armature.", flush=True)

    # 3. Tag Spring Bones
    for entry in data.get("jiggle_bones", []):
        b_name = entry.get("bone_name", "")
        p_bone = pose_bones.get(b_name) or pose_bones_ci.get(b_name.lower())
        if p_bone:
            p_bone["abp_replicated"] = True
            counts["jiggle_tagged"] += 1

    bpy.ops.object.mode_set(mode='OBJECT')

    print("\n" + "=" * 55, flush=True)
    print("=== PALBAKER BLENDER CONSTRAINTS SUMMARY ===", flush=True)
    print(f"  • Damped Track (LookAt) Added: {counts['damped_track']}", flush=True)
    print(f"  • Copy Location Added:        {counts['copy_location']}", flush=True)
    print(f"  • Copy Rotation Added:        {counts['copy_rotation']}", flush=True)
    print(f"  • Copy Scale Added:           {counts['copy_scale']}", flush=True)
    print(f"  • Spring Target Bones Tagged: {counts['jiggle_tagged']}", flush=True)
    if counts["skipped_missing_bones"] > 0:
        print(f"  • Skipped Unmatched Bones:    {counts['skipped_missing_bones']}", flush=True)
    print("=" * 55 + "\n", flush=True)


def reconstruct_blend(input_path, blend_path, sidecar_path=None):
    if not input_path or not os.path.exists(input_path):
        print(f"ERROR: Input mesh file not found at {input_path}")
        sys.exit(1)

    input_path = os.path.abspath(input_path).replace("\\", "/")
    blend_path = os.path.abspath(blend_path).replace("\\", "/")

    if os.name == 'nt':
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            ext_path = os.path.join(appdata, "Blender Foundation", "Blender", "5.1", "extensions")
            if os.path.exists(ext_path) and ext_path not in sys.path:
                sys.path.append(ext_path)

    print("Clearing default scene objects...")
    translator.clean_scene()

    print(f"Importing mesh file: {input_path}")
    translator.import_mesh(input_path)
    
    translator.fix_hierarchy("Armature")
    
    working_dir = os.path.dirname(blend_path).replace("\\", "/")
    reconstruct_materials(working_dir)

    if not sidecar_path:
        mod_name = os.path.splitext(os.path.basename(blend_path))[0]
        sidecar_path = os.path.join(working_dir, f"{mod_name}_blend.json")

    apply_replicated_constraints(sidecar_path, "Armature")

    print(f"Saving .blend file to: {blend_path}")
    translator.save_blend(blend_path)
    print("BLEND Reconstruction Complete.")

if __name__ == "__main__":
    fbx, blend, sidecar = parse_args()
    reconstruct_blend(fbx, blend, sidecar)