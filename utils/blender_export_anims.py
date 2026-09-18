# utils/blender_export_anims.py
import bpy
import os
import sys
import re

def parse_args():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    output_fbx = None
    for i, arg in enumerate(args):
        if arg == "--output-fbx" and i + 1 < len(args):
            output_fbx = args[i + 1]
    return output_fbx

def export_animations_fbx(output_fbx: str):
    arm_obj = bpy.data.objects.get("Armature")
    if not arm_obj:
        print("[PalBaker Anims Export] Error: Armature not found in .blend file.", flush=True)
        sys.exit(1)

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    
    # Select both the Armature and Mesh objects so they export unified
    arm_obj.select_set(True)
    for obj in bpy.data.objects:
        if obj.type in {'ARMATURE', 'MESH'}:
            obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj

    # Unmute all NLA tracks
    original_mutes = {}
    if arm_obj.animation_data:
        for track in arm_obj.animation_data.nla_tracks:
            original_mutes[track.name] = track.mute
            track.mute = False

    for action in bpy.data.actions:
        action.use_fake_user = True

    os.makedirs(os.path.dirname(output_fbx), exist_ok=True)
    print(f"[PalBaker Anims Export] Baking {len(bpy.data.actions)} animation actions with mesh into {os.path.basename(output_fbx)}...", flush=True)

    # Export armature, mesh, and baked actions together into unified FBX
    bpy.ops.export_scene.fbx(
        filepath=os.path.abspath(output_fbx),
        use_selection=False,
        object_types={'ARMATURE', 'MESH'},
        bake_anim=True,
        bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=False,   # <-- Disables duplicate take generation
        bake_anim_use_all_actions=True,   # <-- Bakes each unique action once
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
        add_leaf_bones=False,
        mesh_smooth_type='FACE',
        armature_nodetype='ROOT',
        global_scale=0.01,
        apply_scale_options='FBX_SCALE_ALL'
    )

    if arm_obj.animation_data:
        for track in arm_obj.animation_data.nla_tracks:
            if track.name in original_mutes:
                track.mute = original_mutes[track.name]

    print("[PalBaker Anims Export] Animation FBX export completed successfully!", flush=True)

if __name__ == "__main__":
    fbx_target = parse_args()
    if fbx_target:
        export_animations_fbx(fbx_target)