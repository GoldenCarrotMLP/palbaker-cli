# scrape_all_anim_enums.py
import os
import sys
import json
import re
from collections import defaultdict

# =============================================================================
# HARDCODED TARGET DIRECTORY
# =============================================================================
BP_ROOT_DIR = r"H:\SteamLibrary\steamapps\common\Palworld\Output\Exports\Pal\Content\Pal\Blueprint\Character\Monster\PalActorBP"

# Output files
ENUM_MAP_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enum_to_anims.json")
TS_OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "animation-enums.ts")
PY_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deps", "anim_mapping_cache.json")
# =============================================================================

def clean_asset_to_anim_name(asset_raw: str) -> str:
    """
    Strips the Pal name entirely from any Montage, Sequence, or BlendSpace.
    Examples:
      AM_Anubis_Damage              -> Damage
      AM_GrimGirl_FarSkill_Start    -> FarSkill_Start
      AS_Kitsunebi_JumpLoop         -> JumpLoop
      BS_Move_Anubis                -> Move
      BS_Swim_AmaterasuWolf         -> Swim
      BS_Move_AmaterasuWolf_Riding  -> Move_Riding
      BP_Action_Unique_Anubis_Tackle -> Tackle
    """
    clean = asset_raw.split("'")[-2] if "'" in asset_raw else asset_raw
    clean = clean.split("/")[-1].split(".")[0]

    # 1. Montages & Sequences: AM_<PalName>_<AnimName> or AS_<PalName>_<AnimName>
    m = re.match(r'^(?:AM|AS)_[a-zA-Z0-9]+?_(.+)$', clean)
    if m:
        return m.group(1)

    # 2. BlendSpaces: BS_<Type>_<PalName> or BS_<Type>_<PalName>_<SubName>
    m = re.match(r'^BS_([a-zA-Z]+)_[a-zA-Z0-9]+(?:_(.+))?$', clean)
    if m:
        bs_type, sub = m.group(1), m.group(2)
        return f"{bs_type}_{sub}" if sub else bs_type

    # 3. BlendSpaces fallback: BS_<Name>
    if clean.startswith("BS_"):
        return clean[3:]

    # 4. Unique Waza Actions: BP_Action_Unique_<PalName>_<Skill>
    m = re.match(r'^(?:BP_Action_Unique|BP_UniqueAction)_[a-zA-Z0-9]+?_(.+)$', clean)
    if m:
        return m.group(1)

    return clean

def find_key_globally(node, target_key):
    if isinstance(node, dict):
        if target_key in node:
            return node[target_key]
        for v in node.values():
            res = find_key_globally(v, target_key)
            if res is not None:
                return res
    elif isinstance(node, list):
        for item in node:
            res = find_key_globally(item, target_key)
            if res is not None:
                return res
    return None

def main():
    print("=== PalBaker Global Enum -> Animation Names Scraper ===")
    print(f"Reading from:\n  -> {BP_ROOT_DIR}\n")

    if not os.path.exists(BP_ROOT_DIR):
        print(f"❌ ERROR: Directory does not exist:\n{BP_ROOT_DIR}")
        sys.exit(1)

    folders = [d for d in os.listdir(BP_ROOT_DIR) if os.path.isdir(os.path.join(BP_ROOT_DIR, d))]
    print(f"Found {len(folders)} Pal directories.")

    # Dictionary: EnumKey -> Set of valid animation names
    # Example: "EPalActionType::KnockBack" -> {"Damage"}
    enum_to_anims = defaultdict(set)
    
    # Reverse lookup for Python CLI: AnimName -> EnumKey
    # Example: "Damage" -> "EPalActionType::KnockBack"
    anim_to_enum_reverse = {}

    for idx, base_pal in enumerate(folders):
        pal_dir = os.path.join(BP_ROOT_DIR, base_pal)
        
        bp_json = os.path.join(pal_dir, f"BP_{base_pal}.json")
        if not os.path.exists(bp_json):
            candidates = [f for f in os.listdir(pal_dir) if f.startswith("BP_") and f.endswith(".json")]
            if not candidates:
                continue
            bp_json = os.path.join(pal_dir, candidates[0])

        try:
            with open(bp_json, "r", encoding="utf-8-sig") as f:
                raw_json = json.load(f)

            props = None
            if isinstance(raw_json, list):
                for obj in raw_json:
                    if obj.get("Type") == "PalStaticCharacterParameterComponent" or "StaticCharacterParameterComponent" in obj.get("Name", ""):
                        props = obj.get("Properties", {})
                        break

            maps_to_scan = [
                (props.get("GeneralAnimSequenceMap", []) if props else find_key_globally(raw_json, "GeneralAnimSequenceMap") or [], "LocomotionSequence"),
                (props.get("GeneralMontageMap", []) if props else find_key_globally(raw_json, "GeneralMontageMap") or [], "GeneralMontage"),
                (props.get("ActionMontageMap", []) if props else find_key_globally(raw_json, "ActionMontageMap") or [], "ActionMontage"),
                (props.get("GeneralBlendSpaceMap", []) if props else find_key_globally(raw_json, "GeneralBlendSpaceMap") or [], "BlendSpace"),
                (props.get("WazaActionDeclarationMap", []) if props else find_key_globally(raw_json, "WazaActionDeclarationMap") or [], "UniqueAttack"),
            ]

            for map_list, category in maps_to_scan:
                for entry in map_list:
                    full_key = entry.get("Key", "")
                    if not full_key or full_key.endswith("::None") or full_key.endswith("::MAX"):
                        continue

                    asset_ref = entry.get("Value", {}).get("ObjectName", "")
                    if not asset_ref and "AssetPathName" in entry.get("Value", {}):
                        asset_ref = entry["Value"]["AssetPathName"]

                    if asset_ref:
                        anim_name = clean_asset_to_anim_name(asset_ref)
                        if anim_name:
                            enum_to_anims[full_key].add(anim_name)
                            if anim_name not in anim_to_enum_reverse:
                                anim_to_enum_reverse[anim_name] = {
                                    "category": category,
                                    "enum_key": full_key,
                                    "display_name": f"{category.replace('Montage', '')}: {full_key.split('::')[-1].replace('_', ' ')}"
                                }

        except Exception as e:
            pass

    # Sort and convert sets to lists
    final_enum_map = {k: sorted(list(v)) for k, v in sorted(enum_to_anims.items())}

    print("\n=================== SAMPLE OUTPUT ===================")
    for sample_key in [
        "EPalActionType::KnockBack",
        "EPalActionType::Menace",
        "EPalGeneralMontageType::BeLiftupLoop",
        "EPalGeneralMontageType::DamageAdditive",
        "EPalGeneralBlendSpaceType::GeneralMove"
    ]:
        if sample_key in final_enum_map:
            print(f"  {sample_key} -> {final_enum_map[sample_key]}")
    print("=====================================================")

    # 1. Output clean JSON (Enum -> Array of Anim Names)
    with open(ENUM_MAP_JSON, "w", encoding="utf-8") as f:
        json.dump(final_enum_map, f, indent=4)
    print(f"\n✅ Generated JSON: {ENUM_MAP_JSON}")

    # 2. Output TypeScript File for UI
    ts_content = f"""// palbaker-ui/lib/animation-enums.ts
// AUTO-GENERATED BY scrape_all_anim_enums.py

export interface EngineAnimSlotDef {{
  category: "LocomotionSequence" | "GeneralMontage" | "ActionMontage" | "BlendSpace" | "UniqueAttack"
  enumKey: string
  shortName: string
  expectedNlaTracks: string[]
  primaryNlaTrack: string
  description: string
}}

export const ENUM_TO_ANIM_NAMES: Record<string, string[]> = {json.dumps(final_enum_map, indent=2)};

export const ALL_ENGINE_ANIM_SLOTS: EngineAnimSlotDef[] = Object.entries(ENUM_TO_ANIM_NAMES).map(([enumKey, animNames]) => {{
  const shortName = enumKey.split("::").pop() || enumKey;
  let category: EngineAnimSlotDef["category"] = "ActionMontage";

  if (enumKey.startsWith("EPalGeneralBlendSpaceType")) category = "BlendSpace";
  else if (enumKey.startsWith("EPalGeneralMontageType")) category = "GeneralMontage";
  else if (enumKey.startsWith("EPalGeneralAnimSequenceType")) category = "LocomotionSequence";
  else if (enumKey.startsWith("EPalWazaID")) category = "UniqueAttack";

  return {{
    category,
    enumKey,
    shortName,
    expectedNlaTracks: animNames,
    primaryNlaTrack: animNames[0] || shortName,
    description: `${{category}}: ${{shortName.replace(/_/g, " ")}}`
  }};
}});
"""
    with open(TS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ts_content)
    print(f"✅ Generated TypeScript: {TS_OUTPUT_FILE}")

    # 3. Output Python Backend Cache (Anim Name -> Enum)
    os.makedirs(os.path.dirname(PY_CACHE_FILE), exist_ok=True)
    with open(PY_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(anim_to_enum_reverse, f, indent=4)
    print(f"✅ Generated Python Backend Cache: {PY_CACHE_FILE}")

if __name__ == "__main__":
    main()