# utils/blueprint_patcher/feature_manager/funnel.py
"""
====================================================================================================
                  SATELLITE MINION FUNNEL SCHEMA & REFERENCE
====================================================================================================

OVERVIEW:
---------
Controls companion satellite minions that orbit the player and fire synchronized attacks.
Funnel parameters are stored inside InheritableComponentHandler.Records for the
PalPartnerSkillParameter component.

SCHEMA SPECIFICATION:
---------------------
1. Method Signatures:
   • set_partner_funnel(
         preset_name: str = None,
         custom_waza_id: str = None,
         custom_character_class: str = None,
         custom_controller_class: str = None
     )
   • get_partner_funnel_params() -> dict
   • clear_partner_funnel()

2. Standard In-Game Funnel Presets:
   • "Daedream" / "DreamDemon":
     Character:  BP_FunnelCharacter_DreamDemon_C
     Controller: BP_FunnelCharacterAIController_C
     Attack:     EPalWazaID::Funnel_DreamDemon (Dark element projectile barrage)
   • "Dazzi" / "RaijinDaughter":
     Character:  BP_FunnelCharacter_RaijinDaughter_C
     Controller: BP_FunnelCharacterAIController_C
     Attack:     EPalWazaID::Funnel_RaijinDaughter (Electric shock strike)
   • "Flopie" / "FlowerRabbit":
     Character:  BP_FunnelCharacter_FlowerRabbit_C
     Controller: BP_FunnelCharacterAIController_C
     Attack:     EPalWazaID::None (Non-combat automated item retrieval)

3. Targeting AI Actions (FunnelSkillAIActionClass):
   • "ShadowBall":     Homing dark sphere projectile barrage
   • "Thunderbolt":    Instantaneous vertical lightning strike
   • "SeedMachinegun": High-frequency rapid fire stream of seed bullets

4. Custom Attack Overrides:
   custom_waza_id can be set to any valid EPalWazaID in the engine, e.g.:
   EPalWazaID::DarkLaser, EPalWazaID::SolarBeam, EPalWazaID::IceMissile.
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class FunnelManagerMixin:
    """
    Manages satellite minion funnels (Daedream, Dazzi, Flopie) that orbit the player.
    """

    FUNNEL_PRESETS = {
        "Daedream": {
            "char_class": "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_DreamDemon.BP_FunnelCharacter_DreamDemon_C",
            "ctrl_class": "/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            "waza_id": "Funnel_DreamDemon"
        },
        "DreamDemon": {
            "char_class": "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_DreamDemon.BP_FunnelCharacter_DreamDemon_C",
            "ctrl_class": "/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            "waza_id": "Funnel_DreamDemon"
        },
        "Dazzi": {
            "char_class": "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_RaijinDaughter.BP_FunnelCharacter_RaijinDaughter_C",
            "ctrl_class": "/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            "waza_id": "Funnel_RaijinDaughter"
        },
        "RaijinDaughter": {
            "char_class": "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_RaijinDaughter.BP_FunnelCharacter_RaijinDaughter_C",
            "ctrl_class": "/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            "waza_id": "Funnel_RaijinDaughter"
        },
        "Flopie": {
            "char_class": "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_FlowerRabbit.BP_FunnelCharacter_FlowerRabbit_C",
            "ctrl_class": "/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            "waza_id": "None"
        },
        "FlowerRabbit": {
            "char_class": "/Game/Pal/Blueprint/Character/Funnel/BP_FunnelCharacter_FlowerRabbit.BP_FunnelCharacter_FlowerRabbit_C",
            "ctrl_class": "/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C",
            "waza_id": "None"
        }
    }

    FUNNEL_TARGETING_ACTIONS = {
        "ShadowBall": "/Game/Pal/Blueprint/Funnel/ReticleTargetAttack/BP_AIActionFunnelSkill_ShadowBall.BP_AIActionFunnelSkill_ShadowBall_C",
        "Thunderbolt": "/Game/Pal/Blueprint/Funnel/ReticleTargetAttack/BP_AIActionFunnelSkill_Thunderbolt.BP_AIActionFunnelSkill_Thunderbolt_C",
        "SeedMachinegun": "/Game/Pal/Blueprint/Funnel/ReticleTargetAttack/BP_AIActionFunnelSkill_SeedMachinegun.BP_AIActionFunnelSkill_SeedMachinegun_C"
    }

    def set_partner_funnel(
        self,
        preset_name: str = None,
        custom_waza_id: str = None,
        custom_character_class: str = None,
        custom_controller_class: str = None
    ):
        """
        Injects satellite minion parameters into ICH PalPartnerSkillParameter using named presets
        ('Daedream', 'Dazzi', 'Flopie') or arbitrary custom character/controller/skill classes.
        """
        preset = self.FUNNEL_PRESETS.get(preset_name, {}) if preset_name else {}

        char_class = custom_character_class or preset.get("char_class")
        ctrl_class = custom_controller_class or preset.get("ctrl_class", "/Game/Pal/Blueprint/Controller/Funnel/BP_FunnelCharacterAIController.BP_FunnelCharacterAIController_C")
        waza = custom_waza_id or preset.get("waza_id", "None")

        if not char_class:
            raise ValueError(f"No valid character class resolved for funnel. Provide a valid preset or custom_character_class.")

        self.set_partner_funnel_params(
            funnel_character_class=char_class,
            funnel_controller_class=ctrl_class,
            funnel_waza_id=waza
        )
        sync_namemap(self.data)

    def get_partner_funnel_params(self) -> dict:
        """
        Parses and returns the currently configured funnel parameters in InheritableComponentHandler.
        Returns: {'FunnelCharacterClass': str, 'FunnelControllerClass': str, 'FunnelAttackWazaID': str}
        """
        _, ich_export = self.find_ich_export()
        if not ich_export or not isinstance(ich_export.get("Data"), list):
            return {}

        records_prop = next((p for p in ich_export["Data"] if isinstance(p, dict) and p.get("Name") == "Records"), None)
        if not records_prop or not isinstance(records_prop.get("Value"), list):
            return {}

        target_template_idx = None
        for rec in records_prop["Value"]:
            if not isinstance(rec, dict):
                continue
            comp_key = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentKey"), None)
            if comp_key and isinstance(comp_key.get("Value"), list):
                var_prop = next((p for p in comp_key["Value"] if isinstance(p, dict) and p.get("Name") == "SCSVariableName"), None)
                if var_prop and var_prop.get("Value") == "PalPartnerSkillParameter":
                    tmpl_prop = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentTemplate"), None)
                    if tmpl_prop:
                        target_template_idx = tmpl_prop.get("Value")
                        break

        if not target_template_idx or not (1 <= target_template_idx <= len(self.exports)):
            return {}

        tmpl_export = self.exports[target_template_idx - 1]
        tmpl_data = tmpl_export.get("Data", [])

        result = {}
        for prop in tmpl_data:
            if isinstance(prop, dict):
                p_name = prop.get("Name")
                if p_name in ["FunnelCharacterClass", "FunnelControllerClass"]:
                    imp_idx = prop.get("Value")
                    if isinstance(imp_idx, int) and imp_idx < 0 and (-imp_idx - 1) < len(self.imports):
                        imp = self.imports[-imp_idx - 1]
                        result[p_name] = f"{imp.get('ObjectName')}"
                elif p_name == "FunnelAttackWazaID":
                    val = prop.get("Value")
                    if isinstance(val, str) and val and not val.startswith("EPalWazaID::"):
                        val = f"EPalWazaID::{val}"
                    result[p_name] = val

        return result

    def clear_partner_funnel(self):
        """Strips funnel parameters from ICH PalPartnerSkillParameter."""
        _, ich_export = self.find_ich_export()
        if not ich_export or not isinstance(ich_export.get("Data"), list):
            return

        records_prop = next((p for p in ich_export["Data"] if isinstance(p, dict) and p.get("Name") == "Records"), None)
        if not records_prop or not isinstance(records_prop.get("Value"), list):
            return

        target_template_idx = None
        for rec in records_prop["Value"]:
            if not isinstance(rec, dict):
                continue
            comp_key = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentKey"), None)
            if comp_key and isinstance(comp_key.get("Value"), list):
                var_prop = next((p for p in comp_key["Value"] if isinstance(p, dict) and p.get("Name") == "SCSVariableName"), None)
                if var_prop and var_prop.get("Value") == "PalPartnerSkillParameter":
                    tmpl_prop = next((p for p in rec.get("Value", []) if isinstance(p, dict) and p.get("Name") == "ComponentTemplate"), None)
                    if tmpl_prop:
                        target_template_idx = tmpl_prop.get("Value")
                        break

        if target_template_idx and 1 <= target_template_idx <= len(self.exports):
            tmpl_export = self.exports[target_template_idx - 1]
            tmpl_data = tmpl_export.get("Data")
            if isinstance(tmpl_data, list):
                tmpl_export["Data"] = [
                    p for p in tmpl_data
                    if isinstance(p, dict) and p.get("Name") not in ["FunnelCharacterClass", "FunnelControllerClass", "FunnelAttackWazaID"]
                ]

        sync_namemap(self.data)