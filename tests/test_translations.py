"""Translation coverage tests for the Pollen Levels integration."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

# 🔧 Adjust this per repository
INTEGRATION_DOMAIN = "pollenlevels"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = PROJECT_ROOT / "custom_components" / INTEGRATION_DOMAIN
TRANSLATIONS_DIR = COMPONENT_DIR / "translations"
CONFIG_FLOW_PATH = COMPONENT_DIR / "config_flow.py"
CONST_PATH = COMPONENT_DIR / "const.py"


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
                f"{translation_path.name}: "
                f"missing {sorted(missing)} extra {sorted(extra)}"
            )
    assert not problems, "Translation keys mismatch: " + "; ".join(problems)


def test_config_flow_translation_keys_present() -> None:
    """Ensure config/options flow keys referenced in code exist in English JSON."""

    english = _flatten_keys(_load_translation(TRANSLATIONS_DIR / "en.json"))
    flow_keys = _extract_config_flow_keys()
    missing = flow_keys - english
    assert not missing, f"Missing config_flow translation keys: {sorted(missing)}"


def _extract_constant_assignments(tree: ast.AST) -> dict[str, str]:
    """Collect string literal assignments from an AST.

    Only handles simple cases like:
        NAME = "literal"
    """

    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target_name: str | None = None
            if isinstance(node, ast.Assign):
                if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                    continue
                target_name = node.targets[0].id
                value = node.value
            else:
                if not isinstance(node.target, ast.Name):
                    continue
                target_name = node.target.id
                value = node.value
            if (
                target_name
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                constants[target_name] = value.value
    return constants


def _resolve_name(name: str, mapping: dict[str, str]) -> str | None:
    """Resolve a variable name to its string value if known."""

    return mapping.get(name)


def _fields_from_schema_call(call: ast.Call, mapping: dict[str, str]) -> set[str]:
    """Extract field keys from a vol.Schema(...) call.

    Looks for patterns like:
        vol.Schema({vol.Required(CONF_USERNAME): str, ...})
    """

    if not call.args:
        return set()
    arg = call.args[0]
    if not isinstance(arg, ast.Dict):
        return set()

    fields: set[str] = set()
    for key in arg.keys:
        if not isinstance(key, ast.Call):
            continue
        if not isinstance(key.func, ast.Attribute):
            continue
        if key.func.attr not in {"Required", "Optional"}:
            continue
        if not key.args:
            continue
        selector = key.args[0]
        if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
            fields.add(selector.value)
        elif isinstance(selector, ast.Name):
            resolved = _resolve_name(selector.id, mapping)
            if resolved:
                fields.add(resolved)
    return fields


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
            returns = [
                child for child in ast.walk(node) if isinstance(child, ast.Return)
            ]
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
                if kw.arg == "errors" and isinstance(kw.value, ast.Dict):
                    for err_value in kw.value.values:
                        if isinstance(err_value, ast.Constant) and isinstance(
                            err_value.value, str
                        ):
                            keys.add(f"{prefix}.error.{err_value.value}")

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
