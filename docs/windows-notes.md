# Windows 移植说明与维护笔记

[README](../README.md) 只讲"怎么播、出问题怎么办"。这里放**改它之前需要知道的东西**：
结构、实测读数、门禁怎么自证、以及每一条平台边界的技术原因。
逐轮的判断过程与被推翻的假设在 [windows-log.md](windows-log.md)。

## 目录结构

```
player.py            播放器主体：字符画、字幕、频谱、帧循环、键位分发
scenes.py            逐帧编排（纯 math，零平台调用，与上游一致）
lyrics.json          中英字幕时间轴（UTF-8，129 条）
spectrum.json        逐帧频谱数据
config.json          音频路径、时长、字幕偏移、（可选）宽字形名单
播放MV.cmd           双击入口：全屏
播放MV_窗口.cmd       双击入口：最大化窗口（留任务栏）
win\audioclock.ps1   Windows 音频时钟（WinRT Media Foundation）
win\winconsole.py    控制台 VT 模式、尺寸、按键线程、高精度定时器
win\get_song.py      取音频并做三段校验
win\launch.py        启动决策（三档窗口、缺音频时自动取）
win\calibrate.py     实测终端给每个字形画了几格（像素法）
win\screenctl.py     GDI 抓屏，供 calibrate 使用
win\launch.cmd       .cmd 只负责找到 Python；判断逻辑都在 launch.py，因为 cmd 在括号块里
                     是解析期就展开 %ERRORLEVEL%（拿到的是上一条命令的旧值），
                     而且引号与分号规则容易出事
tests\test_win_audio.py        音频时钟契约 21 项
tests\test_win_render.py       与上游逐帧等价 9 项
docs\windows-log.md            逐轮记录：实测数字、判据替换、被推翻的假设
docs\win-glyph-metrics.json    字形占格的机器可读测量结果
双语歌词.lrc / 双语字幕.srt     给人用的歌词与字幕，程序不读取
```

## 音频时钟的接缝

上游用 macOS 的 `AVAudioPlayer` 当时间源，接口是一条很干净的行协议，本副本**逐字保留**：

- 父 → 子（子进程 stdin，一行一条）：`play` / `pause` / `seek <秒>` / `volume <0..1>` / `quit`
- 子 → 父（子进程 stdout，约 64 Hz 一行）：`{"time":f,"duration":f,"playing":bool}`，
  出错时 `{"error":"..."}`
- 父侧保护：20 秒内等不到非零 `duration` 就报错；帧循环里 `last` 超过 2 秒没刷新报错；
  子进程退出报错。

额外多带的 `backend` / `pid` 两个键是**故意留的自证接口**：`player.Audio` 读到未知键会忽略，
而测试可以断言"回答我的那个进程确实是我起的那个"，而不是测试自己假装连上了。

## 三档窗口的实测几何

判据是**客户区**而不是窗口矩形——最大化窗口的边框本来就外扩 11 px 到屏幕外，
拿窗口矩形判会得出"遮住了任务栏"的假红。屏幕 2560×1600 @150%，工作区底边 1528。

| 用法 | 形态 | 实测客户区 |
| --- | --- | --- |
| `播放MV.cmd` | 全屏，盖住任务栏 | `[0,0,2560,1600]` |
| `播放MV_窗口.cmd` | 最大化，任务栏可见 | `[0,0,2560,1528]` ＝ 工作区 |
| `win\launch.cmd win` | 普通可拖动窗口 | `[65,76,1397,1012]`，`IsZoomed=False` |

窗口档那一行还配了一条独立佐证：抓屏看任务栏那条带有 36～44 个不同色块（在正常绘制），
而终端行只有 1 个（纯背景）。

## 音频从哪来：三段都必须真跑

`spectrum.json` 是照着**某一个具体录音**逐帧采的，字幕时间轴也对齐它，换音源就会错位。
上游不提交音频（`.gitignore` 里有 `/media/`），音频只内嵌在 Release 播放包里。
`win\get_song.py` 因此做三段校验，
**全过才落盘**（校验期间写在 `.build/` 的临时件上，`media/` 不会留下没验过的文件）：

| 段 | 判据 | 实测 |
| --- | --- | --- |
| 1 传输 | 下载的包必须匹配作者公布的 `SHA256SUMS.txt`；**取不到这条就直接失败**，不退化成"只信包内清单" | `world-execute-mv.pyz` 9,205,195 字节，`55043652a24c…` |
| 2 内容 | 解出的 mp3 必须匹配包内 `bundle-manifest.json` 的 SHA-256 | `media/song.mp3` 8,620,427 字节，`2da5fb306fc8…` |
| 3 时长 | 用**播放器同一套媒体引擎**读时长，与 `config.json` 相差 ≤ 0.5 秒 | 引擎 211.98365 s ／ 配置 211.906667 s，差 0.077 s |

第 3 段刻意不用 MCI：本机 MCI 打不开 MP3（见下面"平台边界"），用它当校验等于永远拿
"未验证"退出码 0。通过的包留在 `.build/cache/` 并配 `.verified` 摘要，复用缓存时仍要与
当期公布值一致。强制重取：`python win\get_song.py --force`。

## 本机实测读数

| 项 | 值 |
| --- | --- |
| 音频时钟发报频率 | 64 Hz（.NET 睡眠落在 15.6 ms 刻度；请求 90 Hz 即一个刻度，请求 17 ms 反而只有 32 Hz） |
| 暂停 / seek | 暂停时位置逐位冻结；暂停态 `seek 158.7` 回读 158.700000 且不自行起播 |
| 播放推进 | 位置增量与墙钟差 < 0.02 s |
| 音频就绪 | 2.45 s（冷启动 2.95 s）——这段时间画面还没开始画 |
| 8～10 秒实播 | 198～244 帧 / 24.3～24.8 fps / 最坏一帧 18.2～18.8 ms（预算 41.7 ms）/ 窗口 179×56 |
| 字形占格 | 34 个 East-Asian-Ambiguous 字形全部 1.0 格；控制组汉字 1.98 格；cell 14.2927 px |
| 控制台模式改动 | 输入模式 `0x1f7 -> 0x191`（关 QuickEdit / InsertMode / LineInput / Echo） |
| 听觉与画面 | 用户实听确认有声并验收画面 |

## 重跑门禁

```bat
C:\Python314\python.exe tests\test_win_audio.py      :: 21 项，缺音频会红而不是静默跳过
C:\Python314\python.exe tests\test_win_render.py     :: 9 项，与上游逐帧等价
wt.exe --fullscreen -d . C:\Python314\python.exe win\calibrate.py   :: 字形占格实测
```

`test_win_render.py` 的对照物钉在 commit `9d8e815`（SHA-256 `aac5c7b48f663013…`）的上游
`player.py`，只补两处让它能在 Windows 上 import（去掉 `termios` 导入、给 `read_text()`
加编码），改动量被断言为"恰好 8 行差异"，多一处就红；对照物缺失时自行从 git 取回并按摘要
复核，不允许静默 skip。**提交本仓库之后它仍读那个固定 commit**，不会退化成"拿我的文件跟
我的文件比"——这条在每次提交后都要重验一遍。

等价性扫描覆盖 0.5 s 步长到 `config` 时长之后 0.6 s（引擎实际报 211.98365），逐帧同时比
`plain()` 与 `ansi()`，合计 **426 帧 × 2 种序列化 = 852 次比较**。负对照做过：把 `─` 记成
2 格 → 424 帧里 19 帧报差、2 项转红，证明这把尺红得起来。

`win\calibrate.py` 会**覆写** `docs/win-glyph-metrics.json`，并把测量那一屏存成
`.build/calibrate-screen.png` 作为证据（`.build/` 不入库）。它的自检是内置的：ASCII 控制组
必须读 1 格、汉字控制组必须读约 2 格、两把标尺右边缘必须互差 < 半格，任一不满足就报
`BROKEN_INSTRUMENT` 并以退出码 1 结束。

## 平台边界与原因

- **MCI 不能放 MP3**：`MPEGVideo` 驱动注册为 `mciqtz32.dll`（QuickTime 包装器），未装
  QuickTime 时 `mciSendStringW` 打开 MP3 恒返回 err 277，与路径是否含非 ASCII 无关
  （`waveaudio` 驱动本身可用）。所以播放与时长校验都走 Media Foundation。
- **PowerShell 5.1 里 WinRT 类型要写全投影**：`[Windows.Media.Playback.MediaPlayer,
  Windows.Media.Playback,ContentType=WindowsRuntime]`；`MediaSource` 用静态
  `CreateFromUri`；`MediaPlayer` 只有 `Dispose()` 没有 `Close()`；
  `CommandManager.AutoPlay` 在本机投影里不可用，靠 `Play(); Pause()` 预载也能拿到时长且
  不漏音（位置停在 0）。
- **`[Console]::In` 是 `SyncTextReader`**，它的 `ReadLineAsync()` 在调用线程上阻塞——
  子进程会一帧都不发。必须用 `StreamReader([Console]::OpenStandardInput())`。
- **`timeBeginPeriod(1)` 救不了 PowerShell 的睡眠**（`Thread.Sleep(1)` 仍 15.46 ms），
  但能收紧 Python `time.sleep` 的抖动上界（23.89 → 17.97 ms）。
- **Windows Terminal 不回答 `ESC[6n`**（`msvcrt` / `os.read` / `ReadConsoleW` 三种读法实测
  都收不到），所以字形占格只能像素法测。
- **DPI 不感知的抓屏是左上裁片**：`GetSystemMetrics`/`BitBlt` 工作在缩放坐标，
  1707×1067 其实是 2560×1600 的左上角，画在第 44 行的东西根本不在图里。
  `screenctl` 导入时即声明 `SetProcessDpiAwarenessContext(-4)`。
- **中文 Windows 默认编码 cp936**：`Path.read_text()` 不带 encoding 读 UTF-8 中文字幕会直接
  `UnicodeDecodeError`（实测在 `lyrics.json` 第 76 字节）；stdout 被重定向成管道时同样是
  cp936，画 `♥ ◉` 会炸，所以非 tty 时显式 `reconfigure(encoding='utf-8')`。控制台 stdout
  走 `WriteConsoleW`，与代码页无关——因此**不要** `chcp 65001`、不要重开 `CONOUT$`，
  `.cmd` 文件也必须保持纯 ASCII（cmd 按控制台代码页解析该文件）。
- **`wt.exe` 的参数按空格切，且 `;` 是它自己的分隔符**：仓库目录名含 `;` `(` `)` 空格与
  em-dash，所以启动器一律 `wt -d .`（实测解析为调用者 cwd），命令行里只放无空格 token；
  本机 F 盘也拿不到 8.3 短名。
- **`closeOnExit` 只在退出码 0 时关标签页**：正常按 Q 退出会自动关窗；`taskkill` 或播放报错
  （码 1）时窗口留着——这也是为了让 `播放失败：…` 能被看见。

## 与 macOS 版的差异

保留行协议与全部画面逻辑，换掉三处平台绑定：音频时钟（AVFoundation → Media Foundation）、
终端输入（`termios`/`tty`/`select` → 控制台 API + `msvcrt` 工作线程 + 按键队列）、
尺寸与模式（`/dev/tty` → `GetConsoleScreenBufferInfo` + `SetConsoleMode`）。
`AudioClock.swift`、`run.sh`、`build-audio.sh`、`播放MV.command`、`运行单文件.command`
与 `tools/` 打包脚本已删除，历史在 `git log`。

## 未验证 / 未做

- 未验证：N 版 Windows（无媒体组件）的 MP3 解码路径；legacy conhost 下的实际观感
  （只改了取尺寸的顺序）。
- 未做：单文件 `.pyz` 的 Windows 包（`.pyz` 在 Windows 没有双击关联，收益低）；
  冷启动那约 2.5 秒无画面（要消掉得解耦"等时长"与"画首帧"，属于改结构）。
