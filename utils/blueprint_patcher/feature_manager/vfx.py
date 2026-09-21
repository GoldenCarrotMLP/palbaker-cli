# utils/blueprint_patcher/feature_manager/vfx.py
"""
====================================================================================================
                  NIAGARA PARTICLE VFX ATTACHMENT SCHEMA & REFERENCE
====================================================================================================

OVERVIEW:
---------
Allows the permanent attachment of looping or persistent Niagara particle systems
to specific skeletal bone sockets on the Pal (e.g., flaming eyes, dark auras, dripping water).

SCHEMA SPECIFICATION:
---------------------
1. Method Signature:
   add_niagara_particle(
       var_name: str,
       system_package: str,
       system_name: str,
       attach_socket: str = "root"
   ) -> int
====================================================================================================
"""

from utils.uasset_helper import sync_namemap

class VFXManagerMixin:
    """
    Manages the instantiation and attachment of real-time Niagara particle systems.
    """

    def add_niagara_particle(
        self,
        var_name: str,
        system_package: str,
        system_name: str,
        attach_socket: str = "root"
    ) -> int:
        """
        Injects a NiagaraComponent onto the Pal and binds it to a specific bone socket.
        """
        # Ensure the NiagaraSystem is imported
        system_idx = self.ensure_import_chain(system_package, system_name, "NiagaraSystem")

        template_props = [
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": "Asset",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": system_idx
            }
        ]

        node_idx = self.add_component(
            var_name=var_name,
            comp_class_package="/Script/Niagara",
            comp_class_name="NiagaraComponent",
            template_properties=template_props,
            attach_to_name=attach_socket,
            parent_var_name="CharacterMesh0",
            b_is_parent_native=True
        )

        sync_namemap(self.data)
        return node_idx

    def remove_niagara_particle(self, var_name: str):
        """Removes a previously injected Niagara particle component."""
        self.remove_component(var_name)