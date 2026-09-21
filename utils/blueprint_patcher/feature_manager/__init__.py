# utils/blueprint_patcher/feature_manager/__init__.py
from .manager import BlueprintFeatureManager
from .funnel_builder import synthesize_funnel_character_ast
from .weapon_builder import synthesize_flamethrower_cluster

__all__ = [
    "BlueprintFeatureManager",
    "synthesize_funnel_character_ast",
    "synthesize_flamethrower_cluster"
]