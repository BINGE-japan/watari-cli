import copy
import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
BASELINE = ROOT / "docs" / "baseline"
OVERLAY = ROOT / "docs" / "governance" / "errata" / "0001.json"
OVERLAY_2 = ROOT / "docs" / "governance" / "errata" / "0002.json"
OVERLAYS = (OVERLAY, OVERLAY_2)
REGISTRY = ROOT / "docs" / "governance" / "issue-dag-overlays.jsonl"

BASELINE_DIGESTS = {
    "manifest": "fb7c6866229a17faec8b65d84a70390d94a2bbde7799cfb89d2d0cc99cda6832",
    "implementation_plan": "3cc65da6a333271d6efed00cdf13f419249d40692126c87ae02096f6bfb6d4de",
    "issue_dag": "b12d22906422da41a69e98b16e93f81c86fe570dc81fb5c8e17b5999920d4be4",
}
OVERLAY_DIGEST = "bcc4c53aa397f1352ed0196dd091fc49fe0835f410addb3a0ecc799ca911b662"
OVERLAY_DIGESTS = (
    OVERLAY_DIGEST,
    "2ba62da46e29b1c6cde8dad35c00dca793540df15ae7404366a464f35371a7b2",
)
OVERLAY_SEMANTIC_DIGESTS = (
    "c6f1279f8f0c458c62da8ceb08bd8bf3b692313aad5be81424ded5cf2a9af934",
    "eb33970821c5c24c7b4b13ad7d1ab048be424ad1755c434d6428e35c847b3ca0",
)
APPROVAL_ID = "chat-2026-07-17-gov-001-issue-dag-erratum-0001"
APPROVAL_IDS = (
    APPROVAL_ID,
    "chat-2026-07-18-gov-002-issue-dag-erratum-0002",
)
RECORD_LINE_DIGESTS = (
    "e95dbb1776e97f00da2a3d2f93d17df15858874668fdf90540891a9266729ba8",
    "ec0ad09daa8895a52602b457fa00e68e82d9be989bcc87346abfda5b4db4b013",
)
RECORD_DIGESTS = (
    "watari-overlay-record-v1:5312664adbce460a64e5f54fdcedbc0d84c0b7fb666339a45665b235b0302747",
    "watari-overlay-record-v1:607dc1957d76fc1dcc4c535858f0b1c76dee3f57b57aa4fe24e764a1670a2a8f",
)
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


def canonical_json(value):
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


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


def validate_chain(overlays, records):
    """Validate the exact approved cumulative overlays and their registry chain."""
    errors = set()
    if type(overlays) is not list or len(overlays) != 2:
        return {"chain.overlay_count"}
    if type(records) is not list or len(records) != 2:
        return {"chain.record_count"}
    if not all(type(value) is dict for value in overlays):
        return {"chain.overlay_type"}
    if not all(type(value) is dict for value in records):
        return {"chain.record_type"}

    errors.update("0001:" + error for error in validate(overlays[0], records[0]))
    expected_ids = ("issue-dag-erratum-0001", "issue-dag-erratum-0002")
    expected_paths = (
        "docs/governance/errata/0001.json",
        "docs/governance/errata/0002.json",
    )
    expected_baseline = {
        key + "_sha256": value for key, value in BASELINE_DIGESTS.items()
    }
    for index, (overlay, record) in enumerate(zip(overlays, records)):
        sequence = index + 1
        if type(overlay.get("schema_version")) is not int:
            errors.add(f"overlay{sequence}.schema_version_type")
        if type(overlay.get("sequence")) is not int:
            errors.add(f"overlay{sequence}.sequence_type")
        if type(record.get("schema_version")) is not int:
            errors.add(f"record{sequence}.schema_version_type")
        if type(record.get("sequence")) is not int:
            errors.add(f"record{sequence}.sequence_type")
        if sha256_bytes(canonical_json(overlay)) != OVERLAY_SEMANTIC_DIGESTS[index]:
            errors.add(f"overlay{sequence}.closed_semantics")
        if set(record) != REGISTRY_KEYS:
            errors.add(f"record{sequence}.schema")
            continue
        if sha256_bytes(canonical_json(record)) != RECORD_LINE_DIGESTS[index]:
            errors.add(f"record{sequence}.closed_semantics")
        expected_record = {
            "schema_version": 1,
            "sequence": sequence,
            "overlay_id": expected_ids[index],
            "overlay_path": expected_paths[index],
            "overlay_sha256": OVERLAY_DIGESTS[index],
            "baseline_sha256": BASELINE_DIGESTS,
            "previous_record_digest": None if index == 0 else RECORD_DIGESTS[0],
            "owner": "BINGE-japan",
            "approval_id": APPROVAL_IDS[index],
            "approval_evidence_locator": (
                "current-thread:user-message:" + APPROVAL_IDS[index]
            ),
            "record_digest": RECORD_DIGESTS[index],
        }
        if record != expected_record:
            errors.add(f"record{sequence}.exact")
        token = record.get("record_digest")
        if type(token) is not str or not RECORD_TOKEN.fullmatch(token):
            errors.add(f"record{sequence}.digest_type")
        elif token != record_digest(record):
            errors.add(f"record{sequence}.digest_frame")
        if overlay.get("schema_version") != 1:
            errors.add(f"overlay{sequence}.schema_version")
        if overlay.get("sequence") != sequence:
            errors.add(f"overlay{sequence}.sequence")
        if overlay.get("overlay_id") != expected_ids[index]:
            errors.add(f"overlay{sequence}.id")
        if overlay.get("baseline") != expected_baseline:
            errors.add(f"overlay{sequence}.baseline")
        if record.get("overlay_id") != overlay.get("overlay_id"):
            errors.add(f"record{sequence}.overlay_id_binding")

    for field in ("overlay_id", "overlay_path", "overlay_sha256", "approval_id"):
        values = [record.get(field) for record in records]
        if not all(type(value) is str and value for value in values):
            errors.add("chain.nonempty:" + field)
        elif len(set(values)) != 2:
            errors.add("chain.unique:" + field)
    if [overlay.get("sequence") for overlay in overlays] != [1, 2]:
        errors.add("chain.overlay_sequence")
    if [record.get("sequence") for record in records] != [1, 2]:
        errors.add("chain.record_sequence")
    if records[0].get("previous_record_digest") is not None:
        errors.add("chain.first_previous")
    if records[1].get("previous_record_digest") != records[0].get("record_digest"):
        errors.add("chain.previous")
    if records[0].get("approval_id") == records[1].get("approval_id"):
        errors.add("chain.approval_reuse")
    return errors


class IssueDagOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        actual_errata = tuple(sorted(OVERLAY.parent.glob("*.json")))
        if actual_errata != OVERLAYS:
            raise AssertionError("errata directory must contain exactly 0001 and 0002")
        cls.overlay_raws = [path.read_bytes() for path in OVERLAYS]
        cls.overlays = [strict_json(raw.decode("utf-8")) for raw in cls.overlay_raws]
        registry_raw = REGISTRY.read_bytes()
        if not registry_raw.endswith(b"\n") or registry_raw.endswith(b"\n\n"):
            raise AssertionError("registry must have exactly one terminal LF")
        raw_lines = registry_raw[:-1].split(b"\n")
        if len(raw_lines) != 2 or any(not line for line in raw_lines):
            raise AssertionError("registry must contain exactly two non-empty records")
        cls.registry_lines = [line.decode("utf-8") for line in raw_lines]
        cls.records = [strict_json(line) for line in cls.registry_lines]
        cls.overlay_raw, cls.overlay = cls.overlay_raws[0], cls.overlays[0]
        cls.registry_line, cls.record = cls.registry_lines[0], cls.records[0]

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
        for raw, expected in zip(self.overlay_raws, OVERLAY_DIGESTS):
            self.assertTrue(raw.endswith(b"\n"))
            self.assertFalse(raw.endswith(b"\n\n"))
            self.assertEqual(sha256_bytes(raw), expected)
        self.assertEqual(validate_chain(self.overlays, self.records), set())

    def test_t_gov_approval_binding(self):
        for index, (line, record) in enumerate(
            zip(self.registry_lines, self.records)
        ):
            self.assertEqual(record["approval_id"], APPROVAL_IDS[index])
            self.assertEqual(record["owner"], "BINGE-japan")
            self.assertEqual(record["record_digest"], record_digest(record))
            self.assertEqual(line.encode("utf-8"), canonical_json(record))
            self.assertEqual(sha256_bytes(line.encode("utf-8")), RECORD_LINE_DIGESTS[index])
        self.assertEqual(
            self.records[1]["previous_record_digest"],
            self.records[0]["record_digest"],
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
        repairs = {
            patch["ticket_id"]: patch for patch in self.overlays[1]["patches"]
        }
        self.assertEqual(set(repairs), {"GOV-002", "D001-R2", "D002-R1"})
        self.assertEqual(
            repairs["GOV-002"]["changed_paths"],
            [
                "docs/governance/errata/0002.json",
                "docs/governance/issue-dag-overlays.jsonl",
                "tests/governance/test_issue_dag_overlay.py",
            ],
        )
        self.assertEqual(repairs["D001-R2"]["test_contract"]["expected_test_count"], 8)
        self.assertEqual(repairs["D002-R1"]["test_contract"]["expected_test_count"], 7)

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

        def overlay_case(path, value):
            overlays = copy.deepcopy(self.overlays)
            target = overlays[1]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return overlays, copy.deepcopy(self.records)

        def record_case(index, field, value):
            records = copy.deepcopy(self.records)
            records[index][field] = value
            return copy.deepcopy(self.overlays), records

        chain_mutations = [
            overlay_case(("sequence",), True),
            overlay_case(("patches",), list(reversed(self.overlays[1]["patches"]))),
            overlay_case(("patches", 0, "changed_paths"), ["src/**"]),
            overlay_case(("patches", 0, "review_class"), "H"),
            overlay_case(("patches", 0, "network"), "allowed"),
            overlay_case(
                ("patches", 0, "diff_guideline_exception", "maximum_added_lines"),
                651,
            ),
            overlay_case(
                ("patches", 1, "mapping_contract", "sha256"), "0" * 64
            ),
            record_case(1, "approval_id", APPROVAL_IDS[0]),
            record_case(1, "previous_record_digest", RECORD_DIGESTS[1]),
            record_case(1, "overlay_path", self.records[0]["overlay_path"]),
            record_case(1, "sequence", 2.0),
            record_case(1, "overlay_sha256", "0" * 64),
        ]
        missing = copy.deepcopy(self.overlays)
        del missing[1]["activation"]
        chain_mutations.append((missing, copy.deepcopy(self.records)))
        extra = copy.deepcopy(self.overlays)
        extra[1]["unknown"] = True
        chain_mutations.append((extra, copy.deepcopy(self.records)))
        chain_mutations.append((list(reversed(self.overlays)), self.records))
        chain_mutations.append((self.overlays, list(reversed(self.records))))
        for overlays, records in chain_mutations:
            self.assertTrue(validate_chain(overlays, records))

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
