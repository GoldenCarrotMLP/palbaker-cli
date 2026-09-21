# utils/blueprint_patcher/feature_manager/utility.py
"""
====================================================================================================
                  PARTNER UTILITY ACTION SCHEMA & REFERENCE
====================================================================================================

OVERVIEW:
---------
Manages non-weapon partner utility cooperation abilities. In Palworld, when the player activates
partner skills like healing, player revival, or dungeon radar, the character executes an action
class bound in StaticCharacterParameterComponent.AIActionMap[EPalAIActionType::Cooperation].

SCHEMA SPECIFICATION:
---------------------
1. Method Signature:
   set_coop_utility(skill_type: str)

2. Discovered Utility Presets:
   ┌──────────────────┬─────────────────────────────────────────────────────────────┐
   │ Skill Key        │ AI Controller Class Path                                    │
   ├──────────────────┼─────────────────────────────────────────────────────────────┤
   │ "Heal"           │ .../Coop/BP_AIActionHealCall.BP_AIActionHealCall_C         │
   │ "HealLilyQueen"  │ .../Coop/BP_AIActionHealCall_LilyQueen_C                    │
   │ "RevivePlayer"   │ .../Coop/BP_AIActionRevivePlayer.BP_AIActionRevivePlayer_C │
   │ "RevivePal"      │ .../Coop/BP_AIActionRevivePal.BP_AIActionRevivePal_C       │
   │ "MetalDetector"  │ .../Coop/BP_AIActionMetalDetector.BP_AIActionMetalDetector_C│
   │ "DungeonSearch"  │ .../Coop/BP_AIActionSearchDungeonMapObject_C                │
   │ "RelicSearch"    │ .../Coop/BP_AIActionSearchRelic.BP_AIActionSearchRelic_C    │
   │ "Berserk"        │ .../Coop/BP_AIActionCoop_Berserk.BP_AIActionCoop_Berserk_C  │
   │ "NightVision"    │ .../Coop/BP_AIActionNightVision.BP_AIActionNightVision_C    │
   │ "NightRunner"    │ .../Coop/BP_AIActionCoop_NightRunner.BP_AIActionCoop_NightRunner_C │
   │ "ReturnToCamp"   │ .../Coop/BP_AIAction_ReturnToBaseCampCall_C                 │
   │ "Stealth"        │ .../Coop/BP_AIAction_Stealth.BP_AIAction_Stealth_C          │
   │ "StatusUp"       │ .../Coop/BP_AIActionCoop_StatusUp.BP_AIActionCoop_StatusUp_C│
   │ "OpenTreasure"   │ .../Coop/BP_AIAction_OpenTreasure.BP_AIAction_OpenTreasure_C│
   └──────────────────┴─────────────────────────────────────────────────────────────┘
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class UtilityManagerMixin:
    """
    Manages non-weapon partner utility actions (healing, resuscitation, radar, stealth, etc.).
    """

    UTILITY_PRESETS = {
        "Heal": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionHealCall.BP_AIActionHealCall_C",
        "HealLilyQueen": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionHealCall_LilyQueen.BP_AIActionHealCall_LilyQueen_C",
        "RevivePlayer": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionRevivePlayer.BP_AIActionRevivePlayer_C",
        "RevivePal": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionRevivePal.BP_AIActionRevivePal_C",
        "MetalDetector": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionMetalDetector.BP_AIActionMetalDetector_C",
        "DungeonSearch": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionSearchDungeonMapObject.BP_AIActionSearchDungeonMapObject_C",
        "RelicSearch": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionSearchRelic.BP_AIActionSearchRelic_C",
        "Berserk": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionCoop_Berserk.BP_AIActionCoop_Berserk_C",
        "NightVision": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionNightVision.BP_AIActionNightVision_C",
        "NightRunner": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionCoop_NightRunner.BP_AIActionCoop_NightRunner_C",
        "ReturnToCamp": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_ReturnToBaseCampCall.BP_AIAction_ReturnToBaseCampCall_C",
        "Stealth": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_Stealth.BP_AIAction_Stealth_C",
        "StatusUp": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionCoop_StatusUp.BP_AIActionCoop_StatusUp_C",
        "OpenTreasure": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_OpenTreasure.BP_AIAction_OpenTreasure_C"
    }

    def set_coop_utility(self, skill_type: str):
        """
        Binds AIActionMap[EPalAIActionType::Cooperation] to a utility AI controller class.
        Supported options: Heal, RevivePlayer, RevivePal, MetalDetector, DungeonSearch,
        RelicSearch, Berserk, NightVision, NightRunner, ReturnToCamp, Stealth, StatusUp, OpenTreasure.
        """
        if not skill_type or skill_type == "None":
            self.remove_coop_utility()
            return

        action_path = self.UTILITY_PRESETS.get(skill_type)
        if not action_path:
            raise ValueError(f"Unknown utility skill: '{skill_type}'. Options: {list(self.UTILITY_PRESETS.keys())}")

        self.set_ai_action("EPalAIActionType::Cooperation", action_path)
        sync_namemap(self.data)

    def remove_coop_utility(self):
        """Unbinds the Cooperation AI action."""
        self.remove_ai_action("EPalAIActionType::Cooperation")
        sync_namemap(self.data)