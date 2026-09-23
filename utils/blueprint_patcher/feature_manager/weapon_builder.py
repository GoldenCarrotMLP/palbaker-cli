# utils/blueprint_patcher/feature_manager/weapon_builder.py
"""
====================================================================================================
               STANDALONE PARTNER WEAPON CLUSTER SYNTHESIZER (WEAPON BUILDER)
====================================================================================================

OVERVIEW:
---------
Synthesizes the complete multi-asset cluster required for partner weapons:
1. Three standalone partner skill montages:
   • AM_<Pal>_Flamethrower             (Idle hold loop)
   • AM_<Pal>_Flamethrower_Fire_Start  (Initial trigger windup)
   • AM_<Pal>_Flamethrower_Fire        (Continuous firing & damage tick loop)
2. Standalone weapon actor blueprint:
   • BP_<Pal>_Flamethrower
     - Retargets internal puppet mesh to SK_<Pal>
     - Retargets Niagara particle system to custom VFX (e.g. FrostBreath, Electric, Dark)
     - Retargets bytecode montage calls to the newly synthesized montages
     - Remaps muzzle raycast socket (Socket_Mouth, head, etc.) and player hold socket
     - Patches damage element and status effect byte properties in the CDO
====================================================================================================
"""

import json
import base64
import re
from utils.uasset_helper import sync_namemap, patch_montage_ast

ELEMENT_MAP = {
    "None": 0, "Normal": 1, "Fire": 2, "Water": 3, "Leaf": 4,
    "Electricity": 5, "Ice": 6, "Earth": 7, "Dark": 8, "Dragon": 9
}

EFFECT_MAP = {
    "None": 0, "Stun": 1, "Sleep": 2, "Poison": 3, "Burn": 4,
    "Wetness": 5, "Freeze": 6, "Electrical": 7, "Muddy": 8,
    "IvyCling": 9, "Darkness": 10, "AttackUp": 11, "DefenseUp": 12, "Recovery": 13, "Trap_LegHold": 14
}

def synthesize_flamethrower_cluster(
    seed_weapon_data: dict,
    seed_montages: dict,
    pal_id: str,
    template_id: str = "Kitsunebi",
    skeleton_guid: str = "BF21DEE0-4BCF0A09-60C97DA1-367595A0",
    config: dict = None
) -> dict:
    """
    Synthesizes the complete multi-asset weapon cluster for a partner weapon:
    Returns: {
        "weapon_bp": dict (AST of BP_<Pal>_Flamethrower),
        "montages": {
            f"AM_{pal_id}_Flamethrower": dict,
            f"AM_{pal_id}_Flamethrower_Fire_Start": dict,
            f"AM_{pal_id}_Flamethrower_Fire": dict
        }
    }
    """
    cfg = config or {}
    element_str = cfg.get("element", "Fire").replace("EPalElementType::", "")
    effect_str = cfg.get("effect", "Burn").replace("EPalAdditionalEffectType::", "")
    niagara_path = cfg.get("niagara_system", "/Game/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower")
    muzzle_socket = cfg.get("muzzle_socket", "Socket_Mouth")
    equip_socket = cfg.get("equip_socket", "Socket_Weapon_R")

    elem_byte = ELEMENT_MAP.get(element_str, 2)
    eff_byte = EFFECT_MAP.get(effect_str, 4)

    # -------------------------------------------------------------------------
    # 1. Synthesize the 3 Partner Skill Montages
    # -------------------------------------------------------------------------
    synthesized_montages = {}

    montage_configs = [
        ("idle", f"AM_{pal_id}_Flamethrower", "Flamethrower"),
        ("start", f"AM_{pal_id}_Flamethrower_Fire_Start", "Flamethrower_Fire_Start"),
        ("loop", f"AM_{pal_id}_Flamethrower_Fire", "Flamethrower_Fire")
    ]

    for key, target_montage_name, sub_name in montage_configs:
        seed_ast = seed_montages.get(key)
        if seed_ast:
            mutated_ast = patch_montage_ast(
                seed_ast,
                template_id=template_id,
                target_pal=pal_id,
                skeleton_guid=skeleton_guid
            )
            # Ensure ObjectName matches target
            mutated_ast["Exports"][0]["ObjectName"] = target_montage_name
            sync_namemap(mutated_ast)
            synthesized_montages[target_montage_name] = mutated_ast

    # -------------------------------------------------------------------------
    # 2. Synthesize Weapon Actor Blueprint (BP_<Pal>_Flamethrower)
    # -------------------------------------------------------------------------
    raw_str = json.dumps(seed_weapon_data)

    # 2a. Package and Class Names
    old_pkg = f"/Game/Pal/Blueprint/Weapon/BP_{template_id}_Flamethrower"
    new_pkg = f"/Game/Pal/Blueprint/Weapon/BP_{pal_id}_Flamethrower"
    raw_str = raw_str.replace(old_pkg, new_pkg)

    raw_str = raw_str.replace(f"BP_{template_id}_Flamethrower_C", f"BP_{pal_id}_Flamethrower_C")
    raw_str = raw_str.replace(f"BP_{template_id}_Flamethrower", f"BP_{pal_id}_Flamethrower")
    raw_str = raw_str.replace(f"Default__BP_{template_id}_Flamethrower_C", f"Default__BP_{pal_id}_Flamethrower_C")
    raw_str = raw_str.replace(f"ExecuteUbergraph_BP_{template_id}_Flamethrower", f"ExecuteUbergraph_BP_{pal_id}_Flamethrower")

    # 2b. Internal Puppet Mesh
    raw_str = raw_str.replace(
        f"/Game/Pal/Model/Character/Monster/{template_id}/SK_{template_id}",
        f"/Game/Pal/Model/Character/Monster/{pal_id}/SK_{pal_id}"
    )
    raw_str = raw_str.replace(f'"SK_{template_id}"', f'"SK_{pal_id}"')
    raw_str = raw_str.replace(f"'SK_{template_id}'", f"'SK_{pal_id}'")

    # 2c. Montages and Sequence references in Imports & Bytecode
    for suffix in ["Flamethrower", "Flamethrower_Fire", "Flamethrower_Fire_Start"]:
        raw_str = raw_str.replace(f"AM_{template_id}_{suffix}", f"AM_{pal_id}_{suffix}")
        raw_str = raw_str.replace(f"AS_{template_id}_{suffix}", f"AS_{pal_id}_{suffix}")
    raw_str = raw_str.replace(f"/Monster/{template_id}/", f"/Monster/{pal_id}/")

    # 2d. Custom Sockets
    if muzzle_socket != "Socket_Mouth":
        raw_str = raw_str.replace('"Socket_Mouth"', f'"{muzzle_socket}"')
    if equip_socket != "Socket_Weapon_R":
        raw_str = raw_str.replace('"Socket_Weapon_R"', f'"{equip_socket}"')

    # 2e. Custom Niagara VFX System
    default_vfx_pkg = "/Game/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower"
    default_vfx_name = "NS_CommonSkill_Flamethrower"
    if niagara_path != default_vfx_pkg:
        clean_vfx_pkg = niagara_path.rsplit(".", 1)[0]
        clean_vfx_name = clean_vfx_pkg.split("/")[-1]
        raw_str = raw_str.replace(default_vfx_pkg, clean_vfx_pkg)
        raw_str = raw_str.replace(f'"{default_vfx_name}"', f'"{clean_vfx_name}"')

    weapon_ast = json.loads(raw_str)

    # --- CRITICAL FIX: Re-link Component Pointers ---
    skel_mesh_idx = None
    niagara_idx = None
    
    for i, imp in enumerate(weapon_ast.get("Imports", [])):
        if imp.get("ClassName") == "SkeletalMesh" and pal_id.lower() in imp.get("ObjectName", "").lower():
            skel_mesh_idx = -(i + 1)
        elif imp.get("ClassName") == "NiagaraSystem" and target_niagara_name.lower() in imp.get("ObjectName", "").lower():
            niagara_idx = -(i + 1)

    # -------------------------------------------------------------------------
    # 3. Patch CDO Element & Status Effect
    # -------------------------------------------------------------------------
    for export in weapon_ast.get("Exports", []):
        obj_name = export.get("ObjectName", "")

        # Repair broken pointers due to shifted import arrays
        if obj_name == "Mesh_GEN_VARIABLE" and skel_mesh_idx:
            for p in export.get("Data", []):
                if p.get("Name") in ["SkeletalMesh", "SkinnedAsset"]:
                    p["Value"] = skel_mesh_idx
                    
        elif obj_name == "MuzzleEffect_GEN_VARIABLE" and niagara_idx:
            for p in export.get("Data", []):
                if p.get("Name") == "Asset":
                    p["Value"] = niagara_idx

        # CDO Export (Default__BP_<Pal>_Flamethrower_C)
        if obj_name.startswith("Default__BP_") and obj_name.endswith("_Flamethrower_C"):
            # Case A: RawExport (Base64 Bytecode Data)
            if export.get("$type", "").endswith("RawExport, UAssetAPI"):
                b64_data = export.get("Data", "")
                if isinstance(b64_data, str) and b64_data:
                    b_data = bytearray(base64.b64decode(b64_data))
                    for i in range(max(0, len(b_data) - 24), len(b_data) - 1):
                        # Detect [0x02, 0x04] (Fire, Burn) or [0x06, 0x06] (Ice, Freeze) signatures
                        if (b_data[i] in [0x02, 0x06]) and (b_data[i + 1] in [0x04, 0x06]):
                            b_data[i] = elem_byte
                            b_data[i + 1] = eff_byte
                            export["Data"] = base64.b64encode(b_data).decode('utf-8')
                            break

            # Case B: NormalExport (Property List)
            elif isinstance(export.get("Data"), list):
                for prop in export["Data"]:
                    if isinstance(prop, dict):
                        p_name = prop.get("Name", "").lower()
                        if p_name == "element":
                            prop["Value"] = f"EPalElementType::{element_str}"
                        elif "effect" in p_name and "type" in p_name:
                            prop["Value"] = f"EPalAdditionalEffectType::{effect_str}"

    sync_namemap(weapon_ast)

    return {
        "weapon_bp": weapon_ast,
        "montages": synthesized_montages
    }