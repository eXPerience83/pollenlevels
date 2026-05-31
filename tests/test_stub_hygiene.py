"""Guard against import-time installation of shared test stubs."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

BLOCKED_HELPERS = {
    "clear_integration_modules",
    "force_module",
    "stub_aiohttp_module",
    "stub_config_entry_class",
    "stub_custom_components_packages",
    "stub_exceptions",
    "stub_homeassistant_package",
    "stub_update_coordinator_module",
}


class ImportTimeStubVisitor(ast.NodeVisitor):
    """Find the concrete import-time stub patterns this suite must avoid."""

    def __init__(self) -> None:
        self.scope_depth = 0
        self.sys_aliases = {"sys"}
        self.sys_modules_aliases: set[str] = set()
        self.helper_aliases = set(BLOCKED_HELPERS)
        self.violations: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        if self.scope_depth == 0:
            for alias in node.names:
                if alias.name == "sys":
                    self.sys_aliases.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.scope_depth == 0:
            for alias in node.names:
                local_name = alias.asname or alias.name
                if node.module == "sys" and alias.name == "modules":
                    self.sys_modules_aliases.add(local_name)
                if alias.name in BLOCKED_HELPERS:
                    self.helper_aliases.add(local_name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_decorators_and_defaults(node)
        self._visit_nested(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_decorators_and_defaults(node)
        self._visit_nested(node.body)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_argument_defaults(node.args)
        self.scope_depth += 1
        self.visit(node.body)
        self.scope_depth -= 1

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
            if self._is_sys_modules_method_call(node):
                self.violations.append(
                    (node.lineno, "top-level sys.modules mutation call")
                )
            elif self._is_blocked_helper_call(node):
                self.violations.append(
                    (node.lineno, "top-level shared stub helper call")
                )
        self.generic_visit(node)

    def _visit_decorators_and_defaults(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_argument_defaults(node.args)

    def _visit_argument_defaults(self, arguments: ast.arguments) -> None:
        for default in [*arguments.defaults, *arguments.kw_defaults]:
            if default is not None:
                self.visit(default)

    def _visit_nested(self, body: list[ast.stmt]) -> None:
        self.scope_depth += 1
        for statement in body:
            self.visit(statement)
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

    def _is_sys_modules_method_call(self, node: ast.Call) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"clear", "pop", "popitem", "setdefault", "update"}
            and self._is_sys_modules(node.func.value)
        )

    def _is_blocked_helper_call(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id in self.helper_aliases
        if isinstance(node.func, ast.Attribute):
            return node.func.attr in BLOCKED_HELPERS
        return False

    def _is_sys_modules(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id in self.sys_aliases
        ) or (isinstance(node, ast.Name) and node.id in self.sys_modules_aliases)


def _scanned_test_paths() -> list[Path]:
    paths = {
        *TESTS_DIR.glob("test_*.py"),
        *TESTS_DIR.glob("*_test.py"),
        TESTS_DIR / "conftest.py",
        TESTS_DIR / "__init__.py",
    }
    paths.discard(TESTS_DIR / "_ha_stubs.py")
    return sorted(path for path in paths if path.exists())


def test_tests_do_not_install_shared_stubs_at_import_time() -> None:
    """Keep shared stubs fixture-scoped instead of import-time global."""

    violations: list[str] = []

    for path in _scanned_test_paths():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        visitor = ImportTimeStubVisitor()
        visitor.visit(tree)
        source_lines = source.splitlines()
        for line_number, reason in visitor.violations:
            offending_source = source_lines[line_number - 1].strip()
            violations.append(
                f"{path.relative_to(ROOT)}:{line_number}: {reason}: "
                f"{offending_source}"
            )

    assert not violations, "\n".join(
        [
            "Shared test stubs must not be installed at module import time.",
            "Move the operation into a fixture or test-local import helper.",
            *violations,
        ]
    )
