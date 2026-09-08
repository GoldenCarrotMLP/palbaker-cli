# unreal_scripts/dependency_crawler.py
import unreal  # type: ignore
import json
import os
import tempfile

def crawl_dependencies():
    temp_dir = tempfile.gettempdir()
    cfg_path = os.path.join(temp_dir, "palbaker_crawler_config.json")
    out_path = os.path.join(temp_dir, "palbaker_crawler_result.json")

    if not os.path.exists(cfg_path):
        print(f"[PalBaker Crawler] Error: Config missing at {cfg_path}", flush=True)
        return

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    root_packages = cfg.get("root_packages", [])
    blacklist = set(p.lower() for p in cfg.get("blacklist", []))
    has_anims = cfg.get("has_anims", False)

    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    ar.scan_paths_synchronous(["/Game"], True)

    options = unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=True,
        include_hard_package_references=True,
        include_searchable_names=False
    )

    visited = set()
    to_visit = list(root_packages)
    discovered = set()

    while to_visit:
        curr_pkg = to_visit.pop(0)
        if curr_pkg in visited:
            continue
        visited.add(curr_pkg)

        deps = ar.get_dependencies(curr_pkg, options)
        if deps is None:
            continue

        for dep in deps:
            dep_str = str(dep)
            dep_lower = dep_str.lower()

            if not dep_str.startswith("/Game/"):
                continue
            if dep_lower.startswith("/engine/") or dep_lower.startswith("/script/"):
                continue
            if not has_anims and "skeleton" in dep_lower:
                continue
            if "physicsasset" in dep_lower:
                continue
            if dep_lower in blacklist:
                continue

            discovered.add(dep_str)
            if dep_str not in visited:
                to_visit.append(dep_str)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sorted(list(discovered)), f, indent=4)

    print(f"[PalBaker Crawler] Discovered {len(discovered)} external dependency packages.", flush=True)

crawl_dependencies()