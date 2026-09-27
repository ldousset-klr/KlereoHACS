"""Test wiring: the Home Assistant stub, the import path, and the recorder.

`klereo_stub` installs its fake `homeassistant.*` modules the moment it is
imported, so importing it here — before pytest collects any test module —
is what lets `custom_components/klereo` import at all.
"""
import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "custom_components"))

import klereo_stub  # noqa: E402  — must precede any klereo import


class Check:
    """Records every comparison, so one run reports every failure at once.

    A bare `assert` would stop at the first, and these suites are tables:
    knowing that three of sixteen outputs are wrong is worth more than
    knowing the first one is.
    """

    def __init__(self):
        self.failures = []
        self.count = 0

    def __call__(self, label, got, want):
        self.count += 1
        if got != want:
            self.failures.append(f"{label}: got {got!r}, wanted {want!r}")

    def assert_ok(self):
        assert not self.failures, (
            f"{len(self.failures)} of {self.count} checks failed:\n  "
            + "\n  ".join(self.failures)
        )


@pytest.fixture
def check():
    return Check()


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    """Confirmations poll on COMMAND_POLL_DELAYS; nobody wants to wait 26 s.

    Patched for every test rather than the two that need it: nothing else in
    the component sleeps, so there is no behaviour left to hide.
    """
    async def instant(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)
