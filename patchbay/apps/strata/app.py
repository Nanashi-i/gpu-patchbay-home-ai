"""Strata: 起動スクリプト(run-*.sh)と、環境変数 STRATA_API_KEY で動く。モデルは、フォルダ直下の項目として一覧する。

起動コマンドの組み立て(スクリプト・API キー)は、ScriptApp の、設定に従う動きで足りる。ここには、Strata 固有の既定だけを置く。
"""
from ..base import ScriptApp


class StrataApp(ScriptApp):
    app_id = "strata"
    # models(): App の既定(scan_entries)= フォルダ直下の項目 + 設定ファイル(strata-*.json)からの参照
