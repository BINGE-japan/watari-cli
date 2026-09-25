"""Fixed operations for the bundled Pi tools; not an MCP or a security broker.

The Pi extension owns the observed batch in process memory. This local Python
interface reuses ingestion; it does not authenticate hostile local callers.
Only existing configured conversation reads and memory Git sync use the network.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
from itertools import groupby

from watari_cli import git_sync, host, storage
from watari_cli.engine import audit, extract, ingest, watari_lib as wl

MAX_BYTES = 32_000
MAX_REQUEST_BYTES = 256_000
ROW_FIELDS = {'kind', 'domain', 'topic', 'summary', 'mastery', 'heat', 'note',
              'related', 'freshness', 'profile', 'status', 'deadline', 'tags'}
REF_FIELDS = ('uuid', 'session', 'cwd', 'machine', 'computer', 'runtime')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _error(message):
    raise ValueError(message)


def _message(raw):
    if not isinstance(raw, dict) or raw.get('role') not in ('user', 'assistant'):
        _error('発話の形式を確認できません。')
    if not isinstance(raw.get('uuid'), str) or not raw['uuid']:
        _error('発話の識別情報がありません。')
    if not isinstance(raw.get('ts'), str) or wl.parse_ts(raw['ts']).tzinfo is None:
        _error('発話の日時にタイムゾーンが必要です。')
    out = {k: raw[k] for k in (*REF_FIELDS, 'ts', 'role', 'store') if raw.get(k) is not None}
    text = raw.get('text', '')
    if isinstance(text, list):
        out['text'] = '\n'.join(b['text'] for b in text
                               if isinstance(b, dict) and b.get('type') == 'text' and isinstance(b.get('text'), str))
        if any(isinstance(b, dict) and b.get('type') == 'image' for b in text):
            out['omitted_images'] = True
    elif isinstance(text, str):
        out['text'] = text
    else:
        _error('発話本文の形式に対応していません。')
    return out


def make_batch(snapshot, *, max_messages=40, max_bytes=MAX_BYTES):
    """Bound chronological batches without splitting an equal-instant group."""
    stores = copy.deepcopy(snapshot['stores'])
    if not isinstance(stores, dict):
        _error('取得範囲の形式を確認できません。')
    for key, info in stores.items():
        if key != 'pi' and not (key.startswith('cloud_') and len(key) > 6):
            _error('未対応の会話の取得元です。')
        if not isinstance(info, dict) or type(info.get('readable')) is not bool:
            _error('取得の成否を確認できません。')
    messages = sorted((_message(m) for m in snapshot['messages']),
                      key=lambda m: (wl.parse_ts(m['ts']), m['uuid']))
    if any(m.get('store') not in stores for m in messages):
        _error('発話と取得範囲が一致しません。')
    result = {'version': 1, 'mode': 'conversations', 'stores': stores, 'messages': []}
    for _, group in groupby(messages, key=lambda m: wl.parse_ts(m['ts'])):
        group = list(group)
        if len(result['messages']) >= max_messages:
            break
        trial = {**result, 'messages': result['messages'] + group}
        # Reserve room for the tool's batch identifier and result metadata.
        if len(encoded(trial).encode()) > max_bytes - 1024:
            if not result['messages']:
                _error('同時刻の発話が一度に扱える量を超えています。従来の整理手順で内容を確認してください。')
            break
        result = trial
    for key, info in stores.items():
        selected = [m for m in result['messages'] if m['store'] == key]
        available = sum(m['store'] == key for m in messages)
        info['truncated'] = bool(info.get('truncated')) or len(selected) < available
        info['count'] = len(selected)
        info['max_ts'] = selected[-1]['ts'] if selected else None
    if len(encoded(result).encode()) > max_bytes:
        _error('取得範囲の情報が上限を超えています。')
    return result


def current_batch(message):
    value = _message(message)
    if value['role'] != 'user':
        _error('本人の発話だけを根拠にできます。')
    result = {'version': 1, 'mode': 'current', 'stores': {}, 'messages': [value]}
    if len(encoded(result).encode()) > MAX_BYTES:
        _error('発話が一度に扱える量を超えています。')
    return result


def prepare():
    # Keep the existing pre-read synchronization and recovery semantics.
    from watari_cli.cli import _ensure_state
    with storage.file_lock(wl.MEM):
        storage.recover(wl.MEM)
        git_sync.sync_before_read(wl.MEM)
        _ensure_state()
        return make_batch(extract.run())


def _rows(batch, decisions):
    if (not isinstance(batch, dict) or type(batch.get('version')) is not int
            or batch['version'] != 1 or batch.get('mode') not in ('current', 'conversations')):
        _error('対応していない処理形式です。材料を取得し直してください。')
    evidence = {}
    for m in batch['messages']:
        m = _message(m)
        if m['role'] == 'user':
            if m['uuid'] in evidence and evidence[m['uuid']] != m:
                _error('同じ識別情報の発話が一致しません。')
            evidence[m['uuid']] = m
    if not isinstance(decisions, list) or len(decisions) != len(evidence):
        _error('各本人発話について、残す内容または空のrowsを一つずつ指定してください。')
    rows, seen = [], set()
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) != {'uuid', 'rows'}:
            _error('選別結果の形式が不正です。')
        uuid = decision['uuid']
        if not isinstance(uuid, str) or uuid not in evidence or uuid in seen:
            _error('根拠が未取得・重複・本人以外のいずれかです。')
        seen.add(uuid)
        if not isinstance(decision['rows'], list) or len(decision['rows']) > 4:
            _error('一つの発話から残せる内容は種類ごとに一件です。')
        kinds = set()
        for value in decision['rows']:
            if not isinstance(value, dict) or not set(value).issubset(ROW_FIELDS):
                _error('日時・出所・参照情報は自動設定します。不明な項目は指定できません。')
            kind = value.get('kind')
            if not isinstance(kind, str) or kind in kinds:
                _error('一つの発話に同じ種類の記憶を複数指定できません。')
            kinds.add(kind)
            m = evidence[uuid]
            rows.append({**value, 'ts': m['ts'], 'source': 'watari',
                         'refs': {k: m[k] for k in REF_FIELDS if k in m}})
    return rows


def _advances(batch):
    args = {'advance_cloud': [], 'advance_ext': []}
    if batch['mode'] == 'current':
        if batch['stores']:
            _error('現在の発話では読み取り済み範囲を変更できません。')
        return args
    cursors = host.load_cursors(wl.MEM)
    for key, info in batch['stores'].items():
        if type(info.get('readable')) is not bool:
            _error('取得の成否を確認できません。')
        if not info['readable'] or not info.get('max_ts'):
            continue
        if key != 'pi' and not (key.startswith('cloud_') and len(key) > 6):
            _error('未対応の取得元です。')
        target = 'transcripts_pi' if key == 'pi' else key
        current = cursors.get(target)
        # An identical completed batch is safe to replay through existing dedup.
        if current not in (info.get('cursor'), info['max_ts']):
            _error('別の整理で読み取り範囲が変わりました。材料を取得し直してください。')
        if key == 'pi':
            args['advance_pi'] = info['max_ts']
        else:
            args['advance_cloud'].append(f"{key[6:]}={info['max_ts']}")
    return args


def save_batch(batch, decisions, *, allow_new_domain=False):
    if type(allow_new_domain) is not bool:
        _error('学習分野の追加指定が不正です。')
    rows = _rows(batch, decisions)
    from watari_cli.cli import _ensure_state
    with storage.file_lock(wl.MEM):
        storage.recover(wl.MEM)
        advances = _advances(batch)
        summary = ingest.apply(rows, allow_new_domain=allow_new_domain, **advances)
        warnings = io.StringIO()
        try:
            with contextlib.redirect_stderr(warnings):
                git_sync.sync_after_write(wl.MEM)
        except Exception:
            warnings.write('保存済みですが同期結果を確認できません。')
        # A pull during sync can change the local records; verify the final view.
        try:
            _ensure_state()
            problems, infos, _ = audit.audit_report()
        except Exception:
            problems, infos = ['保存済みですが検査を完了できません。記憶の検査を再実行してください。'], []
    return {'saved': True, 'checked': not problems, 'summary': summary,
            'problems': [p[:500] for p in problems[:20]], 'problem_count': len(problems), 'info_count': len(infos),
            'sync': 'warning' if warnings.getvalue() else 'attempted_or_local',
            'warnings': warnings.getvalue().strip()[:4000],
            'incomplete_sources': [k for k, v in batch['stores'].items()
                                   if not v['readable'] or v.get('truncated')]}


def get_memory(kind, topic, *, domain=None, offset=0, limit=5):
    if kind not in wl.KIND_TO_GENRE or not isinstance(topic, str) or not topic or len(topic) > 2048:
        _error('記憶の種類と正確な話題名を指定してください。')
    if (kind == 'study' and (not isinstance(domain, str) or not domain)) or (kind != 'study' and domain is not None):
        _error('学習内容だけに分野を指定してください。')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20:
        _error('取得範囲が不正です。')
    with storage.file_lock(wl.MEM):
        storage.recover(wl.MEM)
        aliases = wl.load_aliases() if kind == 'study' else {}
        rows = [r for r in wl.load_log(wl.KIND_TO_GENRE[kind])
                if r.get('kind') == kind
                and ((r.get('profile') or {}).get('key') or r.get('topic')) == topic
                and (kind != 'study' or aliases.get(r.get('domain'), r.get('domain')) == aliases.get(domain, domain))]
    rows.sort(key=lambda r: (wl.parse_ts(r['ts']), r.get('refs', {}).get('uuid', '')), reverse=True)
    selected = [{k: v for k, v in r.items() if not k.startswith('_')}
                for r in rows[offset:offset + limit]]
    result = {'rows': selected, 'total': len(rows),
              'next_offset': offset + len(selected) if offset + len(selected) < len(rows) else None}
    while selected and len(encoded(result).encode()) > MAX_BYTES:
        selected.pop()
        result['next_offset'] = offset + len(selected)
    if not selected and offset < len(rows):
        _error('一件の記録が取得上限を超えています。従来のファイル読取で範囲を指定してください。')
    return result


def main():
    """Bounded stdin/stdout transport for the bundled extension, no shell syntax."""
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            _error('入力が上限を超えています。')
        request = json.loads(raw)
        if not isinstance(request, dict) or type(request.get('version')) is not int or request.pop('version') != 1:
            _error('対応していない要求形式です。')
        action = request.pop('action', None)
        if action == 'prepare' and not request:
            result = prepare()
        elif action == 'current' and set(request) == {'message'}:
            result = current_batch(request['message'])
        elif action == 'save' and set(request).issubset({'batch', 'decisions', 'allow_new_domain'}):
            result = save_batch(**request)
        elif action == 'get' and set(request).issubset({'kind', 'topic', 'domain', 'offset', 'limit'}):
            result = get_memory(**request)
        else:
            _error('未対応の操作または入力項目です。')
        print(encoded(result))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
        print(encoded({'error': str(error)[:8000]}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
