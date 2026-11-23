"""Offline tests for the credit-card surcharge: rules, Tap to Pay, Pay Now
confirm, and webhook Payment Entry construction. No network — Stripe and
ERPNext are faked.

    python -m unittest discover -s payments/tests -v
"""

import json
import os
import sys
import types
import unittest
from unittest import mock

LAMBDAS = os.path.join(os.path.dirname(__file__), "..", "lambdas")
sys.path.insert(0, os.path.abspath(LAMBDAS))
sys.modules.setdefault("boto3", types.ModuleType("boto3"))  # config imports it; never called here

from common import surcharge  # noqa: E402


class Obj(dict):
    """Minimal StripeObject stand-in: attribute access + to_dict()."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def to_dict(self):
        return json.loads(json.dumps(self))


class FakeERP:
    def __init__(self, docs=None, lists=None):
        self.docs = docs or {}
        self.lists = lists or {}
        self.created, self.submitted = [], []

    def get(self, doctype, name):
        return self.docs.get((doctype, name))

    def list(self, doctype, filters=None, fields=None, limit=100):
        return self.lists.get(doctype, [])

    def exists(self, doctype, filters):
        return bool(self.lists.get(doctype))

    def update(self, doctype, name, doc):
        return doc

    def create(self, doctype, doc):
        self.created.append((doctype, doc))
        return {"name": "PE-0001"}

    def submit(self, doctype, name):
        self.submitted.append(name)

    def call(self, method, **params):
        return self.pe_template


class SurchargeRules(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CARD_SURCHARGE_RATE", None)
        os.environ.pop("CARD_SURCHARGE_EXCLUDED_STATES", None)

    def test_credit_card_gets_3_percent(self):
        b = surcharge.compute(100_00, funding="credit", invoice_doctype="Sales Invoice")
        self.assertEqual((b["surcharge_cents"], b["total_cents"]), (300, 103_00))

    def test_rounding_half_up(self):
        self.assertEqual(surcharge.compute(1_50, funding="credit", invoice_doctype="Sales Invoice")["surcharge_cents"], 5)

    def test_debit_prepaid_unknown_and_bank_are_free(self):
        for funding in ("debit", "prepaid", "unknown", None):
            self.assertEqual(surcharge.compute(100_00, funding=funding, invoice_doctype="Sales Invoice")["surcharge_cents"], 0, funding)

    def test_purchase_invoice_never_surcharged(self):
        self.assertEqual(surcharge.compute(100_00, funding="credit", invoice_doctype="Purchase Invoice")["surcharge_cents"], 0)

    def test_excluded_states_by_code_or_name(self):
        for st in ("CT", "ct", "Massachusetts", " connecticut "):
            self.assertEqual(surcharge.compute(100_00, funding="credit", invoice_doctype="Sales Invoice", billing_state=st)["surcharge_cents"], 0, st)
        self.assertEqual(surcharge.compute(100_00, funding="credit", invoice_doctype="Sales Invoice", billing_state="Texas")["surcharge_cents"], 300)

    def test_rate_above_cap_refused(self):
        with mock.patch.dict(os.environ, {"CARD_SURCHARGE_RATE": "0.04"}):
            with self.assertRaises(ValueError):
                surcharge.compute(100_00, funding="credit", invoice_doctype="Sales Invoice")

    def test_description_discloses_fee(self):
        b = surcharge.compute(250_00, funding="credit", invoice_doctype="Sales Invoice")
        self.assertEqual(surcharge.describe("SINV-1", b),
                         "Karavan Imports invoice SINV-1: $250.00 + 3% credit card surcharge $7.50")


class TapToPay(unittest.TestCase):
    def _run(self, funding, outstanding=200.0, state=None, status="requires_confirmation"):
        from terminal import handler as th
        pi = Obj(id="pi_1", status=status, currency="usd",
                 metadata={"channel": "tap_to_pay", "invoice_name": "SINV-9", "invoice_doctype": "Sales Invoice",
                           "base_cents": "20000", "surcharge_cents": "0"},
                 payment_method={"type": "card_present",
                                 "card_present": {"funding": funding, "brand": "visa", "last4": "4242"}})
        client = mock.MagicMock()
        client.PaymentIntent.retrieve.return_value = pi
        docs = {("Sales Invoice", "SINV-9"): {"outstanding_amount": outstanding, "customer_address": "A1" if state else None}}
        if state:
            docs[("Address", "A1")] = {"state": state}
        resp = th._apply_surcharge(client, FakeERP(docs), "driver@x", {"payment_intent_id": "pi_1"})
        return resp, client

    def test_credit_tap_raises_amount(self):
        resp, client = self._run("credit")
        self.assertEqual(resp["statusCode"], 200)
        kwargs = client.PaymentIntent.modify.call_args.kwargs
        self.assertEqual(kwargs["amount"], 206_00)
        self.assertEqual(kwargs["metadata"]["surcharge_cents"], "600")
        self.assertEqual(json.loads(resp["body"])["card_last4"], "4242")

    def test_debit_tap_unchanged(self):
        resp, client = self._run("debit")
        self.assertEqual(client.PaymentIntent.modify.call_args.kwargs["amount"], 200_00)

    def test_excluded_state_tap_unchanged(self):
        resp, client = self._run("credit", state="Connecticut")
        self.assertEqual(client.PaymentIntent.modify.call_args.kwargs["amount"], 200_00)

    def test_stale_balance_cancels(self):
        resp, client = self._run("credit", outstanding=50.0)
        self.assertEqual(resp["statusCode"], 409)
        client.PaymentIntent.cancel.assert_called_once_with("pi_1")
        client.PaymentIntent.modify.assert_not_called()

    def test_wrong_state_refused(self):
        resp, client = self._run("credit", status="succeeded")
        self.assertEqual(resp["statusCode"], 409)


class PayNowConfirm(unittest.TestCase):
    def test_confirm_charges_total_and_records_breakdown(self):
        from pay_now import handler as ph
        client = mock.MagicMock()
        client.ConfirmationToken.retrieve.return_value = Obj(
            payment_method_preview={"type": "card", "card": {"funding": "credit", "brand": "mastercard", "last4": "1111"}})
        client.PaymentIntent.search.return_value = Obj(data=[])
        client.PaymentIntent.create.return_value = Obj(id="pi_9", status="succeeded", client_secret="cs")
        erp = FakeERP({("Sales Invoice", "SINV-2"): {"outstanding_amount": 1000.0, "customer": "C1", "currency": "USD"},
                       ("Customer", "C1"): {"email_id": "a@b.c", "custom_stripe_customer_id": "cus_1"}})
        with mock.patch.object(ph, "erpnext_config", return_value={"url": "u", "api_key": "k", "api_secret": "s"}), \
             mock.patch.object(ph, "ERPNextClient", return_value=erp), \
             mock.patch.object(ph, "stripe_config", return_value={"secret_key": "sk", "publishable_key": "pk"}), \
             mock.patch.object(ph, "get_stripe_client", return_value=client):
            resp = ph._confirm({"invoice_doctype": "Sales Invoice", "invoice_name": "SINV-2", "confirmation_token": "ctoken_1"})
        self.assertEqual(resp["statusCode"], 200, resp["body"])
        kwargs = client.PaymentIntent.create.call_args.kwargs
        self.assertEqual(kwargs["amount"], 1030_00)
        self.assertEqual(kwargs["confirmation_token"], "ctoken_1")
        self.assertEqual(kwargs["metadata"]["surcharge_cents"], "3000")


class WebhookPaymentEntry(unittest.TestCase):
    def _pe(self, amount, surcharge_amt, outstanding=100.0):
        from stripe_webhook import handler as wh
        erp = FakeERP(docs={("Company", "Karavan"): {"cost_center": "Main - K"}},
                      lists={"Account": [{"name": "Credit Card Surcharge Income - K"}]})
        erp.lists_pe = []
        erp.exists = lambda dt, f: False
        erp.pe_template = {"company": "Karavan", "paid_amount": outstanding, "received_amount": outstanding,
                           "references": [{"reference_doctype": "Sales Invoice", "reference_name": "SINV-1",
                                           "allocated_amount": outstanding}]}
        wh._create_payment_entry(erp, "Sales Invoice", "SINV-1", amount, "pi_1", "2026-11-23", "Card", surcharge=surcharge_amt)
        return erp.created[0][1]

    def test_surcharge_booked_as_negative_deduction(self):
        pe = self._pe(103.0, 3.0)
        self.assertEqual(pe["paid_amount"], 103.0)
        self.assertEqual(pe["references"][0]["allocated_amount"], 100.0)
        self.assertEqual(pe["deductions"], [{"account": "Credit Card Surcharge Income - K", "cost_center": "Main - K",
                                             "amount": -3.0, "description": "Credit card surcharge"}])
        # ERPNext's balance rule for Receive: allocated - received - deductions == 0
        self.assertAlmostEqual(100.0 - pe["paid_amount"] - sum(d["amount"] for d in pe["deductions"]), 0)

    def test_no_surcharge_unchanged_behaviour(self):
        pe = self._pe(100.0, 0.0)
        self.assertNotIn("deductions", pe)
        self.assertEqual(pe["references"][0]["allocated_amount"], 100.0)

    def test_partial_installment_still_works(self):
        pe = self._pe(40.0, 0.0)
        self.assertEqual((pe["paid_amount"], pe["references"][0]["allocated_amount"]), (40.0, 40.0))


if __name__ == "__main__":
    unittest.main()
