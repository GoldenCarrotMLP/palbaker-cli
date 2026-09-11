# utils/blueprint_patcher/clone_weapons.py
import os
import json
import glob
import subprocess
import base64
from utils.extractor.core import extract_game_files

def clone_partner_weapons(json_data: dict, json_str: str, template_id: str, pal_id: str, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, pal_data: dict = None) -> tuple[dict, str]:
    if pal_data is None:
        pal_data = {}

    target_element = pal_data.get("PartnerWeaponElement", "EPalElementType::Fire")
    target_effect = pal_data.get("PartnerWeaponEffectType", "EPalAdditionalEffectType::Burn")
    target_niagara_path = pal_data.get("PartnerWeaponNiagara", "Pal/Content/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower")

    # Clean and resolve paths for Niagara System
    target_niagara_clean = target_niagara_path.replace("\\", "/").strip("/")
    target_niagara_name = target_niagara_clean.split("/")[-1]
    target_niagara_game_pkg = "/" + target_niagara_clean.replace("Pal/Content", "Game")
    target_niagara_rel_pkg = target_niagara_clean

    imports = json_data.get("Imports", [])
    discovered_weapons = set()

    for imp in imports:
        if imp.get("ClassName") == "Package":
            pkg_name = imp.get("ObjectName", "")
            if "/Pal/Blueprint/Weapon/" in pkg_name and template_id in pkg_name:
                discovered_weapons.add(pkg_name)

    project_dir = os.path.dirname(settings.get("uproject", ""))
    project_name = os.path.splitext(os.path.basename(settings.get("uproject", "")))[0]
    weapon_cooked_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Weapon")
    os.makedirs(weapon_cooked_dir, exist_ok=True)

    for wp_pkg in discovered_weapons:
        wp_name = wp_pkg.split("/")[-1]
        new_wp_name = wp_name.replace(template_id, pal_id)
        new_wp_pkg = f"/Game/Pal/Blueprint/Weapon/{new_wp_name}"
        new_rel_core = f"Pal/Content/Pal/Blueprint/Weapon/{new_wp_name}"

        log(f"  [Action: Weapon] Creating clean Child Blueprint for {new_wp_name}...", "standard")
        
        # 1. Extract official child template (e.g. BP_Kitsunebi_Flamethrower_ICE)
        extract_game_files(settings, [f"Pal/Content/Pal/Blueprint/Weapon/{wp_name}_ICE*"], temp_dir, format_type="raw")
        
        child_source_core = None
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.lower().endswith("_ice.uasset"):
                    child_source_core = os.path.join(root, f)
                    break
            if child_source_core:
                break

        if child_source_core and os.path.exists(child_source_core):
            source_disk = child_source_core
            source_wp_name = os.path.basename(child_source_core).replace(".uasset", "")
            source_wp_pkg = f"/Game/Pal/Blueprint/Weapon/{source_wp_name}"
            source_rel_core = f"Pal/Content/Pal/Blueprint/Weapon/{source_wp_name}"
        else:
            log(f"  [Action: Weapon] Warning: No child template found for {wp_name}.", "warning")
            rel_core = wp_pkg.replace("/Game/", "Pal/Content/")
            extract_game_files(settings, [f"{rel_core}*"], temp_dir, format_type="raw")
            source_disk = os.path.join(temp_dir, f"{wp_name}.uasset")
            source_wp_name = wp_name
            source_wp_pkg = wp_pkg
            source_rel_core = rel_core

        if not os.path.exists(source_disk):
            continue

        temp_wp_json = os.path.join(temp_dir, f"{new_wp_name}.json")
        subprocess.run([uasset_gui, "tojson", source_disk, temp_wp_json, "VER_UE5_1"], check=True, creationflags=flags)

        with open(temp_wp_json, "r", encoding="utf-8") as f_wp:
            wp_content = f_wp.read()

        # 2. Retarget Package & Class Names
        wp_content = wp_content.replace(source_wp_pkg, new_wp_pkg)
        wp_content = wp_content.replace(source_rel_core, new_rel_core)
        wp_content = wp_content.replace(f"Default__{source_wp_name}_C", f"Default__{new_wp_name}_C")
        wp_content = wp_content.replace(f"Default__{source_wp_name}", f"Default__{new_wp_name}")
        wp_content = wp_content.replace(f"{source_wp_name}_C", f"{new_wp_name}_C")
        wp_content = wp_content.replace(f'"{source_wp_name}"', f'"{new_wp_name}"')
        wp_content = wp_content.replace(f"'{source_wp_name}'", f"'{new_wp_name}'")

        # 3. Retarget Skeletal Mesh
        wp_content = wp_content.replace(f"/Monster/Kitsunebi_Ice/SK_Kitsunebi_Ice", f"/Monster/{pal_id}/SK_{pal_id}")
        wp_content = wp_content.replace(f"SkeletalMesh'SK_Kitsunebi_Ice'", f"SkeletalMesh'SK_{pal_id}'")
        wp_content = wp_content.replace('"SK_Kitsunebi_Ice"', f'"SK_{pal_id}"')
        wp_content = wp_content.replace(f"/Monster/{template_id}/SK_{template_id}", f"/Monster/{pal_id}/SK_{pal_id}")
        wp_content = wp_content.replace(f"SkeletalMesh'SK_{template_id}'", f"SkeletalMesh'SK_{pal_id}'")
        wp_content = wp_content.replace(f'"SK_{template_id}"', f'"SK_{pal_id}"')

        # 4 & 5. Conditional Retargeting for Customizable VFX Weapons
        partner_skill = pal_data.get("PartnerSkill", "")
        CUSTOMIZABLE_WEAPONS = [
            "PartnerSkill_Kitsunebi", "Flamethrower",
            "PartnerSkill_Penguin", "Launcher",
            "PartnerSkill_Monkey", "AssaultRifle", "Rifle",
            "PartnerSkill_Carbunclo", "SubmachineGun", "Submachinegun",
            "PartnerSkill_Grizzbolt", "HeavyWeapon", "Minigun"
        ]
        
        if partner_skill in CUSTOMIZABLE_WEAPONS:
            # Retarget Niagara Effect
            wp_content = wp_content.replace("Pal/Content/Pal/Effect/Skill/FrostBreath/NS_CommonSkill_FrostBreath", target_niagara_rel_pkg)
            wp_content = wp_content.replace("/Game/Pal/Effect/Skill/FrostBreath/NS_CommonSkill_FrostBreath", target_niagara_game_pkg)
            wp_content = wp_content.replace("NS_CommonSkill_FrostBreath", target_niagara_name)
    
            wp_content = wp_content.replace("Pal/Content/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower", target_niagara_rel_pkg)
            wp_content = wp_content.replace("/Game/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower", target_niagara_game_pkg)
            wp_content = wp_content.replace("NS_CommonSkill_Flamethrower", target_niagara_name)

            # Mutate Element & Effect Enums safely
            target_elem_short = target_element.split("::")[-1] if "::" in target_element else target_element
            target_eff_short = target_effect.split("::")[-1] if "::" in target_effect else target_effect
            target_elem_full = f"EPalElementType::{target_elem_short}"
            target_eff_full = f"EPalAdditionalEffectType::{target_eff_short}"

            # Tier A: Direct String Replacements
            for old_elem in ["EPalElementType::Ice", "EPalElementType::Fire"]:
                wp_content = wp_content.replace(old_elem, target_elem_full)
            wp_content = wp_content.replace('"Ice"', f'"{target_elem_short}"')
            wp_content = wp_content.replace('"Fire"', f'"{target_elem_short}"')

            for old_eff in ["EPalAdditionalEffectType::Freeze", "EPalAdditionalEffectType::Burn"]:
                wp_content = wp_content.replace(old_eff, target_eff_full)
            wp_content = wp_content.replace('"Freeze"', f'"{target_eff_short}"')
            wp_content = wp_content.replace('"Burn"', f'"{target_eff_short}"')

            # Tier B: Base64 Unversioned Binary Patching (For RawExport CDOs)
            try:
                wp_dict = json.loads(wp_content)
                
                elem_int_map = {
                    "None": 0, "Normal": 1, "Fire": 2, "Water": 3, "Leaf": 4, 
                    "Electricity": 5, "Ice": 6, "Earth": 7, "Dark": 8, "Dragon": 9
                }
                eff_int_map = {
                    "None": 0, "Stun": 1, "Sleep": 2, "Poison": 3, "Burn": 4, 
                    "Wetness": 5, "Freeze": 6, "Electrical": 7, "Muddy": 8, 
                    "IvyCling": 9, "Darkness": 10, "AttackUp": 11, "DefenseUp": 12, "Recovery": 13, "Trap_LegHold": 14
                }
                
                elem_byte_val = elem_int_map.get(target_elem_short, 1)
                eff_byte_val = eff_int_map.get(target_eff_short, 0)
                
                for export in wp_dict.get("Exports", []):
                    if export.get("ObjectName") == f"Default__{new_wp_name}_C":
                        b64_data = export.get("Data")
                        
                        # Base64 Raw Export Scenario
                        if isinstance(b64_data, str):
                            b_data = bytearray(base64.b64decode(b64_data))
                            
                            # Search the last 8 bytes of the CDO for the exact ICE [06, 06] or FIRE [02, 04] signature
                            # This bypasses all length discrepancies across different game versions
                            for i in range(max(0, len(b_data) - 8), len(b_data) - 1):
                                if (b_data[i] == 0x06 and b_data[i+1] == 0x06) or (b_data[i] == 0x02 and b_data[i+1] == 0x04):
                                    b_data[i] = elem_byte_val
                                    b_data[i+1] = eff_byte_val
                                    export["Data"] = base64.b64encode(b_data).decode('utf-8')
                                    log(f"  [Action: Weapon] Mutated Base64 sequence to Element: {elem_byte_val}, Effect: {eff_byte_val}", "success")
                                    break
                                    
                        # Normal Export Scenario (List of properties)
                        elif isinstance(b64_data, list):
                            for prop in b64_data:
                                if isinstance(prop, dict):
                                    prop_name = str(prop.get("Name", "")).lower()
                                    if prop_name == "element":
                                        if "Value" in prop and isinstance(prop["Value"], str):
                                            prop["Value"] = target_elem_full if "::" in prop["Value"] else target_elem_short
                                        elif "Value" in prop and isinstance(prop["Value"], (int, float)):
                                            prop["Value"] = elem_byte_val
                                    elif "effect" in prop_name and "type" in prop_name:
                                        if "Value" in prop and isinstance(prop["Value"], str):
                                            prop["Value"] = target_eff_full if "::" in prop["Value"] else target_eff_short
                                        elif "Value" in prop and isinstance(prop["Value"], (int, float)):
                                            prop["Value"] = eff_byte_val
                                            
                wp_content = json.dumps(wp_dict, indent=4)
            except Exception as e:
                log(f"  [Action: Weapon] Warning during Base64 CDO patch: {e}", "warning")

        with open(temp_wp_json, "w", encoding="utf-8") as f_wp:
            f_wp.write(wp_content)

        dest_wp_uasset = os.path.join(weapon_cooked_dir, f"{new_wp_name}.uasset")
        subprocess.run([uasset_gui, "fromjson", temp_wp_json, dest_wp_uasset], check=True, creationflags=flags)
        log(f"  ✓ Compiled weapon blueprint with customized VFX ({target_niagara_name}): {dest_wp_uasset}", "success")

        # 6. Retarget parent character blueprint
        json_str = json_str.replace(wp_pkg, new_wp_pkg)
        json_str = json_str.replace(f"'{wp_name}_C'", f"'{new_wp_name}_C'")
        json_str = json_str.replace(f'"{wp_name}_C"', f'"{new_wp_name}_C"')
        json_str = json_str.replace(f'"{wp_name}"', f'"{new_wp_name}"')

    try:
        updated_dict = json.loads(json_str)
        return updated_dict, json_str
    except Exception:
        return json_data, json_str