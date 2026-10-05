# utils/blender_export_anims.py
import bpy
import os
import sys
import re

def clean_to_track_name(name: str, base_pal: str = "", mod_name: str = "") -> str:
    clean = name.split("'")[-2] if "'" in name else name
    clean = clean.split("/")[-1].split(".")[0]
    
    m = re.match(r'^BS_([a-zA-Z]+)_[a-zA-Z0-9]+(?:_(.+))?$', clean)
    if m: clean = f"{m.group(1)}_{m.group(2)}" if m.group(2) else m.group(1)
    elif clean.startswith("BS_"): clean = clean[3:]
    else:
        m = re.match(r'^(?:BP_Action_Unique|BP_UniqueAction)_[a-zA-Z0-9]+?_(.+)$', clean)
        if m: clean = m.group(1)

    prefixes = []
    if mod_name: prefixes.extend([f"AM_{mod_name}_", f"AS_{mod_name}_", f"{mod_name}_"])
    if base_pal: prefixes.extend([f"AM_{base_pal}_", f"AS_{base_pal}_", f"{base_pal}_"])
    prefixes.extend(["Armature_", "Anim_Armature_", "AM_", "AS_"])
    prefixes.sort(key=len, reverse=True)

    changed = True
    while changed:
        changed = False
        for pfx in prefixes:
            if clean.lower().startswith(pfx.lower()):
                clean = clean[len(pfx):]
                changed = True
                break

    return clean

def parse_args():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    output_dir = None
    mod_name = ""
    base_pal = ""
    for i, arg in enumerate(args):
        if arg == "--output-dir" and i + 1 < len(args):
            output_dir = args[i + 1]
        elif arg == "--mod-name" and i + 1 < len(args):
            mod_name = args[i + 1]
        elif arg == "--base-pal" and i + 1 < len(args):
            base_pal = args[i + 1]
    return output_dir, mod_name, base_pal

def export_individual_animations(output_dir: str, mod_name: str, base_pal: str):
    arm_obj = bpy.data.objects.get("Armature")
    if not arm_obj or arm_obj.type != 'ARMATURE':
        print("[PalBaker Anims Export] Error: Armature not found in .blend file.", flush=True)
        sys.exit(1)

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj

    if not arm_obj.animation_data:
        arm_obj.animation_data_create()

    # Mute all NLA tracks so they do not blend with the active action
    for track in arm_obj.animation_data.nla_tracks:
        track.mute = True

    # 1. Harvest unique actions from NLA strips and bpy.data.actions
    actions_map = {}
    
    for track in arm_obj.animation_data.nla_tracks:
        if track.name.startswith(".") or "[action stash]" in track.name.lower():
            continue
        if track.name.upper().startswith("AM_"):
            continue
        for strip in track.strips:
            if strip.action:
                if strip.action.name.upper().startswith("AM_"):
                    continue
                clean_track = clean_to_track_name(track.name, base_pal, mod_name)
                actions_map[clean_track] = strip.action

    for act in bpy.data.actions:
        if act.name.upper().startswith("AM_"):
            continue
        clean_track = clean_to_track_name(act.name, base_pal, mod_name)
        if clean_track not in actions_map:
            actions_map[clean_track] = act

    os.makedirs(output_dir, exist_ok=True)
    print(f"[PalBaker Anims Export] Exporting {len(actions_map)} individual animation FBXs...", flush=True)

    exported_count = 0
    for clean_track, action in actions_map.items():
        # Set active action and frame range explicitly
        arm_obj.animation_data.action = action
        frame_start = int(action.frame_range[0])
        frame_end = int(action.frame_range[1])
        bpy.context.scene.frame_start = frame_start
        bpy.context.scene.frame_end = frame_end

        target_seq_name = f"AS_{mod_name}_{clean_track}"
        target_fbx = os.path.join(output_dir, f"{target_seq_name}.fbx")

        # Export Armature only (lightweight, under 50KB, bakes in <0.05s)
        bpy.ops.export_scene.fbx(
            filepath=target_fbx,
            use_selection=True,
            object_types={'ARMATURE'},
            bake_anim=True,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
            add_leaf_bones=False,
            armature_nodetype='ROOT',
            global_scale=0.01,
            apply_scale_options='FBX_SCALE_ALL'
        )
        exported_count += 1
        print(f"  ✓ Exported: {target_seq_name}.fbx ({frame_end - frame_start} frames)", flush=True)

    # Clean active action
    arm_obj.animation_data.action = None
    print(f"[PalBaker Anims Export] Completed exporting {exported_count} animation files.", flush=True)

if __name__ == "__main__":
    out_dir, m_name, b_pal = parse_args()
    if out_dir:
        export_individual_animations(out_dir, m_name, b_pal)