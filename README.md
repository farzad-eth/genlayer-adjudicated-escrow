# AdjudicatedEscrow — Contract-Acquired Evidence Escrow

AdjudicatedEscrow is a GenLayer bonded escrow primitive for obligations that require substantive judgment. A depositor posts payment plus fee, and a contractor posts a 25% forfeitable bond plus fee. Settlement is decided by GenLayer validators, but the facts that determine settlement are acquired by the contract itself—not supplied as arbitrary text by a permissionless resolver.

> **Corrective guarantee:** `resolve(agreement_id)` has no evidence parameter. It resolves only from the HTTPS evidence manifest committed during `open_agreement` and accepted by the contractor when bonding the agreement.

## Verified Live Deployment

| Item | Evidence |
| --- | --- |
| Contract | [`0x0A8E5B4fa9c29546AC719ca5A0e9D1a4fB02Bd07`](https://explorer-studio.genlayer.com/address/0x0A8E5B4fa9c29546AC719ca5A0e9D1a4fB02Bd07) |
| Deployment transaction | [`0x3ba3269e32a247d4e9ef9cb553cde4053cc1e5a574579061c0974effad71f12a`](https://explorer-studio.genlayer.com/tx/0x3ba3269e32a247d4e9ef9cb553cde4053cc1e5a574579061c0974effad71f12a) |
| Explorer result | **FINALIZED**; constructor **SUCCESS**; consensus **Accepted** |
| Direct Mode tests | **36 passed** |

## Corrected Evidence Model

At agreement creation, the depositor commits a bounded, canonical newline-delimited manifest of one to three unique HTTPS URLs. The contractor’s acceptance binds them to that exact source set. During `resolve`, the leader and every validator independently call `gl.nondet.web.render(url, mode="text")` for every committed URL. Retrieved material is bounded and explicitly framed as untrusted data before adjudication.

| Risk | Contract control |
| --- | --- |
| Resolver injects self-serving text | `resolve(id)` accepts no evidence argument. |
| A party changes the source set after acceptance | The manifest is stored before bonding and is never mutable. |
| Validators accept a leader’s claimed facts | Each validator independently retrieves the committed URLs and reruns adjudication. |
| Free-form model text prevents consensus | Only the `outcome` enum is compared; `reason` is audit-only. |
| A transient source outage settles an escrow | Retrieval faults are transient and reject the leader rather than become a settlement outcome. |
| Prompt injection from a deliverable page | Retrieved content is size-capped and treated as untrusted data. |

## Lifecycle

```text
open_agreement(spec, deadline, evidence_manifest)
  -> depositor locks payment plus fee; manifest becomes immutable
accept_agreement(id)
  -> contractor locks 25% bond plus fee and accepts that manifest
deliver(id) or deadline passes
resolve(id) by anyone
  -> validators independently fetch the manifest URLs and compare only outcome
  -> fulfilled: contractor receives principal pot minus fees
  -> failed: depositor receives principal pot minus fees
  -> refunded: contract applies the refund rule
```

## Interface

| Method | Type | Description |
| --- | --- | --- |
| `open_agreement(contractor_hint, spec, deadline, evidence_manifest)` | Payable write | Commits 1–3 HTTPS evidence sources before acceptance. |
| `accept_agreement(id)` | Payable write | Locks the required contractor bond. |
| `deliver(id)` | Write | Records contractor delivery notice. |
| `resolve(id)` | Permissionless write | Retrieves committed sources and settles only after validator agreement. |
| `approve_cancellation(id)` | Write | Mutual cancellation path. |
| `get_agreement(id)` | View | Returns agreement state, committed manifest, and ruling. |

## Test Coverage

The Direct Mode suite covers lifecycle invariants, manifest validation, contract-side source retrieval, empty-source failure, prompt-injection framing, validator replay, divergent outcomes, malformed LLM results, error classification, and escrow accounting. The verified final run completed with **36 passed**.

## References

[GenLayer web content retrieval](https://docs.genlayer.com/developers/intelligent-contracts/examples/fetch-web-content) · [GenLayer testing guidance](https://docs.genlayer.com/developers/intelligent-contracts/testing) · [GenLayer networks](https://docs.genlayer.com/developers/networks)

## License

MIT — see [LICENSE](LICENSE).
