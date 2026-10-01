# utils/builder/workspace.py
import os
import json

class ModWorkspace:
    def __init__(self, base_pal: str, mod_name: str, category: str, settings: dict):
        self.base_pal = base_pal
        self.mod_name = mod_name
        self.category = category
        self.settings = settings
        self.is_variant = (base_pal != mod_name)

        self.fmodel_root = settings.get("fmodel_output", "")
        self.ue_root = settings.get("ue_root", "")
        self.uproject_path = settings.get("uproject", "")
        self.blender_path = settings.get("blender", "blender")
        self.palworld_exe = settings.get("palworld_exe", "")

        self.project_dir = os.path.dirname(self.uproject_path) if self.uproject_path else ""
        self.target_project_name = os.path.splitext(os.path.basename(self.uproject_path))[0] if self.uproject_path else ""

        self.ue_cmd_path = os.path.join(self.ue_root, "Engine", "Binaries", "Win64", "UnrealEditor-Cmd.exe") if self.ue_root else ""
        self.unrealpak_path = os.path.join(self.ue_root, "Engine", "Binaries", "Win64", "UnrealPak.exe") if self.ue_root else ""

        # Local source path: if a physical nested subfolder exists, use it; otherwise use shared parent folder
        nested_dir = os.path.join(self.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal, mod_name) if self.fmodel_root else ""
        parent_dir = os.path.join(self.fmodel_root, "Exports", "Pal", "Content", "Pal", "Model", "Character", category, base_pal) if self.fmodel_root else ""

        if self.is_variant and os.path.exists(nested_dir):
            self.fmodel_dir = nested_dir
            self.is_nested_subfolder = True
        else:
            self.fmodel_dir = parent_dir
            self.is_nested_subfolder = False
        
        # Standalone Custom Pal detection
        creator_json = os.path.join(self.fmodel_root, "Exports", "Pal", "Content", "Palbaker", "Creator", f"{mod_name}_creator.json") if self.fmodel_root else ""
        self.is_custom_pal = os.path.exists(creator_json)

        # FIXED: Always check the base_pal's manifest, even if this specific workspace is a variant!
        self.is_dynamic_pals_active = False
        manifest_path = os.path.join(parent_dir, f"{base_pal}_dynamic_pals.json") if parent_dir else ""
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.is_dynamic_pals_active = bool(data.get("is_dynamic_pals_active", False))
            except Exception:
                pass


        # Check if this base Pal is a nested vanilla variant and load custom packaging blacklist
        self.vanilla_parent_folder = None
        self.custom_blacklist = []
        sidecar_path = os.path.join(self.fmodel_dir, f"{mod_name}_blend.json") if self.fmodel_dir else ""
        if os.path.exists(sidecar_path):
            try:
                with open(sidecar_path, "r", encoding="utf-8") as f_side:
                    s_data = json.load(f_side)
                    self.custom_blacklist = s_data.get("custom_blacklist", [])
                    if not self.is_variant:
                        self.vanilla_parent_folder = s_data.get("vanilla_parent_folder")
            except Exception:
                pass

        # Load skipped variants from .palbaker_state.json
        self.skipped_variants = []
        if parent_dir and os.path.exists(parent_dir):
            try:
                from utils.state import get_skipped_variants
                self.skipped_variants = get_skipped_variants(parent_dir)
            except Exception:
                pass
        self.is_skipped = (self.is_variant and self.mod_name in self.skipped_variants)

        # Determine target mesh name and virtual path based on variance and parent nesting
        category_sanitized = category.replace(" ", "_")
        
        # If user created an Dynamic Pals subfolder, route to the subfolder; otherwise keep in shared parent
        if self.is_variant and self.is_nested_subfolder:
            self.target_mesh_name = f"SK_{mod_name}"
            self.ue_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{base_pal}/{mod_name}"
        else:
            self.target_mesh_name = f"SK_{mod_name}"
            self.ue_virtual_path = f"/Game/Pal/Model/Character/{category_sanitized}/{base_pal}"

        # --- DETERMINISTIC PARENT TEMPLATE RESOLUTION ---
        template_id = base_pal
        if self.is_custom_pal:
            try:
                with open(creator_json, "r", encoding="utf-8") as f:
                    c_data = json.load(f)
                    template_id = c_data.get("TemplateID", base_pal)
            except Exception:
                pass
        else:
            if not self.is_variant and os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        variants = data.get("variants", {})
                        if isinstance(variants, dict):
                            base_block = variants.get("base", {})
                        else:
                            base_block = next((v for v in variants if v.get("is_base")), {})
                        template_id = base_block.get("TemplateID", base_pal)
                except Exception:
                    pass
                    
        self.template_id = template_id
        
        # Read base type from manifest to check for custom skeletons
        self.base_type = "vanilla"
        if not self.is_variant and os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.base_type = data.get("variants", {}).get("base", {}).get("base_type", "vanilla")
            except Exception:
                pass

        # Category-agnostic pathing: dynamically supports Monster, NPC, NPC/Boss, and Player
        cat_rel = os.path.normpath(category.replace("/", os.sep))
        cat_virtual = category_sanitized

        self.anims_source_dir = ""
        if self.project_dir:
            if self.is_variant:
                self.anims_source_dir = os.path.join(self.project_dir, "Content", "Pal", "Animation", "Character", cat_rel, base_pal, mod_name)
            else:
                self.anims_source_dir = os.path.join(self.project_dir, "Content", "Pal", "Animation", "Character", cat_rel, base_pal)
        
        # Check custom animations strictly from sidecar manifest, NOT folder presence
        self.has_anims = False
        sidecar_path = os.path.join(self.fmodel_dir, f"{mod_name}_blend.json") if self.fmodel_dir else ""
        if os.path.exists(sidecar_path):
            try:
                with open(sidecar_path, "r", encoding="utf-8") as f_side:
                    s_data = json.load(f_side)
                    self.has_anims = bool(s_data.get("custom_animations", {}).get("is_active", False))
            except Exception:
                pass
        self.custom_shader_raw = os.path.join(self.project_dir, "Content", "CartoonCelShader", "Materials", "CelShader") if self.project_dir else ""
        self.has_custom_shader = os.path.exists(self.custom_shader_raw) if self.custom_shader_raw else False

        # Resolve skeleton directory dynamically for Humans / NPCs / Monsters
        if self.vanilla_parent_folder:
            skel_folder = self.vanilla_parent_folder
        elif "npc" in self.category.lower() or "player" in self.category.lower():
            skel_folder = "Human" if os.path.exists(os.path.join(self.project_dir, "Content", "Pal", "Model", "Character", "Skeleton", "Human")) else "Player"
        else:
            skel_folder = base_pal

        # Nest custom skeleton inside parent to isolate it from the vanilla skeleton
        if self.is_variant and self.has_anims:
            self.skeleton_virtual_path = f"/Game/Pal/Model/Character/Skeleton/{skel_folder}/{mod_name}"
        else:
            self.skeleton_virtual_path = f"/Game/Pal/Model/Character/Skeleton/{skel_folder}"
        
        # Route blueprints and animations inside parent to mirror variant folder logic
        if "npc" in category.lower():
            self.blueprint_virtual_path = f"/Game/Pal/Blueprint/Character/NPC/{base_pal}/{mod_name}" if self.is_variant else f"/Game/Pal/Blueprint/Character/NPC/{mod_name}"
        elif "player" in category.lower():
            self.blueprint_virtual_path = f"/Game/Pal/Blueprint/Character/Player/{base_pal}/{mod_name}" if self.is_variant else f"/Game/Pal/Blueprint/Character/Player/{mod_name}"
        else:
            self.blueprint_virtual_path = f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{base_pal}/{mod_name}" if self.is_variant else f"/Game/Pal/Blueprint/Character/Monster/PalActorBP/{mod_name}"
        
        if self.is_variant:
            self.anims_virtual_path = f"/Game/Pal/Animation/Character/{cat_virtual}/{base_pal}/{mod_name}"
        else:
            self.anims_virtual_path = f"/Game/Pal/Animation/Character/{cat_virtual}/{base_pal}"
            
        self.icon_virtual_path = "/Game/Pal/Texture/PalIcon/Normal"

        self.icon_fmodel_path = os.path.normpath(os.path.join(self.fmodel_dir, f"T_{mod_name}_icon_normal.png")) if self.fmodel_dir else ""
        self.has_icon = os.path.exists(self.icon_fmodel_path) if self.icon_fmodel_path else False

        self.config_dir = os.path.join(self.project_dir, "Config") if self.project_dir else ""
        self.ini_path = os.path.join(self.config_dir, "DefaultGame.ini") if self.config_dir else ""
        self.ini_backup = os.path.join(self.config_dir, "DefaultGame.ini.palbaker.bak") if self.config_dir else ""

        self.cooked_dir = os.path.join(self.project_dir, "Saved", "Cooked", "Windows", self.target_project_name, "Content", self.ue_virtual_path.replace("/Game/", "").replace("/", os.sep)) if self.project_dir else ""
        self.cooked_skel_dir = os.path.join(self.project_dir, "Saved", "Cooked", "Windows", self.target_project_name, "Content", self.skeleton_virtual_path.replace("/Game/", "").replace("/", os.sep)) if self.project_dir else ""
        self.cooked_anims_dir = os.path.join(self.project_dir, "Saved", "Cooked", "Windows", self.target_project_name, "Content", self.anims_virtual_path.replace("/Game/", "").replace("/", os.sep)) if self.project_dir else ""
        self.cooked_bp_dir = os.path.join(self.project_dir, "Saved", "Cooked", "Windows", self.target_project_name, "Content", self.blueprint_virtual_path.replace("/Game/", "").replace("/", os.sep)) if self.project_dir else ""

        self.output_dir = self.fmodel_dir if os.path.exists(self.fmodel_dir) else self.project_dir
        if self.palworld_exe and os.path.exists(self.palworld_exe):
            self.output_dir = os.path.join(os.path.dirname(self.palworld_exe), "Pal", "Content", "Paks", "palBaker")

       # Compile the output pak into mod_name for variants, or base_pal for parents
        pak_name = mod_name if self.is_variant else base_pal
        self.output_pak_clean = os.path.join(self.output_dir, f"{pak_name}_P.pak")
        self.output_pak_err = os.path.join(self.output_dir, f"{pak_name}_err_P.pak")

        self.audio_media_dir = os.path.join(self.fmodel_dir, ".palbaker_audio", "WwiseAudio", "Media") if self.fmodel_dir else ""