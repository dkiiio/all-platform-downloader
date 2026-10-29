"""选择下载引擎、拼命令、执行并识别常见错误。"""

import codecs
import os
import re
import shutil
import subprocess
import sys

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

# gallery-dl 某个文件下载失败时的日志
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
        if sys.stdout.isatty():
            # 输出走管道时 gallery-dl 不显示进度,大视频会像卡住一样
            cmd += ["-o", "output.mode=terminal"]
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


def _split_lines(buf, lines, final=False):
    """把完整的行加进 lines,返回还没结束的部分。单独以 \r 结尾的是进度条刷新,丢掉。"""
    hold = ""
    if buf.endswith("\r") and not final:
        # 可能是被切开的 \r\n,等下一块再判断
        buf, hold = buf[:-1], "\r"
    parts = re.split(r"(\r\n|\n|\r)", buf)
    for seg, sep in zip(parts[0::2], parts[1::2]):
        if sep != "\r":
            lines.append(seg + "\n")
    return parts[-1] + hold


def run(cmd):
    """执行命令,原样实时输出,返回 (退出码, 去掉进度条刷新后的全部输出)。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if sys.stdout.isatty():
        # 子进程的输出是管道,拿不到终端宽度
        env["COLUMNS"] = str(shutil.get_terminal_size().columns)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    lines, pending = [], ""
    try:
        while True:
            data = proc.stdout.read1(65536)
            text = decoder.decode(data, final=not data)
            if text:
                # 收到多少写多少,yt-dlp 的进度条才能原地刷新且不滞后
                sys.stdout.write(text)
                sys.stdout.flush()
                pending = _split_lines(pending + text, lines)
            if not data:
                break
    except KeyboardInterrupt:
        # 终端的 Ctrl-C 已经发给了子进程,等它自己收尾
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise
    pending = _split_lines(pending, lines, final=True)
    if pending:
        lines.append(pending + "\n")
    return proc.wait(), "".join(lines)


def gallery_dl_saved(output):
    """gallery-dl 每保存/跳过一个文件输出一行:管道模式是绝对路径或「# 路径」,终端模式是「✔ 路径」。"""
    return sum(1 for line in output.splitlines() if line.startswith(("/", "# ", "\u2714")))


def gallery_dl_no_results(output, url):
    """顶层任务一个文件都没有(子任务的 No results 不算,比如关注列表里某个人没有媒体)。"""
    pattern = r"No results for " + re.escape(url) + r"\s*$"
    return gallery_dl_saved(output) == 0 and re.search(pattern, output, re.M) is not None


def gallery_dl_partial(output):
    """存下了一部分,另一部分失败。"""
    return PARTIAL in output and gallery_dl_saved(output) > 0


_X_LOGIN_HINT = (
    "需要登录态:确认该浏览器/配置里已登录 x.com,且在 X 的「设置 → 隐私和安全 → 你看到的内容」中"
    "勾选了「显示可能含有敏感内容的媒体」;仍不行就运行 xdl --update。"
)
_SITE_LOGIN_HINT = "可能需要登录或引擎过旧:确认浏览器里已登录该网站,或运行 xdl --update 升级下载引擎。"

# (名字, 匹配报错/警告行的正则, 提示);"login" 会按是否是 X 链接换成对应提示
_HINTS = (
    (
        "safari",
        r"binarycookies|com\.apple\.safari|safari cookies",
        "读取 Safari cookie 被系统拦截:到「系统设置 → 隐私与安全性 → 完全磁盘访问权限」里给"
        "终端(或「快捷指令」/Automator)打开权限后重试。",
    ),
    (
        "keychain",
        r"keyring|keychain|safe storage|decrypt",
        "读取浏览器 cookie 失败:macOS 弹出钥匙串提示(来自「security」)时要点「始终允许」,详见 README 常见问题。",
    ),
    (
        "profile",
        r"(?:could not|unable to) find (?!safari)\w+ cookies database",
        "找不到浏览器配置:检查 --browser / --profile 是否正确(Chrome 在 chrome://version 的「个人资料路径」末尾"
        "能看到名字,如 Default、Profile 1;Firefox 是 Profiles 下的文件夹名)。",
    ),
    (
        "blocked",
        r"blocked your account",
        "对方屏蔽了你当前登录的 X 账号:换一个登录了其他账号的浏览器配置(-b / -p)再试。",
    ),
    (
        "protected",
        r"protected tweet|tweets are protected",
        "受保护账号:需要用已关注对方的 X 账号登录。",
    ),
    (
        "login",
        r"\bhttp ?error:? 40[13]\b|\b40[13] (?:unauthorized|forbidden)\b|authorizationerror|authrequired"
        r"|credentials required|could not authenticate|requires? (?:authentication|login)|log ?in required"
        r"|\buse --cookies|sign in to confirm|\bnsfw\b|sensitive (?:content|media)|age-restricted",
        "login",
    ),
    (
        "ratelimit",
        r"\bhttp ?error:? 429\b|\b429 too many requests\b|too many requests|rate[- ]limit",
        "被限流了:稍等十几分钟再试,批量下载时别一次塞太多链接。",
    ),
    (
        "permission",
        r"operation not permitted|permission denied",
        "没有权限写入下载目录:用 -o 换个目录,或在「系统设置 → 隐私与安全性」里给终端(或「快捷指令」)"
        "该文件夹的访问权限。",
    ),
)

# 命中前者时不再给后者:被屏蔽/受保护不是没登录;Safari 的权限问题已有专门提示
_SUPPRESS = {"blocked": {"login"}, "protected": {"login"}, "safari": {"permission"}}


def _error_lines(output):
    """只看报错/警告行,避免推文 ID、下载速度里的数字被误判。"""
    return "\n".join(
        line for line in output.lower().splitlines() if "error" in line or "warning" in line
    )


def diagnose(output, url=""):
    """根据输出给出中文排查提示(可能为空)。"""
    text = _error_lines(output)
    matched = [name for name, pattern, _ in _HINTS if re.search(pattern, text)]
    suppressed = set().union(*(_SUPPRESS.get(name, set()) for name in matched))
    hints = []
    for name, _, hint in _HINTS:
        if name in matched and name not in suppressed:
            if hint == "login":
                hint = _X_LOGIN_HINT if urls.is_x(url) else _SITE_LOGIN_HINT
            hints.append(hint)
    return hints
