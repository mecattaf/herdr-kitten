"""Import audit (spec 1.3, D1): every repo Python source imports ONLY the
stdlib, the local hk package, or kitty's in-process API (kitten side only)."""

import ast
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
ALLOWED_PREFIXES = ("hk", "kitten")  # local packages (repo tree)
# kitty/kittens are provided by kitty in-process; ladder/fork_state are the
# kitten's own modules, importable flat when installed to ~/.config/kitty/
KITTEN_ONLY_PREFIXES = ("kitty", "kittens", "ladder", "fork_state")


def _imports(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _sources():
    yield REPO / "bin" / "hk", False
    for p in (REPO / "hk").rglob("*.py"):
        yield p, False
    for p in (REPO / "kitten").rglob("*.py"):
        yield p, True
    for p in (REPO / "tests").rglob("*.py"):
        yield p, False


class ImportAuditTest(unittest.TestCase):
    def test_stdlib_only(self):
        offenders = []
        for path, is_kitten in _sources():
            for name in _imports(path):
                top = name.split(".")[0]
                if top in sys.stdlib_module_names:
                    continue
                if top in ALLOWED_PREFIXES:
                    continue
                if is_kitten and top in KITTEN_ONLY_PREFIXES:
                    continue
                offenders.append(f"{path}: {name}")
        self.assertEqual(offenders, [], f"non-stdlib imports found: {offenders}")

    def test_sources_exist(self):
        self.assertTrue((REPO / "bin" / "hk").exists())
