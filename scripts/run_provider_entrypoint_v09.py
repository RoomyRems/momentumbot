"""Run only the two remaining v0.9 recovery provider entry points.

The audited v0.4 HTTPS/request-budget guard is reused byte-for-byte. The v0.9
allowlist cannot repeat Massive, identity, market, SEC, or float acquisition.
Only the identity-compatible news and scanner-source adapters can run.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import runpy
import stat
import sys

if __package__:
    from scripts import run_provider_entrypoint_v04 as transport
else:  # Exact ``python scripts/...`` workflow invocation.
    import run_provider_entrypoint_v04 as transport


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENTRYPOINTS = frozenset(
    {
        "scripts/build_causal_news_enrichment_v09.py",
        "scripts/build_causal_scanner_snapshot_v09.py",
    }
)
EXPECTED_PARENT_REQUEST_HOSTS = frozenset(
    {"api.massive.com", "data.alpaca.markets", "data.sec.gov"}
)
CHILD_REQUEST_HOSTS = frozenset(
    {"data.alpaca.markets"}
)


def resolve_entrypoint(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("provider entry point must be repository-relative")
    rendered = relative.as_posix()
    if rendered not in ALLOWED_ENTRYPOINTS:
        raise ValueError("provider entry point is not frozen for v0.9 recovery")
    candidate = ROOT / relative
    try:
        mode = candidate.lstat().st_mode
    except OSError as exc:
        raise ValueError("provider entry point is missing or inaccessible") from exc
    if not stat.S_ISREG(mode):
        raise ValueError("provider entry point must be a regular non-symlink file")
    resolved = candidate.resolve()
    if resolved.parent != (ROOT / "scripts").resolve():
        raise ValueError("provider entry point escaped scripts")
    return resolved


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("entrypoint")
    result.add_argument("arguments", nargs=argparse.REMAINDER)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    entrypoint = resolve_entrypoint(args.entrypoint)
    original_hosts = transport.ALLOWED_REQUEST_HOSTS
    if original_hosts != EXPECTED_PARENT_REQUEST_HOSTS:
        raise RuntimeError("parent provider host guard changed")
    transport.ALLOWED_REQUEST_HOSTS = CHILD_REQUEST_HOSTS
    try:
        transport.install_transport_guards()
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
    finally:
        transport.ALLOWED_REQUEST_HOSTS = original_hosts


if __name__ == "__main__":
    main()
