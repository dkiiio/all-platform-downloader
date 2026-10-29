import sys
from pathlib import Path

import pytest

from xdl import engines
from xdl.config import Config
from xdl.engines import GALLERY_DL, YT_DLP, build_command, diagnose, plan


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://x.com/jack/status/20", [GALLERY_DL, YT_DLP]),
        ("https://fxtwitter.com/jack/status/20", [GALLERY_DL, YT_DLP]),
        ("https://www.youtube.com/watch?v=abc", [YT_DLP, GALLERY_DL]),
        ("https://m.youtube.com/watch?v=abc", [YT_DLP, GALLERY_DL]),
        ("https://music.youtube.com/watch?v=abc", [YT_DLP, GALLERY_DL]),
        ("https://youtu.be/abc", [YT_DLP, GALLERY_DL]),
        ("https://www.bilibili.com/video/BV1xx", [YT_DLP, GALLERY_DL]),
        ("https://www.instagram.com/p/abc/", [GALLERY_DL, YT_DLP]),
        ("https://example.com/some/page", [YT_DLP]),
        ("https://notyoutube.com/watch", [YT_DLP]),
    ],
)
def test_plan(url, expected):
    assert plan(url) == expected


@pytest.mark.parametrize("engine", engines.ENGINES)
def test_plan_forced(engine):
    assert plan("https://x.com/jack/status/20", engine) == [engine]


def test_plan_without_gallery_dl(monkeypatch):
    monkeypatch.setitem(sys.modules, "gallery_dl", None)  # import -> ImportError
    assert plan("https://www.instagram.com/p/abc/") == [YT_DLP]


URL = "https://x.com/jack/status/20"


def _after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


@pytest.mark.parametrize("engine, module, out_flag, archive", [
    (GALLERY_DL, "gallery_dl", "-d", ".archive-gallery-dl.sqlite3"),
    (YT_DLP, "yt_dlp", "-P", ".archive-yt-dlp.txt"),
])
def test_build_command(tmp_path, engine, module, out_flag, archive):
    cfg = Config(browser="chrome", profile="Profile 2", output=str(tmp_path))
    cmd = build_command(engine, URL, cfg)
    assert cmd[:3] == [sys.executable, "-m", module]
    assert cmd[-1] == URL
    assert _after(cmd, out_flag) == str(tmp_path)
    assert _after(cmd, "--cookies-from-browser") == "chrome:Profile 2"  # one argv item
    assert Path(_after(cmd, "--download-archive")) == tmp_path / archive


@pytest.mark.parametrize("engine", engines.ENGINES)
def test_build_command_no_cookies_no_archive(tmp_path, engine):
    cmd = build_command(engine, URL, Config(output=str(tmp_path), cookies=False, archive=False))
    assert "--cookies-from-browser" not in cmd
    assert "--download-archive" not in cmd


def test_build_command_unknown_engine():
    with pytest.raises(ValueError):
        build_command("wget", URL, Config())


@pytest.mark.parametrize("output, keyword", [
    ("ERROR: Failed to decrypt with DPAPI", "钥匙串"),
    ("[cookies][warning] chrome: Failed to decrypt cookie (keyring)", "钥匙串"),
    ("ERROR: could not find chrome cookies database in '/x/Profile 9'", "--profile"),
    ("ERROR: [Errno 1] Operation not permitted: '/Users/a/Library/Cookies/Cookies.binarycookies'", "完全磁盘访问"),
    ("[twitter][error] AuthRequired: NSFW Tweet", "敏感内容"),
    ("ERROR: [twitter] 20: NSFW tweet requires authentication. Use --cookies", "敏感内容"),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "敏感内容"),
    ("[twitter][error] HttpError: '429 Too Many Requests' for 'https://x.com/i/api'", "限流"),
    ("WARNING: [twitter] Rate-limit exceeded; falling back to syndication endpoint", "限流"),
    ("[twitter][error] 'Could not authenticate you.'", "敏感内容"),
    ("ERROR: [twitter] 1840000000000000000: Error(s) while querying API: Could not authenticate you.", "敏感内容"),
    ("ERROR: [youtube] id: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies", "敏感内容"),
    ("ERROR: could not find safari cookies database", "完全磁盘访问"),
    ("[twitter][error] AuthorizationError: someone blocked your account", "屏蔽"),
    ("ERROR: [twitter] 1: You are not authorized to view this protected tweet. Use --cookies-from-browser", "受保护"),
    ("ERROR: unable to open for writing: [Errno 1] Operation not permitted: '/Volumes/USB/a.part'", "-o"),
])
def test_diagnose(output, keyword):
    hints = diagnose(output, URL)
    assert len(hints) == 1 and keyword in hints[0]


def test_diagnose_login_hint_depends_on_site():
    out = "ERROR: [youtube] abc: HTTP Error 403: Forbidden"
    (hint,) = diagnose(out, "https://www.youtube.com/watch?v=abc")
    assert "x.com" not in hint and "--update" in hint


@pytest.mark.parametrize("output", [
    # 推文 ID、用户名、下载速度里的 401/403/429/login/nsfw 不该触发提示
    "[twitter][error] NotFoundError: https://x.com/someone/status/1840123456789012345",
    "[twitter][error] HttpError: Connection timed out (https://x.com/nsfw_loginless/status/1842901234567890123)",
    "[download] 42.0% of 10.00MiB at 403.21KiB/s\nERROR: Postprocessing: ffprobe and ffmpeg not found",
    # 不影响使用的 cookie 数据库版本警告
    "WARNING: Possibly unsupported firefox cookies database version: 18",
    "[cookies][warning] Failed to get cookie database meta version (OperationalError)",
])
def test_diagnose_no_false_positives(output):
    assert diagnose(output, URL) == []


def test_diagnose_none_and_multiple():
    assert diagnose("") == []
    assert diagnose("all good") == []
    assert len(diagnose("ERROR: keyring locked\nERROR: rate limit exceeded")) == 2


def test_gallery_dl_fetches_card_videos_for_x_only(tmp_path):
    cfg = Config(output=str(tmp_path))
    assert "cards=true" in build_command(GALLERY_DL, URL, cfg)
    assert "cards=true" not in build_command(GALLERY_DL, "https://www.instagram.com/p/abc/", cfg)


def test_gallery_dl_output_analysis():
    url = "https://x.com/a/status/1"
    assert engines.gallery_dl_saved("/dl/1.jpg\n# /dl/2.jpg\n\u2714 dl/3.jpg\n[twitter][info] x\n") == 3
    assert engines.gallery_dl_no_results("[twitter][info] No results for https://x.com/a/status/1\n", url)
    assert not engines.gallery_dl_no_results("[twitter][info] No results for https://x.com/id:9/timeline\n", url)
    assert not engines.gallery_dl_partial("[download][error] Failed to download 1_1.mp4\n")
    assert engines.gallery_dl_partial("/dl/1.jpg\n[download][error] Failed to download 1_2.jpg\n")


def test_split_lines_handles_cr_across_chunks():
    lines = []
    pending = engines._split_lines("a\r", lines)
    pending = engines._split_lines(pending + "\nb 10%\rb 20%\r", lines)
    pending = engines._split_lines(pending + "done", lines, final=True)
    assert lines == ["a\n"] and pending == "done"


def test_run_keeps_progress_out_of_tail(capsys):
    script = "import sys\nfor i in range(3): sys.stdout.write('\\r%d%%' % i)\nprint()\nprint('中文 done')"
    code, tail = engines.run([sys.executable, "-c", script])
    assert code == 0
    assert "中文 done" in tail and "0%" not in tail
    assert "\r0%\r1%\r2%" in capsys.readouterr().out


def test_run_streams_and_returns_tail(capsys):
    code, tail = engines.run([sys.executable, "-c", "import sys; print('a'); print('b'); sys.exit(3)"])
    assert code == 3
    assert tail.splitlines() == ["a", "b"]
    assert capsys.readouterr().out.splitlines() == ["a", "b"]
