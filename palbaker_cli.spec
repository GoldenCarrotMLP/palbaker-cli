# pythoncli/palbaker_cli.spec
# -*- mode: python ; coding: utf-8 -*-

import os

# Define the explicit raw files and folders PyInstaller must bundle into the executable folder
datas = [
    ('plugins', 'plugins'),
    ('deps', 'deps'),
    ('unreal_scripts', 'unreal_scripts'),
    ('utils', 'utils'),
    ('assets', 'assets'),
    ('templates', 'templates'),
    ('ue_import.py', '.'),
    ('ue_export.py', '.')
]

# Dynamically include database JSONs if they have been built locally
if os.path.exists('traits_db.json'):
    datas.append(('traits_db.json', '.'))

a = Analysis(
    ['palbaker_cli.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'uuid',
        'socket',
        'select',
        'struct',
        'logging'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Prevent PyInstaller from aggressively duplicating 'deps' binaries into the root directory
# Instead of deleting them, we remap their destination paths to safely land inside the _internal/deps folder!
repo_root = os.path.abspath(SPECPATH)
deps_dir = os.path.join(repo_root, 'deps')

filtered_binaries = []
for b in a.binaries:
    dest, src, typecode = b
    src_abs = os.path.abspath(src)
    if src_abs.startswith(deps_dir):
        # Remap the destination to preserve the directory structure inside _internal/deps
        rel_dest = os.path.relpath(src_abs, repo_root).replace("\\", "/")
        filtered_binaries.append((rel_dest, src, typecode))
    else:
        filtered_binaries.append(b)
        
a.binaries = filtered_binaries

# Drop dev-only payload from the bundled data folders: debug symbols, IntelliSense docs,
# the unused deps/Mappings/ duplicate (code reads deps/Mappings.usmap), and Python bytecode caches.
def _is_shipped_data(dest):
    d = dest.replace("\\", "/").lower()
    if d.endswith((".pdb", ".pyc")) or "/__pycache__/" in d:
        return False
    if d == "deps/uassetapi.xml":  # Wwise ships real .xml configs, so only drop this one
        return False
    if d.startswith("deps/mappings/"):
        return False
    return True

a.datas = [entry for entry in a.datas if _is_shipped_data(entry[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='palbaker_cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='palbaker_cli',
)