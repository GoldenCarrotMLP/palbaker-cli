# utils/blueprint_patcher/clone_actions.py
import os
import re
import json
import subprocess
from utils.extractor.core import extract_game_files

def clone_unique_actions(json_data: dict, json_str: str, template_id: str, pal_id: str, settings: dict, temp_dir: str, cooked_dir: str, uasset_gui: str, flags: int, log) -> tuple[dict, str]:
    """
    Actions contain compiled bytecode that breaks when regex-replaced (causing player T-poses).
    Instead of cloning them, we allow the custom Pal to inherit and use the pristine vanilla actions.
    The vanilla actions will dynamically read the Pal's CoopParam_Weapon class anyway.
    """
    log(f"  [Action: Skill] Safely inheriting vanilla actions to prevent bytecode corruption.", "standard")
    return json_data, json_str