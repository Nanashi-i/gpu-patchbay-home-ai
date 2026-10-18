"""ダウンロードの保存先の安全確認。"""
from ..core.config import exts, models_dir
from ..core.errors import HubError


def safe_dest(service, directory, name):
    """directory/name を返す。service の models_dir の外・許可外の拡張子・既存ファイルは拒否。"""
    root = models_dir(service).resolve()
    dest = (directory / name).resolve()
    if root not in dest.parents:
        raise HubError("保存先がこのサービスのモデルフォルダの外です")
    if dest.suffix.lower() not in exts(service):
        raise HubError(f"このサービスでは {', '.join(sorted(exts(service)))} のみ保存できます: {dest.name}")
    if dest.exists() or dest.is_symlink():
        raise HubError(f"既に存在します: {dest.relative_to(root)}")
    return dest
