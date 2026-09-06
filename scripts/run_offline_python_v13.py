"""Execute a registered recovery command with network/process I/O denied.

This guard applies to the scientific replay process, not package installation
or the explicitly authorized GitHub artifact transfer in the workflow.
"""

from __future__ import annotations

from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SCRIPTS = {
    "scripts/build_causal_scanner_snapshot_v10.py",
    "scripts/build_sealed_historical_source_checkpoint_v10.py",
    "scripts/run_sealed_historical_source_acquisition_v13.py",
}


def deny_external_io(event: str, args: tuple[object, ...]) -> None:
    if event.startswith("socket.") or event in {
        "subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp",
        "os.exec", "os.fork", "os.forkpty",
    }:
        raise RuntimeError("provider-free recovery forbids network/process I/O")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in ALLOWED_SCRIPTS:
        raise SystemExit("an exact registered offline recovery script is required")
    relative, *script_arguments = arguments
    if relative.endswith("build_causal_scanner_snapshot_v10.py"):
        if script_arguments.count("--phase") != 1:
            raise SystemExit("offline scanner requires one explicit freeze phase")
        index = script_arguments.index("--phase")
        if script_arguments[index + 1:index + 2] != ["freeze-snapshots"]:
            raise SystemExit("only provider-free freeze-snapshots is permitted")
    script = ROOT / relative
    if script.is_symlink() or not script.is_file():
        raise SystemExit("recovery script must be a regular file")
    sys.addaudithook(deny_external_io)
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.argv = [str(script), *script_arguments]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
