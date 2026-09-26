# utils/blueprint_patcher/feature_manager/saddle.py
"""
====================================================================================================
                  SADDLE & RIDING ARCHETYPE SCHEMA & PROPERTY REFERENCE
====================================================================================================

OVERVIEW:
---------
Controls mounting, player rider socket parenting, trample collisions, and mounted shooting.
In Palworld, mountable Pals possess a RideMarker component (defining rider seating rules)
and optionally PalSpeedCollisionComponent (for sprint ramming) and PalShooterComponent
(allowing the player to fire handheld weapons while steering).

SCHEMA SPECIFICATION:
---------------------
1. Method Signature:
   add_saddle(
       marker_type: str = "Saddle",
       ride_position_type: str = None,
       attach_socket: str = "PlayerRideMarker",
       relative_rotation: dict = None,
       relative_location: dict = None,
       ride_action_class_path: str = "...",
       with_speed_collision: bool = False
   ) -> int

2. Ride Marker Archetypes:
   • "Saddle":      BP_PalRideMarkerSaddle_C (Standard saddle for medium quadrupeds/bipeds).
   • "BiggerHorse": BP_PalRideMarkerBiggerHorse_C (Large mount saddle with higher camera offset).
   • "Sit":         BP_PalRideMarkerSit_C (Upright sitting pose used by ElecPanda, KingAlpaca, etc.).

3. Ride Posture Enums (EPalRidePositionType):
   • "HorseRide":       Default straddle pose.
   • "BiggerHorseRide": Wider straddle stance for massive mounts.
   • "Sit":             Legs-forward seated stance.

4. Spatial Coordinates:
   • relative_rotation: {"Pitch": float, "Yaw": float, "Roll": float} (Default: 90 deg pitch offset)
   • relative_location: {"X": float, "Y": float, "Z": float}
   • attach_socket: Target bone ("PlayerRideMarker", "spine_01", "spine_02", "pelvis", "neck_01").
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class SaddleManagerMixin:
    """
    Manages mountable Pal mechanics, saddle components (BP_PalRideMarkerSaddle,
    BP_PalRideMarkerBiggerHorse, BP_PalRideMarkerSit), speed collisions, and mounted shooting.
    """

    RIDE_MARKER_PRESETS = {
        "Saddle": {
            "pkg": "/Game/Pal/Blueprint/Component/RideMarker/BP_PalRideMarkerSaddle",
            "class_name": "BP_PalRideMarkerSaddle_C",
            "var_name": "BP_PalRideMarkerSaddle",
            "default_position": "HorseRide"
        },
        "BiggerHorse": {
            "pkg": "/Game/Pal/Blueprint/Component/RideMarker/BP_PalRideMarkerBiggerHorse",
            "class_name": "BP_PalRideMarkerBiggerHorse_C",
            "var_name": "BP_PalRideMarkerBiggerHorse",
            "default_position": "BiggerHorseRide"
        },
        "Sit": {
            "pkg": "/Game/Pal/Blueprint/Component/RideMarker/BP_PalRideMarkerSit",
            "class_name": "BP_PalRideMarkerSit_C",
            "var_name": "BP_PalRideMarkerSit",
            "default_position": "HorseRide"
        }
    }

    def add_saddle(
        self,
        marker_type: str = "Saddle",
        ride_position_type: str = None,
        attach_socket: str = "PlayerRideMarker",
        relative_rotation: dict = None,
        relative_location: dict = None,
        ride_action_class_path: str = "/Game/Pal/Blueprint/Controller/AIAction/Coop/BP_AIActionRideCall.BP_AIActionRideCall_C",
        with_speed_collision: bool = False
    ) -> int:
        """
        Gives any Pal the ability to be ridden.
        Supports presets: "Saddle", "BiggerHorse", and "Sit".
        Optionally adds PalSpeedCollisionComponent for heavy trample damage.
        """
        preset = self.RIDE_MARKER_PRESETS.get(marker_type, self.RIDE_MARKER_PRESETS["Saddle"])
        var_name = preset["var_name"]
        comp_pkg = preset["pkg"]
        comp_class = preset["class_name"]

        # Clean up any conflicting ride marker components if switching types
        for other_preset in self.RIDE_MARKER_PRESETS.values():
            if other_preset["var_name"] != var_name and self.has_component(other_preset["var_name"]):
                self.remove_component(other_preset["var_name"])

        template_props = []

        # --- CRITICAL SAFETY BOUNDARY ---
        # Injecting serialized properties into a dynamically added template shifts the byte alignment 
        # of the unversioned CDO, causing D3D11 'CreateBuffer E_INVALIDARG' crashes on CharacterMesh0.
        # We only apply these relative offsets if the component already exists natively (e.g. Boar).
        if self.has_component(var_name):
            if relative_location:
                template_props.append({
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
                                "Z": float(relative_location.get("Z", 10.0))
                            }
                        }
                    ]
                })

            if relative_rotation:
                template_props.append({
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "StructType": "Rotator",
                    "SerializeNone": True,
                    "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                    "SerializationControl": "NoExtension",
                    "Operation": "None",
                    "Name": "RelativeRotation",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Structs.RotatorPropertyData, UAssetAPI",
                            "Name": "RelativeRotation",
                            "ArrayIndex": 0,
                            "PropertyGuid": None,
                            "IsZero": False,
                            "PropertyTagFlags": "None",
                            "PropertyTypeName": None,
                            "PropertyTagExtensions": "NoExtension",
                            "Value": {
                                "$type": "UAssetAPI.UnrealTypes.FRotator, UAssetAPI",
                                "Pitch": float(relative_rotation.get("Pitch", 0.0)),
                                "Yaw": float(relative_rotation.get("Yaw", 0.0)),
                                "Roll": float(relative_rotation.get("Roll", 0.0))
                            }
                        }
                    ]
                })

        node_idx = self.add_component(
            var_name=var_name,
            comp_class_package=comp_pkg,
            comp_class_name=comp_class,
            template_properties=template_props,
            attach_to_name=attach_socket,
            parent_var_name="CharacterMesh0",
            b_is_parent_native=True
        )

        self.set_ai_action("EPalAIActionType::Cooperation", ride_action_class_path)

        # Fallback: If template has no RidingMove BlendSpace (e.g. Kitsunebi), map it to GeneralMove
        comp = self.find_static_char_param_export()
        if comp and isinstance(comp.get("Data"), list):
            bs_map = next((p for p in comp["Data"] if isinstance(p, dict) and p.get("Name") == "GeneralBlendSpaceMap"), None)
            if bs_map and isinstance(bs_map.get("Value"), list):
                has_riding_move = any(
                    isinstance(e, list) and len(e) >= 1 and isinstance(e[0], dict) and "RidingMove" in str(e[0].get("Value", ""))
                    for e in bs_map["Value"]
                )
                if not has_riding_move:
                    gen_move_entry = next(
                        (e for e in bs_map["Value"] if isinstance(e, list) and len(e) >= 2 and isinstance(e[0], dict) and "GeneralMove" in str(e[0].get("Value", ""))),
                        None
                    )
                    if gen_move_entry and isinstance(gen_move_entry[1], dict):
                        bs_map["Value"].append([
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI",
                                "EnumType": None,
                                "InnerType": None,
                                "Name": "GeneralBlendSpaceMap",
                                "ArrayIndex": 0,
                                "PropertyGuid": None,
                                "IsZero": False,
                                "PropertyTagFlags": "None",
                                "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension",
                                "Value": "EPalGeneralBlendSpaceType::RidingMove"
                            },
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                                "Name": "GeneralBlendSpaceMap",
                                "ArrayIndex": 0,
                                "PropertyGuid": None,
                                "IsZero": False,
                                "PropertyTagFlags": "None",
                                "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension",
                                "Value": gen_move_entry[1].get("Value")
                            }
                        ])

        if with_speed_collision:
            self.add_speed_collision()

        sync_namemap(self.data)
        return node_idx

    def remove_saddle(self):
        """Removes any ride marker component."""
        for preset in self.RIDE_MARKER_PRESETS.values():
            if self.has_component(preset["var_name"]):
                self.remove_component(preset["var_name"])
        sync_namemap(self.data)

    def has_saddle(self) -> bool:
        """Returns True if the Pal has any saddle or ride marker component attached."""
        return any(self.has_component(p["var_name"]) for p in self.RIDE_MARKER_PRESETS.values())

    def add_speed_collision(self, var_name: str = "PalSpeedCollision") -> int:
        """Injects PalSpeedCollisionComponent for mounted dash/trample damage."""
        template_props = []

        if self.has_component(var_name):
            template_props.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "Vector",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": "RelativeScale3D",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": [
                    {
                        "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                        "Name": "RelativeScale3D",
                        "ArrayIndex": 0,
                        "PropertyGuid": None,
                        "IsZero": False,
                        "PropertyTagFlags": "None",
                        "PropertyTypeName": None,
                        "PropertyTagExtensions": "NoExtension",
                        "Value": {
                            "$type": "UAssetAPI.UnrealTypes.FVector, UAssetAPI",
                            "X": 2.5,
                            "Y": 2.5,
                            "Z": 2.0
                        }
                    }
                ]
            })

        return self.add_component(
            var_name=var_name,
            comp_class_package="/Script/Pal",
            comp_class_name="PalSpeedCollisionComponent",
            template_properties=template_props,
            attach_to_name="root",
            parent_var_name="CharacterMesh0",
            b_is_parent_native=True
        )

    def has_speed_collision(self, var_name: str = "PalSpeedCollision") -> bool:
        """Returns True if PalSpeedCollision is attached."""
        return self.has_component(var_name)

    def remove_speed_collision(self, var_name: str = "PalSpeedCollision"):
        """Removes PalSpeedCollision."""
        self.remove_component(var_name)

    def add_mounted_shooter(self, var_name: str = "PalShooter") -> int:
        """Injects PalShooterComponent allowing the rider to shoot weapons while mounted."""
        return self.add_component(
            var_name=var_name,
            comp_class_package="/Script/Pal",
            comp_class_name="PalShooterComponent"
        )

    def has_mounted_shooter(self, var_name: str = "PalShooter") -> bool:
        """Returns True if PalShooter is attached."""
        return self.has_component(var_name)

    def remove_mounted_shooter(self, var_name: str = "PalShooter"):
        """Removes PalShooter."""
        self.remove_component(var_name)