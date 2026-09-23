# utils/blueprint_patcher/feature_manager/shield.py
"""
====================================================================================================
                  DEFENSIVE SHIELD COMPONENT SCHEMA & REFERENCE
====================================================================================================

OVERVIEW:
---------
Instantiates energy shields (Lamball, SaintCentaur, WhiteShieldDragon) that absorb projectile
and melee damage in a spherical zone. A SphereComponent defines the physical collision barrier,
while BP_CoopParam_Sheild manages activation timers, durability, and AI cooperation binding.

SCHEMA SPECIFICATION:
---------------------
1. Method Signature:
   add_shield(
       radius: float = 90.0,
       attach_socket: str = "lowerarm_l",
       relative_location: dict = None,
       action_class_path: str = "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionShieldCall.BP_AIActionShieldCall_C"
   ) -> int

2. Component & Variable Mapping:
   • Collision Sphere:  SphereComponent ('Shield', radius in units, tag: ['Shield'])
   • Coop Parameter:    BP_CoopParam_Shield_C (Variable: 'BP_CoopParam_Sheild')
   • AIAction Binding:  AIActionMap[EPalAIActionType::Cooperation] -> BP_AIActionShieldCall_C

3. Spatial Coordinates:
   • relative_location: {"X": float, "Y": float, "Z": float} (e.g. {"X": 0.0, "Y": 0.0, "Z": 62.5})
   • attach_socket: Target bone ("lowerarm_l", "pelvis", "spine_01").
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class ShieldManagerMixin:
    """
    Manages defensive shield components (Lamball / SaintCentaur / WhiteShieldDragon).
    """

    def add_shield(
        self,
        radius: float = 90.0,
        attach_socket: str = "lowerarm_l",
        relative_location: dict = None,
        action_class_path: str = "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionShieldCall.BP_AIActionShieldCall_C"
    ) -> int:
        """
        Injects a defensive energy shield onto the Pal:
        1. Adds SphereComponent 'Shield' with SphereRadius, location offset, and tag ['Shield'].
        2. Adds 'BP_CoopParam_Sheild' component pointing to class BP_CoopParam_Shield_C.
        3. Sets Cooperation AIAction to BP_AIActionShieldCall_C.
        """
        shield_props = [
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                "Name": "SphereRadius",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": float(radius)
            },
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                "ArrayType": "NameProperty",
                "Name": "ComponentTags",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                        "Name": "0",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": "Shield"
                    }
                ]
            }
        ]

        if relative_location:
            shield_props.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "Vector",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": "RelativeLocation",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                        "Name": "RelativeLocation",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": {
                            "$type": "UAssetAPI.UnrealTypes.FVector, UAssetAPI",
                            "X": float(relative_location.get("X", 0.0)),
                            "Y": float(relative_location.get("Y", 0.0)),
                            "Z": float(relative_location.get("Z", 62.5))
                        }
                    }
                ]
            })

        # 1. SphereComponent
        node_idx = self.add_component(
            var_name="Shield",
            comp_class_package="/Script/Engine",
            comp_class_name="SphereComponent",
            template_properties=shield_props,
            attach_to_name=attach_socket,
            parent_var_name="CharacterMesh0",
            b_is_parent_native=True
        )

        # 2. CoopParam (Package and Class use 'Shield', variable name uses 'Sheild')
        coop_props = [
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                "Name": "AttachSocketName",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": attach_socket
            }
        ]

        self.add_component(
            var_name="BP_CoopParam_Sheild",
            comp_class_package="/Game/Pal/Blueprint/Character/Monster/CoopParam/BP_CoopParam_Shield",
            comp_class_name="BP_CoopParam_Shield_C",
            template_properties=coop_props
        )

        # 3. Action
        self.set_ai_action("EPalAIActionType::Cooperation", action_class_path)

        sync_namemap(self.data)
        return node_idx

    def remove_shield(self):
        """Removes shield components."""
        self.remove_component("Shield")
        self.remove_component("BP_CoopParam_Sheild")
        sync_namemap(self.data)
        
    def has_shield(self) -> bool:
        """Returns True if the Pal has a Shield component."""
        return self.has_component("Shield")