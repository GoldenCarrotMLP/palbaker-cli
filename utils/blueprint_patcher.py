# utils/blueprint_patcher.py

"""
================================================================================
          PALBAKER BLUEPRINT PATCHER ENGINE - STRICT PRESERVATION GUIDE
================================================================================
CRITICAL CONSTRAINTS:

1. ANIMATION BLUEPRINT INHERITANCE (THE "ABP_WEASELDRAGON" CONSTRAINT):
   Custom standalone Pals must inherit and utilize their parent template's 
   animations and skeletons (e.g., ABP_WeaselDragon_C). Naively replacing 
   "BP_WeaselDragon" inside class paths will corrupt "ABP_WeaselDragon_C" into 
   "ABP_Furret_C". Since "ABP_Furret_C" does not exist, the Pal will spawn in 
   a static T-Pose/A-Pose or freeze.
   
   - DO NOT perform blind global string replacements of the template name.
   - ALWAYS use a negative lookbehind (?<!A) when targeting class strings:
     e.g., re.sub(rf"(?<!A)BP_{template_id}", ...)
     This guarantees that "ABP_WeaselDragon" remains completely untouched.

2. OBJECTNAME & OBJECTPATH PAIRING RULE:
   Unreal Engine's serialization framework mandates that both the ObjectPath 
   and the ObjectName reference structures are updated in tandem:
   - ObjectPath: "/Game/Pal/Model/Character/Monster/Furret/SK_Furret"
   - ObjectName: "SkeletalMesh'SK_Furret'" (NOT "SkeletalMesh'SK_WeaselDragon'")
   Failing to replace the ObjectName alongside the ObjectPath results in 
   a null-mesh binding, making the Pal completely invisible in-world.

3. DOUBLE-QUOTED RAW REFERENCE BINDINGS:
   UAssetGUI imports include raw double-quoted strings in the Imports table 
   (e.g., '"SK_WeaselDragon"'). These must be explicitly searched and replaced 
   with double-quoted targets ('"SK_Furret"') to allow the serializer to 
   bind the newly cooked uassets at runtime.
================================================================================
"""

# utils/blueprint_patcher.py
from utils.blueprint import patch_actor_blueprint