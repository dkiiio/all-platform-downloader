"""选择下载引擎、拼命令、执行并识别常见错误。"""

import io
import os
import re
import subprocess
import sys
from collections import deque

from . import urls

GALLERY_DL = "gallery-dl"
YT_DLP = "yt-dlp"
ENGINES = (GALLERY_DL, YT_DLP)

# 两个引擎都支持 --cookies-from-browser 的浏览器
SUPPORTED_BROWSERS = ("chrome", "chromium", "edge", "brave", "opera", "vivaldi", "firefox", "safari")

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

# gallery-dl 退出码为 0 但实际什么都没下载
NO_RESULTS = "No results for"
# gallery-dl 下载了一部分文件,另一部分失败
PARTIAL = "Failed to download"


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
        if urls.is_x(url):
            # 视频放在卡片(unified_card)里的推文默认会被跳过;链接预览图不要
            cmd += ["-o", "cards=true", "-o", 'cards-blacklist=["summary","summary_large_image"]']
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
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    # newline="" 保留 \r,让 yt-dlp 的进度条原地刷新,而不是变成几百行
    reader = io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace", newline="")
    try:
        for chunk in reader:
            sys.stdout.write(chunk)
            sys.stdout.flush()
            if not chunk.endswith("\r"):
                tail.append(chunk)
    except KeyboardInterrupt:
        # 终端的 Ctrl-C 已经发给了子进程,等它自己收尾
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise
    return proc.wait(), "".join(tail)


_X_LOGIN_HINT = (
    "需要登录态:确认该浏览器/配置里已登录 x.com,且在 X 的「设置 → 隐私和安全 → 你看到的内容」中"
    "勾选了「显示可能含有敏感内容的媒体」;仍不行就运行 xdl --update。"
)
_SITE_LOGIN_HINT = "可能需要登录或引擎过旧:确认浏览器里已登录该网站,或运行 xdl --update 升级下载引擎。"

# (匹配错误行的正则, 提示);登录类提示会按是否是 X 链接替换
_HINTS = (
    (
        r"operation not permitted|binarycookies|safari cookies",
        "读取 Safari cookie 被系统拦截:到「系统设置 → 隐私与安全性 → 完全磁盘访问权限」里给"
        "终端(或「快捷指令」/Automator)打开权限后重试。",
    ),
    (
        r"keyring|keychain|safe storage|decrypt",
        "读取浏览器 cookie 失败:macOS 弹出钥匙串提示(来自「security」)时要点「始终允许」,详见 README 常见问题。",
    ),
    (
        r"cookies? database",
        "找不到浏览器配置:检查 --browser / --profile 是否正确(Chrome 在 chrome://version 的「个人资料路径」末尾能看到名字,如 Default、Profile 1)。",
    ),
    (
        r"\bhttp ?error:? 40[13]\b|\b40[13] (?:unauthorized|forbidden)\b|authorizationerror|authrequired"
        r"|credentials required|requires? (?:authentication|login)|log ?in required|\bnsfw\b|sensitive (?:content|media)|age-restricted",
        "login",
    ),
    (
        r"\bhttp ?error:? 429\b|\b429 too many requests\b|too many requests|rate limit",
        "被限流了:稍等十几分钟再试,批量下载时别一次塞太多链接。",
    ),
)


def _error_lines(output):
    """只看报错/警告行,避免推文 ID、下载速度里的数字被误判。"""
    return "\n".join(
        line for line in output.lower().splitlines() if "error" in line or "warning" in line
    )


def diagnose(output, url=""):
    """根据输出给出中文排查提示(可能为空)。"""
    text = _error_lines(output)
    hints = []
    for pattern, hint in _HINTS:
        if re.search(pattern, text):
            if hint == "login":
                hint = _X_LOGIN_HINT if urls.is_x(url) else _SITE_LOGIN_HINT
            hints.append(hint)
    return hints
