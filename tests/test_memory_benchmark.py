"""Regression contracts for the offline Japanese memory baseline, not AI accuracy."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'tests' / 'memory_benchmark.py'


@pytest.fixture(scope='module')
def report(tmp_path_factory):
    # An inherited live-looking home must be ignored, not even read or amended.
    sentinel = tmp_path_factory.mktemp('untouched-memory')
    (sentinel / 'sentinel').write_text('unchanged')
    result = subprocess.run(
        [sys.executable, str(RUNNER), '--json'], cwd=ROOT,
        env={**os.environ, 'WATARI_HOME': str(sentinel)},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert sorted(p.name for p in sentinel.iterdir()) == ['sentinel']
    assert (sentinel / 'sentinel').read_text() == 'unchanged'
    return json.loads(result.stdout)


def test_japanese_memory_baseline_traces_corrections_and_real_context(report):
    assert report['version'] == 1
    assert report['fixture'] == 'memory-ja-v1'
    assert report['checks'] and all(c['passed'] for c in report['checks'])
    trace = next(q for q in report['queries'] if q['id'] == 'corrected-destination')
    assert trace['search'][0]['topic'] == 'delivery_destination'
    assert trace['evidence'][0]['refs']['uuid'] == 'u02'
    assert trace['evidence'][1]['refs']['uuid'] == 'u01'
    assert trace['retrieved_evidence']['fact:delivery_destination'][0]['refs']['uuid'] == 'u02'
    source = next(m for m in report['source_messages'] if m['uuid'] == 'u02')
    assert source['role'] == 'user' and '訂正' in source['text']
    assert '霧町' in trace['contexts']['balanced']['matches'][0]['note']
    assert report['not_measured'] == ['model_selection', 'answer_accuracy', 'synchronization', 'live_memory']


def test_baseline_reports_misses_instead_of_hiding_or_failing_them(report):
    queries = [q for q in report['queries'] if q['expected']]
    for mode in ('search', 'fast', 'balanced', 'butler'):
        measured = report['metrics'][mode]
        assert measured['queries'] == len(queries)
        scores = [q['scores'][mode] for q in queries]
        assert measured['recall'] == pytest.approx(sum(s['recall'] for s in scores) / len(scores))
        if mode == 'search':
            assert measured['mrr'] == pytest.approx(sum(s['rr'] for s in scores) / len(scores))
        else:
            assert 'mrr' not in measured  # Automatic context is not a ranked result list.
    paraphrases = [q for q in queries if q['group'] == 'paraphrase']
    assert len(paraphrases) == 2
    assert report['search_by_group']['paraphrase']['recall'] == pytest.approx(
        sum(q['scores']['search']['recall'] for q in paraphrases) / len(paraphrases)
    )
    unknown = next(q for q in report['queries'] if q['id'] == 'unknown-information')
    assert unknown['expected'] == []
    assert unknown['search'] == []
    # A closed task shares words with another fact: unrelated hits are measured,
    # not assumed to be zero. This gate tests honest reporting, not retrieval quality.
    negatives = [q for q in report['queries'] if not q['expected']]
    assert report['negative_queries'] == {
        'queries': len(negatives),
        'search_false_positive_queries': sum(bool(q['search']) for q in negatives),
    }


def test_baseline_preserves_source_roles_and_closed_history(report):
    assert all(row['refs']['uuid'].startswith('u') for row in report['records'])
    assert not any(row['refs']['uuid'] == 'u06' for row in report['records'])
    closed = report['histories']['proofreading']
    assert [row['status'] for row in closed] == ['closed', 'open']
    assert [row['refs']['uuid'] for row in closed] == ['u04', 'u03']
    assert {c['id'] for c in report['checks']} >= {
        'save-checked', 'correction-current', 'closed-task-history',
        'assistant-source-rejected', 'replay-deduplicated',
        'regeneration-deterministic', 'context-budgets', 'approval-preserved',
    }


def test_context_titles_without_details_do_not_count_as_supplied_memory():
    from tests.memory_benchmark import _context_keys
    assert _context_keys({'profile': {}, 'matches': [{'kind': 'fact', 'topic': 'title-only'}],
                          'attention': [], 'catalog': {'facts': ['catalog-only']}}) == set()
    assert _context_keys({'full_context': True, 'profile': {},
                          'life': {'facts': {'empty-fact': {'note': ''}}}}) == set()


def test_ranking_metrics_penalize_missing_and_low_rank_results():
    from tests.memory_benchmark import ranking_metrics
    assert ranking_metrics(['a', 'b'], ['x', 'a', 'a', 'y', 'b'], 3) == {'recall': 0.5, 'rr': 0.5}
    assert ranking_metrics(['a'], [], 6) == {'recall': 0.0, 'rr': 0.0}
    assert ranking_metrics([], ['a'], 6) is None


def test_baseline_is_reproducible(report):
    result = subprocess.run([sys.executable, str(RUNNER), '--json'], cwd=ROOT,
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == report


def test_baseline_refuses_an_already_imported_memory_runtime(monkeypatch):
    from tests.memory_benchmark import run_benchmark
    monkeypatch.setitem(sys.modules, 'watari_cli.engine.watari_lib', object())
    with pytest.raises(RuntimeError, match='fresh process'):
        run_benchmark()


def test_unknown_fixture_version_fails_closed():
    from tests.memory_benchmark import validate_fixture
    for version in (True, 2, None):
        with pytest.raises(ValueError, match='version'):
            validate_fixture({'version': version})
