# Deployment Audit Notes

The current accounting correction is validated locally with `gltest tests/ -v`. The Studio UI source import preserved the multiline contract source, and its schema loader accepted the current contract header. An initial Studio UI deployment transaction (`0xcf5a3cc4fec33549e337a313e0457814eb8900438ea422e423c3b49dac18e50c`) reached `FINALIZED` consensus but its constructor execution failed: the Studio generic address fields were serialized as integers, producing `AttributeError: 'int' object has no attribute 'as_bytes'`. It is not evidence for the corrected deployment.

To eliminate that UI serialization defect while retaining the deployed recipient configuration, this revision binds both `arbiter_hint` and `fee_recipient` to `gl.message.sender_address` during construction and accepts only `base_fee` as a constructor argument. The deployed recipient remains the deployer, exactly as intended for the test deployment. The Direct Mode fixtures set the deployer explicitly and assert this binding.

## Final verified deployment

The exact source published in GitHub commit [`3565f6d`](https://github.com/farzad-eth/genlayer-adjudicated-escrow/commit/3565f6d9bde26b24ddb3ae2c89e864e0ca528808) was deployed in Normal (full-consensus) mode. Its SHA-256 is `59b6fc8124e733fd4ea2135c52909b4385bcecc077c197f44c2bc3f61bf83377`; fetching the public commit source produced the identical digest and byte-for-byte comparison result.

| Check | Verified evidence |
| --- | --- |
| Contract | [`0x5369686c013561ECfDA9D92275D632F188c7Bb20`](https://explorer-studio.genlayer.com/address/0x5369686c013561ECfDA9D92275D632F188c7Bb20) |
| Deployment transaction | [`0x705eb5f83aac8a5441e53132b7b2562beead8524378e46deea3affe86bddf984`](https://explorer-studio.genlayer.com/tx/0x705eb5f83aac8a5441e53132b7b2562beead8524378e46deea3affe86bddf984) |
| Explorer address identity | **Contract**, created by the deployer account |
| Transaction result | **FINALIZED**, constructor **SUCCESS**, consensus **Accepted** |
| Local validation | `gltest tests/ -v` — **29 passed** |

Relevant external references include the [GenLayer deployment guide](https://docs.genlayer.com/developers/intelligent-contracts/deploying), the [GenVM runner specification](https://sdk.genlayer.com/v0.2.9/spec/02-execution-environment/04-runners.html), and the failed Studio transaction [Explorer page](https://explorer-studio.genlayer.com/tx/0xcf5a3cc4fec33549e337a313e0457814eb8900438ea422e423c3b49dac18e50c).
