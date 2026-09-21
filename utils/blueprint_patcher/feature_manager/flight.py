# utils/blueprint_patcher/feature_manager/flight.py
"""
====================================================================================================
                  FLIGHT & ALTITUDE CONTROLLER SCHEMA & REFERENCE
====================================================================================================

OVERVIEW:
---------
Controls hovering, floating height, and water plane elevation adjustments.
In Unreal Engine 5.1, airborne and levitating Pals (JetDragon, Suzaku, CuteButterfly, DreamDemon)
rely on PalFlyMeshHeightCtrlComponent.

SCHEMA SPECIFICATION:
---------------------
1. Method Signature:
   add_fly_height_controller(var_name: str = "PalFlyMeshHeightCtrl") -> int

2. Component Class:
   • Package:    /Script/Pal
   • Class Name: PalFlyMeshHeightCtrlComponent
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class FlightManagerMixin:
    """
    Manages floating, altitude, and aerial movement controllers.
    """

    def add_fly_height_controller(self, var_name: str = "PalFlyMeshHeightCtrl") -> int:
        """
        Injects PalFlyMeshHeightCtrlComponent to control hovering, vertical flight,
        and water navigation height adjustments.
        """
        node_idx = self.add_component(
            var_name=var_name,
            comp_class_package="/Script/Pal",
            comp_class_name="PalFlyMeshHeightCtrlComponent"
        )
        sync_namemap(self.data)
        return node_idx

    def has_fly_height_controller(self, var_name: str = "PalFlyMeshHeightCtrl") -> bool:
        """Returns True if PalFlyMeshHeightCtrl is actively registered."""
        return self.has_component(var_name)

    def remove_fly_height_controller(self, var_name: str = "PalFlyMeshHeightCtrl"):
        """Removes PalFlyMeshHeightCtrl."""
        self.remove_component(var_name)
        sync_namemap(self.data)