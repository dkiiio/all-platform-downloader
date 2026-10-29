#!/bin/zsh
# 下载剪贴板里的链接,完成后弹 macOS 通知。
# 给「快捷指令」或 Automator 的「运行 Shell 脚本」使用:它们的 PATH 很短,这里补上常见位置。
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v xdl >/dev/null 2>&1; then
  osascript -e 'display notification "找不到 xdl,请先按 README 用 pipx 安装" with title "xdl"'
  exit 127
fi

LOG="$HOME/Library/Logs/xdl.log"
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  xdl --notify "$@" </dev/null
} >>"$LOG" 2>&1
