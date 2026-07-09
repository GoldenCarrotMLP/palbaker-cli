# utils/builder/config_helper.py
import os
import shutil

def restore_palbaker_backup(uproject_path: str):
    if not uproject_path or not os.path.exists(uproject_path):
        return
    project_dir = os.path.dirname(uproject_path)
    ini_path = os.path.join(project_dir, "Config", "DefaultGame.ini")
    backup_path = ini_path + ".palbaker.bak"
    if os.path.exists(backup_path):
        try:
            shutil.copy2(backup_path, ini_path)
            os.remove(backup_path)
        except Exception:
            pass

def inject_packaging_settings(ini_path: str, ue_virtual_path: str, skeleton_virtual_path: str, anims_virtual_path: str, has_anims: bool, extra_paths: list | None = None):
    if not os.path.exists(ini_path):
        return
        
    with open(ini_path, "r", encoding="utf-8-sig", errors="replace") as f:
        content = f.read()

    section_header = "[/Script/UnrealEd.ProjectPackagingSettings]"
    lines = content.splitlines()
    
    new_lines = []
    in_section = False
    section_found = False
    
    keys_to_override = [
        "DirectoriesToAlwaysCook", "+DirectoriesToAlwaysCook", "-DirectoriesToAlwaysCook",
        "bCookAll", "bUseIoStore", "bShareMaterialShaderCode", "MapsToCook", "+MapsToCook", "-MapsToCook"
    ]
    
    append_lines = [
        "bCookAll=False\n",
        "bUseIoStore=False\n",
        "bShareMaterialShaderCode=False\n",
        f'+DirectoriesToAlwaysCook=(Path="{ue_virtual_path}")\n',
        f'+DirectoriesToAlwaysCook=(Path="{skeleton_virtual_path}")\n'
    ]
    
    if has_anims:
        append_lines.append(f'+DirectoriesToAlwaysCook=(Path="{anims_virtual_path}")\n')
        
    if extra_paths:
        for path in extra_paths:
            append_lines.append(f'+DirectoriesToAlwaysCook=(Path="{path}")\n')
            
    append_lines.append("MapsToCook=(Map=\"/Engine/Maps/Entry\")\n")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section:
                new_lines.extend(append_lines)
            
            if stripped.lower() == section_header.lower():
                in_section = True
                section_found = True
                new_lines.append(line)
                continue
            else:
                in_section = False
                
        if in_section:
            clean_key = stripped.split("=")[0].strip()
            if clean_key in keys_to_override:
                continue
                
        new_lines.append(line)
        
    if in_section:
        new_lines.extend(append_lines)
        
    if not section_found:
        new_lines.append(f"\n{section_header}\n")
        new_lines.extend(append_lines)
        
    with open(ini_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

class GameIniCookContext:
    def __init__(self, workspace, extra_paths: list | None = None):
        self.workspace = workspace
        self.extra_paths = extra_paths or []

    def __enter__(self):
        if self.workspace.config_dir:
            os.makedirs(self.workspace.config_dir, exist_ok=True)

        if os.path.exists(self.workspace.ini_path):
            shutil.copy2(self.workspace.ini_path, self.workspace.ini_backup)
            
            actual_extra_paths = list(self.extra_paths)
            
            # --- DYNAMIC RECURSIVE DISCOVERY AND BINDING ---
            category_sanitized = self.workspace.category.replace(" ", "_")
            base_fmodel_dir = os.path.normpath(os.path.join(
                self.workspace.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", 
                self.workspace.category, self.workspace.base_pal
            ))
            
            if os.path.exists(base_fmodel_dir):
                for sub in os.listdir(base_fmodel_dir):
                    sub_path = os.path.join(base_fmodel_dir, sub)
                    # Automatically queue every subdirectory on disk to always cook
                    if os.path.isdir(sub_path) and not sub.startswith(".") and sub.lower() != "sources":
                        variant_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{self.workspace.base_pal}/{sub}"
                        actual_extra_paths.append(variant_virtual_path)
                        print(f"  [Recursive Cook] Automatically queued variant subfolder: {variant_virtual_path}", flush=True)

            inject_packaging_settings(
                self.workspace.ini_path,
                self.workspace.ue_virtual_path,
                self.workspace.skeleton_virtual_path,
                self.workspace.anims_virtual_path,
                self.workspace.has_anims,
                extra_paths=actual_extra_paths
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if os.path.exists(self.workspace.ini_backup):
            shutil.move(self.workspace.ini_backup, self.workspace.ini_path)