# PalBaker Architecture & Coding Guidelines (Claude Code Reference)

Automated modding pipeline for Palworld (UE 5.1). Bridges CUE4Parse asset extraction, headless Blender workspace reconstruction, Unreal Engine Python Remote Execution, UAssetAPI AST serialization, micro-cooking, and UnrealPak packaging.

## Core Conventions & Rules
1. **Never Blind-Replace Donor Names**: When retargeting actions/modules, do NOT execute `content.replace(donor_pal, pal_id)`. Base game VFX (`BP_SkillEffect_*`), Niagara systems (`NS_*`), and audio events (`AKE_*`) live in vanilla engine packages and must retain their donor paths.
2. **Order of String Replacements**: Always replace full package paths (`/Game/.../{donor}/{asset}`) BEFORE replacing bare class names (`{asset}`).
3. **Tagged Serialization in UE 5.1**: Ensure `HasUnversionedProperties = False` on patched animation/blueprint ASTs to prevent `FUnversionedHeader` bitstream drift and `Array.cpp` buffer overflow crashes.
4. **Subprocess Resilience**: Run subprocesses with `CREATE_NO_WINDOW` on Windows (`creationflags = 0x08000000`) and UTF-8 encoding.
5. **Blender 5.x Slotted Actions**: Do not access `act.fcurves` directly; verify `hasattr(act, "fcurves")` or inspect action channelbags/layers. Only auto-push actions beginning with `AS_` into NLA tracks.
6. **AnimMontage/Sequence In-Bounds Guard**: Never inject notifies past `SequenceLength` (`Time > Duration`).

## Common CLI Commands
- Run Pipeline: `python palbaker_cli.py mod <action> <base_pal> <mod_name>` (actions: `extract`, `create-blend`, `push`, `cook`, `pack`, `full`, `refresh-blend`, `dump-anims`, `push-anims`)
- Creator: `python palbaker_cli.py creator <list|add|update|delete|refresh-bp|validate>`
- Dynamic Pals: `python palbaker_cli.py dynamic_pals <list|add|save|delete|sidecar|metadata|set-json-name>`
- Environment: `python palbaker_cli.py env <verify|install-plugin|ue4ss-install|palschema-install|status|launch-unreal|restart-unreal|enable-remote-exec|autodetect>`
- Run Tests: `python tests/run_all_tests.py`

## Directory Map & File Responsibilities

### Root Orchestrators
- `palbaker_cli.py`: Unified CLI router (`config`, `mod`, `audio`, `dynamic_pals`, `creator`, `manager`, `env`).
- `build_mod.py`: Headless pipeline worker executing Blender FBX export, Unreal remote import, micro-cooking, and `UnrealPak` packaging.
- `ue_import.py`: In-engine Python script importing FBX meshes, textures, generating material instances, and wiring AnimBPs.
- `ue_export.py`: In-engine Python script exporting SkeletalMeshes and material topology metadata to disk.
- `palbaker_cli.spec`: PyInstaller bundle specification.
- `manager_settings.json`: User path configuration (`fmodel_output`, `ue_root`, `uproject`, `blender`, `palworld_exe`).

### `ui_client/` (Frontend Communication)
- `dispatcher.py`: Async wrapper (`PalBakerCLI`) executing CLI subcommands and streaming JSONL logs.
- `utils.py`: Event wrapper decorator (`@cli_action`) managing UI button state.

### `unreal_scripts/` (In-Editor Remote Execution)
- `importer.py`: Imports FBX meshes/textures, deduplicates physics assets, and injects skeleton sockets/VBs.
- `materials.py`: Builds and binds `MaterialInstanceConstant` assets to skeletal mesh slots.
- `rigging.py`: Instantiates `AnimBlueprint` assets and invokes C++ plugin node generation.
- `dependency_crawler.py`: Scans asset dependencies in `/Game` to discover external packages for cooking.
- `import_anims.py`: Ingests animation FBXs into Unreal, binds skeletons, and flags root motion.

### `utils/` (Core Pipeline Logic)
- `scanner.py`: Scans `Monster`, `NPC`, `Player` character folders; resolves casing, variants, and pak status.
- `state.py`: MTime delta tracking between source files and cooked assets (`.palbaker_state.json`).
- `sidecar_helper.py`: Safe JSON loader and non-destructive updater for companion sidecars (`*_blend.json`).
- `names.py`: Localized Pal/NPC display name resolver via `deps/pal_names_map.json`.
- `node_builder.py`: Constructs Principled BSDF shader networks in Blender from JSON material parameters.
- `image_combiner.py`: Packs Metallic, Roughness, and AO channels into MRAO PNG textures using NumPy.
- `fmodel_helper.py`: Extracts texture references from FModel material JSONs, copies assets, and syncs baselines.
- `config.py`: Loads, validates, and normalizes UNC paths in `manager_settings.json`.
- `notifications.py`: Dispatches native OS toasts and audio chimes upon build completion.
- `validator.py`: Cross-references Pal Creator features against companion sidecars for missing animations, notifies, or socket mismatches.
- `uasset_safety_validator.py`: Inspects UAssetAPI ASTs for unversioned serialization leaks or illegal properties.
- `uasset_helper.py`: UAssetGUI CLI wrapper (`tojson`, `fromjson`), NameMap synchronizer, and montage/sequence AST retargeter.
- `plugin_manager.py`: Verifies MSVC toolchain and compiles `PalBakerEditorUtils` into project.
- `check_compiler_requirements.py`: Diagnoses MSVC v143 (14.3x) compiler toolsets and repairs `BuildConfiguration.xml`.
- `palschema_helper.py`: Manages automated downloading, extraction, and configuration of PalSchema mod.
- `ue4ss_helper.py`: Detects, installs, and validates UE4SS branches in game binary folders.

### `utils/builder/` (Subprocess Helpers for `build_mod.py`)
- `workspace.py`: Immutable `ModWorkspace` dataclass resolving disk and `/Game/...` virtual paths.
- `config_helper.py`: Context manager (`GameIniCookContext`) temporarily restricting `DefaultGame.ini` cooking paths.
- `cooker_helper.py`: RAM checker, asset manifest resolver, and `UnrealPak.exe` execution wrapper.
- `blender_helper.py`: Headless Blender process runner (`run_headless_blender`) with version detection.
- `unreal_helper.py`: UDP multicast remote execution connector (`run_remote_command`, `run_remote_import`).
- `blacklist_helper.py`: Scans and excludes master materials from being packaged into final paks.
- `dependency_crawler.py`: Remote dependency resolution coordinator.
- `log_analyzer.py`: Streams and parses compiler log lines to match known error signatures.
- `pipeline_runner.py`: Async subprocess runner with throttled log streaming.

### `utils/creator/` (Standalone Pal Creation)
- `__init__.py`: `CreatorController` orchestrating standalone Pal workflows.
- `pal_manager.py`: CRUD operations for `*_creator.json` manifests.
- `cache_loader.py`: Loads static caches from `deps/`.
- `palschema_exporter.py`: Generates and deploys PalSchema JSON tables (`pals`, `translations`, `raw`, `spawners`).
- `waza_scraper.py`: Discovers donor Pals for unique wazas and extracts action dependencies.

### `utils/dynamic_pals/` & `utils/dynamic_pals_helper.py` (Runtime Variant Swapping)
- `manifest_manager.py`: Manages `*_dynamic_pals.json` variant manifests.
- `cloner.py`: Clones `.blend` models and sidecars for sub-variants.
- `compiler.py`: Compiles and deploys Format V2 JSON configs to `~Mods/ModelJSON`.
- `dynamic_pals_helper.py`: Extracts Blender slots/morphs, compiles unified ModelJSON, and syncs sidecar metadata.

### `utils/blueprint_patcher/` (Actor Blueprint AST Synthesizer)
- `__init__.py`: Master orchestrator `patch_actor_blueprint()` synthesizing BP, ABP, BS, montages, and unique wazas.
- `build_variants.py`: Synthesizes Alpha Boss (`_BOSS`), Predator (`_PREDATOR`), and Raid (`_RAID`) blueprints.
- `clone_actions.py`: Manages unique action blueprint inheritance.
- `clone_funnels.py`: Clones satellite minion funnel character blueprints.
- `clone_weapons.py`: Clones and compiles child partner weapon blueprints (flamethrowers, launchers, katanas).
- `patch_classes.py` / `patch_mesh.py`: Retargets class names, CDOs, SkeletalMeshes, and PhysicsAssets.
- `feature_manager/`: Modular AST mixins:
  - `manager.py`: Unified `BlueprintFeatureManager` interface.
  - `components.py`: Manages SCS_Node exports and `*_GEN_VARIABLE` component templates.
  - `cdo.py`: Manages `StaticCharacterParameterComponent`, `AIActionMap`, and `WazaActionDeclarationMap`.
  - `ich.py`: Manages `InheritableComponentHandler` records.
  - `bytecode.py`: Transfers Kismet bytecode and delegate bindings across blueprints.
  - `saddle.py`: Configures ride markers, speed collision, and mounted shooters.
  - `weapons.py`: Configures partner weapon components and raycast origins.
  - `funnel.py` & `funnel_builder.py`: Synthesizes companion satellite minion blueprints.
  - `weapon_builder.py`: Synthesizes partner weapon actor blueprints and 3-part montage clusters.
  - `shield.py`, `flight.py`, `evasion.py`, `utility.py`, `vfx.py`, `props.py`, `physics.py`: Modular subsystem mixins.

### `plugins/PalBakerEditorUtils/` (Unreal Engine C++ Module)
- `AnimScriptingLibrary.cpp` / `.h`: Exposes programmatic node wiring for AnimBlueprints (ModifyBone, SpringBone, LookAt, CopyBone, ModifyCurve), virtual bones, and sockets.
- `IKRetargetScriptingLibrary.cpp` / `.h`: Exposes IK Rig and IK Retargeter creation, chain mapping, and retarget pose offsets.

### `tests/` (Automated Test Suite)
- `run_all_tests.py`: Master test runner running sequential tests (`test_01` to `test_18`).
- `test_helper.py`: Settings sandbox (`empty`, `garbage`, `real` configurations) and editor process gating.