# utils/builder/blender_helper.py
import os
import re
import urllib.request
import zipfile
import tempfile
import shutil
import ssl
import subprocess
import sys

# Inject paths into context to allow importing from the utils package dynamically
utils_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

from blender_utils import translator

def resolve_active_addon_flag(blender_path: str, version_str: str) -> str:
    """Finds which single extension/addon folder physically exists to prevent double-registration collisions."""
    try:
        ver_val = float(version_str)
    except ValueError:
        ver_val = 4.2

    if ver_val < 4.2:
        return "io_scene_psk_psa"

    blender_dir = os.path.dirname(blender_path)
    appdata = os.environ.get("APPDATA", "")

    # Priority 1: System extensions (inside Blender install folder)
    system_ext = os.path.join(blender_dir, version_str, "extensions", "system", "io_scene_psk_psa")
    if os.path.exists(system_ext):
        return "bl_ext.system.io_scene_psk_psa"

    # Priority 2: User Default extensions (AppData)
    if appdata:
        user_ext = os.path.join(appdata, "Blender Foundation", "Blender", version_str, "extensions", "user_default", "io_scene_psk_psa")
        if os.path.exists(user_ext):
            return "bl_ext.user_default.io_scene_psk_psa"

        blender_org_ext = os.path.join(appdata, "Blender Foundation", "Blender", version_str, "extensions", "blender_org", "io_scene_psk_psa")
        if os.path.exists(blender_org_ext):
            return "bl_ext.blender_org.io_scene_psk_psa"

    return "bl_ext.system.io_scene_psk_psa"

def get_blender_version(blender_path: str) -> str:
    """Queries the Blender executable headlessly to parse its version string."""
    if not blender_path or not os.path.exists(blender_path):
        return "4.2"
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run(
            [blender_path, "-v"], 
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            errors='replace', 
            creationflags=creation_flags, 
            timeout=3
        )
        match = re.search(r"Blender\s+(\d+\.\d+)", result.stdout)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "4.2"

def get_blender_version_tuple(version_str: str) -> tuple:
    """Parses a "X.Y" version string into a (major, minor) tuple."""
    try:
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return (4, 2)

def patch_extracted_addon_files(target_addon_dir: str):
    """
    Scans the extracted addon files and automatically patches known 3rd-party API breaks
    (like 'use_auto_smooth' in 4.1+). This function is strictly idempotent and self-healing.
    It will strip out corrupted stacked 'try:' blocks from previous errors before re-applying.
    """
    print("[PalBaker] Running automated compatibility patcher on extracted addon files...", flush=True)
    for root, _, files in os.walk(target_addon_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    
                    modified = False
                    patched_lines = []
                    for line in lines:
                        # Idempotent & Self-Healing: Target lines with assignments to 'use_auto_smooth'
                        if "use_auto_smooth" in line and "=" in line:
                            # Strip out any existing 'try:' prefixes to cure stacked corruption
                            clean_code = re.sub(r'(try:\s*)+', '', line.strip())
                            indent = line[:len(line) - len(line.lstrip())]
                            
                            patched_lines.append(f"{indent}try: {clean_code}\n")
                            patched_lines.append(f"{indent}except AttributeError: pass\n")
                            modified = True
                        elif "except AttributeError: pass" in line:
                            # Skip floating except blocks left over from previous runs
                            continue
                        else:
                            patched_lines.append(line)
                    
                    if modified:
                        print(f"  Patching compat rules inside: {os.path.basename(file_path)}", flush=True)
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.writelines(patched_lines)
                except Exception as e:
                    print(f"  Warning: Failed to patch {file}: {e}", flush=True)

def _user_addon_dirs(appdata: str, version_str: str, version_val: float) -> list:
    """Per-user addon locations under AppData (no admin rights needed)."""
    base = os.path.join(appdata, "Blender Foundation", "Blender", version_str)
    if version_val >= 4.2:
        return [
            os.path.join(base, "extensions", "user_default", "io_scene_psk_psa"),
            os.path.join(base, "extensions", "blender_org", "io_scene_psk_psa"),
        ]
    return [os.path.join(base, "scripts", "addons", "io_scene_psk_psa")]

def _has_addon_files(path: str) -> bool:
    try:
        return os.path.isdir(path) and any(f.endswith(".py") for f in os.listdir(path))
    except OSError:
        return False

def _elevated_copy(src_dir: str, dst_dir: str) -> bool:
    """
    Copies src_dir into dst_dir through robocopy launched with the Windows UAC ("runas") prompt.
    Only this copy runs elevated, never PalBaker itself. Returns False if the user declines
    the prompt, elevation is unavailable, or the copy fails.
    """
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NOASYNC = 0x00000100
    SW_HIDE = 0
    ERROR_CANCELLED = 1223

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    robocopy = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "robocopy.exe")
    # Strip trailing backslashes: a backslash before a closing quote escapes the quote.
    params = f'"{src_dir.rstrip(os.sep)}" "{dst_dir.rstrip(os.sep)}" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP'

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = robocopy
    info.lpParameters = params
    info.nShow = SW_HIDE

    print("[PalBaker] Requesting administrator permission (Windows UAC prompt) to install the PSK addon into Blender's folder...", flush=True)
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        if err == ERROR_CANCELLED:
            print("[PalBaker] Administrator permission was declined.", flush=True)
        else:
            print(f"[PalBaker] Warning: Could not request administrator permission (error {err}).", flush=True)
        return False
    if not info.hProcess:
        return False
    try:
        kernel32.WaitForSingleObject(info.hProcess, 120_000)
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    finally:
        kernel32.CloseHandle(info.hProcess)
    # robocopy exit codes below 8 mean success (0-7 describe what was copied)
    if code.value >= 8:
        print(f"[PalBaker] Warning: Elevated copy failed (robocopy exit code {code.value}).", flush=True)
        return False
    return _has_addon_files(dst_dir)

def _extract_addon_zip(zip_path: str, dest_dir: str):
    """Extracts the addon package from the zip into dest_dir, flattening a nested root folder."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        namelist = zip_ref.namelist()
        addon_source_subfolder = ""
        if "__init__.py" not in namelist:
            init_paths = [f for f in namelist if f.endswith("/__init__.py")]
            if init_paths:
                init_paths.sort(key=lambda f: f.count("/"))
                addon_source_subfolder = os.path.dirname(init_paths[0])

        if not addon_source_subfolder:
            zip_ref.extractall(dest_dir)
            return
        for member in zip_ref.infolist():
            if member.filename.startswith(addon_source_subfolder + "/"):
                rel_path = os.path.relpath(member.filename, addon_source_subfolder)
                dest_file = os.path.join(dest_dir, rel_path)
                if member.is_dir():
                    os.makedirs(dest_file, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    with zip_ref.open(member) as source, open(dest_file, "wb") as target:
                        shutil.copyfileobj(source, target)

def pre_install_psk_addon(blender_path: str):
    """
    Downloads the PSK addon matching the Blender version and installs it into Blender's own
    folder. If that folder is write-protected (e.g. Program Files), asks for administrator
    permission via the Windows UAC prompt; if that is declined, installs into AppData instead.
    """
    blender_dir = os.path.dirname(blender_path)
    version_str = get_blender_version(blender_path)
    try:
        version_val = float(version_str)
    except ValueError:
        version_val = 4.2

    version_tuple = get_blender_version_tuple(version_str)

    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return

    system_addon_dir = translator.execute_with_version("get_target_addon_directory", version_tuple, blender_dir, version_str, appdata)
    user_addon_dirs = _user_addon_dirs(appdata, version_str, version_val)

    # Already installed anywhere Blender looks? Don't install a second copy (double registration).
    for existing in [system_addon_dir] + user_addon_dirs:
        if _has_addon_files(existing):
            print(f"[PalBaker] PSK Importer addon is already installed: {existing}", flush=True)
            # Execute patcher anyway to heal corrupted files from previous errors
            patch_extracted_addon_files(existing)
            return

    print(f"[PalBaker] PSK Importer addon is missing. Pre-installing version-compliant release for Blender {version_str}...", flush=True)

    url = translator.execute_with_version("get_download_url", version_tuple, version_str)

    staging_root = None
    zip_path = os.path.join(tempfile.gettempdir(), f"io_scene_psk_psa_{version_str}.zip")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )

        print(f"  Downloading: {url} -> {zip_path}", flush=True)
        with urllib.request.urlopen(req, context=ctx) as response, open(zip_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)

        # Extract and patch in a temp folder first; only the final copy may need admin rights.
        staging_root = tempfile.mkdtemp(prefix="palbaker_psk_")
        staging_dir = os.path.join(staging_root, "io_scene_psk_psa")
        _extract_addon_zip(zip_path, staging_dir)
        patch_extracted_addon_files(staging_dir)

        installed_to = None
        try:
            print(f"  Installing to: {system_addon_dir}", flush=True)
            shutil.copytree(staging_dir, system_addon_dir, dirs_exist_ok=True)
            installed_to = system_addon_dir
        except PermissionError:
            print("[PalBaker] Blender's install folder is write-protected.", flush=True)
            if _elevated_copy(staging_dir, system_addon_dir):
                installed_to = system_addon_dir

        if not installed_to:
            installed_to = user_addon_dirs[0]
            print(f"[PalBaker] Installing to the user folder instead: {installed_to}", flush=True)
            shutil.copytree(staging_dir, installed_to, dirs_exist_ok=True)

        print(f"[PalBaker] Successfully pre-installed PSK addon for Blender {version_str} in {installed_to}", flush=True)

    except Exception as e:
        print(f"ERROR: Failed to pre-install PSK addon: {e}", flush=True)
    finally:
        try: os.remove(zip_path)
        except OSError: pass
        if staging_root:
            shutil.rmtree(staging_root, ignore_errors=True)

def run_headless_blender(blender_path: str, blend_file: str | None, script_path: str, args: list) -> subprocess.CompletedProcess:
    """Executes a script inside headless Blender, loading startup files, enabling addons via CLI, and capturing output."""
    version_str = get_blender_version(blender_path)
    v_tuple = get_blender_version_tuple(version_str)

    # RULE CHECK: Only run pre-install and load addons if we are actually importing/reconstructing a PSK!
    # This prevents loading or downloading any classes during simple "Refresh Layout" operations.
    # Ensure PSK/PSA tasks include dump_anims and .psa files
    is_psk_task = (
        "blender_reconstruct.py" in script_path or 
        "blender_dump_anims.py" in script_path or 
        any(".psk" in str(arg).lower() or ".psa" in str(arg).lower() for arg in args)
    )

    cmd = [blender_path, "-b"]
    
    # Bypasses double-registration/AppData collisions entirely by running an isolated clean environment
    cmd.append("--factory-startup")

    if blend_file and blend_file.lower().endswith(".blend"):
        cmd.append(blend_file)
        
    if is_psk_task:
        pre_install_psk_addon(blender_path)
        addon_flag = resolve_active_addon_flag(blender_path, version_str)
        cmd.extend(["--addons", addon_flag])
    
    cmd.extend(["--python", script_path, "--"])
    cmd.extend(args)
    
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')