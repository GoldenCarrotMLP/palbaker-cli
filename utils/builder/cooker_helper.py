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

def clean_cook_environment(workspace):
    for p in [workspace.output_pak_clean, workspace.output_pak_err]:
        if os.path.exists(p):
            try:
                os.remove(p)
                print(f"Cleaned old target pak: {os.path.basename(p)}", flush=True)
            except OSError:
                print(f"CRITICAL ERROR: Cannot overwrite '{os.path.basename(p)}'. Close the game!", flush=True)
                sys.exit(1)

    if os.path.exists(workspace.cooked_dir): 
        shutil.rmtree(workspace.cooked_dir, ignore_errors=True)
    if os.path.exists(workspace.cooked_skel_dir): 
        shutil.rmtree(workspace.cooked_skel_dir, ignore_errors=True)
    if os.path.exists(workspace.cooked_anims_dir): 
        shutil.rmtree(workspace.cooked_anims_dir, ignore_errors=True)
    if os.path.exists(workspace.cooked_bp_dir): 
        if not workspace.is_custom_pal:
            shutil.rmtree(workspace.cooked_bp_dir, ignore_errors=True)

def resolve_packaging_manifest(workspace, has_anims: bool) -> list[tuple[str, str]]:
    folders_to_pack = []

    # 1. Pack the primary targeted directory (whether base pal or nested mod folder)
    if os.path.exists(workspace.cooked_dir):
        folders_to_pack.append((workspace.cooked_dir, workspace.ue_virtual_path.replace("/Game/", "")))
        
    # 2. DYNAMIC RECURSIVE DISCOVERY AND GATHERING
    category_sanitized = workspace.category.replace(" ", "_")
    base_fmodel_dir = os.path.normpath(os.path.join(
        workspace.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", 
        workspace.category, workspace.base_pal
    ))
    
    if os.path.exists(base_fmodel_dir):
        for sub in os.listdir(base_fmodel_dir):
            sub_path = os.path.join(base_fmodel_dir, sub)
            if os.path.isdir(sub_path) and not sub.startswith(".") and sub.lower() != "sources":
                # Resolve cooked folders path for sub-variants inside Unreal Saved directory
                variant_rel = f"Pal/Model/Character/{category_sanitized}/{workspace.base_pal}/{sub}"
                variant_cooked_dir = os.path.join(
                    workspace.project_dir, "Saved", "Cooked", "Windows", workspace.target_project_name, 
                    "Content", os.path.normpath(variant_rel)
                )
                if os.path.exists(variant_cooked_dir):
                    folders_to_pack.append((variant_cooked_dir, variant_rel))
                    print(f"  [Recursive Pack] Bundled cooked assets for variant subfolder: {sub}", flush=True)

    if os.path.exists(workspace.cooked_skel_dir):
        folders_to_pack.append((workspace.cooked_skel_dir, workspace.skeleton_virtual_path.replace("/Game/", "")))

    if hasattr(workspace, 'cooked_bp_dir') and os.path.exists(workspace.cooked_bp_dir):
        bp_parts_found = False
        for cooked_file in glob.glob(os.path.join(workspace.cooked_bp_dir, "BP_*.*")):
            filename = os.path.basename(cooked_file)
            virtual_rel_path = workspace.blueprint_virtual_path.replace('/Game/', '')
            virtual_file = f"{virtual_rel_path}/{filename}"
            folders_to_pack.append((cooked_file, virtual_file))
            bp_parts_found = True
        if bp_parts_found:
            print(f"  -> Standalone Blueprint detected: Packing {workspace.blueprint_virtual_path} files.", flush=True)

    if has_anims:
        folders_to_pack.append((workspace.cooked_anims_dir, workspace.anims_virtual_path.replace("/Game/", "")))
        print("  -> Custom animations detected: Shipping complete Skeleton and Animations.", flush=True)
    else:
        print("  -> No custom animations: Shipping BP assets, but stripping Skeleton asset to prevent ragdoll glitches.", flush=True)

    if workspace.has_custom_shader:
        custom_shader_cooked = os.path.join(workspace.project_dir, "Saved", "Cooked", "Windows", workspace.target_project_name, "Content", "CartoonCelShader", "Materials", "CelShader")
        folders_to_pack.append((custom_shader_cooked, "CartoonCelShader/Materials/CelShader"))

    if workspace.has_icon:
        icon_cooked_base = os.path.join(workspace.project_dir, "Saved", "Cooked", "Windows", workspace.target_project_name, "Content", "Pal", "Texture", "PalIcon", "Normal", f"T_{workspace.mod_name}_icon_normal")
        icon_parts_found = False
        for ext in [".uasset", ".uexp", ".ubulk"]:
            cooked_file = icon_cooked_base + ext
            if os.path.exists(cooked_file):
                virtual_file = f"Pal/Texture/PalIcon/Normal/T_{workspace.mod_name}_icon_normal{ext}"
                folders_to_pack.append((cooked_file, virtual_file))
                icon_parts_found = True

    audio_overrides = get_staged_audio_overrides(workspace)
    if audio_overrides:
        folders_to_pack.extend(audio_overrides)

    return folders_to_pack

def pack_cooked_assets(unrealpak_path: str, response_file: str, output_pak: str, folders_to_pack: list, has_anims: bool) -> int:
    os.makedirs(os.path.dirname(response_file), exist_ok=True)
    PACKAGING_BLACKLIST = ["extra"]
    files_found = 0
    
    with open(response_file, "w") as f:
        for path_on_disk, relative_virtual_path in folders_to_pack:
            if os.path.exists(path_on_disk):
                if os.path.isdir(path_on_disk):
                    for root, _, files in os.walk(path_on_disk):
                        for file in files:
                            if file.endswith((".uasset", ".uexp", ".ubulk")):
                                if "PhysicsAsset" in file:
                                    continue
                                if "Skeleton" in file and not has_anims:
                                    continue
                                if any(term.lower() in file.lower() for term in PACKAGING_BLACKLIST):
                                    continue
                                    
                                abs_path = os.path.join(root, file)
                                rel_to_cooked = os.path.relpath(abs_path, path_on_disk)
                                rel_virtual = "../../../Pal/Content/" + relative_virtual_path + "/" + rel_to_cooked.replace("\\", "/")
                                f.write(f'"{abs_path}" "{rel_virtual}"\n')
                                files_found += 1
                else:
                    filename = os.path.basename(path_on_disk)
                    if any(term.lower() in filename.lower() for term in PACKAGING_BLACKLIST):
                        continue
                    rel_virtual = "../../../Pal/Content/" + relative_virtual_path.replace("\\", "/")
                    f.write(f'"{path_on_disk}" "{rel_virtual}"\n')
                    files_found += 1
                                
    if files_found > 0:
        clean_response_path = response_file.replace("\\", "/")
        run_and_stream([unrealpak_path, output_pak, f"-Create={clean_response_path}"])
            
    return files_found