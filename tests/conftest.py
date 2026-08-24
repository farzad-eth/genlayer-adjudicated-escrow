"""
Shared fixtures and helpers for AdjudicatedEscrow Direct Mode tests.
"""

import json
import os
import time
from datetime import datetime, timezone

import pytest

# gltest-direct replaces stdin with a temp-file fd and unlinks it while the
# duplicate is still open. POSIX allows that; Windows raises PermissionError.
# Tolerate it: the leftover temp files are harmless in a test run.
if os.name == "nt":
    _orig_unlink = os.unlink

    def _tolerant_unlink(path, *args, **kwargs):
        try:
            return _orig_unlink(path, *args, **kwargs)
        except PermissionError:
            return None

    os.unlink = _tolerant_unlink

CONTRACT_PATH = "contracts/AdjudicatedEscrow.py"

# ---------------------------------------------------------------------------
# gltest-direct's create_address() yields plain bytes, but the v0.2.16 SDK's
# calldata roundtrip and storage layer require a real genlayer Address.
# Override the address fixtures with SDK-typed equivalents.
# ---------------------------------------------------------------------------

import sys
from pathlib import Path


def _ensure_genlayer_std_importable() -> None:
    """Put the extracted genlayer-std (pinned SDK_VERSION) on sys.path so the
    Address type used by contract storage is the very same class the VM uses.

    gltest-direct REMOVES every sys.path entry containing 'gltest-direct'
    (and evicts the matching modules) after each test, so this must re-check
    and re-insert on every call — no caching allowed here.
    """
    base = (
        Path.home()
        / ".cache"
        / "gltest-direct"
        / "extracted"
        / SDK_VERSION
        / "py-lib-genlayer-std"
    )
    if base.exists():
        for child in sorted(base.iterdir()):
            if child.is_dir():
                p = str(child)
                if p not in sys.path:
                    sys.path.insert(0, p)
                break


def _sdk_address(raw) -> object:
    _ensure_genlayer_std_importable()
    if isinstance(raw, bytes):
        from genlayer.py.types import Address as _Address

        return _Address(raw)
    return raw  # already an SDK Address once genlayer-std is importable


from gltest.direct.pytest_plugin import (  # noqa: E402
    create_address as _create_address,
)


@pytest.fixture
def direct_alice():
    return _sdk_address(_create_address("alice"))


@pytest.fixture
def direct_bob():
    return _sdk_address(_create_address("bob"))


@pytest.fixture
def direct_charlie():
    return _sdk_address(_create_address("charlie"))

# The gltest-direct loader fetches `genvm-universal.tar.xz` from the LATEST
# genvm release, but newer releases stopped publishing that asset. We pin
# the last release that ships it and seed the local cache (see README).
SDK_VERSION = "v0.2.16"

# Deterministic economic constants mirroring the contract's defaults used in
# these tests (base_fee is a constructor argument, chosen small here).
BASE_FEE = 10 ** 15  # 0.001 GEN
DEPOSIT = 10 ** 18  # 1 GEN
BOND = DEPOSIT * 2500 // 10000  # 25% of deposit
WEEK = 7 * 24 * 3600

# Anchored to real wall-clock at import so deadlines are future-valid under
# any GenVM build (clock-pinned or not). Direct Mode runs in milliseconds,
# so the anchor stays valid for the whole run.
T0 = int(time.time()) // 3600 * 3600

SPEC_OK = (
    "Deliver a five-page market report on EU battery recycling with cited "
    "sources, formatted as markdown and sent before the deadline."
)
SPEC_ALT = (
    "Paint the community mural on Elm Street's north wall using weatherproof "
    "paint, finishing at least two days before the deadline."
)


def iso(ts: int) -> str:
    """Unix seconds -> ISO string accepted by direct_vm.warp()."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def verdict(outcome: int, reason: str = "obligations judged against evidence") -> str:
    """LLM mock payload shaped exactly like the contract expects."""
    return json.dumps({"outcome": outcome, "reason": reason})


@pytest.fixture
def escrow(direct_deploy, direct_alice, direct_charlie):
    """A freshly deployed factory. Alice is the canonical depositor, Charlie
    the fee recipient."""
    return direct_deploy(
        CONTRACT_PATH, direct_alice, direct_charlie, BASE_FEE,
        sdk_version=SDK_VERSION,
    )


@pytest.fixture
def opened(direct_vm, escrow, direct_alice, direct_bob):
    """An OPEN agreement (id 1) posted by Alice, hinting Bob as contractor."""
    return open_agreement(direct_vm, escrow, direct_alice, direct_bob)


@pytest.fixture
def committed(opened, direct_vm, escrow, direct_bob):
    """An OPEN agreement whose contractor (Bob) has accepted and bonded."""
    accept_agreement(direct_vm, escrow, direct_bob, opened)
    return opened


# ---------------------------------------------------------------------------
# Call helpers — they manipulate vm.sender / vm.value around each call and
# derive ids from views so the suite never depends on write-return plumbing.
# ---------------------------------------------------------------------------


def open_agreement(vm, escrow, depositor, contractor_hint,
                   spec: str = SPEC_OK, deadline: int = T0 + WEEK,
                   value: int = DEPOSIT + BASE_FEE) -> int:
    vm.sender = depositor
    vm.value = value
    escrow.open_agreement(contractor_hint, spec, deadline)
    vm.value = 0
    return escrow.next_agreement_id() - 1


def accept_agreement(vm, escrow, contractor, agreement_id: int,
                     value: int = BOND + BASE_FEE) -> None:
    vm.sender = contractor
    vm.value = value
    escrow.accept_agreement(agreement_id)
    vm.value = 0


def resolve(vm, escrow, caller, agreement_id: int, evidence: str = "see attached"):
    vm.sender = caller
    escrow.resolve(agreement_id, evidence)


def state_of(escrow, agreement_id: int) -> dict:
    return escrow.get_agreement(agreement_id)
