"""选择下载引擎、拼命令、执行并识别常见错误。"""

import subprocess
import sys
from collections import deque

from . import urls

GALLERY_DL = "gallery-dl"
YT_DLP = "yt-dlp"
ENGINES = (GALLERY_DL, YT_DLP)

# 视频站优先交给 yt-dlp
VIDEO_FIRST_HOSTS = (
    "youtube.com",
    "youtu.be",
    "bilibili.com",
    "b23.tv",
    "tiktok.com",
    "douyin.com",
    "vimeo.com",
    "twitch.tv",
    "nicovideo.jp",
    "ixigua.com",
)


def _gallery_dl_supports(url):
    try:
        from gallery_dl import extractor
    except ImportError:
        return False
    try:
        return extractor.find(url) is not None
    except Exception:
        return False


def plan(url, forced=None):
    """返回按顺序尝试的引擎列表。"""
    if forced:
        return [forced]
    if urls.is_x(url):
        # gallery-dl 一次拿全图片、视频、GIF;yt-dlp 作为 X 接口变动时的备用
        return [GALLERY_DL, YT_DLP]
    host = urls.host_of(url)
    if any(host == h or host.endswith("." + h) for h in VIDEO_FIRST_HOSTS):
        return [YT_DLP, GALLERY_DL]
    if _gallery_dl_supports(url):
        return [GALLERY_DL, YT_DLP]
    return [YT_DLP]


def build_command(engine, url, cfg):
    out = cfg.output_dir
    if engine == GALLERY_DL:
        cmd = [sys.executable, "-m", "gallery_dl", "-d", str(out)]
        if cfg.cookies:
            cmd += ["--cookies-from-browser", cfg.cookie_spec]
        if cfg.archive:
            cmd += ["--download-archive", str(out / ".archive-gallery-dl.sqlite3")]
    elif engine == YT_DLP:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-P", str(out),
            "-o", "%(extractor_key)s/%(uploader_id,uploader|unknown)s/%(id)s_%(title).60B.%(ext)s",
            "--no-mtime",
        ]
        if cfg.cookies:
            cmd += ["--cookies-from-browser", cfg.cookie_spec]
        if cfg.archive:
            cmd += ["--download-archive", str(out / ".archive-yt-dlp.txt")]
    else:
        raise ValueError("未知引擎: " + engine)
    return cmd + [url]


def run(cmd):
    """执行命令,实时输出,返回 (退出码, 最后若干行输出)。"""
    tail = deque(maxlen=80)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        tail.append(line)
    return proc.wait(), "".join(tail)


_HINTS = (
    (
        ("keyring", "keychain", "safe storage", "decrypt", "failed to decrypt"),
        "读取浏览器 cookie 失败:macOS 弹出「Chrome Safe Storage」钥匙串提示时要点「始终允许」;"
        "用 Safari 需要给终端/快捷指令开「完全磁盘访问权限」。",
    ),
    (
        ("cookies database", "cookie database"),
        "找不到浏览器配置:检查 --browser / --profile 是否正确(Chrome 在 chrome://version 的「个人资料路径」末尾能看到名字,如 Default、Profile 1)。",
    ),
    (
        ("401", "403", "unauthorized", "login", "log in", "authenticat", "nsfw", "sensitive", "age-restricted"),
        "需要登录态:确认该浏览器/配置里已登录 x.com,且在 X 的「设置 → 隐私和安全 → 你看到的内容」中勾选了「显示可能含有敏感内容的媒体」。",
    ),
    (
        ("429", "rate limit", "too many requests"),
        "被限流了:稍等十几分钟再试,批量下载时别一次塞太多链接。",
    ),
)


def diagnose(output):
    """根据输出给出中文排查提示(可能为空)。"""
    low = output.lower()
    return [hint for keys, hint in _HINTS if any(k in low for k in keys)]
