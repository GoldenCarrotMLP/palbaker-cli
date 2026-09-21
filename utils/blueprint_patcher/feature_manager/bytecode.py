# utils/blueprint_patcher/feature_manager/bytecode.py
import json
from utils.uasset_helper import sync_namemap

class BytecodeManagerMixin:
    """
    Manages Kismet VM EventGraph bytecode transference, delegate binding exports,
    function symbol maps, and StackNode re-pointing.
    """

    def transfer_uber_graph(self, src_data: dict, target_class_name: str):
        """
        Transfers Ubergraph functions, bytecode, and delegate bindings from a source Blueprint:
        1. Copies FunctionExports (ExecuteUbergraph and delegate signatures) and remaps references.
        2. Copies ComponentDelegateBinding export.
        3. Updates ClassExport (FuncMap, Children, UberGraphFunction, DynamicBindingObjects).
        4. Injects UberGraphFrame into LoadedProperties.
        """
        src_exports = src_data.get("Exports", [])
        src_imports = src_data.get("Imports", [])

        uber_func_src = next((e for e in src_exports if "ExecuteUbergraph" in str(e.get("ObjectName", ""))), None)
        delegate_func_src = next((e for e in src_exports if "BndEvt__" in str(e.get("ObjectName", ""))), None)
        binding_src = next((e for e in src_exports if e.get("ObjectName") == "ComponentDelegateBinding_0"), None)

        if not uber_func_src or not delegate_func_src:
            return

        import_map = self._build_import_map(src_imports)

        src_uber_idx = src_exports.index(uber_func_src) + 1
        src_delegate_idx = src_exports.index(delegate_func_src) + 1

        # 1. Ensure UberGraphFrame property exists in target LoadedProperties
        loaded_props = self.class_export.setdefault("LoadedProperties", [])
        if not any(isinstance(p, dict) and p.get("Name") == "UberGraphFrame" for p in loaded_props):
            coreuobj_pkg = self.find_or_add_import("/Script/CoreUObject", "Package", "/Script/CoreUObject", 0)
            struct_ptr_idx = self.find_or_add_import("PointerToUberGraphFrame", "ScriptStruct", "/Script/CoreUObject", coreuobj_pkg)
            loaded_props.insert(0, {
                "$type": "UAssetAPI.FieldTypes.FStructProperty, UAssetAPI",
                "Struct": struct_ptr_idx,
                "ArrayDim": "TArray",
                "ElementSize": 16,
                "PropertyFlags": "CPF_Transient, CPF_DuplicateTransient",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "StructProperty",
                "Name": "UberGraphFrame",
                "Flags": "RF_Public, RF_LoadCompleted",
                "MetaDataMap": None
            })

        new_delegate_func_name = f"BndEvt__{target_class_name}_PalPartnerSkillParameter_K2Node_ComponentBoundEvent_2_OnStop__DelegateSignature"
        new_uber_func_name = f"ExecuteUbergraph_{target_class_name}"

        # Resolve clean function and binding class imports in target
        coreuobj_pkg = self.find_or_add_import("/Script/CoreUObject", "Package", "/Script/CoreUObject", 0)
        func_class_idx = self.find_or_add_import("Function", "Class", "/Script/CoreUObject", coreuobj_pkg)
        func_default_idx = self.find_or_add_import("Default__Function", "Function", "/Script/CoreUObject", coreuobj_pkg)

        engine_pkg = self.find_or_add_import("/Script/Engine", "Package", "/Script/CoreUObject", 0)
        binding_class_idx = self.find_or_add_import("ComponentDelegateBinding", "Class", "/Script/CoreUObject", engine_pkg)
        binding_default_idx = self.find_or_add_import("Default__ComponentDelegateBinding", "ComponentDelegateBinding", "/Script/Engine", engine_pkg)

        # 2. Clone and append Delegate Binding export with clean dependencies
        binding_idx = None
        if binding_src:
            cloned_binding = json.loads(json.dumps(binding_src))
            self._remap_asset_indices(cloned_binding, import_map, src_uber_idx, -999, src_delegate_idx, -999)
            cloned_binding["OuterIndex"] = 1
            cloned_binding["ClassIndex"] = binding_class_idx
            cloned_binding["TemplateIndex"] = binding_default_idx
            cloned_binding["SerializationBeforeSerializationDependencies"] = []
            cloned_binding["CreateBeforeSerializationDependencies"] = []
            cloned_binding["SerializationBeforeCreateDependencies"] = [binding_class_idx, binding_default_idx]
            cloned_binding["CreateBeforeCreateDependencies"] = [1]

            binding_data = cloned_binding.get("Data")
            if isinstance(binding_data, list):
                for prop in binding_data:
                    if isinstance(prop, dict) and isinstance(prop.get("Value"), list):
                        for b_val in prop["Value"]:
                            if isinstance(b_val, dict) and isinstance(b_val.get("Value"), list):
                                for inner_p in b_val["Value"]:
                                    if isinstance(inner_p, dict) and inner_p.get("Name") == "FunctionNameToBind":
                                        inner_p["Value"] = new_delegate_func_name
            binding_idx = self._append_export(cloned_binding)

        # 3. Clone and append Ubergraph Function export with clean dependencies
        cloned_uber = json.loads(json.dumps(uber_func_src))
        cloned_uber["ObjectName"] = new_uber_func_name
        cloned_uber["OuterIndex"] = 1
        cloned_uber["ClassIndex"] = func_class_idx
        cloned_uber["TemplateIndex"] = func_default_idx
        cloned_uber["SerializationBeforeSerializationDependencies"] = []
        cloned_uber["CreateBeforeSerializationDependencies"] = []
        cloned_uber["SerializationBeforeCreateDependencies"] = []
        cloned_uber["CreateBeforeCreateDependencies"] = [1]
        new_uber_idx = self._append_export(cloned_uber)

        # 4. Clone and append Delegate Signature Function export with clean dependencies
        cloned_delegate = json.loads(json.dumps(delegate_func_src))
        cloned_delegate["ObjectName"] = new_delegate_func_name
        cloned_delegate["OuterIndex"] = 1
        cloned_delegate["ClassIndex"] = func_class_idx
        cloned_delegate["TemplateIndex"] = func_default_idx
        cloned_delegate["SerializationBeforeSerializationDependencies"] = []
        cloned_delegate["CreateBeforeSerializationDependencies"] = [new_uber_idx]
        cloned_delegate["SerializationBeforeCreateDependencies"] = []
        cloned_delegate["CreateBeforeCreateDependencies"] = [1]
        new_delegate_idx = self._append_export(cloned_delegate)

        # Remap bytecode internals now that target indices are finalized
        self._remap_asset_indices(cloned_uber, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)
        self._remap_asset_indices(cloned_delegate, import_map, src_uber_idx, new_uber_idx, src_delegate_idx, new_delegate_idx)

        # 5. Link in ClassExport
        func_map = self.class_export.setdefault("FuncMap", [])
        func_map.append([new_uber_func_name, new_uber_idx])
        func_map.append([new_delegate_func_name, new_delegate_idx])

        children = self.class_export.setdefault("Children", [])
        if new_delegate_idx not in children:
            children.append(new_delegate_idx)
        if new_uber_idx not in children:
            children.append(new_uber_idx)

        class_data = self.class_export.setdefault("Data", [])

        uber_prop = next((p for p in class_data if isinstance(p, dict) and p.get("Name") == "UberGraphFunction"), None)
        if uber_prop:
            uber_prop["Value"] = new_uber_idx
        else:
            class_data.append({
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": "UberGraphFunction",
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": new_uber_idx
            })

        if binding_idx:
            dyn_prop = next((p for p in class_data if isinstance(p, dict) and p.get("Name") == "DynamicBindingObjects"), None)
            if dyn_prop and isinstance(dyn_prop.get("Value"), list):
                dyn_prop["Value"].append({
                    "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                    "Name": str(len(dyn_prop["Value"])),
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": binding_idx
                })
            else:
                class_data.append({
                    "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                    "ArrayType": "ObjectProperty",
                    "Name": "DynamicBindingObjects",
                    "ArrayIndex": 0,
                    "PropertyGuid": None,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTypeName": None,
                    "PropertyTagExtensions": "NoExtension",
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                            "Name": "0",
                            "ArrayIndex": 0,
                            "PropertyGuid": None,
                            "IsZero": False,
                            "PropertyTagFlags": "None",
                            "PropertyTypeName": None,
                            "PropertyTagExtensions": "NoExtension",
                            "Value": binding_idx
                        }
                    ]
                })

        sync_namemap(self.data)