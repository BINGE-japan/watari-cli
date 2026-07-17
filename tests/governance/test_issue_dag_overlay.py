import copy
import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
BASELINE = ROOT / "docs" / "baseline"
OVERLAY = ROOT / "docs" / "governance" / "errata" / "0001.json"
REGISTRY = ROOT / "docs" / "governance" / "issue-dag-overlays.jsonl"

BASELINE_DIGESTS = {
    "manifest": "fb7c6866229a17faec8b65d84a70390d94a2bbde7799cfb89d2d0cc99cda6832",
    "implementation_plan": "3cc65da6a333271d6efed00cdf13f419249d40692126c87ae02096f6bfb6d4de",
    "issue_dag": "b12d22906422da41a69e98b16e93f81c86fe570dc81fb5c8e17b5999920d4be4",
}
OVERLAY_DIGEST = "bcc4c53aa397f1352ed0196dd091fc49fe0835f410addb3a0ecc799ca911b662"
APPROVAL_ID = "chat-2026-07-17-gov-001-issue-dag-erratum-0001"
RECORD_TOKEN = re.compile(r"^watari-overlay-record-v1:[0-9a-f]{64}$")
AGENTS_SHA256 = "7b52c4d016b538fb8eff472da4b17ce0499400a393e68ddc9132273273e6c19b"

EXPECTED_EXECUTION_GOVERNANCE = """The baseline files remain immutable. Narrow execution-metadata corrections are
active only when listed in `docs/governance/issue-dag-overlays.jsonl`, bound to
the exact baseline and overlay byte digests, and explicitly approved by the
owner named in the registry record. The effective order is:

1. this file's safety boundary and implementation discipline;
2. the frozen parent implementation plan;
3. only the fields explicitly enumerated by a validated, activated overlay;
4. every unmodified field of the frozen issue DAG.

Unknown overlays, fields, operations, wildcard paths, sequence gaps, broken
hash chains, missing approvals, or digest mismatches fail closed. An overlay
cannot expand network, credential, live-read, external-write, or review
authority. `tests/governance/test_issue_dag_overlay.py` is the executable
validator; an unregistered erratum file has no authority."""

OVERLAY_KEYS = {
    "schema_version",
    "overlay_id",
    "sequence",
    "baseline",
    "activation",
    "patches",
    "unchanged_invariants",
    "observed_process_deviations",
}
REGISTRY_KEYS = {
    "schema_version",
    "sequence",
    "overlay_id",
    "overlay_path",
    "overlay_sha256",
    "baseline_sha256",
    "previous_record_digest",
    "owner",
    "approval_id",
    "approval_evidence_locator",
    "record_digest",
}
D005_KEYS = {
    "operation",
    "ticket_id",
    "dependencies_before",
    "dependencies_after",
    "changed_paths_before",
    "changed_paths_after",
    "test_contract",
    "diff_guideline_exception",
    "review_class",
    "safety_authority_change",
}
D001_R1_KEYS = {
    "operation",
    "ticket_id",
    "dependencies",
    "changed_paths",
    "test_contract",
    "requirements_document_changes",
    "review_class",
    "network",
    "credentials",
    "live_data",
    "external_write",
}
TEST_CONTRACT_KEYS = {
    "test_path",
    "command",
    "expected_exit",
    "case_ids",
}


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def strict_json(text):
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicates)


def canonical_record_body(record):
    body = {key: value for key, value in record.items() if key != "record_digest"}
    return json.dumps(
        body, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def record_digest(record):
    body = canonical_record_body(record)
    frame = (
        b"WATARI\x00issue-dag-overlay-record/v1\x00"
        + len(body).to_bytes(8, "big")
        + body
    )
    return "watari-overlay-record-v1:" + sha256_bytes(frame)


def overlay_bytes(overlay):
    return (json.dumps(overlay, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )


def path_is_exact(path):
    return (
        type(path) is str
        and bool(path)
        and not path.startswith(("/", "../"))
        and ".." not in Path(path).parts
        and not any(token in path for token in ("*", "?", "[", "]"))
    )


def validate(overlay, record):
    errors = set()

    if type(overlay) is not dict or set(overlay) != OVERLAY_KEYS:
        return {"overlay.schema"}
    if type(record) is not dict or set(record) != REGISTRY_KEYS:
        return {"registry.schema"}

    if overlay["schema_version"] != 1:
        errors.add("overlay.schema_version")
    if overlay["overlay_id"] != "issue-dag-erratum-0001":
        errors.add("overlay.id")
    if overlay["sequence"] != 1:
        errors.add("overlay.sequence")
    if set(overlay["baseline"]) != {
        "manifest_sha256",
        "implementation_plan_sha256",
        "issue_dag_sha256",
    }:
        errors.add("overlay.baseline.schema")
    else:
        expected = {key + "_sha256": value for key, value in BASELINE_DIGESTS.items()}
        if overlay["baseline"] != expected:
            errors.add("overlay.baseline.digest")

    activation = overlay["activation"]
    expected_activation = {
        "mode": "registered-owner-approval-only",
        "owner": "BINGE-japan",
        "review_class": "O",
        "existing_approval_reuse": "forbidden",
        "approval_binding": "registry-record-must-bind-raw-overlay-sha256",
    }
    if activation != expected_activation:
        errors.add("overlay.activation")

    patches = overlay["patches"]
    if type(patches) is not list or len(patches) != 2:
        return errors | {"overlay.patches"}
    by_id = {
        patch.get("ticket_id"): patch
        for patch in patches
        if type(patch) is dict
    }
    if set(by_id) != {"D005", "D001-R1"} or len(by_id) != 2:
        return errors | {"overlay.patch_ids"}

    d005 = by_id["D005"]
    if set(d005) != D005_KEYS:
        errors.add("D005.schema")
    else:
        if d005["operation"] != "replace-ticket-execution-metadata":
            errors.add("D005.operation")
        if d005["dependencies_before"] != ["D001"]:
            errors.add("D005.dependencies_before")
        if d005["dependencies_after"] != ["D001", "D003"]:
            errors.add("D005.dependencies_after")
        expected_before = [
            "docs/threat-model.md",
            "docs/adr/005-data-routes.md",
        ]
        expected_after = expected_before + [
            "tests/contracts/test_route_matrix.py"
        ]
        if d005["changed_paths_before"] != expected_before:
            errors.add("D005.paths_before")
        if d005["changed_paths_after"] != expected_after:
            errors.add("D005.paths_after")
        if not all(path_is_exact(path) for path in d005["changed_paths_after"]):
            errors.add("D005.path_not_exact")
        if d005["review_class"] != "H":
            errors.add("D005.review_class")
        if d005["safety_authority_change"] != "none":
            errors.add("D005.safety_authority")

        contract = d005["test_contract"]
        if set(contract) != TEST_CONTRACT_KEYS | {"expected_test_count"}:
            errors.add("D005.test.schema")
        else:
            if contract["test_path"] != expected_after[-1]:
                errors.add("D005.test.path")
            if contract["expected_exit"] != 0 or contract["expected_test_count"] != 20:
                errors.add("D005.test.expectation")
            cases = contract["case_ids"]
            if (
                type(cases) is not list
                or len(cases) != 20
                or len(set(cases)) != 20
                or not all(case.startswith("test_t_") for case in cases)
            ):
                errors.add("D005.test.cases")

        exception = d005["diff_guideline_exception"]
        expected_exception_keys = {
            "baseline_guideline_added_lines",
            "maximum_added_lines",
            "maximum_changed_files",
            "reason",
            "applies_only_to_ticket",
        }
        if set(exception) != expected_exception_keys:
            errors.add("D005.diff_exception.schema")
        elif (
            exception["baseline_guideline_added_lines"] != 300
            or exception["maximum_added_lines"] != 5000
            or exception["maximum_changed_files"] != 3
            or exception["applies_only_to_ticket"] != "D005"
            or type(exception["reason"]) is not str
            or not exception["reason"]
        ):
            errors.add("D005.diff_exception")

    repair = by_id["D001-R1"]
    if set(repair) != D001_R1_KEYS:
        errors.add("D001-R1.schema")
    else:
        if repair["operation"] != "add-repair-ticket":
            errors.add("D001-R1.operation")
        if repair["dependencies"] != ["GOV-001", "D001"]:
            errors.add("D001-R1.dependencies")
        if repair["changed_paths"] != [
            "tests/contracts/test_requirements_trace.py"
        ]:
            errors.add("D001-R1.paths")
        if not all(path_is_exact(path) for path in repair["changed_paths"]):
            errors.add("D001-R1.path_not_exact")
        contract = repair["test_contract"]
        if set(contract) != TEST_CONTRACT_KEYS:
            errors.add("D001-R1.test.schema")
        else:
            if contract["test_path"] != repair["changed_paths"][0]:
                errors.add("D001-R1.test.path")
            if contract["expected_exit"] != 0:
                errors.add("D001-R1.test.exit")
            if contract["case_ids"] != [
                "T-REQ-TRACE-001",
                "T-REQ-TRACE-002",
                "T-REQ-TRACE-003",
                "T-REQ-TRACE-004",
                "T-REQ-TRACE-005",
                "T-REQ-TRACE-006",
            ]:
                errors.add("D001-R1.test.cases")
        for field in (
            "requirements_document_changes",
            "network",
            "credentials",
            "live_data",
            "external_write",
        ):
            expected_value = "forbidden" if field == "requirements_document_changes" else "none"
            if repair[field] != expected_value:
                errors.add("D001-R1.authority:" + field)
        if repair["review_class"] != "H":
            errors.add("D001-R1.review_class")

    expected_invariants = [
        "baseline-files-remain-byte-identical",
        "all-unlisted-issue-dag-fields-remain-authoritative",
        "unknown-overlay-or-field-fails-closed",
        "overlay-sequence-and-hash-chain-are-contiguous",
        "network-credential-live-read-and-external-write-authority-do-not-expand",
        "ticket-review-classes-and-independent-review-requirements-do-not-weaken",
    ]
    if overlay["unchanged_invariants"] != expected_invariants:
        errors.add("overlay.invariants")
    expected_deviations = [
        "D001-completed-without-an-executable-T-REQ-TRACE-artifact",
        "D005-work-started-before-this-overlay-was-approved",
        "test-first-ordering-cannot-be-retroactively-restored",
        "activation-does-not-reclassify-past-work-as-compliant",
    ]
    if overlay["observed_process_deviations"] != expected_deviations:
        errors.add("overlay.process_deviations")

    if record["schema_version"] != 1 or record["sequence"] != 1:
        errors.add("registry.version_or_sequence")
    if record["overlay_id"] != overlay["overlay_id"]:
        errors.add("registry.overlay_id")
    if record["overlay_path"] != "docs/governance/errata/0001.json":
        errors.add("registry.overlay_path")
    if record["overlay_sha256"] != OVERLAY_DIGEST:
        errors.add("registry.overlay_digest")
    if sha256_bytes(overlay_bytes(overlay)) != record["overlay_sha256"]:
        errors.add("registry.overlay_bytes")
    if record["baseline_sha256"] != BASELINE_DIGESTS:
        errors.add("registry.baseline")
    if record["previous_record_digest"] is not None:
        errors.add("registry.previous")
    if record["owner"] != "BINGE-japan":
        errors.add("registry.owner")
    if record["approval_id"] != APPROVAL_ID:
        errors.add("registry.approval_id")
    if record["approval_evidence_locator"] != (
        "current-thread:user-message:" + APPROVAL_ID
    ):
        errors.add("registry.approval_evidence")
    if not RECORD_TOKEN.fullmatch(record["record_digest"]):
        errors.add("registry.record_token")
    elif record["record_digest"] != record_digest(record):
        errors.add("registry.record_digest")
    return errors


class IssueDagOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay_raw = OVERLAY.read_bytes()
        cls.overlay = strict_json(cls.overlay_raw.decode("utf-8"))
        lines = REGISTRY.read_text(encoding="utf-8").splitlines()
        if len(lines) != 1 or not lines[0]:
            raise AssertionError("registry must contain exactly one record")
        cls.registry_line = lines[0]
        cls.record = strict_json(lines[0])

    def test_t_gov_baseline_digest(self):
        paths = {
            "manifest": BASELINE / "manifest.json",
            "implementation_plan": BASELINE / "implementation-plan.md",
            "issue_dag": BASELINE / "issue-dag.md",
        }
        for key, path in paths.items():
            self.assertEqual(sha256_bytes(path.read_bytes()), BASELINE_DIGESTS[key])
        manifest = strict_json((BASELINE / "manifest.json").read_text("utf-8"))
        self.assertEqual(
            manifest["files"]["implementation-plan.md"],
            "sha256:" + BASELINE_DIGESTS["implementation_plan"],
        )
        self.assertEqual(
            manifest["files"]["issue-dag.md"],
            "sha256:" + BASELINE_DIGESTS["issue_dag"],
        )

    def test_t_gov_overlay_closed(self):
        self.assertEqual(sha256_bytes(self.overlay_raw), OVERLAY_DIGEST)
        self.assertEqual(validate(self.overlay, self.record), set())

    def test_t_gov_approval_binding(self):
        self.assertEqual(self.record["approval_id"], APPROVAL_ID)
        self.assertEqual(self.record["owner"], "BINGE-japan")
        self.assertEqual(self.record["record_digest"], record_digest(self.record))
        self.assertEqual(
            self.registry_line,
            json.dumps(
                self.record,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

    def test_t_gov_design_test_scope(self):
        issue_dag = (BASELINE / "issue-dag.md").read_text(encoding="utf-8")
        design_rows = {
            match.group(1): match.group(0)
            for match in re.finditer(r"^\| (D\d{3}) /.*$", issue_dag, re.MULTILINE)
        }
        self.assertEqual(set(design_rows), {f"D{i:03d}" for i in range(1, 13)})
        for ticket in sorted(set(design_rows) - {"D001", "D005"}):
            self.assertRegex(
                design_rows[ticket],
                r"tests/|storage_harness\.py",
                ticket,
            )
        patches = {patch["ticket_id"]: patch for patch in self.overlay["patches"]}
        self.assertEqual(
            patches["D005"]["test_contract"]["test_path"],
            "tests/contracts/test_route_matrix.py",
        )
        self.assertEqual(
            patches["D001-R1"]["changed_paths"],
            ["tests/contracts/test_requirements_trace.py"],
        )

    def test_t_gov_mutation_corpus(self):
        mutations = []

        overlay = copy.deepcopy(self.overlay)
        overlay["unknown"] = True
        mutations.append((overlay, self.record))

        overlay = copy.deepcopy(self.overlay)
        overlay["patches"][0]["changed_paths_after"].append("src/**")
        mutations.append((overlay, self.record))

        overlay = copy.deepcopy(self.overlay)
        overlay["patches"][0]["dependencies_after"] = ["D001"]
        mutations.append((overlay, self.record))

        overlay = copy.deepcopy(self.overlay)
        overlay["baseline"]["issue_dag_sha256"] = "0" * 64
        mutations.append((overlay, self.record))

        record = copy.deepcopy(self.record)
        record["approval_id"] = ""
        mutations.append((self.overlay, record))

        record = copy.deepcopy(self.record)
        record["overlay_sha256"] = "0" * 64
        mutations.append((self.overlay, record))

        record = copy.deepcopy(self.record)
        record["previous_record_digest"] = "watari-overlay-record-v1:" + "0" * 64
        mutations.append((self.overlay, record))

        record = copy.deepcopy(self.record)
        record["unknown"] = True
        mutations.append((self.overlay, record))

        for overlay, record in mutations:
            self.assertTrue(validate(overlay, record))

        with self.assertRaises(ValueError):
            strict_json('{"sequence":1,"sequence":2}')

    def test_t_gov_entrypoint_precedence(self):
        agents_raw = (ROOT / "AGENTS.md").read_bytes()
        self.assertEqual(sha256_bytes(agents_raw), AGENTS_SHA256)
        agents = agents_raw.decode("utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        matches = list(re.finditer(
            r"^## Execution governance\n\n(?P<body>.*?)\n\n(?=^## )",
            agents,
            re.MULTILINE | re.DOTALL,
        ))
        self.assertEqual(len(matches), 1, "execution-governance section must be unique")
        self.assertEqual(matches[0].group("body"), EXPECTED_EXECUTION_GOVERNANCE)
        self.assertIn("issue-dag-overlays.jsonl", readme)


if __name__ == "__main__":
    unittest.main()
