# utils/dynamic_pals/compiler.py
import os
from utils.dynamic_pals_helper import compile_unified_dynamic_pals_json

class DynamicPalsCompiler:
    def __init__(self, controller):
        self.c = controller

    def deploy_to_game(self, current_char_id: str, fmodel_target_dir: str):
        """Compiles the memory states and deploys the Format V2 JSON directly to ~Mods/ModelJSON (migrating any legacy SwapJSON)."""
        palworld_exe = self.c.settings.get("palworld_exe", "")
        if palworld_exe and os.path.exists(palworld_exe):
            from utils.dynamic_pals_helper import get_model_json_dirs
            model_json_dir, legacy_swap_json_dir = get_model_json_dirs(palworld_exe)
            success, msg = compile_unified_dynamic_pals_json(
                current_char_id, fmodel_target_dir, model_json_dir, legacy_swap_json_dir
            )
            if success:
                self.c.view.write_log(f"Auto-deployed updated Dynamic Pals JSON: {msg}", "success")
            else:
                self.c.view.write_log(f"Auto-deployment failed: {msg}", "error")
