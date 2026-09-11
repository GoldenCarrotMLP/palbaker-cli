# utils/blueprint_patcher/patch_classes.py
import re

def patch_actor_class_and_cdo(json_str: str, template_id: str, pal_id: str, log) -> str:
    """
    Retargets the main Actor Blueprint Class, CDO, and virtual package path.
    Strictly uses lookaheads and word boundaries to protect ABP_ and weapon sub-classes.
    """
    log(f"  [Action: Class] Retargeting BP_{template_id} -> BP_{pal_id}...", "standard")

    # 1. Package path
    json_str = json_str.replace(
        f"/PalActorBP/{template_id}/BP_{template_id}",
        f"/PalActorBP/{pal_id}/BP_{pal_id}"
    )

    # 2. CDO (Default Object)
    json_str = re.sub(rf"Default__BP_{template_id}_C(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}_C", json_str)
    json_str = re.sub(rf"Default__BP_{template_id}(?![a-zA-Z0-9_])", f"Default__BP_{pal_id}", json_str)

    # 3. Class generated types
    json_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{template_id}_C(?![a-zA-Z0-9_])", f"BP_{pal_id}_C", json_str)
    json_str = re.sub(rf"(?<![a-zA-Z0-9_])BP_{template_id}(?![a-zA-Z0-9_])", f"BP_{pal_id}", json_str)

    return json_str