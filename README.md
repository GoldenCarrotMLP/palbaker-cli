# PalBaker CLI & Modding Suite

Automated modding pipeline and developer toolchain for Palworld (Unreal Engine 5.1). Bridges raw game extracts, Blender 3.x–5.x headless workspaces, Unreal Engine remote Python execution, UAssetAPI AST patching, and target micro-cooking into production `_P.pak` archives.

---

## Architecture Overview

```
                      ┌───────────────────────────────────────┐
                      │    palbaker_cli.py / ui_client        │
                      └──────────────────┬────────────────────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 ▼                       ▼                       ▼
      [CUE4Parse Ingestion]      [Headless Blender]      [Unreal Remote Exec]
       Dumps game paks, .psk,    Exports clean .fbx,      Serializes textures/
       textures, and tables.     bakes MRAO, tracks       materials, compiles
                                 NLA durations, bones.    AnimBP via C++ module.
                                         │
                                         ▼
                             [Actor Blueprint Synthesizer]
                              UAssetAPI AST patcher: mounts,
                              weapons, funnels, wazas, VFX.
                                         │
                                         ▼
                               [UnrealEngine Cooker]
                               Targeted micro-cooking via
                               DefaultGame.ini injection.
                                         │
                                         ▼
                                [UnrealPak Packaging]
                                Safe skeleton/physics asset
                                stripping + ModelJSON deploy.
```

---

## Directory & File Reference

| File / Folder | Purpose |
| :--- | :--- |
| **`palbaker_cli.py`** | Main CLI entry point routing `mod`, `creator`, `dynamic_pals`, `audio`, `env`, `manager`, and `config` commands. |
| **`build_mod.py`** | Backend orchestrator running Blender export, Unreal remote import, micro-cooking, and packaging in an unbuffered subprocess. |
| **`ue_import.py`** | Remote Python script executed inside Unreal Editor to import FBX models, textures, build Material Instances, and bind AnimBPs. |
| **`ue_export.py`** | Remote Python script executed inside Unreal Editor to decompile SkeletalMeshes and material topologies back to disk. |
| **`CLAUDE.md`** | Dedicated, token-optimized context reference for Claude Code and LLM engineering sessions. |
| **`ui_client/`** | Lightweight async client layer (`dispatcher.py`, `utils.py`) bridging GUI applications to `palbaker_cli.py`. |
| **`unreal_scripts/`** | Scripts injected into running Unreal Editor (`importer.py`, `materials.py`, `rigging.py`, `import_anims.py`, `dependency_crawler.py`). |
| **`utils/anim_patcher/`** | Animation discovery and cloning subsystem (`anim_discovery.py`, `anim_cloner.py`, `montage_generator.py`). |
| **`utils/blender_utils/`** | Dynamic Blender version adapter (`BlenderTranslator`) supporting Blender 3.x, 4.x, and 5.x Slotted Actions. |
| **`utils/blueprint_patcher/`**| UAssetAPI AST patcher synthesizing Actor Blueprints, mounts, funnels, partner weapons, and unique attacks. |
| **`utils/builder/`** | Subprocess utilities for `build_mod.py`: workspace pathing, `DefaultGame.ini` context manager, cooker runner, and log analyzer. |
| **`utils/creator/`** | Standalone Pal Creator system (`pal_manager.py`, `palschema_exporter.py`, `waza_scraper.py`, `cache_loader.py`). |
| **`utils/dynamic_pals/`** | Runtime variant swapping (`manifest_manager.py`, `cloner.py`, `compiler.py`, `dynamic_pals_helper.py`). |
| **`utils/extractor/`** | `cue4parse.exe` extraction wrapper, asset cloner, and database cache compiler (`db_builder.py`). |
| **`utils/plugins/`** | MSVC compiler diagnostic, `PalBakerEditorUtils` UBT/RunUAT compiler, and Unreal Editor process lifecycle manager. |
| **`plugins/PalBakerEditorUtils/`** | Custom Unreal Engine 5.1 C++ Editor module exposing AnimGraph node instantiation, socket injection, and IK Retargeting. |
| **`tests/`** | Atomic end-to-end integration test harness (`run_all_tests.py`, `test_01` through `test_18`). |

---

## Quick Start (CLI)

```bash
# 1. Verify system environment, MSVC v143 compiler, and Unreal paths
python palbaker_cli.py env verify

# 2. Extract base Pal assets from game paks
python palbaker_cli.py mod extract Kitsunebi Kitsunebi

# 3. Create .blend reconstruction workspace
python palbaker_cli.py mod create-blend Kitsunebi Kitsunebi

# 4. Push model and materials to Unreal Editor (requires running Editor with Remote Execution enabled)
python palbaker_cli.py mod push Kitsunebi Kitsunebi

# 5. Compile and pack final _P.pak archive
python palbaker_cli.py mod cook Kitsunebi Kitsunebi
python palbaker_cli.py mod pack Kitsunebi Kitsunebi
```

---

## Testing

Run the full end-to-end regression suite:
```bash
python tests/run_all_tests.py
```