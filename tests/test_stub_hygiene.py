"""Guard against import-time installation of test stub modules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
ALLOWED_STUB_HELPER_MODULE = TESTS_DIR / "_ha_stubs.py"
STUB_HELPERS = {
    "clear_integration_modules",
    "force_module",
    "stub_aiohttp_module",
    "stub_config_entry_class",
    "stub_custom_components_packages",
    "stub_exceptions",
    "stub_homeassistant_package",
    "stub_update_coordinator_module",
}


def _test_files() -> list[Path]:
    return sorted([TESTS_DIR / "conftest.py", *TESTS_DIR.glob("test_*.py")])


class _ImportTimeStubMutationVisitor(ast.NodeVisitor):
    """Find sys.modules mutations and stub installs that run during import."""

    def __init__(self) -> None:
        self.stub_module_aliases: set[str] = set()
        self.stub_helper_names: set[str] = set()
        self.violations: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in {"tests._ha_stubs", "_ha_stubs"}:
                self.stub_module_aliases.add(alias.asname or alias.name.split(".")[-1])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module in {"tests._ha_stubs", "_ha_stubs"}:
            for alias in node.names:
                if alias.name in STUB_HELPERS:
                    self.stub_helper_names.add(alias.asname or alias.name)
            return

        if node.module == "tests" or (node.level > 0 and node.module is None):
            for alias in node.names:
                if alias.name == "_ha_stubs":
                    self.stub_module_aliases.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(_is_sys_modules_subscript(target) for target in node.targets):
            self._add(node, "top-level sys.modules[...] assignment")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if _is_sys_modules_subscript(node.target):
            self._add(node, "top-level sys.modules[...] assignment")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if _is_sys_modules_subscript(node.target):
            self._add(node, "top-level sys.modules[...] assignment")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_sys_modules_method_call(node, {"setdefault", "update"}):
            self._add(node, f"top-level sys.modules.{node.func.attr}(...) call")
        elif self._is_stub_helper_call(node):
            self._add(node, "top-level test stub helper call")
        self.generic_visit(node)

    def _is_stub_helper_call(self, node: ast.Call) -> bool:
        match node.func:
            case ast.Name(id=name):
                return name in self.stub_helper_names
            case ast.Attribute(value=ast.Name(id=alias), attr=name):
                return alias in self.stub_module_aliases and name in STUB_HELPERS
            case _:
                return False

    def _add(self, node: ast.AST, message: str) -> None:
        self.violations.append((node.lineno, message))


def _violations_for_source(source: str) -> list[tuple[int, str]]:
    visitor = _ImportTimeStubMutationVisitor()
    visitor.visit(ast.parse(source))
    return visitor.violations


def _is_sys_modules_subscript(node: ast.AST) -> bool:
    return isinstance(node, ast.Subscript) and _is_sys_modules(node.value)


def _is_sys_modules_method_call(node: ast.Call, method_names: set[str]) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in method_names
        and _is_sys_modules(node.func.value)
    )


def _is_sys_modules(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "modules"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def test_from_tests_import_ha_stubs_detects_top_level_helper_call() -> None:
    violations = _violations_for_source("""\
from tests import _ha_stubs
_ha_stubs.stub_aiohttp_module()
""")

    assert violations == [(2, "top-level test stub helper call")]


def test_relative_import_ha_stubs_detects_top_level_helper_call() -> None:
    violations = _violations_for_source("""\
from . import _ha_stubs
_ha_stubs.stub_aiohttp_module()
""")

    assert violations == [(2, "top-level test stub helper call")]


def test_tests_do_not_install_stubs_at_module_import_time() -> None:
    """Keep Home Assistant/aiohttp stubs scoped to fixtures or test helpers."""

    violations: list[str] = []
    for path in _test_files():
        if path == ALLOWED_STUB_HELPER_MODULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _ImportTimeStubMutationVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{path.relative_to(ROOT)}:{line}: {message}"
            for line, message in visitor.violations
        )

    assert not violations, "\n".join(
        [
            "Do not install Home Assistant/aiohttp stubs at module import time.",
            "Move sys.modules mutations or stub helper calls into fixtures/tests/helpers.",
            *violations,
        ]
    )
