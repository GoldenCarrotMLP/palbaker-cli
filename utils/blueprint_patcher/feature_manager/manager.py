# utils/blueprint_patcher/feature_manager/manager.py
from .base import BaseFeatureManager
from .imports import ImportManagerMixin
from .components import ComponentManagerMixin
from .saddle import SaddleManagerMixin
from .flight import FlightManagerMixin
from .weapons import WeaponManagerMixin
from .funnel import FunnelManagerMixin
from .shield import ShieldManagerMixin
from .utility import UtilityManagerMixin
from .evasion import EvasionManagerMixin
from .props import PropsManagerMixin
from .ich import ICHManagerMixin
from .cdo import CDOManagerMixin
from .bytecode import BytecodeManagerMixin
from .vfx import VFXManagerMixin
from .physics import PhysicsManagerMixin
from .funnel_builder import synthesize_funnel_character_ast
from .weapon_builder import synthesize_flamethrower_cluster

class BlueprintFeatureManager(
    BaseFeatureManager,
    ImportManagerMixin,
    ComponentManagerMixin,
    SaddleManagerMixin,
    FlightManagerMixin,
    WeaponManagerMixin,
    FunnelManagerMixin,
    ShieldManagerMixin,
    UtilityManagerMixin,
    EvasionManagerMixin,
    PropsManagerMixin,
    ICHManagerMixin,
    CDOManagerMixin,
    BytecodeManagerMixin,
    VFXManagerMixin,
    PhysicsManagerMixin
):
    """
    High-level AST controller for Unreal Engine 5.1 Pal Actor Blueprints.
    Composes all modular feature mixins into a unified programmatic interface.
    """

    @staticmethod
    def create_funnel_character_ast(
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
        """Convenience factory method to synthesize standalone satellite actor blueprints."""
        return synthesize_funnel_character_ast(
            seed_funnel_data=seed_funnel_data,
            target_pal_id=target_pal_id,
            template_pal_id=template_pal_id,
            targeting_action=targeting_action,
            mesh_capsule_half_height=mesh_capsule_half_height,
            mesh_capsule_radius=mesh_capsule_radius,
            mesh_z_offset=mesh_z_offset,
            custom_targeting_action_pkg=custom_targeting_action_pkg,
            custom_targeting_action_class=custom_targeting_action_class
        )

    @staticmethod
    def create_flamethrower_cluster(
        seed_weapon_data: dict,
        seed_montages: dict,
        pal_id: str,
        template_id: str = "Kitsunebi",
        skeleton_guid: str = "BF21DEE0-4BCF0A09-60C97DA1-367595A0",
        config: dict | None = None
    ) -> dict:
        """Convenience factory method to synthesize standalone weapon actor and montages cluster."""
        return synthesize_flamethrower_cluster(
            seed_weapon_data=seed_weapon_data,
            seed_montages=seed_montages,
            pal_id=pal_id,
            template_id=template_id,
            skeleton_guid=skeleton_guid,
            config=config
        )