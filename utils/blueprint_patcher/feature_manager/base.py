# utils/blueprint_patcher/feature_manager/base.py

class BaseFeatureManager:
    """
    Base state manager for Unreal Engine 5.1 cooked Actor Blueprints.
    Maintains AST references and synchronizes package-level summary headers.
    """

    def __init__(self, data: dict):
        self.data = data
        self.exports = data.setdefault("Exports", [])
        self.imports = data.setdefault("Imports", [])
        self.class_export = self.exports[0] if self.exports else None

    def _append_export(self, export_node: dict) -> int:
        """
        Safely appends an export node to the Blueprint, ensuring that
        DependsMap and Generation counts remain perfectly synchronized.
        Returns the 1-based index of the newly added export.
        """
        self.exports.append(export_node)
        new_idx = len(self.exports)

        # Synchronize DependsMap array size
        depends_map = self.data.setdefault("DependsMap", [])
        while len(depends_map) < len(self.exports):
            depends_map.append([])

        # Synchronize Generation ExportCount
        generations = self.data.get("Generations", [])
        if generations and isinstance(generations, list):
            generations[0]["ExportCount"] = new_idx

        return new_idx