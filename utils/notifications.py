# utils/notifications.py
import os
import sys
import subprocess
import shutil

def play_chime():
    """Plays the bell.mp3 asset natively without blocking UI or external heavy libraries."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bell_path = os.path.join(repo_root, "assets", "bell.mp3")
    
    if not os.path.exists(bell_path):
        return

    if sys.platform == "win32":
        import ctypes
        # Use mciSendStringW to natively decode and play MP3s on Windows via winmm.dll
        # We use 'wait' to block the Python thread just long enough for the short chime to finish,
        # otherwise the process might exit immediately and clip the sound.
        ctypes.windll.winmm.mciSendStringW(f'open "{bell_path}" alias palbaker_bell', None, 0, None)
        ctypes.windll.winmm.mciSendStringW('play palbaker_bell wait', None, 0, None)
        ctypes.windll.winmm.mciSendStringW('close palbaker_bell', None, 0, None)
    elif sys.platform == "darwin":
        subprocess.Popen(["afplay", bell_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
    else:
        for player in ["paplay", "aplay", "play", "mpg123"]:
            if shutil.which(player):
                subprocess.Popen([player, bell_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
                break

def send_notification(title: str, message: str):
    """Dispatches a native OS desktop notification."""
    if sys.platform == "win32":
        # Dispatches a native Balloon Tip / Toast notification via hidden PowerShell execution
        ps_script = f"""
        Add-Type -AssemblyName System.Windows.Forms
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.BalloonTipIcon = 'Info'
        $notify.BalloonTipTitle = '{title}'
        $notify.BalloonTipText = '{message}'
        $notify.Visible = $True
        $notify.ShowBalloonTip(5000)
        Start-Sleep -Seconds 5
        $notify.Dispose()
        """
        creation_flags = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script], 
            creationflags=creation_flags
        )
    elif sys.platform == "darwin":
        os.system(f"""osascript -e 'display notification "{message}" with title "{title}"'""")
    else:
        if shutil.which("notify-send"):
            os.system(f'notify-send "{title}" "{message}"')

def trigger_action_complete(action: str, mod_name: str, settings: dict, success: bool = True):
    """
    Router to trigger sounds and popups according to user settings and action type.
    """
    if not success:
        return
        
    use_sound = settings.get("notification_sound", True)
    use_popup = settings.get("notification_popup", True)
    
    # Actions that should play the chime sound
    chime_actions = {"push", "push-anims", "cook", "pack", "pack-only", "cook-only", "full", "recursive-cook", "recursive_cook", "cook_only", "pack_only"}
    
    # Actions that indicate the absolute completion of a "bake"
    popup_actions = {"pack", "pack-only", "full", "pack_only"}

    if use_sound and action in chime_actions:
        play_chime()
        
    if use_popup and action in popup_actions:
        send_notification("PalBaker", f"Successfully baked: {mod_name}")
