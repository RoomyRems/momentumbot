"""Register or bind original historical sources offline; never execute orders."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--bind-sources", action="store_true")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--expected-registration-sha256")
    for key in ("scanner", "management", "exit", "entry-result", "entry-consumption"):
        parser.add_argument("--" + key + "-zip", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_source_binding_v01 as m
    root = Path(__file__).resolve().parents[1]
    if args.bind_sources:
        if args.output_root is None or args.output_root.exists() or args.output_root.resolve().is_relative_to(root):
            raise ValueError("source binding requires a new external output directory")
        paths = {key: getattr(args, key + "_zip") for key in m.SOURCES}
        if any(value is None for value in paths.values()):
            raise ValueError("all five original archives required")
        with m.OriginalSources(root, paths, expected_registration_sha256=args.expected_registration_sha256) as sources:
            manifest = sources.manifest()
            access = []
            for path in manifest["paths"]:
                for slot in path["sessions"]:
                    for ref in slot["opportunity_inputs"]:
                        context = sources.context(path["path_id"], ref["opportunity_id"],
                            expected_manifest_sha256=manifest["content_sha256"])
                        access.append({"path_id": path["path_id"], "session_id": slot["session_id"],
                            "opportunity_id": ref["opportunity_id"], "context_content_sha256": context["context_content_sha256"],
                            "candidate_content_sha256": m.canonical_fingerprint(context["candidate"]),
                            "binding_content_sha256": context["binding_content_sha256"],
                            "entry_input_status": context["entry_input_status"]})
            files = m._documents({"source-bindings.json": manifest,
                "context-access-verification.json": m.seal({"contract_id": m.CONTRACT_ID,
                    "source_bindings_content_sha256": manifest["content_sha256"], "contexts": access, **m.BOUNDARY})},
                m.expected_contract(root)["content_sha256"])
            result = m.write_files(root, args.output_root, files)
            result = m.seal({**{k: v for k, v in result.items() if k != "content_sha256"},
                "source_bindings_content_sha256": manifest["content_sha256"]})
    else:
        if args.expected_registration_sha256 or any(getattr(args, key + "_zip") for key in m.SOURCES):
            raise ValueError("source archive options require --bind-sources")
        output = args.output_root or root / m.OUTPUT_PATH
        result = m.write_files(root, output, m.build_bundle(root), registration=True) if args.build else m.verify_bundle(root, output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
