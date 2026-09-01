from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_provider_entrypoint_v06 as wrapper


class ProviderEntrypointV06Tests(unittest.TestCase):
    def test_allowlist_contains_only_remaining_recovery_routes(self) -> None:
        self.assertEqual(
            wrapper.ALLOWED_ENTRYPOINTS,
            {
                "scripts/build_causal_float_enrichment_v06.py",
                "scripts/build_causal_news_enrichment_v04.py",
                "scripts/build_causal_scanner_snapshot_v04.py",
            },
        )
        for value in wrapper.ALLOWED_ENTRYPOINTS:
            self.assertEqual(wrapper.resolve_entrypoint(value), wrapper.ROOT / value)
        self.assertEqual(
            wrapper.CHILD_REQUEST_HOSTS,
            {"data.alpaca.markets", "data.sec.gov"},
        )
        self.assertNotIn("api.massive.com", wrapper.CHILD_REQUEST_HOSTS)

    def test_parent_routes_and_obsolete_float_adapters_are_prohibited(self) -> None:
        for value in (
            "scripts/build_massive_historical_census.py",
            "scripts/build_identity_resolved_market_discovery_v04.py",
            "scripts/build_causal_float_enrichment_v04.py",
            "scripts/build_causal_float_enrichment_v05.py",
        ):
            with self.assertRaisesRegex(ValueError, "not frozen"):
                wrapper.resolve_entrypoint(value)

    def test_main_installs_guard_before_running_exact_file(self) -> None:
        target = wrapper.ROOT / "scripts/build_causal_news_enrichment_v04.py"
        observed: list[frozenset[str]] = []
        with patch.object(
            wrapper.transport,
            "install_transport_guards",
            side_effect=lambda: observed.append(wrapper.transport.ALLOWED_REQUEST_HOSTS),
        ) as guard, patch.object(
            wrapper.runpy,
            "run_path",
            side_effect=lambda *_args, **_kwargs: observed.append(
                wrapper.transport.ALLOWED_REQUEST_HOSTS
            ),
        ) as run:
            wrapper.main(["scripts/build_causal_news_enrichment_v04.py", "--help"])
        guard.assert_called_once_with()
        run.assert_called_once_with(target.as_posix(), run_name="__main__")
        self.assertEqual(observed, [wrapper.CHILD_REQUEST_HOSTS] * 2)
        self.assertEqual(
            wrapper.transport.ALLOWED_REQUEST_HOSTS,
            wrapper.EXPECTED_PARENT_REQUEST_HOSTS,
        )

    def test_symlink_entrypoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            target = scripts / "build_causal_float_enrichment_v06.py"
            target.symlink_to(wrapper.ROOT / "scripts/build_causal_float_enrichment_v06.py")
            with patch.object(wrapper, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "regular non-symlink"):
                    wrapper.resolve_entrypoint(
                        "scripts/build_causal_float_enrichment_v06.py"
                    )

    def test_exact_workflow_script_invocations_resolve_peer_modules(self) -> None:
        provider = subprocess.run(
            [sys.executable, "scripts/run_provider_entrypoint_v06.py", "--help"],
            cwd=wrapper.ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(provider.returncode, 0, provider.stderr)
        self.assertNotIn("ModuleNotFoundError", provider.stderr)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            diagnostic = root / "float-normalization-rejections.json"
            float_help = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_causal_float_enrichment_v06.py",
                    "--sanitized-normalization-diagnostics",
                    str(diagnostic),
                    "--census-root",
                    str(source),
                    "--help",
                ],
                cwd=wrapper.ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(float_help.returncode, 0, float_help.stderr)
        self.assertNotIn("ModuleNotFoundError", float_help.stderr)


if __name__ == "__main__":
    unittest.main()
