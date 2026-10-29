"""配置:命令行参数 > 环境变量 > 配置文件 > 默认值。"""

import configparser
import os
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.config/xdl/config.ini").expanduser()

_FIELDS = ("browser", "profile", "output")


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
        return self.browser + (":" + self.profile if self.profile else "")


def load(path=None, env=None, overrides=None):
    env = os.environ if env is None else env
    cfg = Config()

    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if path.is_file():
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        if parser.has_section("xdl"):
            section = parser["xdl"]
            cfg = replace(cfg, **{k: section[k] for k in _FIELDS if section.get(k)})

    from_env = {k: env["XDL_" + k.upper()] for k in _FIELDS if env.get("XDL_" + k.upper())}
    cfg = replace(cfg, **from_env)

    if overrides:
        cfg = replace(cfg, **{k: v for k, v in overrides.items() if v is not None})
    return cfg
