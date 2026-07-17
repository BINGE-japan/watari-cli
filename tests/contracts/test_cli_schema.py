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


if __name__ == "__main__":
    unittest.main()
