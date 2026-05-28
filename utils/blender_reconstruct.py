import bpy
import sys
import os
import json

# Ensure utils package can be imported inside the headless Blender environment
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

import node_builder

def parse_args():
    """Parses command-line arguments passed after the double dash '--' in Blender."""
    args = []
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
    
    fbx_path = None
    blend_path = None
    for i, arg in enumerate(args):
        if arg == "--fbx" and i + 1 < len(args):
            fbx_path = args[i + 1]
        elif arg == "--output" and i + 1 < len(args):
            blend_path = args[i + 1]
    return fbx_path, blend_path

def fix_hierarchy():
    """Removes dummy Empties from UE FBX imports and secures the Armature name."""
    print("Cleaning up FBX hierarchy (removing dummy Empties)...")
    empties = [obj for obj in bpy.data.objects if obj.type == 'EMPTY']
    
    for empty in empties:
        children = list(empty.children)
        for child in children:
            world_mat = child.matrix_world.copy()
            child.parent = None
            child.matrix_world = world_mat
        
        bpy.data.objects.remove(empty, do_unlink=True)
        
    # FIXED: Named the Armature "root" to maintain single root bone compatibility in Unreal
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            obj.name = "root"
            obj.data.name = "root"

def reconstruct_materials(working_dir):
    """Reads metadata and calls the node_builder to construct materials."""
    meta_path = os.path.join(working_dir, "materials_metadata.json")
    if not os.path.exists(meta_path):
        print("No materials_metadata.json found. Skipping node generation.")
        return

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    for mat_name, data in metadata.items():
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            
        parent_class = data.get("parent_class", "")
        params = data.get("parameters", {})
        
        node_builder.build_material(mat, parent_class, params, working_dir)

def reconstruct_blend(fbx_path, blend_path):
    if not fbx_path or not os.path.exists(fbx_path):
        print(f"ERROR: FBX file not found at {fbx_path}")
        sys.exit(1)

    print("Resetting scene to empty factory defaults...")
    bpy.ops.wm.read_factory_settings(use_empty=True)

    print(f"Importing FBX: {fbx_path}")
    bpy.ops.import_scene.fbx(
        filepath=fbx_path,
        ignore_leaf_bones=True,
        global_scale=100.0
    )
    
    fix_hierarchy()
    
    working_dir = os.path.dirname(blend_path)
    reconstruct_materials(working_dir)

    print(f"Saving .blend file to: {blend_path}")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("BLEND Reconstruction Complete.")

if __name__ == "__main__":
    fbx, blend = parse_args()
    reconstruct_blend(fbx, blend)