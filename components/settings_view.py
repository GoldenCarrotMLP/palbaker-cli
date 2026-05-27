import flet as ft
from utils.config import save_settings
from utils.plugin_manager import (
    check_project_requirements, 
    install_and_compile_plugin, 
    inject_missing_assets, 
    enable_remote_execution_settings,
    enable_cooking_settings,
    restart_unreal_editor
)
import threading

class SettingsView:
    def __init__(self, page: ft.Page, settings: dict, on_save_callback):
        self.main_page = page
        self.settings = settings
        self.on_save_callback = on_save_callback

        # Input Fields
        self.fmodel_output_field = ft.TextField(label="FModel Output Folder", value=str(settings.get("fmodel_output", "")), expand=True)
        self.ue_root_field = ft.TextField(label="Unreal Engine Root (e.g. UE_5.1)", value=str(settings.get("ue_root", "")), expand=True)
        self.uproject_field = ft.TextField(label="Palworld ModKit .uproject Path", value=str(settings.get("uproject", "")), expand=True)
        self.blender_field = ft.TextField(label="Blender Executable Path", value=str(settings.get("blender", "")), expand=True)
        self.palworld_exe_field = ft.TextField(label="Palworld.exe Path", value=str(settings.get("palworld_exe", "")), expand=True)

        # Preferences
        self.show_mapped_switch = ft.Switch(
            label="Show Mapped Names (e.g. Chillet instead of WeaselDragon)", 
            value=bool(settings.get("show_mapped", False))
        )

        view_controls: list[ft.Control] = []
        view_controls.extend([
            ft.Text("Application Paths", size=20, weight=ft.FontWeight.BOLD),
            ft.Row([self.fmodel_output_field, ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=self.pick_fmodel_folder)]),
            ft.Row([self.ue_root_field, ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=self.pick_ue_root)]),
            ft.Row([self.uproject_field, ft.IconButton(ft.Icons.FILE_OPEN, on_click=self.pick_uproject)]),
            ft.Row([self.blender_field, ft.IconButton(ft.Icons.FILE_OPEN, on_click=self.pick_blender_exe)]),
            ft.Row([self.palworld_exe_field, ft.IconButton(ft.Icons.FILE_OPEN, on_click=self.pick_palworld_exe)]),
            ft.Divider(),
            ft.Text("Preferences", size=20, weight=ft.FontWeight.BOLD),
            self.show_mapped_switch,
            ft.Divider(),
            ft.ElevatedButton("Save and Reload Mod List", icon=ft.Icons.SAVE, on_click=self.save_clicked, height=50)
        ])
        
        self.view = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=20,
            controls=view_controls
        )

    async def pick_fmodel_folder(self, e):
        picker = ft.FilePicker()
        result = await picker.get_directory_path()
        if result:
            self.fmodel_output_field.value = str(result)
            self.fmodel_output_field.update()

    async def pick_ue_root(self, e):
        picker = ft.FilePicker()
        result = await picker.get_directory_path()
        if result:
            self.ue_root_field.value = str(result)
            self.ue_root_field.update()

    async def pick_uproject(self, e):
        picker = ft.FilePicker()
        result = await picker.pick_files(allow_multiple=False, allowed_extensions=["uproject"])
        if result and result[0].path:
            self.uproject_field.value = str(result[0].path)
            self.uproject_field.update()

    async def pick_blender_exe(self, e):
        picker = ft.FilePicker()
        result = await picker.pick_files(allow_multiple=False)
        if result and result[0].path:
            self.blender_field.value = str(result[0].path)
            self.blender_field.update()

    async def pick_palworld_exe(self, e):
        picker = ft.FilePicker()
        result = await picker.pick_files(allow_multiple=False, allowed_extensions=["exe"])
        if result and result[0].path:
            self.palworld_exe_field.value = str(result[0].path)
            self.palworld_exe_field.update()

    def on_picker_result(self, e, field: ft.TextField):
        if e.path:
            field.value = e.path
        elif e.files:
            field.value = e.files[0].path
        field.update()

    def save_clicked(self, e):
        self.settings.update({
            "fmodel_output": str(self.fmodel_output_field.value),
            "ue_root": str(self.ue_root_field.value),
            "uproject": str(self.uproject_field.value),
            "blender": str(self.blender_field.value),
            "palworld_exe": str(self.palworld_exe_field.value),
            "show_mapped": bool(self.show_mapped_switch.value)
        })
        save_settings(self.settings)

        # Run verification asynchronously so it doesn't freeze the Flet UI
        def verify_and_build():
            # Synchronous dialog helper using events
            def ask_user_modal(title, content_control):
                result = [False]
                event = threading.Event()

                def on_yes(e):
                    result[0] = True
                    self.main_page.pop_dialog()
                    event.set()

                def on_no(e):
                    result[0] = False
                    self.main_page.pop_dialog()
                    event.set()

                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text(title),
                    content=content_control,
                    actions=[
                        ft.TextButton("Cancel", on_click=on_no),
                        ft.TextButton("Yes, Install", on_click=on_yes, style=ft.ButtonStyle(color=ft.Colors.BLUE)),
                    ]
                )
                self.main_page.show_dialog(dlg)
                event.wait()
                return result[0]

            reqs = check_project_requirements(self.settings["ue_root"], self.settings["uproject"])

            if reqs.get("error"):
                self.main_page.overlay.append(ft.SnackBar(ft.Text(reqs["error"], color=ft.Colors.RED_400), open=True))
                self.main_page.update()
                self.on_save_callback()
                return

            # --- 1. PLUGIN MODAL ---
            if reqs["needs_plugin_sync"] or reqs["needs_compile"]:
                content = ft.Column([
                    ft.Text("PalBaker requires a custom C++ Editor Utility Plugin to automatically generate Animation Blueprints via Python."),
                    ft.Text("The plugin is missing or outdated in your active Unreal Engine project.", color=ft.Colors.ORANGE_400),
                    ft.Text("Would you like to install and bind it to your ModKit now?", weight=ft.FontWeight.BOLD)
                ], tight=True)

                if ask_user_modal("Required Plugin Missing", content):
                    self.main_page.overlay.append(ft.SnackBar(ft.Text("Installing and verifying C++ plugin... (This may take a moment)"), open=True))
                    self.main_page.update()
                    
                    success, msg = install_and_compile_plugin(self.settings["ue_root"], self.settings["uproject"])
                    color = ft.Colors.GREEN_400 if success else ft.Colors.RED_400
                    self.main_page.overlay.append(ft.SnackBar(ft.Text(msg, color=color), open=True))
                    self.main_page.update()

            # --- 2. ASSETS MODAL ---
            missing_assets = reqs.get("missing_assets", [])
            if len(missing_assets) > 0:
                files_controls = [ft.Text(f" • {f}", size=12, color=ft.Colors.WHITE70) for f in missing_assets]
                files_list = ft.ListView(
                    controls=files_controls,
                    height=150,
                    spacing=2,
                    padding=10
                )
                
                content = ft.Column([
                    ft.Text("The following core framework assets are missing from your ModKit's Content directory:"),
                    ft.Container(
                        content=files_list,
                        border=ft.Border.all(1, ft.Colors.WHITE24),
                        border_radius=5,
                    ),
                    ft.Text("PalBaker requires these to cleanly bind Material Instances.\nWould you like to inject them into your project automatically?", weight=ft.FontWeight.BOLD)
                ], tight=True)

                if ask_user_modal("Missing Core Assets", content):
                    success, msg = inject_missing_assets(self.settings["uproject"])
                    color = ft.Colors.GREEN_400 if success else ft.Colors.RED_400
                    self.main_page.overlay.append(ft.SnackBar(ft.Text(msg, color=color), open=True))
                    self.main_page.update()

            # --- 3. REMOTE EXECUTION & COOKING CONFIG MODAL (CONSOLIDATED) ---
            needs_remote_exec = reqs.get("needs_remote_exec_enable")
            needs_cooking_setup = reqs.get("needs_cooking_setup")

            if needs_remote_exec or needs_cooking_setup:
                reasons = []
                if needs_remote_exec:
                    reasons.append(" • Enable 'Python Remote Execution' (allows Python script orchestration)")
                if needs_cooking_setup:
                    reasons.append(" • Disable 'I/O Store' & 'Material Shader Sharing' (forces compilation to loose .uasset files)")

                reasons_str = "\n".join(reasons)
                content = ft.Column([
                    ft.Text("PalBaker needs to apply the following required configuration changes to your project's .ini files:"),
                    ft.Text(reasons_str, color=ft.Colors.ORANGE_400),
                    ft.Text("Please ensure your work inside Unreal is saved before proceeding! Clicking 'Yes, Install' will write these settings and AUTOMATICALLY restart your Unreal Editor project.", weight=ft.FontWeight.BOLD)
                ], tight=True)

                if ask_user_modal("Project Configurations Required", content):
                    # Write settings
                    if needs_remote_exec:
                        enable_remote_execution_settings(self.settings["uproject"])
                    if needs_cooking_setup:
                        enable_cooking_settings(self.settings["uproject"])
                        
                    self.main_page.overlay.append(ft.SnackBar(ft.Text("Configurations successfully written. Restarting Unreal Editor..."), open=True))
                    self.main_page.update()
                    
                    # Restart Editor (Applies both settings simultaneously)
                    restart_success, restart_msg = restart_unreal_editor(self.settings["ue_root"], self.settings["uproject"])
                    color = ft.Colors.GREEN_400 if restart_success else ft.Colors.RED_400
                    self.main_page.overlay.append(ft.SnackBar(ft.Text(restart_msg, color=color), open=True))
                    self.main_page.update()

            self.main_page.overlay.append(ft.SnackBar(ft.Text("Settings saved and verified!"), open=True))
            self.main_page.update()
            
            self.on_save_callback()

        threading.Thread(target=verify_and_build, daemon=True).start()