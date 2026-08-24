"""
AdjudicatedEscrow — unit & consensus tests (genlayer-test, Direct Mode).

Layers, per GenLayer's testing strategy:
  1. pure storage/lifecycle tests (no LLM involved)
  2. mocked-adjudication happy paths (mock_llm)
  3. consensus tests via direct_vm.run_validator():
       - agreement on identical decisions
       - rejection (leader rotation) on differing decisions
       - deterministic error classification on malformed model output
"""

import json

import pytest
from conftest import (
    BASE_FEE,
    BOND,
    DEPOSIT,
    SPEC_ALT,
    SPEC_OK,
    T0,
    WEEK,
    accept_agreement,
    iso,
    open_agreement,
    resolve,
    state_of,
    verdict,
)

FULFILLED = 1
FAILED = 2
REFUNDED = 3


# ---------------------------------------------------------------------------
# 1. Deployment, configuration, pure lifecycle
# ---------------------------------------------------------------------------


class TestDeploymentAndViews:
    def test_config_view(self, escrow, direct_alice, direct_charlie):
        cfg = escrow.config()
        assert cfg["arbiter_hint"] == direct_alice.as_hex
        assert cfg["fee_recipient"] == direct_charlie.as_hex
        assert cfg["base_fee"] == BASE_FEE
        assert cfg["bond_bps"] == 2500

    def test_empty_registry(self, escrow):
        assert escrow.agreement_count() == 0
        assert escrow.next_agreement_id() == 1
        assert escrow.get_total_escrowed() == 0

    def test_unknown_agreement_reverts(self, escrow):
        with direct_expect_revert("unknown agreement id"):
            escrow.get_agreement(99)


class TestOpenAgreement:
    def test_open_stores_terms_and_escrows_deposit(
        self, escrow, direct_alice, direct_bob
    ):
        aid = open_agreement(direct_vm_holder.vm, escrow, direct_alice, direct_bob)
        rec = state_of(escrow, aid)
        assert rec["depositor"] == direct_alice.as_hex
        assert rec["state"] == 0
        assert rec["deposit"] == DEPOSIT
        assert rec["bond"] == 0
        assert rec["fee"] == BASE_FEE
        assert rec["spec"] == SPEC_OK
        assert rec["delivered_at"] == 0
        assert escrow.get_total_escrowed() == DEPOSIT
        assert escrow.agreement_count() == 1

    def test_ids_increase_monotonically(self, escrow, direct_alice, direct_bob):
        vm = direct_vm_holder.vm
        a = open_agreement(vm, escrow, direct_alice, direct_bob, spec=SPEC_OK)
        b = open_agreement(vm, escrow, direct_alice, direct_bob, spec=SPEC_ALT)
        assert b == a + 1
        assert escrow.agreement_count() == 2

    def test_value_below_deposit_plus_fee_reverts(self, escrow, direct_alice, direct_bob):
        with direct_expect_revert("value must exceed"):
            open_agreement(
                direct_vm_holder.vm, escrow, direct_alice, direct_bob,
                value=BASE_FEE,
            )

    def test_deadline_too_soon_reverts(self, escrow, direct_alice, direct_bob):
        with direct_expect_revert("at least"):
            open_agreement(
                direct_vm_holder.vm, escrow, direct_alice, direct_bob,
                deadline=T0 + 60,
            )

    def test_spec_too_short_reverts(self, escrow, direct_alice, direct_bob):
        with direct_expect_revert("spec must be"):
            open_agreement(
                direct_vm_holder.vm, escrow, direct_alice, direct_bob,
                spec="too short",
            )


class TestAcceptance:
    def test_accept_locks_contractor_and_bond(self, committed, escrow, direct_bob):
        rec = state_of(escrow, committed)
        assert rec["contractor"] == direct_bob.as_hex
        assert rec["bond"] == BOND
        assert rec["fee"] == 2 * BASE_FEE
        assert escrow.get_total_escrowed() == DEPOSIT + BOND

    def test_depositor_cannot_accept_own_agreement(self, opened, escrow, direct_alice):
        with direct_expect_revert("cannot accept their own"):
            accept_agreement(direct_vm_holder.vm, escrow, direct_alice, opened)

    def test_wrong_bond_value_reverts(self, opened, escrow, direct_bob):
        with direct_expect_revert("attach exactly"):
            accept_agreement(
                direct_vm_holder.vm, escrow, direct_bob, opened, value=BOND
            )

    def test_acceptance_window_closes_before_deadline(
        self, escrow, direct_alice, direct_bob
    ):
        vm = direct_vm_holder.vm
        aid = open_agreement(vm, escrow, direct_alice, direct_bob)
        # jump to 23h before the deadline: inside the 24h blackout
        direct_vm_warp(T0 + WEEK - 23 * 3600)
        with direct_expect_revert("acceptance window closed"):
            accept_agreement(vm, escrow, direct_bob, aid)

    def test_double_accept_reverts(self, committed, escrow, direct_charlie):
        with direct_expect_revert("already has a contractor"):
            accept_agreement(
                direct_vm_holder.vm, escrow, direct_charlie, committed
            )


class TestDeliveryAndCancellation:
    def test_only_contractor_can_deliver(self, committed, escrow, direct_alice):
        with direct_expect_revert("only the contractor"):
            vm = direct_vm_holder.vm
            vm.sender = direct_alice
            escrow.deliver(committed)

    def test_deliver_records_timestamp_once(self, committed, escrow, direct_bob):
        vm = direct_vm_holder.vm
        direct_vm_warp(T0 + 3600)
        vm.sender = direct_bob
        escrow.deliver(committed)
        assert state_of(escrow, committed)["delivered_at"] == T0 + 3600
        with direct_expect_revert("already reported"):
            escrow.deliver(committed)

    def test_deliver_after_deadline_reverts(self, committed, escrow, direct_bob):
        direct_vm_warp(T0 + WEEK + 10)
        with direct_expect_revert("deadline passed"):
            vm = direct_vm_holder.vm
            vm.sender = direct_bob
            escrow.deliver(committed)

    def test_mutual_cancellation_refunds_everything(
        self, committed, escrow, direct_alice, direct_bob
    ):
        vm = direct_vm_holder.vm
        vm.sender = direct_alice
        escrow.approve_cancellation(committed)
        # one signature alone must NOT settle
        assert state_of(escrow, committed)["state"] == 0
        vm.sender = direct_bob
        escrow.approve_cancellation(committed)
        rec = state_of(escrow, committed)
        assert rec["state"] == REFUNDED
        assert rec["ruling"]["outcome"] == REFUNDED
        assert escrow.get_total_escrowed() == 0

    def test_stranger_cannot_consent(self, committed, escrow, direct_charlie):
        with direct_expect_revert("only agreement parties"):
            vm = direct_vm_holder.vm
            vm.sender = direct_charlie
            escrow.approve_cancellation(committed)


# ---------------------------------------------------------------------------
# 2. Resolution with mocked adjudication (happy paths)
# ---------------------------------------------------------------------------


class TestResolution:
    def test_resolution_requires_delivery_or_expired_deadline(
        self, committed, escrow, direct_charlie
    ):
        with direct_expect_revert("resolvable only after"):
            resolve(direct_vm_holder.vm, escrow, direct_charlie, committed)

    def test_fulfilled_pays_pot_to_contractor(
        self, committed, escrow, direct_bob, direct_charlie
    ):
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(verdict(FULFILLED))
        resolve(vm, escrow, direct_charlie, committed)
        rec = state_of(escrow, committed)
        assert rec["state"] == FULFILLED
        assert rec["ruling"]["outcome"] == FULFILLED
        assert len(rec["ruling"]["reason"]) > 0
        assert escrow.get_total_escrowed() == 0

    def test_failed_pays_pot_to_depositor(
        self, committed, escrow, direct_bob, direct_charlie
    ):
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(verdict(FAILED))
        resolve(vm, escrow, direct_charlie, committed, evidence="walls unfinished")
        assert state_of(escrow, committed)["state"] == FAILED

    def test_resolve_after_deadline_without_delivery(
        self, committed, escrow, direct_charlie
    ):
        # contractor vanished; anyone may resolve once the deadline passes
        direct_vm_warp(T0 + WEEK + 5)
        direct_vm_mock_llm(verdict(FAILED))
        resolve(direct_vm_holder.vm, escrow, direct_charlie, committed)
        assert state_of(escrow, committed)["state"] == FAILED

    def test_double_resolution_reverts(self, committed, escrow, direct_bob, direct_charlie):
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(verdict(FULFILLED))
        resolve(vm, escrow, direct_charlie, committed)
        with direct_expect_revert("already resolved"):
            resolve(vm, escrow, direct_charlie, committed)

    def test_evidence_size_cap(self, committed, escrow, direct_bob, direct_charlie):
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        with direct_expect_revert("evidence limited"):
            resolve(vm, escrow, direct_charlie, committed, evidence="x" * 5000)


# ---------------------------------------------------------------------------
# 3. Consensus semantics — the heart of the primitive
# ---------------------------------------------------------------------------


class TestConsensus:
    def test_validator_agrees_on_identical_decision(
        self, committed, escrow, direct_bob
    ):
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(verdict(FAILED))
        resolve(vm, escrow, direct_bob, committed)
        # validator re-runs the same prompt under the same mock: agrees
        assert vm.run_validator() is True

    def test_validator_rejects_differing_decision(
        self, committed, escrow, direct_bob
    ):
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(verdict(FULFILLED))
        resolve(vm, escrow, direct_bob, committed)
        # a dissenting validator saw the opposite outcome: reject -> rotate
        direct_vm_clear_mocks()
        direct_vm_mock_llm(verdict(FAILED))
        assert vm.run_validator() is False

    @pytest.mark.parametrize("bad_payload", [
        "not json at all",
        '{"outcome": "maybe", "reason": ""}',   # wrong enum type
        '{"reason": "missing outcome field"}',
        "[1, 2, 3]",
    ])
    def test_malformed_leader_output_fails_deterministically(
        self, committed, escrow, direct_bob, bad_payload
    ):
        """A leader whose model output is unusable produces a typed,
        deterministic business error — the tx rolls back (no state change)
        instead of storing garbage."""
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(bad_payload)
        with direct_expect_revert("ADJUDICATION_"):
            resolve(vm, escrow, direct_bob, committed)
        assert state_of(escrow, committed)["state"] == 0

    @pytest.mark.parametrize("bad_payload", [
        "not json at all",
        '{"outcome": "maybe", "reason": ""}',   # wrong enum type
        '{"reason": "missing outcome field"}',
        "[1, 2, 3]",
    ])
    def test_error_classification_validator_agreement(
        self, committed, escrow, direct_bob, bad_payload
    ):
        """Validators AGREE a transaction must fail only when an independent
        re-run reproduces the same business-rule failure; they reject it when
        their own model call succeeds. This is what turns transient provider
        hiccups into leader rotation rather than stuck or corrupted state."""
        vm = direct_vm_holder.vm
        # seed a validator capture with a healthy resolution first
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(verdict(FULFILLED))
        resolve(vm, escrow, direct_bob, committed)

        direct_vm_clear_mocks()
        direct_vm_mock_llm(bad_payload)  # validator's own re-run fails the same way
        assert (
            vm.run_validator(leader_error=Exception("ADJUDICATION_UNPARSABLE"))
            is True
        )

        direct_vm_clear_mocks()
        direct_vm_mock_llm(verdict(FULFILLED))  # this validator's run is clean
        assert (
            vm.run_validator(leader_error=Exception("ADJUDICATION_UNPARSABLE"))
            is False
        )

    def test_outcome_enum_enforced_against_leader(
        self, committed, escrow, direct_bob
    ):
        vm = direct_vm_holder.vm
        vm.sender = direct_bob
        escrow.deliver(committed)
        direct_vm_mock_llm(verdict(FULFILLED))
        resolve(vm, escrow, direct_bob, committed)
        # leader claiming an out-of-enum outcome is rejected even if we
        # happened to agree numerically
        assert vm.run_validator(leader_result={"outcome": 9, "reason": "x"}) is False
        assert vm.run_validator(leader_result={"outcome": 1, "reason": "different prose"}) is True


# ---------------------------------------------------------------------------
# Plumbing shims — keep the suite readable whether helpers live on vm or here
# ---------------------------------------------------------------------------

import threading  # noqa: E402


class _VMHolder:
    """Lazy reference filled by autouse fixture so helper classes above can
    reach the current test's vm without changing every call signature."""

    vm = None


direct_vm_holder = _VMHolder()


@pytest.fixture(autouse=True)
def _wire_helpers(direct_vm):
    direct_vm_holder.vm = direct_vm
    yield
    direct_vm_holder.vm = None


def direct_vm_warp(ts: int) -> None:
    direct_vm_holder.vm.warp(iso(ts))


def direct_vm_mock_llm(payload: str) -> None:
    direct_vm_holder.vm.mock_llm(r"neutral adjudicator", payload)


def direct_vm_clear_mocks() -> None:
    direct_vm_holder.vm.clear_mocks()


def direct_expect_revert(fragment: str):
    return direct_vm_holder.vm.expect_revert(fragment)
