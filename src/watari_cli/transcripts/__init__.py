"""他の AI CLI（Claude Code / Codex 等）の会話ログを夢のソースにする connector 群。

watari-cli 組み込みの transcript は Pi 一本（`transcripts_pi`。engine/watari_lib.py）だが、
watari chat の外で別の AI CLI とも会話しているユーザーのため、それらのログも
`watari connect <name>`（scope="local"）経由で夢のソースに登録できる。

認証は不要（ローカルファイルを読むだけ）なので、auth_kind="local"（connectors.py 参照）を使う:
verify() がログ置き場を自動検出→見つからなければパス入力を促す→検証して config に保存、まで
一括で行う（freee の auth_kind="oauth" 一括パターンと同じ形）。scope="local" なので、各マシンが
自分のログを自分で夢に見る（cloud スコープの「担当1台」ルールは適用されない）。

各サービス固有の検出・パース・（Codex の）リプレイ除去はこのパッケージ内の各モジュールに閉じ、
connectors.py / cli/__init__.py にサービス名の分岐は増やさない。
"""
