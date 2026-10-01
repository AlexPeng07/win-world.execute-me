# world.execute(me); —ascii （Windows 版）

Mili《[world.execute(me);](https://github.com/yym8224961/world.execute-me-ascii)》的
**终端字符动画 MV**：整个画面是 Python 画的 ANSI 字符，音频驱动时间轴，中英字幕与频谱条
跟着音频走。改编者AlexPeng07，改编自 yym8224961/world.execute-me-ascii，本副本只做 Windows。

## 三步播起来

1. **双击 `播放MV.cmd`** —— 自动打开全屏 Windows Terminal。
   想留着底部任务栏就双击 **`播放MV_窗口.cmd`**（最大化窗口，仍带标题栏）。
2. 首次运行会自己下载官方发布包（约 9.2 MB）取出内嵌音频并**三段校验**，几秒钟；
   之后完全离线可播。
3. 出现片头后**按空格**开始。

要求：Windows 10/11、Python 3.9 以上（本机 3.14.4）、Windows Terminal。**不需要 pip 装任何
东西，不需要管理员权限。** 若你的 Python 不在 `C:\Python314\`，改 `win\launch.cmd` 里 `PY=` 一行。

命令行方式（参数一样能用）：

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
| 1 – 5 | 跳章节：创建 / 献出自我 / 离开 / 失控 / 困于爱 |
| `,` / `.` | 上一句 / 下一句 |
| `[` / `]` | 字幕提前 / 延后 0.1 秒 |
| `+` / `-` | 音量 |
| H | 帮助 |
| Q / Esc | 退出 |

播放中 `Alt+Enter` 切换全屏/窗口，`Ctrl+Shift+加号/减号` 调字号换更多行
（Windows Terminal 自带键位）。画面至少 **65 列 × 24 行**；本机全屏实测 179 × 56。

## 它长什么样

![world.execute(me);](docs/images/mv-cover.png)

## 出问题了

| 现象 | 怎么办 |
| --- | --- |
| 提示"当前终端宿主是 console / vscode…" | 不在 Windows Terminal 里跑。改用双击入口 |
| 画面只占左上角一小块 | 终端窗口小于 65×24，那是程序主动画的提示画面。放大窗口或 `Ctrl+Shift+减号` 缩字号 |
| 按空格没声音 | 屏幕上有 `音频引擎报错：…` 就照它说；没有就去系统音量里看这个应用的会话音量（`+/-` 调的是播放器内部音量，不动系统音量） |
| 退出后留一个全屏黑窗 | 正常按 Q 会自动关。`taskkill` 或播放报错退出时窗口留着，是为了让你看见 `播放失败：…` 那句话 |
| 卡在片头几秒没反应 | 首次运行在下载并校验音频；之后每次启动也有约 2.5 秒等媒体引擎就绪 |

排障用的三个开关：

```bat
player.py --backend none             :: 不出声，只放画面（这一档不需要音频文件）
player.py --snapshot 159.85 --plain  :: 不开终端也能看某一帧
player.py --report .build\f.json --start 60 --stop-after 68 --autoplay
```

`--report` 写出的 JSON 会记下帧数、真实窗口尺寸、**尺寸是谁报的**、最坏一帧耗时、
音频就绪秒数、以及对控制台模式做了哪些改动——先跑一遍看这份文件，比猜快。

## 来历与版权

- **改编自**：<https://github.com/yym8224961/world.execute-me-ascii>，
  移植基线是上游 commit `9d8e815281a104ccb648ec2f2df88cd9f0cb8c12`。
  画面、字幕、频谱与上游**逐帧等价**（有门禁盯着，见下）。
- **原曲与歌词**：Mili《world.execute(me);》，版权归原权利方。本仓库是个人学习与备份用途的
  改编，不发布音频、不对任何第三方素材授予额外许可。
- **音频**：仓库不含音频，运行时从上游 Release v1.0.0 的播放包里解出作者内嵌的那一份，
  落在被 `.gitignore` 挡住的 `media/song.mp3`。必须是这一份，因为 `spectrum.json` 是照着
  它逐帧采的，换音源就会错位。

## 想改它，或想知道为什么这么定

| 文件 | 里面是什么 |
| --- | --- |
| [docs/windows-notes.md](docs/windows-notes.md) | 目录结构、音频时钟的行协议、三档窗口的实测几何、三段校验的具体哈希、实测读数、平台边界与原因（为什么不是 MCI、为什么 `.cmd` 必须纯 ASCII……）、与 macOS 版的差异、未验证清单 |
| [docs/windows-log.md](docs/windows-log.md) | 逐轮记录：做了什么、数字、判据替换、**被推翻的假设** |
| [docs/win-glyph-metrics.json](docs/win-glyph-metrics.json) | 字形占格的机器可读测量结果 |

改完至少跑这两套（第二条会拿钉死的上游源码做逐帧对照，所以它自己不能坏）：

```bat
C:\Python314\python.exe tests\test_win_audio.py      :: 音频时钟契约 21 项
C:\Python314\python.exe tests\test_win_render.py     :: 与上游逐帧等价 9 项
```
