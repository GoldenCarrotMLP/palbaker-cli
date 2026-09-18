# utils/blueprint_patcher/__init__.py
import os
import re
import json
import shutil
import glob
import subprocess
from utils.extractor.core import extract_game_files

from .patch_mesh import patch_mesh_references, patch_physics_asset
from .patch_classes import patch_actor_class_and_cdo
from .clone_weapons import clone_partner_weapons
from .clone_actions import clone_unique_actions
from .clone_funnels import clone_funnel_character
from .build_variants import build_boss_variant, build_predator_variant

def find_skeleton_guid_in_json(json_path: str) -> str:
    if not json_path or not os.path.exists(json_path):
        return ""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        def search(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.lower() in ["skeletonguid", "virtualboneguid", "guid"] and isinstance(v, str) and len(v) >= 32:
                        return v
                    res = search(v)
                    if res: return res
            elif isinstance(node, list):
                for item in node:
                    res = search(item)
                    if res: return res
            return None
        return search(data) or ""
    except Exception:
        return ""

def create_notify_event_node(index_str: str, time_val: float, name_val: str, duration_val: float = 0.0):
    node_value = [
        { "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerTimeOffset", "Value": 0.0001 },
        { "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "EndTriggerTimeOffset", "Value": -0.0001 },
        { "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "TriggerWeightThreshold", "Value": 0.00001 },
        { "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI", "Name": "NotifyName", "Value": name_val },
        { "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "Notify", "Value": 0 }
    ]
    if duration_val > 0.0:
        node_value.append({ "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "Duration", "Value": float(duration_val) })
    node_value.append({ "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "LinkValue", "Value": float(time_val) })

    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "AnimNotifyEvent",
        "SerializeNone": True,
        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
        "SerializationControl": "NoExtension",
        "Operation": "None",
        "Name": index_str,
        "ArrayIndex": 0,
        "PropertyGuid": None,
        "IsZero": False,
        "PropertyTagFlags": "None",
        "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": node_value
    }

def patch_actor_blueprint(settings: dict, pal_id: str, template_id: str, pal_data: dict = None, log_callback=None, has_anims: bool = False, category: str = "Monster", base_pal: str = "") -> bool:
    def log(msg, cat="standard"):
        if log_callback: log_callback(msg, cat)
        else: print(f"[Blueprint Patch] {msg}", flush=True)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uasset_gui_exe = os.path.normpath(os.path.join(repo_root, "deps", "UAssetGUI.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    if not os.path.exists(uasset_gui_exe):
        log(f"Error: UAssetGUI.exe not found", "error")
        return False

    uproject = settings.get("uproject", "")
    project_dir = os.path.dirname(uproject) if uproject else ""
    project_name = os.path.splitext(os.path.basename(uproject))[0] if uproject else ""

    fmodel_output = settings.get("fmodel_output", "")
    if pal_data is None and fmodel_output:
        creator_json = os.path.normpath(os.path.join(fmodel_output, "Exports", "Pal", "Content", "Palbaker", "Creator", f"{pal_id}_creator.json"))
        if os.path.exists(creator_json):
            try:
                with open(creator_json, "r", encoding="utf-8") as f:
                    pal_data = json.load(f)
            except Exception: pal_data = {}
        else: pal_data = {}
    elif pal_data is None: pal_data = {}

    is_custom_pal = bool(pal_data and pal_data.get("CharacterID") == pal_id)
    is_variant = (not is_custom_pal and base_pal and base_pal.lower() != pal_id.lower())
    cat_sanitized = category.replace(" ", "_")

    if is_variant:
        cooked_bp_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Character", "Monster", "PalActorBP", base_pal, pal_id)
    else:
        cooked_bp_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Character", "Monster", "PalActorBP", pal_id)
    os.makedirs(cooked_bp_dir, exist_ok=True)

    temp_dir = os.path.join(repo_root, "temp_bp_extract")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # STEP 1: Extract Base Template Blueprint
        has_funnel = pal_data.get("HasFunnel", False)
        funnel_base = "RaijinDaughter" if "RaijinDaughter" in pal_data.get("FunnelWazaID", "") else "DreamDemon"
        bp_source_name = funnel_base if has_funnel else template_id

        success, msg = extract_game_files(settings, [
            f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/BP_{bp_source_name}.uasset",
            f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/BP_{bp_source_name}.uexp"
        ], temp_dir, format_type="raw")

        if not success:
            log(f"Failed to extract base blueprint: {msg}", "error")
            return False

        src_base_uasset = None
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.lower() == f"bp_{bp_source_name.lower()}.uasset":
                    src_base_uasset = os.path.join(root, f)
                    break
            if src_base_uasset: break

        temp_base_json = os.path.join(temp_dir, f"BP_{bp_source_name}.json")
        subprocess.run([uasset_gui_exe, "tojson", src_base_uasset, temp_base_json, "VER_UE5_1"], check=True, creationflags=flags)

        with open(temp_base_json, "r", encoding="utf-8") as f:
            base_json_str = f.read()

        # STEP 2: Dynamically Discover Actions & Animation Dependencies
        action_pattern = re.compile(rf'(Pal/Blueprint/Action/[\w/]*/(BP_Action_[a-zA-Z0-9_]+))', re.IGNORECASE)
        discovered_actions = sorted(list(set(action_pattern.findall(base_json_str))))
        
        # Filter actions that strictly belong to the template or base
        valid_actions = []
        for p_core, a_name in discovered_actions:
            if f"/{bp_source_name}/" in p_core or f"/{template_id}/" in p_core or bp_source_name in a_name or template_id in a_name:
                valid_actions.append((p_core, a_name))

        discovered_blendspaces = []
        discovered_montages = []
        discovered_abps = []

        if has_anims:
            bs_pattern = re.compile(rf'PalActorBP/{bp_source_name}/(BS_[a-zA-Z0-9_]+)', re.IGNORECASE)
            discovered_blendspaces = sorted(list(set(bs_pattern.findall(base_json_str))))

            am_pattern = re.compile(rf'Animation/Character/{cat_sanitized}/{bp_source_name}/(AM_[a-zA-Z0-9_]+)', re.IGNORECASE)
            discovered_montages = sorted(list(set(am_pattern.findall(base_json_str))))
            
            abp_pattern = re.compile(rf'PalActorBP/{bp_source_name}/(ABP_{bp_source_name}[a-zA-Z0-9_]*)', re.IGNORECASE)
            discovered_abps = sorted(list(set(abp_pattern.findall(base_json_str))))

        # STEP 3: Extract Discovered Dependencies
        dep_queue = []
        for path_core, _ in valid_actions:
            dep_queue.extend([f"Pal/Content/{path_core}.uasset", f"Pal/Content/{path_core}.uexp"])
            
        for bs in discovered_blendspaces:
            dep_queue.extend([f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/{bs}.uasset", f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/{bs}.uexp"])
            
        for am in discovered_montages:
            dep_queue.extend([f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{bp_source_name}/{am}.uasset", f"Pal/Content/Pal/Animation/Character/{cat_sanitized}/{bp_source_name}/{am}.uexp"])
            
        for abp in discovered_abps:
            dep_queue.extend([f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/{abp}.uasset", f"Pal/Content/Pal/Blueprint/Character/Monster/PalActorBP/{bp_source_name}/{abp}.uexp"])

        if has_anims:
            dep_queue.extend([
                f"Pal/Content/Pal/Model/Character/Skeleton/{bp_source_name}/SK_{bp_source_name}_Skeleton.uasset",
                f"Pal/Content/Pal/Model/Character/Skeleton/{bp_source_name}/SK_{bp_source_name}_Skeleton.uexp"
            ])

        if dep_queue:
            log(f"  Extracting {len(dep_queue)//2} dynamic dependencies (Actions, ABP, BS, AM)...")
            extract_game_files(settings, dep_queue, temp_dir, format_type="raw")

        # Gather custom skeleton GUID
        vanilla_guid = "BF21DEE0-4BCF0A09-60C97DA1-367595A0"
        custom_guid = "F3642458-43D36EB4-2B398F89-8DDC8313"
        custom_anims = {}

        if has_anims:
            v_skel = None
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if f.lower() == f"sk_{bp_source_name.lower()}_skeleton.uasset":
                        v_skel = os.path.join(root, f)
                        break
                if v_skel: break
            if v_skel:
                sk_json = os.path.join(temp_dir, "vanilla_skel.json")
                subprocess.run([uasset_gui_exe, "tojson", v_skel, sk_json, "VER_UE5_1"], check=True, creationflags=flags)
                vanilla_guid = find_skeleton_guid_in_json(sk_json) or vanilla_guid

            sidecar_path = os.path.join(fmodel_output, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal or pal_id, f"{pal_id}_blend.json")
            if os.path.exists(sidecar_path):
                try:
                    with open(sidecar_path, "r", encoding="utf-8") as f_sc:
                        sc_data = json.load(f_sc)
                        custom_anims = sc_data.get("custom_animations", {})
                        custom_guid = custom_anims.get("custom_skeleton_guid", custom_guid)
                except Exception: pass

        # STEP 4: Global Patching Function
        def global_patch(content: str) -> str:
            if has_funnel:
                custom_waza = pal_data.get("FunnelWazaID", f"Funnel_{funnel_base}")
                content = content.replace(f"Funnel_{funnel_base}", "FUNNEL_PROTECTED_ID")
                content = content.replace(funnel_base, template_id)
                content = content.replace("FUNNEL_PROTECTED_ID", custom_waza)
                content = content.replace(f"BP_FunnelCharacter_{template_id}", f"BP_FunnelCharacter_{pal_id}")
                
            content = content.replace(f"SK_{template_id}", f"SK_{pal_id}")
            content = content.replace(f"PA_{template_id}", f"PA_{pal_id}")
            content = content.replace(f"/Model/Character/Monster/{template_id}", f"/Model/Character/Monster/{pal_id}")

            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}_C(?![A-Za-z0-9_])", f"BP_{pal_id}_C", content)
            content = re.sub(rf"(?<![A-Za-z0-9_])BP_{template_id}(?![A-Za-z0-9_])", f"BP_{pal_id}", content)

            for path_core, a_name in valid_actions:
                new_path_core = path_core.replace(template_id, pal_id)
                new_name = a_name.replace(template_id, pal_id)
                content = content.replace(f"/Game/{path_core}.{a_name}_C", f"/Game/{new_path_core}.{new_name}_C")
                content = content.replace(f"/Game/{path_core}", f"/Game/{new_path_core}")
                content = content.replace(f"Pal/Content/{path_core}", f"Pal/Content/{new_path_core}")
                content = re.sub(rf"(?<![A-Za-z0-9_]){a_name}(?![A-Za-z0-9_])", new_name, content)

            if has_anims:
                content = content.replace(vanilla_guid, custom_guid)
                content = content.replace(f"SK_{template_id}_Skeleton", f"SK_{pal_id}_Skeleton")
                content = content.replace(f"Animation/Character/{cat_sanitized}/{template_id}", f"Animation/Character/{cat_sanitized}/{pal_id}")

                for abp in discovered_abps:
                    new_abp = abp.replace(template_id, pal_id)
                    content = content.replace(f"{abp}_C", f"{new_abp}_C")
                    content = content.replace(abp, new_abp)

                for bs in discovered_blendspaces:
                    new_bs = re.sub(rf"(BS_[a-zA-Z0-9_]*?)_{template_id}", rf"\1_{pal_id}", bs)
                    content = content.replace(bs, new_bs)

                for am in discovered_montages:
                    new_am = am.replace(template_id, pal_id)
                    content = content.replace(am, new_am)
                    
            return content

        # STEP 5: Patch & Compile Dependencies
        for path_core, a_name in valid_actions:
            action_uasset = os.path.join(temp_dir, f"Pal/Content/{path_core}.uasset")
            if os.path.exists(action_uasset):
                a_json = action_uasset.replace(".uasset", ".json")
                subprocess.run([uasset_gui_exe, "tojson", action_uasset, a_json, "VER_UE5_1"], check=True, creationflags=flags)
                with open(a_json, "r", encoding="utf-8") as f_aj:
                    a_str = global_patch(f_aj.read())
                with open(a_json, "w", encoding="utf-8") as f_aj:
                    f_aj.write(a_str)
                
                new_path_core = path_core.replace(template_id, pal_id)
                new_name = a_name.replace(template_id, pal_id)
                # Correctly target the Actions directory inside the Cooked Project
                action_dest_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", os.path.dirname(new_path_core))
                os.makedirs(action_dest_dir, exist_ok=True)
                subprocess.run([uasset_gui_exe, "fromjson", a_json, os.path.join(action_dest_dir, f"{new_name}.uasset")], check=True, creationflags=flags)
                log(f"  ✓ Retargeted unique action: {new_name}")

        # STEP 8: Process ABP, BlendSpaces, and Montages (If Anims Active)
        if has_anims:
            from utils.uasset_helper import patch_montage_ast, compile_uasset, decompile_uasset

            anim_files = []
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    if (f.startswith("ABP_") or f.startswith("BS_") or f.startswith("AM_")) and f.endswith(".uasset"):
                        anim_files.append(os.path.join(root, f))

            for a_uasset in anim_files:
                a_json = a_uasset.replace(".uasset", ".json")
                orig_filename = os.path.basename(a_uasset).replace(".uasset", "")

                # Decompile with usmap so AM_ montages unpack as NormalExport
                if orig_filename.startswith("AM_"):
                    decompile_uasset(uasset_gui_exe, a_uasset, a_json, usmap_path)
                else:
                    decompile_uasset(uasset_gui_exe, a_uasset, a_json)

                with open(a_json, "r", encoding="utf-8") as f_aj:
                    a_data = json.load(f_aj)

                # Montages: apply deep AST retargeting, notify injection, and NameMap sync
                if orig_filename.startswith("AM_"):
                    clean_track = orig_filename.replace(f"AM_{template_id}_", "")
                    user_anim = next((v for v in custom_anims.get("anims", {}).values() if v.get("nla_track_name") == clean_track), None)
                    user_notifies = user_anim.get("notifies") if user_anim else None

                    a_data = patch_montage_ast(
                        a_data,
                        template_id=template_id,
                        target_pal=pal_id,
                        skeleton_guid=custom_guid,
                        notifies=user_notifies
                    )
                else:
                    # ABP / BS: apply standard text retargeting
                    a_str = global_patch(json.dumps(a_data, indent=2))
                    a_data = json.loads(a_str)

                with open(a_json, "w", encoding="utf-8") as f_aj:
                    json.dump(a_data, f_aj, indent=2)

                # Route compiled montages and blendspaces
                target_dest_filename = re.sub(rf"((?:AM|BS|ABP)_[a-zA-Z0-9_]*?)_{template_id}", rf"\1_{pal_id}", orig_filename)
                target_dest_filename = target_dest_filename.replace(template_id, pal_id) + ".uasset"

                if orig_filename.startswith("AM_"):
                    cat_san = category.replace(" ", "_")
                    if is_variant:
                        am_cooked_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Animation", "Character", cat_san, base_pal, pal_id)
                    else:
                        am_cooked_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Animation", "Character", cat_san, pal_id)
                    dest_anim_uasset = os.path.join(am_cooked_dir, target_dest_filename)
                    compile_uasset(uasset_gui_exe, a_json, dest_anim_uasset, usmap_path)
                else:
                    dest_anim_uasset = os.path.join(cooked_bp_dir, target_dest_filename)
                    compile_uasset(uasset_gui_exe, a_json, dest_anim_uasset)

                log(f"  ✓ Compiled animation asset: {target_dest_filename}", "success")

        # STEP 6: Patch & Compile Main Actor Blueprint
        base_json_str = global_patch(base_json_str)
        try: base_json_data = json.loads(base_json_str)
        except Exception: pass

        if is_custom_pal:
            base_json_data, base_json_str = clone_partner_weapons(
                base_json_data, base_json_str, template_id, pal_id, settings,
                temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, pal_data=pal_data
            )
            base_json_data, base_json_str = clone_funnel_character(
                base_json_data, base_json_str, template_id, pal_id, settings,
                temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log, pal_data=pal_data
            )

        if has_anims and "anims" in custom_anims:
            rest_anims = [a for a in custom_anims["anims"].values() if a.get("category") == "RandomRest"]
            if rest_anims:
                try:
                    new_rest_infos = []
                    rest_anims.sort(key=lambda x: x.get("enum_key", ""))
                    for ra in rest_anims:
                        props = ra.get("rest_props", {})
                        m_asset = ra.get("montage_asset")
                        if not m_asset: continue
                        m_asset_retargeted = m_asset.replace(template_id, pal_id)
                        cat_san = category.replace(" ", "_")
                        if is_variant:
                            m_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{base_pal}/{pal_id}/{m_asset}"
                        else:
                            m_pkg = f"/Game/Pal/Animation/Character/{cat_sanitized}/{pal_id}/{m_asset}"

                        new_rest_infos.append({
                            "RandomRestMontage": { "ObjectName": f"AnimMontage'{m_asset}'", "ObjectPath": f"{m_pkg}.0" },
                            "Weight": float(props.get("weight", 1.0)),
                            "LoopNum_Min": int(props.get("loop_min", 1)),
                            "LoopNum_Max": int(props.get("loop_max", 1)),
                            "AfterIdleTime": float(props.get("after_idle_time", 2.0))
                        })

                    for exp in base_json_data.get("Exports", []):
                        if exp.get("Type") == "PalStaticCharacterParameterComponent" or "StaticCharacterParameterComponent" in exp.get("Name", ""):
                            exp.setdefault("Properties", {})["RandomRestMontageInfos"] = new_rest_infos

                    base_json_str = json.dumps(base_json_data, indent=4)
                except Exception as e:
                    log(f"Warning: Failed to inject Random Rests: {e}", "warning")

        with open(temp_base_json, "w", encoding="utf-8") as f:
            f.write(base_json_str)

        dest_base_uasset = os.path.join(cooked_bp_dir, f"BP_{pal_id}.uasset")
        subprocess.run([uasset_gui_exe, "fromjson", temp_base_json, dest_base_uasset], check=True, creationflags=flags)
        log(f"  ✓ Compiled Actor Blueprint: BP_{pal_id}.uasset", "success")

        # STEP 7: Build Variants
        boss_scale = float(pal_data.get("BossScale", 1.4))
        generate_boss = pal_data.get("GenerateBoss", True) is not False
        generate_predator = bool(pal_data.get("GeneratePredator", False))

        if generate_boss:
            build_boss_variant(base_json_str, template_id, pal_id, boss_scale, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log)
        if generate_predator:
            build_predator_variant(template_id, pal_id, generate_boss, settings, temp_dir, cooked_bp_dir, uasset_gui_exe, flags, log)

        shutil.rmtree(temp_dir, ignore_errors=True)
        return True

    except Exception as e:
        log(f"Fatal error during unified blueprint patching: {e}", "error")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False