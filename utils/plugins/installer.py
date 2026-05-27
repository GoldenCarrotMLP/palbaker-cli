import os
import shutil
import subprocess
import time

def sync_plugin_files(src_dir: str, dest_dir: str, verbose: bool = False):
    """Syncs/copies the plugin folder structure from the repository to the ModKit."""
    if verbose:
        print(f">>> Copying plugin source files to: {dest_dir}")
    shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)

def inject_framework_assets(src_assets_dir: str, dest_content_dir: str, verbose: bool = False):
    """Injects precompiled framework .uassets (materials, etc.) into the ModKit's Content directory."""
    if os.path.exists(src_assets_dir):
        if verbose:
            print(f">>> Injecting Palworld master material dependencies to: {dest_content_dir}")
        shutil.copytree(src_assets_dir, dest_content_dir, dirs_exist_ok=True)
    return True, "Master materials successfully injected into project!"

def copy_dlls_back(dest_dll_dir: str, src_dll_dir: str, verbose: bool = False):
    """Copies compiled DLLs back to the repository, aggressively filtering out PDBs and Live Coding junk."""
    if os.path.exists(dest_dll_dir):
        if verbose:
            print(f">>> Copying clean compiled binaries back into local repository: {src_dll_dir}")
        os.makedirs(src_dll_dir, exist_ok=True)
        
        # Clear old DLLs in source directory first
        for f in os.listdir(src_dll_dir):
            try:
                os.remove(os.path.join(src_dll_dir, f))
            except Exception:
                pass

        for f in os.listdir(dest_dll_dir):
            # Skip Live Coding/Hot Reload temporary binaries (e.g. *-0001.dll)
            if "-" in f and f.split("-")[-1].split(".")[0].isdigit():
                continue
            # Skip massive .pdb debug databases (saves ~50MB per build in Git)
            if f.endswith(".pdb"):
                continue
            
            shutil.copy2(os.path.join(dest_dll_dir, f), os.path.join(src_dll_dir, f))

def enable_remote_execution_settings(uproject_path: str) -> tuple[bool, str]:
    """Safely injects Python Remote Execution settings into DefaultEngine.ini."""
    project_dir = os.path.dirname(uproject_path)
    config_dir = os.path.join(project_dir, "Config")
    os.makedirs(config_dir, exist_ok=True)
    
    ini_path = os.path.join(config_dir, "DefaultEngine.ini")
    
    lines = []
    if os.path.exists(ini_path):
        with open(ini_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
            
    new_lines = []
    in_section = False
    section_found = False
    remote_exec_found = False
    dev_mode_found = False
    
    section_header = "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]"
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped.lower() == section_header.lower():
                in_section = True
                section_found = True
                new_lines.append(line)
                continue
            else:
                in_section = False
                
        if in_section:
            clean_line = stripped.replace(" ", "").lower()
            if clean_line.startswith("bremoteexecution="):
                new_lines.append("bRemoteExecution=True\n")
                remote_exec_found = True
                continue
            elif clean_line.startswith("bdevelopermode="):
                new_lines.append("bDeveloperMode=True\n")
                dev_mode_found = True
                continue
                
        new_lines.append(line)
        
    if not section_found:
        new_lines.append("\n" + section_header + "\n")
        new_lines.append("bRemoteExecution=True\n")
        new_lines.append("bDeveloperMode=True\n")
    else:
        if not remote_exec_found or not dev_mode_found:
            new_lines.append("\n" + section_header + "\n")
            if not remote_exec_found:
                new_lines.append("bRemoteExecution=True\n")
            if not dev_mode_found:
                new_lines.append("bDeveloperMode=True\n")
                
    with open(ini_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    return True, "Python Remote Execution successfully enabled!"

def enable_cooking_settings(uproject_path: str) -> tuple[bool, str]:
    """Safely injects bUseIoStore=False and bShareMaterialShaderCode=False into DefaultGame.ini."""
    project_dir = os.path.dirname(uproject_path)
    config_dir = os.path.join(project_dir, "Config")
    os.makedirs(config_dir, exist_ok=True)
    
    ini_path = os.path.join(config_dir, "DefaultGame.ini")
    
    lines = []
    if os.path.exists(ini_path):
        with open(ini_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
            
    new_lines = []
    in_section = False
    section_found = False
    io_store_found = False
    shader_code_found = False
    
    section_header = "[/Script/UnrealEd.ProjectPackagingSettings]"
    keys_to_override = ["bUseIoStore", "bShareMaterialShaderCode"]
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped.lower() == section_header.lower():
                in_section = True
                section_found = True
                new_lines.append(line)
                continue
            else:
                in_section = False
                
        if in_section:
            clean_line = stripped.replace(" ", "").lower()
            if clean_line.startswith("buseiostore="):
                new_lines.append("bUseIoStore=False\n")
                io_store_found = True
                continue
            elif clean_line.startswith("bsharematerialshadercode="):
                new_lines.append("bShareMaterialShaderCode=False\n")
                shader_code_found = True
                continue
                
        new_lines.append(line)
        
    if not section_found:
        new_lines.append("\n" + section_header + "\n")
        new_lines.append("bUseIoStore=False\n")
        new_lines.append("bShareMaterialShaderCode=False\n")
    else:
        if not io_store_found or not shader_code_found:
            new_lines.append("\n" + section_header + "\n")
            if not io_store_found:
                new_lines.append("bUseIoStore=False\n")
            if not shader_code_found:
                new_lines.append("bShareMaterialShaderCode=False\n")
                
    with open(ini_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    return True, "Project packaging settings successfully configured!"

def restart_unreal_editor(ue_root: str, uproject_path: str, verbose: bool = False) -> tuple[bool, str]:
    """Terminates any running UnrealEditor.exe processes and headlessly relaunches the target project."""
    editor_exe = os.path.join(ue_root, "Engine", "Binaries", "Win64", "UnrealEditor.exe")
    if not os.path.exists(editor_exe):
        return False, f"Could not find UnrealEditor.exe at {editor_exe}"
        
    if verbose:
        print(">>> Terminating running Unreal Editor instances...")
    try:
        if os.name == 'nt':
            subprocess.run(["taskkill", "/F", "/IM", "UnrealEditor.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "UnrealEditor"], capture_output=True)
    except Exception as e:
        if verbose:
            print(f"Warning during taskkill: {e}")
            
    time.sleep(1.0)
    
    if verbose:
        print(f">>> Relaunching project: {uproject_path}")
    try:
        creation_flags = 0x00000008 if os.name == 'nt' else 0
        subprocess.Popen(
            [editor_exe, uproject_path],
            creationflags=creation_flags,
            close_fds=True,
            start_new_session=True if os.name != 'nt' else False
        )
        return True, "Unreal Editor successfully restarted!"
    except Exception as e:
        return False, f"Failed to relaunch Unreal Editor: {e}"