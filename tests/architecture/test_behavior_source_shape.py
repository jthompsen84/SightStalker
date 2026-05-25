"""Source-shape boundary guards for BEHAVIOR-SPEC-1.

Each guard is a pure function over Python source (parsed with ``ast``) so it can
be exercised both against the real tree and against synthetic violating source
in a self-test. Guards are labeled PERMANENT or SNAPSHOT-v0.4.3 in their test
docstrings per the spec.

No future package is imported here. The checks use ``pathlib`` + ``ast`` only.
"""

from __future__ import annotations

import ast
from pathlib import Path

import sightstalker

_PKG_ROOT = Path(sightstalker.__file__).resolve().parent

# Forbidden interaction method names on engine protocol classes.
_FORBIDDEN_ENGINE_METHODS = {
    "type_text",
    "click",
    "scroll",
    "press_key",
    "move_mouse",
    "interaction_target",
    "resolve_environment_profile",
    "initialize_context",
}

# Scoped future symbol names forbidden as AST Name/Attribute references.
_FUTURE_SYMBOL_NAMES = {
    "InteractionProfile",
    "InteractionSimulator",
    "EnvironmentProfile",
    "ContextConfigResolver",
    "ContextInitializer",
    "ConfiguredInteractionSimulator",
}


# --- pure guard helpers ----------------------------------------------------


def imported_modules(source: str) -> set[str]:
    """Return the set of top-level absolute module paths imported by source."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                found.add(node.module)
    return found


def imports_any_forbidden(source: str, forbidden_prefixes: set[str]) -> set[str]:
    """Return forbidden imports (exact or dotted-prefix) used by source."""
    hits: set[str] = set()
    for mod in imported_modules(source):
        for prefix in forbidden_prefixes:
            if mod == prefix or mod.startswith(prefix + "."):
                hits.add(mod)
    return hits


def class_methods(source: str) -> dict[str, set[str]]:
    """Map each top-level class name to the set of method names it defines."""
    tree = ast.parse(source)
    result: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = {
                m.name
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            result[node.name] = methods
    return result


def referenced_names(source: str) -> set[str]:
    """Return all Name ids and Attribute attrs referenced in the source."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _py_files(*parts: str) -> list[Path]:
    base = _PKG_ROOT.joinpath(*parts)
    return sorted(base.rglob("*.py")) if base.exists() else []


# --- engines: PERMANENT ----------------------------------------------------

_ENGINE_FORBIDDEN_IMPORTS = {
    "sightstalker.ops",
    "sightstalker.interaction",
    "sightstalker.environment",
    "sightstalker.cli",
    "sightstalker.persistence",
    "sightstalker.diagnostics",
}


def test_engines_forbidden_imports_permanent() -> None:
    """PERMANENT: engines import no ops/interaction/environment/cli/persistence/diagnostics."""
    offenders: dict[str, set[str]] = {}
    files = _py_files("engines")
    assert files, "no engine source files found"
    for path in files:
        hits = imports_any_forbidden(
            path.read_text(encoding="utf-8"), _ENGINE_FORBIDDEN_IMPORTS
        )
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"engines import forbidden modules: {offenders}"


def test_engine_protocols_have_no_interaction_methods_permanent() -> None:
    """PERMANENT: engine protocol classes gain no interaction/profile/init methods."""
    base = _PKG_ROOT / "engines" / "base.py"
    methods_by_class = class_methods(base.read_text(encoding="utf-8"))
    protocol_classes = {
        "BrowserEngine",
        "BrowserRuntime",
        "BrowserContextHandle",
        "PageHandle",
    }
    offenders: dict[str, set[str]] = {}
    for cls, methods in methods_by_class.items():
        if cls in protocol_classes:
            bad = methods & _FORBIDDEN_ENGINE_METHODS
            if bad:
                offenders[cls] = bad
    assert offenders == {}, f"engine protocols gained interaction methods: {offenders}"


# --- sessions: PERMANENT ---------------------------------------------------

_SESSION_FORBIDDEN_IMPORTS = {
    "sightstalker.interaction",
    "sightstalker.environment",
    "sightstalker.cli",
}


def test_sessions_forbidden_imports_permanent() -> None:
    """PERMANENT: sessions import no interaction/environment/cli."""
    offenders: dict[str, set[str]] = {}
    files = _py_files("sessions")
    assert files, "no session source files found"
    for path in files:
        hits = imports_any_forbidden(
            path.read_text(encoding="utf-8"), _SESSION_FORBIDDEN_IMPORTS
        )
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"sessions import forbidden modules: {offenders}"


def test_sessions_no_future_symbol_references_permanent() -> None:
    """PERMANENT: sessions reference no future selector/simulator/resolver names."""
    forbidden = {
        "InteractionProfile",
        "InteractionSimulator",
        "EnvironmentProfile",
        "ContextConfigResolver",
        "ContextInitializer",
    }
    offenders: dict[str, set[str]] = {}
    for path in _py_files("sessions"):
        bad = referenced_names(path.read_text(encoding="utf-8")) & forbidden
        if bad:
            offenders[path.name] = bad
    assert offenders == {}, f"sessions reference future names: {offenders}"


# --- ops: relaxed by ENVIRONMENT-1 -----------------------------------------

# After ENVIRONMENT-1, ops may import the narrow environment protocol/model
# modules for resolver/override/resolution typing and invocation, but must not
# import the concrete environment implementation modules (it is the composition
# root, not the implementation home) and must not import interaction.
_OPS_FORBIDDEN_ENV_MODULES = {
    "sightstalker.environment.stores",
    "sightstalker.environment.selectors",
    "sightstalker.environment.applicators",
    "sightstalker.environment.resolver",
    "sightstalker.environment.errors",
}
_OPS_FORBIDDEN_IMPORTS = {"sightstalker.interaction"}
_OPS_ALLOWED_ENV_MODULES = {
    "sightstalker.environment.protocols",
    "sightstalker.environment.models",
    "sightstalker.environment.types",
}


def test_ops_does_not_import_interaction_permanent_snapshot() -> None:
    """SNAPSHOT-v0.4.3: ops may import env protocols/models but not interaction.

    Relaxed for environment by ENVIRONMENT-1; interaction relaxed later by
    INTERACTION-WIRING-1.
    """
    offenders: dict[str, set[str]] = {}
    files = _py_files("ops")
    assert files, "no ops source files found"
    for path in files:
        modules = imported_modules(path.read_text(encoding="utf-8"))
        bad: set[str] = set()
        for mod in modules:
            for prefix in _OPS_FORBIDDEN_IMPORTS:
                if mod == prefix or mod.startswith(prefix + "."):
                    bad.add(mod)
            if mod in _OPS_FORBIDDEN_ENV_MODULES:
                bad.add(mod)
            # Any non-allowed environment submodule is forbidden.
            if mod.startswith("sightstalker.environment") and (
                mod not in _OPS_ALLOWED_ENV_MODULES
            ):
                bad.add(mod)
        if bad:
            offenders[path.name] = bad
    assert offenders == {}, f"ops imports forbidden modules: {offenders}"


def test_ops_only_imports_allowed_environment_modules() -> None:
    """ENVIRONMENT-1: ops environment imports are limited to protocols/models."""
    for path in _py_files("ops"):
        for mod in imported_modules(path.read_text(encoding="utf-8")):
            if mod.startswith("sightstalker.environment"):
                assert mod in _OPS_ALLOWED_ENV_MODULES, (
                    f"{path.name} imports disallowed env module {mod}"
                )


# --- cli: MIXED ------------------------------------------------------------

_CLI_FORBIDDEN_IMPORTS_SNAPSHOT = {
    "sightstalker.interaction",
    "sightstalker.environment",
}


def test_cli_does_not_import_future_packages_snapshot() -> None:
    """SNAPSHOT-v0.4.3: relaxed by CLI-OPT-IN-1 (CLI may parse, ops still wires)."""
    offenders: dict[str, set[str]] = {}
    files = _py_files("cli")
    assert files, "no cli source files found"
    for path in files:
        hits = imports_any_forbidden(
            path.read_text(encoding="utf-8"), _CLI_FORBIDDEN_IMPORTS_SNAPSHOT
        )
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"cli imports future packages: {offenders}"


def test_cli_does_not_construct_future_objects_permanent() -> None:
    """PERMANENT: CLI does not directly reference future implementation classes."""
    offenders: dict[str, set[str]] = {}
    for path in _py_files("cli"):
        bad = referenced_names(path.read_text(encoding="utf-8")) & _FUTURE_SYMBOL_NAMES
        if bad:
            offenders[path.name] = bad
    assert offenders == {}, f"cli references future symbols: {offenders}"


# --- synthetic self-tests (each guard fails when violated) -----------------


def test_selftest_import_guard_detects_violation() -> None:
    src = "from sightstalker.interaction import x\nimport os\n"
    assert imports_any_forbidden(src, {"sightstalker.interaction"}) == {
        "sightstalker.interaction"
    }
    # And passes on clean source.
    assert imports_any_forbidden("import os\n", {"sightstalker.interaction"}) == set()


def test_selftest_dotted_import_guard_detects_violation() -> None:
    src = "import sightstalker.environment.resolver\n"
    assert imports_any_forbidden(src, {"sightstalker.environment"}) == {
        "sightstalker.environment.resolver"
    }


def test_selftest_engine_method_guard_detects_violation() -> None:
    src = (
        "class PageHandle:\n"
        "    async def goto(self, url): ...\n"
        "    async def click(self, sel): ...\n"
    )
    methods = class_methods(src)["PageHandle"]
    assert methods & _FORBIDDEN_ENGINE_METHODS == {"click"}
    # Clean protocol passes.
    clean = "class PageHandle:\n    async def goto(self, url): ...\n"
    assert class_methods(clean)["PageHandle"] & _FORBIDDEN_ENGINE_METHODS == set()


def test_selftest_name_reference_guard_detects_violation() -> None:
    src = "def f():\n    return EnvironmentProfile()\n"
    assert "EnvironmentProfile" in referenced_names(src)
    # Clean source passes.
    assert "EnvironmentProfile" not in referenced_names("def f():\n    return 1\n")


def test_selftest_attribute_reference_guard_detects_violation() -> None:
    src = "def f(m):\n    return m.InteractionSimulator\n"
    assert "InteractionSimulator" in referenced_names(src)
