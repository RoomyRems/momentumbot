"""Unarmed exact-parent census launch gates; no authority is created on import."""
from datetime import datetime, timedelta, timezone
import importlib.metadata
import platform
from pathlib import Path
import re

from momentumbot.research import early_pullback_census_v01 as adapter

base = adapter.parent.parent
require, exact, seal, sha = adapter.require, adapter.exact, adapter.seal, adapter.sha
ID = "early-pullback-census-hosted-v0.1"
PARENT = "242e5e6516339658216269dbf85cb0590acedda0"
PARENT_TREE = "e3479b68367e467cdb0bbbd70827e5b68d4f93fb"
PARENT_SHA = "1203e49170a69c5c6eb725b77aca997a61872379c69bece4bead42a7ec6a73a7"
CONTRACT_PATH = f"research/strategy/{ID}.json"
EXECUTION_PATH = f"research/strategy/{ID}-execution.json"
WORKFLOW_PATH = ".github/workflows/early-pullback-census-hosted-v01.yml"
CONSUMPTION_REF = f"refs/tags/{ID}-consumed"
BASE = f"research/data-audits/{ID}"
LOCK = "requirements-sealed-source-v04.txt"
OWN_FILES = ("src/momentumbot/research/early_pullback_census_hosted_v01.py",
             "scripts/run_early_pullback_census_hosted_v01.py",
             "tests/test_early_pullback_census_hosted_v01.py", WORKFLOW_PATH)
ENV_KEYS = ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_EVENT_NAME",
            "GITHUB_REPOSITORY", "GITHUB_REF", "GITHUB_WORKFLOW_REF", "GITHUB_WORKFLOW_SHA",
            "CENSUS_PREFLIGHT_SHA256", "CENSUS_PREFLIGHT_ARTIFACT_ID")
RUNTIME = {"python": "3.12.14", "numpy": "2.3.5", "pandas": "2.2.3", "PyYAML": "6.0.3",
           "system": "Linux", "machine": "x86_64"}
APPROVAL_TEXT = "Approve one bounded 30-date census pass, at most 601 requests, no retries, no incremental charges or subscription changes."
PREFLIGHT_FILES = {"parent-ci.json", "parent-ci-jobs.json", "consumption-ref.json",
    "launcher-contract.json", "adapter-contract.json", "execution.json", "consumption.json", "runtime.json"}
PREFLIGHT_LIMIT = 4_000_000


def registration(root):
    inherited = adapter.validate_registration(root)
    require(inherited["content_sha256"] == PARENT_SHA, "frozen census adapter differs")
    files = set(inherited["file_bindings"]) | set(OWN_FILES) | {adapter.CONTRACT_PATH,
        adapter.BASE + "/hosted-ci-verification.json", LOCK}
    bindings = {}
    for name in sorted(files):
        path = root / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), "regular bound file required")
        raw = path.read_bytes()
        bindings[name] = {"bytes": len(raw), "sha256": sha(raw)}
    return seal({"contract_id": ID, "artifact_type": "unarmed_hosted_launcher_registration",
        "parent_commit": PARENT, "parent_tree": PARENT_TREE, "parent_registration_sha256": PARENT_SHA,
        "file_bindings": bindings, "selected_dates": list(adapter.DATES), "limits": adapter.limits(),
        "runtime": RUNTIME, "maximum_approval_lifetime_days": 7,
        "preflight_maximum_bytes": PREFLIGHT_LIMIT, "consumption_ref": CONSUMPTION_REF,
        "credential_name": "MASSIVE_API_KEY", "credential_fallback": False,
        "hypothesis": "exact-parent approval and retained single-use consumption are required before any credential read or census transport",
        "entitlement_basis": "separate explicit owner attestation required; neither a successful sample request nor a fixture proves subscription entitlement",
        "next_gate": "explicit owner approval and subscription attestation, then sole-file execution child of successfully tested code; no execution file is shipped here",
        **adapter.BOUNDARY})


def validate_registration(root):
    saved = base.frozen(root / CONTRACT_PATH)
    exact(saved, registration(root), "hosted launcher registration differs")
    return saved


def stamp(value):
    require(type(value) is str and len(value) <= 40, "bounded timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "aware timestamp required")
    return result.astimezone(timezone.utc)


def validate_approval(value, now):
    require(type(value) is dict, "explicit approval record required")
    base.hash_value(value.get("approval_record_sha256"))
    base.hash_value(value.get("entitlement_record_sha256"))
    require(value["approval_record_sha256"] != "0" * 64 and value["entitlement_record_sha256"] != "0" * 64,
            "placeholder approval evidence rejected")
    approved, expires = stamp(value.get("approved_at")), stamp(value.get("expires_at"))
    require(approved <= now < expires and expires - approved <= timedelta(days=7), "approval expired, future or overlong")
    exact(value, {"approved_at": value["approved_at"], "expires_at": value["expires_at"],
        "approval_record_sha256": value["approval_record_sha256"],
        "entitlement_record_sha256": value["entitlement_record_sha256"],
        "approved_by": "repository_owner", "statement": APPROVAL_TEXT,
        "entitlement_basis": "owner_attested_existing_subscription", "entitlement_is_provider_verified": False,
        "provider": "Massive", "credential_name": "MASSIVE_API_KEY",
        "routes": [adapter.parent.CENSUS_ROUTE, adapter.type_request()["url"]],
        "selected_dates": list(adapter.DATES), "maximum_requests": 601,
        "incremental_cost_usd": "0.00", "subscription_changes_authorized": False}, "approval/entitlement scope differs")
    return value


def execution_payload(contract, *, code_commit, code_tree, ci_run_id, approval, now):
    base.hash_value(code_commit, 40)
    base.hash_value(code_tree, 40)
    require(type(ci_run_id) is str and re.fullmatch(r"[1-9][0-9]*", ci_run_id), "CI identity required")
    validate_approval(approval, now)
    return seal({"contract_id": ID, "artifact_type": "sole_file_single_use_census_execution",
        "contract_sha256": contract["content_sha256"], "adapter_registration_sha256": PARENT_SHA,
        "code_commit_sha": code_commit, "code_tree_sha": code_tree, "successful_code_ci_run_id": ci_run_id,
        "workflow_sha256": contract["file_bindings"][WORKFLOW_PATH]["sha256"],
        "approval": approval, "limits": adapter.limits(), "consumption_ref": CONSUMPTION_REF,
        "single_use_census_execution_authorized": True, **adapter.BOUNDARY})


def validate_execution(execution, contract, env, facts, now):
    expected = execution_payload(contract, code_commit=facts["parent_commit"], code_tree=facts["parent_tree"],
        ci_run_id=execution.get("successful_code_ci_run_id"), approval=execution.get("approval"), now=now)
    exact(execution, expected, "exact tested execution parent required")
    exact(facts["changed_files"], ["A\t" + EXECUTION_PATH], "sole added execution file required")
    exact(facts["parents"], [facts["parent_commit"]], "single parent required")
    base.hash_value(facts["head"], 40)
    require(facts["clean"] is True and facts["head"] == env.get("GITHUB_SHA"), "clean exact checkout required")
    require(env.get("GITHUB_REPOSITORY") == "RoomyRems/momentumbot"
        and env.get("GITHUB_EVENT_NAME") == "push" and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and env.get("GITHUB_REF") == "refs/heads/phase-3-historical-snapshot"
        and env.get("GITHUB_WORKFLOW_SHA") == facts["head"]
        and env.get("GITHUB_WORKFLOW_REF") == "RoomyRems/momentumbot/" + WORKFLOW_PATH + "@refs/heads/phase-3-historical-snapshot"
        and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")), "first-attempt exact-workflow research push required")
    return execution


def validate_ci(receipt, jobs, execution):
    base.validate_ci(receipt, execution)
    require(type(jobs) is dict and type(jobs.get("total_count")) is int
        and jobs["total_count"] == 1 and type(jobs.get("jobs")) is list and len(jobs["jobs"]) == 1,
        "complete single-job CI inventory required")
    job = jobs["jobs"][0]
    require(str(job.get("run_id")) == execution["successful_code_ci_run_id"]
        and job.get("head_sha") == execution["code_commit_sha"] and job.get("name") == "test"
        and job.get("status") == "completed" and job.get("conclusion") == "success", "exact successful test job required")
    steps = job.get("steps")
    require(type(steps) is list and steps and {"Install package", "Run tests", "Compile"} <= {s.get("name") for s in steps}
        and all(s.get("status") == "completed" and s.get("conclusion") == "success" for s in steps), "all CI steps must succeed")


def validate_ref(value, env):
    require(value.get("ref") == CONSUMPTION_REF and value.get("object", {}).get("type") == "commit"
        and value.get("object", {}).get("sha") == env["GITHUB_SHA"], "permanent consumption ref differs")


def consumption(execution, env):
    return seal({"contract_id": ID, "execution_sha256": execution["content_sha256"],
        "execution_commit_sha": env["GITHUB_SHA"], "workflow_run_id": env["GITHUB_RUN_ID"],
        "workflow_run_attempt": 1, "consumption_ref": CONSUMPTION_REF})


def runtime_facts():
    return {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine(),
            **{p: importlib.metadata.version(p) for p in ("numpy", "pandas", "PyYAML")}}


def read_preflight(path, *, complete):
    path = Path(path)
    require(path.is_dir() and not any(p.is_symlink() for p in (path, *path.parents)), "regular preflight directory required")
    expected = PREFLIGHT_FILES | {"preflight-inventory.json"} if complete else {"parent-ci.json", "parent-ci-jobs.json", "consumption-ref.json"}
    files = list(path.iterdir())
    require({p.name for p in files} == expected and all(p.is_file() and not p.is_symlink() for p in files), "exact preflight population required")
    require(sum(p.stat().st_size for p in files) <= PREFLIGHT_LIMIT, "preflight byte limit")
    return {p.name: p.read_bytes() for p in files}


def expected_preflight(contract, adapter_contract, execution, env, runtime):
    exact(runtime, RUNTIME, "frozen runtime differs")
    return {"launcher-contract.json": contract, "adapter-contract.json": adapter_contract,
        "execution.json": execution, "consumption.json": consumption(execution, env), "runtime.json": runtime}


def prepare(path, contract, adapter_contract, execution, env, runtime):
    files = read_preflight(path, complete=False)
    validate_ci(base.json_object(files["parent-ci.json"]), base.json_object(files["parent-ci-jobs.json"]), execution)
    validate_ref(base.json_object(files["consumption-ref.json"]), env)
    for name, value in expected_preflight(contract, adapter_contract, execution, env, runtime).items():
        raw = adapter.render(value)
        with (path / name).open("xb") as handle:
            handle.write(raw)
        files[name] = raw
    inventory = seal({"contract_id": ID, "files": {name: {"bytes": len(raw), "sha256": sha(raw)} for name, raw in sorted(files.items())}})
    raw_inventory = adapter.render(inventory)
    require(sum(map(len, files.values())) + len(raw_inventory) <= PREFLIGHT_LIMIT, "preflight byte limit")
    with (path / "preflight-inventory.json").open("xb") as handle:
        handle.write(raw_inventory)
    return sha(raw_inventory)


def verify_preflight(files, contract, adapter_contract, execution, env, runtime, live_ref, artifact):
    require(set(files) == PREFLIGHT_FILES | {"preflight-inventory.json"}
        and all(type(v) is bytes for v in files.values()) and sum(map(len, files.values())) <= PREFLIGHT_LIMIT,
        "bounded exact preflight bytes required")
    pin = env.get("CENSUS_PREFLIGHT_SHA256")
    base.hash_value(pin)
    require(sha(files["preflight-inventory.json"]) == pin, "independent consumption-job inventory pin differs")
    expected_inventory = seal({"contract_id": ID, "files": {name: {"bytes": len(raw), "sha256": sha(raw)} for name, raw in sorted(files.items()) if name != "preflight-inventory.json"}})
    exact(base.json_object(files["preflight-inventory.json"]), expected_inventory, "preflight byte commitments differ")
    for name, value in expected_preflight(contract, adapter_contract, execution, env, runtime).items():
        require(files[name] == adapter.render(value), "durable preflight projection differs")
    validate_ci(base.json_object(files["parent-ci.json"]), base.json_object(files["parent-ci-jobs.json"]), execution)
    validate_ref(base.json_object(files["consumption-ref.json"]), env)
    validate_ref(live_ref, env)
    require(re.fullmatch(r"[1-9][0-9]*", env.get("CENSUS_PREFLIGHT_ARTIFACT_ID", ""))
        and type(artifact.get("id")) is int and str(artifact["id"]) == env["CENSUS_PREFLIGHT_ARTIFACT_ID"]
        and artifact.get("name") == "early-pullback-census-hosted-v01-consumption-" + env["GITHUB_RUN_ID"] + "-1"
        and artifact.get("expired") is False
        and str(artifact.get("workflow_run", {}).get("id")) == env["GITHUB_RUN_ID"]
        and artifact["workflow_run"].get("head_sha") == env["GITHUB_SHA"]
        and artifact["workflow_run"].get("head_branch") == "phase-3-historical-snapshot", "exact durable consumption artifact required")
    require(type(artifact.get("digest")) is str and artifact["digest"].startswith("sha256:"), "artifact digest required")
    base.hash_value(artifact["digest"][7:])
    require(type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= PREFLIGHT_LIMIT, "bounded artifact size required")
    return consumption(execution, env)


def capture(*, root, output, preflight, env, facts, now, runtime, live_ref, artifact,
            credential_loader, transport_factory, session_factory=adapter.CaptureSession):
    """Validate every gate before invoking the credential loader; no retries."""
    contract = validate_registration(root)
    adapter_contract = adapter.validate_registration(root)
    execution = validate_execution(base.frozen(root / EXECUTION_PATH), contract, env, facts, now)
    marker = verify_preflight(preflight, contract, adapter_contract, execution, env, runtime, live_ref, artifact)
    output = Path(output)
    require(not any(p.is_symlink() for p in (output, *output.parents)), "regular new output required")
    output.mkdir(parents=True, exist_ok=False)
    launch = output / "launch"
    launch.mkdir()
    for name, raw in preflight.items():
        with (launch / name).open("xb") as handle:
            handle.write(raw)
    for name, value in (("current-ref.json", live_ref), ("artifact-metadata.json", artifact)):
        base.write_once(launch / name, value)
    failure, result = "interrupted", None
    try:
        credential = credential_loader()
        runner = session_factory(adapter_contract, output=output / "capture", transport=transport_factory(), credential=credential)
        result = runner.run()
        failure = None if result["protocol_complete"] else "capture_failed"
        return result
    except Exception:
        failure = "launch_failed"
        raise
    finally:
        links = {}
        for name in ("report.json", "inventory.json"):
            path = output / "capture" / name
            links[name] = {"bytes": path.stat().st_size, "sha256": sha(path.read_bytes())} if path.is_file() else None
        base.write_once(launch / "capture-link.json", seal({"contract_id": ID, "consumption": marker,
            "preflight_inventory_sha256": env["CENSUS_PREFLIGHT_SHA256"], "capture_files": links,
            "failure": failure, "protocol_complete": result is not None and result["protocol_complete"],
            "provider_origin_independently_verified": False, **adapter.BOUNDARY}))
