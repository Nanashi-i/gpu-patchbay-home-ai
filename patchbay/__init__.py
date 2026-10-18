"""GPU Patchbay Home AI: ローカル AI サービス(llama.cpp / Strata / ComfyUI / Forge など)の起動・停止ダッシュボード。

構成(依存は上から下への一方向):
  server.py            起動(初期化はここから)
  api/                 HTTP の入口(ルート表・認証・静的ファイル・全体状態)
  core/                基礎(設定・保存・秘密情報・プリセット・プロセス・起動の流れ)
  apps/                アプリごとの知識(起動コマンド・モデルの置き方・ダウンロードのルール・指標)
  downloads/           ダウンロードの仕組み(キュー・再開・Hugging Face の解析)
  monitor/             PC のモニター(CPU・メモリ・GPU・SSD)
"""
__version__ = "0.1.0"
