# utils/builder/config_helper.py

import os

def inject_packaging_settings(ini_path: str, ue_virtual_path: str, skeleton_virtual_path: str, anims_virtual_path: str, has_anims: bool, extra_paths: list = None):
    """Safely updates DefaultGame.ini packaging settings without modifying existing user entries."""
    if not os.path.exists(ini_path):
        return
        
    with open(ini_path, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()
        
    new_lines = []
    in_section = False
    section_found = False
    section_header = "[/Script/UnrealEd.ProjectPackagingSettings]"
    
    keys_to_override = [
        "DirectoriesToAlwaysCook", "+DirectoriesToAlwaysCook", "-DirectoriesToAlwaysCook",
        "bCookAll", "bUseIoStore", "bShareMaterialShaderCode", "MapsToCook", "+MapsToCook", "-MapsToCook"
    ]
    
    # Compile the base cook targets
    append_lines = [
        "bCookAll=False\n",
        "bUseIoStore=False\n",
        "bShareMaterialShaderCode=False\n",
        f'+DirectoriesToAlwaysCook=(Path="{ue_virtual_path}")\n',
        f'+DirectoriesToAlwaysCook=(Path="{skeleton_virtual_path}")\n',
    ]
    if has_anims:
        append_lines.append(f'+DirectoriesToAlwaysCook=(Path="{anims_virtual_path}")\n')
        
    # Append custom third-party shaders/materials if detected
    if extra_paths:
        for path in extra_paths:
            append_lines.append(f'+DirectoriesToAlwaysCook=(Path="{path}")\n')
            
    append_lines.append("MapsToCook=\n")
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped.lower() == section_header.lower():
                in_section = True
                section_found = True
                new_lines.append(line)
                new_lines.extend(append_lines)
                continue
            else:
                in_section = False
                
        if in_section:
            if any(stripped.startswith(k) for k in keys_to_override):
                continue
        new_lines.append(line)
        
    if not section_found:
        new_lines.append("\n" + section_header + "\n")
        new_lines.extend(append_lines)
        
    with open(ini_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)