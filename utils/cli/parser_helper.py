# utils/cli/parser_helper.py
import argparse

def create_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PalBaker Headless CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # config
    config_parser = subparsers.add_parser("config", help="Manage settings")
    config_subparsers = config_parser.add_subparsers(dest="subcommand", required=True)
    config_get = config_subparsers.add_parser("get", help="Get all settings")
    config_set = config_subparsers.add_parser("set", help="Set a specific setting")
    config_set.add_argument("key", help="Setting key to update")
    config_set.add_argument("value", help="Setting value to save")

    # mod
    mod_parser = subparsers.add_parser("mod", help="Pipeline execution")
    mod_parser.add_argument("action", choices=[
        "extract", "create-blend", "push", "cook", "pack", "full", "decompile",
        "set-icon", "browse-ue", "open-source", "open-ue", "open-pak", "ping",
        "set-preserve-materials", "refresh-blend", "recursive-cook", "set-push-setting",
        "set-blacklist", "dump-anims", "push-anims", "save-notifies", "toggle-anims",
        "set-variant-pack"
    ])
    mod_parser.add_argument("base_pal", help="Original base Pal (e.g., WeaselDragon)")
    mod_parser.add_argument("mod", help="Unique name of the mod")
    mod_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing .blend files during decompile")
    mod_parser.add_argument("--path", help="Path to icon file (or value for toggle)")
    mod_parser.add_argument("--key", help="Specific push setting key (materials, textures, animbp)")

    # audio
    audio_parser = subparsers.add_parser("audio", help="Manage custom audio overrides")
    audio_subparsers = audio_parser.add_subparsers(dest="subcommand", required=True)
    
    audio_set = audio_subparsers.add_parser("set", help="Set a custom audio file for a Pal cry")
    audio_set.add_argument("base_pal", help="Original base Pal")
    audio_set.add_argument("mod", help="Unique name of the mod")
    audio_set.add_argument("cry", help="Name of the cry (e.g. Normal, Joy)")
    audio_set.add_argument("path", help="Path to the audio file (.wav, .mp3, .ogg)")
    
    audio_clear = audio_subparsers.add_parser("clear", help="Clear a custom audio file")
    audio_clear.add_argument("base_pal", help="Original base Pal")
    audio_clear.add_argument("mod", help="Unique name of the mod")
    audio_clear.add_argument("cry", help="Name of the cry")

    audio_play = audio_subparsers.add_parser("play", help="Play a custom audio file")
    audio_play.add_argument("base_pal", help="Original base Pal")
    audio_play.add_argument("mod", help="Unique name of the mod")
    audio_play.add_argument("cry", help="Name of the cry")

    # dynamic_pals
    dyn_parser = subparsers.add_parser("dynamic_pals", help="Manage Dynamic Pal variants")
    dyn_subparsers = dyn_parser.add_subparsers(dest="subcommand", required=True)

    # Add inside dyn_subparsers in parser_helper.py:
    dyn_set_name = dyn_subparsers.add_parser("set-json-name", help="Set custom deployed SwapJSON name")
    dyn_set_name.add_argument("base_pal", help="Original base Pal")
    dyn_set_name.add_argument("mod", help="Unique name of the mod")
    dyn_set_name.add_argument("--name", default="", help="Custom deployed JSON file name")
    
    dyn_toggle = dyn_subparsers.add_parser("toggle", help="Toggle Dynamic Pals framework on/off")
    dyn_toggle.add_argument("base_pal", help="Original base Pal")
    dyn_toggle.add_argument("mod", help="Unique name of the mod")
    dyn_toggle.add_argument("status", choices=["on", "off"], help="Toggle status")
    
    dyn_list = dyn_subparsers.add_parser("list", help="List all variants")
    dyn_list.add_argument("base_pal", help="Original base Pal")
    dyn_list.add_argument("mod", help="Unique name of the mod")

    dyn_add = dyn_subparsers.add_parser("add", help="Add Dynamic Pal variant")
    dyn_add.add_argument("base_pal", help="Original base Pal")
    dyn_add.add_argument("mod", help="Unique name of the mod")
    dyn_add.add_argument("label", help="Variant label name")
    dyn_add.add_argument("--custom", action="store_true", help="Create custom mesh blend")
    dyn_add.add_argument("--source", default="base", help="Skeleton source choice")
    dyn_add.add_argument("--anim-target", default="", help="Cross-pal animation target")

    dyn_delete = dyn_subparsers.add_parser("delete", help="Delete Dynamic Pal variant")
    dyn_delete.add_argument("base_pal", help="Original base Pal")
    dyn_delete.add_argument("mod", help="Unique name of the mod")
    dyn_delete.add_argument("index", type=int, help="Variant index to delete")

    dyn_save = dyn_subparsers.add_parser("save", help="Save/update Dynamic Pal variant")
    dyn_save.add_argument("index", type=int, help="Variant index (-1 for new)")
    dyn_save.add_argument("--data", required=True, help="JSON data payload")

    dyn_sidecar = dyn_subparsers.add_parser("sidecar", help="Sync/Fetch Dynamic Pal sidecar")
    dyn_sidecar.add_argument("base_pal", help="Original base Pal")
    dyn_sidecar.add_argument("mod", help="Unique name of the mod")
    dyn_sidecar.add_argument("blend_name", help="Blend file name")

    dyn_metadata = dyn_subparsers.add_parser("metadata", help="Fetch blend files and available materials for a mod context")
    dyn_metadata.add_argument("base_pal", help="Original base Pal")
    dyn_metadata.add_argument("mod", help="Unique name of the mod")

    dyn_open_blend = dyn_subparsers.add_parser("open-blend", help="Open a .blend file in Blender")
    dyn_open_blend.add_argument("base_pal", help="Original base Pal")
    dyn_open_blend.add_argument("mod", help="Unique name of the mod")
    dyn_open_blend.add_argument("blend_name", help="Blend file name or 'base'")
    dyn_open_blend.add_argument("--category", default="Monster", help="Pal category name")

    # creator
    creator_parser = subparsers.add_parser("creator", help="Manage custom standalone Pals")
    creator_subparsers = creator_parser.add_subparsers(dest="subcommand", required=True)
    creator_list = creator_subparsers.add_parser("list", help="List all custom standalone Pals")
    
    creator_add = creator_subparsers.add_parser("add", help="Create a new standalone Pal")
    creator_add.add_argument("id", help="Target unique ID of the custom Pal")
    creator_add.add_argument("--template", required=True, help="Parent template Pal ID to clone")
    
    creator_delete = creator_subparsers.add_parser("delete", help="Delete a custom standalone Pal")
    creator_delete.add_argument("id", help="Target unique ID to delete")
    
    creator_update = creator_subparsers.add_parser("update", help="Update parameters of a custom standalone Pal")
    creator_update.add_argument("id", help="Target unique ID to update")
    creator_update.add_argument("--data", required=True, help="JSON payload to save")

    creator_refresh_bp = creator_subparsers.add_parser("refresh-bp", help="Refresh Actor Blueprint")
    creator_refresh_bp.add_argument("id", help="Target unique ID to refresh")
    creator_refresh_bp.add_argument("--keep-temp", action="store_true", help="Keep temporary decompiled JSON files in temp_bp_extract for debugging")

    creator_validate = creator_subparsers.add_parser("validate", help="Validate custom Pal features and dependencies")
    creator_validate.add_argument("id", help="Target unique ID to validate")
    # manager
    manager_parser = subparsers.add_parser("manager", help="Global state management")
    manager_subparsers = manager_parser.add_subparsers(dest="subcommand", required=True)
    manager_build_db = manager_subparsers.add_parser("build-db", help="Build the Pal database cache")
    manager_list = manager_subparsers.add_parser("list", help="List all parsed mods")
    manager_list.add_argument("--show-unextracted", action="store_true", help="Include unextracted Pals")
    manager_caches = manager_subparsers.add_parser("get-caches", help="Fetch consolidated database/skills caches directly")

    # env
    env_parser = subparsers.add_parser("env", help="Environment and UE4SS tasks")
    env_subparsers = env_parser.add_subparsers(dest="subcommand", required=True)
    env_subparsers.add_parser("verify", help="Verify workspace setup")
    
    env_ue4ss = env_subparsers.add_parser("ue4ss-install", help="Install, uninstall, or repair UE4SS")
    env_ue4ss.add_argument("--action", choices=["install-palworld", "install-latest", "repair", "uninstall"], default="install-palworld")
    
    env_plugin = env_subparsers.add_parser("install-plugin", help="Install or uninstall PalSchema Plugin")
    env_plugin.add_argument("--action", choices=["install", "uninstall"], default="install")

    env_palschema = env_subparsers.add_parser("palschema-install", help="Install or uninstall PalSchema")
    env_palschema.add_argument("--action", choices=["install", "uninstall"], default="install")

    # Append inside create_cli_parser():
    replacer_parser = subparsers.add_parser("set-vanilla-replacer")
    replacer_parser.add_argument("base_pal")
    replacer_parser.add_argument("variant_name")

    env_subparsers.add_parser("inject-assets", help="Inject required ModKit material assets and templates")
    env_status = env_subparsers.add_parser("status", help="Fetch complete real-time status of UE4SS and PalSchema")
    env_subparsers.add_parser("launch-unreal", help="Launch the configured Unreal Editor for the project")
    env_subparsers.add_parser("restart-unreal", help="Restart the configured Unreal Editor for the project")
    env_subparsers.add_parser("enable-remote-exec", help="Configure DefaultEngine.ini to enable remote Python execution")
    env_subparsers.add_parser("autodetect", help="Autodetect Unreal Engine, Palworld, and Blender paths")
    env_subparsers.add_parser("extract-icons", help="Extract all vanilla Pal icon textures from game archives")

    return parser