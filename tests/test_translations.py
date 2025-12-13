"""Translation coverage tests for the Pollen Levels integration.

These tests parse ``config_flow.py`` with a simple AST walker to ensure every
translation key used in the config/options flows exists in each locale file.
If the flow code changes structure, update the helper below rather than
changing the assertions to keep the guarantees intact.
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


def _fields_from_schema_call(call: ast.Call, mapping: dict[str, str]) -> set[str]:
    """Extract field keys from a vol.Schema(...) call.

    Looks for patterns like:
        vol.Schema({vol.Required(CONF_USERNAME): str, ...})
    """

    if not call.args or not isinstance(call.args[0], ast.Dict):
        _fail_unexpected_ast("schema call arguments")
    arg = call.args[0]

    fields: set[str] = set()
    for key, value in zip(arg.keys, arg.values, strict=False):
        if isinstance(key, ast.Call) and isinstance(key.func, ast.Name):
            # section("...", SectionConfig(...)): {vol.Optional(...): ...}
            if key.func.id == "section":
                if not isinstance(value, ast.Dict):
                    _fail_unexpected_ast("section value")
                for nested_key in value.keys:
                    if not isinstance(nested_key, ast.Call) or not isinstance(
                        nested_key.func, ast.Attribute
                    ):
                        _fail_unexpected_ast("schema key wrapper")
                    if nested_key.func.attr not in {"Required", "Optional"}:
                        _fail_unexpected_ast(
                            f"unexpected schema call {nested_key.func.attr}"
                        )
                    if not nested_key.args:
                        _fail_unexpected_ast("schema key args")
                    selector = nested_key.args[0]
                    if isinstance(selector, ast.Constant) and isinstance(
                        selector.value, str
                    ):
                        fields.add(selector.value)
                    elif isinstance(selector, ast.Name):
                        resolved = _resolve_name(selector.id, mapping)
                        if resolved:
                            fields.add(resolved)
                        else:
                            _fail_unexpected_ast(f"unmapped selector {selector.id}")
                    else:
                        _fail_unexpected_ast("selector type")
                continue

        if not isinstance(key, ast.Call) or not isinstance(key.func, ast.Attribute):
            _fail_unexpected_ast("schema key wrapper")
        if key.func.attr not in {"Required", "Optional"}:
            _fail_unexpected_ast(f"unexpected schema call {key.func.attr}")
        if not key.args:
            _fail_unexpected_ast("schema key args")
        selector = key.args[0]
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
