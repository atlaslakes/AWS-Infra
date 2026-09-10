"""
End-to-end ACH sandbox test — proves money moves and "lands".

No SDKs, no deployed Lambdas, no Base44. Talks straight to the Plaid and Dwolla
SANDBOX REST APIs using the credentials already in .env:

    PLAID_CLIENT_ID / PLAID_SECRET / PLAID_ENV=sandbox
    DWOLLA_KEY / DWOLLA_SECRET / DWOLLA_ENV=sandbox
    DWOLLA_MASTER_FUNDING_SOURCE_URL   (Atlas Lakes' business bank account)

What it does:
  1. Plaid sandbox: spin up a fake verified bank (First Platypus Bank) and mint a
     Dwolla processor_token for a checking account.  (done twice)
  2. Dwolla sandbox: create two Customers -- "TestCustomer" (payer) and
     "TestVendor" (payee) -- and attach each Plaid-verified account as a funding
     source (instant verification, no micro-deposits).
  3. Initiate transfers:
        a) TestCustomer  -> TestVendor          $12.34   (customer-collection shape)
        b) TestVendor    -> TestCustomer         $ 5.00   (vendor-payout shape)
        c) TestCustomer  -> MASTER funding src   $ 3.21   (real inbound collection,
                                                           only if the master FS is
                                                           usable as a destination)
  4. Settle: try POST /sandbox/simulations, then poll each transfer until it reads
     `processed` (= landed) or `failed`. If the programmatic simulator is not
     enabled on this Dwolla account, the run stops with the transfers `pending`
     and its state saved; advance them from the Dwolla sandbox dashboard
     ("Sandbox" > "Process bank transfers") and then:
         python scripts/setup/test_ach_sandbox.py --recheck

Also verifies (and reports) the DWOLLA_MASTER_FUNDING_SOURCE_URL from .env, and
verifies it via micro-deposits if it is still `unverified` (the master account
setup script adds it unverified).

Safe: Dwolla/Plaid sandbox only, no real banks, no real money. Creates fresh
sandbox Customers each run (throwaway).

Run from the repo root:
    python scripts/setup/test_ach_sandbox.py            # full run
    python scripts/setup/test_ach_sandbox.py --recheck  # re-poll the last run
"""

import os
import sys
import json
import time
import base64
from pathlib import Path

import requests

STATE_FILE = Path(__file__).with_name(".test_ach_sandbox_state.json")

PLAID_BASE = "https://sandbox.plaid.com"
DWOLLA_BASE = "https://api-sandbox.dwolla.com"
DWOLLA_HEADERS = {
    "Accept": "application/vnd.dwolla.v1.hal+json",
    "Content-Type": "application/vnd.dwolla.v1.hal+json",
}
PLAID_SANDBOX_INSTITUTION = "ins_109508"  # First Platypus Bank (supports auth)


# --------------------------------------------------------------------------- #
# env
# --------------------------------------------------------------------------- #
def load_dotenv():
    """Minimal .env loader so the script runs with no wrapper. Real env wins."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_dotenv()

PLAID_CLIENT_ID = os.environ.get("PLAID_CLIENT_ID")
PLAID_SECRET = os.environ.get("PLAID_SECRET")
DWOLLA_KEY = os.environ.get("DWOLLA_KEY")
DWOLLA_SECRET = os.environ.get("DWOLLA_SECRET")
MASTER_FS = os.environ.get("DWOLLA_MASTER_FUNDING_SOURCE_URL")

_missing = [
    n for n, v in [
        ("PLAID_CLIENT_ID", PLAID_CLIENT_ID), ("PLAID_SECRET", PLAID_SECRET),
        ("DWOLLA_KEY", DWOLLA_KEY), ("DWOLLA_SECRET", DWOLLA_SECRET),
    ] if not v
]
if _missing:
    sys.exit(f"Missing env vars: {', '.join(_missing)}")

for name, val in [("PLAID_ENV", os.environ.get("PLAID_ENV")),
                  ("DWOLLA_ENV", os.environ.get("DWOLLA_ENV"))]:
    if val and val.lower() not in ("sandbox", ""):
        sys.exit(f"{name}={val!r} — refusing to run against anything but sandbox.")


def log(msg=""):
    print(msg, flush=True)


def die(msg, resp=None):
    log(f"\n!! {msg}")
    if resp is not None:
        log(f"   HTTP {resp.status_code}: {resp.text[:600]}")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Plaid
# --------------------------------------------------------------------------- #
def plaid_post(path, payload):
    body = {"client_id": PLAID_CLIENT_ID, "secret": PLAID_SECRET, **payload}
    return requests.post(f"{PLAID_BASE}{path}", json=body, timeout=30)


def mint_dwolla_processor_token(label):
    """Fake-link a bank in Plaid sandbox and return a Dwolla processor_token.

    Returns None if the Plaid keys aren't enabled for the Dwolla processor
    integration (Plaid Dashboard > Developers > Integrations > Dwolla) — the
    caller then falls back to Dwolla's own sandbox bank values.
    """
    log(f"  [{label}] creating Plaid sandbox public_token…")
    r = plaid_post("/sandbox/public_token/create", {
        "institution_id": PLAID_SANDBOX_INSTITUTION,
        "initial_products": ["auth"],
    })
    if r.status_code != 200:
        die(f"[{label}] plaid public_token create failed", r)
    public_token = r.json()["public_token"]

    r = plaid_post("/item/public_token/exchange", {"public_token": public_token})
    if r.status_code != 200:
        die(f"[{label}] plaid token exchange failed", r)
    access_token = r.json()["access_token"]
    item_id = r.json()["item_id"]

    r = plaid_post("/accounts/get", {"access_token": access_token})
    if r.status_code != 200:
        die(f"[{label}] plaid accounts/get failed", r)
    accounts = r.json()["accounts"]
    acct = next((a for a in accounts if a.get("subtype") == "checking"), accounts[0])
    account_id = acct["account_id"]
    log(f"  [{label}] plaid link OK: {acct.get('name')} ****{acct.get('mask')}  item={item_id}")

    r = plaid_post("/processor/token/create", {
        "access_token": access_token,
        "account_id": account_id,
        "processor": "dwolla",
    })
    if r.status_code == 200:
        return r.json()["processor_token"]
    if r.json().get("error_code") in ("INVALID_PRODUCT", "PRODUCTS_NOT_SUPPORTED"):
        log(f"  [{label}] Plaid->Dwolla processor integration NOT enabled on these "
            f"keys — falling back to Dwolla sandbox bank values.")
        return None
    die(f"[{label}] plaid processor/token/create failed", r)


# --------------------------------------------------------------------------- #
# Dwolla
# --------------------------------------------------------------------------- #
class Dwolla:
    def __init__(self, key, secret):
        basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
        r = requests.post(
            f"{DWOLLA_BASE}/token",
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        if r.status_code != 200:
            die("dwolla token request failed", r)
        self.token = r.json()["access_token"]
        self.h = {**DWOLLA_HEADERS, "Authorization": f"Bearer {self.token}"}

    def get(self, url):
        if not url.startswith("http"):
            url = f"{DWOLLA_BASE}{url}"
        return requests.get(url, headers=self.h, timeout=30)

    def post(self, url, json=None):
        if not url.startswith("http"):
            url = f"{DWOLLA_BASE}{url}"
        return requests.post(url, headers=self.h, json=json or {}, timeout=30)

    def account_url(self):
        r = self.get("/")
        if r.status_code != 200:
            die("dwolla root fetch failed", r)
        return r.json()["_links"]["account"]["href"]

    def create_customer(self, first, last, email):
        r = self.post("/customers", {
            "firstName": first, "lastName": last, "email": email, "type": "unverified",
        })
        if r.status_code != 201:
            die(f"dwolla create customer {email} failed", r)
        return r.headers["Location"]

    def attach_plaid_fs(self, customer_url, processor_token, name):
        r = self.post(f"{customer_url}/funding-sources", {
            "plaidToken": processor_token, "name": name,
        })
        if r.status_code != 201:
            die(f"dwolla attach funding source ({name}) failed", r)
        return r.headers["Location"]

    def attach_raw_fs(self, customer_url, name, account_number):
        """Sandbox fallback: add a bank by raw routing/account, then verify it."""
        r = self.post(f"{customer_url}/funding-sources", {
            "routingNumber": "222222226",
            "accountNumber": account_number,
            "bankAccountType": "checking",
            "name": name,
        })
        if r.status_code != 201:
            die(f"dwolla raw funding source ({name}) failed", r)
        fs = r.headers["Location"]
        self.ensure_verified(fs, name)
        return fs

    def ensure_verified(self, fs, name):
        """Verify a funding source via simulated micro-deposits if it isn't
        already (sandbox deposit amounts are always $0.01 / $0.01)."""
        status = self.get(fs).json().get("status")
        if status == "verified":
            log(f"  [{name}] already verified")
            return
        r = self.post(f"{fs}/micro-deposits")
        if r.status_code not in (201, 200):
            die(f"dwolla initiate micro-deposits ({name}) failed", r)
        self.simulate()
        time.sleep(2)
        r = self.post(f"{fs}/micro-deposits", {
            "amount1": {"value": "0.01", "currency": "USD"},
            "amount2": {"value": "0.01", "currency": "USD"},
        })
        if r.status_code not in (200, 201):
            die(f"dwolla verify micro-deposits ({name}) failed", r)
        log(f"  [{name}] micro-deposit verified -> status={self.get(fs).json().get('status')}")

    def funding_source(self, customer_url, processor_token, name, account_number):
        if processor_token:
            return self.attach_plaid_fs(customer_url, processor_token, name)
        return self.attach_raw_fs(customer_url, name, account_number)

    def create_transfer(self, source, dest, amount, metadata=None):
        body = {
            "_links": {"source": {"href": source}, "destination": {"href": dest}},
            "amount": {"currency": "USD", "value": f"{amount:.2f}"},
        }
        if metadata:
            body["metadata"] = metadata
        r = self.post("/transfers", body)
        if r.status_code != 201:
            return None, r
        return r.headers["Location"], r

    def simulate(self):
        return self.post("/sandbox/simulations")

    def transfer_status(self, url):
        r = self.get(url)
        if r.status_code != 200:
            return f"<lookup failed {r.status_code}>"
        return r.json().get("status", "<none>")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ts = int(time.time())
    log("=" * 70)
    log("ACH SANDBOX END-TO-END TEST")
    log("=" * 70)

    log("\n[1] Plaid sandbox — minting two verified bank accounts")
    pt_customer = mint_dwolla_processor_token("payer")
    pt_vendor = mint_dwolla_processor_token("payee")

    log("\n[2] Dwolla sandbox — auth + customers + funding sources")
    dw = Dwolla(DWOLLA_KEY, DWOLLA_SECRET)
    log(f"  business account: {dw.account_url()}")

    cust_url = dw.create_customer("Karavan", "TestCustomer", f"ki-test-cust-{ts}@example.com")
    vend_url = dw.create_customer("Karavan", "TestVendor", f"ki-test-vend-{ts}@example.com")
    log(f"  customer: {cust_url}")
    log(f"  vendor  : {vend_url}")

    cust_fs = dw.funding_source(cust_url, pt_customer, "TestCustomer checking", "111111111")
    vend_fs = dw.funding_source(vend_url, pt_vendor, "TestVendor checking", "222222222")
    log(f"  customer FS: {cust_fs}")
    log(f"  vendor FS  : {vend_fs}")

    if not MASTER_FS:
        die("DWOLLA_MASTER_FUNDING_SOURCE_URL not set — cannot test real transfers.")
    r = dw.get(MASTER_FS)
    if r.status_code != 200:
        die(f"master funding source lookup failed", r)
    j = r.json()
    log(f"  master FS  : {MASTER_FS}")
    log(f"               name={j.get('name')!r} status={j.get('status')} removed={j.get('removed')}")
    if j.get("removed"):
        die("master funding source is removed — re-run setup_dwolla_master_account.py")
    dw.ensure_verified(MASTER_FS, "master")

    log("\n[3] Initiating transfers")
    log("    (unverified Dwolla customers can only transact with the business")
    log("     account, so every test transfer has the master FS on one side)")
    transfers = []

    def kick(label, src, dst, amt):
        url, resp = dw.create_transfer(src, dst, amt, metadata={"test": label, "ts": str(ts)})
        if url:
            log(f"  OK   {label:24s} ${amt:>6.2f}  {url}")
            transfers.append((label, url))
        else:
            log(f"  FAIL {label:24s} ${amt:>6.2f}  HTTP {resp.status_code}: {resp.text[:300]}")

    kick("customer->MASTER (collect)", cust_fs, MASTER_FS, 12.34)
    kick("MASTER->vendor (payout)", MASTER_FS, vend_fs, 5.00)
    kick("MASTER->customer (refund)", MASTER_FS, cust_fs, 3.21)

    if not transfers:
        die("No transfers were created — nothing to settle.")

    STATE_FILE.write_text(json.dumps({
        "created": ts, "transfers": transfers,
        "customer_fs": cust_fs, "vendor_fs": vend_fs, "master_fs": MASTER_FS,
    }, indent=2))

    log("\n[4] Advancing to settlement")
    sim = dw.simulate()
    if sim.status_code in (200, 201, 202):
        for attempt in range(1, 11):
            time.sleep(3)
            statuses = {l: dw.transfer_status(u) for l, u in transfers}
            log(f"  poll {attempt:>2}: " + "  ".join(f"{l.split()[0]}={s}" for l, s in statuses.items()))
            if all(s in ("processed", "failed", "cancelled") for s in statuses.values()):
                break
            dw.simulate()
    else:
        log(f"  POST /sandbox/simulations -> HTTP {sim.status_code}: the programmatic")
        log(f"  sandbox simulator is not enabled on this Dwolla account.")
        log(f"  Advance the transfers manually, then re-check:")
        log(f"    1. Sign in at https://dashboard-sandbox.dwolla.com")
        log(f"    2. Left nav > 'Sandbox' > click 'Process bank transfers'")
        log(f"    3. python scripts/setup/test_ach_sandbox.py --recheck")

    _report(dw, transfers)


def _report(dw, transfers):
    log("\n" + "=" * 70)
    log("RESULT")
    log("=" * 70)
    landed = 0
    for label, url in transfers:
        st = dw.transfer_status(url)
        if st == "processed":
            landed += 1
        mark = "LANDED " if st == "processed" else ("FAILED " if st in ("failed", "cancelled") else "pending")
        log(f"  [{mark}] {label:26s} {st:12s} {url}")
    log("")
    log(f"  {landed}/{len(transfers)} transfers settled as 'processed'"
        f"{' — all landed.' if landed == len(transfers) else '.'}")
    log("  Dashboard: https://dashboard-sandbox.dwolla.com  (Transfers)")
    sys.exit(0 if landed == len(transfers) else 2)


def recheck():
    if not STATE_FILE.exists():
        die("No prior run found — run without --recheck first.")
    state = json.loads(STATE_FILE.read_text())
    transfers = [tuple(t) for t in state["transfers"]]
    log(f"Re-checking {len(transfers)} transfer(s) from the run at "
        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(state['created']))}")
    dw = Dwolla(DWOLLA_KEY, DWOLLA_SECRET)
    _report(dw, transfers)


if __name__ == "__main__":
    if "--recheck" in sys.argv:
        recheck()
    else:
        main()
