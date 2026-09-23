# utils/blueprint_patcher/feature_manager/weapons.py
"""
====================================================================================================
               CO-OP PARTNER WEAPON COMPONENT SCHEMA & ARCHETYPE REFERENCE
====================================================================================================

OVERVIEW:
---------
Controls combat weapon attachments and partner skill firing modes. In Unreal Engine 5.1,
partner weapons are governed by a CoopParam component (which manages firing state and ammo)
paired with an optional SkeletalMesh component (rendering the held firearm), a SceneComponent
(defining the raycast / muzzle origin), and a Cooperation AIAction class.

SCHEMA SPECIFICATION:
---------------------
1. Method Signature:
   add_coop_weapon(
       mode: str,
       weapon_class_package: str = None,
       weapon_class_name: str = None,
       attach_socket: str = "Socket_Weapon_R",
       skill_magnification: list[float] = None,
       aim_blur_angles: list[float] = None,
       custom_mesh_package: str = None,
       custom_mesh_name: str = None
   ) -> int

2. Weapon Archetypes & Discovered Presets:
   ┌──────────────────────┬───────────────────────────────┬────────────────────────────┬────────────────────────────┐
   │ Mode Key             │ Primary Component Class       │ Attached Mesh              │ AIAction Cooperation Class │
   ├──────────────────────┼───────────────────────────────┼────────────────────────────┼────────────────────────────┤
   │ "AssaultRifle"       │ BP_CoopParam_AssaultRifleMode │ SK_Weapon_AssaultRifle_004 │ BP_AIAction_AssaultRifleMode│
   │ "Shotgun"            │ BP_CoopParam_ShotgunMode      │ SK_Weapon_Shotgun_004      │ BP_AIAction_ShotgunMode    │
   │ "Flamethrower"       │ BP_CoopParam_Weapon           │ Spawned Weapon Actor       │ BP_AIAction_WeaponCall     │
   │ "Launcher"           │ BP_CoopParam_Weapon           │ Spawned Weapon Actor       │ BP_AIAction_WeaponCall     │
   │ "OnHeadSubmachineGun"│ BP_CoopParam_OnHeadShot       │ StaticMeshComponent_Gun    │ BP_AIActionOnHeadShotCall  │
   │ "Minigun" / "Cover"  │ BP_CoopParam_Cover            │ Attached to Gatling Sentry │ Native (Rider Controlled)  │
   │ "ThrowBomb"          │ BP_CoopParam_Weapon           │ Spawned Grenade Actor      │ BP_AIAction_ThrowWeaponCall│
   │ "Katana"             │ BP_CoopParam_Weapon           │ Spawned Melee Actor        │ BP_AIAction_MeleeWeaponCall│
   │ "JumpFrog"           │ BP_CoopParam_JumpFrog         │ None                       │ BP_AIAction_JumpCall       │
   └──────────────────────┴───────────────────────────────┴────────────────────────────┴────────────────────────────┘

3. Tuning Parameters:
   • skill_magnification: Array of floats (Rank 0..10) scaling weapon base damage per rank.
     Example: [0.15, 0.20, 0.25, 0.30, 0.35, 0.40] (Assault Rifle default)
   • aim_blur_angles: Array of floats (Rank 0..5) controlling projectile spread cone in degrees.
     Example: [3.0, 2.5, 1.25, 0.5, 0.0] (0.0 = laser accuracy at max rank)
   • attach_socket: The skeletal bone name to parent the weapon mesh to (default: "Socket_Weapon_R").
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class WeaponManagerMixin:
    """
    Manages Co-op Partner Weapons and weapon attachment components.
    Provides preset configurations for all in-game partner weapon archetypes.
    """

    WEAPON_PRESETS = {
        "AssaultRifle": {
            "param_var": "BP_CoopParam_AssaultRifleMode",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_AssaultRifleMode",
            "param_class": "BP_CoopParam_AssaultRifleMode_C",
            "ray_var": "AssultrifleModeRayStart",
            "mesh_var": "SkeletalMesh",
            "mesh_pkg": "/Game/Pal/Model/Weapon/AssaultRifle/SK_Weapon_AssaultRifle_004",
            "mesh_name": "SK_Weapon_AssaultRifle_004",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_AssaultRifleMode.BP_AIAction_AssaultRifleMode_C"
        },
        "Shotgun": {
            "param_var": "BP_CoopParam_ShotgunMode",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_ShotgunMode",
            "param_class": "BP_CoopParam_ShotgunMode_C",
            "ray_var": "ShotgunModeRayStart",
            "mesh_var": "SkeletalMesh",
            "mesh_pkg": "/Game/Pal/Model/Weapon/Shotgun/SK_Weapon_Shotgun_004",
            "mesh_name": "SK_Weapon_Shotgun_004",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_ShotgunMode.BP_AIAction_ShotgunMode_C"
        },
        "Flamethrower": {
            "param_var": "BP_CoopParam_Weapon",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Weapon",
            "param_class": "BP_CoopParam_Weapon_C",
            "default_weapon_pkg": "/Game/Pal/Blueprint/Weapon/BP_Kitsunebi_Flamethrower",
            "default_weapon_class": "BP_Kitsunebi_Flamethrower_C",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_WeaponCall.BP_AIAction_WeaponCall_C"
        },
        "Launcher": {
            "param_var": "BP_CoopParam_Weapon",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Weapon",
            "param_class": "BP_CoopParam_Weapon_C",
            "default_weapon_pkg": "/Game/Pal/Blueprint/Weapon/BP_PenguinLauncher",
            "default_weapon_class": "BP_PenguinLauncher_C",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_WeaponCall.BP_AIAction_WeaponCall_C"
        },
        "OnHeadSubmachineGun": {
            "param_var": "BP_CoopParam_OnHeadShot",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_OnHeadShot",
            "param_class": "BP_CoopParam_OnHeadShot_C",
            "gun_var": "StaticMeshComponent_Gun",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionOnHeadShotCall.BP_AIActionOnHeadShotCall_C"
        },
        "Minigun": {
            "param_var": "BP_CoopParam_Cover",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Cover",
            "param_class": "BP_CoopParam_Cover_C",
            "needs_pal_shooter": True,
            "action": None
        },
        "Cover": {
            "param_var": "BP_CoopParam_Cover",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Cover",
            "param_class": "BP_CoopParam_Cover_C",
            "needs_pal_shooter": True,
            "action": None
        },
        "ThrowBomb": {
            "param_var": "BP_CoopParam_Weapon",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Weapon",
            "param_class": "BP_CoopParam_Weapon_C",
            "default_weapon_pkg": "/Game/Pal/Blueprint/Weapon/BP_ThrowElecBomb_CoopWeapon",
            "default_weapon_class": "BP_ThrowElecBomb_CoopWeapon_C",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_ThrowWeaponCall.BP_AIAction_ThrowWeaponCall_C"
        },
        "Katana": {
            "param_var": "BP_CoopParam_Weapon",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Weapon",
            "param_class": "BP_CoopParam_Weapon_C",
            "default_weapon_pkg": "/Game/Pal/Blueprint/Weapon/BP_SwordCutlassfish_Katana",
            "default_weapon_class": "BP_SwordCutlassfish_Katana_C",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_MeleeWeaponCall_SwordCutlassfish.BP_AIAction_MeleeWeaponCall_SwordCutlassfish_C"
        },
        "JumpFrog": {
            "param_var": "BP_CoopParam_JumpFrog",
            "param_pkg": "/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_JumpFrog",
            "param_class": "BP_CoopParam_JumpFrog_C",
            "action": "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIAction_JumpCall.BP_AIAction_JumpCall_C"
        }
    }

    def add_coop_weapon(
        self,
        mode: str,
        weapon_class_package: str = None,
        weapon_class_name: str = None,
        attach_socket: str = "Socket_Weapon_R",
        skill_magnification: list[float] = None,
        aim_blur_angles: list[float] = None,
        custom_mesh_package: str = None,
        custom_mesh_name: str = None
    ) -> int:
        """
        Instantiates a Co-op Partner Weapon onto the Pal according to standard presets.
        Injects weapon components, raystart scene components, weapon meshes, and binds AIActionMap.
        """
        preset = self.WEAPON_PRESETS.get(mode)
        if not preset:
            raise ValueError(f"Unknown weapon mode: '{mode}'. Available modes: {list(self.WEAPON_PRESETS.keys())}")

        param_var = preset["param_var"]
        param_pkg = preset["param_pkg"]
        param_class = preset["param_class"]
        template_props = []

        # 1. WeaponClass configuration for actor-spawning weapons
        if "default_weapon_pkg" in preset or weapon_class_package:
            wp_pkg = weapon_class_package or preset.get("default_weapon_pkg")
            wp_cls = weapon_class_name or preset.get("default_weapon_class")
            wp_class_idx = self.ensure_import_chain(wp_pkg, wp_cls)

            template_props.append({
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": "WeaponClass",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": wp_class_idx
            })

        # 2. Damage Magnification Array override
        if skill_magnification:
            float_nodes = [
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                    "Name": str(i),
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": float(v)
                }
                for i, v in enumerate(skill_magnification)
            ]
            template_props.append({
                "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                "ArrayType": "FloatProperty",
                "Name": "PartnerSkillMagnification",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": float_nodes
            })

        # 3. Accuracy Blur Angles Array override
        if aim_blur_angles:
            blur_nodes = [
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                    "Name": str(i),
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": float(v)
                }
                for i, v in enumerate(aim_blur_angles)
            ]
            template_props.append({
                "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                "ArrayType": "FloatProperty",
                "Name": "AimBlurAngles",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": blur_nodes
            })

        # Inject main CoopParam component
        node_idx = self.add_component(
            var_name=param_var,
            comp_class_package=param_pkg,
            comp_class_name=param_class,
            template_properties=template_props
        )

        # Inject RayStart component if needed
        if "ray_var" in preset:
            self.add_component(
                var_name=preset["ray_var"],
                comp_class_package="/Script/Engine",
                comp_class_name="SceneComponent",
                attach_to_name="CharacterMesh0",
                parent_var_name="CharacterMesh0",
                b_is_parent_native=True
            )

        # Inject attached weapon SkeletalMeshComponent if needed
        if "mesh_var" in preset or custom_mesh_package:
            mesh_pkg = custom_mesh_package or preset.get("mesh_pkg")
            mesh_name = custom_mesh_name or preset.get("mesh_name")
            mesh_class_idx = self.ensure_import_chain(mesh_pkg, mesh_name, "SkeletalMesh")
            mesh_props = [
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": "SkeletalMesh",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": mesh_class_idx
                }
            ]
            self.add_component(
                var_name=preset.get("mesh_var", "SkeletalMesh"),
                comp_class_package="/Script/Engine",
                comp_class_name="SkeletalMeshComponent",
                template_properties=mesh_props,
                attach_to_name=attach_socket,
                parent_var_name="CharacterMesh0",
                b_is_parent_native=True
            )

        # Inject on-head gun static mesh component if needed
        if "gun_var" in preset:
            self.add_component(
                var_name=preset["gun_var"],
                comp_class_package="/Script/Engine",
                comp_class_name="StaticMeshComponent",
                attach_to_name=attach_socket,
                parent_var_name="CharacterMesh0",
                b_is_parent_native=True
            )

        # Inject PalShooterComponent if needed
        if preset.get("needs_pal_shooter"):
            self.add_component(
                var_name="PalShooter",
                comp_class_package="/Script/Pal",
                comp_class_name="PalShooterComponent"
            )

        # Bind Cooperation AI Action
        if preset.get("action"):
            self.set_ai_action("EPalAIActionType::Cooperation", preset["action"])

        sync_namemap(self.data)
        return node_idx