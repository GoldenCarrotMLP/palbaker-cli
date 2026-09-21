# utils/anim_patcher/feature_scraper.py
import os
import json
import re
from collections import defaultdict

def extract_notifies(am_json_path: str) -> list[str]:
    """Extracts all Notify names from an AnimMontage JSON."""
    notifies = set()
    try:
        with open(am_json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            
        for exp in data.get("Exports", []):
            if "AnimMontage" in exp.get("$type", "") or exp.get("ObjectName", "").startswith("AM_"):
                for prop in exp.get("Data", []):
                    if prop.get("Name") == "Notifies" and isinstance(prop.get("Value"), list):
                        for item in prop["Value"]:
                            for inner_prop in item.get("Value", []):
                                if inner_prop.get("Name") == "NotifyName":
                                    notifies.add(inner_prop.get("Value"))
    except Exception:
        pass
    return list(notifies)

def scrape_feature_requirements(fmodel_exports_dir: str, output_path: str):
    """
    Scans the FModel Exports directory to build the global feature dependency map.
    """
    print("Scraping feature dependencies from game archives...")
    requirements = {
        "UniqueAttacks": {},
        "WorkSuitabilities": {
            "EmitFlame": {"action": "Cooking", "anims": [], "notifies": ["PalEffect"]},
            "Watering": {"action": "WaterGun", "anims": [], "notifies": ["PalEffect"]},
            "Seeding": {"action": "Seeding", "anims": [], "notifies": ["PalEffect"]},
            "GenerateElectricity": {"action": "GenerateElectricity", "anims": [], "notifies": ["PalEffect"]},
            "Handcraft": {"action": "CommonWork", "anims": [], "notifies": []},
            "Mining": {"action": "Mining", "anims": [], "notifies": []},
            "Deforest": {"action": "Deforest", "anims": [], "notifies": []},
            "ProductMedicine": {"action": "ProductMedicine", "anims": [], "notifies": []},
            "Cool": {"action": "Cool", "anims": [], "notifies": ["PalEffect"]}
        },
        "CoopWeapons": {
            "AssaultRifle": {"anims": ["Fire_AssaultRifle"], "notifies": {"Fire_AssaultRifle": ["OnShoot"]}},
            "Shotgun": {"anims": ["Fire_Shotgun"], "notifies": {"Fire_Shotgun": ["OnShoot"]}},
            "Launcher": {"anims": ["Fire_Launcher"], "notifies": {"Fire_Launcher": ["OnShoot"]}},
            "Flamethrower": {"anims": ["Flamethrower", "Flamethrower_Fire_Start", "Flamethrower_Fire"], "notifies": {}}
        }
    }

    # 1. Scrape Unique Attacks
    waza_dir = os.path.join(fmodel_exports_dir, "Pal", "Content", "Pal", "Blueprint", "Action", "Waza")
    if os.path.exists(waza_dir):
        for root, _, files in os.walk(waza_dir):
            for file in files:
                if file.startswith("BP_Action_Unique_") and file.endswith(".json"):
                    waza_id = file.replace("BP_Action_", "").replace(".json", "")
                    with open(os.path.join(root, file), "r", encoding="utf-8-sig") as f:
                        content = f.read()
                        # Find all AM_ references
                        am_refs = re.findall(r'(AM_[a-zA-Z0-9_]+)', content)
                        # Strip prefixes to get generic track names
                        clean_anims = list(set([re.sub(r'^AM_[a-zA-Z0-9]+?_', '', am) for am in am_refs]))
                        
                        requirements["UniqueAttacks"][waza_id] = {
                            "anims": clean_anims,
                            "notifies": {}
                        }

    # Write the knowledge base
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(requirements, f, indent=4)
        
    print(f"Knowledge Base generated successfully at: {output_path}")

if __name__ == "__main__":
    # If run standalone, provide paths
    import sys
    if len(sys.argv) > 2:
        scrape_feature_requirements(sys.argv[1], sys.argv[2])