# utils/blueprint_patcher/feature_manager/props.py
"""
====================================================================================================
                  VISUAL LIGHTS & ATTACHED PROPS SCHEMA & REFERENCE
====================================================================================================

OVERVIEW:
---------
Controls attached cosmetic meshes (such as GrimGirl's machete, FlowerDinosaur's bouquet, or
QueenBee's staff) and bioluminescent night lights (BP_PalTimerPointLightComponent).

SCHEMA SPECIFICATION:
---------------------
1. Method Signatures:
   • add_timer_point_light(var_name: str = "BP_PalTimerPointLightComponent") -> int
   • add_hand_prop(
         var_name: str = "Weapon",
         attach_socket: str = "Socket_Weapon_R",
         mesh_class_package: str | None = None,
         mesh_class_name: str | None = None,
         is_skeletal: bool = True
     ) -> int

2. Component Specifications:
   • Point Light Timer: BP_PalTimerPointLightComponent_C (Turns off during daytime, activates at dusk).
   • Hand Prop Mesh:    SkeletalMeshComponent or StaticMeshComponent attached to hand/weapon sockets.
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class PropsManagerMixin:
    """
    Manages in-hand weapon props, held tools, and bioluminescent point light timers.
    """

    def add_timer_point_light(self, var_name: str = "BP_PalTimerPointLightComponent") -> int:
        """
        Injects BP_PalTimerPointLightComponent for nocturnal glowing Pals.
        """
        node_idx = self.add_component(
            var_name=var_name,
            comp_class_package="/Game/Pal/Blueprint/Component/PointLight/BP_PalTimerPointLightComponent",
            comp_class_name="BP_PalTimerPointLightComponent_C"
        )
        sync_namemap(self.data)
        return node_idx

    def has_timer_point_light(self, var_name: str = "BP_PalTimerPointLightComponent") -> bool:
        """Returns True if the Pal has a timer point light component."""
        return self.has_component(var_name)

    def remove_timer_point_light(self, var_name: str = "BP_PalTimerPointLightComponent"):
        """Removes the timer point light component."""
        self.remove_component(var_name)
        sync_namemap(self.data)

    def add_hand_prop(
        self,
        var_name: str = "Weapon",
        attach_socket: str = "Socket_Weapon_R",
        mesh_class_package: str | None = None,
        mesh_class_name: str | None = None,
        is_skeletal: bool = True
    ) -> int:
        """
        Injects a held tool or weapon prop (SkeletalMeshComponent or StaticMeshComponent)
        attached to the character's hand socket (seen on QueenBee, SoldierBee, GrimGirl, FlowerDinosaur).
        """
        comp_class_name = "SkeletalMeshComponent" if is_skeletal else "StaticMeshComponent"
        template_props = []

        if mesh_class_package and mesh_class_name:
            mesh_idx = self.ensure_import_chain(
                mesh_class_package,
                mesh_class_name,
                "SkeletalMesh" if is_skeletal else "StaticMesh"
            )
            template_props.append({
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": "SkeletalMesh" if is_skeletal else "StaticMesh",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": mesh_idx
            })

        node_idx = self.add_component(
            var_name=var_name,
            comp_class_package="/Script/Engine",
            comp_class_name=comp_class_name,
            template_properties=template_props,
            attach_to_name=attach_socket,
            parent_var_name="CharacterMesh0",
            b_is_parent_native=True
        )

        sync_namemap(self.data)
        return node_idx

    def has_hand_prop(self, var_name: str = "Weapon") -> bool:
        """Returns True if the Pal has a hand prop component."""
        return self.has_component(var_name)

    def remove_hand_prop(self, var_name: str = "Weapon"):
        """Removes the hand prop component."""
        self.remove_component(var_name)
        sync_namemap(self.data)