#!/bin/zsh
# 下载剪贴板里的链接,完成后弹 macOS 通知。
# 给「快捷指令」或 Automator 的「运行 Shell 脚本」使用:它们的 PATH 很短,这里补上常见位置。
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

LOG="$HOME/Library/Logs/xdl.log"
mkdir -p "${LOG:h}"

if ! command -v xdl >/dev/null 2>&1; then
  osascript -e 'display notification "找不到 xdl,请先按 README 用 pipx 安装" with title "xdl"'
  exit 127
fi

echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >>"$LOG"
xdl --notify --clipboard-fallback "$@" </dev/null >>"$LOG" 2>&1
rc=$?  # zsh 里 status 是只读变量,不能用

# 0/1/2/3/130 xdl 自己会发通知;其他退出码说明 xdl 根本没跑起来(比如 pipx 的 Python 被 brew 升级掉了)
case $rc in
  0|1|2|3|130) ;;
  *) osascript -e 'display notification "xdl 无法启动,详见 ~/Library/Logs/xdl.log" with title "xdl 出错"' ;;
esac
exit $rc
