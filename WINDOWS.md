# Windows 播放说明

本仓库已就地改造为 **Windows 版**：动画、字幕、频谱数据与原仓库逐帧一致（见文末验证），
只把 macOS 专属的音频时钟、终端输入和启动脚本换成了 Windows 的实现。原
`AudioClock.swift`、`run.sh`、`build-audio.sh`、`*.command` 与 `tools/` 打包脚本已 `git rm`
（**删除只进了索引，尚未提交**；新文件也还没提交，是否提交由你决定）。

## 怎么播

两个双击入口，选一个（判断逻辑都在 `win\launch.py`，`.cmd` 只负责找到 Python）：

| 文件 | 形态 |
| --- | --- |
| `播放MV.cmd` | **全屏**（盖住任务栏，最沉浸） |
| `播放MV_窗口.cmd` | **最大化窗口**：保留标题栏与标签栏，**底部任务栏可见** |

出现片头后按 **空格** 开始。播放中随时 `Alt+Enter` 在"全屏 ↔ 窗口"之间切换（Windows Terminal
自带键位），`Ctrl+Shift+加号/减号` 调字号换更多行。

想要普通可拖动大小的窗口：`win\launch.cmd win`（或把 `播放MV_窗口.cmd` 末行的 `max` 改成 `win`）。
本机实测三档：`full` 客户区 `[0,0,2560,1600]`（盖住任务栏）、`max` 客户区 `[0,0,2560,1528]`
（正好等于工作区，任务栏 72 px 未被遮）、`win` 客户区 `[65,76,1397,1012]` 且 `IsZoomed=False`。

首次运行会自动取音频，**三段校验全部实跑才落盘**：

1. 下载的 `world-execute-mv.pyz`（9,205,195 字节）必须匹配作者公布的 `SHA256SUMS.txt`；
   拿不到这条就**直接失败**，不再退化成"只信包内清单"。
2. 解出的 `media/song.mp3`（8,620,427 字节）必须匹配包内 `bundle-manifest.json` 的 SHA-256。
3. 用播放器同一套媒体引擎读它的时长，必须与 `config.json` 的 211.906667 相差 ≤ 0.5 秒
   （实测引擎报 211.98365，差 0.077 秒）。

第 3 段以前用的是 MCI，而本机 MCI 打不开 MP3（见"已知边界"），所以那一腿当时是死的。
校验通过的包会留在 `.build/cache/` 并配一个 `.verified` 摘要文件，第二次运行走缓存
（`package_origin: cache`），但缓存仍要与当期公布的 SHA256SUMS 相符才用。

仓库本身不含音频，而 `spectrum.json` 是照着这首歌逐帧采的，换音源会对不上。

也可以手动跑：

```bat
C:\Python314\python.exe player.py
C:\Python314\python.exe player.py --start 158.7 --autoplay
```

## 键位

| 键 | 作用 |
| --- | --- |
| 空格 / 回车 | 开始 / 暂停 |
| ← / → | 后退 / 前进 5 秒 |
| R | 从头播放 |
| 1 – 5 | 跳五个章节（创建 / 献出自我 / 离开 / 失控 / 困于爱） |
| , / . | 上一句 / 下一句 |
| [ / ] | 字幕提前 / 延后 0.1 秒 |
| + / - | 音量 |
| H | 帮助 |
| Q / Esc | 退出 |

推荐全屏。终端至少 **65 列 × 24 行**（最后一列留给防自动换行，64 列会触发提示画面——
这条是上游行为）。本机全屏实测 **179 列 × 56 行**。

## 排障参数

```bat
player.py --backend none            :: 不出声，只放画面；此档不需要 media/song.mp3
player.py --snapshot 159.85 --plain :: 不开终端也能看某一帧
player.py --report f.json --stop-after 68 --autoplay --start 60
```

`--report` 记下：帧数、真实窗口尺寸、**尺寸是谁报的**、最坏一帧渲染耗时、音频就绪秒数、
本次对控制台模式做了什么改动（`console_mode_changes`）、以及生效的宽字形名单。

## 本机实测到的数

| 项 | 实测值 |
| --- | --- |
| 音频时钟发报频率 | 64 Hz（PowerShell 睡眠落在 15.6 ms 刻度，请求 90 Hz 即一个刻度） |
| 时长读数 | 引擎 211.98365 s，`config.json` 记 211.906667 s，差 0.077 s |
| 暂停时位置 | 相隔 0.7 s 两次读数逐位相同 |
| 暂停态 seek 158.7 | 回读 158.700000，且不自行起播 |
| 播放推进 | 位置增量与墙钟差 < 0.02 s（两次独立读数的误差界约 16 ms） |
| 音频就绪耗时 | 2.45 s（冷启动可到 2.95 s；这段时间画面还没开始画） |
| 10 秒实播 | 244 帧 / 24.32 fps，最坏一帧 18.8 ms（预算 41.7 ms），窗口 179×56 |
| 尺寸来源 | `GetConsoleScreenBufferInfo(srWindow)`（视口，不是可能含回滚行的缓冲区） |
| 控制台模式 | 输入模式 `0x1f7 -> 0x191`（关掉 QuickEdit / InsertMode / LineInput / Echo） |
| 34 个 Ambiguous 字形占格 | 全部 1.0 格；控制组汉字 1.98 格 |
| 听觉与画面 | 用户实听确认有声（默认内部音量 0.75）并验收画面 |
| 失败启动不留孤儿 | 喂一个假 mp3，`Audio()` 抛错且该 powershell PID 已不在 |

## 与 macOS 版的差别

- 音频后端：AVFoundation → **Windows Media Foundation**（`win/audioclock.ps1`，
  WinRT `Windows.Media.Playback.MediaPlayer`）。**行协议完全不变**；`Audio` 类除了换启动
  命令，还加了新进程组、UTF-8 解码、把就绪上限从 8 秒放宽到 20 秒、以及就绪耗时打点。
- 音量：仍是播放器内部音量（`player.Volume`），不动系统音量、不影响别的应用。
- 单文件包（`.pyz`）这版没做：Windows 下 `.pyz` 没有双击关联，做了也用不上。
- macOS 那条路不再保留，跨平台分支都删了。

## 已知边界

- **MCI 不能放 MP3**：`MPEGVideo` 驱动在本机注册为 `mciqtz32.dll`（QuickTime 包装器），
  没装 QuickTime 运行时，`mciSendStringW` 打开 MP3 恒返回 err 277，与路径是否非 ASCII 无关。
  所以时长校验、播放都走 Media Foundation。
- **别在 legacy conhost / VS Code 终端里跑**：程序会先往 stderr 提示宿主不是 Windows
  Terminal。它仍能画，但 `\x1b[?1049h`（备用屏）与光标显隐在别的宿主上还原得不一样。
- **音频设备中途失效会明确报错**：`play` 发出后 1.5 秒内没进入 Playing、或媒体引擎抛异常、
  或报出非有限的时长，子进程都会发 `{"error":...}` 并以非零码退出，父进程转成
  `音频引擎报错：…`；不再是"画面冻住、什么也不说"。
- **强杀进程会留下一个全屏窗口**：本机 Windows Terminal 默认配置下，退出码 0 才自动关标签页
  （实测：正常 `--stop-after` 收尾 → 窗口自动关；`--audio` 指向不存在的文件 → 退出码 1，
  窗口留着让 `播放失败：…` 被看见）。`taskkill` 同理。
- **N 版 Windows**（无媒体组件）会打不开 MP3；本机是 `CoreCountrySpecific` 正常版，
  N 版路径未验证。
- 目录名 `world.execute(me); —ascii` 里有分号、括号、空格和 em-dash。启动器因此一律
  用 `wt -d .` 的相对路径，不把仓库绝对路径拼进命令行（`wt` 用 `;` 分隔自己的参数）。
  本机 F 盘拿不到 8.3 短名，所以这条路是唯一稳的。

## 重跑验证

```bat
C:\Python314\python.exe tests\test_win_audio.py      :: 音频时钟契约（21 项，缺音频会红而不是跳过）
C:\Python314\python.exe tests\test_win_render.py     :: 与上游逐帧等价（9 项）
wt.exe --fullscreen -d . C:\Python314\python.exe win\calibrate.py   :: 字形占格实测
```

`test_win_render.py` 的对照物是钉在 commit `9d8e815`（SHA-256
`aac5c7b48f663013…`）的上游 `player.py`，只补两处让它能在 Windows 上 import：去掉
`termios` 导入、给 `read_text()` 加 `encoding='utf-8'`。改动量被断言为"恰好 8 行差异"，
多一处就红；对照物缺失时自己从 git 取回并按摘要复核，不允许静默跳过。

扫描范围覆盖到 `config.json` 时长之后 0.6 秒（引擎实际报 211.98365），逐帧同时比
`plain()` 与 `ansi()`。

`win\calibrate.py` 会把结果**覆写**进 `docs/win-glyph-metrics.json`（默认行为，非只读），
并把测量那一屏存成 `.build/calibrate-screen.png/.bmp` 作为证据。
