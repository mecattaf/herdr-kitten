"""Repo hygiene gate (round2-03; BUG-7, BUG-13, BUG-14).

The zero-byte file literally named `herdr: fake blocked` sat tracked at the
repo root from f031824 until round2-03. Nothing recreated it — it was swept in
once by a `git add -A` during an interactive session and then never noticed,
because nothing ever looked. This module is the "looking".

It is deliberately cheap and git-based: it asserts properties of the tracked
file set, so it also fails in a fresh clone on any machine.
"""

import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

# Files whose emptiness is meaningful, not accidental.
ALLOWED_EMPTY = {"tests/unit/__init__.py"}

# Everything a stranger should see at the top level of the repo. Anything else
# is either a reader-facing addition (add it here deliberately) or scaffolding
# that belongs under docs/dev/ (BUG-14).
ALLOWED_ROOT = {
    "LICENSE", "README.md", "install.sh", "flake.nix", "flake.lock", ".gitignore",
}
ALLOWED_ROOT_DIRS = {
    "assets", "bin", "conf", "contrib", "docs", "hk", "kitten", "tests", ".github",
}


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


class TrackedFileHygieneTest(unittest.TestCase):
    def setUp(self):
        self.files = tracked()
        self.assertTrue(self.files, "git ls-files returned nothing")

    def test_no_colon_in_any_tracked_path(self):
        # A colon makes the path illegal on Windows and unclonable there; it is
        # also the signature of a shell redirection accident.
        offenders = [p for p in self.files if ":" in p]
        self.assertEqual(offenders, [], f"tracked paths containing ':': {offenders}")

    def test_no_shell_metacharacters_in_tracked_paths(self):
        bad = set('*?"<>|\n\t')
        offenders = [p for p in self.files if bad & set(p)]
        self.assertEqual(offenders, [], f"tracked paths with shell metacharacters: {offenders}")

    def test_no_accidental_zero_byte_files(self):
        offenders = [p for p in self.files
                     if p not in ALLOWED_EMPTY
                     and (REPO / p).is_file()
                     and (REPO / p).stat().st_size == 0]
        self.assertEqual(offenders, [], f"zero-byte tracked files: {offenders}")

    def test_repo_root_is_reader_facing(self):
        # BUG-14: DEFERRED.md / METRICS.md / acceptance-run.md read as raw agent
        # scaffolding (wave ledgers, token accounting). They live under
        # docs/dev/ now; the root is what a stranger from r/kitty lands on.
        root = {p.split("/")[0] for p in self.files}
        unexpected = root - ALLOWED_ROOT - ALLOWED_ROOT_DIRS
        self.assertEqual(unexpected, set(),
                         f"unexpected entries at the repo root: {sorted(unexpected)}")


class LicenseTest(unittest.TestCase):
    """BUG-7: without a LICENSE the project is legally unusable by a stranger."""

    def test_license_file_exists_and_is_mit(self):
        lic = REPO / "LICENSE"
        self.assertTrue(lic.is_file(), "LICENSE missing — the repo is unusable as posted")
        text = lic.read_text()
        self.assertIn("MIT License", text)
        self.assertIn("Thomas Mecattaf", text)

    def test_license_is_advertised_where_people_look(self):
        self.assertIn("LICENSE", (REPO / "README.md").read_text())
        self.assertIn("licenses.mit", (REPO / "flake.nix").read_text())


class MovedScaffoldingTest(unittest.TestCase):
    def test_no_dangling_links_to_the_moved_files(self):
        """Nothing may still point at the pre-move paths."""
        stale = []
        for doc in list(REPO.glob("*.md")) + list((REPO / "docs").rglob("*.md")):
            text = doc.read_text()
            for needle in ("(DEFERRED.md", "(METRICS.md", "(docs/acceptance-run.md",
                           "`docs/acceptance-run.md`", "`DEFERRED.md`", "`METRICS.md`"):
                if needle in text:
                    stale.append(f"{doc.relative_to(REPO)}: {needle}")
        self.assertEqual(stale, [], f"links to moved scaffolding: {stale}")


if __name__ == "__main__":
    unittest.main()
