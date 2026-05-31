"""Guard against import-time installation of test stubs."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

STUB_INSTALL_HELPERS = {
    "clear_integration_modules",
    "force_module",
    "stub_aiohttp_module",
    "stub_config_entry_class",
    "stub_custom_components_packages",
    "stub_exceptions",
    "stub_homeassistant_package",
    "stub_update_coordinator_module",
}


class ImportTimeStubMutationVisitor(ast.NodeVisitor):
    """Find sys.modules mutations that execute while importing a test module."""

    def __init__(self) -> None:
        self.scope_depth = 0
        self.sys_aliases = {"sys"}
        self.sys_modules_aliases: set[str] = set()
        self.violations: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        if self.scope_depth == 0:
            for alias in node.names:
                if alias.name == "sys":
                    self.sys_aliases.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.scope_depth == 0 and node.module == "sys":
            for alias in node.names:
                if alias.name == "modules":
                    self.sys_modules_aliases.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_nested_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_nested_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_nested_scope(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.scope_depth == 0:
            for target in node.targets:
                self._check_assignment_target(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self.scope_depth == 0:
            self._check_assignment_target(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self.scope_depth == 0:
            self._check_assignment_target(node.target)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        if self.scope_depth == 0:
            for target in node.targets:
                self._check_delete_target(target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.scope_depth == 0:
            if self._is_sys_modules_method_call(
                node, {"clear", "pop", "popitem", "setdefault", "update"}
            ):
                self.violations.append(
                    (node.lineno, "top-level sys.modules mutation call")
                )
            elif self._is_stub_install_helper_call(node):
                self.violations.append(
                    (node.lineno, "top-level stub installation helper call")
                )
        self.generic_visit(node)

    def _visit_nested_scope(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def _check_assignment_target(self, target: ast.expr) -> None:
        if self._is_sys_modules(target):
            self.violations.append(
                (target.lineno, "top-level sys.modules reassignment")
            )
        elif isinstance(target, ast.Subscript) and self._is_sys_modules(target.value):
            self.violations.append((target.lineno, "top-level sys.modules assignment"))

    def _check_delete_target(self, target: ast.expr) -> None:
        if isinstance(target, ast.Subscript) and self._is_sys_modules(target.value):
            self.violations.append((target.lineno, "top-level sys.modules deletion"))

    def _is_sys_modules_method_call(self, node: ast.Call, names: set[str]) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in names
            and self._is_sys_modules(node.func.value)
        )

    def _is_stub_install_helper_call(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id in STUB_INSTALL_HELPERS
        if isinstance(node.func, ast.Attribute):
            return node.func.attr in STUB_INSTALL_HELPERS
        return False

    def _is_sys_modules(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id in self.sys_aliases
        ) or (isinstance(node, ast.Name) and node.id in self.sys_modules_aliases)


def test_tests_do_not_install_stubs_at_import_time() -> None:
    """Keep Home Assistant and aiohttp stubs fixture- or helper-scoped."""

    paths = sorted(TESTS_DIR.glob("test_*.py")) + [TESTS_DIR / "conftest.py"]
    violations: list[str] = []

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = ImportTimeStubMutationVisitor()
        visitor.visit(tree)
        source_lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, reason in visitor.violations:
            source = source_lines[line_number - 1].strip()
            violations.append(
                f"{path.relative_to(ROOT)}:{line_number}: {reason}: {source}"
            )

    assert not violations, "\n".join(
        [
            "Stub modules must not be installed while importing test modules.",
            "Move the operation into a fixture, test, or helper function instead.",
            *violations,
        ]
    )
