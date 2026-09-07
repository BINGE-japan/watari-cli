"""Public claims and automated offline verification must accompany the safety fixes."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_patch_release_version_is_updated():
    metadata = tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert metadata['project']['version'] == '0.1.1'


def test_ci_runs_python_and_actual_pi_hooks_with_read_only_permissions():
    text = (ROOT/'.github/workflows/test.yml').read_text()
    assert 'contents: read' in text
    assert 'pytest' in text and 'pi_runtime.test.mjs' in text
    assert 'macos-latest' in text and 'ubuntu-latest' in text
    assert '@earendil-works/pi-coding-agent@0.84.2' in text


def test_privacy_discloses_original_conversation_ai_provider_and_git_history():
    text = (ROOT/'README.md').read_text()
    assert 'AI提供者' in text and '元の発話' in text and 'Git履歴' in text
    assert '記憶が記憶フォルダの外へ自動で送られることはありません' not in text
    forget = (ROOT/'src/watari_cli/skill/prompts/forget.md').read_text()
    assert '完全削除' in forget and 'Git履歴' in forget
