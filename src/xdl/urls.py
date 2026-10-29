"""链接提取、X 链接识别与规范化。"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit

# 遇到空白、引号、尖括号、中文标点或汉字就截断(浏览器复制的链接里中文都是 %xx 编码)
_URL_RE = re.compile(
    r"https?://[^\s<>\"'，。、；：！？（）【】「」『』《》“”‘’…"
    "\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]+"
)
_TRAILING = ".,;:!?)]}'\""

X_HOSTS = {
    "x.com",
    "twitter.com",
    "mobile.x.com",
    "mobile.twitter.com",
    "m.x.com",
    "m.twitter.com",
    # 常见的嵌入预览镜像,链接结构与 x.com 相同
    "fxtwitter.com",
    "vxtwitter.com",
    "fixupx.com",
    "fixvx.com",
    "twittpr.com",
}

_STATUS_RE = re.compile(r"^/(?P<user>[^/]+)/status(?:es)?/(?P<id>\d+)")
_WEB_STATUS_RE = re.compile(r"^/i/(?:web/)?status/(?P<id>\d+)")
# 分享时附带的跟踪参数,其余参数(如搜索的 q=)要保留
_TRACKING_PARAMS = {"s", "t", "ref_src", "ref_url"}


def extract_urls(text):
    """从任意文本(剪贴板、文件)里提取链接,去重并保持顺序。"""
    seen = set()
    result = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(_TRAILING)
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def host_of(url):
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_x(url):
    return host_of(url) in X_HOSTS


def normalize(url):
    """把 X 的各种链接写法统一成 https://x.com/...,其他链接原样返回。"""
    if not is_x(url):
        return url
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    m = _STATUS_RE.match(path)
    if m and m.group("user") != "i":
        return "https://x.com/{}/status/{}".format(m.group("user"), m.group("id"))
    m = _WEB_STATUS_RE.match(path)
    if m:
        return "https://x.com/i/status/{}".format(m.group("id"))
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k not in _TRACKING_PARAMS])
    return "https://x.com" + path + ("?" + query if query else "")
