import os
import subprocess

def run_ubt_compilation(ue_root: str, uproject_path: str, verbose: bool = False) -> tuple[bool, str]:
    """Helper that regenerates project files and invokes the UBT batch compiler."""
    out_stream = None if verbose else subprocess.PIPE
    err_stream = None if verbose else subprocess.STDOUT

    ubt_exe = os.path.join(ue_root, "Engine", "Binaries", "DotNET", "UnrealBuildTool", "UnrealBuildTool.exe")
    if not os.path.exists(ubt_exe):
        return False, f"Could not find UnrealBuildTool.exe at: {ubt_exe}"

    # 1. Regenerate Project Files
    gen_cmd = [ubt_exe, "-projectfiles", f"-project={uproject_path}", "-game"]
    if verbose:
        print(">>> Regenerating project files...")
    try:
        subprocess.run(gen_cmd, check=True, stdout=out_stream, stderr=err_stream)
    except subprocess.CalledProcessError as e:
        if not verbose:
            print(f"Project generation warning (Exit code: {e.returncode}).")

    # 2. Compile the Project
    build_bat = os.path.join(ue_root, "Engine", "Build", "BatchFiles", "Build.bat")
    project_name = os.path.splitext(os.path.basename(uproject_path))[0]
    cmd = [build_bat, f"{project_name}Editor", "Win64", "Development", f"-Project={uproject_path}", "-WaitMutex"]

    if verbose:
        print(f">>> Compiling Plugin using Command:\n{' '.join(cmd)}\n")
    try:
        subprocess.run(cmd, check=True, stdout=out_stream, stderr=err_stream)
        return True, "Success"
    except subprocess.CalledProcessError as e:
        error_msg = "" if verbose else e.output.decode('utf-8', errors='replace')
        return False, f"Compilation failed with exit code {e.returncode}. {error_msg}"