"""Direct Mode lifecycle, consensus, evidence, and accounting tests."""

import pytest

from conftest import (
    BASE_FEE,
    BOND,
    DEPOSIT,
    EVIDENCE_TEXT,
    MANIFEST_ALT,
    SPEC_ALT,
    T0,
    WEEK,
    accept_agreement,
    mock_evidence,
    mock_llm,
    open_agreement,
    resolve,
    state_of,
    verdict,
    warp,
)

FULFILLED = 1
FAILED = 2
REFUNDED = 3


@pytest.fixture(autouse=True)
def strict_direct_mocks(direct_vm):
    """Fail if a resolution reaches an uncommitted or unmocked URL."""
    direct_vm._strict_mock_mode = True


class TestDeploymentAndOpening:
    def test_config_and_empty_registry(self, escrow, direct_charlie):
        cfg = escrow.config()
        assert cfg["arbiter_hint"] == direct_charlie.as_hex
        assert cfg["fee_recipient"] == direct_charlie.as_hex
        assert cfg["base_fee"] == BASE_FEE
        assert cfg["bond_bps"] == 2500
        assert escrow.agreement_count() == 0
        assert escrow.get_total_escrowed() == 0

    def test_constructor_rejects_zero_fee(self, direct_deploy, direct_vm, direct_charlie):
        direct_vm.sender = direct_charlie
        with pytest.raises(Exception, match="safe non-zero"):
            direct_deploy(
                "contracts/AdjudicatedEscrow.py",
                0,
            )

    def test_open_tracks_complete_liability(self, escrow, direct_vm, direct_alice, direct_bob):
        agreement_id = open_agreement(direct_vm, escrow, direct_alice, direct_bob)
        record = state_of(escrow, agreement_id)
        assert record["depositor"] == direct_alice.as_hex
        assert record["deposit"] == DEPOSIT
        assert record["bond"] == 0
        assert record["fee"] == BASE_FEE
        assert record["evidence_manifest"] == "https://evidence.example/receipt"
        assert record["evidence_source_count"] == 1
        assert escrow.get_total_escrowed() == DEPOSIT + BASE_FEE

    def test_open_rejects_tiny_deposit_before_zero_bond(self, escrow, direct_vm, direct_alice, direct_bob):
        with direct_vm.expect_revert("deposit must be"):
            open_agreement(
                direct_vm,
                escrow,
                direct_alice,
                direct_bob,
                value=BASE_FEE + 3,
            )

    def test_open_rejects_short_spec_and_near_deadline(self, escrow, direct_vm, direct_alice, direct_bob):
        with direct_vm.expect_revert("spec must be"):
            open_agreement(
                direct_vm, escrow, direct_alice, direct_bob, spec="too short"
            )
        with direct_vm.expect_revert("at least"):
            open_agreement(
                direct_vm,
                escrow,
                direct_alice,
                direct_bob,
                deadline=T0 + 60,
            )

    @pytest.mark.parametrize(
        "manifest, error",
        [
            ("http://evidence.example/plain", "valid HTTPS"),
            ("https://evidence.example/a\nhttps://evidence.example/a", "duplicate"),
            ("https://evidence.example/a\nhttps://evidence.example/b\nhttps://evidence.example/c\nhttps://evidence.example/d", "1..3"),
            ("", "1..3"),
        ],
    )
    def test_manifest_is_bounded_and_canonical(self, escrow, direct_vm, direct_alice, direct_bob, manifest, error):
        with direct_vm.expect_revert(error):
            open_agreement(
                direct_vm,
                escrow,
                direct_alice,
                direct_bob,
                manifest=manifest,
            )

    def test_multiple_manifest_sources_are_canonicalized(self, escrow, direct_vm, direct_alice, direct_bob):
        agreement_id = open_agreement(
            direct_vm,
            escrow,
            direct_alice,
            direct_bob,
            manifest="  https://evidence.example/a  \n\nhttps://evidence.example/b ",
        )
        record = state_of(escrow, agreement_id)
        assert record["evidence_manifest"] == MANIFEST_ALT
        assert record["evidence_source_count"] == 2


class TestAcceptanceAndCancellation:
    def test_acceptance_tracks_bond_and_second_fee(self, committed, escrow):
        record = state_of(escrow, committed)
        assert record["bond"] == BOND
        assert record["fee"] == 2 * BASE_FEE
        assert record["accepted"] is True
        assert escrow.get_total_escrowed() == DEPOSIT + BOND + 2 * BASE_FEE

    def test_depositor_cannot_accept_and_wrong_value_reverts(self, opened, escrow, direct_vm, direct_alice, direct_bob):
        with direct_vm.expect_revert("cannot accept"):
            accept_agreement(direct_vm, escrow, direct_alice, opened)
        with direct_vm.expect_revert("attach exactly"):
            accept_agreement(direct_vm, escrow, direct_bob, opened, value=BOND)

    def test_cancellation_requires_contractor_bond(self, opened, escrow, direct_vm, direct_alice):
        direct_vm.sender = direct_alice
        with direct_vm.expect_revert("bonded contractor"):
            escrow.approve_cancellation(opened)

    def test_mutual_cancellation_returns_stake_and_both_attached_fees(
        self, committed, escrow, direct_vm, direct_alice, direct_bob, monkeypatch
    ):
        transfers = []
        monkeypatch.setattr(
            escrow._instance,
            "_pay",
            lambda recipient, amount: transfers.append((recipient.as_hex, int(amount))),
        )
        direct_vm.sender = direct_alice
        escrow.approve_cancellation(committed)
        assert transfers == []
        direct_vm.sender = direct_bob
        escrow.approve_cancellation(committed)
        assert transfers == [
            (direct_alice.as_hex, DEPOSIT + BASE_FEE),
            (direct_bob.as_hex, BOND + BASE_FEE),
        ]
        assert state_of(escrow, committed)["state"] == REFUNDED
        assert escrow.get_total_escrowed() == 0


class TestResolutionAndExactDistribution:
    def _deliver_and_prepare(self, committed, escrow, direct_vm, direct_bob, outcome):
        direct_vm.sender = direct_bob
        escrow.deliver(committed)
        mock_evidence(direct_vm)
        mock_llm(direct_vm, verdict(outcome))

    @pytest.mark.parametrize(
        "outcome, expected_participant",
        [
            (FULFILLED, "contractor"),
            (FAILED, "depositor"),
            (REFUNDED, "split"),
        ],
    )
    def test_each_normal_ruling_distributes_every_attached_unit_once(
        self,
        committed,
        escrow,
        direct_vm,
        direct_alice,
        direct_bob,
        direct_charlie,
        monkeypatch,
        outcome,
        expected_participant,
    ):
        transfers = []
        monkeypatch.setattr(
            escrow._instance,
            "_pay",
            lambda recipient, amount: transfers.append((recipient.as_hex, int(amount))),
        )
        self._deliver_and_prepare(committed, escrow, direct_vm, direct_bob, outcome)
        resolve(direct_vm, escrow, direct_charlie, committed)

        if expected_participant == "contractor":
            expected = [(direct_bob.as_hex, DEPOSIT + BOND)]
        elif expected_participant == "depositor":
            expected = [(direct_alice.as_hex, DEPOSIT + BOND)]
        else:
            expected = [(direct_alice.as_hex, DEPOSIT), (direct_bob.as_hex, BOND)]
        expected.append((direct_charlie.as_hex, 2 * BASE_FEE))

        assert transfers == expected
        assert sum(amount for _, amount in transfers) == DEPOSIT + BOND + 2 * BASE_FEE
        assert state_of(escrow, committed)["state"] == outcome
        assert escrow.get_total_escrowed() == 0

    def test_resolution_requires_delivery_or_expired_deadline(self, committed, escrow, direct_vm, direct_charlie):
        with direct_vm.expect_revert("resolvable only after"):
            resolve(direct_vm, escrow, direct_charlie, committed)

    def test_deadline_allows_resolution_without_delivery(self, committed, escrow, direct_vm, direct_charlie, monkeypatch):
        monkeypatch.setattr(escrow._instance, "_pay", lambda *_: None)
        warp(direct_vm, T0 + WEEK + 1)
        mock_evidence(direct_vm)
        mock_llm(direct_vm, verdict(FAILED))
        resolve(direct_vm, escrow, direct_charlie, committed)
        assert state_of(escrow, committed)["state"] == FAILED

    def test_resolve_has_no_caller_evidence_parameter(self, committed, escrow, direct_vm, direct_charlie):
        direct_vm.sender = direct_charlie
        with pytest.raises(TypeError):
            escrow.resolve(committed, "permissionless prose must not be accepted")

    def test_resolve_uses_committed_web_source(self, committed, escrow, direct_vm, direct_bob, direct_charlie, monkeypatch):
        monkeypatch.setattr(escrow._instance, "_pay", lambda *_: None)
        direct_vm.sender = direct_bob
        escrow.deliver(committed)
        mock_evidence(direct_vm, EVIDENCE_TEXT)
        mock_llm(direct_vm, verdict(FULFILLED))
        resolve(direct_vm, escrow, direct_charlie, committed)
        assert state_of(escrow, committed)["state"] == FULFILLED


class TestConsensus:
    def _captured_resolution(self, committed, escrow, direct_vm, direct_bob, outcome=FULFILLED):
        direct_vm.sender = direct_bob
        escrow.deliver(committed)
        mock_evidence(direct_vm)
        mock_llm(direct_vm, verdict(outcome))
        resolve(direct_vm, escrow, direct_bob, committed)

    def test_validator_independently_retrieves_and_agrees(self, committed, escrow, direct_vm, direct_bob, monkeypatch):
        monkeypatch.setattr(escrow._instance, "_pay", lambda *_: None)
        self._captured_resolution(committed, escrow, direct_vm, direct_bob, FAILED)
        assert direct_vm.run_validator() is True

    def test_validator_rejects_differing_outcome(self, committed, escrow, direct_vm, direct_bob, monkeypatch):
        monkeypatch.setattr(escrow._instance, "_pay", lambda *_: None)
        self._captured_resolution(committed, escrow, direct_vm, direct_bob, FULFILLED)
        direct_vm.clear_mocks()
        mock_evidence(direct_vm)
        mock_llm(direct_vm, verdict(FAILED))
        assert direct_vm.run_validator() is False

    @pytest.mark.parametrize(
        "payload",
        [
            "not json",
            '{"outcome": "fulfilled"}',
            '{"reason": "missing outcome"}',
            "[1, 2, 3]",
        ],
    )
    def test_malformed_model_output_reverts_without_settlement(
        self, committed, escrow, direct_vm, direct_bob, payload
    ):
        direct_vm.sender = direct_bob
        escrow.deliver(committed)
        mock_evidence(direct_vm)
        mock_llm(direct_vm, payload)
        with direct_vm.expect_revert("ADJUDICATION_"):
            resolve(direct_vm, escrow, direct_bob, committed)
        assert state_of(escrow, committed)["state"] == 0
        assert escrow.get_total_escrowed() == DEPOSIT + BOND + 2 * BASE_FEE

    def test_validator_agrees_only_on_reproduced_business_error(
        self, committed, escrow, direct_vm, direct_bob, monkeypatch
    ):
        monkeypatch.setattr(escrow._instance, "_pay", lambda *_: None)
        self._captured_resolution(committed, escrow, direct_vm, direct_bob)
        direct_vm.clear_mocks()
        mock_evidence(direct_vm)
        mock_llm(direct_vm, "not json")
        assert direct_vm.run_validator(leader_error=Exception("ADJUDICATION_UNPARSABLE")) is True

        direct_vm.clear_mocks()
        mock_evidence(direct_vm)
        mock_llm(direct_vm, verdict(FULFILLED))
        assert direct_vm.run_validator(leader_error=Exception("ADJUDICATION_UNPARSABLE")) is False

    def test_validator_ignores_leader_reason_text(self, committed, escrow, direct_vm, direct_bob, monkeypatch):
        monkeypatch.setattr(escrow._instance, "_pay", lambda *_: None)
        self._captured_resolution(committed, escrow, direct_vm, direct_bob)
        assert direct_vm.run_validator(
            leader_result={"outcome": FULFILLED, "reason": "untrusted arbitrary prose"}
        ) is True
        assert direct_vm.run_validator(
            leader_result={"outcome": 9, "reason": "invalid enum"}
        ) is False
