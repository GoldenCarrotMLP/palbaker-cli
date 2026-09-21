# utils/blueprint_patcher/feature_manager/physics.py
"""
====================================================================================================
                  LOCOMOTION LEANING & PHYSICS CALIBRATION SCHEMA
====================================================================================================

OVERVIEW:
---------
Controls the dynamic procedural banking/tilting of a Pal's mesh when navigating corners.
Custom models often clip into the floor because the default LeanParameter_Walk intensity
is tuned for the original mesh proportions.

SCHEMA SPECIFICATION:
---------------------
1. Target Component: StaticCharacterParameterComponent
2. Target Properties: LeanParameter_Walk, LeanParameter_Fly, LeanParameter_Swim
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class PhysicsManagerMixin:
    """
    Manages procedural physics calibrations such as locomotion leaning and banking limits.
    """

    def set_locomotion_leaning(
        self,
        mode: str = "Walk",
        pitch_intensity: float = 0.0,
        pitch_min: float = -30.0,
        pitch_max: float = 30.0,
        roll_intensity: float = 0.0,
        roll_min: float = -30.0,
        roll_max: float = 30.0
    ):
        """
        Calibrates or disables procedural banking during movement to prevent custom 
        meshes from clipping into the floor.
        mode: "Walk", "Fly", or "Swim"
        """
        valid_modes = ["Walk", "Fly", "Swim"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid leaning mode '{mode}'. Must be one of {valid_modes}.")

        comp = self.find_static_char_param_export()
        if not comp:
            return

        comp_data = comp.get("Data")
        if not isinstance(comp_data, list):
            comp_data = []
            comp["Data"] = comp_data

        prop_name = f"LeanParameter_{mode}"
        lean_prop = next((p for p in comp_data if isinstance(p, dict) and p.get("Name") == prop_name), None)

        axis_data = []
        
        # Pitch (Y axis in Palworld's procedural IK leaning)
        axis_data.append(self._build_lean_axis("Y", pitch_intensity, pitch_min, pitch_max))
        # Roll (Z axis in Palworld's procedural IK leaning)
        axis_data.append(self._build_lean_axis("Z", roll_intensity, roll_min, roll_max))

        if lean_prop:
            lean_prop["Value"] = axis_data
        else:
            comp_data.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "PalStaticCharacterInfo_Lean",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": prop_name,
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": axis_data
            })

        sync_namemap(self.data)

    def _build_lean_axis(self, axis_name: str, intensity: float, rot_min: float, rot_max: float) -> dict:
        return {
            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
            "StructType": "PalStaticCharacterInfo_LeanParameter",
            "SerializeNone": True,
            "StructGUID": "{00000000-0000-0000-0000-000000000000}",
            "SerializationControl": "NoExtension",
            "Operation": "None",
            "Name": axis_name,
            "ArrayIndex": 0,
            "PropertyGuid": None,
            "IsZero": False,
            "PropertyTagFlags": "None",
            "PropertyTypeName": None,
            "PropertyTagExtensions": "NoExtension",
            "Value": [
                {
                    "$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                    "Name": "Intensity",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": float(intensity)
                },
                {
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "StructType": "Vector2D",
                    "SerializeNone": True,
                    "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                    "SerializationControl": "NoExtension",
                    "Operation": "None",
                    "Name": "RotLimit",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Structs.Vector2DPropertyData, UAssetAPI",
                            "Name": "RotLimit",
                            "ArrayIndex": 0,
                            "PropertyGuid": None,
                            "IsZero": False,
                            "PropertyTagFlags": "None",
                            "PropertyTypeName": None,
                            "PropertyTagExtensions": "NoExtension",
                            "Value": {
                                "$type": "UAssetAPI.UnrealTypes.FVector2D, UAssetAPI",
                                "X": float(rot_min),
                                "Y": float(rot_max)
                            }
                        }
                    ]
                }
            ]
        }