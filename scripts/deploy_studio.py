"""Deploy the exact checked-in AdjudicatedEscrow source to GenLayer Studionet.

The private key is read from a 0600 file outside the repository (or DEPLOY_PK
for CI). `--check` prints the deployer address and balance without sending a
transaction, which makes it safe to use while funding a freshly generated
Studionet-only account.
"""

import hashlib
import os
import sys
from pathlib import Path

from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "AdjudicatedEscrow.py"
KEY_PATH = Path.home() / ".secrets" / "adjudicated_escrow_studio_deployer.pk"
BASE_FEE = 10**15  # 0.001 GEN; must match the test fixture economics


def load_private_key() -> str:
    key = os.environ.get("DEPLOY_PK", "").strip()
    if key:
        return key
    if not KEY_PATH.exists():
        raise SystemExit(
            "FATAL: no deployment key. Create the 0600 Studionet-only key at "
            f"{KEY_PATH} or set DEPLOY_PK."
        )
    return KEY_PATH.read_text(encoding="utf-8").strip()


def receipt_field(receipt, field: str):
    if isinstance(receipt, dict):
        return receipt.get(field)
    return getattr(receipt, field, None)


def main() -> None:
    code = CONTRACT_PATH.read_text(encoding="utf-8")
    source_sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
    account = create_account(load_private_key())
    client = create_client(chain=studionet, account=account)
    balance = client.get_balance(account.address)

    print("deployer:", account.address)
    print("balance_wei:", balance)
    print("source_sha256:", source_sha256)

    if "--check" in sys.argv:
        return
    if balance <= 0:
        raise SystemExit("FATAL: fund the Studionet-only deployer before deploying.")

    tx_hash = client.deploy_contract(
        code=code,
        args=[BASE_FEE],
    )
    print("tx_hash:", tx_hash)

    receipt = client.wait_for_transaction_receipt(
        tx_hash,
        status=TransactionStatus.FINALIZED,
        interval=3000,
        retries=120,
        full_transaction=True,
    )
    contract_address = receipt_field(receipt, "contract_address")
    print("final_status:", receipt_field(receipt, "status"))
    print("contract_address:", contract_address)
    print("explorer_contract:", f"https://explorer-studio.genlayer.com/address/{contract_address}")
    print("explorer_transaction:", f"https://explorer-studio.genlayer.com/tx/{tx_hash}")


if __name__ == "__main__":
    main()
