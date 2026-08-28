# AdjudicatedEscrow — Contract-Acquired Evidence Escrow

AdjudicatedEscrow is a GenLayer bonded escrow primitive for obligations requiring substantive judgment. The depositor posts payment plus fee; the contractor posts a 25% forfeitable bond plus fee. Settlement is decided by validators, while settlement facts are acquired by the contract itself rather than supplied as arbitrary resolver text.

> **Lint-clean correction:** `resolve(agreement_id)` has no evidence parameter. It resolves only from the immutable HTTPS manifest committed at `open_agreement` and accepted when the contractor bonds.

## Verified deployment

| Item | Evidence |
| --- | --- |
| Contract | [`0x467f95a5F4E284C89bd892B3538987C9182020a4`](https://explorer-studio.genlayer.com/address/0x467f95a5F4E284C89bd892B3538987C9182020a4) |
| Deployment transaction | [`0x62d5544331a049e4ebd2703a33d57dea6452eea2d3f628ce782c97801e73dfc8`](https://explorer-studio.genlayer.com/tx/0x62d5544331a049e4ebd2703a33d57dea6452eea2d3f628ce782c97801e73dfc8) |
| Explorer result | **FINALIZED**; constructor **SUCCESS**; consensus **Accepted** |
| Source commit | [`d9d1d66`](https://github.com/farzad-eth/genlayer-adjudicated-escrow/commit/d9d1d66) |
| Direct Mode tests | **36 passed** |

## Evidence and consensus model

At agreement creation, the depositor commits a bounded canonical newline-delimited manifest containing 1–3 unique HTTPS URLs. The contractor accepts that exact manifest when bonding. During resolution, the callback passed directly to `run_nondet_unsafe` independently calls `gl.nondet.web.render(url, mode="text")` for each committed source. Retrieved content is size-capped and framed as untrusted data before adjudication. Validators independently repeat retrieval and adjudication; only the outcome enum is compared, while reasoning is audit-only. Retrieval faults rotate the leader rather than becoming a settlement outcome.

| Risk | Control |
| --- | --- |
| Resolver injects evidence | `resolve(id)` has no evidence argument. |
| Source set changes after acceptance | The manifest is immutable after bonding. |
| Leader output is trusted | Validators independently retrieve sources and rerun the callback. |
| Free-form text breaks consensus | Only outcome `1`, `2`, or `3` is compared. |
| Prompt injection | Agreement and retrieved pages are explicitly untrusted data. |

## Interface

| Method | Description |
| --- | --- |
| `open_agreement(contractor_hint, spec, deadline, evidence_manifest)` | Commits the HTTPS evidence manifest and locks the depositor payment. |
| `accept_agreement(id)` | Locks the contractor bond and binds the manifest. |
| `deliver(id)` | Records delivery notice. |
| `resolve(id)` | Permissionlessly retrieves committed sources and settles after validator agreement. |
| `approve_cancellation(id)` | Mutual cancellation path. |
| `get_agreement(id)` | Returns auditable agreement state and ruling. |

The Direct Mode suite covers lifecycle invariants, manifest validation, contract-side retrieval, validator replay, divergent outcomes, malformed model output, error classification, prompt-injection framing, and escrow accounting. The final lint-refactored source completed with **36 passed**.

See the [contract source](contracts/AdjudicatedEscrow.py), [tests](tests/test_adjudicated_escrow.py), and [deployment Explorer page](https://explorer-studio.genlayer.com/address/0x467f95a5F4E284C89bd892B3538987C9182020a4).

MIT License; see [LICENSE](LICENSE).
