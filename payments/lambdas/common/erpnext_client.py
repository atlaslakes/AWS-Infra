import json
import requests


class ERPNextClient:
    """Thin REST wrapper mirroring the get/create/update/upsert helpers used
    throughout scripts/setup/*.py, adapted for use inside a Lambda handler."""

    def __init__(self, url, api_key, api_secret):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        # TLS verification stays ON — this call carries the payments API key.
        self.session.verify = True
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"

    def _q(self, name):
        return requests.utils.quote(str(name), safe="")

    def get(self, doctype, name):
        r = self.session.get(f"{self.url}/api/resource/{self._q(doctype)}/{self._q(name)}", timeout=15)
        if r.status_code == 200:
            return r.json()["data"]
        if r.status_code == 404:
            return None
        raise RuntimeError(f"GET {doctype}/{name} failed {r.status_code}: {r.text[:300]}")

    def list(self, doctype, filters=None, fields=None, limit=100):
        params = {"limit_page_length": limit}
        if filters:
            params["filters"] = json.dumps(filters)
        if fields:
            params["fields"] = json.dumps(fields)
        r = self.session.get(f"{self.url}/api/resource/{self._q(doctype)}", params=params, timeout=20)
        if r.status_code == 200:
            return r.json()["data"]
        raise RuntimeError(f"LIST {doctype} failed {r.status_code}: {r.text[:300]}")

    def create(self, doctype, doc):
        r = self.session.post(f"{self.url}/api/resource/{self._q(doctype)}", json=doc, timeout=20)
        if r.status_code in (200, 201):
            return r.json()["data"]
        raise RuntimeError(f"CREATE {doctype} failed {r.status_code}: {r.text[:300]}")

    def update(self, doctype, name, doc):
        r = self.session.put(f"{self.url}/api/resource/{self._q(doctype)}/{self._q(name)}", json=doc, timeout=20)
        if r.status_code in (200, 201):
            return r.json()["data"]
        raise RuntimeError(f"UPDATE {doctype}/{name} failed {r.status_code}: {r.text[:300]}")

    def submit(self, doctype, name):
        return self.update(doctype, name, {"docstatus": 1})

    def cancel(self, doctype, name):
        return self.update(doctype, name, {"docstatus": 2})

    def call(self, method, **params):
        """Invoke a whitelisted server method: GET /api/method/<dotted.path>.
        Used to reach ERPNext helpers like get_payment_entry that assemble a
        fully-populated doc (party, bank accounts, company) server-side."""
        r = self.session.get(f"{self.url}/api/method/{method}", params=params, timeout=20)
        if r.status_code == 200:
            return r.json().get("message")
        raise RuntimeError(f"CALL {method} failed {r.status_code}: {r.text[:300]}")

    def exists(self, doctype, filters):
        """True if at least one record matches. filters is a list of triples."""
        return bool(self.list(doctype, filters=filters, fields=["name"], limit=1))
