"""Shared Direct Mode fixtures and helpers for AdjudicatedEscrow."""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from gltest.direct.pytest_plugin import create_address as _create_address

# gltest-direct replaces stdin with a temporary fd. POSIX permits the unlink
# while it is open; tolerate the Windows difference if the suite is run there.
if os.name == "nt":
    _original_unlink = os.unlink

    def _tolerant_unlink(path, *args, **kwargs):
        try:
            return _original_unlink(path, *args, **kwargs)
        except PermissionError:
            return None

    os.unlink = _tolerant_unlink

CONTRACT_PATH = "contracts/AdjudicatedEscrow.py"
SDK_VERSION = "v0.2.16"

BASE_FEE = 10**15  # 0.001 GEN
DEPOSIT = 10**18  # 1 GEN
BOND = DEPOSIT * 2500 // 10000
WEEK = 7 * 24 * 3600
T0 = int(time.time()) // 3600 * 3600

SPEC_OK = (
    "Deliver a five-page market report on EU battery recycling with cited "
    "sources, formatted as markdown and sent before the deadline."
)
SPEC_ALT = (
    "Paint the community mural on Elm Street's north wall using weatherproof "
    "paint, finishing at least two days before the deadline."
)
MANIFEST = "https://evidence.example/receipt"
MANIFEST_ALT = "https://evidence.example/a\nhttps://evidence.example/b"
EVIDENCE_TEXT = "Delivery receipt: report uploaded before the agreed deadline."


def _ensure_genlayer_std_importable() -> None:
    """Use the cached SDK Address class required by Direct Mode storage."""
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
            if child.is_dir() and str(child) not in sys.path:
                sys.path.insert(0, str(child))
                break
    try:
        from genlayer.py.types import Address  # noqa: F401
        return
    except ModuleNotFoundError:
        # A fresh sandbox has no runner cache. Bootstrap the exact historical
        # runner required by the contract header before building typed fixtures.
        from gltest.direct.sdk_loader import setup_sdk_paths

        setup_sdk_paths(Path(CONTRACT_PATH), version=SDK_VERSION)


def _sdk_address(raw):
    _ensure_genlayer_std_importable()
    if isinstance(raw, bytes):
        from genlayer.py.types import Address

        return Address(raw)
    return raw


@pytest.fixture
def direct_alice():
    return _sdk_address(_create_address("alice"))


@pytest.fixture
def direct_bob():
    return _sdk_address(_create_address("bob"))


@pytest.fixture
def direct_charlie():
    return _sdk_address(_create_address("charlie"))


@pytest.fixture
def escrow(direct_deploy, direct_alice, direct_charlie):
    return direct_deploy(
        CONTRACT_PATH,
        direct_alice,
        direct_charlie,
        BASE_FEE,
        sdk_version=SDK_VERSION,
    )


@pytest.fixture
def opened(direct_vm, escrow, direct_alice, direct_bob):
    return open_agreement(direct_vm, escrow, direct_alice, direct_bob)


@pytest.fixture
def committed(opened, direct_vm, escrow, direct_bob):
    accept_agreement(direct_vm, escrow, direct_bob, opened)
    return opened


def iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def verdict(outcome: int, reason: str = "obligations judged against evidence") -> str:
    return json.dumps({"outcome": outcome, "reason": reason})


def open_agreement(
    vm,
    escrow,
    depositor,
    contractor_hint,
    *,
    spec: str = SPEC_OK,
    deadline: int = T0 + WEEK,
    manifest: str = MANIFEST,
    value: int = DEPOSIT + BASE_FEE,
) -> int:
    vm.sender = depositor
    vm.value = value
    escrow.open_agreement(contractor_hint, spec, deadline, manifest)
    vm.value = 0
    return escrow.next_agreement_id() - 1


def accept_agreement(
    vm,
    escrow,
    contractor,
    agreement_id: int,
    *,
    value: int = BOND + BASE_FEE,
) -> None:
    vm.sender = contractor
    vm.value = value
    escrow.accept_agreement(agreement_id)
    vm.value = 0


def resolve(vm, escrow, caller, agreement_id: int) -> None:
    vm.sender = caller
    escrow.resolve(agreement_id)


def state_of(escrow, agreement_id: int) -> dict:
    return escrow.get_agreement(agreement_id)


def mock_evidence(vm, body: str = EVIDENCE_TEXT) -> None:
    vm.mock_web(r"^https://evidence\.example/", {"status": 200, "body": body})


def mock_llm(vm, payload: str) -> None:
    vm.mock_llm(r"neutral adjudicator", payload)


def warp(vm, timestamp: int) -> None:
    vm.warp(iso(timestamp))
