# utils/creator/palschema_exporter.py
import os
import json
import shutil
import re
from utils.blueprint_patcher import patch_actor_blueprint

class PalSchemaExporter:
    def __init__(self, controller):
        self.c = controller

    def get_palschema_mods_dir(self) -> str | None:
        palworld_exe = self.c.settings.get("palworld_exe", "")
        if not palworld_exe or not os.path.exists(palworld_exe):
            return None
        
        exe_lower = palworld_exe.lower()
        dirname = os.path.dirname(palworld_exe)
        
        if "win64" in exe_lower:
            bin_dir = dirname
        else:
            bin_dir = os.path.join(dirname, "Pal", "Binaries", "Win64")
            
        if not os.path.exists(bin_dir):
            return None
            
        ue4ss_dir_lower = os.path.join(bin_dir, "ue4ss")
        ue4ss_dir_upper = os.path.join(bin_dir, "UE4SS")
        ue4ss_dir = ue4ss_dir_lower if os.path.exists(ue4ss_dir_lower) else ue4ss_dir_upper
        
        if not os.path.exists(ue4ss_dir):
            return None
            
        palschema_mods_dir = os.path.normpath(os.path.join(ue4ss_dir, "Mods", "PalSchema", "mods"))
        
        if not os.path.exists(palschema_mods_dir):
            for root, dirs, _ in os.walk(bin_dir):
                depth = root[len(bin_dir):].count(os.sep)
                if depth > 3:
                    dirs[:] = []
                    continue
                if "PalSchema" in dirs:
                    test_dir = os.path.normpath(os.path.join(root, "PalSchema", "mods"))
                    if os.path.exists(test_dir):
                        palschema_mods_dir = test_dir
                        break

        return palschema_mods_dir if os.path.exists(palschema_mods_dir) else None

    def delete_palschema_export(self, pal_id: str):
        """Permanently deletes the exported PalSchema mod folder to prevent orphan directory clutter."""
        mod_name = f"PalBaker_Custom_{pal_id}"
        
        creator_dir = self.c.get_creator_dir()
        if creator_dir:
            local_mod_root = os.path.join(creator_dir, "PalSchema", mod_name)
            if os.path.exists(local_mod_root):
                try:
                    shutil.rmtree(local_mod_root)
                    self.c.view.write_log(f"Successfully deleted local PalSchema export directory: {mod_name}", "warning")
                except Exception as e:
                    self.c.view.write_log(f"Failed to delete local PalSchema export: {e}", "error")

        mods_dir = self.get_palschema_mods_dir()
        if mods_dir:
            mod_root = os.path.join(mods_dir, mod_name)
            if os.path.exists(mod_root):
                try:
                    shutil.rmtree(mod_root)
                    self.c.view.write_log(f"Successfully deleted deployed PalSchema export directory: {mod_name}", "warning")
                except Exception as e:
                    self.c.view.write_log(f"Failed to delete deployed PalSchema export: {e}", "error")

    def generate_custom_actor_blueprint(self, p: dict) -> bool:
        """Proxies standalone blueprint compilation cleanly to the centralized patching engine."""
        pal_id = p["CharacterID"]
        template_id = p["TemplateID"]
        
        def log_bridge(msg, category):
            self.c.view.write_log(msg, category)

        return patch_actor_blueprint(self.c.settings, pal_id, template_id, log_callback=log_bridge)

    def export_to_palschema(self, p: dict):
        # In utils/creator/palschema_exporter.py

        _KITSUNEBI = {
            "weapon_suffix": "Flamethrower",
            "female_anime": "/Game/Pal/Blueprint/Character/Player/Female/ShooterAnimeBP/BP_Player_Female_ShooterAnime_Kitsunebi_Flamethrower.BP_Player_Female_ShooterAnime_Kitsunebi_Flamethrower_C",
            "male_anime": "/Game/Pal/Blueprint/Character/Player/Male/ShooterAnimeBP/BP_Player_Male_ShooterAnime_Kitsunebi_Flamethrower.BP_Player_Male_ShooterAnime_Kitsunebi_Flamethrower_C",
            "camera_offset": {
                "ArmLength": 250.0,
                "CameraOffset": { "X": 0.0, "Y": 70.0, "Z": 40.0 },
                "CameraInterpTime": 0.0,
                "EndCameraInterpTime": 0.0
            }
        }
        _PENGUIN = {
            "weapon_suffix": "Launcher",
            "female_anime": "/Game/Pal/Blueprint/Character/Player/Female/ShooterAnimeBP/BP_Player_Female_ShooterAnime_RocketLauncher.BP_Player_Female_ShooterAnime_RocketLauncher_C",
            "male_anime": "/Game/Pal/Blueprint/Character/Player/Male/ShooterAnimeBP/BP_Player_Male_ShooterAnime_RocketLauncher.BP_Player_Male_ShooterAnime_RocketLauncher_C",
        }
        _MONKEY = {
            "weapon_suffix": "Rifle",
            "female_anime": "/Game/Pal/Blueprint/Character/Player/Female/ShooterAnimeBP/BP_Player_Female_ShooterAnime_AssaultRifle.BP_Player_Female_ShooterAnime_AssaultRifle_C",
            "male_anime": "/Game/Pal/Blueprint/Character/Player/Male/ShooterAnimeBP/BP_Player_Male_ShooterAnime_AssaultRifle.BP_Player_Male_ShooterAnime_AssaultRifle_C",
        }
        _CARBUNCLO = {
            "weapon_suffix": "Submachinegun",
            "female_anime": "/Game/Pal/Blueprint/Character/Player/Female/ShooterAnimeBP/BP_Player_Female_ShooterAnime_SubmachineGun.BP_Player_Female_ShooterAnime_SubmachineGun_C",
            "male_anime": "/Game/Pal/Blueprint/Character/Player/Male/ShooterAnimeBP/BP_Player_Male_ShooterAnime_SubmachineGun.BP_Player_Male_ShooterAnime_SubmachineGun_C",
        }
        _GRIZZBOLT = {
            "weapon_suffix": "Minigun",
            "female_anime": "/Game/Pal/Blueprint/Character/Player/Female/ShooterAnimeBP/BP_Player_Female_ShooterAnime_HeavyWeapon.BP_Player_Female_ShooterAnime_HeavyWeapon_C",
            "male_anime": "/Game/Pal/Blueprint/Character/Player/Male/ShooterAnimeBP/BP_Player_Male_ShooterAnime_HeavyWeapon.BP_Player_Male_ShooterAnime_HeavyWeapon_C",
        }

        # Multi-mapped to support template fallbacks, explicit IDs, and friendly weapon names
        KNOWN_PARTNER_WEAPONS = {
            "Kitsunebi": _KITSUNEBI, "PartnerSkill_Kitsunebi": _KITSUNEBI, "Flamethrower": _KITSUNEBI,
            "Penguin": _PENGUIN, "PartnerSkill_Penguin": _PENGUIN, "Launcher": _PENGUIN,
            "Monkey": _MONKEY, "PartnerSkill_Monkey": _MONKEY, "AssaultRifle": _MONKEY, "Rifle": _MONKEY,
            "Carbunclo": _CARBUNCLO, "PartnerSkill_Carbunclo": _CARBUNCLO, "SubmachineGun": _CARBUNCLO, "Submachinegun": _CARBUNCLO,
            "Grizzbolt": _GRIZZBOLT, "PartnerSkill_Grizzbolt": _GRIZZBOLT, "HeavyWeapon": _GRIZZBOLT, "Minigun": _GRIZZBOLT
        }

        creator_dir = self.c.get_creator_dir()
        if not creator_dir:
            self.c.view.write_log("Creator directory not found. Cannot export PalSchema data.", "error")
            return

        pal_id = p["CharacterID"]
        template_id = p["TemplateID"]
        paldex_type = p.get("PaldexType", "Species")
        mod_name = f"PalBaker_Custom_{pal_id}"
        
        mod_root = os.path.join(creator_dir, "PalSchema", mod_name)
        os.makedirs(mod_root, exist_ok=True)
        
        base_properties = self.c.templates_cache.get(template_id, {})
        
        custom_folder_name = pal_id
        custom_asset_name = f"BP_{pal_id}"
        bp_virtual_path = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{custom_folder_name}/{custom_asset_name}.{custom_asset_name}_C"
        
        # 1. Base Properties Builder
        new_monster_props = dict(base_properties)
        new_monster_props["BPClass"] = f"MOD_{pal_id}" if paldex_type == "Species" else template_id
        new_monster_props["IsPal"] = True
        
        # Enums & Tribe
        enums_dir = os.path.join(mod_root, "enums")
        if paldex_type == "Species":
            new_monster_props["Tribe"] = f"EPalTribeID::MOD_{pal_id}"
            os.makedirs(enums_dir, exist_ok=True)
            tribes_list = [f"MOD_{pal_id}"]
            if p.get("GeneratePredator", False):
                tribes_list.append(f"MOD_PREDATOR_{pal_id}")
                
            enums_payload = { "EPalTribeID": tribes_list }
            with open(os.path.join(enums_dir, f"{pal_id}_enums.json"), "w", encoding="utf-8") as f_enum:
                json.dump(enums_payload, f_enum, indent=4)
        else:
            new_monster_props["Tribe"] = base_properties.get("Tribe", f"EPalTribeID::{template_id}")

        # Core Parameters
        base_hp = int(p.get("Hp", p.get("BaseHP", 100)))
        base_melee = int(p.get("MeleeAttack", p.get("BaseAtk", 100)))
        base_shot = int(p.get("ShotAttack", p.get("BaseShot", 100)))
        base_def = int(p.get("Defense", p.get("BaseDef", 100)))
        base_walk = int(p.get("WalkSpeed", 145))
        base_run = int(p.get("RunSpeed", 440))

        new_monster_props["ElementType1"] = p.get("ElementType1", "EPalElementType::Normal")
        new_monster_props["ElementType2"] = p.get("ElementType2", "EPalElementType::None")
        new_monster_props["Hp"] = base_hp
        new_monster_props["MeleeAttack"] = base_melee
        new_monster_props["ShotAttack"] = base_shot
        new_monster_props["Defense"] = base_def
        new_monster_props["Support"] = int(p.get("Support", 100))
        new_monster_props["CraftSpeed"] = int(p.get("CraftSpeed", p.get("BaseWorkSpeed", 100)))
        new_monster_props["Size"] = p.get("Size", "EPalSizeType::M")
        new_monster_props["Rarity"] = int(p.get("Rarity", 1))
        new_monster_props["Price"] = float(p.get("Price", 1000.0))
        new_monster_props["WalkSpeed"] = base_walk
        new_monster_props["RunSpeed"] = base_run
        new_monster_props["RideSprintSpeed"] = int(p.get("RideSprintSpeed", 620))
        new_monster_props["TransportSpeed"] = int(p.get("TransportSpeed", 200))
        new_monster_props["FoodAmount"] = int(p.get("FoodAmount", 1))
        new_monster_props["Stamina"] = int(p.get("Stamina", 100))
        new_monster_props["MaleProbability"] = int(p.get("MaleProbability", 50))
        new_monster_props["CombiRank"] = int(p.get("CombiRank", 100))
        new_monster_props["CaptureRateCorrect"] = float(p.get("CaptureRateCorrect", 1.0))
        new_monster_props["MeshCapsuleHalfHeight"] = float(p.get("MeshCapsuleHalfHeight", 100.0))
        new_monster_props["MeshCapsuleRadius"] = float(p.get("MeshCapsuleRadius", 40.0))
        
        mesh_loc = p.get("MeshRelativeLocation", {"X": 0.0, "Y": 0.0, "Z": -30.0})
        new_monster_props["MeshRelativeLocation"] = {
            "X": float(mesh_loc.get("X", 0.0)),
            "Y": float(mesh_loc.get("Y", 0.0)),
            "Z": float(mesh_loc.get("Z", -30.0))
        }

        # Clean rogue keys (Keep PartnerSkill so it is correctly serialized into the monster parameter table!)
        for rogue in ["BaseSkills", "PassiveSkills"]:
            new_monster_props.pop(rogue, None)
            
        partner_skill = p.get("PartnerSkill", "None")
        if partner_skill and partner_skill != "None":
            new_monster_props["PartnerSkill"] = partner_skill

        # Explicitly map the translation text ID so it doesn't display raw variables in-game
        new_monster_props["OverridePartnerSkillTextID"] = f"PARTNERSKILL_MOD_{pal_id}"

        passives = p.get("PassiveSkills", [])
        new_monster_props["PassiveSkill1"] = passives[0] if len(passives) > 0 else "None"
        new_monster_props["PassiveSkill2"] = passives[1] if len(passives) > 1 else "None"
        new_monster_props["PassiveSkill3"] = passives[2] if len(passives) > 2 else "None"
        new_monster_props["PassiveSkill4"] = passives[3] if len(passives) > 3 else "None"

        for k in p.keys():
            if k.startswith("WorkSuitability_"):
                new_monster_props[k] = int(p[k])

        # 2. Build Multi-Row Pals Dictionary (Standard, Boss, and Predator)
        pals_payload = {
            f"MOD_{pal_id}": new_monster_props
        }

        # BOSS VARIATION
        if p.get("GenerateBoss", True) is not False:
            boss_props = dict(new_monster_props)
            boss_hp_mult = float(p.get("BossHPMultiplier", 5.0))
            boss_props["IsBoss"] = True
            boss_props["Size"] = "EPalSizeType::XL"
            boss_props["Rarity"] = min(10, int(p.get("Rarity", 6)) + 2)
            boss_props["Hp"] = int(base_hp * boss_hp_mult)
            boss_props["MeleeAttack"] = int(base_melee * 1.15)
            boss_props["ShotAttack"] = int(base_shot * 1.15)
            boss_props["Defense"] = int(base_def * 1.25)
            boss_props["EnemyReceiveDamageRate"] = 0.30
            boss_props["UseBossHPGauge"] = True
            boss_props["AIResponse"] = "BOSS"
            boss_props["BattleBGM"] = "FieldBoss_Tier_4"
            boss_props["BPClass"] = f"MOD_BOSS_{pal_id}" if paldex_type == "Species" else f"BOSS_{template_id}"
            boss_props["NamePrefixID"] = f"PREFIX_NAME_BOSS_{pal_id}"
            boss_props["OverrideNameTextID"] = f"PAL_NAME_MOD_{pal_id}"
            if p.get("GenerateBountyToken"):
                boss_props["FirstDefeatRewardItemID"] = f"BossDefeatReward_{pal_id}"
            pals_payload[f"MOD_BOSS_{pal_id}"] = boss_props

        # PREDATOR VARIATION
        if p.get("GeneratePredator", False):
            pred_props = dict(new_monster_props)
            pred_hp_mult = float(p.get("PredatorHPMultiplier", 10.0))
            pred_atk_mult = float(p.get("PredatorAtkMultiplier", 2.0))
            pred_speed_mult = float(p.get("PredatorSpeedMultiplier", 1.5))
            
            pred_props["IsBoss"] = True
            pred_props["Predator"] = True
            pred_props["IsUncapturable"] = True
            pred_props["CaptureRateCorrect"] = 0.0
            pred_props["ExpRatio"] = 25.0
            pred_props["Size"] = "EPalSizeType::XL"
            pred_props["Rarity"] = 9
            pred_props["Hp"] = int(base_hp * pred_hp_mult)
            pred_props["MeleeAttack"] = int(base_melee * pred_atk_mult)
            pred_props["ShotAttack"] = int(base_shot * pred_atk_mult)
            pred_props["Defense"] = int(base_def * 1.4)
            pred_props["EnemyReceiveDamageRate"] = 0.1
            pred_props["EnemyInflictDamageRate"] = 2.5
            pred_props["WalkSpeed"] = int(base_walk * pred_speed_mult)
            pred_props["RunSpeed"] = int(base_run * pred_speed_mult)
            pred_props["AIResponse"] = "BOSS"
            pred_props["UseBossHPGauge"] = True
            pred_props["BattleBGM"] = "Predator"
            pred_props["IgnoreLeanBack"] = True
            pred_props["IgnoreBlowAway"] = True
            pred_props["IgnoreStun"] = True
            pred_props["Nocturnal"] = True
            pred_props["BPClass"] = f"MOD_PREDATOR_{pal_id}" if paldex_type == "Species" else f"PREDATOR_{template_id}"
            pred_props["NamePrefixID"] = f"PREFIX_NAME_PREDATOR_{pal_id}"
            pred_props["OverrideNameTextID"] = f"PAL_NAME_MOD_{pal_id}"
            pred_props["Tribe"] = f"EPalTribeID::MOD_PREDATOR_{pal_id}" if paldex_type == "Species" else f"EPalTribeID::{template_id}"
            pals_payload[f"MOD_PREDATOR_{pal_id}"] = pred_props

        # Save Pals table
        pals_dir = os.path.join(mod_root, "pals")
        os.makedirs(pals_dir, exist_ok=True)
        with open(os.path.join(pals_dir, f"{pal_id}.json"), "w", encoding="utf-8") as f:
            json.dump(pals_payload, f, indent=4)

        # 3. Translations Table
        trans_dir = os.path.join(mod_root, "translations", "en")
        os.makedirs(trans_dir, exist_ok=True)
        
        pal_names_table = {
            f"PAL_NAME_MOD_{pal_id}": p["Name"],
            f"PAL_NAME_MOD_BOSS_{pal_id}": p["Name"],
            f"PAL_NAME_MOD_PREDATOR_{pal_id}": p["Name"]
        }
        
        prefix_table = {
            f"PREFIX_NAME_BOSS_{pal_id}": p.get("BossPrefix", "Gilded Monarch"),
            f"PREFIX_NAME_PREDATOR_{pal_id}": p.get("PredatorPrefix", "Rampaging Predator")
        }

        custom_skill_name = p.get("PartnerSkillName")
        if not custom_skill_name:
            custom_skill_name = f"{p['Name']}'s Partner Skill"

        trans_payload = {
            "DT_PalNameText": pal_names_table,
            "DT_NamePrefixText_Common": prefix_table,
            "DT_PalFirstActivatedInfoText": {
                f"PAL_FIRST_SPAWN_DESC_MOD_{pal_id}": p["Description"]
            },
            "DT_SkillNameText_Common": {
                f"PARTNERSKILL_MOD_{pal_id}": custom_skill_name
            }
        }
        
        if p.get("EnablePaldeck", False) or p.get("ZukanIndex", -1) != -1:
            trans_payload["DT_PalLongDescriptionText"] = {
                f"PAL_LONG_DESC_MOD_{pal_id}": p.get("LongDescription", p["Description"])
            }
            
        with open(os.path.join(trans_dir, "names.json"), "w", encoding="utf-8") as f:
            json.dump(trans_payload, f, indent=4)

        # 4. Learnset (DT_WazaMasterLevel_Common)
        raw_dir = os.path.join(mod_root, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        
        learnset_list = p.get("Learnset", [])
        if learnset_list:
            learnset_rows = {}
            for idx, entry in enumerate(learnset_list):
                row_key = f"{pal_id}_Learn_{idx+1}"
                learnset_rows[row_key] = {
                    "PalId": f"MOD_{pal_id}",
                    "WazaID": f"EPalWazaID::{entry['WazaID']}",
                    "Level": entry["Level"]
                }
                # Boss variation shares learnset
                if p.get("GenerateBoss", True) is not False:
                    learnset_rows[f"BOSS_{row_key}"] = {
                        "PalId": f"MOD_BOSS_{pal_id}",
                        "WazaID": f"EPalWazaID::{entry['WazaID']}",
                        "Level": entry["Level"]
                    }
                
            with open(os.path.join(raw_dir, "DT_WazaMasterLevel_Common.json"), "w", encoding="utf-8") as f:
                json.dump({ "DT_WazaMasterLevel_Common": learnset_rows }, f, indent=4)

        # 5. Item Drops & Loot (DT_PalDropItem)
        loot_table = {}
        item_drops = p.get("ItemDrops", [])
        
        if item_drops:
            drop_row = { "CharacterID": f"MOD_{pal_id}", "Level": 0 }
            for i in range(1, 11):
                if i - 1 < len(item_drops):
                    d = item_drops[i - 1]
                    drop_row[f"ItemId{i}"] = d["itemId"]
                    drop_row[f"Rate{i}"] = float(d["rate"])
                    drop_row[f"min{i}"] = int(d["min"])
                    drop_row[f"Max{i}"] = int(d["max"])
                else:
                    drop_row[f"ItemId{i}"] = "None"
                    drop_row[f"Rate{i}"] = 0.0
                    drop_row[f"min{i}"] = 0
                    drop_row[f"Max{i}"] = 0
            loot_table[f"MOD_{pal_id}000"] = drop_row
        else:
            # Fallback to parent template drops
            parent_drops = {}
            if hasattr(self.c, "pal_drop_item_cache"):
                parent_drops = self.c.pal_drop_item_cache.get(f"{template_id}000", {})
            if not parent_drops:
                parent_drops = { "ItemId1": "Money", "Rate1": 100.0, "min1": 10, "Max1": 50 }
            loot_table[f"MOD_{pal_id}000"] = parent_drops

        # Boss loot with token
        if p.get("GenerateBoss", True) is not False:
            boss_drops = dict(loot_table[f"MOD_{pal_id}000"])
            if p.get("GenerateBountyToken"):
                boss_drops["ItemId1"] = f"BossDefeatReward_{pal_id}"
                boss_drops["Rate1"] = 100.0
                boss_drops["min1"] = 1
                boss_drops["Max1"] = 1
            loot_table[f"MOD_BOSS_{pal_id}000"] = boss_drops

        with open(os.path.join(raw_dir, "DT_PalDropItem.json"), "w", encoding="utf-8") as f_drop:
            json.dump({ "DT_PalDropItem": loot_table }, f_drop, indent=4)

        # 6. Breeding Combos (DT_PalCombiUnique)
        combos = p.get("BreedingCombos", [])
        if combos:
            combi_rows = {}
            for idx, combo in enumerate(combos):
                pA = combo["parentA"]
                pB = combo["parentB"]
                tribeA = pA if pA.startswith("EPalTribeID::") else f"EPalTribeID::{pA}"
                tribeB = pB if pB.startswith("EPalTribeID::") else f"EPalTribeID::{pB}"
                
                combi_rows[f"MOD_{pal_id}_Combi_{idx+1}"] = {
                    "ParentTribeA": tribeA,
                    "ParentGenderA": "EPalGenderType::None",
                    "ParentTribeB": tribeB,
                    "ParentGenderB": "EPalGenderType::None",
                    "ChildCharacterID": f"MOD_{pal_id}"
                }
            with open(os.path.join(raw_dir, "DT_PalCombiUnique.json"), "w", encoding="utf-8") as f_combi:
                json.dump({ "DT_PalCombiUnique": combi_rows }, f_combi, indent=4)

        # 7. Syndicate Cage Spawns (DT_CapturedCagePal)
        cages = p.get("CageSpawns", [])
        if cages:
            cage_rows = {}
            for idx, field in enumerate(cages):
                cage_rows[f"MOD_{pal_id}_Cage_{idx+1}"] = {
                    "FieldName": field,
                    "PalId": f"MOD_{pal_id}",
                    "Weight": 1.0,
                    "MinLevel": 15,
                    "MaxLevel": 30
                }
            with open(os.path.join(raw_dir, "DT_CapturedCagePal.json"), "w", encoding="utf-8") as f_cage:
                json.dump({ "DT_CapturedCagePal": cage_rows }, f_cage, indent=4)

        # 8. Bounty Token Items (items/ folder)
        if p.get("GenerateBountyToken"):
            items_dir = os.path.join(mod_root, "items")
            os.makedirs(items_dir, exist_ok=True)
            token_payload = {
                f"BossDefeatReward_{pal_id}": {
                    "Name": f"{p['Name']} Bounty Token",
                    "Description": f"Proof of defeating [{p.get('BossPrefix', 'Alpha')} {p['Name']}]. Possessing it proves your victory.",
                    "Type": "Generic",
                    "TypeA": "Essential",
                    "TypeB": "Essential_BossReward",
                    "Rank": 1,
                    "Rarity": 1,
                    "Price": 1,
                    "MaxStackCount": 9999,
                    "Weight": 0.0,
                    "VisualBlueprintClassSoft": "/Game/Pal/Blueprint/Item/VisualModel/BP_Item_CoinGold.BP_Item_CoinGold_C"
                }
            }
            with open(os.path.join(items_dir, f"{pal_id}_tokens.json"), "w", encoding="utf-8") as f_item:
                json.dump(token_payload, f_item, indent=4)

        # 9. Actor Blueprints Class Mapping (DT_PalBPClass)
        bp_virtual_path_base = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{custom_folder_name}/{custom_asset_name}.{custom_asset_name}_C"
        bp_virtual_path_boss = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{custom_folder_name}/{custom_asset_name}_BOSS.{custom_asset_name}_BOSS_C"
        bp_virtual_path_pred = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{custom_folder_name}/{custom_asset_name}_PREDATOR.{custom_asset_name}_PREDATOR_C"

        bp_class_payload = {
            f"MOD_{pal_id}": { "BPClass": bp_virtual_path_base }
        }
        if p.get("GenerateBoss", True) is not False:
            bp_class_payload[f"MOD_BOSS_{pal_id}"] = { "BPClass": bp_virtual_path_boss }
        if p.get("GeneratePredator", False):
            bp_class_payload[f"MOD_PREDATOR_{pal_id}"] = { "BPClass": bp_virtual_path_pred }

        with open(os.path.join(raw_dir, "DT_PalBPClass.json"), "w", encoding="utf-8") as f_bp:
            json.dump({ "DT_PalBPClass": bp_class_payload }, f_bp, indent=4)

        # 10. Partner Skill Blueprint Data & Passive Buff Auto-Generation
        saddle_item = p.get("SaddleItem", "None")
        player_buff = p.get("PartnerPlayerBuff", "None")
        camp_buff = p.get("PartnerCampBuff", "None")
        drop_items = p.get("PartnerDropItems", [])
        partner_skill_id = p.get("PartnerSkill", "None")

        generated_passives = {}
        
        # Clone parent's PartnerSkillParameter base structure to inherit their actual skill configs!
        parent_params = {}
        if hasattr(self.c, "partner_skill_params_cache"):
            parent_params = self.c.partner_skill_params_cache.get(template_id, {})
            
        # Initialize the 5 rank arrays from the parent if they exist
        partner_skill_levels = []
        parent_passives = parent_params.get("PassiveSkills", [])
        for i in range(5):
            if i < len(parent_passives) and isinstance(parent_passives[i], dict):
                arr = parent_passives[i].get("SkillAndParametersArray", [])
                partner_skill_levels.append(list(arr))
            else:
                partner_skill_levels.append([])

        if player_buff != "None" or camp_buff != "None" or drop_items:
            for rank in range(1, 6):
                skills_for_this_rank = []

                # 1. Periodic Item Drops (GainItemDrop effect)
                if drop_items:
                    drop_passive_id = f"MOD_{pal_id}_DropBuff_{rank}"
                    generated_passives[drop_passive_id] = {
                        "Rank": 1,
                        "LotteryWeight": 100,
                        "EffectType1": "EPalPassiveSkillEffectType::GainItemDrop",
                        "EffectValue1": 100.0 * rank,
                        "TargetType1": "EPalPassiveSkillEffectTargetType::ToSelfAndTrainer",
                        "EffectType2": "EPalPassiveSkillEffectType::CollectItemDrop",
                        "EffectValue2": 100.0 * rank,
                        "TargetType2": "EPalPassiveSkillEffectTargetType::ToSelfAndTrainer",
                        "InvokeActiveOtomo": True,
                        "InvokeAlways": False,
                        "Category": "EPalPassiveCategory::SortNotDisplayable"
                    }
                    skills_for_this_rank.append({
                        "SkillName": { "Key": drop_passive_id },
                        "Parameters": {
                            "ItemParam": {
                                "ItemIds": [{"Key": item} for item in drop_items]
                            }
                        }
                    })

                # 2. Player Stat Buffs
                if player_buff != "None":
                    stat_passive_id = f"MOD_{pal_id}_StatBuff_{rank}"
                    effect_map = {
                        "Attack": "EPalPassiveSkillEffectType::ShotAttack",
                        "Defense": "EPalPassiveSkillEffectType::Defense",
                        "WorkSpeed": "EPalPassiveSkillEffectType::WorkSpeed"
                    }
                    generated_passives[stat_passive_id] = {
                        "Rank": 1,
                        "LotteryWeight": 100,
                        "EffectType1": effect_map.get(player_buff, "EPalPassiveSkillEffectType::no"),
                        "EffectValue1": 5.0 + (rank * 2.0), # Scales 7%, 9%, 11%, 13%, 15%
                        "TargetType1": "EPalPassiveSkillEffectTargetType::ToTrainer",
                        "InvokeAlways": True,
                        "IsStackablePartnerSkillBySameTribe": True,
                        "Category": "EPalPassiveCategory::SortNotDisplayable"
                    }
                    skills_for_this_rank.append({
                        "SkillName": { "Key": stat_passive_id },
                        "Parameters": {}
                    })

                # 3. Base Camp Work Suitability Buffs
                if camp_buff != "None":
                    camp_passive_id = f"WorkSuitabilityAddRank_{camp_buff}"
                    skills_for_this_rank.append({
                        "SkillName": { "Key": camp_passive_id },
                        "Parameters": {
                            "bNotAssignSelf": True # Applies to other pals in the camp
                        }
                    })

                partner_skill_levels[rank - 1].extend(skills_for_this_rank)

        # Write the generated passives to DT_PassiveSkill_Main
        if generated_passives:
            with open(os.path.join(raw_dir, "DT_PassiveSkill_Main.json"), "w", encoding="utf-8") as f_pass:
                json.dump({ "DT_PassiveSkill_Main": generated_passives }, f_pass, indent=4)

        # Write the partner skill parameters mapping
        packed_levels = []
        for arr in partner_skill_levels:
            packed_levels.append({"SkillAndParametersArray": arr})

        if packed_levels[0] or parent_params:
            active_skill_block = parent_params.get("ActiveSkill", {
                "SkillName": "Unknown",
                "WazaID": "EPalWazaID::None"
            })
            
            # Inject the custom partner skill name if overridden by the user
            if partner_skill_id and partner_skill_id != "None":
                active_skill_block["SkillName"] = partner_skill_id
            
            partner_param_payload = {
                f"MOD_{pal_id}": {
                    "RestrictionItems": [{"Key": saddle_item}] if saddle_item and saddle_item != "None" else parent_params.get("RestrictionItems", []),
                    "ActiveSkill": active_skill_block,
                    "PassiveSkills": packed_levels
                }
            }
            if p.get("GenerateBoss", True) is not False:
                partner_param_payload[f"MOD_BOSS_{pal_id}"] = partner_param_payload[f"MOD_{pal_id}"]
            if p.get("GeneratePredator", False):
                partner_param_payload[f"MOD_PREDATOR_{pal_id}"] = partner_param_payload[f"MOD_{pal_id}"]

            with open(os.path.join(raw_dir, "DT_PartnerSkillParameter.json"), "w", encoding="utf-8") as f_param:
                json.dump({ "DT_PartnerSkillParameter": partner_param_payload }, f_param, indent=4)

        # Legacy Blueprint Actor Injection (If any basic CoopPassives were set)
        bp_payload = {}
        target_bp_key = f"{custom_asset_name}_C"
        pal_bp_data = {}
        
        if saddle_item and saddle_item != "None":
            pal_bp_data.setdefault("PalPartnerSkillParameter", {})["RestrictionItems"] = [{"Key": saddle_item}]
        
        coop_passives_list = []
        for cp_id in p.get("CoopPassives", []):
            if cp_id and cp_id != "None":
                coop_passives_list.append({
                    "SkillAndParameters": [{"Key": {"Key": cp_id}, "Value": {"TriggerTypeFlags": 4}}]
                })
        if coop_passives_list:
            pal_bp_data.setdefault("PalPartnerSkillParameter", {})["PassiveSkills"] = coop_passives_list

        if pal_bp_data:
            bp_payload[target_bp_key] = pal_bp_data
            blueprints_dir = os.path.join(mod_root, "blueprints")
            os.makedirs(blueprints_dir, exist_ok=True)
            with open(os.path.join(blueprints_dir, f"{pal_id}_blueprint.json"), "w", encoding="utf-8") as f_bp:
                json.dump(bp_payload, f_bp, indent=4)

        # 10b. Player Weapon Animation & Gender Changer Registration
        lookup_key = partner_skill_id if partner_skill_id in KNOWN_PARTNER_WEAPONS else template_id
        if lookup_key in KNOWN_PARTNER_WEAPONS:
            wp_info = KNOWN_PARTNER_WEAPONS[lookup_key]
            wp_class_name = f"BP_{pal_id}_{wp_info['weapon_suffix']}"
            wp_class_path = f"/Game/Pal/Blueprint/Weapon/{wp_class_name}.{wp_class_name}_C"

            player_anim_payload = {
                "BP_Player_Female_C": {
                    "ShooterComponent": {
                        "OtherWeaponAnimeAssetBPSoftClassMap": [
                            {
                                "Key": wp_class_path,
                                "Value": wp_info["female_anime"]
                            }
                        ]
                    }
                },
                "BP_PlayerGenderChanger_C": {
                    "MaleCharacterParams": {
                        "OtherWeaponAnimeAssetBPSoftClassMap": [
                            {
                                "Key": wp_class_path,
                                "Value": wp_info["male_anime"]
                            }
                        ]
                    },
                    "FemaleCharacterParams": {
                        "OtherWeaponAnimeAssetBPSoftClassMap": [
                            {
                                "Key": wp_class_path,
                                "Value": wp_info["female_anime"]
                            }
                        ]
                    }
                }
            }

            if "camera_offset" in wp_info:
                player_anim_payload["BP_Player_Female_C"]["CameraBoom"] = {
                    "UniqueWeaponStandCameraParameterMap": [
                        {
                            "Key": wp_class_path,
                            "Value": wp_info["camera_offset"]
                        }
                    ]
                }

            blueprints_dir = os.path.join(mod_root, "blueprints")
            os.makedirs(blueprints_dir, exist_ok=True)
            with open(os.path.join(blueprints_dir, f"{pal_id}_player_weapon_anim.json"), "w", encoding="utf-8") as f_pwa:
                json.dump(player_anim_payload, f_pwa, indent=4)

        # 11. Icon Row
        fmodel_base = self.c.settings.get("fmodel_output", "")
        if fmodel_base:
            custom_icon_path = os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", pal_id, f"T_{pal_id}_icon_normal.png"))
            if os.path.exists(custom_icon_path):
                icon_key = f"MOD_{pal_id}" if paldex_type == "Species" else template_id
                icon_asset_path = f"/Game/Pal/Texture/PalIcon/Normal/T_{pal_id}_icon_normal.T_{pal_id}_icon_normal"
                with open(os.path.join(raw_dir, "DT_PalCharacterIconDataTable.json"), "w", encoding="utf-8") as f_ic:
                    json.dump({ "DT_PalCharacterIconDataTable": { icon_key: { "Icon": icon_asset_path } } }, f_ic, indent=4)

        # 12. Camera Offsets
        parent_offset = self.c.camera_offsets_cache.get(template_id, {
            "LocationOffset": { "X": 333.0, "Y": 800.0, "Z": 130.0 },
            "Rotator": { "Pitch": 3.0, "Yaw": 248.0, "Roll": 0.0 }
        })
        camera_payload = {
            f"MOD_{pal_id}": parent_offset,
            f"MOD_BOSS_{pal_id}": parent_offset
        }
        with open(os.path.join(raw_dir, "DT_PalUICaptureCameraOffsetData.json"), "w", encoding="utf-8") as f_cam:
            json.dump({ "DT_PalUICaptureCameraOffsetData": camera_payload }, f_cam, indent=4)

        # 13. Overworld Spawners (Blueprint Infiltration)
        if p.get("EnableSpawns", True):
            blueprints_dir = os.path.join(mod_root, "blueprints")
            os.makedirs(blueprints_dir, exist_ok=True)
            spawn_location = p.get("SpawnLocationID", "1_1_plain_begginer")
            spawner_bp_path = f"/Game/Pal/Blueprint/Spawner/SheetsVariant/BP_PalSpawner_Sheets_{spawn_location}.BP_PalSpawner_Sheets_{spawn_location}_C"
            
            spawner_items = [
                {
                    "Weight": int(p.get("SpawnWeight", 40)),
                    "PalList": [
                        {
                            "PalId": { "Key": f"MOD_{pal_id}" },
                            "Level": int(p.get("SpawnMinLevel", 2)),
                            "Level_Max": int(p.get("SpawnMaxLevel", 5)),
                            "Num": int(p.get("SpawnMinGroup", 1)),
                            "Num_Max": int(p.get("SpawnMaxGroup", 3))
                        }
                    ]
                }
            ]

            # Predator encounter at night
            if p.get("GeneratePredator", False):
                spawner_items.append({
                    "Weight": 5,
                    "OnlyTime": "EPalOneDayTimeType::Night",
                    "PalList": [
                        {
                            "PalId": { "Key": f"MOD_PREDATOR_{pal_id}" },
                            "Level": int(p.get("SpawnMaxLevel", 5)) + 15,
                            "Level_Max": int(p.get("SpawnMaxLevel", 5)) + 20,
                            "Num": 1,
                            "Num_Max": 1
                        }
                    ]
                })

            spawner_payload = {
                spawner_bp_path: {
                    "SpawnGroupList": {
                        "Items": spawner_items
                    }
                }
            }
            with open(os.path.join(blueprints_dir, f"{pal_id}_spawner_bp.json"), "w", encoding="utf-8") as f_bp:
                json.dump(spawner_payload, f_bp, indent=4)

        # 14. Fixed Field Boss Spawner Coordinates (BossSpawn.json)
        field_boss_spawns = p.get("FieldBossSpawns", [])
        if field_boss_spawns:
            spawners_dir = os.path.join(mod_root, "spawners")
            os.makedirs(spawners_dir, exist_ok=True)
            boss_spawn_entries = []
            for idx, fb in enumerate(field_boss_spawns):
                boss_spawn_entries.append({
                    "Type": "Sheet",
                    "Location": { "X": fb.get("x", 0.0), "Y": fb.get("y", 0.0), "Z": fb.get("z", 0.0) },
                    "Rotation": { "Pitch": 0.0, "Yaw": 0.0, "Roll": 0.0 },
                    "SpawnerName": f"BOSS_MOD_{pal_id}_Spawn_{idx+1}",
                    "SpawnerType": "FieldBoss",
                    "SpawnGroupList": [
                        {
                            "Weight": 100,
                            "PalList": [
                                {
                                    "PalId": f"MOD_BOSS_{pal_id}",
                                    "Level": int(fb.get("level", 50)),
                                    "Level_Max": int(fb.get("level", 50)),
                                    "Num": 1,
                                    "Num_Max": 1
                                }
                            ]
                        }
                    ]
                })
            with open(os.path.join(spawners_dir, f"{pal_id}_BossSpawn.json"), "w", encoding="utf-8") as f_bs:
                json.dump(boss_spawn_entries, f_bs, indent=4)

        # 15. Deploy to Palworld directory
        game_mods_dir = self.get_palschema_mods_dir()
        if game_mods_dir:
            game_mod_root = os.path.join(game_mods_dir, mod_name)
            if os.path.exists(game_mod_root):
                for root, dirs, files in os.walk(game_mod_root, topdown=False):
                    for file in files:
                        try: os.remove(os.path.join(root, file))
                        except OSError: pass
                    for directory in dirs:
                        try: os.rmdir(os.path.join(root, directory))
                        except OSError: pass
                try:
                    os.rmdir(game_mod_root)
                except OSError: pass
            try:
                shutil.copytree(mod_root, game_mod_root, dirs_exist_ok=True)
                self.c.view.write_log(f"Successfully deployed PalSchema schemas to game: {mod_name}", "success")
            except Exception as e:
                self.c.view.write_log(f"Failed to deploy PalSchema config to game: {e}", "error")
                raise RuntimeError(f"Deployment failed: {e}")
        else:
            self.c.view.write_log("Game PalSchema directory not found. Saved schemas locally in workspace.", "warning")