# utils/extractor/core.py
import os
import sys
import shutil
import subprocess
import glob
from .paths import get_paks_dir
from utils import tool_cache


def _pak_identity(paks_dir: str) -> list:
    # Hashing multi-GB paks per call is too slow; name + size + mtime changes on every game update.
    ident = []
    for filepath in sorted(glob.glob(os.path.join(paks_dir, "Pal-Windows*"))):
        st = os.stat(filepath)
        ident.append(f"{os.path.basename(filepath)}:{st.st_size}:{st.st_mtime_ns}")
    return ident

def extract_game_files(settings: dict, relative_paths: list[str], output_dir: str, format_type: str = "raw") -> tuple[bool, str]:
    """Runs cue4parse.exe to headlessly extract a list of game files from Palworld .pak archives."""
    palworld_exe = settings.get("palworld_exe", "")
    paks_dir = get_paks_dir(palworld_exe)
    if not paks_dir or not os.path.exists(paks_dir):
        return False, f"Paks directory not found or Palworld.exe path is invalid: {paks_dir}"

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cue4parse_exe = os.path.normpath(os.path.join(repo_root, "deps", "cue4parse.exe"))
    usmap_path = os.path.normpath(os.path.join(repo_root, "deps", "Mappings.usmap"))

    # Same game paks + same request = same files (see utils/tool_cache.py)
    cache_key = None
    if os.path.exists(cue4parse_exe) and os.path.exists(usmap_path):
        cache_key = tool_cache.make_key(
            "extract", tool_cache.tool_fingerprint(cue4parse_exe, usmap_path), "GAME_UE5_1", format_type,
            *_pak_identity(paks_dir), "|", *sorted(relative_paths)
        )
        hit = tool_cache.lookup("extract", cache_key)
        if hit:
            os.makedirs(output_dir, exist_ok=True)
            tool_cache.restore(hit, output_dir)
            return True, "Extraction restored from cache."

    isolated_dir = os.path.join(paks_dir, ".temp_palbaker_isolate")
    shutil.rmtree(isolated_dir, ignore_errors=True)
    os.makedirs(isolated_dir, exist_ok=True)
    
    files_linked = 0
    official_patterns = ["Pal-Windows*"]
    for pattern in official_patterns:
        for filepath in glob.glob(os.path.join(paks_dir, pattern)):
            if os.path.isfile(filepath):
                filename = os.path.basename(filepath)
                dest_link = os.path.join(isolated_dir, filename)
                try:
                    if hasattr(os, "link"):
                        os.link(filepath, dest_link)
                        files_linked += 1
                except Exception:
                    pass
                    
    active_input_dir = isolated_dir if files_linked > 0 else paks_dir

    if not os.path.exists(cue4parse_exe):
        shutil.rmtree(isolated_dir, ignore_errors=True)
        return False, f"Missing cue4parse.exe dependency at {cue4parse_exe}"
    if not os.path.exists(usmap_path):
        shutil.rmtree(isolated_dir, ignore_errors=True)
        return False, f"Missing Mappings.usmap dependency at {usmap_path}"

    os.makedirs(output_dir, exist_ok=True)
    # Extract into a clean staging folder so exactly this request's files are copied out and cached
    staging_dir = tool_cache.new_staging_dir("extract")

    cmd = [
        cue4parse_exe,
        "-i", active_input_dir,
        "-o", staging_dir,
        "-m", usmap_path,
        "-g", "GAME_UE5_1",
        "-f", format_type,
        "-y"
    ]

    for rel_path in relative_paths:
        cmd.extend(["-p", rel_path])

    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
        shutil.rmtree(isolated_dir, ignore_errors=True)

        if result.returncode != 0:
            error_details = result.stderr or result.stdout
            return False, f"cue4parse exited with code {result.returncode}. Details: {error_details}"

        produced = {}
        for root, _, files in os.walk(staging_dir):
            for name in files:
                src = os.path.join(root, name)
                rel = os.path.relpath(src, staging_dir)
                dst = os.path.join(output_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
                produced[rel] = src
        if cache_key:
            tool_cache.store("extract", cache_key, produced)
        return True, "Extraction completed successfully."
    except Exception as e:
        shutil.rmtree(isolated_dir, ignore_errors=True)
        return False, f"Failed to execute cue4parse.exe process: {e}"
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

def extract_single_file(settings: dict, relative_path: str, output_dir: str) -> bool:
    """Helper wrapper to extract a single file directly from paks."""
    success, msg = extract_game_files(settings, [relative_path], output_dir)
    if not success:
        print(f"[Extractor Helper] Extraction failed for {relative_path}: {msg}", flush=True)
    return success