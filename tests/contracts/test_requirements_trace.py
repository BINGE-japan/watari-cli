"""D001 requirements trace contract (T-REQ-TRACE-001..006).

D001-R1 forbids requirements-document changes, so raw source digests are the
first gate.  The semantic checks then parse the one canonical Markdown table
form used by the frozen documents.  A future owner-approved document revision
must update both the digest and these explicit checks.
"""

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REQ_PATH = ROOT / "docs" / "requirements.md"
DEC_PATH = ROOT / "docs" / "decisions.md"
PLAN_PATH = ROOT / "docs" / "baseline" / "implementation-plan.md"
DAG_PATH = ROOT / "docs" / "baseline" / "issue-dag.md"

DIGESTS = {
    "requirements": "b2ade4aff4372e94f284237b66a5c873012397bd2b3281debca246a4a4056e80",
    "decisions": "0a2777989164cc0773c64ab91e032d72fe5e39384d7418ff6859547cc2e88981",
    "plan": "3cc65da6a333271d6efed00cdf13f419249d40692126c87ae02096f6bfb6d4de",
    "dag": "b12d22906422da41a69e98b16e93f81c86fe570dc81fb5c8e17b5999920d4be4",
}

DOMAIN_SPECS = {
    "User requirements": ("id", "kind", "requirement", "acceptance", "status", "owner", "trace"),
    "Non-goals": ("id", "kind", "non-goal", "acceptance boundary", "status", "owner", "trace"),
    "Acceptance criteria": ("id", "kind", "observable result", "status", "owner", "trace"),
    "Runtime/source matrices": ("id", "matrix", "capability", "required runtime/source", "data class", "required test/gate", "support", "trace"),
    "Mandatory sandbox contract": ("id", "kind", "invariant", "verification", "status", "owner", "trace"),
}
DECISION_SPECS = {
    "Frozen decisions": ("id", "decision", "status", "owner", "rationale", "consequences", "trace"),
    "Open decisions": ("id", "decision", "status", "owner", "reason it remains open", "close gate", "trace"),
}
PREFIXES = {
    "User requirements": ("RQ", "requirement"),
    "Non-goals": ("NM", "non-goal"),
    "Acceptance criteria": ("AC", "acceptance"),
    "Runtime/source matrices": ("MX", None),
    "Mandatory sandbox contract": ("SB", "sandbox"),
}

TRACE_GRAMMAR = re.compile(
    r"`[A-Z][A-Z0-9-]*[0-9][A-Za-z0-9-]*`"
    r"(?:, `[A-Z][A-Z0-9-]*[0-9][A-Za-z0-9-]*`)*"
)
TRACE_TOKEN = re.compile(r"`([A-Z][A-Z0-9-]*[0-9][A-Za-z0-9-]*)`")


class ContractError(AssertionError):
    pass


def require(value: bool, code: str, detail: str) -> None:
    if not value:
        raise ContractError(f"{code}: {detail}")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def split_row(line: str, code: str) -> list[str]:
    require(line.startswith("|") and line.endswith("|"), code, "noncanonical row")
    return [cell.strip() for cell in line[1:-1].split("|")]


def parse_tables(text: str, specs: dict[str, tuple[str, ...]], code: str):
    headings = list(re.finditer(r"^## ([^\n]+)\n", text, re.MULTILINE))
    tables = {}
    for title, headers in specs.items():
        matches = [item for item in headings if item.group(1) == title]
        require(len(matches) == 1, code, f"section count {title}")
        match = matches[0]
        later = [item.start() for item in headings if item.start() > match.start()]
        body = text[match.end() : min(later, default=len(text))]
        groups, group = [], []
        for line in body.splitlines():
            if line.startswith("|"):
                group.append(line)
            elif group:
                groups.append(group)
                group = []
        if group:
            groups.append(group)
        require(len(groups) == 1 and len(groups[0]) >= 3, code, f"table count {title}")
        lines = groups[0]
        require(tuple(split_row(lines[0], code)) == headers, code, f"headers {title}")
        separator = split_row(lines[1], code)
        require(len(separator) == len(headers) and set(separator) == {"---"}, code, f"separator {title}")
        rows = []
        for line in lines[2:]:
            cells = split_row(line, code)
            require(len(cells) == len(headers) and all(cells), code, f"row shape {title}")
            rows.append(dict(zip(headers, cells)))
        tables[title] = rows
    return tables


def parse_domain(text: str, code: str):
    tables = parse_tables(text, DOMAIN_SPECS, code)
    ids = []
    for title, rows in tables.items():
        prefix, kind = PREFIXES[title]
        for row in rows:
            require(re.fullmatch(rf"{prefix}-[0-9]{{3}}", row["id"]) is not None, code, "ID grammar")
            if kind is not None:
                require(row["kind"] == kind and row["status"] in {"frozen", "open"}, code, row["id"])
            ids.append(row["id"])
    require(len(ids) == len(set(ids)), code, "duplicate domain ID")
    observed = re.findall(r"^\| ((?:RQ|NM|AC|MX|SB)-[0-9]{3}) \|", text, re.MULTILINE)
    require(sorted(observed) == sorted(ids), code, "domain row outside named table")
    return tables


def index(rows, code: str):
    result = {row["id"]: row for row in rows}
    require(len(result) == len(rows), code, "duplicate ID")
    return result


def tokens(cell: str, code: str, row_id: str):
    require(TRACE_GRAMMAR.fullmatch(cell) is not None, code, f"trace grammar {row_id}")
    result = TRACE_TOKEN.findall(cell)
    require(len(result) == len(set(result)), code, f"duplicate trace {row_id}")
    return result


def baseline_ids(plan: str, dag: str):
    result = set(re.findall(r"^\| ([A-Z][A-Z0-9-]*[0-9][A-Za-z0-9-]*) / [LHOC] \|", dag, re.MULTILINE))
    result.update(re.findall(r"^### (B000)\b", dag, re.MULTILINE))
    result.update(re.findall(r"^### (ADR-[0-9]{3}):\s", plan, re.MULTILINE))
    result.update(re.findall(r"^### (P[0-9]+[a-z]?)\s", plan, re.MULTILINE))
    return result


def expected(prefix: str, last: int):
    return {f"{prefix}-{number:03d}" for number in range(1, last + 1)}


def row_line(text: str, row_id: str):
    found = [line for line in text.splitlines() if line.startswith(f"| {row_id} |")]
    if len(found) != 1:
        raise AssertionError(f"mutation row count {row_id}: {len(found)}")
    return found[0]


def mutate(text: str, row_id: str, position: int, value: str):
    line = row_line(text, row_id)
    cells = split_row(line, "MUTATION")
    cells[position] = value
    replacement = "| " + " | ".join(cells) + " |"
    require(text.count(line) == 1, "MUTATION", "ambiguous row")
    return text.replace(line, replacement, 1)


def delete(text: str, row_id: str):
    line = row_line(text, row_id) + "\n"
    require(text.count(line) == 1, "MUTATION", "ambiguous deletion")
    return text.replace(line, "", 1)


class RequirementsTraceTest(unittest.TestCase):
    def setUp(self):
        self.req_raw, self.dec_raw = REQ_PATH.read_bytes(), DEC_PATH.read_bytes()
        self.plan_raw, self.dag_raw = PLAN_PATH.read_bytes(), DAG_PATH.read_bytes()
        for name, raw in (("requirements", self.req_raw), ("decisions", self.dec_raw), ("plan", self.plan_raw), ("dag", self.dag_raw)):
            self.assertEqual(digest(raw), DIGESTS[name], name)
        self.req, self.dec = self.req_raw.decode(), self.dec_raw.decode()
        self.plan, self.dag = self.plan_raw.decode(), self.dag_raw.decode()

    def tearDown(self):
        for name, path in (("requirements", REQ_PATH), ("decisions", DEC_PATH), ("plan", PLAN_PATH), ("dag", DAG_PATH)):
            self.assertEqual(digest(path.read_bytes()), DIGESTS[name], name)

    def rejected(self, function, *args):
        with self.assertRaises(ContractError):
            function(*args)

    def test_t_req_trace_001_domain_ids_are_unique(self):
        parse_domain(self.req, "T-REQ-TRACE-001")
        self.rejected(parse_domain, mutate(self.req, "RQ-002", 0, "RQ-001"), "T-REQ-TRACE-001")
        self.rejected(parse_domain, mutate(self.req, "RQ-001", 1, "wrong"), "T-REQ-TRACE-001")
        self.assertNotEqual(digest(self.req_raw + b"\n"), DIGESTS["requirements"])

    def test_t_req_trace_002_all_trace_references_resolve(self):
        code = "T-REQ-TRACE-002"
        tables = parse_domain(self.req, code)
        universe = baseline_ids(self.plan, self.dag) | {row["id"] for rows in tables.values() for row in rows}
        for rows in tables.values():
            for row in rows:
                require(set(tokens(row["trace"], code, row["id"])) <= universe, code, f"unknown trace {row['id']}")
        for value in ("", "`AC-001`, `Q999`", "`AC-001`, `AC-001`"):
            changed = mutate(self.req, "RQ-001", 6, value)
            self.rejected(lambda text: [require(set(tokens(row["trace"], code, row["id"])) <= universe, code, "unknown") for rows in parse_domain(text, code).values() for row in rows], changed)

    def test_t_req_trace_003_required_runtime_source_matrix(self):
        code = "T-REQ-TRACE-003"
        rows = index(parse_domain(self.req, code)["Runtime/source matrices"], code)
        require(expected("MX", 9) <= set(rows), code, "required matrix IDs")
        require(all(rows[f"MX-{n:03d}"]["matrix"] == "MATRIX-PRIVATE" for n in range(1, 6)), code, "private matrix")
        require(all(rows[f"MX-{n:03d}"]["matrix"] == "MATRIX-PUBLIC-1.0" for n in range(6, 10)), code, "public matrix")
        require(rows["MX-004"]["capability"] == "Watari session receipt source" and rows["MX-005"]["capability"] == "enabled read-only connectors", code, "separate source rows")
        self.rejected(lambda text: require(expected("MX", 9) <= set(index(parse_domain(text, code)["Runtime/source matrices"], code)), code, "missing"), delete(self.req, "MX-009"))

    def test_t_req_trace_004_required_sandbox_contract(self):
        code = "T-REQ-TRACE-004"
        rows = index(parse_domain(self.req, code)["Mandatory sandbox contract"], code)
        require(expected("SB", 7) <= set(rows), code, "required sandbox IDs")
        for item_id, row in rows.items():
            require((row["kind"], row["status"], row["owner"]) == ("sandbox", "frozen", "security"), code, item_id)
            require(bool(row["invariant"] and row["verification"] and row["trace"]), code, item_id)
        self.rejected(lambda text: require(expected("SB", 7) <= set(index(parse_domain(text, code)["Mandatory sandbox contract"], code)), code, "missing"), delete(self.req, "SB-007"))
        self.rejected(parse_domain, mutate(self.req, "SB-003", 3, ""), code)

    def test_t_req_trace_005_required_decisions_and_open_state(self):
        code = "T-REQ-TRACE-005"
        tables = parse_tables(self.dec, DECISION_SPECS, code)
        frozen, opened = index(tables["Frozen decisions"], code), index(tables["Open decisions"], code)
        require(all(re.fullmatch(r"DEC-[0-9]{3}", item) for item in frozen), code, "frozen ID grammar")
        require(all(re.fullmatch(r"DEC-OPEN-[0-9]{3}", item) for item in opened), code, "open ID grammar")
        require(expected("DEC", 6) <= set(frozen) and expected("DEC-OPEN", 6) <= set(opened), code, "decision IDs")
        require(all(row["status"] == "frozen" and all(row.values()) for row in frozen.values()), code, "frozen decisions")
        require(all(row["status"] == "open" and all(row.values()) for row in opened.values()), code, "open decisions")
        self.rejected(lambda text: require(all(row["status"] == "open" for row in parse_tables(text, DECISION_SPECS, code)["Open decisions"]), code, "open"), mutate(self.dec, "DEC-OPEN-001", 2, "frozen"))

    def test_t_req_trace_006_requirement_and_non_goal_acceptance_coverage(self):
        code = "T-REQ-TRACE-006"
        tables = parse_domain(self.req, code)
        acceptances = set(index(tables["Acceptance criteria"], code))
        for title, field in (("User requirements", "acceptance"), ("Non-goals", "acceptance boundary")):
            for row in tables[title]:
                require(bool(row[field]), code, f"empty acceptance {row['id']}")
                require(bool(set(tokens(row["trace"], code, row["id"])) & acceptances), code, f"no AC trace {row['id']}")
        self.rejected(parse_domain, mutate(self.req, "RQ-001", 3, ""), code)
        changed = mutate(self.req, "RQ-002", 6, "`R019`, `I003`, `Q007`")
        self.rejected(lambda text: [require(bool(set(tokens(row["trace"], code, row["id"])) & set(index(parse_domain(text, code)["Acceptance criteria"], code))), code, "no AC") for row in parse_domain(text, code)["User requirements"]], changed)


if __name__ == "__main__":
    unittest.main()
