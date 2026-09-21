# utils/blueprint_patcher/feature_manager/blendspace_builder.py
"""
====================================================================================================
               STANDALONE MOUNT BLENDSPACE SYNTHESIZER (BLENDSPACE BUILDER)
====================================================================================================
Synthesizes a valid BlendSpace1D asset (BS_Move_<Pal>_Riding) from an existing locomotion
blendspace seed, retargeting the skeleton, sequence imports, and speed interpolation segments.
====================================================================================================
"""

import json
from utils.uasset_helper import sync_namemap

def synthesize_riding_blendspace_ast(
    seed_blendspace_data: dict,
    target_pal_id: str,
    template_pal_id: str,
    max_speed: float = 1050.0,
    use_custom_anims: bool = False
) -> dict:
    raw_str = json.dumps(seed_blendspace_data)

    old_bs_name = f"BS_Move_{template_pal_id}_Riding" if f"BS_Move_{template_pal_id}_Riding" in raw_str else f"BS_Move_{template_pal_id}"
    new_bs_name = f"BS_Move_{target_pal_id}_Riding"

    # 1. Retarget Package and Asset Names
    raw_str = raw_str.replace(old_bs_name, new_bs_name)
    raw_str = raw_str.replace(
        f"/PalActorBP/{template_pal_id}/{old_bs_name}",
        f"/PalActorBP/{target_pal_id}/{new_bs_name}"
    )

    # 2. Retarget Skeleton
    raw_str = raw_str.replace(f"SK_{template_pal_id}_Skeleton", f"SK_{target_pal_id}_Skeleton")
    raw_str = raw_str.replace(
        f"/Model/Character/Skeleton/{template_pal_id}/SK_{template_pal_id}_Skeleton",
        f"/Model/Character/Skeleton/{target_pal_id}/SK_{target_pal_id}_Skeleton"
    )

    # 3. Retarget Animation Sequences to regular Idle/Walk/Run if riding takes don't exist
    if not use_custom_anims:
        raw_str = raw_str.replace(f"AS_{template_pal_id}_Run_Riding", f"AS_{target_pal_id}_Run")
        raw_str = raw_str.replace(f"AS_{template_pal_id}_Walk_Riding", f"AS_{target_pal_id}_Walk")
    else:
        raw_str = raw_str.replace(f"AS_{template_pal_id}_Run_Riding", f"AS_{target_pal_id}_Run_Riding")
        raw_str = raw_str.replace(f"AS_{template_pal_id}_Walk_Riding", f"AS_{target_pal_id}_Walk_Riding")

    raw_str = raw_str.replace(f"AS_{template_pal_id}_Idle", f"AS_{target_pal_id}_Idle")
    raw_str = raw_str.replace(f"AS_{template_pal_id}_Run", f"AS_{target_pal_id}_Run")
    raw_str = raw_str.replace(f"AS_{template_pal_id}_Walk", f"AS_{target_pal_id}_Walk")
    raw_str = raw_str.replace(f"/Monster/{template_pal_id}/", f"/Monster/{target_pal_id}/")

    data = json.loads(raw_str)

    # 4. Set Object Name & Max Speed
    main_export = data["Exports"][0]
    main_export["ObjectName"] = new_bs_name

    for prop in main_export.get("Data", []):
        if prop.get("Name") == "BlendParameters":
            for bp in prop.get("Value", []):
                if bp.get("Name") == "Max":
                    bp["Value"] = float(max_speed)

    sync_namemap(data)
    return data