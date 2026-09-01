from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_provider_entrypoint_v04 import (
    _guarded_https_connect,
    _reject_redirect_request,
    _socket_transport_scope,
    _urllib_transport_scope,
    load_blocked_attempt_ledger,
    provider_audit_hook,
    resolve_entrypoint,
    transport_audit_hook,
    validate_provider_url,
)


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PROVIDER_FILES = (
    "scripts/audit_historical_identity_continuity.py",
    "scripts/audit_massive_alpaca_market_coverage.py",
    "scripts/audit_massive_instrument_metadata.py",
    "scripts/build_causal_float_enrichment_v04.py",
    "scripts/build_causal_news_enrichment_v04.py",
    "scripts/build_causal_scanner_snapshot_v04.py",
    "scripts/build_identity_resolved_market_discovery_v04.py",
    "scripts/build_massive_historical_census.py",
    "src/momentumbot/providers/alpaca.py",
    "src/momentumbot/providers/http_json.py",
    "src/momentumbot/providers/massive.py",
    "src/momentumbot/providers/sec_edgar.py",
)


class ProviderEntrypointV04Tests(unittest.TestCase):
    def test_exact_https_hosts_are_allowed(self) -> None:
        for host in (
            "api.massive.com",
            "data.alpaca.markets",
            "data.sec.gov",
        ):
            self.assertEqual(
                validate_provider_url(f"https://{host}/safe/path?secret=not-logged"),
                host,
            )
            self.assertEqual(validate_provider_url(f"https://{host}:443/path"), host)

    def test_scheme_credentials_port_and_lookalike_hosts_fail_closed(self) -> None:
        invalid = (
            "http://data.alpaca.markets/path",
            "https://evil.example/path",
            "https://data.alpaca.markets.evil.example/path",
            "https://user:secret@data.alpaca.markets/path",
            "https://data.alpaca.markets:444/path",
            "not-a-url",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                validate_provider_url(value)

    def test_audit_hook_checks_urllib_requests_only(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE": "",
                "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT": "",
            },
            clear=False,
        ):
            # Clear both values entirely; an empty configured pair is invalid.
            os.environ.pop("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE")
            os.environ.pop("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT")
            provider_audit_hook("unrelated.event", ())
            provider_audit_hook(
                "urllib.Request",
                ("https://api.massive.com/v3/reference/tickers", None, {}, "GET"),
            )
            with self.assertRaisesRegex(RuntimeError, "blocked before network"):
                provider_audit_hook(
                    "urllib.Request",
                    ("https://unexpected.example/path", None, {}, "GET"),
                )

    def test_each_urllib_audit_event_consumes_one_attempt_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            budget = Path(temporary) / "budget.json"
            with patch.dict(
                os.environ,
                {
                    "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE": str(budget),
                    "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT": "2",
                },
            ):
                provider_audit_hook(
                    "urllib.Request",
                    ("https://data.alpaca.markets/first", None, {}, "GET"),
                )
                with self.assertRaisesRegex(RuntimeError, "blocked before network"):
                    provider_audit_hook(
                        "urllib.Request",
                        ("https://blocked.example/second", None, {}, "GET"),
                    )
                state = json.loads(budget.read_text(encoding="utf-8"))
                self.assertEqual(state["total_attempts"], 2)
                self.assertEqual(
                    state["by_host"],
                    {"blocked.example": 1, "data.alpaca.markets": 1},
                )
                with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
                    provider_audit_hook(
                        "urllib.Request",
                        ("https://data.sec.gov/third", None, {}, "GET"),
                    )

    def test_direct_sockets_and_process_escape_are_blocked(self) -> None:
        for event in (
            "socket.connect",
            "socket.getaddrinfo",
            "socket.sendto",
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
        ):
            with self.subTest(event=event), self.assertRaisesRegex(
                RuntimeError, "blocked"
            ):
                transport_audit_hook(event, ())
        with _socket_transport_scope():
            transport_audit_hook("socket.getaddrinfo", ())
            transport_audit_hook("socket.connect", ())

    def test_blocked_attempt_ledger_is_strict_and_contains_only_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "blocked.json"
            environment = {
                "MOMENTUMBOT_PROVIDER_BLOCKED_ATTEMPT_FILE": str(ledger),
            }
            with patch.dict(os.environ, environment, clear=False):
                os.environ.pop("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE", None)
                os.environ.pop("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT", None)
                with self.assertRaises(RuntimeError):
                    provider_audit_hook(
                        "urllib.Request",
                        (
                            "https://blocked.example/path?token=host-secret",
                            None,
                            {},
                            "GET",
                        ),
                    )
                with self.assertRaises(RuntimeError):
                    _reject_redirect_request(
                        __import__("urllib.request").request.HTTPRedirectHandler(),
                        __import__("urllib.request").request.Request(
                            "https://data.alpaca.markets/source?token=source-secret"
                        ),
                        object(),
                        302,
                        "Found",
                        {},
                        "https://data.sec.gov/target?token=redirect-secret",
                    )
                with self.assertRaises(RuntimeError):
                    transport_audit_hook("socket.connect", ())
                with self.assertRaises(RuntimeError):
                    transport_audit_hook("subprocess.Popen", ())
                direct_connection = type(
                    "Connection",
                    (),
                    {
                        "host": "data.alpaca.markets",
                        "port": 443,
                        "_tunnel_host": None,
                    },
                )()
                with self.assertRaises(RuntimeError):
                    _guarded_https_connect(direct_connection)

            payload = load_blocked_attempt_ledger(ledger)
            self.assertEqual(payload["total_blocked_attempts"], 5)
            self.assertEqual(
                payload["by_category"],
                {
                    "hostname": 1,
                    "https_transport": 1,
                    "redirect": 1,
                    "request_budget": 0,
                    "socket": 1,
                    "subprocess": 1,
                },
            )
            self.assertEqual(
                payload["by_host"],
                {
                    "blocked.example": 1,
                    "data.alpaca.markets": 1,
                    "data.sec.gov": 1,
                },
            )
            rendered = ledger.read_text(encoding="utf-8")
            for forbidden in (
                "/path",
                "/target",
                "host-secret",
                "redirect-secret",
                "source-secret",
            ):
                self.assertNotIn(forbidden, rendered)

            ledger.write_text('{"schema_version":1}\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "schema is invalid"):
                load_blocked_attempt_ledger(ledger)

            valid = {
                "schema_version": 1,
                "total_blocked_attempts": 0,
                "by_category": {
                    "hostname": 0,
                    "https_transport": 0,
                    "redirect": 0,
                    "request_budget": 0,
                    "socket": 0,
                    "subprocess": 0,
                },
                "by_host": {},
            }
            rendered_valid = json.dumps(valid, separators=(",", ":"))
            duplicate = rendered_valid.replace(
                '"schema_version":1,',
                '"schema_version":1,"schema_version":1,',
                1,
            )
            ledger.write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "JSON is invalid"):
                load_blocked_attempt_ledger(ledger)

            nonfinite = rendered_valid.replace('"hostname":0', '"hostname":NaN')
            ledger.write_text(nonfinite, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "JSON is invalid"):
                load_blocked_attempt_ledger(ledger)

            ledger.unlink()
            target = Path(temporary) / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            ledger.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "regular file"):
                load_blocked_attempt_ledger(ledger)

    def test_redirect_is_rejected_without_disclosing_either_url(self) -> None:
        source_secret = "https://data.alpaca.markets/source?api_key=source-secret"
        target_secret = "https://data.alpaca.markets/target?token=target-secret"
        request = __import__("urllib.request").request.Request(source_secret)
        with self.assertRaises(RuntimeError) as captured:
            _reject_redirect_request(
                __import__("urllib.request").request.HTTPRedirectHandler(),
                request,
                object(),
                302,
                "Found",
                {},
                target_secret,
            )
        rendered = str(captured.exception)
        self.assertIn("redirect blocked", rendered)
        self.assertNotIn(source_secret, rendered)
        self.assertNotIn(target_secret, rendered)
        self.assertNotIn("source-secret", rendered)
        self.assertNotIn("target-secret", rendered)

    def test_installed_guard_centralizes_legacy_and_redirect_accounting(self) -> None:
        code = r'''
import json
import os
from pathlib import Path
import sys

from scripts import run_provider_entrypoint_v04 as wrapper
from momentumbot.providers import http_json, request_budget

wrapper.install_transport_guards()
request_budget.consume_provider_request("https://data.alpaca.markets/legacy")
http_json.consume_provider_request("https://data.alpaca.markets/legacy")
sys.audit("urllib.Request", "https://data.alpaca.markets/initial", None, {}, "GET")
redirect_target = "https://data.alpaca.markets/redirect?token=must-not-leak"
try:
    wrapper.urllib.request.HTTPRedirectHandler().redirect_request(
        wrapper.urllib.request.Request("https://data.alpaca.markets/initial"),
        object(),
        302,
        "Found",
        {},
        redirect_target,
    )
except RuntimeError as exc:
    assert redirect_target not in str(exc), str(exc)
    assert "must-not-leak" not in str(exc), str(exc)
else:
    raise AssertionError("redirect was not blocked")
try:
    sys.audit("socket.connect", None, ("127.0.0.1", 1))
except RuntimeError:
    pass
else:
    raise AssertionError("direct socket was not blocked")
try:
    sys.audit("subprocess.Popen", "curl", ["curl"], None, None)
except RuntimeError:
    pass
else:
    raise AssertionError("subprocess was not blocked")
with wrapper._socket_transport_scope():
    sys.audit("socket.getaddrinfo", "data.alpaca.markets", 443, 0, 0, 0)
state = json.loads(Path(os.environ["MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE"]).read_text())
assert state["total_attempts"] == 1, state
print(json.dumps(state, sort_keys=True))
'''
        with tempfile.TemporaryDirectory() as temporary:
            budget = Path(temporary) / "budget.json"
            blocked = Path(temporary) / "blocked.json"
            environment = {
                **os.environ,
                "MOMENTUMBOT_PROVIDER_BLOCKED_ATTEMPT_FILE": str(blocked),
                "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE": str(budget),
                "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT": "5",
            }
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"total_attempts": 1', completed.stdout)

    def test_guarded_urllib_allows_only_direct_registered_https_transport(self) -> None:
        code = r'''
import json
import os
from pathlib import Path
import sys

from scripts import run_provider_entrypoint_v04 as wrapper

class Connection:
    host = "data.alpaca.markets"
    port = 443
    _tunnel_host = None
    _create_connection = staticmethod(wrapper._ORIGINAL_SOCKET_CREATE_CONNECTION)

def fake_connect(connection):
    sys.audit("socket.getaddrinfo", connection.host, connection.port, 0, 0, 0)
    sys.audit("socket.connect", None, ("192.0.2.1", connection.port))
    return "connected"

def fake_open(_opener, fullurl, _data=None, _timeout=None):
    sys.audit("urllib.Request", fullurl, None, {}, "GET")
    return wrapper._guarded_https_connect(Connection())

wrapper._ORIGINAL_HTTPS_CONNECT = fake_connect
wrapper._ORIGINAL_OPENER_OPEN = fake_open
wrapper.install_transport_guards()
result = wrapper.urllib.request.OpenerDirector().open(
    "https://data.alpaca.markets/v2/stocks/bars"
)
assert result == "connected", result
state = json.loads(Path(os.environ["MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE"]).read_text())
assert state["total_attempts"] == 1, state
assert wrapper.urllib.request._opener is not None
assert not any(
    isinstance(handler, wrapper.urllib.request.ProxyHandler) and handler.proxies
    for handler in wrapper.urllib.request._opener.handlers
)
print(json.dumps(state, sort_keys=True))
'''
        with tempfile.TemporaryDirectory() as temporary:
            budget = Path(temporary) / "budget.json"
            blocked = Path(temporary) / "blocked.json"
            environment = {
                **os.environ,
                "HTTPS_PROXY": "https://unregistered-proxy.example:443",
                "https_proxy": "https://unregistered-proxy.example:443",
                "MOMENTUMBOT_PROVIDER_BLOCKED_ATTEMPT_FILE": str(blocked),
                "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE": str(budget),
                "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT": "5",
            }
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"total_attempts": 1', completed.stdout)

    def test_https_connection_cannot_replace_the_validated_socket_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "blocked.json"
            with patch.dict(
                os.environ,
                {"MOMENTUMBOT_PROVIDER_BLOCKED_ATTEMPT_FILE": str(ledger)},
                clear=False,
            ):
                os.environ.pop("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE", None)
                os.environ.pop("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT", None)
                with _urllib_transport_scope():
                    provider_audit_hook(
                        "urllib.Request",
                        ("https://data.alpaca.markets/path", None, {}, "GET"),
                    )
                    replaced = type(
                        "Connection",
                        (),
                        {
                            "host": "data.alpaca.markets",
                            "port": 443,
                            "_tunnel_host": None,
                            "_create_connection": staticmethod(
                                lambda *_args, **_kwargs: None
                            ),
                        },
                    )()
                    with self.assertRaisesRegex(RuntimeError, "blocked before network"):
                        _guarded_https_connect(replaced)
            payload = load_blocked_attempt_ledger(ledger)
            self.assertEqual(payload["total_blocked_attempts"], 1)
            self.assertEqual(payload["by_category"]["https_transport"], 1)
            self.assertEqual(payload["by_host"], {"data.alpaca.markets": 1})

    def test_uncaught_provider_error_is_replaced_by_one_sanitized_line(self) -> None:
        code = r'''
from pathlib import Path

from scripts import run_provider_entrypoint_v04 as wrapper

wrapper.resolve_entrypoint = lambda _value: Path("/safe/provider_script.py")
wrapper.install_transport_guards = lambda: None

def fail(*_args, **_kwargs):
    raise RuntimeError(
        "https://data.alpaca.markets/private?api_key=secret response body: PRIVATE-BODY"
    )

wrapper.runpy.run_path = fail
wrapper.main(["scripts/build_massive_historical_census.py"])
'''
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=os.environ,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(
            completed.stderr,
            "provider entry point provider_script.py failed with RuntimeError\n",
        )
        self.assertNotIn("PRIVATE-BODY", completed.stderr)
        self.assertNotIn("api_key", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_frozen_transport_call_graph_has_no_alternate_network_stack(self) -> None:
        forbidden_roots = {
            "aiohttp",
            "httpx",
            "requests",
            "socket",
            "subprocess",
        }
        urlopen_files: set[str] = set()
        for relative in ALLOWED_PROVIDER_FILES:
            source = (ROOT / relative).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".", 1)[0])
                elif (
                    isinstance(node, ast.Attribute)
                    and node.attr == "urlopen"
                ):
                    urlopen_files.add(relative)
            self.assertTrue(
                forbidden_roots.isdisjoint(imported),
                f"alternate transport imported by {relative}: {forbidden_roots & imported}",
            )
        self.assertEqual(
            urlopen_files,
            {
                "src/momentumbot/providers/http_json.py",
                "src/momentumbot/providers/sec_edgar.py",
            },
        )

    def test_only_frozen_repository_entrypoints_are_resolved(self) -> None:
        resolved = resolve_entrypoint("scripts/build_massive_historical_census.py")
        self.assertEqual(resolved.name, "build_massive_historical_census.py")
        for value in (
            "/tmp/script.py",
            "../script.py",
            "scripts/provider_smoke.py",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_entrypoint(value)

    def test_symlink_and_non_regular_entrypoints_are_rejected(self) -> None:
        relative = Path("scripts/build_massive_historical_census.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            target = root / "target.py"
            target.write_text("pass\n", encoding="utf-8")
            candidate = root / relative

            candidate.symlink_to(target)
            with patch("scripts.run_provider_entrypoint_v04.ROOT", root):
                with self.assertRaisesRegex(ValueError, "regular non-symlink"):
                    resolve_entrypoint(relative.as_posix())

            candidate.unlink()
            candidate.mkdir()
            with patch("scripts.run_provider_entrypoint_v04.ROOT", root):
                with self.assertRaisesRegex(ValueError, "regular non-symlink"):
                    resolve_entrypoint(relative.as_posix())


if __name__ == "__main__":
    unittest.main()
