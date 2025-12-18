"""Translation coverage tests for the Pollen Levels integration.

These tests ensure:
- All locale files have the exact same keyset as en.json (en.json is the source of truth).
- Translation keys referenced by config_flow.py (config + options flows) exist in en.json.
- Translation keys referenced by sensor.py via entity/device translation_key exist in en.json.

The config_flow extraction uses an AST walker. If config_flow.py changes structure in
unexpected ways, the helpers should fail loudly so we don't silently lose coverage.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

# 🔧 Adjust this per repository
INTEGRATION_DOMAIN = "pollenlevels"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = PROJECT_ROOT / "custom_components" / INTEGRATION_DOMAIN
TRANSLATIONS_DIR = COMPONENT_DIR / "translations"
CONFIG_FLOW_PATH = COMPONENT_DIR / "config_flow.py"
CONST_PATH = COMPONENT_DIR / "const.py"
SENSOR_PATH = COMPONENT_DIR / "sensor.py"


def _fail_unexpected_ast(context: str) -> None:
    """Fail with a consistent, actionable message for unsupported AST shapes."""

    pytest.fail(
        "Unexpected AST layout while extracting translation keys from "
        f"config_flow.py ({context}); please update the helper in test_translations.py",
    )


def _flatten_keys(data: dict[str, Any], prefix: str = "") -> set[str]:
    """Flatten nested dict keys into dotted paths."""

    keys: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.update(_flatten_keys(value, path))
        else:
            keys.add(path)
    return keys


def _load_translation(path: Path) -> dict[str, Any]:
    """Load a translation JSON file."""

    if not path.is_file():
        raise AssertionError(f"Missing translation file: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _extract_sensor_translation_key_usage() -> tuple[set[str], set[str]]:
    """Extract translation keys referenced by sensor entities and devices.

    Entity keys:
      - _attr_translation_key = "<key>"  -> entity.sensor.<key>.name

    Device keys:
      - "translation_key": "<key>" in a device_info dict literal
      - values in a mapping like: translation_keys = {"type": "types", ...}
      - default used in translation_keys.get(..., "<default>")

    This stays intentionally narrow; unsupported AST changes should fail loudly.
    """

    if not SENSOR_PATH.is_file():
        raise AssertionError(f"Missing sensor.py at {SENSOR_PATH}")

    tree = ast.parse(SENSOR_PATH.read_text(encoding="utf-8"))

    entity_keys: set[str] = set()
    device_keys: set[str] = set()

    # 1) Entity translation keys: _attr_translation_key = "<key>"
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                continue
            target = node.targets[0]
            value = node.value
        else:
            target = node.target
            value = node.value

        if (
            isinstance(target, ast.Name)
            and target.id == "_attr_translation_key"
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            entity_keys.add(value.value)

    # 2) Device translation keys from explicit dict literals: {"translation_key": "<key>"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values, strict=False):
            if (
                isinstance(k, ast.Constant)
                and k.value == "translation_key"
                and isinstance(v, ast.Constant)
                and isinstance(v.value, str)
            ):
                device_keys.add(v.value)

    # 3) Device translation keys from a mapping: translation_keys = {...}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        if not (
            isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "translation_keys"
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            _fail_unexpected_ast("sensor.py translation_keys assignment is not a dict")
        for v in node.value.values:
            if not (isinstance(v, ast.Constant) and isinstance(v.value, str)):
                _fail_unexpected_ast(
                    "sensor.py translation_keys dict contains non-string values"
                )
            device_keys.add(v.value)

    # 4) Default device translation key: translation_keys.get(..., "<default>")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "get"):
            continue
        if not (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "translation_keys"
        ):
            continue
        if len(node.args) >= 2:
            default = node.args[1]
            if isinstance(default, ast.Constant) and isinstance(default.value, str):
                device_keys.add(default.value)
            else:
                _fail_unexpected_ast(
                    "sensor.py translation_keys.get default is not a string literal"
                )

    return entity_keys, device_keys


def test_translations_match_english_keyset() -> None:
    """Verify all locale files mirror the English translation keyset."""

    en_path = TRANSLATIONS_DIR / "en.json"
    english_keys = _flatten_keys(_load_translation(en_path))

    problems: list[str] = []
    for translation_path in TRANSLATIONS_DIR.glob("*.json"):
        if translation_path.name == "en.json":
            continue
        locale_keys = _flatten_keys(_load_translation(translation_path))
        missing = english_keys - locale_keys
        extra = locale_keys - english_keys
        if missing or extra:
            problems.append(
                f"{translation_path.name}: missing {sorted(missing)} extra {sorted(extra)}"
            )

    assert not problems, "Translation keys mismatch: " + "; ".join(problems)


def test_config_flow_translation_keys_present() -> None:
    """Ensure config/options flow keys referenced in code exist in English JSON."""

    english = _flatten_keys(_load_translation(TRANSLATIONS_DIR / "en.json"))
    flow_keys = _extract_config_flow_keys()
    missing = flow_keys - english
    assert not missing, f"Missing config_flow translation keys: {sorted(missing)}"


def test_config_flow_extractor_includes_helper_error_keys() -> None:
    """Regression: helper-propagated errors must be detected by AST extraction."""

    keys = _extract_config_flow_keys()
    assert "config.error.invalid_update_interval" in keys
    assert "options.error.invalid_update_interval" in keys
    assert "config.error.invalid_forecast_days" in keys
    assert "options.error.invalid_forecast_days" in keys


def test_sensor_translation_keys_present() -> None:
    """Ensure entity/device translation keys referenced by sensor.py exist in en.json."""

    english = _flatten_keys(_load_translation(TRANSLATIONS_DIR / "en.json"))
    entity_keys, device_keys = _extract_sensor_translation_key_usage()

    assert entity_keys, "No _attr_translation_key values found in sensor.py"
    assert device_keys, "No device translation_key values found in sensor.py"

    missing: list[str] = []
    for key in sorted(entity_keys):
        tkey = f"entity.sensor.{key}.name"
        if tkey not in english:
            missing.append(tkey)

    for key in sorted(device_keys):
        tkey = f"device.{key}.name"
        if tkey not in english:
            missing.append(tkey)

    assert not missing, "Missing sensor/device translation keys in en.json: " + ", ".join(
        missing
    )


def _extract_constant_assignments(tree: ast.AST) -> dict[str, str]:
    """Collect string literal assignments from an AST.

    Only handles simple cases like:
        NAME = "literal"
    """

    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        target = None
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1:
                target = node.targets[0]
        else:  # AnnAssign
            target = node.target

        value = node.value
        if (
            isinstance(target, ast.Name)
            and value is not None
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            constants[target.id] = value.value
    return constants


def _resolve_name(name: str, mapping: dict[str, str]) -> str | None:
    """Resolve a variable name to its string value if known."""

    return mapping.get(name)


def _fields_from_section_value(value: ast.AST, mapping: dict[str, str]) -> set[str]:
    """Extract fields from a section(...) value."""

    if isinstance(value, ast.Dict):
        return _fields_from_schema_dict(value, mapping)
    if isinstance(value, ast.Call):
        if isinstance(value.func, ast.Attribute) and value.func.attr == "Schema":
            return _fields_from_schema_call(value, mapping)
    _fail_unexpected_ast("unexpected section value AST")
    return set()


def _fields_from_schema_dict(
    schema_dict: ast.Dict, mapping: dict[str, str]
) -> set[str]:
    """Extract field keys from an AST dict representing a schema."""

    fields: set[str] = set()
    for key_node, value_node in zip(schema_dict.keys, schema_dict.values, strict=False):
        if not isinstance(key_node, ast.Call):
            _fail_unexpected_ast("schema key wrapper")

        if isinstance(key_node.func, ast.Attribute) and key_node.func.attr in {
            "Required",
            "Optional",
        }:
            if not key_node.args:
                _fail_unexpected_ast("schema key args")
            selector = key_node.args[0]
            if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
                fields.add(selector.value)
            elif isinstance(selector, ast.Name):
                resolved = _resolve_name(selector.id, mapping)
                if resolved:
                    fields.add(resolved)
                else:
                    _fail_unexpected_ast(f"unmapped selector {selector.id}")
            else:
                _fail_unexpected_ast("selector type")
        elif isinstance(key_node.func, ast.Name) and key_node.func.id == "section":
            fields.update(_fields_from_section_value(value_node, mapping))
        else:
            _fail_unexpected_ast("unexpected schema call wrapper")
    return fields


def _fields_from_schema_call(call: ast.Call, mapping: dict[str, str]) -> set[str]:
    """Extract field keys from a vol.Schema(...) call.

    Looks for patterns like:
        vol.Schema({vol.Required(CONF_USERNAME): str, ...})
    """

    if not call.args or not isinstance(call.args[0], ast.Dict):
        _fail_unexpected_ast("schema call arguments")

    return _fields_from_schema_dict(call.args[0], mapping)


def _extract_schema_fields(
    tree: ast.AST, mapping: dict[str, str]
) -> dict[str, set[str]]:
    """Map schema helper names to their field keys.

    Collects:
    - Functions like _user_schema / _options_schema returning vol.Schema(...)
    - Top-level assignments like USER_SCHEMA = vol.Schema(...)
    """

    fields: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {
            "_user_schema",
            "_options_schema",
        }:
            returns = [child for child in ast.walk(node) if isinstance(child, ast.Return)]
            for ret in returns:
                if isinstance(ret.value, ast.Call):
                    fields.setdefault(node.name, set()).update(
                        _fields_from_schema_call(ret.value, mapping)
                    )

        if isinstance(node, ast.Assign):
            if (
                isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "Schema"
            ):
                name = node.targets[0].id
                fields.setdefault(name, set()).update(
                    _fields_from_schema_call(node.value, mapping)
                )
    return fields


def _extract_helper_error_keys(tree: ast.AST) -> dict[str, set[str]]:
    """Discover module-level helper functions that emit error keys via _parse_int_option(..., error_key=...)."""

    helpers: dict[str, set[str]] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.FunctionDef):
            continue

        emitted: set[str] = set()
        for call in ast.walk(node):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
                continue
            if call.func.id != "_parse_int_option":
                continue
            for kw in call.keywords:
                if kw.arg != "error_key":
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    emitted.add(kw.value.value)
                else:
                    _fail_unexpected_ast(
                        f"error_key in {node.name} is not a string literal"
                    )
        if emitted:
            helpers[node.name] = emitted
    return helpers


def _is_options_flow_class(name: str) -> bool:
    """Heuristic to decide if a class represents an options flow.

    Works for names like:
        AirzoneOptionsFlow
        PollenLevelsOptionsFlowHandler
        MyIntegrationOptionsFlow
    """

    lower = name.lower()
    return "optionsflow" in lower or "options_flow" in lower


def _extract_config_flow_keys() -> set[str]:
    """Parse config_flow.py to derive translation keys used in flows.

    This covers:
    - config.step.<step_id>.title
    - config.step.<step_id>.description
    - config.step.<step_id>.data.<field>
    - config.error.<code>
    - config.abort.<reason>
    And the equivalent options.* keys for options flows.
    """

    if not CONFIG_FLOW_PATH.is_file():
        raise AssertionError(f"Missing config_flow.py at {CONFIG_FLOW_PATH}")

    config_tree = ast.parse(CONFIG_FLOW_PATH.read_text(encoding="utf-8"))
    const_tree: ast.AST | None = None
    if CONST_PATH.is_file():
        const_tree = ast.parse(CONST_PATH.read_text(encoding="utf-8"))

    manual_mapping: dict[str, str] = {
        "CONF_USERNAME": "username",
        "CONF_PASSWORD": "password",
        "CONF_API_KEY": "api_key",
        "CONF_LATITUDE": "latitude",
        "CONF_LONGITUDE": "longitude",
        "CONF_LANGUAGE": "language",
        "CONF_SCAN_INTERVAL": "scan_interval",
    }

    mapping: dict[str, str] = dict(manual_mapping)
    if const_tree is not None:
        mapping.update(_extract_constant_assignments(const_tree))
    mapping.update(_extract_constant_assignments(config_tree))

    schema_fields = _extract_schema_fields(config_tree, mapping)

    # Helper functions can return error keys indirectly (e.g., interval_error/days_error).
    helper_error_keys = _extract_helper_error_keys(config_tree)

    language_error_returns: set[str] = set()

    class _LanguageErrorVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name != "_language_error_to_form_key":
                return
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Return)
                    and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)
                ):
                    language_error_returns.add(child.value.value)

    _LanguageErrorVisitor().visit(config_tree)

    def _extract_error_values(value: ast.AST) -> set[str]:
        values: set[str] = set()
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.add(value.value)
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "_language_error_to_form_key"
        ):
            values.update(language_error_returns)
        return values

    def _extract_error_key_kw(call: ast.Call) -> str | None:
        for kw in call.keywords:
            if kw.arg != "error_key":
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
            _fail_unexpected_ast("error_key kwarg is not a string literal")
        return None

    class _ScopedErrorsVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str | None] = []
            self.by_class: dict[str | None, set[str]] = {}

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            for target in node.targets:
                self._record_errors(target, node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
            self._record_errors(node.target, node.value)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            # Collect helper-propagated errors used in a class scope, e.g.:
            #   interval_value, interval_error = _parse_update_interval(...); errors[...] = interval_error
            class_name = self.class_stack[-1] if self.class_stack else None
            if class_name is None:
                self.generic_visit(node)
                return

            if isinstance(node.func, ast.Name):
                if node.func.id == "_parse_int_option":
                    err = _extract_error_key_kw(node)
                    if err:
                        self.by_class.setdefault(class_name, set()).add(err)
                elif node.func.id in helper_error_keys:
                    self.by_class.setdefault(class_name, set()).update(
                        helper_error_keys[node.func.id]
                    )

            self.generic_visit(node)

        def _record_errors(self, target: ast.AST, value: ast.AST | None) -> None:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "errors"
                and value is not None
            ):
                class_name = self.class_stack[-1] if self.class_stack else None
                self.by_class.setdefault(class_name, set()).update(
                    _extract_error_values(value)
                )

    scoped_errors = _ScopedErrorsVisitor()
    scoped_errors.visit(config_tree)

    keys: set[str] = set()

    class FlowVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []
            self.local_schema_vars: dict[str, set[str]] = dict(schema_fields)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            if (
                isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "Schema"
            ):
                name = node.targets[0].id
                self.local_schema_vars[name] = _fields_from_schema_call(
                    node.value, mapping
                )
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            prefix = "config"
            if self.class_stack and _is_options_flow_class(self.class_stack[-1]):
                prefix = "options"

            func_attr: str | None = None
            if isinstance(node.func, ast.Attribute):
                func_attr = node.func.attr

            if func_attr == "async_show_form":
                self._handle_show_form(node, prefix)
            if func_attr == "async_abort":
                self._handle_abort(node, prefix)

            self.generic_visit(node)

        def _handle_show_form(self, node: ast.Call, prefix: str) -> None:
            step_id: str | None = None
            schema_name: str | None = None
            inline_schema_fields: set[str] = set()

            for kw in node.keywords:
                if kw.arg == "step_id" and isinstance(kw.value, ast.Constant):
                    step_id = str(kw.value.value)
                if kw.arg == "data_schema":
                    if isinstance(kw.value, ast.Name):
                        schema_name = kw.value.id
                    elif isinstance(kw.value, ast.Call):
                        if (
                            isinstance(kw.value.func, ast.Attribute)
                            and kw.value.func.attr == "Schema"
                        ):
                            inline_schema_fields.update(
                                _fields_from_schema_call(kw.value, mapping)
                            )
                if kw.arg == "errors":
                    if isinstance(kw.value, ast.Dict):
                        for err_value in kw.value.values:
                            err_key: str | None = None
                            if isinstance(err_value, ast.Constant) and isinstance(
                                err_value.value, str
                            ):
                                err_key = err_value.value
                            elif isinstance(err_value, ast.Name):
                                err_key = _resolve_name(err_value.id, mapping)
                            if err_key:
                                keys.add(f"{prefix}.error.{err_key}")
                    elif isinstance(kw.value, ast.Name):
                        if kw.value.id == "errors":
                            class_name = (
                                self.class_stack[-1] if self.class_stack else None
                            )
                            for err_key in scoped_errors.by_class.get(
                                class_name, set()
                            ):
                                keys.add(f"{prefix}.error.{err_key}")
                        else:
                            resolved = _resolve_name(kw.value.id, mapping)
                            if resolved:
                                keys.add(f"{prefix}.error.{resolved}")

            if not step_id:
                return

            keys.add(f"{prefix}.step.{step_id}.title")
            keys.add(f"{prefix}.step.{step_id}.description")

            if schema_name and schema_name in self.local_schema_vars:
                for field in self.local_schema_vars[schema_name]:
                    keys.add(f"{prefix}.step.{step_id}.data.{field}")

            for field in inline_schema_fields:
                keys.add(f"{prefix}.step.{step_id}.data.{field}")

        def _handle_abort(self, node: ast.Call, prefix: str) -> None:
            for kw in node.keywords:
                if (
                    kw.arg == "reason"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    keys.add(f"{prefix}.abort.{kw.value.value}")

    FlowVisitor().visit(config_tree)

    return keys

