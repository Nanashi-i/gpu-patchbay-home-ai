"""Hugging Face / 直リンクのための HTTP の道具(認証ヘッダ・リダイレクト・URL の解析)。"""
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

from ..core.config import CFG
from ..core.errors import HubError
from ..core.secrets import get_token

# トークンを付けてよい相手(ドメイン名そのもの、または、その下のサブドメインだけ。"evilhf.co" のような似た名前は対象外)
TOKEN_HOSTS = {"hf": ("huggingface.co", "hf.co"), "civitai": ("civitai.com",)}


def _origin(url):
    u = urllib.parse.urlsplit(url)
    return (u.scheme, (u.hostname or "").lower(), u.port or {"http": 80, "https": 443}.get(u.scheme))


def _under(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def check_public_host(url):
    """内部のアドレス(自分自身・LAN・リンクローカルなど)への接続を断る(SSRF 対策)。
    machine.json の allow_private_downloads が true のときだけ、許可する(NAS など、LAN 内から取りたい人向け)。"""
    if CFG.get("allow_private_downloads") or urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return   # (http / https 以外は、そもそも、engine が受け付けない)
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        raise HubError("URL にホスト名がありません")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return   # 名前が引けないなら、どのみち接続できない(取得の段階でエラーになる)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise HubError(f"内部のアドレス({ip})へは接続しません(machine.json の allow_private_downloads で許可できます)")


class _Redir(urllib.request.HTTPRedirectHandler):
    """リダイレクトのたびに、行き先を確認する: 内部アドレスは断る・https から http へは行かない・
    ホストが変わったら、トークンを外す。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new_o = _origin(req.full_url), _origin(newurl)
        if old[0] == "https" and new_o[0] != "https":
            raise urllib.error.HTTPError(req.full_url, code, "https から http へのリダイレクトは拒否しました", headers, fp)
        check_public_host(newurl)
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new and old != new_o:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


OPENER = urllib.request.build_opener(_Redir)


def auth_headers(url):
    h = {"User-Agent": "gpu-patchbay-home-ai"}
    scheme, host, _ = _origin(url)
    if scheme != "https":   # トークンは、暗号化された通信にだけ付ける
        return h
    for kind, domains in TOKEN_HOSTS.items():
        if _under(host, domains) and get_token(kind):
            h["Authorization"] = "Bearer " + get_token(kind)
            break
    return h


def parse_hf(url):
    u = urllib.parse.urlparse(url)
    if u.netloc not in ("huggingface.co", "www.huggingface.co", "hf.co"):
        return None
    parts = [urllib.parse.unquote(x) for x in u.path.strip("/").split("/")]
    if len(parts) < 2:
        return None
    repo, rev, path = f"{parts[0]}/{parts[1]}", "main", None
    if len(parts) >= 4 and parts[2] in ("resolve", "blob", "tree"):
        rev = parts[3]
        if parts[2] != "tree" and len(parts) > 4:
            path = "/".join(parts[4:])
    return repo, rev, path
