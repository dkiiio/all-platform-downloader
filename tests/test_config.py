from pathlib import Path

import pytest

from xdl import config
from xdl.config import Config, load


@pytest.fixture
def ini(tmp_path):
    def write(body):
        path = tmp_path / "config.ini"
        path.write_text(body, encoding="utf-8")
        return path
    return write


@pytest.fixture(autouse=True)
def no_real_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", tmp_path / "missing.ini")


def test_defaults_when_file_missing():
    cfg = load(env={})
    assert cfg == Config()
    assert cfg.cookie_spec == "chrome"
    assert cfg.output_dir == Path("~/Downloads/xdl").expanduser()


def test_explicit_missing_file_is_an_error(tmp_path):
    with pytest.raises(config.ConfigError, match="找不到配置文件"):
        load(tmp_path / "nope.ini", env={})


def test_explicit_path_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "x.ini").write_text("[xdl]\nbrowser = firefox\n", encoding="utf-8")
    assert load("~/x.ini", env={}).browser == "firefox"


def test_file_values(ini):
    path = ini("[xdl]\nbrowser = firefox\nprofile = Profile 2\noutput = /tmp/dl\n")
    cfg = load(path, env={})
    assert (cfg.browser, cfg.profile, cfg.output) == ("firefox", "Profile 2", "/tmp/dl")
    assert cfg.cookie_spec == "firefox:Profile 2"


def test_blank_values_ignored(ini):
    assert load(ini("[xdl]\nbrowser =\n"), env={}).browser == "chrome"


@pytest.mark.parametrize("body", ["browser = firefox\n", "[other]\nbrowser = safari\n"])
def test_malformed_file_is_an_error(ini, body):
    with pytest.raises(config.ConfigError):
        load(ini(body), env={})


def test_percent_in_value_is_literal(ini):
    assert load(ini("[xdl]\noutput = ~/Downloads/100%\n"), env={}).output == "~/Downloads/100%"


def test_precedence_file_env_cli(ini):
    path = ini("[xdl]\nbrowser = firefox\nprofile = FileProf\noutput = /from/file\n")
    env = {"XDL_BROWSER": "edge", "XDL_PROFILE": "EnvProf", "XDL_OUTPUT": ""}
    cfg = load(path, env=env, overrides={"browser": None, "profile": None, "output": None})
    assert cfg.browser == "edge"        # env > file, None override ignored
    assert cfg.profile == "EnvProf"
    assert cfg.output == "/from/file"   # empty env ignored
    cfg = load(path, env=env, overrides={"browser": "brave", "profile": "CliProf"})
    assert (cfg.browser, cfg.profile) == ("brave", "CliProf")


def test_switching_browser_drops_lower_profile(ini):
    path = ini("[xdl]\nbrowser = chrome\nprofile = Profile 2\n")
    assert load(path, env={}, overrides={"browser": "firefox"}).cookie_spec == "firefox"
    assert load(path, env={"XDL_BROWSER": "safari"}).profile == ""
    # 同一个浏览器则保留
    assert load(path, env={}, overrides={"browser": "chrome"}).cookie_spec == "chrome:Profile 2"


def test_safari_never_gets_profile():
    assert Config(browser="safari", profile="Profile 2").cookie_spec == "safari"


def test_bool_overrides():
    cfg = load(env={}, overrides={"cookies": False, "archive": None})
    assert cfg.cookies is False and cfg.archive is True


def test_output_dir_expands_user():
    cfg = load(env={"XDL_OUTPUT": "~/foo"})
    assert cfg.output_dir == Path.home() / "foo"
