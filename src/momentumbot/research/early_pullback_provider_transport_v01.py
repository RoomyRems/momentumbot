"""No-retry HTTP transport for the four fixed availability requests."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from momentumbot.research import early_pullback_provider_check_v01 as m


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


class BoundedProbe:
    def __init__(self, contract, execution, marker, env, *, output, credentials, opener=None):
        m.exact(execution, m.execution_payload(contract, code_commit=execution["code_commit_sha"],
            code_tree=execution["code_tree_sha"], ci_run_id=execution["successful_code_ci_run_id"]), "execution required")
        m.exact(marker, m.consumption(execution, env), "durable consumption binding required")
        required = ("ALPACA_API_KEY", "ALPACA_API_SECRET", "DATABENTO_API_KEY")
        m.require(all(type(credentials.get(k)) is str and credentials[k] for k in required), "required provider credentials missing")
        massive = credentials.get("MASSIVE_API_KEY")
        polygon = credentials.get("POLYGON_API_KEY")
        m.require(bool(massive or polygon), "membership credential missing")
        self.membership_route = "massive" if massive else "polygon"
        self.membership_key = massive or polygon
        self.credentials = {k: credentials[k] for k in required}
        m.require(all("\n" not in v and "\r" not in v for v in (*self.credentials.values(), self.membership_key)),
                  "invalid credential format")
        self.contract, self.execution, self.marker = contract, execution, marker
        self.output = Path(output)
        m.require(not any(p.is_symlink() for p in (self.output, *self.output.parents)), "no symbolic output paths")
        self.output.mkdir(parents=True, exist_ok=False)
        for name, value in (("contract.json", contract), ("execution.json", execution),
                            ("consumption.json", marker), ("requests.json", m.request_document(contract))):
            m.write_once(self.output / name, value)
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.next_ordinal = 0
        self.receipts = []
        self.finished = False

    def _request(self, request):
        ordinal = request["ordinal"]
        route = "alpaca" if ordinal == 0 else self.membership_route if ordinal in (1, 2) else "databento"
        params = dict(request["request"]["parameters"])
        headers = {"User-Agent": "MomentumBot/0.2 " + m.ID, "Accept": "application/json", "Accept-Encoding": "identity"}
        if ordinal == 0:
            headers.update({"APCA-API-KEY-ID": self.credentials["ALPACA_API_KEY"],
                            "APCA-API-SECRET-KEY": self.credentials["ALPACA_API_SECRET"]})
        elif ordinal in (1, 2):
            params["apiKey"] = self.membership_key
        else:
            m.require(params.pop("method") == "metadata.get_dataset_range", "fixed metadata method required")
            encoded = base64.b64encode((self.credentials["DATABENTO_API_KEY"] + ":").encode()).decode()
            headers["Authorization"] = "Basic " + encoded
        url = m.ROUTES[route] + "?" + urllib.parse.urlencode(params)
        return route, urllib.request.Request(url, headers=headers, method="GET")

    def once(self, ordinal):
        m.require(not self.finished and type(ordinal) is int and ordinal == self.next_ordinal < 4,
                  "one strictly ordered provider attempt per request")
        request = self.contract["requests"][ordinal]
        route, http = self._request(request)
        started = m.intent(request, self.marker, route, now())
        # Intent is fsynced before network access. Interruptions cannot appear as zero calls.
        m.write_once(self.output / f"intent-{ordinal}.json", started)
        self.next_ordinal += 1
        status, body, complete = None, None, False
        projection = {"ok": False, "reason": "transport_error"}
        response = None
        try:
            try:
                response = self.opener.open(http, timeout=self.contract["timeout_seconds"])
            except urllib.error.HTTPError as error:
                # Includes redirects refused by NoRedirect. Read only a bounded digest.
                response = error
            status = response.status
            m.require(type(status) is int and 100 <= status <= 599, "invalid HTTP status")
            m.require(response.geturl() == http.full_url, "redirected response rejected")
            encoding = response.headers.get("Content-Encoding", "identity").lower()
            if encoding not in ("", "identity"):
                projection = {"ok": False, "reason": "content_encoding"}
            else:
                body = response.read(m.MAX_RESPONSE_BYTES + 1)
                m.require(type(body) is bytes, "raw response bytes required")
                if len(body) > m.MAX_RESPONSE_BYTES:
                    projection = {"ok": False, "reason": "response_too_large"}
                else:
                    complete = True
                    if status != 200:
                        projection = {"ok": False, "reason": "http_error"}
                    else:
                        try:
                            payload = m.json_object(body)
                        except (ValueError, TypeError, UnicodeError):
                            projection = {"ok": False, "reason": "invalid_json"}
                        else:
                            try:
                                projection = m.project(ordinal, payload)
                            except (ValueError, TypeError, KeyError, OverflowError):
                                projection = {"ok": False, "reason": "invalid_payload"}
        except Exception:
            # Never serialize exception text, provider headers, URLs or credentials.
            projection = {"ok": False, "reason": "transport_error"}
        finally:
            if response is not None:
                response.close()
        receipt = m.seal({"contract_id": m.ID, "ordinal": ordinal, "request_sha256": request["request_sha256"],
            "consumption_sha256": self.marker["content_sha256"], "route": route,
            "started_at": started["started_at"], "finished_at": now(), "intent_sha256": started["content_sha256"],
            "status": status, "body_bytes_observed": 0 if body is None else len(body),
            "body_sha256": None if body is None else m.sha(body), "body_complete": complete, "projection": projection})
        m.validate_receipt(receipt, request, self.marker)
        rendered = json.dumps(receipt, sort_keys=True)
        for secret in (*self.credentials.values(), self.membership_key):
            m.require(secret not in rendered and urllib.parse.quote(secret, safe="") not in rendered,
                      "credential reached sanitized receipt")
        m.write_once(self.output / f"receipt-{ordinal}.json", receipt)
        self.receipts.append(receipt)
        return receipt

    def run(self):
        m.require(self.next_ordinal == 0 and not self.finished, "no restart or resume")
        try:
            for i in range(4):
                self.once(i)
            report = m.report(self.contract, self.execution, self.marker, self.receipts)
            m.write_once(self.output / "report.json", report)
            return report
        finally:
            self.finished = True
            m.write_once(self.output / "inventory.json", m.inventory(self.output))
