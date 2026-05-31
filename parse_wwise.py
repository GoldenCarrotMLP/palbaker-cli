import json
import re
import os

def parse_pal_audio_metadata(input_json_path: str, output_json_path: str = None) -> dict:
    """
    Parses a raw Wwise AkAudioEvent JSON dump and restructures it into an 
    optimized lookup dictionary grouped by Pal internal names.
    """
    if not os.path.exists(input_json_path):
        raise FileNotFoundError(f"Cannot find {input_json_path}")

    with open(input_json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Validate standard array wrapper
    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise ValueError("Invalid JSON structure: Expected a list of objects.")

    root_obj = raw_data[0]
    
    # Navigate safely through the Wwise JSON hierarchy
    try:
        media_array = root_obj["EventCookedData"]["EventLanguageMap"][0]["Value"]["Media"]
    except KeyError:
        raise KeyError("Could not locate 'Media' array inside EventCookedData -> EventLanguageMap.")

    optimized_map = {}

    # Regex to extract Pal name and State from strings like "VO_CowPal_06_Death.wav"
    # Group 1: Pal Name (e.g., "CowPal", "CatMage")
    # Group 2: State (e.g., "Death", "Joy", "Normal")
    regex_pattern = re.compile(r"^VO_(.+?)_\d+_(.+)\.wav$")

    for media in media_array:
        media_id = str(media.get("MediaId"))
        debug_name = media.get("DebugName", "")

        match = regex_pattern.match(debug_name)
        if not match:
            continue

        pal_name = match.group(1)
        state_name = match.group(2)

        # Ensure the Pal exists in the dictionary
        if pal_name not in optimized_map:
            optimized_map[pal_name] = {}

        # Map the state to its target physical path
        optimized_map[pal_name][state_name] = {
            "media_id": media_id,
            "target_path": f"Pal/Content/WwiseAudio/Media/{media_id}.wem"
        }

    # Optionally write to a clean JSON file
    if output_json_path:
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(optimized_map, f, indent=4)
            
    return optimized_map

# --- Execution Example ---
if __name__ == "__main__":
    # Assuming the raw data is saved as "AKE_Pal_Cry_Test.json"
    input_file = "AKE_Pal_Cry_Test.json"
    output_file = "pal_audio_map.json"
    
    if os.path.exists(input_file):
        clean_map = parse_pal_audio_metadata(input_file, output_file)
        print(f"Successfully mapped {len(clean_map)} Pals.")
        print(f"Data saved to {output_file}")