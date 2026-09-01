"""Remote-tier units (spec 9.7, 10.3, D13, F.11)."""

import os
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from hk import verbs


class NiriGateTest(unittest.TestCase):
    def test_no_niri_socket_zero_compositor_calls(self):
        env = {k: v for k, v in os.environ.items() if k != "NIRI_SOCKET"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("subprocess.run") as run:
            verbs._niri_adopt("hk-ws-w1")
        run.assert_not_called()  # spec 9.7: absent -> ZERO compositor calls

    def test_only_niri_call_site(self):
        """spec F.11: `niri` is invoked from the one gated adapter only."""
        repo = pathlib.Path(__file__).resolve().parent.parent.parent
        offenders = []
        for path in list(repo.glob("hk/*.py")) + list(repo.glob("kitten/*.py")) + [repo / "bin" / "hk"]:
            if path.name == "verbs.py":
                continue
            if '"niri"' in path.read_text():
                offenders.append(str(path))
        self.assertEqual(offenders, [])
