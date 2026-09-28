# pythoncli/utils/creator/pal_manager.py
import os
import json
import re
import threading

FLYING_TEMPLATES = {
    "JetDragon", "Horus", "Suzaku", "Suzaku_Water", "HadesBird",
    "ThunderBird", "ThunderBird_Ice", "BirdDragon", "BirdDragon_Ice",
    "Eagle", "FairyDragon", "FairyDragon_Water", "GhostDragon",
    "BlackGriffon", "WhiteShieldDragon", "BlueSkyDragon", "CuteButterfly",
    "DreamDemon"
}

BIG_MOUNT_TEMPLATES = {
    "Grassmammoth", "Grassmammoth_Ice", "KingAlpaca", "KingAlpaca_Ice",
    "ElecPanda", "GrassPanda", "GrassPanda_Electric", "Gorilla",
    "Baphomet", "Baphomet_Dark", "AmaterasuWolf", "AmaterasuWolf_Dark",
    "Deer", "IceDeer", "Boar", "ThunderDog", "ThunderDog_Ice",
    "Garm", "Umihebi", "Umihebi_Fire", "SakuraSaurus", "SakuraSaurus_Water",
    "Manticore", "Manticore_Dark", "FireKirin", "FireKirin_Dark",
    "Kirin", "Kirin_Ice", "JetDragon", "BlueSkyDragon", "SaintCentaur",
    "BlackCentaur", "FengyunDeeper", "RaijinDaughter"
}

SIT_MOUNT_TEMPLATES = {
    "KingAlpaca", "KingAlpaca_Ice", "ElecPanda", "GrassPanda", "GrassPanda_Electric", "Gorilla"
}

TRAMPLE_TEMPLATES = {
    "Boar", "Deer", "IceDeer", "KingAlpaca", "KingAlpaca_Ice",
    "Grassmammoth", "Grassmammoth_Ice", "FeatherOstrich", "TropicalOstrich",
    "NightBlueHorse", "NightBlueHorse_Neutral"
}

MOUNTED_SHOOTER_TEMPLATES = {
    "Deer", "IceDeer", "Boar", "AmaterasuWolf", "AmaterasuWolf_Dark",
    "Kirin", "Kirin_Ice", "FireKirin", "FireKirin_Dark",
    "ThunderDog", "ThunderDog_Ice", "BlueThunderHorse", "Garm"
}

WEAPON_PARTNER_TEMPLATES = {
    "Kitsunebi": { "Mode": "Flamethrower", "Element": "EPalElementType::Fire", "Effect": "EPalAdditionalEffectType::Burn", "Niagara": "Pal/Content/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower" },
    "Kitsunebi_Ice": { "Mode": "Flamethrower", "Element": "EPalElementType::Ice", "Effect": "EPalAdditionalEffectType::Freeze", "Niagara": "Pal/Content/Pal/Effect/Skill/FrostBreath/NS_CommonSkill_FrostBreath" },
    "Penguin": { "Mode": "Launcher", "Element": "EPalElementType::Water", "Effect": "EPalAdditionalEffectType::None", "Niagara": "Pal/Content/Pal/Effect/Skill/BlastCanon/NS_CommonSkill_BlastCannon_Impact" },
    "Monkey": { "Mode": "AssaultRifle", "Element": "EPalElementType::Leaf", "Effect": "EPalAdditionalEffectType::None", "Niagara": "Pal/Content/Pal/Effect/Skill/SeedMachinegun/NS_CommonSkill_SeedMachinegun" },
    "Carbunclo": { "Mode": "OnHeadSubmachineGun", "Element": "EPalElementType::Leaf", "Effect": "EPalAdditionalEffectType::None" },
    "Grizzbolt": { "Mode": "Minigun", "Element": "EPalElementType::Electricity", "Effect": "EPalAdditionalEffectType::Electrical" },
}

FUNNEL_TEMPLATES = {
    "DreamDemon": { "Preset": "DreamDemon", "TargetingAction": "ShadowBall", "CustomWazaID": "EPalWazaID::Funnel_DreamDemon" },
    "Daedream": { "Preset": "DreamDemon", "TargetingAction": "ShadowBall", "CustomWazaID": "EPalWazaID::Funnel_DreamDemon" },
    "RaijinDaughter": { "Preset": "Dazzi", "TargetingAction": "Thunderbolt", "CustomWazaID": "EPalWazaID::Funnel_RaijinDaughter" },
    "Dazzi": { "Preset": "Dazzi", "TargetingAction": "Thunderbolt", "CustomWazaID": "EPalWazaID::Funnel_RaijinDaughter" },
    "FlowerRabbit": { "Preset": "Flopie", "TargetingAction": "SeedMachinegun", "CustomWazaID": "None" },
    "Flopie": { "Preset": "Flopie", "TargetingAction": "SeedMachinegun", "CustomWazaID": "None" },
}

SHIELD_TEMPLATES = {
    "SheepBall": { "Radius": 90.0, "AttachSocket": "lowerarm_l", "RelativeLocation": { "X": 0.0, "Y": 0.0, "Z": 62.5 } },
    "Lamball": { "Radius": 90.0, "AttachSocket": "lowerarm_l", "RelativeLocation": { "X": 0.0, "Y": 0.0, "Z": 62.5 } },
    "SaintCentaur": { "Radius": 140.0, "AttachSocket": "lowerarm_l" },
    "Paladius": { "Radius": 140.0, "AttachSocket": "lowerarm_l" },
}

EVASION_TEMPLATES = {
    "Anubis": { "SideMoveStyle": "Teleport", "LeaveStyle": "BackStep" },
    "DarkScorpion": { "SideMoveStyle": "RoundStep", "LeaveStyle": "BackStep" },
    "AmaterasuWolf": { "SideMoveStyle": "DashTurn", "LeaveStyle": "TurnRun" },
    "AmaterasuWolf_Dark": { "SideMoveStyle": "DashTurn", "LeaveStyle": "TurnRun" },
    "Ronin": { "SideMoveStyle": "SideStep", "LeaveStyle": "BackStep" },
}

UTILITY_TEMPLATES = {
    "LilyQueen": "HealLilyQueen",
    "LilyQueen_Dark": "HealLilyQueen",
    "Lyleen": "HealLilyQueen",
    "Lyleen_Noct": "HealLilyQueen",
    "FairyCat": "Heal",
    "Petallia": "Heal",
    "FeatherOstrich": "ReturnToCamp",
    "Mallow": "OpenTreasure"
}

LIGHT_TEMPLATES = {
    "Kitsunebi", "Foxcicle", "DreamDemon", "Daedream", "RaijinDaughter",
    "Dazzi", "Rayhound", "ThunderDog", "VolcanicMonster", "DarkScorpion"
}

def infer_template_features(template_id: str, base_props: dict, parent_params: dict, saddle_item: str, partner_skill: str) -> dict:
    features = {
        "CustomFeaturesEnabled": False,
        "Riding": { "Enabled": False },
        "Flight": { "Enabled": False },
        "CoopWeapon": { "Enabled": False },
        "Funnel": { "Enabled": False },
        "Shield": { "Enabled": False },
        "CombatEvasion": { "SideMoveStyle": "None", "LeaveStyle": "None" },
        "CoopUtility": { "SkillType": "None" },
        "VFX": [],
        "LocomotionLeaning": {},
        "TimerPointLight": { "Enabled": False }
    }

    # 1. Riding
    is_weapon_or_funnel = (template_id in WEAPON_PARTNER_TEMPLATES or template_id in FUNNEL_TEMPLATES)
    is_rideable = (
        not is_weapon_or_funnel and (
            template_id in BIG_MOUNT_TEMPLATES or 
            template_id in SIT_MOUNT_TEMPLATES or 
            "Ride" in partner_skill or
            "Saddle" in saddle_item
        )
    )
    if is_rideable:
        marker_type = "Sit" if template_id in SIT_MOUNT_TEMPLATES else ("BiggerHorse" if (template_id in BIG_MOUNT_TEMPLATES or base_props.get("Size") in ["EPalSizeType::L", "EPalSizeType::XL"]) else "Saddle")
        ride_pos = "Sit" if marker_type == "Sit" else ("BiggerHorseRide" if marker_type == "BiggerHorse" else "HorseRide")
        
        # Vanilla mount skeletons have dedicated 'PlayerRideMarker' sockets.
        # Non-mountable Pals (like Kitsunebi, SheepBall, CatMage) do NOT have this socket;
        # attaching to non-existent sockets causes bone index -1 -> NaN transforms -> D3D11 buffer crash.
        has_dedicated_marker = (
            template_id in BIG_MOUNT_TEMPLATES or 
            template_id in SIT_MOUNT_TEMPLATES or 
            template_id in FLYING_TEMPLATES
        )
        attach_socket = "PlayerRideMarker" if has_dedicated_marker else "pelvis"
        pitch_rot = 90.0 if has_dedicated_marker else 0.0
        z_offset = 10.0 if has_dedicated_marker else 40.0

        features["Riding"] = {
            "Enabled": True,
            "MarkerType": marker_type,
            "RidePosition": ride_pos,
            "AttachSocket": attach_socket,
            "WithSpeedCollision": template_id in TRAMPLE_TEMPLATES,
            "WithMountedShooter": template_id in MOUNTED_SHOOTER_TEMPLATES,
            "RelativeRotation": { "Pitch": pitch_rot, "Yaw": 0.0, "Roll": 0.0 },
            "RelativeLocation": { "X": 0.0, "Y": 0.0, "Z": z_offset }
        }

    # 2. Flight
    if template_id in FLYING_TEMPLATES:
        features["Flight"] = { "Enabled": True }

    # 3. Weapons
    if template_id in WEAPON_PARTNER_TEMPLATES:
        wp_cfg = WEAPON_PARTNER_TEMPLATES[template_id]
        features["CoopWeapon"] = {
            "Enabled": True,
            "Mode": wp_cfg.get("Mode", "AssaultRifle"),
            "Element": wp_cfg.get("Element", "EPalElementType::Fire"),
            "Effect": wp_cfg.get("Effect", "EPalAdditionalEffectType::Burn"),
            "Niagara": wp_cfg.get("Niagara", "")
        }

    # 4. Funnels
    if template_id in FUNNEL_TEMPLATES:
        fn_cfg = FUNNEL_TEMPLATES[template_id]
        features["Funnel"] = {
            "Enabled": True,
            "Preset": fn_cfg["Preset"],
            "TargetingAction": fn_cfg["TargetingAction"],
            "CustomWazaID": fn_cfg["CustomWazaID"]
        }

    # 5. Shields
    if template_id in SHIELD_TEMPLATES:
        sh_cfg = SHIELD_TEMPLATES[template_id]
        features["Shield"] = {
            "Enabled": True,
            "Radius": sh_cfg.get("Radius", 90.0),
            "AttachSocket": sh_cfg.get("AttachSocket", "lowerarm_l"),
            "RelativeLocation": sh_cfg.get("RelativeLocation")
        }

    # 6. Evasion
    if template_id in EVASION_TEMPLATES:
        features["CombatEvasion"] = dict(EVASION_TEMPLATES[template_id])

    # 7. Utility
    if template_id in UTILITY_TEMPLATES:
        features["CoopUtility"] = { "SkillType": UTILITY_TEMPLATES[template_id] }

    # 8. Point Light
    if template_id in LIGHT_TEMPLATES:
        features["TimerPointLight"] = { "Enabled": True }

    return features

class PalManager:
    def __init__(self, controller):
        self.c = controller

    def get_creator_dir(self) -> str | None:
        fmodel_base = self.c.settings.get("fmodel_output", "")
        if not fmodel_base: return None
        return os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Palbaker", "Creator"))

    def load_custom_pals(self):
        """Scans the local Palbaker Creator directory and parses existing custom Pal JSONs."""
        self.c.custom_pals.clear()
        creator_dir = self.get_creator_dir()
        if not creator_dir or not os.path.exists(creator_dir):
            return

        fmodel_base = self.c.settings.get("fmodel_output", "")

        for f in os.listdir(creator_dir):
            if f.endswith("_creator.json"):
                f_path = os.path.join(creator_dir, f)
                try:
                    with open(f_path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        
                        # Resolve icon path on backend to prevent front-end blocking I/O!
                        pal_id = data.get("CharacterID", "")
                        resolved_icon_path = ""
                        if fmodel_base and pal_id:
                            custom_icon_path = os.path.normpath(os.path.join(
                                fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", pal_id, f"T_{pal_id}_icon_normal.png"
                            ))
                            shared_icon_path = os.path.normpath(os.path.join(
                                fmodel_base, "Exports", "Pal", "Content", "Pal", "Texture", "PalIcon", "Normal", f"T_{pal_id}_icon_normal.png"
                            ))
                            if os.path.exists(custom_icon_path):
                                resolved_icon_path = custom_icon_path
                            elif os.path.exists(shared_icon_path):
                                resolved_icon_path = shared_icon_path
                        
                        data["resolved_icon_path"] = resolved_icon_path
                        
                        # Resolve all_bones from the model's companion sidecar
                        all_bones = []
                        if fmodel_base:
                            template_id = data.get("TemplateID", "")
                            sidecar_candidates = [
                                os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", pal_id, f"{pal_id}_blend.json")),
                                os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", pal_id, f"{template_id}_blend.json")),
                                os.path.normpath(os.path.join(fmodel_base, "Exports", "Pal", "Content", "Pal", "Model", "Character", "Monster", template_id, f"{template_id}_blend.json")),
                            ]
                            for sc in sidecar_candidates:
                                if os.path.exists(sc):
                                    try:
                                        with open(sc, "r", encoding="utf-8") as f_sc:
                                            sc_json = json.load(f_sc)
                                            if "all_bones" in sc_json and isinstance(sc_json["all_bones"], list):
                                                all_bones = sc_json["all_bones"]
                                                break
                                    except Exception:
                                        pass
                        data["all_bones"] = all_bones
                        
                        self.c.custom_pals.append(data)
                except Exception: pass

    def add_custom_pal(self, pal_id: str, template_id: str, sync: bool = False):
        """Clones a parent template from cache and instantiates a new Creator JSON on disk."""
        creator_dir = self.get_creator_dir()
        if not creator_dir:
            self.c.view.show_snackbar("Configure your Workspace Folder first.", "#E53935")
            return

        clean_id = re.sub(r'[^a-zA-Z0-9_]', '_', pal_id.strip())
        if not clean_id: return

        if any(p.get("CharacterID") == clean_id for p in self.c.custom_pals):
            self.c.view.show_snackbar(f"Error: A Pal named '{clean_id}' already exists!", "#E53935")
            return

        from utils.names import load_names_map
        names_map = load_names_map()
        if clean_id in names_map:
            self.c.view.show_snackbar(f"Error: '{clean_id}' is a reserved vanilla Pal name.", "#E53935")
            return

        def background_adder():
            import time
            if not sync:
                time.sleep(0.1)
            
            os.makedirs(creator_dir, exist_ok=True)
            
            base_properties = self.c.templates_cache.get(template_id, {})
            cloned_learnset = self.c.learnsets_cache.get(template_id, [])

            # Query Partner Skill Parameter table for exact active skill and unlock item
            parent_params = {}
            if hasattr(self.c, "partner_skill_params_cache"):
                parent_params = self.c.partner_skill_params_cache.get(template_id, {})

            # 1. Resolve exact default partner skill identifier
            resolved_partner_skill = "None"
            active_skill_name = parent_params.get("ActiveSkill", {}).get("SkillName")
            if active_skill_name and active_skill_name != "Unknown" and active_skill_name != "None":
                resolved_partner_skill = active_skill_name
            elif base_properties.get("PartnerSkill") and base_properties.get("PartnerSkill") != "None":
                resolved_partner_skill = base_properties.get("PartnerSkill")

            # 2. Resolve exact saddle / harness unlock item
            resolved_saddle = f"SkillUnlock_{template_id}"
            restriction_items = parent_params.get("RestrictionItems", [])
            if restriction_items and isinstance(restriction_items, list) and len(restriction_items) > 0:
                item_key = restriction_items[0].get("Key")
                if item_key and item_key != "None":
                    resolved_saddle = item_key

            predicted_coop_passives = []
            if "weaseldragon" in template_id.lower() or "amaterasuwolf" in template_id.lower():
                predicted_coop_passives.append("GiveADragon_Ride")

            predicted_spawner = self.c.monster_spawners_default_map.get(template_id, "1_1_plain_begginer")

            new_pal_data = {
                "CharacterID": clean_id,
                "TemplateID": template_id,
                "Name": clean_id,
                "Description": f"A custom standalone Pal cloned from {template_id}.",
                
                "ElementType1": base_properties.get("ElementType1", "EPalElementType::Normal"),
                "ElementType2": base_properties.get("ElementType2", "EPalElementType::None"),
                "Hp": base_properties.get("Hp", 100),
                "MeleeAttack": base_properties.get("MeleeAttack", 100),
                "ShotAttack": base_properties.get("ShotAttack", 100),
                "Defense": base_properties.get("Defense", 100),
                "Support": base_properties.get("Support", 100),
                "CraftSpeed": base_properties.get("CraftSpeed", 100),

                "PartnerSkill": resolved_partner_skill,
                "PartnerWeaponElement": base_properties.get("ElementType1", "EPalElementType::Fire"),
                "PartnerWeaponEffectType": "EPalAdditionalEffectType::Burn",
                "PartnerWeaponNiagara": "Pal/Content/Pal/Effect/Skill/FlameThrower/NS_CommonSkill_Flamethrower",
                "Learnset": cloned_learnset,
                "SaddleItem": resolved_saddle,
                
                "Size": base_properties.get("Size", "EPalSizeType::M"),
                "Rarity": base_properties.get("Rarity", 1),
                "Price": base_properties.get("Price", 1000.0),
                "WalkSpeed": base_properties.get("WalkSpeed", 100),
                "RunSpeed": base_properties.get("RunSpeed", 500),
                "RideSprintSpeed": base_properties.get("RideSprintSpeed", 700),
                "TransportSpeed": base_properties.get("TransportSpeed", 200),
                "FoodAmount": base_properties.get("FoodAmount", 1),
                "Stamina": base_properties.get("Stamina", 100),
                "MaleProbability": base_properties.get("MaleProbability", 50),
                "CombiRank": base_properties.get("CombiRank", 100),
                "CaptureRateCorrect": base_properties.get("CaptureRateCorrect", 1.0),

                "MeshCapsuleHalfHeight": base_properties.get("MeshCapsuleHalfHeight", 110.0),
                "MeshCapsuleRadius": base_properties.get("MeshCapsuleRadius", 50.0),
                "MeshRelativeLocation": base_properties.get("MeshRelativeLocation", {"X": 0.0, "Y": 0.0, "Z": -110.0}),

                "BaseSkills": ["AirCanon", "IgnisBlast"],
                "PassiveSkills": [],
                "PartnerSkill": resolved_partner_skill,
                "Learnset": cloned_learnset,
                "SaddleItem": resolved_saddle,
                "CoopPassives": predicted_coop_passives,
                "HasFunnel": False,
                "FunnelWazaID": "Funnel_DreamDemon",
                 "WildSpawners": [
                    {
                        "SpawnLocationID": predicted_spawner,
                        "SpawnWeight": 40,
                        "SpawnMinLevel": 2,
                        "SpawnMaxLevel": 5,
                        "SpawnMinGroup": 1,
                        "SpawnMaxGroup": 3
                    }
                ],
                "EnablePaldeck": True,
                "ZukanIndex": -1,
                "ZukanIndexSuffix": "",
                "LongDescription": f"A custom standalone Pal cloned from {template_id}.",
                "PaldexType": "Species"
            }
            
            # Initialize WorkSuitabilities map & legacy keys
            new_suits = {}
            default_anim_map = {
                "EmitFlame": "Cooking", "Watering": "WaterGun", "Seeding": "Seeding",
                "GenerateElectricity": "GenerateElectricity", "Handcraft": "CommonWork",
                "Collection": "CommonWork", "Deforest": "Deforest", "Mining": "Mining",
                "OilExtraction": "CommonWork", "ProductMedicine": "ProductMedicine",
                "Cool": "Cool", "Transport": "Transport", "MonsterFarm": "CommonWork"
            }
            for k in base_properties.keys():
                if k.startswith("WorkSuitability_"):
                    lvl = int(base_properties[k])
                    new_pal_data[k] = lvl
                    if lvl > 0:
                        s_name = k.replace("WorkSuitability_", "")
                        new_suits[s_name] = {
                            "Level": lvl,
                            "Animation": default_anim_map.get(s_name, "CommonWork")
                        }

            new_pal_data["WorkSuitabilities"] = new_suits
            new_pal_data["Features"] = infer_template_features(
                template_id, base_properties, parent_params, resolved_saddle, resolved_partner_skill
            )

            target_file = os.path.join(creator_dir, f"{clean_id}_creator.json")
            try:
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(new_pal_data, f, indent=4)
                self.c.view.write_log(f"Successfully created brand new Pal template: {clean_id}", "success")
                
                from utils.extractor.asset_cloner import extract_pal_assets
                self.c.view.write_log(f"Cloning parent assets and setting up workspace for {clean_id}...", "standard")
                success, msg = extract_pal_assets(self.c.settings, clean_id, "Monster")
                if success:
                    self.c.view.write_log(msg, "success")
                else:
                    self.c.view.write_log(f"Workspace cloning failed: {msg}", "warning")

                self.c.exporter.generate_custom_actor_blueprint(new_pal_data)
                self.c.export_to_palschema(new_pal_data)
            except Exception as e:
                self.c.view.write_log(f"Failed to save new Pal: {e}", "error")
                if sync:
                    raise e

            self.refresh_pals()

        if sync:
            background_adder()
        else:
            threading.Thread(target=background_adder, daemon=True).start()

    def save_custom_pal(self, pal_id: str, updated_data: dict, sync: bool = False):
        """Asynchronously writes edited parameters back to the localized JSON file."""
        creator_dir = self.get_creator_dir()
        if not creator_dir: return

        target_file = os.path.join(creator_dir, f"{pal_id}_creator.json")
        
        def background_writer():
            import time
            if not sync:
                time.sleep(0.1)
            try:
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(updated_data, f, indent=4)
                self.c.view.write_log(f"Successfully saved Pal Creator adjustments: {pal_id}", "success")
                
                self.c.export_to_palschema(updated_data)
            except Exception as e:
                self.c.view.write_log(f"Failed to write Pal updates: {e}", "error")
                if sync:
                    raise e
            self.refresh_pals()

        if sync:
            background_writer()
        else:
            threading.Thread(target=background_writer, daemon=True).start()


    def delete_custom_pal(self, pal_id: str, sync: bool = False):
        """Removes the local creator JSON configuration file permanently from disk."""
        creator_dir = self.get_creator_dir()
        if not creator_dir: return

        target_file = os.path.join(creator_dir, f"{pal_id}_creator.json")
        
        def background_deleter():
            import time
            if not sync:
                time.sleep(0.1)
            if os.path.exists(target_file):
                try:
                    os.remove(target_file)
                    self.c.view.write_log(f"Deleted custom Pal config: {pal_id}", "warning")
                    self.c.delete_palschema_export(pal_id)
                except Exception as e:
                    self.c.view.write_log(f"Failed to delete Pal config: {e}", "error")
            self.refresh_pals()

        if sync:
            background_deleter()
        else:
            threading.Thread(target=background_deleter, daemon=True).start()

    def refresh_pals(self):
        """Instructs the main view to re-render using cached list entries."""
        self.load_custom_pals()
        self.c.view.refresh_creator_mods_ui()