# AdjudicatedEscrow — Contract-Acquired Evidence Escrow

AdjudicatedEscrow is a GenLayer bonded escrow primitive for obligations requiring substantive judgment. A depositor posts payment plus an adjudication fee; a contractor posts a **25% forfeitable bond plus an adjudication fee**. Settlement facts are acquired by the contract itself, not supplied as arbitrary resolver text, and every terminal path distributes the entire attached value exactly once.

> **Current corrected deployment:** the exact source at commit [`3565f6d`](https://github.com/farzad-eth/genlayer-adjudicated-escrow/commit/3565f6d9bde26b24ddb3ae2c89e864e0ca528808) is deployed on Studionet. The public GitHub file and the locally deployed file have the same SHA-256: `59b6fc8124e733fd4ea2135c52909b4385bcecc077c197f44c2bc3f61bf83377`.

## Verified deployment

| Item | Evidence |
| --- | --- |
| Contract | [`0x5369686c013561ECfDA9D92275D632F188c7Bb20`](https://explorer-studio.genlayer.com/address/0x5369686c013561ECfDA9D92275D632F188c7Bb20) |
| Deployment transaction | [`0x705eb5f83aac8a5441e53132b7b2562beead8524378e46deea3affe86bddf984`](https://explorer-studio.genlayer.com/tx/0x705eb5f83aac8a5441e53132b7b2562beead8524378e46deea3affe86bddf984) |
| Explorer result | **Contract** address; transaction **FINALIZED**; constructor **SUCCESS**; consensus **Accepted** |
| Deployed source | [`contracts/AdjudicatedEscrow.py` at commit `3565f6d`](https://github.com/farzad-eth/genlayer-adjudicated-escrow/blob/3565f6d9bde26b24ddb3ae2c89e864e0ca528808/contracts/AdjudicatedEscrow.py) |
| Direct Mode validation | `gltest tests/ -v` — **29 passed** |

## Corrected settlement accounting

Every accepted agreement has a complete liability of `deposit + bond + fee`, where `fee` accumulates both attached adjudication fees. `total_escrowed` records this same complete liability. On every terminal state, `_apply_ruling` first derives that liability, makes transfers totaling exactly that amount, and then decreases the tracked liability once. Thus, no normal ruling can strand fees or subtract them twice from the participant pot.

| Terminal outcome | Participant distribution | Fee distribution | Total transferred |
| --- | --- | --- | --- |
| Fulfilled | Contractor receives `deposit + bond` | Recipient receives `fee` | `deposit + bond + fee` |
| Failed | Depositor receives `deposit + bond` | Recipient receives `fee` | `deposit + bond + fee` |
| Refunded | Depositor and contractor receive their respective stakes | Recipient receives `fee` | `deposit + bond + fee` |
| Mutual cancellation | Depositor receives deposit; contractor receives bond | Recipient receives both attached fees | `deposit + bond + fee` |

The constructor requires a non-zero bounded base fee. Agreement creation constrains the deposit, and acceptance checks bond-plus-fee and aggregate-fee bounds before mutation. This prevents overflow or underflow in reusable, adversarially parameterized deployments. To avoid generic UI address-serialization defects, the one-argument constructor `__init__(base_fee)` binds both the arbiter hint and fee recipient to the immutable deploying account.

## Evidence and consensus model

At agreement creation, the depositor commits a bounded canonical newline-delimited manifest containing **one to three unique HTTPS URLs**. The contractor accepts that exact manifest when bonding. `resolve(agreement_id)` accepts **no evidence parameter**.

During resolution, the direct local `adjudicate()` callback passed to `run_nondet_unsafe` independently calls `gl.nondet.web.render(url, mode="text")` for each committed source. Retrieved content is size-capped and framed as untrusted data before adjudication. Validators independently repeat retrieval and adjudication; only the outcome enum is compared, while explanatory reasoning is audit-only. Retrieval faults rotate the leader rather than becoming a settlement outcome.

| Risk | Control |
| --- | --- |
| Resolver injects evidence | `resolve(id)` has no evidence argument. |
| Source set changes after acceptance | The manifest is immutable after bonding. |
| GenVM cannot trace web acquisition | `web.render` is directly inside the consensus callback; no nested acquisition helper remains. |
| Leader output is trusted | Validators independently retrieve sources and rerun the callback. |
| Free-form text breaks consensus | Only outcome `1`, `2`, or `3` is compared. |
| Prompt injection | Agreement and retrieved pages are explicitly untrusted data. |
| Fee value is stranded or double-counted | Full liability is tracked and exact distribution is asserted for every terminal state. |

## Interface

| Method | Description |
| --- | --- |
| `open_agreement(contractor_hint, spec, deadline, evidence_manifest)` | Commits the HTTPS evidence manifest and locks the depositor payment plus fee. |
| `accept_agreement(id)` | Locks the contractor bond plus fee and binds the manifest. |
| `deliver(id)` | Records a delivery notice. |
| `resolve(id)` | Permissionlessly retrieves committed sources and settles after validator agreement. |
| `approve_cancellation(id)` | Executes the mutually approved unwind. |
| `get_agreement(id)` | Returns auditable agreement state and ruling. |

The Direct Mode suite covers lifecycle invariants, manifest validation, contract-side retrieval, validator replay, divergent outcomes, malformed model output, error classification, prompt-injection framing, bounded arithmetic, complete liability tracking, and exact normal-ruling distributions.

See the [contract source](contracts/AdjudicatedEscrow.py), [test suite](tests/test_adjudicated_escrow.py), and [deployment audit](DEPLOYMENT_AUDIT.md).

MIT License; see [LICENSE](LICENSE).
