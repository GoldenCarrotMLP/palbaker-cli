# utils/tool_cache.py
"""Content-addressed cache for PalBaker's external tools (cue4parse, UAssetGUI).

Every slow step in the pipeline is a tool call whose output depends only on its inputs:
  - cue4parse extract : game pak files + requested paths + format + mappings
  - UAssetGUI tojson  : .uasset/.uexp/.ubulk bytes + tool + mappings
  - UAssetGUI fromjson: .json bytes + tool + mappings
The cache key is a hash of exactly those inputs, so a hit can never be stale and nothing has to be
registered per feature: unchanged assets come back instantly, edited ones miss and rebuild.

Disable with PALBAKER_NO_CACHE=1. Location: PALBAKER_CACHE_DIR, else %LOCALAPPDATA%/PalBaker/cache.
"""
import hashlib
import json
import os
import shutil
import tempfile
import uuid

CACHE_VERSION = "1"
_PACKAGE_EXTS = (".uasset", ".uexp", ".ubulk", ".uptnl")
_file_hash_memo = {}
_stats = {"hit": 0, "miss": 0}


def enabled() -> bool:
    return os.environ.get("PALBAKER_NO_CACHE", "").strip() not in ("1", "true", "yes")


def cache_root() -> str:
    root = os.environ.get("PALBAKER_CACHE_DIR")
    if not root:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
        root = os.path.join(base, "PalBaker", "cache")
    return root


def stats() -> dict:
    return dict(_stats)


def file_hash(path: str) -> str:
    """sha256 of a file, memoized per process on (path, size, mtime)."""
    st = os.stat(path)
    memo_key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    cached = _file_hash_memo.get(memo_key)
    if cached:
        return cached
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _file_hash_memo[memo_key] = digest
    return digest


def make_key(kind: str, *parts) -> str:
    h = hashlib.sha256(f"{CACHE_VERSION}|{kind}".encode())
    for p in parts:
        h.update(b"\0")
        h.update(str(p).encode("utf-8", "surrogateescape"))
    return h.hexdigest()


def tool_fingerprint(exe_path: str, *extra_paths: str) -> str:
    """Hash of a tool binary (plus sibling DLLs it loads) and any data files such as Mappings.usmap."""
    parts = []
    exe_dir = os.path.dirname(os.path.abspath(exe_path))
    for p in [exe_path, *extra_paths]:
        if p and os.path.exists(p):
            parts.append(file_hash(p))
    if exe_path.lower().endswith("uassetgui.exe"):
        for dll in ("UAssetAPI.dll", "UAssetGUI.dll"):
            p = os.path.join(exe_dir, dll)
            if os.path.exists(p):
                parts.append(file_hash(p))
    return make_key("tool", *parts)


def package_files(uasset_path: str) -> list:
    """The .uasset and its existing sibling halves (.uexp, .ubulk, ...), in a fixed order."""
    stem = os.path.splitext(uasset_path)[0]
    return [stem + ext for ext in _PACKAGE_EXTS if os.path.exists(stem + ext)]


def _entry_dir(kind: str, key: str) -> str:
    return os.path.join(cache_root(), kind, key[:2], key)


def lookup(kind: str, key: str):
    """Returns the directory of a stored entry, or None."""
    if not enabled():
        return None
    d = _entry_dir(kind, key)
    if os.path.isfile(os.path.join(d, ".complete")):
        _stats["hit"] += 1
        return d
    _stats["miss"] += 1
    return None


def store(kind: str, key: str, files: dict) -> None:
    """Stores {relative_name: source_path} atomically. Failures are ignored (the cache is optional)."""
    if not enabled():
        return
    final = _entry_dir(kind, key)
    if os.path.isfile(os.path.join(final, ".complete")):
        return
    staging = f"{final}.tmp-{uuid.uuid4().hex[:8]}"
    try:
        for rel, src in files.items():
            dst = os.path.join(staging, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        with open(os.path.join(staging, ".complete"), "w") as f:
            json.dump(sorted(files), f)
        os.makedirs(os.path.dirname(final), exist_ok=True)
        shutil.rmtree(final, ignore_errors=True)
        os.replace(staging, final)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)


def restore(entry_dir: str, dest_root: str, rename: dict = None) -> list:
    """Copies a stored entry into dest_root. `rename` maps stored names to destination names."""
    with open(os.path.join(entry_dir, ".complete")) as f:
        names = json.load(f)
    written = []
    for rel in names:
        dst = os.path.join(dest_root, (rename or {}).get(rel, rel))
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        shutil.copyfile(os.path.join(entry_dir, rel), dst)
        written.append(dst)
    return written


def new_staging_dir(prefix: str) -> str:
    return tempfile.mkdtemp(prefix=f"palbaker_{prefix}_")


def clean() -> None:
    shutil.rmtree(cache_root(), ignore_errors=True)
