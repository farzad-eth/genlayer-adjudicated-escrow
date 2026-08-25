# Deploy AdjudicatedEscrow to GenLayer Testnet Bradbury
# Reads the private key from env var DEPLOY_PK (never written to disk).
import os
import sys

from genlayer_py import create_client, create_account
from genlayer_py.chains import testnet_bradbury

CONTRACT = os.path.join(os.path.dirname(__file__), "..", "contracts", "AdjudicatedEscrow.py")

pk = os.environ.get("DEPLOY_PK")
if not pk:
    print("FATAL: set DEPLOY_PK env var")
    sys.exit(2)

account = create_account(pk)
print("deployer:", account.address)

client = create_client(chain=testnet_bradbury, account=account)
bal = client.get_balance(account.address)
print("balance (wei):", bal)

with open(CONTRACT, "r", encoding="utf-8") as f:
    code = f.read()

BURNER = account.address  # fee recipient + arbiter hint = deployer burner
BASE_FEE = 10**15  # 0.001 GEN

tx = client.deploy_contract(
    code=code,
    args=[BURNER, BURNER, BASE_FEE],
)
print("tx hash:", tx)

rcpt = client.wait_for_transaction_receipt(tx, timeout=300)
status = getattr(rcpt, "status", rcpt.get("status") if isinstance(rcpt, dict) else "?")
addr = getattr(rcpt, "contract_address", None) or (rcpt.get("contract_address") if isinstance(rcpt, dict) else None)
print("status:", status)
print("contract_address:", addr)
print("EXPLORER:", f"https://explorer-bradbury.genlayer.com/address/{addr}")
