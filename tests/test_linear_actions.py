"""Linearの固定操作境界: 任意GraphQLを許さず、従来必要だった操作だけを通す。"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watari_cli import linear_actions
from watari_cli.cli import _build_parser, _load_bounded_json


class LinearActionValidationTest(unittest.TestCase):
    def test_issue_create_uses_fixed_mutation_and_validated_fields(self):
        request = {
            "action": "issue_create",
            "input": {
                "title": "Synthetic task",
                "teamId": "team_123",
                "description": "Synthetic description",
                "priority": 2,
                "dueDate": "2026-08-10",
                "labelIds": ["label_1", "label_1", "label_2"],
            },
        }
        with patch.object(linear_actions.linear, "_post", return_value={"issueCreate": {"success": True}}) as post:
            result = linear_actions.perform("synthetic-key", request)
        query = post.call_args.args[1]
        variables = post.call_args.args[2]
        self.assertIn("mutation WatariIssueCreate", query)
        self.assertNotIn("query", request)
        self.assertEqual(variables["input"]["title"], "Synthetic task")
        self.assertEqual(variables["input"]["labelIds"], ["label_1", "label_2"])
        self.assertEqual(result["action"], "issue_create")

    def test_issue_update_requires_a_change_and_rejects_unknown_fields(self):
        with self.assertRaisesRegex(ValueError, "変更する項目"):
            linear_actions.normalize_request({
                "action": "issue_update", "input": {"issueId": "GEN-123"},
            })
        with self.assertRaisesRegex(ValueError, "許可されていない項目"):
            linear_actions.normalize_request({
                "action": "issue_update",
                "input": {"issueId": "GEN-123", "admin": True},
            })

    def test_comment_is_limited_to_issue_comments(self):
        with self.assertRaisesRegex(ValueError, "issueId は必須"):
            linear_actions.normalize_request({
                "action": "comment_create", "input": {"body": "hello"},
            })
        with self.assertRaisesRegex(ValueError, "許可されていない項目"):
            linear_actions.normalize_request({
                "action": "comment_create",
                "input": {"projectId": "project_1", "body": "hello"},
            })
        action, target, fields = linear_actions.normalize_request({
            "action": "comment_create",
            "input": {"issueId": "GEN-1", "body": "Synthetic comment"},
        })
        self.assertEqual(action, "comment_create")
        self.assertEqual(target, {})
        self.assertEqual(fields["issueId"], "GEN-1")

    def test_project_workspace_and_attachment_actions_are_rejected(self):
        for action in ("project_create", "project_update", "label_create",
                       "attachment_create", "relation_create"):
            with self.subTest(action=action), self.assertRaisesRegex(
                    ValueError, "許可されていないLinear操作"):
                linear_actions.normalize_request({"action": action, "input": {}})

    def test_arbitrary_action_and_graphql_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "許可されていないLinear操作"):
            linear_actions.normalize_request({
                "action": "graphql", "input": {"query": "mutation { workspaceDelete }"},
            })
        with self.assertRaisesRegex(ValueError, "許可されていない項目"):
            linear_actions.normalize_request({
                "action": "issue_update",
                "input": {"issueId": "GEN-1", "query": "mutation"},
            })

    def test_priority_and_dates_are_validated(self):
        bad_requests = [
            {"action": "issue_create", "input": {"title": "x", "teamId": "t", "priority": 9}},
            {"action": "issue_create", "input": {"title": "x", "teamId": "t", "dueDate": "2026-02-31"}},
        ]
        for request in bad_requests:
            with self.subTest(request=request), self.assertRaises(ValueError):
                linear_actions.normalize_request(request)


class LinearRequestFileTest(unittest.TestCase):
    def test_internal_cli_is_parsed_and_request_reader_rejects_symlinks_and_large_files(self):
        args = _build_parser().parse_args(["linear", "catalog"])
        self.assertEqual(args.func.__name__, "cmd_linear_catalog")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "request.json"
            target.write_text('{"action":"comment_create","input":{}}')
            link = root / "link.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaises(OSError):
                _load_bounded_json(str(link))
            large = root / "large.json"
            large.write_bytes(b"x" * 65_537)
            with self.assertRaisesRegex(ValueError, "大きすぎ"):
                _load_bounded_json(str(large))


class LinearCatalogTest(unittest.TestCase):
    def test_catalog_uses_only_named_fixed_queries(self):
        def fake_post(_key, query, variables=None):
            self.assertIsNone(variables)
            self.assertIn("query Watari", query)
            root = {
                "WatariTeams": "teams",
                "WatariUsers": "users",
                "WatariProjects": "projects",
                "WatariStates": "workflowStates",
                "WatariLabels": "issueLabels",
            }
            operation = next(name for name in root if name in query)
            return {root[operation]: {"nodes": [{"id": operation}]}}

        with patch.object(linear_actions.linear, "_post", side_effect=fake_post) as post:
            result = linear_actions.catalog("synthetic-key")
        self.assertEqual(set(result), {"teams", "users", "projects", "states", "labels"})
        self.assertEqual(post.call_count, 5)


if __name__ == "__main__":
    unittest.main()
