# utils/blueprint_patcher/patch_mesh.py

def patch_mesh_references(json_str: str, template_id: str, pal_id: str, log) -> str:
    """Retargets SkeletalMesh references and packages from template to custom pal."""
    log(f"  [Action: Mesh] Retargeting SK_{template_id} -> SK_{pal_id}...", "standard")
    replacements = {
        f"/Monster/{template_id}/SK_{template_id}": f"/Monster/{pal_id}/SK_{pal_id}",
        f"SkeletalMesh'SK_{template_id}'": f"SkeletalMesh'SK_{pal_id}'",
        f'"SK_{template_id}"': f'"SK_{pal_id}"',
    }
    for old, new in replacements.items():
        json_str = json_str.replace(old, new)
    return json_str

def patch_physics_asset(json_str: str, template_id: str, pal_id: str, log) -> str:
    """Retargets PhysicsAsset references from template to custom pal."""
    log(f"  [Action: Physics] Retargeting PA_{template_id}_PhysicsAsset -> PA_{pal_id}_PhysicsAsset...", "standard")
    replacements = {
        f"/Monster/{template_id}/PA_{template_id}": f"/Monster/{pal_id}/PA_{pal_id}",
        f"PhysicsAsset'PA_{template_id}_PhysicsAsset'": f"PhysicsAsset'PA_{pal_id}_PhysicsAsset'",
        f'"PA_{template_id}_PhysicsAsset"': f'"PA_{pal_id}_PhysicsAsset"',
    }
    for old, new in replacements.items():
        json_str = json_str.replace(old, new)
    return json_str