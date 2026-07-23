"""Read-only proactive briefing assembled from observed memory/service state.

Signals are normalized and ranked deterministically. Delivery history stores only
stable ids/fingerprints below XDG_STATE_HOME; source content remains in its
original service and is never copied into Watari memory by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _fmt_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _signal(*, signal_id: str, kind: str, source: str, urgency: int, title: str,
            reason: str, due_at: str | None = None, pointer: str | None = None) -> dict:
    return {
        "id": signal_id, "kind": kind, "source": source,
        "urgency": max(1, min(3, int(urgency))), "title": title,
        "reason": reason, "due_at": due_at, "pointer": pointer,
    }


def memory_signals(life: dict, now: datetime) -> list[dict]:
    """Create only directly supported deadline/dormancy signals from life state."""
    rows = []
    for thread in life.get("open_threads") or []:
        topic = thread.get("topic")
        if not topic:
            continue
        deadline = _parse_ts(thread.get("deadline"))
        if deadline is not None:
            seconds = (deadline - now).total_seconds()
            if seconds < 0:
                urgency, reason = 3, "期限が過ぎています"
            elif seconds <= 24 * 3600:
                urgency, reason = 3, "期限まで24時間以内です"
            elif seconds <= 7 * 86400:
                urgency, reason = 2, "期限まで7日以内です"
            else:
                urgency = 0
            if urgency:
                rows.append(_signal(
                    signal_id=f"memory:thread:{topic}", kind="deadline", source="memory",
                    urgency=urgency, title=topic, reason=reason,
                    due_at=_fmt_ts(deadline), pointer=None,
                ))
                continue
        if thread.get("dormant"):
            rows.append(_signal(
                signal_id=f"memory:thread:{topic}", kind="dormant", source="memory",
                urgency=1, title=topic,
                reason=f"{int(thread.get('dormant_days') or 0)}日間、進捗が記録されていません",
                pointer=None,
            ))
    return rank_signals(rows)


def collect(life: dict, now: datetime) -> dict:
    """Collect memory plus declared/connected service signals; one source failure is isolated."""
    from watari_cli import config, connectors

    signals = memory_signals(life, now)
    errors = []
    names = []
    for declaration in config.load_connectors():
        name = declaration.get("name")
        if name and name not in names:
            names.append(name)
    for name in names:
        service = connectors.get_service(name)
        if service is None or service.brief is None or not connectors.is_connected(name):
            continue
        try:
            signals.extend(connectors.brief(name, now))
        except Exception as error:
            errors.append({"source": name, "error": str(error)})
    return {"generated": _fmt_ts(now), "signals": rank_signals(signals), "errors": errors}


def rank_signals(signals: list[dict]) -> list[dict]:
    far_future = "9999-12-31T23:59:59Z"
    return sorted(signals, key=lambda row: (
        -int(row.get("urgency") or 0), row.get("due_at") or far_future,
        row.get("source") or "", row.get("id") or "",
    ))


def delivery_state_path() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "watari", "briefing.json")


def _fingerprint(signal: dict) -> str:
    stable = {key: signal.get(key) for key in ("id", "kind", "urgency", "due_at", "reason")}
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_delivery(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {"shown": {}}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"shown": {}}


def select_for_delivery(signals: list[dict], now: datetime, *, limit: int | None,
                        path: str | None = None, mark: bool = False,
                        suppress_recent: bool = True) -> list[dict]:
    """Select visible rows first, then mark only automatic deliveries as shown."""
    selected = (filter_delivery(signals, now, path, mark=False)
                if suppress_recent else rank_signals(signals))
    if limit is not None:
        selected = selected[:limit]
    if mark and selected:
        filter_delivery(selected, now, path, mark=True)
    return selected


def filter_delivery(signals: list[dict], now: datetime, path: str | None = None,
                    *, mark: bool = False, cooldown: timedelta = timedelta(hours=24)) -> list[dict]:
    """Suppress unchanged signals shown within cooldown; optionally mark returned rows."""
    path = path or delivery_state_path()
    state = _load_delivery(path)
    shown = state.get("shown") if isinstance(state.get("shown"), dict) else {}
    output = []
    for signal in rank_signals(signals):
        fingerprint = _fingerprint(signal)
        previous = shown.get(signal["id"]) if isinstance(shown.get(signal["id"]), dict) else {}
        previous_at = _parse_ts(previous.get("shown_at"))
        recent = previous_at is not None and now - previous_at < cooldown
        if previous.get("fingerprint") == fingerprint and recent:
            continue
        output.append(signal)
        if mark:
            shown[signal["id"]] = {"fingerprint": fingerprint, "shown_at": _fmt_ts(now)}
    if mark:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump({"shown": shown}, stream, ensure_ascii=False, indent=1)
            stream.write("\n")
        os.replace(tmp, path)
    return output
