# utils/uasset_safety_validator.py
"""
UAsset Safety & Integrity Validator
-----------------------------------
Analyzes UAssetAPI JSON ASTs to detect structural anomalies that cause
Unreal Engine 5.1 fatal errors (such as Array.cpp buffer overflows during
EventDrivenLoader deserialization).

Checks enforced:
1. HasUnversionedProperties == False (Tagged Serialization Enforcement)
2. ShapeComponents lack BodyInstance/ResponseArray (Bitmask Misalignment Prevention)
3. Enum Properties in AnimNotifies use BytePropertyData with IsZero=False
4. OuterIndex/Dependency Graph circular reference detection
"""

import os
import json

class UAssetSafetyValidator:
    def __init__(self, json_payload: dict | str):
        if isinstance(json_payload, str):
            if os.path.exists(json_payload):
                with open(json_payload, "r", encoding="utf-8-sig") as f:
                    self.data = json.load(f)
            else:
                self.data = json.loads(json_payload)
        else:
            self.data = json_payload

        self.errors = []
        self.warnings = []

    def validate(self) -> dict:
        self.errors.clear()
        self.warnings.clear()

        if not self.data or "Exports" not in self.data:
            self.errors.append("[FATAL] Malformed AST: Missing 'Exports' array.")
            return self._generate_report()

        self._check_unversioned_properties()
        self._check_shape_components()
        self._check_notify_enums()
        self._check_dependency_graph()

        return self._generate_report()

    def _generate_report(self) -> dict:
        return {
            "is_safe": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings
        }

    def _check_unversioned_properties(self):
        """
        Rule 1: Unversioned Serialization Leak
        If HasUnversionedProperties is true, any injected properties will break the FUnversionedHeader
        bitmask, causing the reader to drift into the compressed animation payload.
        """
        has_unv = self.data.get("HasUnversionedProperties", False)
        flags = self.data.get("PackageFlags", "")

        if has_unv or "PKG_UnversionedProperties" in flags:
            self.errors.append(
                "[FATAL] Unversioned Serialization is ENABLED. "
                "Injected sub-objects or notifies will desynchronize the stream, "
                "causing TArray::ResizeTo buffer overflow crashes."
            )

    def _check_shape_components(self):
        """
        Rule 2: Actor-Level Components in Sub-Objects
        Sphere/Capsule components attached to PalAnimNotifyState must only contain geometry 
        parameters (SphereRadius, CapsuleHalfHeight). If they contain BodyInstance or 
        CollisionProfileName, the bitstream will misalign because FBodyInstance collision 
        responses are packed bitfields in UE 5.1, not arrays of serialized structs.
        """
        banned_props = {"BodyInstance", "ResponseArray", "CollisionProfileName", "CollisionResponses"}

        for exp in self.data.get("Exports", []):
            obj_name = exp.get("ObjectName", "")
            
            # Is this a sub-object shape component?
            if any(shape in obj_name for shape in ["CapsuleComponent", "SphereComponent", "BoxComponent"]):
                for prop in exp.get("Data", []):
                    prop_name = prop.get("Name", "")
                    if prop_name in banned_props:
                        self.errors.append(
                            f"[FATAL] Component '{obj_name}' contains banned property '{prop_name}'. "
                            f"This will corrupt the FBodyInstance C++ memory layout during async loading."
                        )

    def _check_notify_enums(self):
        """
        Rule 3: Enum Stream Alignment
        In UE 5.1 AnimNotifies, certain enumerators MUST be strictly formatted as BytePropertyData.
        If IsZero=True is used in an unversioned context, the byte is omitted from the stream,
        causing a 1-byte drift for all subsequent properties.
        """
        target_enums = {"LinkMethod", "CachedLinkMethod", "MontageTickType", "NotifyFilterType"}

        for exp in self.data.get("Exports", []):
            if exp.get("Type") in ["AnimSequence", "AnimMontage"] or exp.get("ObjectName", "").startswith(("AS_", "AM_")):
                for prop in exp.get("Data", []):
                    if prop.get("Name") == "Notifies" and isinstance(prop.get("Value"), list):
                        for notify in prop["Value"]:
                            for p in notify.get("Value", []):
                                p_name = p.get("Name", "")
                                if p_name in target_enums:
                                    p_type = p.get("$type", "")
                                    if "BytePropertyData" not in p_type:
                                        self.warnings.append(
                                            f"[WARNING] Notify Enum '{p_name}' is a '{p_type.split('.')[2]}' "
                                            f"instead of 'BytePropertyData'. This may cause serialization drift."
                                        )
                                    if p.get("IsZero", False):
                                        self.warnings.append(
                                            f"[WARNING] Notify Enum '{p_name}' has IsZero=True. "
                                            f"This omits the byte from the unversioned stream, misaligning adjacent properties."
                                        )

    def _check_dependency_graph(self):
        """
        Rule 4: Circular Dependencies & Orphaned Sub-Objects
        If a sub-object's OuterIndex does not map correctly, or it depends on itself,
        the AsyncLoadingThread will hang or crash during CreateBeforeCreateDependencies.
        """
        exports = self.data.get("Exports", [])
        for i, exp in enumerate(exports):
            exp_idx = i + 1
            obj_name = exp.get("ObjectName", "")
            
            cbcd = exp.get("CreateBeforeCreateDependencies", [])
            if exp_idx in cbcd:
                self.errors.append(
                    f"[FATAL] Export '{obj_name}' (Index {exp_idx}) has a circular dependency on itself."
                )

            outer_idx = exp.get("OuterIndex", 0)
            # If it's a component belonging to a notify state, ensure the outer index points to a valid local export
            if "Component" in obj_name or "Filter" in obj_name:
                if outer_idx <= 0 or outer_idx > len(exports):
                    self.errors.append(
                        f"[FATAL] Sub-object '{obj_name}' has an invalid OuterIndex ({outer_idx}). "
                        f"It must point to a valid parent export."
                    )