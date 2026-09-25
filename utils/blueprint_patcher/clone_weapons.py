# utils/blueprint_patcher/clone_weapons.py
import os
import json
import glob
import subprocess
import base64
from utils.extractor.core import extract_game_files
def clone_partner_weapons(json_data: dict, json_str: str, template_id: str, pal_id: str, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log, pal_data: dict = None, usmap_path: str = None, has_anims: bool = False) -> tuple[dict, str]:

    if pal_data is None:
        pal_data = {}

    coop_weapon = pal_data.get("Features", {}).get("CoopWeapon", {})
    if not coop_weapon.get("Enabled", pal_data.get("PartnerWeaponElement") is not None):
        return json_data, json_str

    target_element = coop_weapon.get("Element", pal_data.get("PartnerWeaponElement", "EPalElementType::Fire"))
    target_effect = coop_weapon.get("Effect", pal_data.get("PartnerWeaponEffectType", "EPalAdditionalEffectType::Burn"))
    target_niagara_path = coop_weapon.get("Niagara", pal_data.get("PartnerWeaponNiagara", "Pal/Content/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower"))

    target_niagara_clean = target_niagara_path.replace("\\", "/").strip("/")
    target_niagara_name = target_niagara_clean.split("/")[-1]
    target_niagara_game_pkg = "/" + target_niagara_clean.replace("Pal/Content", "Game")
    target_niagara_rel_pkg = target_niagara_clean

    mode = coop_weapon.get("Mode", "Flamethrower")
    discovered_weapons = []
    
    if mode == "Flamethrower":
        discovered_weapons.append(("/Game/Pal/Blueprint/Weapon/BP_Kitsunebi_Flamethrower", "Kitsunebi", "Flamethrower"))
    elif mode == "Launcher":
        discovered_weapons.append(("/Game/Pal/Blueprint/Weapon/BP_PenguinLauncher", "Penguin", "Launcher"))
    elif mode == "ThrowBomb":
        discovered_weapons.append(("/Game/Pal/Blueprint/Weapon/BP_ThrowElecBomb_CoopWeapon", "ThrowElecBomb", "ThrowElecBomb_CoopWeapon"))
    elif mode == "Katana":
        discovered_weapons.append(("/Game/Pal/Blueprint/Weapon/BP_SwordCutlassfish_Katana", "SwordCutlassfish", "Katana"))
    
    if not discovered_weapons:
        return json_data, json_str

    project_dir = os.path.dirname(settings.get("uproject", ""))
    project_name = os.path.splitext(os.path.basename(settings.get("uproject", "")))[0]
    weapon_cooked_dir = os.path.join(project_dir, "Saved", "Cooked", "Windows", project_name, "Content", "Pal", "Blueprint", "Weapon")
    os.makedirs(weapon_cooked_dir, exist_ok=True)

    from utils.uasset_helper import decompile_uasset, compile_uasset, sync_namemap

    for wp_pkg, source_wp_base, wp_suffix in discovered_weapons:
        wp_name = wp_pkg.split("/")[-1]
        
        new_wp_name = f"BP_{pal_id}_{wp_suffix}"
        if mode == "Launcher":
            new_wp_name = f"BP_{pal_id}_Launcher"
            
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
            log(f"  [Action: Weapon] Base weapon '{wp_name}' extraction triggered...", "standard")
            rel_core = wp_pkg.replace("/Game/", "Pal/Content/")
            extract_game_files(settings, [f"{rel_core}*"], temp_dir, format_type="raw")
            
            source_disk = None
            for root, _, files in os.walk(temp_dir):
                if f"{wp_name.lower()}.uasset" in [f.lower() for f in files]:
                    source_disk = os.path.join(root, f"{wp_name}.uasset")
                    break
                    
            source_wp_name = wp_name
            source_wp_pkg = wp_pkg
            source_rel_core = rel_core

        if not source_disk or not os.path.exists(source_disk):
            log(f"  [Action: Weapon] Error: Failed to extract weapon {wp_name}. Skipping compilation.", "error")
            continue

        temp_wp_json = os.path.join(temp_dir, f"{new_wp_name}.json")
        decompile_uasset(uasset_gui, source_disk, temp_wp_json, usmap_path)

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
        wp_content = wp_content.replace(f"/Monster/{source_wp_base}_Ice/SK_{source_wp_base}_Ice", f"/Monster/{pal_id}/SK_{pal_id}")
        wp_content = wp_content.replace(f"SkeletalMesh'SK_{source_wp_base}_Ice'", f"SkeletalMesh'SK_{pal_id}'")
        wp_content = wp_content.replace(f'"SK_{source_wp_base}_Ice"', f'"SK_{pal_id}"')
        wp_content = wp_content.replace(f"/Monster/{source_wp_base}/SK_{source_wp_base}", f"/Monster/{pal_id}/SK_{pal_id}")
        wp_content = wp_content.replace(f"SkeletalMesh'SK_{source_wp_base}'", f"SkeletalMesh'SK_{pal_id}'")
        wp_content = wp_content.replace(f'"SK_{source_wp_base}"', f'"SK_{pal_id}"')
        
        # Retargeting template_id -> pal_id in case the child had references to template
        if template_id != source_wp_base:
            wp_content = wp_content.replace(f"/Monster/{template_id}/SK_{template_id}", f"/Monster/{pal_id}/SK_{pal_id}")
            wp_content = wp_content.replace(f"SkeletalMesh'SK_{template_id}'", f"SkeletalMesh'SK_{pal_id}'")
            wp_content = wp_content.replace(f'"SK_{template_id}"', f'"SK_{pal_id}"')
        if has_anims:
            for suffix in ["Flamethrower", "Flamethrower_Fire", "Flamethrower_Fire_Start", "Launcher", "ThrowElecBomb", "Katana"]:
                wp_content = wp_content.replace(f"AM_{source_wp_base}_{suffix}", f"AM_{pal_id}_{suffix}")
                wp_content = wp_content.replace(f"AS_{source_wp_base}_{suffix}", f"AS_{pal_id}_{suffix}")
            wp_content = wp_content.replace(f"/Monster/{source_wp_base}/", f"/Monster/{pal_id}/")
            wp_content = wp_content.replace(f"/Skeleton/{source_wp_base}/", f"/Skeleton/{pal_id}/")
            wp_content = wp_content.replace(f"SK_{source_wp_base}_Skeleton", f"SK_{pal_id}_Skeleton")


        # 4 & 5. Conditional Retargeting for Customizable VFX Weapons
        if mode in ["Flamethrower", "Launcher"]:
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
            for old_elem in ["EPalElementType::Ice", "EPalElementType::Fire", "EPalElementType::Water"]:
                wp_content = wp_content.replace(old_elem, target_elem_full)
            wp_content = wp_content.replace('"Ice"', f'"{target_elem_short}"')
            wp_content = wp_content.replace('"Fire"', f'"{target_elem_short}"')
            wp_content = wp_content.replace('"Water"', f'"{target_elem_short}"')

            for old_eff in ["EPalAdditionalEffectType::Freeze", "EPalAdditionalEffectType::Burn", "EPalAdditionalEffectType::None"]:
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
                            
                            # In BP_Kitsunebi_Flamethrower child CDOs (17 bytes):
                            # Bytes 0-6 are FUnversionedHeader (NEVER mutate b_data[0..6]!)
                            # Bytes 7-10 are the Niagara PackageIndex (-15)
                            # Byte 11 is EPalElementType, Byte 12 is EPalAdditionalEffectType
                            if len(b_data) >= 13:
                                b_data[11] = elem_byte_val
                                b_data[12] = eff_byte_val
                                export["Data"] = base64.b64encode(b_data).decode('utf-8')
                                log(f"  [Action: Weapon] Safely set Element={elem_byte_val} and Effect={eff_byte_val} at bytes [11, 12].", "success")
                                    
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
        compile_uasset(uasset_gui, temp_wp_json, dest_wp_uasset, usmap_path)
        log(f"  ✓ Compiled weapon blueprint: {dest_wp_uasset}", "success")

    try:
        updated_dict = json.loads(json_str)
        return updated_dict, json_str
    except Exception:
        return json_data, json_str