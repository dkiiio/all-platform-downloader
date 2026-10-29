"""命令行入口。"""

import argparse
import shlex
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from . import __version__, config, engines, urls


def _parser():
    p = argparse.ArgumentParser(
        prog="xdl",
        description="用浏览器里的登录态下载 X 等平台的图片和视频。"
        "不给链接时读取剪贴板(macOS),或读取管道输入。",
    )
    p.add_argument("urls", nargs="*", help="要下载的链接,可以是一段包含链接的文字")
    p.add_argument("-f", "--file", help="从文本文件读取链接(每行一个,或任意包含链接的文本)")
    p.add_argument("-o", "--output", help="下载目录(默认 ~/Downloads/xdl)")
    p.add_argument(
        "-b",
        "--browser",
        help="读取 cookie 的浏览器:{}(默认 chrome)".format("、".join(engines.SUPPORTED_BROWSERS)),
    )
    p.add_argument("-p", "--profile", help="浏览器配置名:Chrome 系如 Default、Profile 2;Firefox 是 Profiles 下的文件夹名;Safari 不需要")
    p.add_argument("-e", "--engine", choices=engines.ENGINES, help="强制使用某个下载引擎")
    p.add_argument("--no-cookies", action="store_true", help="不读取浏览器 cookie(匿名下载)")
    p.add_argument("--no-archive", action="store_true", help="不跳过已下载过的内容")
    p.add_argument("--notify", action="store_true", help="完成后发 macOS 通知(给快捷指令用)")
    p.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令")
    p.add_argument("--config", help="配置文件路径(默认 ~/.config/xdl/config.ini)")
    p.add_argument("--update", action="store_true", help="升级 gallery-dl 和 yt-dlp(X 接口变动后常用)")
    p.add_argument("--version", action="version", version="xdl " + __version__)
    return p


def _read_clipboard():
    if shutil.which("pbpaste"):
        return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    return ""


def _collect(args):
    texts = list(args.urls)
    if args.file:
        with open(Path(args.file).expanduser(), encoding="utf-8", errors="replace") as fh:
            texts.append(fh.read())
    found = urls.extract_urls("\n".join(texts))
    piped = ""
    if not texts and sys.stdin is not None and not sys.stdin.isatty():
        piped = sys.stdin.read()
        found = urls.extract_urls(piped)
    # 快捷指令里 stdin 通常是空的,快速操作传进来的可能是文件路径或不含链接的文字,
    # 这些情况都退回剪贴板;只有管道里明确给了文字时才不去碰剪贴板
    if not found and not piped.strip() and not args.file:
        found = urls.extract_urls(_read_clipboard())
    # 规范化之后可能出现重复(比如 twitter.com 与 x.com 同一条)
    return list(dict.fromkeys(urls.normalize(u) for u in found))


def _notify(title, message):
    if not shutil.which("osascript"):
        return
    script = "display notification {} with title {}".format(_as_str(message), _as_str(title))
    subprocess.run(["osascript", "-e", script], check=False)


def _as_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _update():
    cmd = [sys.executable, "-m", "pip", "install", "-U", "gallery-dl", "yt-dlp[default]"]
    print("$", " ".join(shlex.quote(c) for c in cmd))
    return subprocess.call(cmd)


OK, FAILED, PARTIAL = "ok", "failed", "partial"


def download(url, cfg, forced=None, dry_run=False):
    """依次尝试各个引擎,返回 OK / FAILED / PARTIAL。"""
    output = ""
    status = FAILED
    for engine in engines.plan(url, forced):
        cmd = engines.build_command(engine, url, cfg)
        print("\n==> [{}] {}".format(engine, url))
        if dry_run:
            print("$", " ".join(shlex.quote(c) for c in cmd))
            status = OK
            continue
        code, out = engines.run(cmd)
        output += out
        is_gdl = engine == engines.GALLERY_DL
        if is_gdl and engines.PARTIAL in out:
            # 已经存下了一部分,换引擎会重复下载;重跑时存档会跳过已下好的
            print("!! gallery-dl 有文件下载失败,重新运行一次通常能补齐")
            status = PARTIAL
            break
        if code == 0 and not (is_gdl and engines.NO_RESULTS in out):
            return OK
        if code == 0:
            print("!! gallery-dl 没找到可下载的媒体")
        else:
            print("!! {} 失败(退出码 {})".format(engine, code))
    for hint in engines.diagnose(output, url):
        print("提示:" + hint)
    return status


def _fail(args, message, code):
    print(message, file=sys.stderr)
    if args.notify:
        _notify("xdl 出错", message)
    return code


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.update:
        return _update()
    try:
        return _main(args)
    except KeyboardInterrupt:
        return _fail(args, "\n已取消", 130)
    except (config.ConfigError, OSError) as e:
        return _fail(args, str(e), 2)
    except Exception as e:
        traceback.print_exc()
        return _fail(args, "{}: {}(详见 ~/Library/Logs/xdl.log)".format(type(e).__name__, e), 3)


def _main(args):
    cfg = config.load(
        args.config,
        overrides={
            "browser": args.browser,
            "profile": args.profile,
            "output": args.output,
            "cookies": False if args.no_cookies else None,
            "archive": False if args.no_archive else None,
        },
    )
    if cfg.cookies and cfg.browser.lower() not in engines.SUPPORTED_BROWSERS:
        raise config.ConfigError(
            "不支持的浏览器:{}。可选:{}".format(cfg.browser, "、".join(engines.SUPPORTED_BROWSERS))
        )

    targets = _collect(args)
    if not targets:
        return _fail(args, "没有找到链接。用法:xdl <链接>,或先复制链接再直接运行 xdl。", 2)

    if not args.dry_run:
        try:
            cfg.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError("无法创建下载目录 {}:{}".format(cfg.output_dir, e.strerror or e)) from e

    results = [(u, download(u, cfg, args.engine, args.dry_run)) for u in targets]
    failed = [u for u, r in results if r != OK]
    ok = len(targets) - len(failed)

    print("\n完成:成功 {},失败 {}。保存在 {}".format(ok, len(failed), cfg.output_dir))
    for u, r in results:
        if r != OK:
            print("  {}:{}".format("部分失败" if r == PARTIAL else "失败", u))
    if args.notify:
        msg = "成功 {},失败 {}".format(ok, len(failed)) if failed else "已下载 {} 个链接".format(ok)
        _notify("xdl 有下载失败" if failed else "xdl 下载完成", msg)
    return 1 if failed else 0
