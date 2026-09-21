# utils/blueprint_patcher/feature_manager/evasion.py
"""
====================================================================================================
                  COMBAT EVASION & MOVEMENT ACTION SCHEMA & REFERENCE
====================================================================================================

OVERVIEW:
---------
Controls tactical combat mobility including side-stepping, rapid dash pivots, teleporting,
and evasive disengagement. Configured via StaticCharacterParameterComponent.AIActionMap under
the EPalAIActionType::SideMove and EPalAIActionType::Leave slots.

SCHEMA SPECIFICATION:
---------------------
1. Method Signature:
   set_evasion_style(style: str)

2. Evasion & Movement Presets:
   ┌──────────────────────┬──────────────────────┬────────────────────────────────────────────────────────┐
   │ Style Key            │ Action Slot          │ Controller Class Path                                  │
   ├──────────────────────┼──────────────────────┼────────────────────────────────────────────────────────┤
   │ "SideStep"           │ SideMove             │ .../SideMove/BP_AIAction_AnimationSideStep_C           │
   │ "DashTurn"           │ SideMove             │ .../SideMove/BP_AIAction_DashTurn_C                    │
   │ "RoundStep"          │ SideMove             │ .../SideMove/BP_AIAction_RoundStep_C                   │
   │ "Teleport"           │ SideMove             │ .../SideMove/BP_AIAction_Teleport_C                    │
   │ "SideStepOrTeleport" │ SideMove             │ .../SideMove/BP_AIAction_SideStepOrTeleport_C          │
   │ "BackStep"           │ Leave                │ .../Leave/BP_AIAction_Leave_AnimationBackStep_C        │
   │ "TurnRun"            │ Leave                │ .../Leave/BP_AIAction_Leave_TurnRun_C                  │
   └──────────────────────┴──────────────────────┴────────────────────────────────────────────────────────┘
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class EvasionManagerMixin:
    """
    Manages combat evasion, dodging, tactical retreat, and teleportation actions.
    """

    EVASION_PRESETS = {
        "SideStep": {
            "slot": "EPalAIActionType::SideMove",
            "path": "/Game/Pal/Blueprint/Controller/AIAction/SideMove/BP_AIAction_AnimationSideStep.BP_AIAction_AnimationSideStep_C"
        },
        "DashTurn": {
            "slot": "EPalAIActionType::SideMove",
            "path": "/Game/Pal/Blueprint/Controller/AIAction/SideMove/BP_AIAction_DashTurn.BP_AIAction_DashTurn_C"
        },
        "RoundStep": {
            "slot": "EPalAIActionType::SideMove",
            "path": "/Game/Pal/Blueprint/Controller/AIAction/SideMove/BP_AIAction_RoundStep.BP_AIAction_RoundStep_C"
        },
        "Teleport": {
            "slot": "EPalAIActionType::SideMove",
            "path": "/Game/Pal/Blueprint/Controller/AIAction/SideMove/BP_AIAction_Teleport.BP_AIAction_Teleport_C"
        },
        "SideStepOrTeleport": {
            "slot": "EPalAIActionType::SideMove",
            "path": "/Game/Pal/Blueprint/Controller/AIAction/SideMove/BP_AIAction_SideStepOrTeleport.BP_AIAction_SideStepOrTeleport_C"
        },
        "BackStep": {
            "slot": "EPalAIActionType::Leave",
            "path": "/Game/Pal/Blueprint/Controller/AIAction/Leave/BP_AIAction_Leave_AnimationBackStep.BP_AIAction_Leave_AnimationBackStep_C"
        },
        "TurnRun": {
            "slot": "EPalAIActionType::Leave",
            "path": "/Game/Pal/Blueprint/Controller/AIAction/Leave/BP_AIAction_Leave_TurnRun.BP_AIAction_Leave_TurnRun_C"
        }
    }

    def set_evasion_style(self, style: str):
        """
        Configures tactical combat movement (SideMove or Leave) in AIActionMap.
        Options: SideStep, DashTurn, RoundStep, Teleport, SideStepOrTeleport, BackStep, TurnRun.
        """
        if not style or style == "None":
            return

        preset = self.EVASION_PRESETS.get(style)
        if not preset:
            raise ValueError(f"Unknown evasion style: '{style}'. Valid options: {list(self.EVASION_PRESETS.keys())}")

        self.set_ai_action(preset["slot"], preset["path"])
        sync_namemap(self.data)

    def remove_evasion_style(self, style_category: str = "SideMove"):
        """Removes the SideMove or Leave action from AIActionMap."""
        slot = f"EPalAIActionType::{style_category}"
        self.remove_ai_action(slot)
        sync_namemap(self.data)