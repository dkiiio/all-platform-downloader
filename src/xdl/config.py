"""配置:命令行参数 > 环境变量 > 配置文件 > 默认值。"""

import configparser
import os
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.config/xdl/config.ini").expanduser()

_FIELDS = ("browser", "profile", "output")

# 这些浏览器没有「配置名」的概念,传了 profile 反而会让 yt-dlp 把它当成文件路径
_NO_PROFILE_BROWSERS = {"safari"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    browser: str = "chrome"
    profile: str = ""
    output: str = "~/Downloads/xdl"
    cookies: bool = True
    archive: bool = True

    @property
    def output_dir(self):
        return Path(self.output).expanduser()

    @property
    def cookie_spec(self):
        """gallery-dl 和 yt-dlp 通用的 --cookies-from-browser 参数值。"""
        if not self.profile or self.browser.lower() in _NO_PROFILE_BROWSERS:
            return self.browser
        return self.browser + ":" + self.profile


def _apply(cfg, values):
    """合并一层配置。换了浏览器但这一层没给配置名时,丢掉下层的配置名
    (Chrome 的 Profile 2 对 Firefox/Safari 没有意义)。"""
    if "browser" in values and "profile" not in values and values["browser"] != cfg.browser:
        values = dict(values, profile="")
    return replace(cfg, **values)


def _read_file(path, explicit):
    if not path.is_file():
        if explicit:
            raise ConfigError("找不到配置文件:{}".format(path))
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError) as e:
        raise ConfigError("配置文件格式错误:{}(第一行应为 [xdl]):{}".format(path, e)) from e
    if not parser.has_section("xdl"):
        raise ConfigError("配置文件缺少 [xdl] 段:{}".format(path))
    section = parser["xdl"]
    return {k: section[k] for k in _FIELDS if section.get(k)}


def load(path=None, env=None, overrides=None):
    env = os.environ if env is None else env
    cfg = Config()

    explicit = bool(path)
    path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    cfg = _apply(cfg, _read_file(path, explicit))
    cfg = _apply(cfg, {k: env["XDL_" + k.upper()] for k in _FIELDS if env.get("XDL_" + k.upper())})
    if overrides:
        cfg = _apply(cfg, {k: v for k, v in overrides.items() if v is not None})
    return cfg
