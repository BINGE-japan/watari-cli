"""Linear の認証情報をAIへ渡さず、許可した操作だけを実行する境界。

任意の GraphQL は受け付けない。action ごとに入力項目・長さ・型を検証し、固定した mutation へ
変換する。Pi 側では実行直前に本人確認を必須にするため、この層は決定論的な検証とAPI実行だけを担う。
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any

from watari_cli import config, linear
from watari_cli.connectors import ConnectorError

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ACTIONS = {"issue_create", "issue_update", "comment_create"}


def configured_api_key() -> str:
    auth = (config.load_config().get("connectors_auth") or {}).get("linear") or {}
    key = auth.get("api_key")
    if not isinstance(key, str) or not key:
        raise ConnectorError("linear: 接続されていません。watari connect linear を実行してください")
    return key


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} はオブジェクトで指定してください")
    return value


def _unknown(data: dict, allowed: set[str]) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ValueError(f"許可されていない項目です: {', '.join(extra)}")


def _text(data: dict, key: str, *, required: bool = False, maximum: int = 20_000,
          nullable: bool = False) -> str | None:
    if key not in data:
        if required:
            raise ValueError(f"{key} は必須です")
        return None
    value = data[key]
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} は文字列で指定してください")
    value = value.strip() if key in {"title", "name"} else value
    if required and not value:
        raise ValueError(f"{key} は空にできません")
    if len(value) > maximum:
        raise ValueError(f"{key} が長すぎます（最大 {maximum} 文字）")
    return value


def _identifier(data: dict, key: str, *, required: bool = False,
                nullable: bool = False) -> str | None:
    if key not in data:
        if required:
            raise ValueError(f"{key} は必須です")
        return None
    value = data[key]
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"{key} はLinearの識別子で指定してください")
    return value


def _date_value(data: dict, key: str, *, nullable: bool = True) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} は YYYY-MM-DD 形式で指定してください")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{key} は YYYY-MM-DD 形式で指定してください") from error
    return value


def _priority(data: dict) -> int | None:
    if "priority" not in data:
        return None
    value = data["priority"]
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 4:
        raise ValueError("priority は 0〜4 の整数で指定してください")
    return value


def _id_list(data: dict, key: str, *, required: bool = False) -> list[str] | None:
    if key not in data:
        if required:
            raise ValueError(f"{key} は必須です")
        return None
    value = data[key]
    if not isinstance(value, list) or (required and not value):
        raise ValueError(f"{key} はLinear識別子の配列で指定してください")
    if len(value) > 100 or any(not isinstance(item, str) or not _ID_RE.fullmatch(item)
                               for item in value):
        raise ValueError(f"{key} は最大100件のLinear識別子で指定してください")
    return list(dict.fromkeys(value))


def _copy_present(data: dict, output: dict, key: str, reader) -> None:
    if key in data:
        output[key] = reader(data, key)


def _issue_fields(data: dict, *, create: bool) -> dict:
    allowed = {
        "title", "description", "teamId", "assigneeId", "stateId", "dueDate",
        "priority", "projectId", "labelIds", "parentId",
    }
    _unknown(data, allowed)
    output: dict[str, Any] = {}
    if create:
        output["title"] = _text(data, "title", required=True, maximum=500)
        output["teamId"] = _identifier(data, "teamId", required=True)
    else:
        _copy_present(data, output, "title", lambda d, k: _text(d, k, maximum=500))
        _copy_present(data, output, "teamId", lambda d, k: _identifier(d, k))
    _copy_present(data, output, "description", lambda d, k: _text(d, k, maximum=20_000,
                                                                     nullable=True))
    for key in ("assigneeId", "stateId", "projectId", "parentId"):
        _copy_present(data, output, key, lambda d, k: _identifier(d, k, nullable=True))
    _copy_present(data, output, "dueDate", lambda d, k: _date_value(d, k))
    if "priority" in data:
        output["priority"] = _priority(data)
    if "labelIds" in data:
        output["labelIds"] = _id_list(data, "labelIds")
    if not output:
        raise ValueError("変更する項目を1つ以上指定してください")
    return output


def normalize_request(request: dict) -> tuple[str, dict, dict]:
    request = _mapping(request, "request")
    _unknown(request, {"action", "input"})
    action = request.get("action")
    if action not in _ACTIONS:
        raise ValueError(f"許可されていないLinear操作です: {action!r}")
    source = _mapping(request.get("input"), "input")

    if action == "issue_create":
        return action, {}, _issue_fields(source, create=True)
    if action == "issue_update":
        _unknown(source, {"issueId", "title", "description", "teamId", "assigneeId",
                          "stateId", "dueDate", "priority", "projectId", "labelIds",
                          "parentId"})
        target = {"id": _identifier(source, "issueId", required=True)}
        fields = dict(source)
        fields.pop("issueId")
        return action, target, _issue_fields(fields, create=False)
    if action == "comment_create":
        _unknown(source, {"issueId", "body"})
        issue = _identifier(source, "issueId", required=True)
        body = _text(source, "body", required=True, maximum=10_000)
        return action, {}, {"issueId": issue, "body": body}
    raise AssertionError(action)


_QUERIES = {
    "issue_create": """
      mutation WatariIssueCreate($input: IssueCreateInput!) {
        issueCreate(input: $input) { success issue { id identifier title url updatedAt } }
      }
    """,
    "issue_update": """
      mutation WatariIssueUpdate($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) { success issue { id identifier title url updatedAt } }
      }
    """,
    "comment_create": """
      mutation WatariCommentCreate($input: CommentCreateInput!) {
        commentCreate(input: $input) { success comment { id url createdAt } }
      }
    """,
}


def perform(api_key: str, request: dict) -> dict:
    action, target, fields = normalize_request(request)
    variables = {**target, "input": fields}
    data = linear._post(api_key, _QUERIES[action], variables)
    return {"action": action, "result": data}


_CATALOG_QUERIES = {
    "teams": "query WatariTeams { teams(first: 100) { nodes { id key name } } }",
    "users": "query WatariUsers { users(first: 250) { nodes { id name email active } } }",
    "projects": """
      query WatariProjects { projects(first: 250) { nodes { id name slugId } } }
    """,
    "states": """
      query WatariStates {
        workflowStates(first: 250) { nodes { id name type team { id key name } } }
      }
    """,
    "labels": """
      query WatariLabels {
        issueLabels(first: 250) { nodes { id name color team { id key name } } }
      }
    """,
}


def catalog(api_key: str) -> dict:
    """作成・更新時に必要なIDだけを、固定queryで取得する。"""
    output: dict[str, list] = {}
    for name, query in _CATALOG_QUERIES.items():
        data = linear._post(api_key, query)
        root = next(iter(data.values()), {})
        output[name] = root.get("nodes") or [] if isinstance(root, dict) else []
    return output
