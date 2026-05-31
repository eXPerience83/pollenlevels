"""Guard against import-time installation of test stubs."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

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
        self.stub_helper_aliases = set(STUB_INSTALL_HELPERS)
        self.violations: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        if self.scope_depth == 0:
            for alias in node.names:
                if alias.name == "sys":
                    self.sys_aliases.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.scope_depth == 0:
            for alias in node.names:
                imported_name = alias.name
                local_name = alias.asname or imported_name
                if node.module == "sys" and imported_name == "modules":
                    self.sys_modules_aliases.add(local_name)
                if imported_name in STUB_INSTALL_HELPERS:
                    self.stub_helper_aliases.add(local_name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_header(node)
        self._visit_nested_body(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_header(node)
        self._visit_nested_body(node.body)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_argument_defaults(node.args)
        self.scope_depth += 1
        self.visit(node.body)
        self.scope_depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.scope_depth == 0:
            for target in node.targets:
                self._check_assignment_target(target)
                self._track_sys_modules_alias(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self.scope_depth == 0:
            self._check_assignment_target(node.target)
            self._track_sys_modules_alias(node.target, node.value)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        if self.scope_depth == 0:
            self._check_assignment_target(node.target)
            self._track_sys_modules_alias(node.target, node.value)
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

    def _visit_function_header(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_argument_defaults(node.args)

    def _visit_argument_defaults(self, arguments: ast.arguments) -> None:
        for default in [*arguments.defaults, *arguments.kw_defaults]:
            if default is not None:
                self.visit(default)

    def _visit_nested_body(self, body: list[ast.stmt]) -> None:
        self.scope_depth += 1
        for statement in body:
            self.visit(statement)
        self.scope_depth -= 1

    def _track_sys_modules_alias(
        self, target: ast.expr, value: ast.expr | None
    ) -> None:
        if (
            isinstance(target, ast.Name)
            and value is not None
            and self._is_sys_modules(value)
        ):
            self.sys_modules_aliases.add(target.id)

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
            return node.func.id in self.stub_helper_aliases
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


def _violation_reasons(source: str) -> list[str]:
    visitor = ImportTimeStubMutationVisitor()
    visitor.visit(ast.parse(source))
    return [reason for _line, reason in visitor.violations]


def _scanned_test_paths() -> list[Path]:
    paths = {
        *TESTS_DIR.rglob("test_*.py"),
        *TESTS_DIR.rglob("conftest.py"),
        *TESTS_DIR.rglob("__init__.py"),
    }
    paths.discard(TESTS_DIR / "_ha_stubs.py")
    return sorted(paths)


@pytest.mark.parametrize(
    ("source", "expected_reason"),
    [
        (
            """
import sys

class StubContainer:
    sys.modules["homeassistant"] = object()
""",
            "top-level sys.modules assignment",
        ),
        (
            """
import sys

def test_stub(default=sys.modules.setdefault("aiohttp", object())):
    pass
""",
            "top-level sys.modules mutation call",
        ),
        (
            """
import sys

async def test_stub(default=sys.modules.setdefault("aiohttp", object())):
    pass
""",
            "top-level sys.modules mutation call",
        ),
        (
            """
import sys

class StubContainer:
    def helper(self, default=sys.modules.setdefault("aiohttp", object())):
        pass
""",
            "top-level sys.modules mutation call",
        ),
        (
            """
from sys import modules

modules |= {"homeassistant": object()}
""",
            "top-level sys.modules reassignment",
        ),
        (
            """
from tests._ha_stubs import stub_homeassistant_package as install_ha

install_ha()
""",
            "top-level stub installation helper call",
        ),
        (
            """
import sys

sys_modules = sys.modules
sys_modules["homeassistant"] = object()
""",
            "top-level sys.modules assignment",
        ),
        (
            """
import sys

sys_modules = sys.modules
sys_modules.setdefault("aiohttp", object())
""",
            "top-level sys.modules mutation call",
        ),
    ],
)
def test_import_time_stub_visitor_flags_reviewed_patterns(
    source: str, expected_reason: str
) -> None:
    assert expected_reason in _violation_reasons(source)


def test_import_time_stub_visitor_allows_function_scoped_setup() -> None:
    source = """
import sys
from tests._ha_stubs import stub_homeassistant_package as install_ha

def helper():
    sys.modules["homeassistant"] = object()
    sys.modules.setdefault("aiohttp", object())
    install_ha()

class StubContainer:
    def helper(self, default=None):
        sys.modules["homeassistant"] = object()

cb = lambda: install_ha()
"""

    assert _violation_reasons(source) == []


def test_scanned_test_paths_include_pytest_imported_modules() -> None:
    paths = {path.relative_to(ROOT).as_posix() for path in _scanned_test_paths()}

    assert "tests/__init__.py" in paths
    assert "tests/conftest.py" in paths
    assert "tests/test_stub_hygiene.py" in paths
    assert "tests/_ha_stubs.py" not in paths


def test_tests_do_not_install_stubs_at_import_time() -> None:
    """Keep Home Assistant and aiohttp stubs fixture- or helper-scoped."""

    violations: list[str] = []

    for path in _scanned_test_paths():
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
