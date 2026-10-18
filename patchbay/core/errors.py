"""利用者に見せるエラー(検証の失敗など)。画面には、メッセージがそのまま出る。"""


class HubError(Exception):
    pass
