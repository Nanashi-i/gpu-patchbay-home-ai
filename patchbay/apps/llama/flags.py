"""llama-server のチェックボックス用フラグ(値を取らないものだけ)。
machine.json の llama サービスに "flags" を書けば、一覧ごと差し替えられる。
short は、画面に出す一言、note は、マウスオーバーの詳しい説明。
"""

# llama-server のチェックボックス用フラグ(値を取らないものだけ)。machine.json の llama サービスに "flags" を書けば差し替え可能。
LLAMA_FLAGS = [
    {"flag": "--jinja", "short": "Qwen / Gemma 系・ツール呼び出し用", "group": "チャットテンプレート", "note": "Qwen / Gemma 系のチャットテンプレート・ツール呼び出し用。新しい llama.cpp は既定で有効(古い版では必須)"},
    {"flag": "--no-context-shift", "short": "長い会話で文脈が壊れるのを防ぐ", "group": "チャットテンプレート", "note": "コンテキストが溢れても古い部分を自動で捨てない(長い会話で文脈が壊れるのを防ぐ。溢れると停止します)"},
    {"flag": "--swa-full", "short": "Gemma 系のキャッシュ再利用・VRAM 増", "group": "メモリ / VRAM", "note": "SWA(スライディングウィンドウ)キャッシュをフルサイズにする。Gemma 系などでキャッシュ再利用が効く(VRAM増)"},
    {"flag": "--cpu-moe", "short": "MoE を CPU へ・VRAM 節約", "aliases": ["-cmoe"], "group": "メモリ / VRAM", "note": "MoE の重みをすべて CPU に置く(VRAM 節約。遅くなる)"},
    {"flag": "--no-op-offload", "short": "VRAM 不足・不安定なとき", "group": "メモリ / VRAM", "note": "ホスト側テンソル演算の GPU オフロードを止める(VRAM が足りないとき・不安定なとき)"},
    {"flag": "--no-mmproj", "short": "画像入力を使わない・VRAM 節約", "group": "マルチモーダル", "note": "画像入力用の mmproj を自動で読み込まない(VRAM 節約。テキスト専用で使うとき)"},
    {"flag": "--no-warmup", "short": "起動が少し速くなる", "group": "動作", "note": "起動時のウォームアップ実行を省く(起動が少し速くなる)"},
    {"flag": "--no-cache-prompt", "short": "毎回最初から処理", "group": "動作", "note": "プロンプトキャッシュを使わない(毎回、最初から処理。再現性重視)"},
    {"flag": "--metrics", "short": "メトリクスを公開", "group": "動作", "note": "Prometheus 形式のメトリクスを公開する"},
    {"flag": "--check-tensors", "short": "読み込み時に検証・遅くなる", "group": "動作", "note": "モデルのテンソルを読み込み時に検証する(起動が遅くなる。破損の疑いがあるとき)"},
]


def llama_flags(svc):
    return svc.get("flags") or LLAMA_FLAGS
