"""Run one frozen acquisition entry point behind pre-network transport gates.

Every v0.4 provider call currently uses ``urllib``.  This wrapper makes its
audit event the single request-accounting point, so every attempted request
consumes the shared ceiling exactly once.  Automatic redirects are rejected
before their follow-up request.  It also rejects socket traffic outside an
active urllib opener and blocks subprocess/exec escape hatches.  URLs, query
strings, headers, and credentials are never persisted or printed.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import runpy
import socket
import stat
import threading
import sys
import urllib.request
from urllib.parse import urlsplit

from momentumbot.providers.request_budget import (
    consume_provider_request as _BUDGET_CONSUMER,
)


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_ATTEMPT_FILE_ENV = "MOMENTUMBOT_PROVIDER_BLOCKED_ATTEMPT_FILE"
ALLOWED_REQUEST_HOSTS = frozenset(
    {
        "api.massive.com",
        "data.alpaca.markets",
        "data.sec.gov",
    }
)
_BLOCKED_CATEGORIES = (
    "hostname",
    "https_transport",
    "redirect",
    "request_budget",
    "socket",
    "subprocess",
)
ALLOWED_ENTRYPOINTS = frozenset(
    {
        "scripts/audit_historical_identity_continuity.py",
        "scripts/audit_massive_alpaca_market_coverage.py",
        "scripts/audit_massive_instrument_metadata.py",
        "scripts/build_causal_float_enrichment_v04.py",
        "scripts/build_causal_news_enrichment_v04.py",
        "scripts/build_causal_scanner_snapshot_v04.py",
        "scripts/build_identity_resolved_market_discovery_v04.py",
        "scripts/build_massive_historical_census.py",
    }
)

_SOCKET_NETWORK_EVENTS = frozenset(
    {
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyaddr",
        "socket.gethostbyname",
        "socket.gethostbyname_ex",
        "socket.sendmsg",
        "socket.sendto",
    }
)
_PROCESS_ESCAPE_EVENTS = frozenset(
    {
        "os.exec",
        "os.fork",
        "os.forkpty",
        "os.posix_spawn",
        "os.spawn",
        "os.system",
        "subprocess.Popen",
    }
)
_TRANSPORT_STATE = threading.local()
_ORIGINAL_OPENER_OPEN = urllib.request.OpenerDirector.open
_ORIGINAL_HTTPS_CONNECT = http.client.HTTPSConnection.connect
_ORIGINAL_SOCKET_CREATE_CONNECTION = socket.create_connection
_GUARDS_INSTALLED = False


def _empty_blocked_attempt_ledger() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_blocked_attempts": 0,
        "by_category": {category: 0 for category in _BLOCKED_CATEGORIES},
        "by_host": {},
    }


def _is_sanitized_host(value: object) -> bool:
    if value == "<invalid>" or value == "<missing>":
        return True
    if not isinstance(value, str) or len(value) > 253:
        return False
    labels = value.split(".")
    return bool(labels) and all(
        label
        and len(label) <= 63
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(character.isascii() and (character.isalnum() or character == "-") for character in label)
        for label in labels
    )


def _validate_blocked_attempt_ledger(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "total_blocked_attempts",
        "by_category",
        "by_host",
    }:
        raise RuntimeError("provider blocked-attempt ledger schema is invalid")
    total = value.get("total_blocked_attempts")
    categories = value.get("by_category")
    hosts = value.get("by_host")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or type(total) is not int
        or total < 0
        or not isinstance(categories, dict)
        or set(categories) != set(_BLOCKED_CATEGORIES)
        or not isinstance(hosts, dict)
    ):
        raise RuntimeError("provider blocked-attempt ledger schema is invalid")
    for category, count in categories.items():
        if category not in _BLOCKED_CATEGORIES or type(count) is not int or count < 0:
            raise RuntimeError("provider blocked-attempt ledger category is invalid")
    for host, count in hosts.items():
        if not _is_sanitized_host(host) or type(count) is not int or count <= 0:
            raise RuntimeError("provider blocked-attempt ledger host is invalid")
    if sum(categories.values()) != total or sum(hosts.values()) > total:
        raise RuntimeError("provider blocked-attempt ledger counts are invalid")
    return value


def _strict_json_loads(raw: str) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_nonfinite(_value: str) -> object:
        raise ValueError("non-finite JSON number")

    return json.loads(
        raw,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_nonfinite,
    )


def _blocked_attempt_path(*, required: bool) -> Path | None:
    raw = os.environ.get(BLOCKED_ATTEMPT_FILE_ENV)
    if not raw:
        if required:
            raise RuntimeError("provider blocked-attempt ledger path is required")
        return None
    path = Path(raw)
    if not path.is_absolute():
        raise RuntimeError("provider blocked-attempt ledger path must be absolute")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise RuntimeError("provider blocked-attempt ledger parent is invalid")
    return path


def _sanitized_host_from_url(value: object) -> str:
    if not isinstance(value, str):
        return "<invalid>"
    try:
        host = str(urlsplit(value).hostname or "").lower()
    except (TypeError, ValueError):
        return "<invalid>"
    if not host:
        return "<missing>"
    return host if _is_sanitized_host(host) else "<invalid>"


def _mutate_blocked_attempt_ledger(
    *, category: str | None = None, host: str | None = None, required: bool = False
) -> None:
    path = _blocked_attempt_path(required=required)
    if path is None:
        return
    if category is not None and category not in _BLOCKED_CATEGORIES:
        raise RuntimeError("provider blocked-attempt category is invalid")
    if host is not None and not _is_sanitized_host(host):
        host = "<invalid>"

    import fcntl

    flags = os.O_CLOEXEC | os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("provider blocked-attempt ledger cannot be opened") from exc
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise RuntimeError("provider blocked-attempt ledger must be a regular file")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read().strip()
        if raw:
            try:
                state = _validate_blocked_attempt_ledger(_strict_json_loads(raw))
            except (json.JSONDecodeError, ValueError) as exc:
                raise RuntimeError(
                    "provider blocked-attempt ledger JSON is invalid"
                ) from exc
        else:
            state = _empty_blocked_attempt_ledger()
        if category is not None:
            categories = dict(state["by_category"])  # type: ignore[arg-type]
            hosts = dict(state["by_host"])  # type: ignore[arg-type]
            categories[category] += 1
            if host is not None:
                hosts[host] = hosts.get(host, 0) + 1
            state = {
                "schema_version": 1,
                "total_blocked_attempts": state["total_blocked_attempts"] + 1,  # type: ignore[operator]
                "by_category": categories,
                "by_host": dict(sorted(hosts.items())),
            }
            _validate_blocked_attempt_ledger(state)
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_blocked_attempt_ledger(path: str | Path) -> dict[str, object]:
    """Load a sanitized ledger for strict failure-report integration."""

    ledger_path = Path(path)
    try:
        mode = ledger_path.lstat().st_mode
    except OSError as exc:
        raise RuntimeError("provider blocked-attempt ledger is missing") from exc
    if not stat.S_ISREG(mode):
        raise RuntimeError("provider blocked-attempt ledger must be a regular file")
    try:
        payload = _strict_json_loads(ledger_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("provider blocked-attempt ledger JSON is invalid") from exc
    return _validate_blocked_attempt_ledger(payload)


def _noop_legacy_request_counter(_url: str) -> None:
    """The urllib audit hook owns v0.4 accounting after wrapper installation."""


def _urllib_depth() -> int:
    value = getattr(_TRANSPORT_STATE, "urllib_depth", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _socket_depth() -> int:
    value = getattr(_TRANSPORT_STATE, "socket_depth", 0)
    return value if isinstance(value, int) and value >= 0 else 0


@contextmanager
def _urllib_transport_scope():
    prior = _urllib_depth()
    prior_host = getattr(_TRANSPORT_STATE, "audited_host", None)
    _TRANSPORT_STATE.urllib_depth = prior + 1
    _TRANSPORT_STATE.audited_host = None
    try:
        yield
    finally:
        _TRANSPORT_STATE.urllib_depth = prior
        _TRANSPORT_STATE.audited_host = prior_host


@contextmanager
def _socket_transport_scope():
    prior = _socket_depth()
    _TRANSPORT_STATE.socket_depth = prior + 1
    try:
        yield
    finally:
        _TRANSPORT_STATE.socket_depth = prior


def _guarded_opener_open(
    self: urllib.request.OpenerDirector,
    fullurl: object,
    data: object = None,
    timeout: object = urllib.request.socket._GLOBAL_DEFAULT_TIMEOUT,
) -> object:
    """Mark only stdlib urllib opener traffic as eligible for socket access."""

    with _urllib_transport_scope():
        return _ORIGINAL_OPENER_OPEN(self, fullurl, data, timeout)


def _guarded_https_connect(self: http.client.HTTPSConnection) -> object:
    """Permit a direct, validated TLS connection only from guarded urllib."""

    host = str(getattr(self, "host", "") or "").lower()
    clean_host = host if _is_sanitized_host(host) else "<invalid>"
    audited_host = getattr(_TRANSPORT_STATE, "audited_host", None)
    if _urllib_depth() == 0:
        _mutate_blocked_attempt_ledger(
            category="https_transport", host=clean_host
        )
        raise RuntimeError("provider HTTPS transport blocked outside guarded urllib")
    port = getattr(self, "port", None)
    tunnel_host = getattr(self, "_tunnel_host", None)
    create_connection = getattr(self, "_create_connection", None)
    if (
        host not in ALLOWED_REQUEST_HOSTS
        or audited_host != host
        or port not in (None, 443)
        or tunnel_host
        or create_connection is not _ORIGINAL_SOCKET_CREATE_CONNECTION
    ):
        _mutate_blocked_attempt_ledger(
            category="https_transport",
            host=clean_host,
        )
        raise RuntimeError(
            f"provider HTTPS transport blocked before network access for host "
            f"{clean_host}"
        )
    with _socket_transport_scope():
        return _ORIGINAL_HTTPS_CONNECT(self)


def _reject_redirect_request(
    _self: urllib.request.HTTPRedirectHandler,
    _request: urllib.request.Request,
    _file_pointer: object,
    _code: int,
    _message: str,
    _headers: object,
    _new_url: str,
) -> None:
    """Reject redirects without rendering either the source or target URL."""

    _mutate_blocked_attempt_ledger(
        category="redirect", host=_sanitized_host_from_url(_new_url)
    )
    raise RuntimeError("provider redirect blocked before follow-up network access")


def validate_provider_url(value: object) -> str:
    """Return the allowed hostname or fail without exposing the full URL."""

    if not isinstance(value, str):
        raise RuntimeError("provider request URL must be text")
    parsed = urlsplit(value)
    host = str(parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("provider request port is invalid") from exc
    if (
        parsed.scheme != "https"
        or host not in ALLOWED_REQUEST_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise RuntimeError(
            f"provider request blocked before network access for host {host or '<missing>'}"
        )
    return host


def provider_audit_hook(event: str, arguments: tuple[object, ...]) -> None:
    """Count then validate each urllib request attempt; redirects are disabled."""

    if event != "urllib.Request":
        return
    if not arguments:
        raise RuntimeError("provider request audit event lacks a URL")
    # Count first so a blocked hostname remains visible in sanitized failure
    # accounting.  The budget stores only the hostname, never the full URL.
    try:
        _BUDGET_CONSUMER(arguments[0])  # type: ignore[arg-type]
    except Exception:
        _mutate_blocked_attempt_ledger(
            category="request_budget",
            host=_sanitized_host_from_url(arguments[0]),
        )
        raise
    try:
        host = validate_provider_url(arguments[0])
    except Exception:
        _mutate_blocked_attempt_ledger(
            category="hostname", host=_sanitized_host_from_url(arguments[0])
        )
        raise
    if _urllib_depth() > 0:
        _TRANSPORT_STATE.audited_host = host


def transport_audit_hook(event: str, arguments: tuple[object, ...]) -> None:
    """Reject transports that could bypass urllib hostname/budget accounting."""

    if event == "urllib.Request":
        provider_audit_hook(event, arguments)
        return
    if event in _PROCESS_ESCAPE_EVENTS:
        _mutate_blocked_attempt_ledger(category="subprocess")
        raise RuntimeError("provider subprocess or exec blocked before launch")
    if event in _SOCKET_NETWORK_EVENTS and _socket_depth() == 0:
        _mutate_blocked_attempt_ledger(category="socket")
        raise RuntimeError("provider socket traffic blocked outside validated HTTPS")


def install_transport_guards() -> None:
    """Install process-local accounting and transport guards exactly once."""

    global _GUARDS_INSTALLED
    if _GUARDS_INSTALLED:
        raise RuntimeError("v0.4 provider transport guards are already installed")
    _mutate_blocked_attempt_ledger(required=True)

    # Install the audit boundary before importing another project module.  The
    # providers package, request-budget module, and its eager SEC import above
    # are side-effect-free; the frozen call-graph test enforces their transport
    # surface.
    urllib.request.OpenerDirector.open = _guarded_opener_open
    urllib.request.HTTPRedirectHandler.redirect_request = _reject_redirect_request
    http.client.HTTPSConnection.connect = _guarded_https_connect
    sys.addaudithook(transport_audit_hook)

    from momentumbot.providers import http_json, request_budget

    # Legacy call sites count immediately before ``urlopen``.  Replacing those
    # references avoids double accounting while the audit event counts every
    # actual urllib attempt.  Redirects are separately rejected before urllib
    # can issue a follow-up request.  Keep the original consumer in
    # ``_BUDGET_CONSUMER`` above.
    request_budget.consume_provider_request = _noop_legacy_request_counter
    http_json.consume_provider_request = _noop_legacy_request_counter

    # Provider traffic must connect directly to the validated endpoint.  An
    # ambient HTTPS_PROXY would otherwise let a permitted request open a socket
    # to an unregistered proxy host while the URL itself still looked allowed.
    direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    urllib.request.install_opener(direct_opener)
    _GUARDS_INSTALLED = True


def resolve_entrypoint(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("provider entry point must be a repository-relative path")
    rendered = relative.as_posix()
    if rendered not in ALLOWED_ENTRYPOINTS:
        raise ValueError("provider entry point is not frozen for v0.4")
    candidate = ROOT / relative
    try:
        mode = candidate.lstat().st_mode
    except OSError as exc:
        raise ValueError("provider entry point is missing or inaccessible") from exc
    if not stat.S_ISREG(mode):
        raise ValueError("provider entry point must be a regular non-symlink file")
    resolved = candidate.resolve()
    if resolved.parent != (ROOT / "scripts").resolve():
        raise ValueError("provider entry point is missing or escapes scripts")
    return resolved


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("entrypoint")
    result.add_argument("arguments", nargs=argparse.REMAINDER)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    entrypoint = resolve_entrypoint(args.entrypoint)
    install_transport_guards()
    sys.argv = [entrypoint.as_posix(), *args.arguments]
    try:
        runpy.run_path(entrypoint.as_posix(), run_name="__main__")
    except SystemExit as exc:
        if exc.code in (None, 0):
            return
        print(
            f"provider entry point {entrypoint.name} failed with SystemExit",
            file=sys.stderr,
        )
        code = exc.code if type(exc.code) is int and 0 < exc.code <= 255 else 1
        raise SystemExit(code) from None
    except BaseException as exc:
        error_type = type(exc).__name__
        if not error_type.isidentifier() or not error_type.isascii():
            error_type = "Exception"
        print(
            f"provider entry point {entrypoint.name} failed with {error_type}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
