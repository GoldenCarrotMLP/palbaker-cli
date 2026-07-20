# pythoncli/utils/scanner.py
import os
import json
import glob
from .names import get_localized_name, load_names_map
from .audio_helper import get_pal_sound_metadata
from .sidecar_helper import load_sidecar

def scan_character_folders(base_path: str, target_mod: str | None = None) -> list[dict]:
    """
    Scans exactly two levels deep: 
    Level 1: Category -> BasePal (Vanilla)
    Level 2: Category -> BasePal -> ModName (Nested Mod)
    Returns a list of dicts containing routing metadata.
    """
    discovered = []
    if not base_path or not os.path.exists(base_path):
        return discovered
        
    categories = ["Monster", "Pending Monster", "Player", "NPC", "Palmi", "Normal", "RaidMonster", "RaidBoss"]
    
    for cat in categories:
        cat_path = os.path.join(base_path, cat)
        if not os.path.exists(cat_path):
            continue
            
        for item1 in os.listdir(cat_path):
            item1_path = os.path.join(cat_path, item1)
            if not os.path.isdir(item1_path):
                continue
                
            # Level 1: Vanilla Base (e.g. Monster/Alpaca)
            if not target_mod or item1.lower() == target_mod.lower():
                has_assets_l1 = any(f.endswith(('.blend', '.uasset', '.json', '.fbx', '.psk', '.png')) for f in os.listdir(item1_path) if os.path.isfile(os.path.join(item1_path, f)))
                if has_assets_l1:
                    discovered.append({
                        "category": cat,
                        "base_pal": item1,
                        "mod_name": item1,
                        "path": os.path.abspath(item1_path)
                    })
            
            # Level 2: Nested Mod (e.g. Monster/Alpaca/Farigiraf)
            for item2 in os.listdir(item1_path):
                item2_path = os.path.join(item1_path, item2)
                if not os.path.isdir(item2_path):
                    continue
                    
                if target_mod and item2.lower() != target_mod.lower():
                    continue
                    
                has_assets_l2 = any(f.endswith(('.blend', '.uasset', '.json', '.fbx', '.psk', '.png')) for f in os.listdir(item2_path) if os.path.isfile(os.path.join(item2_path, f)))
                if has_assets_l2:
                    discovered.append({
                        "category": cat,
                        "base_pal": item1, # Parent folder is the BasePal
                        "mod_name": item2, # Child folder is the ModName
                        "path": os.path.abspath(item2_path)
                    })
                    
    return discovered

def get_mod_info(settings: dict, target_mod: str | None = None):
    fmodel_base = settings.get("fmodel_output", "")
    uproject = settings.get("uproject", "")
    palworld_exe = settings.get("palworld_exe", "")

    ue_base = ""
    if uproject and os.path.exists(uproject):
        ue_base = os.path.join(os.path.dirname(uproject), "Content", "Pal", "Model", "Character")

    fmodel_export_base = os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character") if fmodel_base else ""

    discovered_fmodel = scan_character_folders(fmodel_export_base, target_mod)
    discovered_ue = scan_character_folders(ue_base, target_mod)

    names_map = load_names_map()
    
    # Track custom pals
    creator_dir = os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Palbaker", "Creator")) if fmodel_base else ""
    custom_pals = []
    if creator_dir and os.path.exists(creator_dir):
        try:
            for f in os.listdir(creator_dir):
                if f.endswith("_creator.json"):
                    cp = f.split("_creator.json")[0]
                    if not target_mod or cp.lower() == target_mod.lower():
                        custom_pals.append(cp)
        except Exception: pass

    # --- CASE NORMALIZATION ENGINE ---
    def resolve_casing(name_str: str) -> str:
        name_lower = name_str.lower()
        for cp in custom_pals:
            if cp.lower() == name_lower:
                return cp
        for k in names_map.keys():
            if k.lower() == name_lower:
                return k
        return name_str[0].upper() + name_str[1:] if name_str else name_str

    discovered_fmodel_norm = []
    for item in discovered_fmodel:
        discovered_fmodel_norm.append({
            "category": item["category"],
            "base_pal": resolve_casing(item["base_pal"]),
            "mod_name": resolve_casing(item["mod_name"]),
            "path": item["path"]
        })

    discovered_ue_norm = []
    for item in discovered_ue:
        discovered_ue_norm.append({
            "category": item["category"],
            "base_pal": resolve_casing(item["base_pal"]),
            "mod_name": resolve_casing(item["mod_name"]),
            "path": item["path"]
        })

    merged_mods = {}
    
    # Pre-populate defaults
    if not target_mod:
        for name in names_map.keys():
            merged_mods[name] = { "base_pal": name, "mod_name": name, "category": "Monster", "fmodel_path": "", "ue_path": "" }
        for cp in custom_pals:
            if cp not in merged_mods:
                merged_mods[cp] = { "base_pal": cp, "mod_name": cp, "category": "Monster", "fmodel_path": "", "ue_path": "" }
    else:
        # Case-insensitive manual targeting fallback
        resolved_target = resolve_casing(target_mod)
        merged_mods[resolved_target] = { "base_pal": resolved_target, "mod_name": resolved_target, "category": "Monster", "fmodel_path": "", "ue_path": "" }

    for item in discovered_fmodel_norm:
        mod_name = item["mod_name"]
        if target_mod and mod_name.lower() != target_mod.lower():
            continue
        if mod_name not in merged_mods:
            merged_mods[mod_name] = { "base_pal": item["base_pal"], "mod_name": mod_name, "category": item["category"], "fmodel_path": "", "ue_path": "" }
        merged_mods[mod_name]["fmodel_path"] = item["path"]
        merged_mods[mod_name]["category"] = item["category"]
        merged_mods[mod_name]["base_pal"] = item["base_pal"]

    for item in discovered_ue_norm:
        mod_name = item["mod_name"]
        if target_mod and mod_name.lower() != target_mod.lower():
            continue
        if mod_name not in merged_mods:
            merged_mods[mod_name] = { "base_pal": item["base_pal"], "mod_name": mod_name, "category": item["category"], "fmodel_path": "", "ue_path": "" }
        merged_mods[mod_name]["ue_path"] = item["path"]
        merged_mods[mod_name]["category"] = item["category"]
        merged_mods[mod_name]["base_pal"] = item["base_pal"]

    results = []

    for mod_name, data in merged_mods.items():
        if target_mod and mod_name.lower() != target_mod.lower():
            continue

        base_pal = data["base_pal"]
        fmodel_path = data["fmodel_path"]
        ue_path = data["ue_path"]
        is_variant = (mod_name != base_pal)

        has_fmodel = bool(fmodel_path and os.path.exists(fmodel_path))
        
        has_ue = False
        if ue_path and os.path.exists(ue_path):
            if any(f.startswith("SK_") and f.endswith(".uasset") and "_PhysicsAsset" not in f for f in os.listdir(ue_path)):
                has_ue = True

        has_blend = False
        if has_fmodel:
            has_blend = any(f.endswith(".blend") for f in os.listdir(fmodel_path))

        # Check Altermatic status (Only matters for Base Pals, variants don't use the manifest natively)
        is_altermatic_active = False
        altermatic_variants = []
        if not is_variant:
            manifest_path = os.path.join(fmodel_path, f"{mod_name}_altermatic.json") if fmodel_path else ""
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        man_data = json.load(f)
                        is_altermatic_active = bool(man_data.get("is_altermatic_active", False))
                        variants_dict = man_data.get("variants", {})
                        for k, v in variants_dict.items():
                            v["label"] = k
                            altermatic_variants.append(v)
                except Exception:
                    pass

        # Check material preservation setting
        preserve_materials = True
        active_vanilla_replacer = ""
        sidecar_path = os.path.join(fmodel_path, f"{mod_name}_blend.json") if fmodel_path else ""
        if os.path.exists(sidecar_path):
            try:
                with open(sidecar_path, "r", encoding="utf-8") as f:
                    sidecar_data = json.load(f)
                    preserve_materials = sidecar_data.get("preserve_materials", True)
                    active_vanilla_replacer = sidecar_data.get("active_vanilla_replacer", "")
            except Exception:
                pass

        # State modifications tracking
        source_modified = False
        ue_modified = False
        ue_modified_files = []
        
        if has_fmodel and has_ue:
            from utils.state import is_source_modified, is_ue_modified
            source_modified = is_source_modified(fmodel_path)
            if ue_path:
                ue_modified_files = is_ue_modified(fmodel_path, ue_path)
                ue_modified = len(ue_modified_files) > 0

        # --- CENTRALIZED UNCONDITIONAL PAK SEARCH ENGINE ---
        # Search for compiled .pak files in your base Pal's directory regardless of extraction status
        active_pak_path = ""
        has_pak = False
        has_pak_err = False
        
        if palworld_exe and os.path.exists(palworld_exe):
            pak_name = base_pal if is_variant else mod_name
            pak_path = os.path.normpath(os.path.join(os.path.dirname(palworld_exe), "Pal", "Content", "Paks", "palBaker", f"{pak_name}_P.pak"))
            pak_err_path = os.path.normpath(os.path.join(os.path.dirname(palworld_exe), "Pal", "Content", "Paks", "palBaker", f"{pak_name}_err_P.pak"))
            
            has_pak = os.path.exists(pak_path)
            has_pak_err = os.path.exists(pak_err_path)
            active_pak_path = pak_path if has_pak else (pak_err_path if has_pak_err else "")

        # Pak Status Validation
        pak_status = "Unpacked"
        if active_pak_path:
            pak_mtime = os.path.getmtime(active_pak_path)
            outdated = False
            
            # Check for local file modification updates if folders are present
            if has_fmodel:
                for root, dirs, files in os.walk(fmodel_path):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for f in files:
                        if f.endswith(('.blend', '.fbx', '.png', '.json')) and os.path.getmtime(os.path.join(root, f)) > pak_mtime:
                            outdated = True
                            break
            if has_ue and not outdated and ue_path:
                for root, _, files in os.walk(ue_path):
                    for f in files:
                        if f.endswith('.uasset') and os.path.getmtime(os.path.join(root, f)) > pak_mtime:
                            outdated = True
                            break
                            
            if outdated:
                pak_status = "Outdated"
            elif has_pak_err:
                pak_status = "Packed with Errors"
            else:
                pak_status = "Packed"
        else:
            if not has_fmodel:
                if is_variant:
                    pak_status = "Unpacked"
                else:
                    pak_status = "Unextracted"

        # Badge Generation
        badges = []
        if not has_fmodel:
            if not is_variant:
                badges.append(["UNEXTRACTED", "#E53935"])
        else:
            if not has_blend:
                badges.append(["RAW", "#71717A"])
            else:
                badges.append(["SOURCE", "#0284C7"])

        if has_ue:
            badges.append(["UE ASSETS", "#EA580C"])
            if ue_modified:
                badges.append(["MODIFIED", "#D32F2F"])

        if source_modified: 
            badges.append(["SRC CHANGED", "#F59E0B"])
            
        if is_altermatic_active and not is_variant: 
            badges.append(["ALTERMATIC", "#06B6D4"])
            
        if is_variant:
            badges.append(["VARIANT", "#9333EA"])

        custom_icon_path = os.path.join(fmodel_path, f"T_{mod_name}_icon_normal.png") if fmodel_path else ""
        
        icon_path = ""
        has_icon = False

        if custom_icon_path and os.path.exists(custom_icon_path):
            icon_path = custom_icon_path
            has_icon = True
        elif not is_variant:
            # Only fall back to extracted vanilla icons if this is the base Pal
            icon_dir = os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Texture", "PalIcon", "Normal")) if fmodel_base else ""
            shared_icon_path = os.path.join(icon_dir, f"T_{mod_name}_icon_normal.png") if icon_dir else ""
            if shared_icon_path and os.path.exists(shared_icon_path):
                icon_path = shared_icon_path
                has_icon = True


        sound_meta = get_pal_sound_metadata(base_pal)
        audio_overrides = {}
        if has_fmodel:
            audio_dir = os.path.join(fmodel_path, ".palbaker_audio", "sources")
            for cry_name in ["Normal", "Joy", "Anger", "Sorrow", "Pain", "Death"]:
                if cry_name in sound_meta:
                    audio_overrides[cry_name] = None
                    for ext in [".wav", ".mp3", ".ogg"]:
                        test_path = os.path.join(audio_dir, f"{cry_name}{ext}")
                        if os.path.exists(test_path):
                            audio_overrides[cry_name] = test_path
                            break

        results.append({
            "id": mod_name,
            "name": mod_name,
            "base_pal": base_pal,
            "category": data["category"],
            "is_variant": is_variant,
            "localized_name": names_map.get(mod_name, names_map.get(base_pal, mod_name)),
            "pak_status": pak_status,
            "pak_path": active_pak_path,
            "modified": "Unknown",
            "source_ext": ".blend" if has_blend else ".psk",
            "has_fmodel": has_fmodel,
            "has_blend": has_blend,
            "has_ue": has_ue,
            "source_modified": source_modified,
            "ue_modified": ue_modified,
            "ue_modified_files": ue_modified_files,
            "has_icon": has_icon,
            "icon_path": icon_path,
            "badges": badges,
            "sound_metadata": sound_meta,
            "audio_overrides": audio_overrides,
            "is_altermatic_active": is_altermatic_active,
            "altermatic_variants": altermatic_variants,
            "preserve_materials": preserve_materials,
            "active_vanilla_replacer": active_vanilla_replacer,
            "physical_variants": [],
            "fmodel_path": fmodel_path,
            "ue_path": ue_path
        })

    normalized_results = sorted(results, key=lambda x: x["name"])
    for item in normalized_results:
        if not item["is_variant"]:
            bp = item["base_pal"]
            item["physical_variants"] = [m["name"] for m in normalized_results if m["base_pal"] == bp and m["is_variant"]]

    return normalized_results