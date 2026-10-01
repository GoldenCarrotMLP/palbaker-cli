# utils/blender_reconstruct.py
import sys
import os
import json
import re
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

def remap_mesh_materials_to_target(working_dir: str, blend_path: str):
    """
    If the imported mesh (e.g. from an extracted template PSK) contains material slots 
    referencing the parent template (e.g. MI_BlackPuppy_Body), this renames the Blender 
    materials and slots to match the local target Pal's material instances (e.g. MI_Emberpup_Body).
    """
    mod_name = os.path.splitext(os.path.basename(blend_path))[0]
    local_mis = [
        os.path.splitext(f)[0] 
        for f in os.listdir(working_dir) 
        if (f.startswith("MI_") or f.startswith("M_")) and f.endswith(".json") and not f.endswith("_blend.json")
    ]
    if not local_mis:
        return

    # Check for creator JSON to identify parent template ID
    template_id = None
    creator_candidates = [
        os.path.join(working_dir, f"{mod_name}_creator.json"),
        os.path.join(os.path.dirname(working_dir), f"{mod_name}_creator.json")
    ]
    fmodel_root = working_dir
    parts = os.path.normpath(working_dir).replace("\\", "/").split("/")
    if "Exports" in parts:
        exp_idx = parts.index("Exports")
        fmodel_root = "/".join(parts[:exp_idx])
        creator_candidates.append(os.path.join(fmodel_root, "Exports", "Pal", "Content", "Palbaker", "Creator", f"{mod_name}_creator.json"))

    for cp in creator_candidates:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f_cr:
                    template_id = json.load(f_cr).get("TemplateID")
                    if template_id:
                        break
            except Exception:
                pass

    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    for obj in mesh_objs:
        for slot in obj.material_slots:
            mat = slot.material
            if not mat:
                continue

            mat_name = mat.name.split(".")[0]
            if mat_name in local_mis:
                continue

            target_name = None
            # Strategy A: Direct template name replacement
            if template_id and template_id.lower() in mat_name.lower():
                pattern = re.compile(re.escape(template_id), re.IGNORECASE)
                candidate = pattern.sub(mod_name, mat_name)
                if candidate in local_mis:
                    target_name = candidate

            # Strategy B: Suffix / Role matching (e.g. Body, Eye, Mouth, Extra)
            if not target_name:
                clean_mat = re.sub(r'^(?:MI_|M_)', '', mat_name, flags=re.IGNORECASE)
                mat_suffix = clean_mat.split('_', 1)[-1].lower() if '_' in clean_mat else clean_mat.lower()
                for lmi in local_mis:
                    clean_lmi = re.sub(r'^(?:MI_|M_)', '', lmi, flags=re.IGNORECASE)
                    lmi_suffix = clean_lmi.split('_', 1)[-1].lower() if '_' in clean_lmi else clean_lmi.lower()
                    if mat_suffix == lmi_suffix:
                        target_name = lmi
                        break

            if target_name:
                print(f"[Blender Reconstruct] Remapping mesh material '{mat.name}' -> '{target_name}'", flush=True)
                existing_mat = bpy.data.materials.get(target_name)
                if existing_mat:
                    slot.material = existing_mat
                else:
                    mat.name = target_name

def reconstruct_materials(working_dir):
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
        if mat_name.lower() == "material" or "dots stroke" in mat_name.lower() or mat_name.startswith("."):
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
            if mat_name.lower() == "material" or "dots stroke" in mat_name.lower() or mat_name.startswith("."):
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

                # Default to proper parent class instead of mat_name
                parent_class = "CharacterBodyBase"
                lower_m = mat_name.lower()
                if "eye" in lower_m or "mouth" in lower_m:
                    parent_class = "CharacterEyeBase"
                elif "hair" in lower_m:
                    parent_class = "CharacterHairBase"
                
                node_builder.build_material(mat_name, parent_class, params, working_dir)
    else:
        node_builder.build_materials_heuristically(working_dir)

def apply_replicated_constraints(sidecar_path: str, armature_name: str = "Armature"):
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
        else:
            counts["skipped_missing_bones"] += 1

    # 2. Apply Copy Constraints (Location / Rotation / Scale)
    copy_list = data.get("copy_bones", [])
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

            if entry.get("copy_rotation"):
                c_rot = t_bone.constraints.get("PalBaker_CopyRotation") or t_bone.constraints.new('COPY_ROTATION')
                c_rot.name = "PalBaker_CopyRotation"
                c_rot.target = arm_obj
                c_rot.subtarget = s_bone.name
                c_rot.target_space = 'POSE'
                c_rot.owner_space = 'POSE'
                c_rot.influence = alpha_val
                counts["copy_rotation"] += 1

            if entry.get("copy_scale"):
                c_scale = t_bone.constraints.get("PalBaker_CopyScale") or t_bone.constraints.new('COPY_SCALE')
                c_scale.name = "PalBaker_CopyScale"
                c_scale.target = arm_obj
                c_scale.subtarget = s_bone.name
                c_scale.target_space = 'POSE'
                c_scale.owner_space = 'POSE'
                c_scale.influence = alpha_val
                counts["copy_scale"] += 1

            t_bone["abp_replicated"] = True
        else:
            counts["skipped_missing_bones"] += 1

    # 3. Tag Spring Bones
    for entry in data.get("jiggle_bones", []):
        b_name = entry.get("bone_name", "")
        p_bone = pose_bones.get(b_name) or pose_bones_ci.get(b_name.lower())
        if p_bone:
            p_bone["abp_replicated"] = True
            counts["jiggle_tagged"] += 1

    bpy.ops.object.mode_set(mode='OBJECT')

def reconstruct_blend(input_path, blend_path, sidecar_path=None):
    if not input_path or not os.path.exists(input_path):
        print(f"ERROR: Input mesh file not found at {input_path}")
        sys.exit(1)

    input_path = os.path.abspath(input_path).replace("\\", "/")
    blend_path = os.path.abspath(blend_path).replace("\\", "/")

    print("Clearing default scene objects...")
    translator.clean_scene()

    print(f"Importing mesh file: {input_path}")
    translator.import_mesh(input_path)
    
    translator.fix_hierarchy("Armature")
    
    working_dir = os.path.dirname(blend_path).replace("\\", "/")
    remap_mesh_materials_to_target(working_dir, blend_path)
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