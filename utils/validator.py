# utils/validator.py
import os
import json

NATIVE_MOUNT_TEMPLATES = {
    "Boar", "Deer", "IceDeer", "AmaterasuWolf", "AmaterasuWolf_Dark",
    "Kirin", "Kirin_Ice", "FireKirin", "FireKirin_Dark", "ThunderDog", "ThunderDog_Ice",
    "Garm", "Umihebi", "Umihebi_Fire", "SakuraSaurus", "SakuraSaurus_Water",
    "Manticore", "Manticore_Dark", "Grassmammoth", "Grassmammoth_Ice",
    "KingAlpaca", "KingAlpaca_Ice", "ElecPanda", "GrassPanda", "GrassPanda_Electric",
    "Gorilla", "Baphomet", "Baphomet_Dark", "JetDragon", "Horus", "Suzaku", "Suzaku_Water",
    "HadesBird", "ThunderBird", "ThunderBird_Ice", "BirdDragon", "BirdDragon_Ice",
    "Eagle", "FairyDragon", "FairyDragon_Water", "GhostDragon", "BlackGriffon",
    "BlueSkyDragon", "SaintCentaur", "BlackCentaur", "FengyunDeeper", "FeatherOstrich",
    "TropicalOstrich", "NightBlueHorse", "NightBlueHorse_Neutral", "BlueThunderHorse"
}

COMMON_SOCKETS = {
    "root", "socket_weapon_r", "socket_weapon_l", "socket_mouth",
    "socket_head", "socket_eye_l", "socket_eye_r", "playerridemarker"
}

class FeatureDependencyValidator:
    def __init__(self, repo_root: str):
        self.kb_path = os.path.join(repo_root, "deps", "feature_requirements.json")
        self.kb = self._load_knowledge_base()

    def _load_knowledge_base(self) -> dict:
        if os.path.exists(self.kb_path):
            try:
                with open(self.kb_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Fallback Knowledge Base
        return {
            "WorkSuitabilities": {
                "WorkSuitability_EmitFlame": {"action": "Cooking", "notifies": ["PalEffect"]},
                "WorkSuitability_Watering": {"action": "WaterGun", "notifies": ["PalEffect"]},
                "WorkSuitability_Seeding": {"action": "Seeding", "notifies": ["PalEffect"]},
                "WorkSuitability_GenerateElectricity": {"action": "GenerateElectricity", "notifies": ["PalEffect"]},
                "WorkSuitability_Handcraft": {"action": "CommonWork", "notifies": []},
                "WorkSuitability_Mining": {"action": "Mining", "notifies": []},
                "WorkSuitability_Deforest": {"action": "Deforest", "notifies": []},
                "WorkSuitability_ProductMedicine": {"action": "ProductMedicine", "notifies": []},
                "WorkSuitability_Cool": {"action": "Cool", "notifies": ["PalEffect"]}
            },
            "CoopWeapons": {
                "AssaultRifle": {"anims": ["Fire_AssaultRifle"], "notifies": {"Fire_AssaultRifle": ["OnShoot"]}},
                "Shotgun": {"anims": ["Fire_Shotgun"], "notifies": {"Fire_Shotgun": ["OnShoot"]}},
                "Launcher": {"anims": ["Fire_Launcher"], "notifies": {"Fire_Launcher": ["OnShoot"]}},
                "Flamethrower": {"anims": ["Flamethrower", "Flamethrower_Fire_Start", "Flamethrower_Fire"], "notifies": {}}
            },
            "UniqueAttacks": {
                "Unique_Anubis_GroundPunch": {"anims": ["Skill_JimenNaguri_Start", "Skill_JimenNaguri_UpLoop", "Skill_JimenNaguri_DownLoop", "Skill_JimenNaguri_End"], "notifies": {}},
                "Unique_SheepBall_Roll": {"anims": ["Skill_Tackle"], "notifies": {}}
            }
        }

    def validate_dependencies(self, pal_data: dict, sidecar_data: dict) -> list[dict]:
        """
        Cross-references enabled Pal features against:
        1. Valid existing bone/socket attachment names.
        2. Incompatible active skill combinations.
        3. Riding locomotion blendspaces.
        4. Animations and notifies baked in Blender NLA.
        """
        missing = []
        user_anims = sidecar_data.get("custom_animations", {}).get("anims", {})
        is_anim_active = bool(sidecar_data.get("custom_animations", {}).get("is_active", False))
        template_id = pal_data.get("TemplateID", "")
        features = pal_data.get("Features", {})

        # --- 1. ATTACHMENT SOCKET VALIDATION ---
        available_bones = set()
        if "all_bones" in sidecar_data and isinstance(sidecar_data["all_bones"], list):
            for b in sidecar_data["all_bones"]:
                available_bones.add(b.lower())
                available_bones.add(b.replace("_", "").lower())
        else:
            for key in ["offset_bones", "jiggle_bones", "copy_bones"]:
                for item in sidecar_data.get(key, []):
                    bname = item.get("bone_name") or item.get("target_bone")
                    if bname:
                        available_bones.add(bname.lower())

        def check_attachment(feature_name: str, socket_name: str, allow_prm: bool = False):
            if not socket_name or not socket_name.strip():
                missing.append({
                    "feature": feature_name,
                    "missing_type": "attachment",
                    "target_socket": socket_name,
                    "message": f"{feature_name} has an empty or unconfigured attach socket."
                })
                return

            sock_clean = socket_name.strip()
            sock_lower = sock_clean.lower()

            if sock_lower == "playerridemarker":
                if not allow_prm:
                    missing.append({
                        "feature": feature_name,
                        "missing_type": "attachment",
                        "target_socket": sock_clean,
                        "message": (
                            f"AttachSocket '{sock_clean}' does not exist on template '{template_id}'. "
                            f"Non-mountable Pals do not possess a 'PlayerRideMarker' socket and will cause DirectX 11 buffer crashes. "
                            f"Please change AttachSocket to an existing bone (e.g. 'pelvis', 'spine_01', or 'spine_02')."
                        )
                    })
                    return

            if available_bones:
                if sock_lower not in available_bones and sock_lower not in COMMON_SOCKETS:
                    missing.append({
                        "feature": feature_name,
                        "missing_type": "attachment",
                        "target_socket": sock_clean,
                        "message": f"AttachSocket '{sock_clean}' was not found in the model's skeleton. Attaching components to non-existent bones causes invalid transforms and game crashes."
                    })

        # 1a. Validate Riding Saddle Attachment
        riding = features.get("Riding", {})
        
        if riding.get("Enabled"):
            socket = riding.get("AttachSocket", "PlayerRideMarker")
            allow_prm = template_id in NATIVE_MOUNT_TEMPLATES
            check_attachment("Riding Saddle", socket, allow_prm=allow_prm)

        # 1b. Validate Defensive Shield Attachment
        shield = features.get("Shield", {})
        if shield.get("Enabled"):
            socket = shield.get("AttachSocket", "lowerarm_l")
            check_attachment("Defensive Shield", socket, allow_prm=False)

        # 1c. Validate Partner Weapon Attachment
        coop_weapon = features.get("CoopWeapon", pal_data.get("CoopWeapon", {}))
        if coop_weapon.get("Enabled"):
            socket = coop_weapon.get("AttachSocket", "Socket_Weapon_R")
            check_attachment("Partner Weapon", socket, allow_prm=False)

        # 1d. Validate Attached VFX Sockets
        vfx_list = features.get("VFX", [])
        for idx, vfx in enumerate(vfx_list):
            socket = vfx.get("AttachSocket", "root")
            vfx_name = vfx.get("VarName", f"VFX #{idx+1}")
            check_attachment(f"VFX Particle ({vfx_name})", socket, allow_prm=False)

        # 1e. Validate Hand Prop Sockets
        hand_prop = features.get("HandProp", {})
        if hand_prop.get("Enabled"):
            socket = hand_prop.get("AttachSocket", "Socket_Weapon_R")
            check_attachment("Hand Prop", socket, allow_prm=False)

        # --- 2. ACTIVE SKILL CONFLICT VALIDATION ---
        # Riding and CoopWeapon both bind to the player interaction key ('F').
        # Funnels are passive companions and CAN safely run alongside either!
        has_weapon = coop_weapon.get("Enabled", False)
        
        if riding.get("Enabled") and has_weapon:
            missing.append({
                "feature": "Active Skill Conflict",
                "missing_type": "conflict",
                "message": (
                    "Keybind conflict: 'Riding' and 'CoopWeapon' are both enabled. "
                    "In Palworld, a Pal can only bind one active skill to the 'F' key simultaneously. "
                    "(Note: Funnel satellites are passive and CAN be safely combined with either)."
                )
            })

        # --- 3. SADDLE BLENDSPACE DEPENDENCY NOTICE ---
        
        if riding.get("Enabled"):
            is_native_mount = template_id in NATIVE_MOUNT_TEMPLATES
            user_blendspaces = sidecar_data.get("custom_animations", {}).get("blend_spaces", {})
            has_custom_riding_bs = any(k in user_blendspaces for k in ["RidingMove", "Move_Riding", "Riding"])

            if not is_native_mount and not has_custom_riding_bs and not is_anim_active:
                missing.append({
                    "feature": "Riding BlendSpace Notice",
                    "missing_type": "notice",
                    "message": (
                        f"Template '{template_id}' has no native mount animations (BS_Move_{template_id}_Riding). "
                        f"PalBaker will automatically fallback-bind 'EPalGeneralBlendSpaceType::RidingMove' to your GeneralMove "
                        f"locomotion blendspace so that the game does not allocate a null vertex buffer on spawn."
                    )
                })

        # --- 4. ANIMATION & NOTIFY VALIDATION (Only when custom animations active) ---
        if is_anim_active:
            def check_anim(feature_name: str, required_anim: str, required_notifies: list):
                anim_node = next((v for v in user_anims.values() if v.get("nla_track_name", "").lower() == required_anim.lower()), None)
                
                if not anim_node or not anim_node.get("in_nla"):
                    missing.append({
                        "feature": feature_name,
                        "missing_type": "animation",
                        "target_anim": required_anim,
                        "message": f"Missing required animation track '{required_anim}' for feature: {feature_name}."
                    })
                    return

                user_notifies = [n.get("Name") for n in anim_node.get("notifies", [])]
                for req_notify in required_notifies:
                    if req_notify not in user_notifies:
                        missing.append({
                            "feature": feature_name,
                            "missing_type": "notify",
                            "target_anim": required_anim,
                            "missing_value": req_notify,
                            "message": f"Animation '{required_anim}' is missing the required '{req_notify}' notify. The feature {feature_name} will not function correctly without it."
                        })

            # Work Suitabilities
            new_suits = pal_data.get("WorkSuitabilities", {})
            for suit_key, rules in self.kb.get("WorkSuitabilities", {}).items():
                level = 0
                action_name = rules["action"]
                short_key = suit_key.replace("WorkSuitability_", "")
                
                if pal_data.get(suit_key, 0) > 0:
                    level = pal_data[suit_key]
                    
                if short_key in new_suits:
                    level = new_suits[short_key].get("Level", 0)
                    action_name = new_suits[short_key].get("Animation", action_name)
                elif suit_key in new_suits:
                    level = new_suits[suit_key].get("Level", 0)
                    action_name = new_suits[suit_key].get("Animation", action_name)
                    
                if level > 0:
                    notifies = rules.get("notifies", [])
                    check_anim(f"Work Suitability: {short_key}", action_name, notifies)

            # Partner Weapon Anims
            if coop_weapon.get("Enabled"):
                mode = coop_weapon.get("Mode")
                wp_rules = self.kb.get("CoopWeapons", {}).get(mode)
                if wp_rules:
                    for req_anim in wp_rules.get("anims", []):
                        req_notifies = wp_rules.get("notifies", {}).get(req_anim, [])
                        check_anim(f"Partner Weapon: {mode}", req_anim, req_notifies)

            # Unique Attack Wazas
            active_wazas = [w["WazaID"] for w in pal_data.get("Learnset", []) if w.get("WazaID", "").startswith("Unique_")]
            funnel = features.get("Funnel", pal_data.get("Funnel", {}))
            if funnel.get("Enabled"):
                fw = funnel.get("CustomWazaID", "")
                if fw.startswith("EPalWazaID::Unique_"):
                    active_wazas.append(fw.replace("EPalWazaID::", ""))

            for waza in set(active_wazas):
                waza_rules = self.kb.get("UniqueAttacks", {}).get(waza)
                if waza_rules:
                    for req_anim in waza_rules.get("anims", []):
                        req_notifies = waza_rules.get("notifies", {}).get(req_anim, [])
                        check_anim(f"Unique Attack: {waza}", req_anim, req_notifies)

        return missing