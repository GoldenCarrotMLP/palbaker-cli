# utils/builder/cooker_helper.py
import os
import sys
import shutil
import subprocess
import glob
import ctypes
from utils.audio_helper import get_staged_audio_overrides

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)
    ]

def get_free_physical_ram() -> float:
    if os.name != 'nt':
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if 'MemAvailable' in line:
                        return int(line.split()[1]) / (1024 * 1024)
        except Exception:
            pass
        return 8.0

    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullAvailPhys / (1024 ** 3)
    except Exception:
        return 8.0

def verify_cooking_memory_limit(threshold_gb: float = 4.0) -> tuple[bool, str]:
    free_ram = get_free_physical_ram()
    if free_ram < threshold_gb:
        return False, f"Low Physical Memory: Only {free_ram:.2f} GB of free RAM is available, need at least {threshold_gb:.2f} GB. Please close background editors."
    return True, ""

def run_and_stream(cmd_args) -> bool:
    process = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1
    )
    had_issues = False
    if process.stdout:
        for line in iter(process.stdout.readline, ''):
            if not line: break
            stripped = line.strip()
            print(stripped, flush=True) 
            if "error:" in stripped.lower():
                had_issues = True
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd_args)
    return had_issues

def verify_unreal_animation_assets(workspace, sidecar_data: dict) -> tuple[bool, list[str]]:
    """
    Validates that only animation sequences ACTUALLY REQUIRED by active
    BlendSpaces or customized Montages exist in Unreal before cooking.
    """
    if not workspace.has_anims:
        return True, []

    errors = []
    anims_dir = getattr(workspace, "anims_source_dir", "")
    
    if not anims_dir or not os.path.exists(anims_dir):
        errors.append(
            f"Custom animations are enabled, but the animation directory was not found in Unreal:\n"
            f"  Expected: '{anims_dir}'\n"
            f"  -> Please click 'Push Animations' first to export and ingest your animation sequences."
        )
        return False, errors

    existing_uassets = {
        os.path.splitext(f)[0].lower() 
        for f in os.listdir(anims_dir) 
        if f.endswith(".uasset")
    }

    if len(existing_uassets) == 0:
        errors.append(
            f"Custom animations are active for '{workspace.mod_name}', but 0 animation sequences (.uasset) "
            f"were found in Unreal at '{anims_dir}'.\n"
            f"  -> Please click 'Push Animations' before cooking!"
        )
        return False, errors

    anims_dict = sidecar_data.get("custom_animations", {}).get("anims", {})
    bs_dict = sidecar_data.get("custom_animations", {}).get("blend_spaces", {})
    missing_sequences = []

    IGNORED_ANIMATION_TRACKS = {"hit", "damageadditive"}

    # 1. Collect sequences required by active BlendSpaces
    required_sequences = {} # { seq_name_lower: (original_seq_name, requirement_description) }
    for bs_name, bs_data in bs_dict.items():
        for sample in bs_data.get("samples", []):
            if sample.get("in_nla", True):
                anim_name = sample.get("animation", "")
                if anim_name:
                    s_lower = anim_name.split(".")[0].lower()
                    required_sequences[s_lower] = (anim_name, f"BlendSpace '{bs_name}' sample '{sample.get('clean_name')}'")

    # 2. Collect sequences required by active / modified Montages
    for anim_key, anim_meta in anims_dict.items():
        if not isinstance(anim_meta, dict):
            continue
        if anim_meta.get("category") == "BlendSpaceSample":
            continue

        track = anim_meta.get("nla_track_name") or ""
        if track.lower() in IGNORED_ANIMATION_TRACKS or anim_key.lower().endswith("_hit"):
            continue

        # If a montage is NOT in NLA and was never modified by the user,
        # it is not custom-required (it will play the vanilla template animation safely)
        if not anim_meta.get("in_nla", False) and not anim_meta.get("is_modified", False):
            continue

        seq_asset = anim_meta.get("sequence_asset")
        if not seq_asset and track:
            seq_asset = f"AS_{workspace.mod_name}_{track}"

        # Only require the sequence the montage ACTUALLY references!
        if seq_asset:
            s_lower = seq_asset.split(".")[0].lower()
            if s_lower not in required_sequences:
                required_sequences[s_lower] = (seq_asset, f"Montage '{anim_meta.get('montage_asset', anim_key)}'")

    # 3. Check required sequences against Unreal's files
    for s_lower, (orig_name, req_source) in required_sequences.items():
        if s_lower in IGNORED_ANIMATION_TRACKS or s_lower.endswith("_hit"):
            continue
        if s_lower not in existing_uassets:
            missing_sequences.append(f"{orig_name}.uasset ({req_source})")

    if missing_sequences:
        errors.append(
            f"The following required animation sequences are missing from your Unreal project:\n" +
            "\n".join(f"  • {s}" for s in missing_sequences) +
            f"\n  -> Push animations to Unreal to import the missing sequences before cooking."
        )
        return False, errors

    return True, []

def clean_cook_environment(workspace):
    for p in [workspace.output_pak_clean, workspace.output_pak_err]:
        if os.path.exists(p):
            try:
                os.remove(p)
                print(f"Cleaned old target pak: {os.path.basename(p)}", flush=True)
            except OSError:
                print(f"CRITICAL ERROR: Cannot overwrite '{os.path.basename(p)}'. Close the game!", flush=True)
                sys.exit(1)

    # Parent Mode Deduplication: If packing parent, clean standalone paks of child variants included in this build
    if not workspace.is_variant:
        cat_parts = workspace.category.replace("/", os.sep)
        base_fmodel_dir = os.path.normpath(os.path.join(
            workspace.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", 
            cat_parts, workspace.base_pal
        )) if workspace.fmodel_root else ""

        ue_char_dir = os.path.normpath(os.path.join(
            workspace.project_dir, "Content", "Pal", "Model", "Character", 
            cat_parts, workspace.base_pal
        )) if workspace.project_dir else ""

        discovered_subs = set()
        if os.path.exists(ue_char_dir):
            discovered_subs.update(s for s in os.listdir(ue_char_dir) if os.path.isdir(os.path.join(ue_char_dir, s)) and not s.startswith("."))
        if os.path.exists(base_fmodel_dir):
            discovered_subs.update(s for s in os.listdir(base_fmodel_dir) if os.path.isdir(os.path.join(base_fmodel_dir, s)) and not s.startswith("."))

        for sub in sorted(list(discovered_subs)):
            if hasattr(workspace, "skipped_variants") and sub in workspace.skipped_variants:
                continue
            if sub.lower() in ["sources", ".palbaker_audio"]:
                continue

            standalone_candidates = [
                os.path.join(workspace.output_dir, f"{sub}_P.pak"),
                os.path.join(workspace.output_dir, f"{sub}_err_P.pak"),
            ]
            if workspace.palworld_exe and os.path.exists(workspace.palworld_exe):
                paks_dir = os.path.join(os.path.dirname(workspace.palworld_exe), "Pal", "Content", "Paks")
                standalone_candidates.extend([
                    os.path.join(paks_dir, "palBaker", f"{sub}_P.pak"),
                    os.path.join(paks_dir, "palBaker", f"{sub}_err_P.pak"),
                ])

            for cand in set(standalone_candidates):
                if os.path.exists(cand):
                    try:
                        os.remove(cand)
                        print(f"Cleaned redundant standalone variant pak: {os.path.basename(cand)} (Will consolidate into {os.path.basename(workspace.output_pak_clean)})", flush=True)
                    except OSError:
                        print(f"CRITICAL ERROR: Cannot remove redundant variant pak '{os.path.basename(cand)}'. Close the game!", flush=True)
                        sys.exit(1)

    # Note: We do NOT delete workspace.cooked_dir so that pre-cooked variant subfolders are preserved!
    if os.path.exists(workspace.cooked_skel_dir): 
        shutil.rmtree(workspace.cooked_skel_dir, ignore_errors=True)
    if os.path.exists(workspace.cooked_anims_dir): 
        shutil.rmtree(workspace.cooked_anims_dir, ignore_errors=True)
    if os.path.exists(workspace.cooked_bp_dir): 
        shutil.rmtree(workspace.cooked_bp_dir, ignore_errors=True)

    # Clean stale custom blueprints (weapons, funnels) in Saved/Cooked for this mod
    if workspace.project_dir:
        cooked_pal_bp = os.path.join(workspace.project_dir, "Saved", "Cooked", "Windows", workspace.target_project_name, "Content", "Pal", "Blueprint")
        if os.path.exists(cooked_pal_bp):
            for sub in ["Character/Funnel", "Weapon"]:
                d = os.path.join(cooked_pal_bp, os.path.normpath(sub))
                if os.path.exists(d):
                    for f in os.listdir(d):
                        if workspace.mod_name.lower() in f.lower() and f.endswith((".uasset", ".uexp", ".ubulk")):
                            try: os.remove(os.path.join(d, f))
                            except OSError: pass

def is_path_blacklisted(game_virtual_path: str, custom_blacklist: list[str] | None) -> bool:
    """
    Checks if a candidate virtual path matches any rule in the blacklist.
    Handles relative paths, folder prefixes, .uasset extensions, or standalone asset names.
    """
    if not custom_blacklist or not game_virtual_path:
        return False
        
    clean_candidate = game_virtual_path.replace("\\", "/").strip("/")
    if clean_candidate.lower().startswith("game/"):
        candidate_rel = clean_candidate[5:]
    else:
        candidate_rel = clean_candidate

    candidate_rel_no_ext = os.path.splitext(candidate_rel)[0]
    candidate_filename = os.path.basename(candidate_rel)
    candidate_asset_name = os.path.splitext(candidate_filename)[0]

    for rule in custom_blacklist:
        if not rule:
            continue
        r = rule.strip()
        if not r or r.startswith("#"):
            continue
            
        r = r.replace("\\", "/").strip("/")
        if "." in r and not r.lower().endswith((".uasset", ".uexp", ".ubulk", ".png", ".wem")):
            r = r.split(".")[0]
            
        if r.lower().startswith("game/"):
            r = r[5:]
        elif r.lower().startswith("pal/content/"):
            r = r[12:]

        r = r.strip("/")
        if not r:
            continue
            
        r_lower = r.lower()
        if "/" in r:
            if candidate_rel.lower().startswith(r_lower) or candidate_rel_no_ext.lower().startswith(r_lower):
                return True
        else:
            # Asset name or filename match
            if candidate_asset_name.lower() == r_lower or candidate_filename.lower() == r_lower:
                return True
                
    return False

def resolve_packaging_manifest(workspace, has_anims: bool, extra_packages: list[str] = None) -> list[tuple[str, str]]:
    folders_to_pack = []
    blacklist = getattr(workspace, "custom_blacklist", [])
    skipped_variants = getattr(workspace, "skipped_variants", [])
    category_sanitized = workspace.category.replace(" ", "_").replace("\\", "/")
    cat_parts = workspace.category.replace("/", os.sep)
    cooked_content = os.path.join(workspace.project_dir, "Saved", "Cooked", "Windows", workspace.target_project_name, "Content")

    if workspace.is_variant:
        # =========================================================================
        # VARIANT / CHILD MOD MODE: STRICTLY ISOLATED TO THIS VARIANT ONLY!
        # =========================================================================
        print(f"  [Pack Manifest] Variant mode: Building isolated package for '{workspace.mod_name}'...", flush=True)

        # 1. Variant Mesh folder
        if os.path.exists(workspace.cooked_dir):
            folders_to_pack.append((workspace.cooked_dir, workspace.ue_virtual_path.replace("/Game/", "")))

        # 2. Variant Dedicated Skeleton (ALWAYS pack if present to satisfy mesh dependency)
        if os.path.exists(workspace.cooked_skel_dir):
            folders_to_pack.append((workspace.cooked_skel_dir, workspace.skeleton_virtual_path.replace("/Game/", "")))
            print(f"  -> Packed variant dedicated skeleton: {workspace.skeleton_virtual_path}", flush=True)

        # 3. Variant Animations (if custom anims active)
        if has_anims and os.path.exists(workspace.cooked_anims_dir):
            folders_to_pack.append((workspace.cooked_anims_dir, workspace.anims_virtual_path.replace("/Game/", "")))
            print(f"  -> Packed variant custom animations for {workspace.mod_name}.", flush=True)

        # 3. Variant PalActorBP folder (BP_, ABP_, BS_)
        if os.path.exists(workspace.cooked_bp_dir):
            for cf in glob.glob(os.path.join(workspace.cooked_bp_dir, "*.*")):
                if cf.endswith((".uasset", ".uexp", ".ubulk")):
                    fn = os.path.basename(cf)
                    v_rel = f"{workspace.blueprint_virtual_path.replace('/Game/', '')}/{fn}"
                    if not is_path_blacklisted(f"/Game/{v_rel}", blacklist):
                        folders_to_pack.append((cf, v_rel))
            print(f"  -> Packed variant Blueprint Stack for {workspace.mod_name}.", flush=True)

        # 4. Variant Waza and Action Blueprints
        blueprint_cooked_root = os.path.join(cooked_content, "Pal", "Blueprint")
        if os.path.exists(blueprint_cooked_root):
            waza_dir = os.path.join(blueprint_cooked_root, "Action", "Waza", workspace.mod_name)
            if os.path.exists(waza_dir):
                waza_vrel = f"Pal/Blueprint/Action/Waza/{workspace.mod_name}"
                if not is_path_blacklisted(f"/Game/{waza_vrel}", blacklist):
                    folders_to_pack.append((waza_dir, waza_vrel))
                    print(f"  -> Packed variant Waza directory: {waza_vrel}", flush=True)

            for root, _, files in os.walk(blueprint_cooked_root):
                clean_r = root.replace("\\", "/")
                if "PalActorBP" in clean_r or "Action/Waza" in clean_r:
                    continue
                for file in files:
                    if workspace.mod_name.lower() in file.lower() and file.endswith((".uasset", ".uexp", ".ubulk")):
                        cf = os.path.join(root, file)
                        rel_bp = "Pal/Blueprint/" + os.path.relpath(cf, blueprint_cooked_root).replace("\\", "/")
                        if not is_path_blacklisted(f"/Game/{rel_bp}", blacklist):
                            folders_to_pack.append((cf, rel_bp))

        # Variant Icon and Audio overrides
        if workspace.has_icon:
            icon_base = os.path.join(cooked_content, "Pal", "Texture", "PalIcon", "Normal", f"T_{workspace.mod_name}_icon_normal")
            for ext in [".uasset", ".uexp", ".ubulk"]:
                cf = icon_base + ext
                if os.path.exists(cf):
                    folders_to_pack.append((cf, f"Pal/Texture/PalIcon/Normal/T_{workspace.mod_name}_icon_normal{ext}"))

        audio_overrides = get_staged_audio_overrides(workspace)
        if audio_overrides:
            folders_to_pack.extend(audio_overrides)

        return folders_to_pack

    else:
        # =========================================================================
        # PARENT / BASE PAL MODE: PACK PARENT + ALL ENABLED CHILDREN COMBINED!
        # =========================================================================
        print(f"  [Pack Manifest] Parent mode: Bundling '{workspace.base_pal}' and all enabled child variants...", flush=True)

        # 1. Base Pal Mesh folder
        if os.path.exists(workspace.cooked_dir):
            folders_to_pack.append((workspace.cooked_dir, workspace.ue_virtual_path.replace("/Game/", "")))

        # 2. Base Pal Skeleton & Anims (if parent has anims)
        if os.path.exists(workspace.cooked_skel_dir):
            folders_to_pack.append((workspace.cooked_skel_dir, workspace.skeleton_virtual_path.replace("/Game/", "")))
        if has_anims and os.path.exists(workspace.cooked_anims_dir):
            folders_to_pack.append((workspace.cooked_anims_dir, workspace.anims_virtual_path.replace("/Game/", "")))

        # 3. Base Pal PalActorBP folder
        if os.path.exists(workspace.cooked_bp_dir):
            for cf in glob.glob(os.path.join(workspace.cooked_bp_dir, "*.*")):
                if cf.endswith((".uasset", ".uexp", ".ubulk")):
                    fn = os.path.basename(cf)
                    v_file = f"{workspace.blueprint_virtual_path.replace('/Game/', '')}/{fn}"
                    if not is_path_blacklisted(f"/Game/{v_file}", blacklist):
                        folders_to_pack.append((cf, v_file))

        # 4. DISCOVER AND BUNDLE ALL ENABLED CHILD VARIANTS!
        base_fmodel_dir = os.path.normpath(os.path.join(
            workspace.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", 
            cat_parts, workspace.base_pal
        )) if workspace.fmodel_root else ""

        ue_char_dir = os.path.normpath(os.path.join(
            workspace.project_dir, "Content", "Pal", "Model", "Character", 
            cat_parts, workspace.base_pal
        )) if workspace.project_dir else ""

        discovered_subs = set()
        if os.path.exists(ue_char_dir):
            discovered_subs.update(s for s in os.listdir(ue_char_dir) if os.path.isdir(os.path.join(ue_char_dir, s)) and not s.startswith("."))
        if os.path.exists(base_fmodel_dir):
            discovered_subs.update(s for s in os.listdir(base_fmodel_dir) if os.path.isdir(os.path.join(base_fmodel_dir, s)) and not s.startswith("."))

        from utils.sidecar_helper import load_sidecar

        for sub in sorted(list(discovered_subs)):
            if sub in skipped_variants or sub.lower() in ["sources", ".palbaker_audio"]:
                print(f"  [Packer] Skipping child variant '{sub}' (marked as skipped in .palbaker_state.json).", flush=True)
                continue

            print(f"  [Packer] Bundling enabled child variant: '{sub}'", flush=True)

            # Child variant mesh folder
            variant_rel = f"Pal/Model/Character/{category_sanitized}/{workspace.base_pal}/{sub}"
            variant_cooked = os.path.join(cooked_content, os.path.normpath(variant_rel))
            if os.path.exists(variant_cooked) and not is_path_blacklisted(f"/Game/{variant_rel}", blacklist):
                folders_to_pack.append((variant_cooked, variant_rel))

            # Check if this child variant has custom animations / dedicated skeleton
            sub_sidecar = os.path.join(base_fmodel_dir, sub, f"{sub}_blend.json")
            if not os.path.exists(sub_sidecar):
                sub_sidecar = os.path.join(base_fmodel_dir, f"{sub}_blend.json")
            sub_data = load_sidecar(sub_sidecar) if os.path.exists(sub_sidecar) else {}
            sub_has_anims = bool(sub_data.get("custom_animations", {}).get("is_active"))

            # Child variant dedicated skeleton (pack if exists)
            sub_skel_dir = os.path.join(cooked_content, "Pal", "Model", "Character", "Skeleton", workspace.base_pal, sub)
            if os.path.exists(sub_skel_dir):
                folders_to_pack.append((sub_skel_dir, f"Pal/Model/Character/Skeleton/{workspace.base_pal}/{sub}"))
                print(f"  -> Packed child variant dedicated skeleton: {sub}", flush=True)

            if sub_has_anims:

                # Child variant animations
                sub_anim_dir = os.path.join(cooked_content, "Pal", "Animation", "Character", category_sanitized, workspace.base_pal, sub)
                if os.path.exists(sub_anim_dir):
                    folders_to_pack.append((sub_anim_dir, f"Pal/Animation/Character/{category_sanitized}/{workspace.base_pal}/{sub}"))

                # Child variant PalActorBP (BP_, ABP_, BS_)
                sub_bp_dir = os.path.join(cooked_content, "Pal", "Blueprint", "Character", "Monster", "PalActorBP", workspace.base_pal, sub)
                if os.path.exists(sub_bp_dir):
                    for cf in glob.glob(os.path.join(sub_bp_dir, "*.*")):
                        if cf.endswith((".uasset", ".uexp", ".ubulk")):
                            fn = os.path.basename(cf)
                            v_rel = f"Pal/Blueprint/Character/Monster/PalActorBP/{workspace.base_pal}/{sub}/{fn}"
                            if not is_path_blacklisted(f"/Game/{v_rel}", blacklist):
                                folders_to_pack.append((cf, v_rel))

                # Child variant Waza folder
                sub_waza_dir = os.path.join(cooked_content, "Pal", "Blueprint", "Action", "Waza", sub)
                if os.path.exists(sub_waza_dir):
                    w_rel = f"Pal/Blueprint/Action/Waza/{sub}"
                    if not is_path_blacklisted(f"/Game/{w_rel}", blacklist):
                        folders_to_pack.append((sub_waza_dir, w_rel))

                # Child variant custom actions / blueprints
                bp_cooked_root = os.path.join(cooked_content, "Pal", "Blueprint")
                if os.path.exists(bp_cooked_root):
                    for root, _, files in os.walk(bp_cooked_root):
                        clean_r = root.replace("\\", "/")
                        if "PalActorBP" in clean_r or "Action/Waza" in clean_r:
                            continue
                        for file in files:
                            if sub.lower() in file.lower() and file.endswith((".uasset", ".uexp", ".ubulk")):
                                cf = os.path.join(root, file)
                                rel_bp = "Pal/Blueprint/" + os.path.relpath(cf, bp_cooked_root).replace("\\", "/")
                                if not is_path_blacklisted(f"/Game/{rel_bp}", blacklist):
                                    folders_to_pack.append((cf, rel_bp))

        # 5. Base Pal Waza and Action Blueprints
        blueprint_cooked_root = os.path.join(cooked_content, "Pal", "Blueprint")
        if os.path.exists(blueprint_cooked_root):
            waza_dir = os.path.join(blueprint_cooked_root, "Action", "Waza", workspace.mod_name)
            if os.path.exists(waza_dir):
                waza_vrel = f"Pal/Blueprint/Action/Waza/{workspace.mod_name}"
                if not is_path_blacklisted(f"/Game/{waza_vrel}", blacklist):
                    folders_to_pack.append((waza_dir, waza_vrel))

            for root, _, files in os.walk(blueprint_cooked_root):
                clean_r = root.replace("\\", "/")
                if "PalActorBP" in clean_r or "Action/Waza" in clean_r:
                    continue
                for file in files:
                    if workspace.mod_name.lower() in file.lower() and file.endswith((".uasset", ".uexp", ".ubulk")):
                        cf = os.path.join(root, file)
                        rel_bp = "Pal/Blueprint/" + os.path.relpath(cf, bp_cooked_root).replace("\\", "/")
                        if not is_path_blacklisted(f"/Game/{rel_bp}", blacklist):
                            folders_to_pack.append((cf, rel_bp))

        # Audio, CelShader, Icons
        if workspace.has_custom_shader:
            cs_dir = os.path.join(cooked_content, "CartoonCelShader", "Materials", "CelShader")
            if not is_path_blacklisted("/Game/CartoonCelShader/Materials/CelShader", blacklist):
                folders_to_pack.append((cs_dir, "CartoonCelShader/Materials/CelShader"))

        if workspace.has_icon:
            icon_base = os.path.join(cooked_content, "Pal", "Texture", "PalIcon", "Normal", f"T_{workspace.mod_name}_icon_normal")
            for ext in [".uasset", ".uexp", ".ubulk"]:
                cf = icon_base + ext
                if os.path.exists(cf):
                    folders_to_pack.append((cf, f"Pal/Texture/PalIcon/Normal/T_{workspace.mod_name}_icon_normal{ext}"))

        audio_overrides = get_staged_audio_overrides(workspace)
        if audio_overrides:
            folders_to_pack.extend(audio_overrides)

        if extra_packages:
            for pkg in extra_packages:
                if is_path_blacklisted(pkg, blacklist):
                    continue
                rel_pkg = pkg.replace("/Game/", "").replace("/", os.sep)
                cf_base = os.path.join(cooked_content, rel_pkg)
                rel_v_dir = pkg.replace("/Game/", "").rsplit("/", 1)[0]
                for ext in [".uasset", ".uexp", ".ubulk"]:
                    cand = cf_base + ext
                    if os.path.exists(cand):
                        folders_to_pack.append((cand, f"{rel_v_dir}/{os.path.basename(cand)}"))

        return folders_to_pack

def pack_cooked_assets(
    unrealpak_path: str, 
    response_file: str, 
    output_pak: str, 
    folders_to_pack: list, 
    has_anims: bool, 
    custom_blacklist: list = None, 
    is_custom_pal: bool = False,
    base_pal: str = "",
    is_variant: bool = False
) -> int:
    os.makedirs(os.path.dirname(response_file), exist_ok=True)
    if custom_blacklist is None:
        custom_blacklist = []
        
    files_found = 0
    print(f"  [Packer] Scanning {len(folders_to_pack)} folder targets for compiled assets...", flush=True)
    
    with open(response_file, "w") as f:
        for path_on_disk, relative_virtual_path in folders_to_pack:
            print(f"  [Packer] Evaluating Target: {path_on_disk}", flush=True)
            
            if os.path.exists(path_on_disk):
                if os.path.isdir(path_on_disk):
                    for root, _, files in os.walk(path_on_disk):
                        print(f"  [Packer] Walking sub-directory '{root}' (Found {len(files)} files)", flush=True)
                        for file in files:
                            if file.endswith((".uasset", ".uexp", ".ubulk")):
                                # Standalone Custom Pals MUST package their physics assets to ragdoll properly
                                if "PhysicsAsset" in file and not is_custom_pal:
                                    continue

                                # Safe Skeleton Stripping:
                                # Only strip the shared vanilla parent skeleton when no custom animations are shipped.
                                # Dedicated variant skeletons (e.g. SK_SexyAzurmane_..._Skeleton) MUST be included
                                # because the variant mesh directly depends on them!
                                if "Skeleton" in file:
                                    filename_lower = file.lower()
                                    target_base = base_pal.lower() if base_pal else ""
                                    is_root_vanilla_skel = (
                                        (filename_lower == f"sk_{target_base}_skeleton.uasset" if target_base else False) and
                                        not is_variant
                                    )
                                    if is_root_vanilla_skel and not has_anims:
                                        continue
                                    
                                abs_path = os.path.join(root, file)
                                rel_to_cooked = os.path.relpath(abs_path, path_on_disk)
                                rel_virtual_tail = relative_virtual_path + "/" + rel_to_cooked.replace("\\", "/")
                                game_virtual_path = f"/Game/{rel_virtual_tail}"
                                
                                # Evaluate user-defined custom blacklist
                                if is_path_blacklisted(game_virtual_path, custom_blacklist):
                                    print(f"  [Packer] Ignored by Blacklist: {game_virtual_path}", flush=True)
                                    continue

                                rel_virtual = "../../../Pal/Content/" + rel_virtual_tail
                                f.write(f'"{abs_path}" "{rel_virtual}"\n')
                                files_found += 1
                else:
                    game_virtual_path = f"/Game/{relative_virtual_path.replace(chr(92), '/')}"
                    if is_path_blacklisted(game_virtual_path, custom_blacklist):
                        print(f"  [Packer] Ignored standalone file by Blacklist: {game_virtual_path}", flush=True)
                        continue
                        
                    rel_virtual = "../../../Pal/Content/" + relative_virtual_path.replace("\\", "/")
                    f.write(f'"{path_on_disk}" "{rel_virtual}"\n')
                    files_found += 1
            else:
                print(f"  [Packer] Target directory does not exist on disk, skipping: {path_on_disk}", flush=True)
                                
    print(f"  [Packer] Total packable files discovered: {files_found}", flush=True)
    
    if files_found > 0:
        # 1. Ensure target directory exists (UnrealPak fails if destination directory does not exist)
        out_dir = os.path.dirname(output_pak)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # 2. Delete existing pak before writing; trigger clean file lock error if in use
        if os.path.exists(output_pak):
            try:
                os.remove(output_pak)
                print(f"Cleaned old target pak: {os.path.basename(output_pak)}", flush=True)
            except OSError as e:
                print(f"CRITICAL ERROR: File lock detected on '{os.path.basename(output_pak)}'. Please close Palworld and try again! Details: {e}", flush=True)
                sys.exit(1)

        clean_response_path = response_file.replace("\\", "/")
        cmd_pack = [
            unrealpak_path, 
            output_pak, 
            f"-Create={clean_response_path}",
            "-compress",
            "-compressionformats=Zlib"
        ]
        run_and_stream(cmd_pack)
            
    return files_found