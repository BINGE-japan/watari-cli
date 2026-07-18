import hashlib
import json
import re
import unittest
from pathlib import Path


DOC = Path(__file__).parents[2] / "docs" / "cli-contract.md"
BASELINE_DAG = Path(__file__).parents[2] / "docs" / "baseline" / "issue-dag.md"
EXIT_CODES = {"0", "2", "10", "11", "12", "20", "21", "30", "40", "50", "60"}
STATE_CLASSES = {"read", "canonical-write", "cache-write"}
BOOLS = {"no", "yes"}
TOKEN_CODES = {
    "USAGE": "2", "NOT_INIT": "10", "INVALID_SCHEMA": "11", "UNSUPPORTED": "12",
    "AUTH": "20", "SOURCE": "21", "GIT": "30", "INTEGRITY": "40",
    "POLICY": "50", "PARTIAL": "60",
}


EXPECTED_COMMANDS = [
    "watari --help", "watari --version", "watari init --state-only", "watari init --restore",
    "watari init", "watari setup", "watari where", "watari status", "watari doctor",
    "watari doctor --deep", "watari verify", "watari", "watari chat",
    "watari profile show", "watari profile edit", "watari profile validate", "watari profile history",
    "watari context build", "watari context explain", "watari memory list", "watari memory search",
    "watari memory show", "watari memory explain", "watari memory correct", "watari memory forget",
    "watari memory restore", "watari memory rebuild", "watari memory verify", "watari remember",
    "watari memory candidates list", "watari memory candidates show", "watari memory candidates accept",
    "watari memory candidates reject", "watari source list", "watari source add", "watari source inspect",
    "watari source test", "watari source disable", "watari source remove", "watari runtime list",
    "watari runtime add", "watari runtime set-default", "watari runtime test", "watari runtime disable",
    "watari runtime remove", "watari model list", "watari model add", "watari model set-default",
    "watari model test", "watari model disable", "watari model remove", "watari auth list",
    "watari auth login", "watari auth status", "watari auth refresh", "watari auth logout",
    "watari auth revoke", "watari project list", "watari project trust", "watari project inspect",
    "watari project revoke", "watari dream", "watari dream --dry-run", "watari dream history",
    "watari dream show", "watari sync status", "watari sync pull", "watari sync push",
    "watari conflict list", "watari conflict show", "watari conflict resolve", "watari device list",
    "watari device register", "watari device trust", "watari device revoke", "watari device set-coordinator",
    "watari backup create", "watari backup verify", "watari backup restore", "watari migrate claude inspect",
    "watari migrate claude snapshot", "watari migrate claude plan", "watari migrate claude import --dry-run",
    "watari migrate claude import --apply", "watari migrate claude verify",
]

TARGET_FIELDS = (
    "command_id", "lock_id", "command", "alias_of", "syntax", "state_class", "network", "auth",
    "external_write", "human_output", "json_output", "json_schema", "exit_codes", "failure",
    "implementation_ticket", "contract_test", "requirement_trace",
)
TARGET_SEPARATOR = "| " + " | ".join(["---"] * 17) + " |"
FIELD_RULE = "| `contract_test` | `implementation_ticket`のbaseline issue-DAG変更範囲にあるexact test path。空欄、複数path、ticket mismatchは禁止 |"
SOURCE_DOC_SHA = "7bdcf2139cd662f481df737c060e5ddc1e3ac5a322b51a3be600fb6031e6a0bd"
SOURCE_NON_MANIFEST_SHA = "4d97515f8e7281bb05403408da8c4d26513e5a15aa151cfef5ef6567ef68bf02"
SOURCE_MANIFEST_SHA = "976c5a7f3a9b92fddbe24fd3e9ea523027066d4280b923178aa8bd02781ef01d"
TARGET_DOC_SHA = "cb59eb3b98fc28a5eb6d6d6b61c3f57f0e5814b99c3c822f587d2ca225d1c738"
MAPPING_SHA = "04cb4fa4add1a3ba9fc86ea4f97d8673d4badbfb9fd8d58c5bfa1e257693a905"
TICKET_TESTS = {
    "A010": "tests/contracts/test_source_cli.py", "B002": "tests/packaging/test_entrypoint.py",
    "C001": "tests/contracts/test_profile_cli.py", "C007": "tests/contracts/test_context_memory_read_cli.py",
    "C008": "tests/contracts/test_memory_write_cli.py", "C009": "tests/contracts/test_project_cli.py",
    "G010": "tests/contracts/test_sync_device_backup_cli.py", "G011": "tests/integration/test_restore_state.py",
    "K005": "tests/contracts/test_auth_cli.py", "L007": "tests/contracts/test_migrate_cli.py",
    "M004": "tests/contracts/test_dream_cli.py", "R017": "tests/contracts/test_runtime_model_cli.py",
    "R018": "tests/integration/test_setup_wizard.py", "R019": "tests/integration/test_chat_dispatch.py",
    "S003": "tests/contracts/test_status.py", "S004": "tests/integration/test_doctor.py",
    "S015": "tests/integration/test_init_state.py", "S016": "tests/contracts/test_verify_rebuild_cli.py",
}
REPAIRS = {"CLI-030": ("C006", "C008"), "CLI-031": ("C006", "C008"), "CLI-079": ("G011", "G010")}


def parse_table(text):
    rows = []
    in_manifest = False
    headers = []
    for line in text.splitlines():
        if line.startswith("## Command manifest"):
            in_manifest = True
            continue
        if in_manifest and line.startswith("## "):
            break
        if not in_manifest or not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] == "command_id":
            headers = cells
        elif headers and len(cells) == len(headers):
            row = dict(zip(headers, cells))
            row["command"] = row["command"].strip("`")
            row["alias_of"] = row["alias_of"].strip("`")
            rows.append(row)
    return rows


def digest(value):
    return hashlib.sha256(value).hexdigest()


def exact_cells(line, count):
    assert line.startswith("| ") and line.endswith(" |")
    cells = line[2:-2].split(" | ")
    assert len(cells) == count and all(cells)
    assert line == "| " + " | ".join(cells) + " |"
    return cells


def validate_exact_mapping(text):
    assert text.endswith("\n") and "\r" not in text
    lines = text.splitlines()
    headings = [i for i, line in enumerate(lines) if line == "## Command manifest / coverage lock"]
    assert len(headings) == 1
    header_i = headings[0] + 2
    header = exact_cells(lines[header_i], 17)
    assert tuple(header) == TARGET_FIELDS
    separator = exact_cells(lines[header_i + 1], 17)
    assert lines[header_i + 1] == TARGET_SEPARATOR and separator == ["---"] * 17
    row_lines = lines[header_i + 2 : header_i + 87]
    assert len(row_lines) == 85 and not lines[header_i + 87].startswith("| CLI-")
    rows = [exact_cells(line, 17) for line in row_lines]
    assert [row[0] for row in rows] == [f"CLI-{number:03d}" for number in range(1, 86)]
    assert [row[2].strip("`") for row in rows] == EXPECTED_COMMANDS
    assert {row[14] for row in rows} == set(TICKET_TESTS)
    assert lines.count(FIELD_RULE) == 1
    rule_i = lines.index(FIELD_RULE)
    assert lines[rule_i - 1].startswith("| `implementation_ticket` |")
    assert lines[rule_i + 1].startswith("| `requirement_trace` |")
    payload_rows = {}
    for cells in rows:
        row = dict(zip(TARGET_FIELDS, cells))
        ticket = row["implementation_ticket"]
        assert ticket in TICKET_TESTS and row["contract_test"] == TICKET_TESTS[ticket]
        assert row["requirement_trace"].split(",").count(ticket) == 1
        payload_rows[row["command_id"]] = {
            "command": row["command"].strip("`"), "implementation_ticket": ticket,
            "contract_test": row["contract_test"],
        }
    payload = {"schema": "watari-cli-baseline-coverage-map/v1", "rows": payload_rows}
    assert digest(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()) == MAPPING_SHA
    scopes = {}
    for line in BASELINE_DAG.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"([A-Z][A-Z0-9-]*[0-9][A-Za-z0-9-]*) / ([LHOC])", cells[0])
        if match:
            assert match.group(1) not in scopes
            scopes[match.group(1)] = cells[2]
    for ticket, path in TICKET_TESTS.items():
        assert ticket in scopes and path in scopes[ticket]
        assert sum(path in scope for scope in scopes.values()) == 1
    excluded = set(range(header_i, header_i + 87))
    non_manifest = [line for i, line in enumerate(lines) if i not in excluded]
    non_manifest.remove(FIELD_RULE)
    assert len(non_manifest) == 72
    assert digest(("\n".join(non_manifest) + "\n").encode()) == SOURCE_NON_MANIFEST_SHA
    inverse = ["| " + " | ".join(header[:15] + [header[16]]) + " |", "| " + " | ".join(separator[:15]) + " |"]
    for cells in rows:
        source = cells[:15] + [cells[16]]
        if source[0] in REPAIRS:
            before, after = REPAIRS[source[0]]
            assert source[14] == after and source[15].endswith("," + after)
            source[14], source[15] = before, source[15][: -(len(after) + 1)]
        inverse.append("| " + " | ".join(source) + " |")
    assert len(inverse) == 87
    assert digest(("\n".join(inverse) + "\n").encode()) == SOURCE_MANIFEST_SHA
    source_lines = lines.copy()
    source_lines.pop(rule_i)
    source_header_i = source_lines.index("## Command manifest / coverage lock") + 2
    source_lines[source_header_i : source_header_i + 87] = inverse
    assert digest(("\n".join(source_lines) + "\n").encode()) == SOURCE_DOC_SHA
    assert digest(text.encode()) == TARGET_DOC_SHA
    return lines, header_i


class CliContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")
        cls.baseline_ids = set(re.findall(r"^\| ([A-Z]+[0-9]{3}) /", BASELINE_DAG.read_text(encoding="utf-8"), re.MULTILINE))
        cls.rows = parse_table(cls.text)

    def test_t_cli_schema_manifest_has_unique_ids_and_full_coverage(self):
        ids = [row["command_id"] for row in self.rows]
        locks = [row["lock_id"] for row in self.rows]
        commands = [row["command"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)), "T-CLI-SCHEMA duplicate command_id")
        self.assertEqual(len(locks), len(set(locks)), "T-CLI-SCHEMA duplicate lock_id")
        self.assertEqual(commands, EXPECTED_COMMANDS, "T-CLI-SCHEMA coverage lock differs from baseline")
        self.assertEqual(len(self.rows), len(EXPECTED_COMMANDS))

    def test_t_cli_schema_rows_have_required_fields(self):
        required = {
            "command_id", "lock_id", "command", "alias_of", "syntax", "state_class",
            "network", "auth", "external_write", "human_output", "json_output", "json_schema", "exit_codes",
            "failure", "implementation_ticket", "requirement_trace",
        }
        for row in self.rows:
            for field in required:
                self.assertTrue(row.get(field), f"T-CLI-SCHEMA empty {field}: {row}")
            self.assertIn(row["state_class"], STATE_CLASSES)
            self.assertIn(row["network"], BOOLS)
            self.assertIn(row["auth"], BOOLS)
            self.assertIn(row["external_write"], BOOLS)
            expected_json = "yes" if "--json" in row["syntax"] else "no"
            self.assertEqual(row["json_output"], expected_json, row["command"])
            if expected_json == "yes":
                self.assertRegex(row["json_schema"], r"^[a-z][a-z0-9-]+\.v[0-9]+$", row["command"])
            else:
                self.assertEqual(row["json_schema"], "-", row["command"])
            self.assertTrue(set(row["exit_codes"].split("/")) <= EXIT_CODES)
            self.assertEqual(len(row["exit_codes"].split("/")), len(set(row["exit_codes"].split("/"))), row["command"])
            tokens = set(row["failure"].split(";"))
            self.assertTrue(tokens <= set(TOKEN_CODES) | {"DRY_RUN"}, row["command"])
            implied = {TOKEN_CODES[token] for token in tokens if token in TOKEN_CODES}
            self.assertEqual(implied, set(row["exit_codes"].split("/")) - {"0"}, row["command"])
            self.assertRegex(row["command_id"], r"^CLI-[0-9]{3}$")
            self.assertRegex(row["lock_id"], r"^LOCK-[0-9]{3}$")
            self.assertIn(row["implementation_ticket"], self.baseline_ids, row["command"])
            trace = set(row["requirement_trace"].split(","))
            self.assertTrue(any(re.fullmatch(r"RQ-[0-9]{3}", item) for item in trace), row["command"])
            self.assertTrue(any(re.fullmatch(r"AC-[0-9]{3}", item) for item in trace), row["command"])

    def test_t_cli_schema_canonical_writes_require_validation_codes(self):
        required = {"INVALID_SCHEMA": "11", "INTEGRITY": "40", "POLICY": "50"}
        for row in self.rows:
            if row["state_class"] != "canonical-write":
                continue
            tokens = set(row["failure"].split(";"))
            codes = set(row["exit_codes"].split("/"))
            for token, code in required.items():
                self.assertIn(token, tokens, row["command"])
                self.assertIn(code, codes, row["command"])

    def test_t_cli_schema_command_specific_boundaries(self):
        by_command = {row["command"]: row for row in self.rows}
        self.assertEqual(by_command["watari verify"]["json_schema"], "verify.v1")
        for command in ("watari init --state-only", "watari init --restore"):
            self.assertNotIn("NOT_INIT", by_command[command]["failure"], command)
            self.assertNotIn("10", by_command[command]["exit_codes"].split("/"), command)
        for command in ("watari init", "watari setup"):
            self.assertIn("SOURCE", by_command[command]["failure"], command)
            self.assertIn("21", by_command[command]["exit_codes"].split("/"), command)
        self.assertIn("GIT", by_command["watari init"]["failure"])
        self.assertIn("30", by_command["watari init"]["exit_codes"].split("/"))
        source_add = by_command["watari source add"]
        self.assertEqual(source_add["auth"], "no")
        self.assertNotIn("AUTH", source_add["failure"])
        self.assertNotIn("20", source_add["exit_codes"].split("/"))
        dry_import = by_command["watari migrate claude import --dry-run"]
        self.assertIn("SOURCE", dry_import["failure"])
        self.assertIn("21", dry_import["exit_codes"].split("/"))
        for command in ("watari", "watari chat"):
            self.assertIn("SOURCE", by_command[command]["failure"], command)
            self.assertIn("GIT", by_command[command]["failure"], command)
            self.assertIn("21", by_command[command]["exit_codes"].split("/"), command)
            self.assertIn("30", by_command[command]["exit_codes"].split("/"), command)
        self.assertIn("GIT", by_command["watari dream"]["failure"])
        self.assertIn("30", by_command["watari dream"]["exit_codes"].split("/"))
        self.assertIn("`json_output=no`は`-`", self.text)

    def test_t_exit_stable_contains_baseline_codes(self):
        stable = re.findall(r"^\| (0|2|10|11|12|20|21|30|40|50|60) \|", self.text, re.MULTILINE)
        self.assertEqual(set(stable), EXIT_CODES, "T-EXIT-STABLE missing baseline exit code")
        for row in self.rows:
            self.assertTrue(set(row["exit_codes"].split("/")), row["command"])

    def test_t_cli_schema_alias_and_special_semantics(self):
        by_command = {row["command"]: row for row in self.rows}
        self.assertEqual(by_command["watari"]["alias_of"], "CLI-013")
        self.assertEqual(by_command["watari chat"]["alias_of"], "-")
        self.assertEqual(by_command["watari"]["syntax"], "`watari`")
        alias = by_command["watari"]
        target = next(row for row in self.rows if row["command_id"] == alias["alias_of"])
        contract_fields = ("state_class", "network", "auth", "external_write", "human_output", "json_output", "json_schema", "exit_codes", "failure", "implementation_ticket", "requirement_trace")
        for field in contract_fields:
            self.assertEqual(alias[field], target[field], f"alias field mismatch: {field}")
        doctor = by_command["watari doctor --deep"]
        self.assertEqual((doctor["state_class"], doctor["network"], doctor["auth"], doctor["external_write"]), ("read", "no", "no", "no"))
        for command in ("watari dream --dry-run", "watari migrate claude import --dry-run"):
            row = by_command[command]
            self.assertEqual(row["state_class"], "read", command)
            self.assertIn("DRY_RUN", row["failure"], command)
        self.assertIn("USAGE", self.text)
        self.assertIn("Unknown commands return `2`", self.text)
        dangerous = {
            "watari": "canonical-write",
            "watari chat": "canonical-write",
            "watari init --state-only": "canonical-write",
            "watari profile edit": "canonical-write",
            "watari memory rebuild": "cache-write",
            "watari dream": "canonical-write",
            "watari sync push": "canonical-write",
            "watari auth login": "canonical-write",
            "watari migrate claude import --apply": "canonical-write",
        }
        for command, state_class in dangerous.items():
            row = by_command[command]
            self.assertEqual(row["state_class"], state_class, command)
            self.assertIn(row["network"], BOOLS, command)
            self.assertIn(row["auth"], BOOLS, command)
            self.assertEqual(row["external_write"], "no", command)
        for row in self.rows:
            if row["state_class"] != "read" or row["network"] == "yes" or row["auth"] == "yes" or row["external_write"] == "yes":
                self.assertNotEqual(row["state_class"], "", row["command"])
                self.assertNotEqual(row["network"], "", row["command"])
                self.assertNotEqual(row["auth"], "", row["command"])
                self.assertNotEqual(row["external_write"], "", row["command"])

    def test_t_cli_schema_exact_implementation_and_contract_test_mapping(self):
        lines, header_i = validate_exact_mapping(self.text)

        def rejected(changed):
            with self.assertRaises((AssertionError, KeyError, ValueError)):
                validate_exact_mapping("\n".join(changed) + "\n")

        def replace(index, cells):
            changed = lines.copy()
            changed[index] = "| " + " | ".join(cells) + " |"
            rejected(changed)

        header = exact_cells(lines[header_i], 17)
        separator = exact_cells(lines[header_i + 1], 17)
        for position in range(17):
            replace(header_i, header[:position] + header[position + 1 :])
            replace(header_i + 1, separator[:position] + separator[position + 1 :])
            changed = separator.copy()
            changed[position] = "--"
            replace(header_i + 1, changed)
        replace(header_i + 1, separator + ["---"])
        for offset in range(85):
            index = header_i + 2 + offset
            cells = exact_cells(lines[index], 17)
            mutations = {0: "CLI-999", 2: "`watari changed`", 14: "D001", 15: "tests/changed.py", 16: "RQ-999,AC-999,D001"}
            for position, value in mutations.items():
                changed = cells.copy()
                changed[position] = value
                replace(index, changed)
            for position in range(17):
                replace(index, cells[:position] + cells[position + 1 :])
            changed = lines.copy()
            changed[index] = changed[index].replace("| ", "|", 1)
            rejected(changed)
            for action in ("missing", "duplicate"):
                changed = lines.copy()
                changed[index : index + 1] = [] if action == "missing" else [lines[index], lines[index]]
                rejected(changed)
        for first_offset in range(84):
            for second_offset in range(first_offset + 1, 85):
                changed = lines.copy()
                first, second = header_i + 2 + first_offset, header_i + 2 + second_offset
                changed[first], changed[second] = changed[second], changed[first]
                rejected(changed)
        changed = lines.copy()
        changed.insert(header_i + 87, lines[header_i + 86])
        rejected(changed)
        for index in (header_i, header_i + 1, header_i + 2):
            for value in (lines[index].replace("| ", "|", 1), lines[index][:-1], lines[index].replace(" | ", "  | ", 1)):
                changed = lines.copy()
                changed[index] = value
                rejected(changed)


if __name__ == "__main__":
    unittest.main()
