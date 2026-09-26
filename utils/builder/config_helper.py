# utils/builder/config_helper.py
import os
import shutil
import time

def safe_copy_file(src: str, dst: str, retries: int = 10, delay: float = 0.3) -> bool:
    """Copies file with retries to gracefully handle momentary Windows file locks (WinError 32)."""
    for i in range(retries):
        try:
            shutil.copy2(src, dst)
            return True
        except (PermissionError, OSError):
            time.sleep(delay)
    # Final attempt
    shutil.copy2(src, dst)
    return True

def restore_palbaker_backup(uproject_path: str):
    if not uproject_path or not os.path.exists(uproject_path):
        return
    project_dir = os.path.dirname(uproject_path)
    ini_path = os.path.join(project_dir, "Config", "DefaultGame.ini")
    backup_path = ini_path + ".palbaker.bak"
    if os.path.exists(backup_path):
        for _ in range(5):
            try:
                shutil.copy2(backup_path, ini_path)
                os.remove(backup_path)
                break
            except (PermissionError, OSError):
                time.sleep(0.3)

def inject_packaging_settings(ini_path: str, ue_virtual_path: str, skeleton_virtual_path: str, anims_virtual_path: str, has_anims: bool, extra_paths: list = None):
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
                clean_p = path.strip()
                # Inject both /Game/... and relative content paths to guarantee UE5 cooker finds the folder
                append_lines.append(f'+DirectoriesToAlwaysCook=(Path="{clean_p}")\n')
                if clean_p.startswith("/Game/"):
                    rel_p = clean_p[6:]
                    append_lines.append(f'+DirectoriesToAlwaysCook=(Path="{rel_p}")\n')
            
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
    def __init__(self, workspace, extra_paths: list = None):
        self.workspace = workspace
        self.extra_paths = extra_paths or []

    def __enter__(self):
        if self.workspace.config_dir:
            os.makedirs(self.workspace.config_dir, exist_ok=True)

        if os.path.exists(self.workspace.ini_path):
            safe_copy_file(self.workspace.ini_path, self.workspace.ini_backup)
            
            actual_extra_paths = list(self.extra_paths)
            
            # --- DYNAMIC RECURSIVE DISCOVERY AND BINDING ---
            category_sanitized = self.workspace.category.replace(" ", "_").replace("\\", "/")
            cat_parts = self.workspace.category.replace("/", os.sep)
                
            # Check both FModel export directory AND Unreal Project Content folder
            candidate_source_dirs = []
                
            base_fmodel_dir = os.path.normpath(os.path.join(
                self.workspace.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", 
                cat_parts, self.workspace.base_pal
            )) if self.workspace.fmodel_root else ""
            if os.path.exists(base_fmodel_dir):
                candidate_source_dirs.append(base_fmodel_dir)

            ue_project_char_dir = os.path.normpath(os.path.join(
                self.workspace.project_dir, "Content", "Pal", "Model", "Character", 
                cat_parts, self.workspace.base_pal
            )) if self.workspace.project_dir else ""
            if os.path.exists(ue_project_char_dir) and ue_project_char_dir not in candidate_source_dirs:
                candidate_source_dirs.append(ue_project_char_dir)

            discovered_subs = set()
            for c_dir in candidate_source_dirs:
                for sub in os.listdir(c_dir):
                    sub_path = os.path.join(c_dir, sub)
                    if os.path.isdir(sub_path) and not sub.startswith(".") and sub.lower() not in ["sources", ".palbaker_audio"]:
                        discovered_subs.add(sub)

            for sub in sorted(list(discovered_subs)):
                if hasattr(self.workspace, "skipped_variants") and sub in self.workspace.skipped_variants:
                    print(f"  [Recursive Cook] Skipping variant subfolder '{sub}' (in skipped_variants).", flush=True)
                    continue
                variant_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{self.workspace.base_pal}/{sub}"
                if variant_virtual_path not in actual_extra_paths:
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
            for _ in range(10):
                try:
                    shutil.move(self.workspace.ini_backup, self.workspace.ini_path)
                    break
                except (PermissionError, OSError):
                    time.sleep(0.3)