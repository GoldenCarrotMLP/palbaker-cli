# utils/builder/blacklist_helper.py
import os

def get_packaging_blacklist(repo_root: str) -> set[str]:
    """
    Dynamically scans plugins/PalBakerEditorUtils/Assets/Content/ and returns 
    the set of lowercase /Game/... package paths to exclude from packaging.
    """
    blacklist = set()
    assets_dir = os.path.normpath(os.path.join(repo_root, "plugins", "PalBakerEditorUtils", "Assets", "Content"))

    if os.path.exists(assets_dir):
        for root, _, files in os.walk(assets_dir):
            for f in files:
                if f.endswith(".uasset"):
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, assets_dir).replace("\\", "/")
                    # /Game/CartoonCelShader/Materials/CelShader/M_CelShader_Base
                    pkg_path = f"/Game/{os.path.splitext(rel_path)[0]}".lower()
                    blacklist.add(pkg_path)

    # Core base materials and engines defaults
    blacklist.add("/game/pal/material/character/common/mi_pallit_characterbodybase")
    blacklist.add("/game/pal/material/character/common/mi_pallit_charactereyebase")
    blacklist.add("/game/pal/material/character/common/mi_pallit_characterhairbase")
    
    return blacklist

def is_package_blacklisted(package_name: str, blacklist: set[str], has_anims: bool = False) -> bool:
    """Evaluates whether a package path should be excluded from packaging."""
    pkg_lower = package_name.lower().strip()

    if not pkg_lower.startswith("/game/"):
        return True
    if pkg_lower.startswith("/engine/") or pkg_lower.startswith("/script/"):
        return True
    if not has_anims and "skeleton" in pkg_lower:
        return True
    if "physicsasset" in pkg_lower:
        return True
    if pkg_lower in blacklist:
        return True

    return False