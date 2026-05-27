# PalBaker (Palworld Mod Manager)

A dedicated, automated modding environment for Palworld that handles the pipeline from raw FModel extracts to a fully cooked and packed `_P.pak` file. It orchestrates Blender, Unreal Engine 5.1, and UnrealPak using a Flet-based UI.

## Features
* **State Tracking:** Detects whether a mod is in a raw state, has active source files (.blend), contains compiled Unreal Engine assets, or has been manually modified inside the Unreal Editor. Warns users before overwriting manual changes with exact file names.
* **Context-Aware Pipeline:** Offers specific actions based on the mod's current state (Push to Unreal, Cook & Pack, or Full Pipeline).
* **Headless Blender Integration:** Automatically converts `.blend` files to `.fbx` with forced bone scaling, rotation, and hierarchy parameters compatible with Palworld's physics limits.
* **Automated Advanced Rigging (Jiggle & Offset Bones):** Extracts structural offsets and physics configurations directly from Blender's pose mode. Natively translates Blender's right-handed local space into Unreal's left-handed parent bone space to seamlessly preserve animations while altering character proportions or adding ragdoll spring physics.
* **Dynamic C++ Plugin Generation:** Automatically injects and headlessly compiles a custom Unreal Editor C++ module (`PalBakerEditorUtils`) using your MSVC toolchain, allowing the script to programmatically build and wire complex `AnimGraph` node trees.
* **Intelligent Animation Blueprint Binding:** Generates an Animation Blueprint from scratch if one doesn't exist, wires the custom physics/offset nodes, compiles it, and automatically binds the generated `_C` class to the Skeletal Mesh's Post-Process slot.
* **Compiler Diagnostics & Auto-Fix:** Includes a built-in diagnostic utility to scan your system for compliant MSVC v143 (14.3x) compiler toolsets and automatically repairs corrupted or misconfigured `BuildConfiguration.xml` files required for UE 5.1 building.
* **Unreal Engine Remote Execution:** Injects asset serialization commands directly into a running Unreal Editor instance, avoiding engine cold-boot times.
* **Targeted Micro-Cooking:** Temporarily overrides `DefaultGame.ini` to restrict the Unreal Cooker to the specific mod folder and skeleton directory, reducing cook times from minutes to seconds.
* **Safe Packaging:** Automatically filters out generated skeletons and physics assets during the packaging phase to prevent in-game ragdoll glitches.
* **Real-Time Progress Tracking:** Parses Python subprocess stdout streams asynchronously to provide a real-time UI progress bar and status console, heavily optimized to prevent WebSocket bottlenecking.

## Prerequisites
1. Python 3.10+
2. `flet` (v0.85.0+)
3. Unreal Engine 5.1
4. Visual Studio 2022 (with MSVC v143 - C++ Desktop Development Workload)
5. Palworld ModKit (`.uproject`)
6. Blender
7. FModel (for initial asset extraction)

## Setup
1. Clone or place this repository in a dedicated directory.
2. Ensure the `pal_names_map.json` file is located in the root of the project.
3. Install dependencies: `pip install flet`
4. Run the manager: `python manager.py`
5. Navigate to the **Settings** tab and configure the executable and directory paths.
6. Click **Save and Reload Mod List**. PalBaker will automatically verify your compiler and generate/compile its required C++ helper plugin inside your ModKit.

## Usage
* Enable **Remote Execution** in your Unreal Engine Project Settings -> Python.
* Keep the Unreal Editor open.
* To create a custom skeleton or jiggle bones, simply rename bones in Blender to end with `_jiggle` or `_phy` and adjust their pose.
* Use the UI to select a mod and execute the relevant build pipeline phase.