import bpy
import json
import sys
import os
import math
from mathutils import Matrix

current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

import image_combiner

def parse_args():
    args = []
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
    
    output_json = "bone_data.json"
    output_fbx = None
    for i, arg in enumerate(args):
        if arg == "--output" and i + 1 < len(args):
            output_json = args[i + 1]
        elif arg == "--fbx" and i + 1 < len(args):
            output_fbx = args[i + 1]
    return output_json, output_fbx

def get_node_image_name(link):
    if link and link[0].from_node.type == 'TEX_IMAGE' and link[0].from_node.image:
        return link[0].from_node.image.name.split(".")[0]
    return None

def extract_metadata(output_path: str):
    armature_obj = next((obj for obj in bpy.data.objects if obj.type == 'ARMATURE'), None)
    if not armature_obj:
        print("ERROR: No armature found.")
        sys.exit(1)
        
    working_dir = os.path.dirname(output_path)
    jiggle_bones = []
    offset_bones = []
    swap = Matrix(((1, 0, 0, 0), (0, -1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    
    for p_bone in armature_obj.pose.bones:
        raw_name = p_bone.name
        ue_bone_name = raw_name.replace('.', '_')
        
        if raw_name.endswith("_jiggle") or "_phy" in raw_name.lower():
            jiggle_bones.append({
                "bone_name": ue_bone_name, "spring_stiffness": 300.0, "spring_damping": 8.0,
                "max_displacement": 20.0, "error_reset_thresh": 1000.0, "limit_displacement": True,
                "translate_x": True, "translate_y": True, "translate_z": True,
                "rotate_x": True, "rotate_y": True, "rotate_z": True
            })
            
        loc, rot, scale = p_bone.matrix_basis.decompose()
        has_transform = (loc.length > 0.0001 or any(abs(v) > 0.0001 for v in rot.to_euler()) or any(abs(v - 1.0) > 0.0001 for v in scale))
        
        if has_transform:
            l_pose = p_bone.parent.matrix.inverted() @ p_bone.matrix if p_bone.parent else p_bone.matrix
            l_rest = p_bone.parent.bone.matrix_local.inverted() @ p_bone.bone.matrix_local if p_bone.parent else p_bone.bone.matrix_local
                
            delta_loc = l_pose.translation - l_rest.translation
            ue_translation = [round(delta_loc.x, 6), round(-delta_loc.y, 6), round(delta_loc.z, 6)]
            
            blender_delta_mat = l_pose @ l_rest.inverted()
            ue_delta_mat = swap @ blender_delta_mat @ swap
            _, rot_ue, _ = ue_delta_mat.decompose()
            rot_euler_ue = rot_ue.to_euler('XYZ')
            ue_rotation = [round(math.degrees(rot_euler_ue.x), 6), round(math.degrees(rot_euler_ue.y), 6), round(math.degrees(rot_euler_ue.z), 6)]
            
            ue_scale = [round(scale.x, 6), round(scale.y, 6), round(scale.z, 6)]
            
            offset_bones.append({
                "bone_name": ue_bone_name, "translation": ue_translation, "rotation": ue_rotation, "scale": ue_scale
            })

    # TOPOLOGY COMPILER (Replaces JSON heuristics)
    materials_compile = {}
    folder_name = os.path.basename(working_dir)

    for mat in bpy.data.materials:
        if not mat.use_nodes: continue
        out_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not out_node or not out_node.inputs['Surface'].links: continue
        
        bsdf = out_node.inputs['Surface'].links[0].from_node
        if bsdf.type != 'BSDF_PRINCIPLED': continue
        
        parent_class = "MI_PalLit_CharacterBodyBase"
        tex_base = tex_normal = tex_mrao = tex_sss = None
        
        # 1. Base Color
        base_link = bsdf.inputs['Base Color'].links
        if base_link:
            base_node = base_link[0].from_node
            if base_node.type == 'MIX':
                a_link = base_node.inputs['A'].links
                tex_base = get_node_image_name(a_link)
            elif base_node.type == 'TEX_IMAGE':
                parent_class = "MI_PalLit_CharacterEyeBase"
                tex_base = base_node.image.name.split(".")[0] if base_node.image else None
                
        # 2. Normal Map
        norm_link = bsdf.inputs['Normal'].links
        if norm_link and norm_link[0].from_node.type == 'NORMAL_MAP':
            tex_normal = get_node_image_name(norm_link[0].from_node.inputs['Color'].links)

        # 3. Subsurface
        sss_link = bsdf.inputs.get('Subsurface Radius')
        if sss_link and sss_link.links:
            tex_sss = get_node_image_name(sss_link.links)

        # 4. MRAO (Trigger Bake if required)
        met_link = bsdf.inputs['Metallic'].links
        if met_link and met_link[0].from_node.type == 'SEPARATE_COLOR':
            color_link = met_link[0].from_node.inputs['Color'].links
            if color_link:
                source_node = color_link[0].from_node
                if source_node.type == 'TEX_IMAGE' and source_node.image:
                    tex_mrao = source_node.image.name.split(".")[0]
                elif source_node.type == 'COMBINE_COLOR':
                    clean_mat_name = mat.name.replace("MI_", "")
                    out_filename = f"T_{folder_name}_{clean_mat_name}_M.png"
                    out_filepath = os.path.join(working_dir, out_filename)
                    
                    print(f"Baking Combine Color node to {out_filename}...")
                    tex_mrao = image_combiner.build_mrao_texture(source_node, out_filepath).split(".")[0]
                        
        materials_compile[mat.name] = {"parent_class": parent_class, "textures": {}}
        if tex_base: materials_compile[mat.name]["textures"]["Base Texture"] = tex_base
        if tex_normal: materials_compile[mat.name]["textures"]["Normal Map"] = tex_normal
        if tex_mrao: materials_compile[mat.name]["textures"]["MetallicRoughnessOcclusionSpecularTexture"] = tex_mrao
        if tex_sss: materials_compile[mat.name]["textures"]["Subsurface Texture"] = tex_sss

    # Write unified JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"jiggle_bones": jiggle_bones, "offset_bones": offset_bones, "materials": materials_compile}, f, indent=4)

    if "--fbx" in sys.argv:
        fbx_path = sys.argv[sys.argv.index("--fbx") + 1]
        print("Clearing pose transforms to Rest Pose...")
        for p_bone in armature_obj.pose.bones:
            p_bone.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        bpy.ops.export_scene.fbx(filepath=os.path.abspath(fbx_path), use_selection=False, add_leaf_bones=False, mesh_smooth_type='FACE', armature_nodetype='ROOT', global_scale=0.01, apply_scale_options='FBX_SCALE_ALL')

if __name__ == "__main__":
    out_json, _ = parse_args()
    extract_metadata(out_json)