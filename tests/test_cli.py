import io
import shlex
import sys

import pytest

from xdl import cli, config, engines


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """不读真实配置/环境/剪贴板,不真的下载。"""
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", tmp_path / "missing.ini")
    for k in ("XDL_BROWSER", "XDL_PROFILE", "XDL_OUTPUT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(cli, "_read_clipboard", lambda: "")
    monkeypatch.setattr(cli, "_notify", lambda *a: None)
    monkeypatch.setattr(sys, "stdin", _Stdin("", tty=True))

    def no_run(cmd):
        raise AssertionError("engines.run should be mocked")
    monkeypatch.setattr(engines, "run", no_run)


class _Stdin(io.StringIO):
    def __init__(self, text, tty=False):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def _commands(out):
    return [shlex.split(line[2:]) for line in out.splitlines() if line.startswith("$ ")]


def _targets(out):
    return list(dict.fromkeys(c[-1] for c in _commands(out)))


def test_dry_run_args(tmp_path, capsys):
    code = cli.main(["--dry-run", "-o", str(tmp_path), "-p", "Profile 2",
                     "看 https://twitter.com/jack/status/20?s=20，以及 https://x.com/jack/status/20/photo/1"])
    assert code == 0
    cmds = _commands(capsys.readouterr().out)
    assert [c[2] for c in cmds] == ["gallery_dl", "yt_dlp"]  # 规范化后去重,并列出备用引擎
    cmd = cmds[0]
    assert cmd[-1] == "https://x.com/jack/status/20"
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "chrome:Profile 2"


def test_dry_run_flags(tmp_path, capsys):
    assert cli.main(["--dry-run", "--no-cookies", "--no-archive", "-e", "yt-dlp",
                     "-o", str(tmp_path), "https://x.com/jack/status/20"]) == 0
    (cmd,) = _commands(capsys.readouterr().out)
    assert cmd[2] == "yt_dlp"
    assert "--cookies-from-browser" not in cmd and "--download-archive" not in cmd


def test_reads_file(tmp_path, capsys):
    f = tmp_path / "links.txt"
    f.write_text("https://x.com/a/status/1\nhttps://www.youtube.com/watch?v=abc\n", encoding="utf-8")
    assert cli.main(["--dry-run", "-o", str(tmp_path), "-f", str(f)]) == 0
    assert _targets(capsys.readouterr().out) == [
        "https://x.com/a/status/1", "https://www.youtube.com/watch?v=abc"]


def test_reads_piped_stdin(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin("https://x.com/a/status/1\n"))
    monkeypatch.setattr(cli, "_read_clipboard", lambda: "https://x.com/clip/status/9")
    assert cli.main(["--dry-run", "-o", str(tmp_path)]) == 0
    assert _targets(capsys.readouterr().out) == ["https://x.com/a/status/1"]


def test_piped_text_without_urls_does_not_use_clipboard(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _Stdin("一段没有链接的文字\n"))
    monkeypatch.setattr(cli, "_read_clipboard", lambda: "https://x.com/clip/status/9")
    assert cli.main(["--dry-run"]) == 2


def test_args_without_urls_fall_back_to_clipboard(monkeypatch, tmp_path, capsys):
    # 快速操作在访达里选中文件时,传进来的是文件路径
    monkeypatch.setattr(cli, "_read_clipboard", lambda: "https://x.com/clip/status/9")
    assert cli.main(["--dry-run", "-o", str(tmp_path), "/Users/a/Desktop/photo.png"]) == 0
    assert _targets(capsys.readouterr().out) == ["https://x.com/clip/status/9"]


@pytest.mark.parametrize("tty", [False, True])
def test_empty_stdin_falls_back_to_clipboard(monkeypatch, tmp_path, capsys, tty):
    monkeypatch.setattr(sys, "stdin", _Stdin("", tty=tty))
    monkeypatch.setattr(cli, "_read_clipboard", lambda: "复制的：https://twitter.com/clip/status/9?s=20")
    assert cli.main(["--dry-run", "-o", str(tmp_path)]) == 0
    assert _targets(capsys.readouterr().out) == ["https://x.com/clip/status/9"]


def test_no_urls_exit_2(monkeypatch, capsys):
    notes = []
    monkeypatch.setattr(cli, "_notify", lambda *a: notes.append(a))
    assert cli.main(["--dry-run", "--notify"]) == 2
    assert "没有找到链接" in capsys.readouterr().err
    assert len(notes) == 1


def test_text_without_urls_exit_2(capsys):
    assert cli.main(["--dry-run", "nothing here"]) == 2


def _fake_run(results, calls):
    def run(cmd):
        calls.append(cmd)
        return results.pop(0)
    return run


def test_falls_back_to_yt_dlp(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(engines, "run", _fake_run([(1, "boom"), (0, "")], calls))
    out_dir = tmp_path / "out"
    assert cli.main(["-o", str(out_dir), "https://x.com/a/status/1"]) == 0
    assert [c[2] for c in calls] == ["gallery_dl", "yt_dlp"]
    assert out_dir.is_dir()
    out = capsys.readouterr().out
    assert "gallery-dl 失败(退出码 1)" in out and "成功 1,失败 0" in out


def test_all_engines_fail_exit_1_with_hints(monkeypatch, tmp_path, capsys):
    calls = []
    # 提示应来自所有引擎的输出,而不只是最后一个
    monkeypatch.setattr(engines, "run", _fake_run(
        [(1, "[cookies][warning] Failed to decrypt cookies"), (1, "ERROR: HTTP Error 429: Too Many Requests")], calls))
    assert cli.main(["-o", str(tmp_path), "https://x.com/a/status/1"]) == 1
    out = capsys.readouterr().out
    assert "钥匙串" in out and "限流" in out
    assert "失败:https://x.com/a/status/1" in out


def test_partial_failure_notifies(monkeypatch, tmp_path):
    notes = []
    monkeypatch.setattr(cli, "_notify", lambda *a: notes.append(a))
    monkeypatch.setattr(engines, "run", _fake_run([(0, ""), (2, ""), (2, "")], []))
    assert cli.main(["--notify", "-o", str(tmp_path),
                     "https://x.com/a/status/1", "https://x.com/b/status/2"]) == 1
    assert notes == [("xdl 有下载失败", "成功 1,失败 1")]


def test_no_results_from_gallery_dl_falls_back(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(engines, "run", _fake_run(
        [(0, "[twitter][info] No results for https://x.com/a/status/1\n"), (0, "")], calls))
    assert cli.main(["-o", str(tmp_path), "https://x.com/a/status/1"]) == 0
    assert [c[2] for c in calls] == ["gallery_dl", "yt_dlp"]
    assert "没找到可下载的媒体" in capsys.readouterr().out


def test_partial_gallery_dl_failure_skips_fallback(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(engines, "run", _fake_run(
        [(4, "[download][error] Failed to download 20_3.jpg\n")], calls))
    assert cli.main(["-o", str(tmp_path), "https://x.com/a/status/1"]) == 1
    assert len(calls) == 1
    assert "部分失败:https://x.com/a/status/1" in capsys.readouterr().out


def test_ctrl_c_exits_130(monkeypatch, tmp_path, capsys):
    notes = []
    monkeypatch.setattr(cli, "_notify", lambda *a: notes.append(a))

    def interrupted(cmd):
        raise KeyboardInterrupt
    monkeypatch.setattr(engines, "run", interrupted)
    assert cli.main(["--notify", "-o", str(tmp_path), "https://x.com/a/status/1", "https://x.com/b/status/2"]) == 130
    assert "已取消" in capsys.readouterr().err
    assert len(notes) == 1


def test_unsupported_browser_exit_2(capsys):
    assert cli.main(["--dry-run", "-b", "arc", "https://x.com/a/status/1"]) == 2
    assert "不支持的浏览器" in capsys.readouterr().err


def test_bad_config_exit_2(tmp_path, capsys):
    bad = tmp_path / "bad.ini"
    bad.write_text("browser = firefox\n", encoding="utf-8")
    assert cli.main(["--dry-run", "--config", str(bad), "https://x.com/a/status/1"]) == 2
    assert "[xdl]" in capsys.readouterr().err


def test_missing_link_file_exit_2(tmp_path, capsys):
    assert cli.main(["--dry-run", "-f", str(tmp_path / "nope.txt")]) == 2


def test_unwritable_output_exit_2(tmp_path, capsys, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert cli.main(["-o", str(blocker / "sub"), "https://x.com/a/status/1"]) == 2
    assert "无法创建下载目录" in capsys.readouterr().err


def test_unexpected_error_exit_3(monkeypatch, tmp_path, capsys):
    def boom(cmd):
        raise RuntimeError("kaput")
    monkeypatch.setattr(engines, "run", boom)
    assert cli.main(["-o", str(tmp_path), "https://x.com/a/status/1"]) == 3
    assert "RuntimeError: kaput" in capsys.readouterr().err


def test_as_str_escapes():
    assert cli._as_str('a"b\\c') == '"a\\"b\\\\c"'


def test_update_runs_pip(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd: calls.append(cmd) or 0)
    assert cli.main(["--update"]) == 0
    assert calls[0][1:5] == ["-m", "pip", "install", "-U"]
