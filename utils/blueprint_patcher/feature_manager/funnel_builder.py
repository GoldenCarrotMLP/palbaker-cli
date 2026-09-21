# utils/blueprint_patcher/feature_manager/funnel_builder.py
"""
====================================================================================================
               STANDALONE SATELLITE CHARACTER SYNTHESIZER (FUNNEL BUILDER)
====================================================================================================

OVERVIEW:
---------
Synthesizes a brand-new standalone satellite minion actor blueprint (BP_FunnelCharacter_<Pal_ID>)
from a seed template (BP_FunnelCharacter_DreamDemon). Allows turning ANY Pal into an orbiting
companion minion with:
  • Retargeted SkeletalMesh (SK_<Pal>)
  • Retargeted Animation Blueprint (ABP_<Pal>_C)
  • Retargeted Locomotion BlendSpace (BS_Move_<Pal>)
  • Calibrated capsule height, radius, and vertical Z-offset
  • Configurable targeting ballistics (ShadowBall, Thunderbolt, SeedMachinegun)
====================================================================================================
"""

import json
import re
from utils.uasset_helper import sync_namemap

TARGETING_ACTION_PRESETS = {
    "ShadowBall": {
        "pkg": "/Game/Pal/Blueprint/Funnel/ReticleTargetAttack/BP_AIActionFunnelSkill_ShadowBall",
        "class": "BP_AIActionFunnelSkill_ShadowBall_C"
    },
    "Thunderbolt": {
        "pkg": "/Game/Pal/Blueprint/Funnel/ReticleTargetAttack/BP_AIActionFunnelSkill_Thunderbolt",
        "class": "BP_AIActionFunnelSkill_Thunderbolt_C"
    },
    "SeedMachinegun": {
        "pkg": "/Game/Pal/Blueprint/Funnel/ReticleTargetAttack/BP_AIActionFunnelSkill_SeedMachinegun",
        "class": "BP_AIActionFunnelSkill_SeedMachinegun_C"
    }
}

def synthesize_funnel_character_ast(
    seed_funnel_data: dict,
    target_pal_id: str,
    template_pal_id: str | None = None,
    targeting_action: str = "ShadowBall",
    mesh_capsule_half_height: float | None = None,
    mesh_capsule_radius: float | None = None,
    mesh_z_offset: float | None = None,
    custom_targeting_action_pkg: str | None = None,
    custom_targeting_action_class: str | None = None
) -> dict:
    """
    Synthesizes a standalone BP_FunnelCharacter_<Pal_ID> AST from seed template data.
    Ensures that mesh, anim blueprint, blendspaces, capsule sizes, and targeting AI actions
    are properly configured and linked.
    """
    template_id = template_pal_id or target_pal_id
    raw_str = json.dumps(seed_funnel_data)

    # 1. Retarget Package & Class Names
    old_pkg = "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_DreamDemon"
    new_pkg = f"/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_{target_pal_id}"
    raw_str = raw_str.replace(old_pkg, new_pkg)

    raw_str = raw_str.replace("BP_FunnelCharacter_DreamDemon_C", f"BP_FunnelCharacter_{target_pal_id}_C")
    raw_str = raw_str.replace("BP_FunnelCharacter_DreamDemon", f"BP_FunnelCharacter_{target_pal_id}")

    # 2. Retarget Mesh
    raw_str = raw_str.replace("/Model/Character/Monster/DreamDemon/SK_DreamDemon", f"/Model/Character/Monster/{target_pal_id}/SK_{target_pal_id}")
    raw_str = raw_str.replace("SK_DreamDemon", f"SK_{target_pal_id}")

    # 3. Retarget Animation Blueprint & Locomotion BlendSpace
    raw_str = raw_str.replace("/PalActorBP/DreamDemon/ABP_DreamDemon", f"/PalActorBP/{template_id}/ABP_{template_id}")
    raw_str = raw_str.replace("ABP_DreamDemon_C", f"ABP_{template_id}_C")
    raw_str = raw_str.replace("ABP_DreamDemon", f"ABP_{template_id}")
    raw_str = raw_str.replace("/PalActorBP/DreamDemon/BS_Move_DreamDemon", f"/PalActorBP/{template_id}/BS_Move_{template_id}")
    raw_str = raw_str.replace("BS_Move_DreamDemon", f"BS_Move_{template_id}")

    # 4. Retarget Attack & Locomotion Montages (AM_DreamDemon_* -> AM_<template>_*)
    raw_str = raw_str.replace("/Animation/Character/Monster/DreamDemon/AM_DreamDemon_", f"/Animation/Character/Monster/{template_id}/AM_{template_id}_")
    raw_str = raw_str.replace("AM_DreamDemon_", f"AM_{template_id}_")

    # 5. Retarget Targeting AI Action Class
    target_action = TARGETING_ACTION_PRESETS.get(targeting_action, TARGETING_ACTION_PRESETS["ShadowBall"])
    new_action_pkg = custom_targeting_action_pkg or target_action["pkg"]
    new_action_class = custom_targeting_action_class or target_action["class"]

    old_action_pkg = "/Game/Pal/Blueprint/Funnel/ReticleTargetAttack/BP_AIActionFunnelSkill_ShadowBall"
    old_action_class = "BP_AIActionFunnelSkill_ShadowBall_C"

    if new_action_pkg != old_action_pkg or new_action_class != old_action_class:
        raw_str = raw_str.replace(old_action_pkg, new_action_pkg)
        raw_str = raw_str.replace(old_action_class, new_action_class)
        raw_str = raw_str.replace("BP_AIActionFunnelSkill_ShadowBall", new_action_class.replace("_C", ""))

    data = json.loads(raw_str)

    # --- CRITICAL FIX: Re-link Component Pointers ---
    # String replacements can shift UAssetAPI import indices, causing D3D11 crashes if SkeletalMesh points to a Class/Package.
    skel_mesh_idx = None
    anim_class_idx = None
    
    for i, imp in enumerate(data.get("Imports", [])):
        if imp.get("ClassName") == "SkeletalMesh" and target_pal_id.lower() in imp.get("ObjectName", "").lower():
            skel_mesh_idx = -(i + 1)
        elif imp.get("ClassName") == "AnimBlueprintGeneratedClass" and imp.get("ObjectName", "").endswith("_C") and template_id.lower() in imp.get("ObjectName", "").lower():
            anim_class_idx = -(i + 1)

    # 6. Apply Custom Physical Dimensions & Z-Offsets
    for exp in data.get("Exports", []):
        obj_name = exp.get("ObjectName", "")

        # CharacterMesh0: adjust relative Z-offset and repair broken pointers
        if obj_name == "CharacterMesh0":
            props = exp.get("Data", [])
            for p in props:
                p_name = p.get("Name")
                if p_name in ["SkeletalMesh", "SkinnedAsset"] and skel_mesh_idx:
                    p["Value"] = skel_mesh_idx
                elif p_name == "AnimClass" and anim_class_idx:
                    p["Value"] = anim_class_idx
                elif p_name == "RelativeLocation":
                    val = p.get("Value")
                    if isinstance(val, list) and len(val) > 0 and mesh_z_offset is not None:
                        inner_val = val[0].get("Value", {})
                        inner_val["Z"] = float(mesh_z_offset)

        # CollisionCylinder (CapsuleComponent): adjust dimensions
        if obj_name == "CollisionCylinder":
            props = exp.get("Data", [])
            if mesh_capsule_half_height is not None:
                hh_prop = next((p for p in props if isinstance(p, dict) and p.get("Name") == "CapsuleHalfHeight"), None)
                if hh_prop:
                    hh_prop["Value"] = float(mesh_capsule_half_height)
                else:
                    props.append({
                        "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                        "Name": "CapsuleHalfHeight",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": float(mesh_capsule_half_height)
                    })

            if mesh_capsule_radius is not None:
                r_prop = next((p for p in props if isinstance(p, dict) and p.get("Name") == "CapsuleRadius"), None)
                if r_prop:
                    r_prop["Value"] = float(mesh_capsule_radius)
                else:
                    props.append({
                        "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                        "Name": "CapsuleRadius",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": float(mesh_capsule_radius)
                    })

        # StaticCharacterParameterComponent: update recorded mesh location & collision parameters
        if obj_name == "StaticCharacterParameterComponent":
            props = exp.get("Data", [])
            if mesh_z_offset is not None:
                m_loc = next((p for p in props if isinstance(p, dict) and p.get("Name") == "MeshRelativeLocation"), None)
                if m_loc and isinstance(m_loc.get("Value"), list) and len(m_loc["Value"]) > 0:
                    m_loc["Value"][0].get("Value", {})["Z"] = float(mesh_z_offset)

            if mesh_capsule_half_height is not None:
                hh_p = next((p for p in props if isinstance(p, dict) and p.get("Name") == "MeshCapsuleHalfHeight"), None)
                if hh_p:
                    hh_p["Value"] = float(mesh_capsule_half_height)
                else:
                    props.append({
                        "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                        "Name": "MeshCapsuleHalfHeight",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": float(mesh_capsule_half_height)
                    })

            if mesh_capsule_radius is not None:
                r_p = next((p for p in props if isinstance(p, dict) and p.get("Name") == "MeshCapsuleRadius"), None)
                if r_p:
                    r_p["Value"] = float(mesh_capsule_radius)
                else:
                    props.append({
                        "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                        "Name": "MeshCapsuleRadius",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": float(mesh_capsule_radius)
                    })

    sync_namemap(data)
    return data