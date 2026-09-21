# utils/blueprint_patcher/feature_manager/imports.py

class ImportManagerMixin:
    """
    Manages package import tables, two-tier class hierarchies,
    and relative index translation across foreign Blueprints.
    """

    def find_or_add_import(
        self,
        object_name: str,
        class_name: str,
        class_package: str = "/Script/Engine",
        outer_index: int = 0
    ) -> int:
        """
        Finds an existing import matching object_name and outer_index, or appends a new one.
        Returns the negative 1-based import index.
        """
        for idx, imp in enumerate(self.imports):
            if imp.get("ObjectName") == object_name and imp.get("OuterIndex") == outer_index:
                return -(idx + 1)

        new_import = {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": object_name,
            "OuterIndex": outer_index,
            "ClassPackage": class_package,
            "ClassName": class_name,
            "PackageName": None,
            "bImportOptional": False
        }
        self.imports.append(new_import)
        return -len(self.imports)

    def ensure_import_chain(
        self,
        package_path: str,
        class_name: str,
        class_type: str | None = None
    ) -> int:
        """
        Resolves or creates the standard two-level package -> class import hierarchy.
        Automatically detects native C++ classes under /Script/ to preserve proper type signatures.
        """
        clean_pkg = package_path.replace("\\", "/").strip()
        is_native = clean_pkg.startswith("/Script/")

        resolved_class_type = class_type or ("Class" if is_native else "BlueprintGeneratedClass")
        resolved_class_pkg = "/Script/CoreUObject" if is_native else "/Script/Engine"

        pkg_idx = self.find_or_add_import(clean_pkg, "Package", "/Script/CoreUObject", 0)
        class_idx = self.find_or_add_import(class_name, resolved_class_type, resolved_class_pkg, pkg_idx)
        return class_idx

    def _build_import_map(self, src_imports: list) -> dict:
        """Recursively builds a translation map matching all source imports to target imports."""
        import_map = {}

        def resolve_src_import(src_idx: int) -> int:
            if src_idx >= 0:
                return src_idx
            if src_idx in import_map:
                return import_map[src_idx]

            src_imp = src_imports[-src_idx - 1]
            src_outer = src_imp.get("OuterIndex", 0)

            target_outer = resolve_src_import(src_outer) if src_outer < 0 else 0

            target_idx = self.find_or_add_import(
                object_name=src_imp.get("ObjectName"),
                class_name=src_imp.get("ClassName"),
                class_package=src_imp.get("ClassPackage"),
                outer_index=target_outer
            )
            import_map[src_idx] = target_idx
            return target_idx

        for i in range(len(src_imports)):
            resolve_src_import(-(i + 1))

        return import_map

    def _remap_asset_indices(
        self,
        node,
        import_map: dict,
        src_uber_idx: int,
        new_uber_idx: int,
        src_delegate_idx: int,
        new_delegate_idx: int
    ):
        """Recursively remaps bytecode property pointers and stack nodes to the new target indices."""
        def get_new_idx(idx):
            if idx < 0:
                return import_map.get(idx, idx)
            elif idx == src_uber_idx:
                return new_uber_idx
            elif idx == src_delegate_idx:
                return new_delegate_idx
            return idx

        if isinstance(node, dict):
            for key in ["ClassIndex", "TemplateIndex", "SuperIndex", "OuterIndex", "PropertyClass", "Struct", "StackNode", "Object"]:
                if key in node and isinstance(node[key], int) and node[key] != 0:
                    node[key] = get_new_idx(node[key])

            if node.get("$type", "").endswith("ObjectPropertyData, UAssetAPI") and "Value" in node and isinstance(node["Value"], int) and node["Value"] != 0:
                node["Value"] = get_new_idx(node["Value"])

            if "ResolvedOwner" in node and isinstance(node["ResolvedOwner"], int) and node["ResolvedOwner"] != 0:
                node["ResolvedOwner"] = get_new_idx(node["ResolvedOwner"])

            for v in node.values():
                self._remap_asset_indices(v, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)

        elif isinstance(node, list):
            for item in node:
                self._remap_asset_indices(item, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)