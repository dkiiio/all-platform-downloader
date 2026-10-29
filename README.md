# xdl

在 macOS 上下载 X(Twitter)等网站的图片和视频。底层用 [gallery-dl](https://github.com/mikf/gallery-dl) 和 [yt-dlp](https://github.com/yt-dlp/yt-dlp),通过 `--cookies-from-browser` 直接复用你浏览器里的登录态。

## 简介 / 原理

之前自建 cobalt 时发现:X 只把敏感内容的媒体给已登录用户,匿名接口拿不到,所以这类方案总是失败。
xdl 不用服务器、不用账号池,读取你本机浏览器里自己的 X 登录 cookie,以登录用户的身份请求,拿到的是原始画质。
cookie 只在本机读取,直接交给 gallery-dl / yt-dlp,不会写成文件,也不会上传。

引擎选择:

- X 链接:先用 gallery-dl(图片、视频、GIF 一次拿全),失败再用 yt-dlp。
- YouTube、Bilibili、TikTok、抖音、Vimeo、Twitch、niconico、西瓜视频:先 yt-dlp,再 gallery-dl。
- 其他网站:gallery-dl 支持就先用它,否则用 yt-dlp。
- `twitter.com`、`mobile.x.com`、`fxtwitter.com`、`vxtwitter.com`、`fixupx.com` 等写法会统一成 `x.com`,重复链接只下一次。

## 安装

```bash
brew install pipx ffmpeg
```

```bash
pipx ensurepath
```

执行完重开一个终端窗口,然后:

```bash
git clone git@github.com:dkiiio/all-platform-downloader.git ~/all-platform-downloader
```

```bash
cd ~/all-platform-downloader && pipx install .
```

```bash
xdl --version
```

ffmpeg 只在音视频分开下发的网站(如 YouTube)需要合并时才用到;只下 X 可以不装。下 YouTube 还需要一个 JS 运行时:

```bash
brew install deno
```

## X 账号准备

1. 在要读取 cookie 的浏览器(默认 Chrome)里登录 x.com。
2. 在 X 里打开:设置 → 隐私和安全 → 你看到的内容 → 勾选「显示可能含有敏感内容的媒体」。不开这个,登录了也拿不到敏感媒体。

可选:用小号放在单独的 Chrome 配置里,不碰主号。

1. Chrome 右上角头像 → 添加,新建一个配置,在里面登录小号,并按上面第 2 步打开敏感内容设置。
2. 在这个配置里打开 `chrome://version`,看「个人资料路径」最后一段,例如 `.../Google/Chrome/Profile 2` 的配置名就是 `Profile 2`(主配置一般是 `Default`)。
3. 用 `-p "Profile 2"` 指定,或写进配置文件(见下文)。

## 用法

下载单条推文:

```bash
xdl https://x.com/someone/status/1234567890123456789
```

一次多条:

```bash
xdl https://x.com/a/status/111 https://x.com/b/status/222
```

先复制链接(或一段含链接的文字),再直接运行,自动读取剪贴板:

```bash
xdl
```

从文件读取(每行一个,或任意含链接的文本):

```bash
xdl -f links.txt
```

下载整个账号的媒体(用户的「媒体」页):

```bash
xdl https://x.com/someone/media
```

用 Firefox 的登录态:

```bash
xdl -b firefox https://x.com/someone/status/1234567890123456789
```

用 Chrome 的指定配置:

```bash
xdl -p "Profile 2" https://x.com/someone/status/1234567890123456789
```

指定下载目录:

```bash
xdl -o ~/Pictures/x https://x.com/someone/status/1234567890123456789
```

忽略下载记录,重新下载:

```bash
xdl --no-archive https://x.com/someone/status/1234567890123456789
```

只打印将执行的命令,不下载:

```bash
xdl --dry-run https://x.com/someone/status/1234567890123456789
```

强制只用某个引擎(不再自动换另一个):

```bash
xdl -e yt-dlp https://x.com/someone/status/1234567890123456789
```

也支持管道输入,例如 `pbpaste | xdl`。

全部参数:

| 参数 | 说明 |
| --- | --- |
| `-f, --file` | 从文本文件读取链接 |
| `-o, --output` | 下载目录,默认 `~/Downloads/xdl` |
| `-b, --browser` | 读取 cookie 的浏览器:chrome、chromium、edge、brave、opera、vivaldi、firefox、safari,默认 chrome |
| `-p, --profile` | 浏览器配置名:Chrome 系如 `Default`、`Profile 2`;Firefox 是 `~/Library/Application Support/Firefox/Profiles/` 下的文件夹名(如 `abcd1234.default-release`);Safari 不需要 |
| `-e, --engine` | 强制引擎:`gallery-dl` 或 `yt-dlp` |
| `--no-cookies` | 不读浏览器 cookie,匿名下载 |
| `--no-archive` | 不跳过已下载过的内容 |
| `--notify` | 完成后发 macOS 通知 |
| `--dry-run` | 只打印命令 |
| `--config` | 配置文件路径,默认 `~/.config/xdl/config.ini` |
| `--update` | 升级 gallery-dl 和 yt-dlp |
| `--version` | 显示版本 |

退出码:全部成功 0;有失败或部分失败 1;没找到链接、配置文件有误或下载目录无法创建 2;意外错误 3;按 Ctrl-C 取消 130。

## 配置文件

`~/.config/xdl/config.ini`:

```ini
[xdl]
browser = chrome
profile = Profile 2
output = ~/Downloads/xdl
```

```bash
mkdir -p ~/.config/xdl && touch ~/.config/xdl/config.ini && open -e ~/.config/xdl/config.ini
```

不需要的项可以不写或留空。

也可以用环境变量:`XDL_BROWSER`、`XDL_PROFILE`、`XDL_OUTPUT`。

```bash
XDL_BROWSER=firefox xdl https://x.com/someone/status/1234567890123456789
```

优先级:命令行参数 > 环境变量 > 配置文件 > 默认值(`chrome`、不指定配置、`~/Downloads/xdl`)。

在高优先级处换了浏览器(比如 `-b firefox`)而没同时给 `-p` 时,配置文件里的 `profile` 会被忽略,因为 Chrome 的配置名对别的浏览器没有意义。配置文件必须以 `[xdl]` 开头,格式不对时 xdl 会直接报错,而不是悄悄用默认值。

## 保存位置与文件命名

gallery-dl 用它的默认目录结构,X 的文件是:

```
<output>/twitter/<用户名>/<推文ID>_<序号>.<扩展名>
```

yt-dlp 的模板是:

```
<output>/%(extractor_key)s/%(uploader_id,uploader|unknown)s/%(id)s_%(title).60B.%(ext)s
```

即 `<output>/<网站>/<上传者ID>/<视频ID>_<标题前60字节>.<扩展名>`,例如 `Youtube/@someone/abc123_标题.mp4`。

下载记录保存在 `<output>/.archive-gallery-dl.sqlite3` 和 `<output>/.archive-yt-dlp.txt`,下过的内容再次运行会直接跳过,所以对同一个账号的 media 页反复运行只会补下新内容。要重下就加 `--no-archive`,或删掉这两个文件。

## 快捷指令 / 一键下载

`macos/xdl-clipboard.sh` 会下载剪贴板里的链接,完成后弹通知,输出追加到 `~/Library/Logs/xdl.log`。它自己补了 PATH(`~/.local/bin`、`/opt/homebrew/bin`),快捷指令里能找到 pipx 装的 `xdl`。

先确认脚本的绝对路径:

```bash
echo ~/all-platform-downloader/macos/xdl-clipboard.sh
```

1. 打开「快捷指令」App → 菜单「快捷指令 → 设置 → 高级」→ 勾选「允许运行脚本」。
2. 新建快捷指令,命名如「xdl 下载」。
3. 添加操作「运行 Shell 脚本」,Shell 选 `zsh`,「传递输入」选「作为参数」,内容填上面的绝对路径加 `"$@"`:

   ```bash
   "$HOME/all-platform-downloader/macos/xdl-clipboard.sh" "$@"
   ```

   作为快速操作在别处选中含链接的文字时,选中的链接会作为参数传进来;没有输入,或输入里没有链接(比如在访达里选中了文件)时,下载剪贴板里的链接。
4. 打开快捷指令的详细信息(右侧 ⓘ 面板),勾选「用作快速操作」(服务菜单 / 访达),需要的话勾选「固定在菜单栏」。
5. 设置快捷键:在同一面板点「添加键盘快捷键」;或在 系统设置 → 键盘 → 键盘快捷键 → 服务 里找到这个快捷指令并设置。
6. 复制一个 X 链接,按快捷键或点菜单栏图标运行,等通知。

首次运行时 macOS 会弹出钥匙串提示:「security」想要访问钥匙串中的「Chrome Safe Storage」。输入登录密码并点「始终允许」,以后就不会再问。没反应或失败时看日志:

```bash
tail -n 50 ~/Library/Logs/xdl.log
```

用 Automator 也可以:新建「快速操作」,添加「运行 Shell 脚本」,内容同上。

## 升级

X 接口经常变,下载突然失败时先升级下载器:

```bash
xdl --update
```

升级 xdl 本身:

```bash
cd ~/all-platform-downloader && git pull && pipx install --force .
```

## 常见问题

**弹出钥匙串提示 / 报 keyring、decrypt 错误**
Chrome 系浏览器的 cookie 是加密的,gallery-dl / yt-dlp 会调用系统自带的 `/usr/bin/security` 去钥匙串里读「Chrome Safe Storage」(Edge、Brave 等名字不同),所以弹窗里写的是「security」而不是终端或快捷指令。弹窗时点「始终允许」。

点过「拒绝」的话,先再运行一次 xdl,通常会重新弹窗。如果不再弹:打开「钥匙串访问」,搜索「Chrome Safe Storage」,双击 →「访问控制」→ 点「+」,在文件选择框里按 `Cmd+Shift+G` 输入 `/usr/bin/security`,添加后存储更改。把终端或快捷指令加进去是没用的。

**Safari 读不到 cookie(Operation not permitted)**
给运行 xdl 的程序开权限:系统设置 → 隐私与安全性 → 完全磁盘访问权限,添加「终端」(或 iTerm),用快捷指令时也添加「快捷指令」。

**找不到浏览器配置(cookies database)**
检查 `-b` / `-p` 是否正确,Chrome 的配置名在 `chrome://version` 的「个人资料路径」末尾。

**快捷指令没反应,或通知「xdl 无法启动」**
多半是 `brew upgrade` 升级了 Python,pipx 里的环境失效了。重装一次:

```bash
pipx reinstall-all
```

**还是 401 / 403 / 下载为空**
依次检查:对应浏览器和配置里确实登录了 x.com;已开启「显示可能含有敏感内容的媒体」;运行 `xdl --update` 后再试。可以用 `--dry-run` 看实际用的是哪个浏览器配置。

提示「部分失败」时,说明这条推文里有的文件已经下好、有的没下成功,直接再运行一次,已下好的会被跳过。

**429 / rate limit**
被 X 限流了。等十几分钟再试,批量下载时别一次塞太多链接,整号 media 页尽量分开跑。

**会不会封号**
xdl 就是用你的登录态发请求,少量个人使用和你自己刷网页差不多。量大或担心的话,用小号放在单独的 Chrome 配置里(见「X 账号准备」)。

**cookie 安全**
cookie 等于你的登录凭据,不要导出发给别人,也不要提交到仓库(`.gitignore` 已排除 `cookies*.txt`、`*.cookies`)。
