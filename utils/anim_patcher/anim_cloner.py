# utils/anim_patcher/anim_cloner.py
import os
import sys
import json
import re
import shutil
import subprocess
from utils.extractor.core import extract_game_files
from utils.uasset_helper import compile_uasset

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding='utf-8', errors='replace')

def execute_animation_stack_clone(settings: dict, base_pal: str, mod_name: str, category: str, temp_dir: str, custom_anims_meta: dict, log_cb=None, is_custom_pal: bool = False) -> bool:
    def log(msg, lvl="standard"):
        if log_cb: log_cb(msg, lvl)
        else: print(f"[PalBaker AnimCloner] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    log(f"Extracting vanilla animation stack and blueprints for {base_pal}...", "standard")
    
    # 1. Extract skeleton, actor BP, anim BP, and all blendspaces
    vanilla_skel_rel = f"Pal/Content/Pal/Model/Character/Skeleton/{base_pal}/SK_{base_pal}_Skeleton"
    vanilla_bp_folder = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}"
    vanilla_anims_folder = f"Pal/Content/Pal/Animation/Character/Monster/{base_pal}"
    
    extraction_queue = [
        f"{vanilla_skel_rel}.uasset", f"{vanilla_skel_rel}.uexp",
        f"{vanilla_bp_folder}/*",
        f"{vanilla_anims_folder}/*"
    ]
    extract_game_files(settings, extraction_queue, temp_dir, format_type="raw")

    # 2. Extract Vanilla Skeleton GUID
    vanilla_skel_disk = None
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower() == f"sk_{base_pal.lower()}_skeleton.uasset":
                vanilla_skel_disk = os.path.join(root, f)
                break
        if vanilla_skel_disk: break

    if not vanilla_skel_disk or not os.path.exists(vanilla_skel_disk):
        log("Error: Vanilla skeleton could not be extracted.", "error")
        return False

    vanilla_skel_json = os.path.join(temp_dir, "vanilla_skel.json")
    subprocess.run([uasset_gui, "tojson", vanilla_skel_disk, vanilla_skel_json, "VER_UE5_1"], check=True, creationflags=creation_flags)
    with open(vanilla_skel_json, "r", encoding="utf-8") as f:
        v_skel_data = f.read()

    guid_match = re.search(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}', v_skel_data)
    vanilla_guid = guid_match.group(0) if guid_match else "BF21DEE0-4BCF0A09-60C97DA1-367595A0"

    # 3. Read Custom Skeleton GUID
    project_dir = os.path.dirname(settings.get("uproject", ""))
    project_name = os.path.splitext(os.path.basename(settings.get("uproject", "")))[0]
    
    custom_skel_candidates = [
        os.path.normpath(os.path.join(project_dir, "Content", "Pal", "Model", "Character", "Skeleton", base_pal, mod_name, f"SK_{mod_name}_Skeleton.uasset")),
        os.path.normpath(os.path.join(project_dir, "Content", "Pal", "Model", "Character", "Skeleton", base_pal, f"SK_{mod_name}_Skeleton.uasset")),
        os.path.normpath(os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Model", "Character", "Skeleton", base_pal, mod_name, f"SK_{mod_name}_Skeleton.uasset")),
        os.path.normpath(os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Model", "Character", "Skeleton", base_pal, f"SK_{mod_name}_Skeleton.uasset")),
    ]
    
    custom_skel_disk = next((p for p in custom_skel_candidates if os.path.exists(p)), None)
    new_guid = custom_anims_meta.get("custom_skeleton_guid", "")

    if not new_guid and custom_skel_disk and os.path.exists(custom_skel_disk):
        custom_skel_json = os.path.join(temp_dir, "custom_skel.json")
        subprocess.run([uasset_gui, "tojson", custom_skel_disk, custom_skel_json, "VER_UE5_1"], check=True, creationflags=creation_flags)
        with open(custom_skel_json, "r", encoding="utf-8") as f:
            c_skel_data = f.read()
        new_guid_match = re.search(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}', c_skel_data)
        if new_guid_match:
            new_guid = new_guid_match.group(0)

    if not new_guid:
        new_guid = "F3642458-43D36EB4-2B398F89-8DDC8313"

    log(f"  Vanilla Skeleton GUID: {vanilla_guid}")
    log(f"  Target Custom Skeleton GUID: {new_guid}")

    # 4. Resolved Virtual and Cooked Paths (Strictly Cooked Staging Only!)
    is_var = (not is_custom_pal and base_pal.lower() != mod_name.lower())
    
    v_new_anim = f"/Game/Pal/Animation/Character/{category}/{base_pal}/{mod_name}" if is_var else f"/Game/Pal/Animation/Character/{category}/{mod_name}"
    raw_new_anim = f"Pal/Content/Pal/Animation/Character/{category}/{base_pal}/{mod_name}" if is_var else f"Pal/Content/Pal/Animation/Character/{category}/{mod_name}"

    v_new_bp = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}/{mod_name}" if is_var else f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{mod_name}"
    raw_new_bp = f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}/{mod_name}" if is_var else f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{mod_name}"

    v_new_skel = f"/Game/Pal/Model/Character/Skeleton/{base_pal}/{mod_name}/SK_{mod_name}_Skeleton" if is_var else f"/Game/Pal/Model/Character/Skeleton/{mod_name}/SK_{mod_name}_Skeleton"
    raw_new_skel = f"Pal/Content/Pal/Model/Character/Skeleton/{base_pal}/{mod_name}/SK_{mod_name}_Skeleton" if is_var else f"Pal/Content/Pal/Model/Character/Skeleton/{mod_name}/SK_{mod_name}_Skeleton"

    v_new_mesh = f"/Game/Pal/Model/Character/{category}/{base_pal}/{mod_name}/SK_{mod_name}" if is_var else f"/Game/Pal/Model/Character/{category}/{mod_name}/SK_{mod_name}"
    raw_new_mesh = f"Pal/Content/Pal/Model/Character/{category}/{base_pal}/{mod_name}/SK_{mod_name}" if is_var else f"Pal/Content/Pal/Model/Character/{category}/{mod_name}/SK_{mod_name}"

    cooked_root = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content")
    anims_cooked_dir = os.path.normpath(os.path.join(cooked_root, v_new_anim.replace("/Game/", "")))
    bp_cooked_dir = os.path.normpath(os.path.join(cooked_root, v_new_bp.replace("/Game/", "")))
    skel_cooked_dir = os.path.normpath(os.path.join(cooked_root, os.path.dirname(v_new_skel.replace("/Game/", ""))))

    for d in [anims_cooked_dir, bp_cooked_dir, skel_cooked_dir]:
        os.makedirs(d, exist_ok=True)

    # 5. Clean any rogue unversioned packages in Content/ that cause editor crashes
    rogue_content_bp = os.path.join(project_dir, "Content", v_new_bp.replace("/Game/", ""))
    if os.path.exists(rogue_content_bp):
        shutil.rmtree(rogue_content_bp, ignore_errors=True)

    extracted_uassets = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.endswith(".uasset") and not f.startswith("SK_"):
                extracted_uassets.append(os.path.join(root, f))

    log(f"Retargeting {len(extracted_uassets)} dependencies (BP, ABP, BS, AM)...", "standard")
    
    for uasset_path in extracted_uassets:
        json_path = uasset_path.replace(".uasset", ".json")
        subprocess.run([uasset_gui, "tojson", uasset_path, json_path, "VER_UE5_1"], check=True, creationflags=creation_flags)
        
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Guided Path Replacements
        content = content.replace(vanilla_guid, new_guid)

        # Animations
        content = content.replace(f"Pal/Content/Pal/Animation/Character/Monster/{base_pal}", raw_new_anim)
        content = content.replace(f"/Game/Pal/Animation/Character/Monster/{base_pal}", v_new_anim)

        # Blueprints (BP, ABP, BS)
        content = content.replace(f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}", raw_new_bp)
        content = content.replace(f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}", v_new_bp)

        # Skeletons
        content = content.replace(vanilla_skel_rel, raw_new_skel)
        content = content.replace(f"/Game/{vanilla_skel_rel[12:]}", v_new_skel)
        content = content.replace(f"Skeleton'SK_{base_pal}_Skeleton'", f"Skeleton'SK_{mod_name}_Skeleton'")
        content = content.replace(f'"SK_{base_pal}_Skeleton"', f'"SK_{mod_name}_Skeleton"')

        # Meshes
        content = content.replace(f"Pal/Content/Pal/Model/Character/Monster/{base_pal}/SK_{base_pal}", raw_new_mesh)
        content = content.replace(f"/Game/Pal/Model/Character/Monster/{base_pal}/SK_{base_pal}", v_new_mesh)
        content = content.replace(f"SkeletalMesh'SK_{base_pal}'", f"SkeletalMesh'SK_{mod_name}'")
        content = content.replace(f'"SK_{base_pal}"', f'"SK_{mod_name}"')

        # Class Names
        content = re.sub(rf"(?<!A)BP_{base_pal}", f"BP_{mod_name}", content)
        content = content.replace(f"ABP_{base_pal}", f"ABP_{mod_name}")

        # Retarget AnimSequences (AS_<base_pal>_<Track> -> AS_<mod_name>_<Track>)
        content = content.replace(f"AS_{base_pal}_", f"AS_{mod_name}_")

        # Retarget AnimMontages (AM_<base_pal>_<Track> -> AM_<mod_name>_<Track>)
        content = content.replace(f"AM_{base_pal}_", f"AM_{mod_name}_")

        # Retarget BlendSpaces (BS_..._<base_pal>... -> BS_..._<mod_name>...)
        content = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{base_pal}([_'\"])", rf"\1_{mod_name}\2", content)

        # Retarget Action Blueprints
        content = content.replace(f"BP_Action_{base_pal}", f"BP_Action_{mod_name}")
        content = content.replace(f"BP_Action_Unique_{base_pal}", f"BP_Action_Unique_{mod_name}")
        content = content.replace(f"BP_Action_UniqueSkill_{base_pal}", f"BP_Action_UniqueSkill_{mod_name}")

        filename = os.path.basename(uasset_path).replace(".uasset", "")

        # Inject user notifies on montages
        if filename.startswith("AM_"):
            anim_meta = custom_anims_meta.get("anims", {}).get(filename)
            if anim_meta and anim_meta.get("notifies"):
                try:
                    montage_obj = json.loads(content)
                    for exp in montage_obj.get("Exports", []):
                        if exp.get("Type") == "AnimMontage":
                            props = exp.setdefault("Properties", {})
                            notifies_arr = props.setdefault("Notifies", [])
                            for user_notify in anim_meta["notifies"]:
                                notifies_arr.append({
                                    "TriggerTimeOffset": 0.0,
                                    "DisplayTime": float(user_notify.get("Time", 0.0)),
                                    "NotifyName": user_notify.get("Name", "PalCustomNotify"),
                                    "Notify": None
                                })
                    content = json.dumps(montage_obj, indent=4)
                except Exception: pass

        with open(json_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Route compiled asset strictly into Cooked Staging
        target_name = f"{filename.replace(base_pal, mod_name)}.uasset"
        if filename.startswith("AM_") or filename.startswith("AS_"):
            dest_cooked = os.path.join(anims_cooked_dir, target_name)
        else:
            dest_cooked = os.path.join(bp_cooked_dir, target_name)

        compile_uasset(uasset_gui, json_path, dest_cooked, usmap_path)

    log("[SUCCESS] Animation stack (BP, ABP, BS) retargeted and staged in Cooked directory!", "success")
    return True