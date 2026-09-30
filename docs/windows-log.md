# Windows 适配轮次记录（只追加，不重写）

判据：每条都要有实测数字或可复跑命令。被推翻的假设保留原文并标注推翻它的证据。

---

## 第一轮 · 2026-10-01 · 克隆 + 音频 + 输入 + 画面，全门禁过

### 做了什么

- `git clone` 上游 `yym8224961/world.execute-me-ascii` @ `9d8e815281a1`（18 个跟踪文件）。
  检出为 CRLF；先把 `player.py`/`README.md` 归一回 LF，并断言归一后的 `player.py`
  与上游 blob **逐字节相同**（sha256 `aac5c7b48f663013…`，17303 字节）才动手改。
- `win/get_song.py`：下载 v1.0.0 `world-execute-mv.pyz`（9,205,195 字节），先对官方
  `SHA256SUMS.txt`（`55043652a24c…`）再对包内 manifest 的每文件 SHA-256，解出
  `media/song.mp3`（8,620,427 字节，`2da5fb306fc8…`）。
- `win/audioclock.ps1`：WinRT `Windows.Media.Playback.MediaPlayer` 音频时钟，说与
  Swift 版完全相同的行协议（stdin `play|pause|seek|volume|quit`，stdout 每行 JSON）。
- `win/winconsole.py`：`SetConsoleMode` 开 VT、关 QuickEdit/InsertMode；尺寸按
  fd1 → fd0 → `GetConsoleScreenBufferInfo` → shutil 的顺序问，并把**是谁答的**记进报告；
  按键走 `msvcrt.getwch()` 工作线程 + 队列，方向键归一化成 ESC 序列，使 `player.py`
  的分发代码一行未改。
- `player.py` 就地改：`termios/tty/select//dev/tty/SIGHUP` 全删；三处 `read_text()`
  补 `encoding='utf-8'`；`cw()` 加 `AMBIGUOUS_WIDE` 旋钮（默认空）；`--backend none`
  给一个同接口静音时钟；`--report` 增 `size_source/host/backend/audio_ready_seconds`。
- 删除 macOS 专属：`AudioClock.swift`、`build-audio.sh`、`run.sh`、`播放MV.command`、
  `运行单文件.command`、`tools/build_bundle.py`、`tools/bundle_main.py`、
  `tests/test_bundle.py`（`git rm`，历史可回）。
- 新增 `播放MV.cmd`（纯 ASCII 内容，双击 → 全屏 Windows Terminal）。

### 实测数字

| 判据 | 读数 |
| --- | --- |
| 音频时钟契约测试 | 14/14 通过；发报 64 Hz；`quit` 后 PID 不再存活；happy path stderr 为空 |
| 与上游逐帧等价 | 9/9 通过；0.5 s 步长扫完 212 s，848 帧 `plain()` 与 `ansi()` 全等；6 种尺寸 × 5 种状态叠加矩阵 150+ 帧全等 |
| 等价性门禁能红 | 负对照：把 `─` 记成 2 格 → 424 帧里 19 帧报差异、字形表报差异，2 项转红 |
| 字形占格 | 34 个 Ambiguous 字形全 1.000；控制组 `中` = 1.98；cell_px 六批全为 14.2927 |
| 真机 8 s 实播 | 199 帧、24.83 fps、窗口 179×56（非回落值）、最坏帧 26.3 ms、末帧时间 68.015 |
| 工作树 | 跑完 `git status --porcelain` 条目数不变（13→13） |

### 被证伪的假设（都留了复验命令）

1. **「MCI 能放 MP3」——错。** 派生的设计 agent 报告 `mciSendStringW` + `type mpegvideo`
   可用且 position/length 天生毫秒。本机复验：MP3 一律 `open` 失败 err 277
   （"初始化 MCI 时发生问题"），且与路径是否非 ASCII 无关（ASCII 临时路径同样 277）。
   根因查注册表：`MPEGVideo` 驱动 = `mciqtz32.dll`，即 QuickTime 包装器，本机无 QuickTime
   运行时。`waveaudio` 驱动本身可用（WAV open/status/close 全 0）。
   → 音频后端整体换成 Media Foundation。**教训：它测试时本机根本没有 mp3 可测**（工作区
   当时是空的），这类"已实测"必须先问取证对象在不在。
2. **「`player.py` 只是缺模块，补上就能跑」——不完整。** 真正的第一个崩溃点在
   `Film.__init__` 的 `read_text()`：本机首选编码 cp936，UTF-8 的 `lyrics.json` 第 76
   字节直接 `UnicodeDecodeError`。与终端、音频无关，任何中文 Windows 上都会先炸这里。
3. **「PowerShell 能按 60 Hz 发报」——差一半。** `Start-Sleep 17` 实测 32.25 ms/次
   （.NET 睡眠落在 15.6 ms 刻度上，17 ms 要两个刻度）。`timeBeginPeriod(1)` 在本机
   对 .NET 睡眠无效（`Sleep(1)` 仍 15.46 ms），但对 Python 的 `time.sleep` 有效
   （17 ms 抖动上界 23.89 → 17.97 ms）。改法：请求 11 ms（一个刻度）→ 实测 64 Hz。
4. **「Windows Terminal 会回答 ESC[6n」——不会。** 三种读法（`msvcrt.getwch`、
   `os.read`、`ReadConsoleW`）在 3 s 窗口内都没收到光标位置报告。
   → 字形占格改用像素法（GDI 抓屏 + 行尾比对）。
5. **「抓屏抓到的是整屏」——第一版不是。** DPI 不感知进程的 `GetSystemMetrics`/`BitBlt`
   工作在缩放坐标里，1707×1067 的"整屏"其实是 2560×1600 的左上裁片，于是第 44 行
   画的东西根本不在图里，表现为"该有 7 个墨条只找到 6 个"。加
   `SetProcessDpiAwarenessContext(-4)` 后 6/6 批全对。
6. **派生 agent 说「WMPLib OCX 卡在 playState=9」** ——未复验。因为 MCI 整条路已废弃、
   WinRT 一次通过，没有再给它上场的机会；此条挂"未验证"，不作为任何结论的依据。

### 判据替换（记清楚换了什么尺）

- 等价性对照物原本打算"跑上游 player.py 比输出"——上游在 Windows 上 import 不了。
  换成：把上游源码 exec 进独立命名空间，且**断言它与上游 blob 的差异恰好是
  1 处 import + 3 处 read_text（diff 8 行）**，多一处就红；对照物缺失时从钉死的
  commit 重新 `git show` 并按 SHA-256 复核，不许静默 skip。
- 字形宽度原本打算用光标报告法；换像素法后，把"仪器自己可信吗"写成断言：
  ASCII 控制组必须读 1、汉字控制组必须读 1.85–2.15、两把尺（首末行标尺）右边缘必须
  相差 < 半格，任一不满足就 `BROKEN_INSTRUMENT` 并以退出码 1 结束。

### 待补 / 已知未做

- 单文件 `.pyz` Windows 包：未做（双击无关联，收益低）。
- N 版 Windows 的 MP3 解码路径：未验证（本机非 N 版）。
- 冷启动到出画约 2.9 s（等 PowerShell + 媒体打开）。要更短就得把"等时长"和"画首帧"
  解耦，属于改结构，这轮没动。
- 复跑命令见 `WINDOWS.md` 末尾。

---

## 第二轮 · 2026-10-01 · 补静音时钟的测试与收尾

- 发现自己写的文档承诺过 `--backend none`，但它一条测试都没有，且它的时钟到片尾仍报
  `playing=True`，会让 `player.py` 的收尾判据（`current>=duration-.05 and not playing`）
  永远等不到——真时钟会停，它不会。补了 `SilentBackendContract` 5 项（接口面、时长来自
  config、seek/play/pause、片尾必须停止声称在播、2 s 看门狗不被误触），并让 `tick()`
  在触顶时把 `playing` 置回 False。
- 最终门禁：`tests/test_win_audio.py` 19/19、`tests/test_win_render.py` 9/9（848 帧全等）。
- 清掉自己的临时件（`__pycache__`、探针脚本、5 MB 抓屏 BMP），保留 `.build/` 下的
  shotA/shotB/shotC 截图与两份 `--report` JSON 作证据；`media/` 与 `.build/` 均被上游
  `.gitignore` 覆盖，`git status --ignored=no` 只剩有意改动。
- 删除动作是 `git rm`（已入索引未提交）。是否提交由用户决定。

---

## 第三轮 · 2026-10-01 · 加窗口（非全屏）播放档

- 用户要"能看见底部任务栏"的版本。做法：把启动逻辑收进 `win\launch.cmd`（三档
  `full|max|win`），根目录留两个薄入口 `播放MV.cmd`（full）与 `播放MV_窗口.cmd`（max，
  最大化但保留标题栏/标签栏 ⇒ 任务栏可见）。不复制粘贴两份启动逻辑。
- `wt --maximized` 是否真留任务栏，用几何量：客户区 `[0,0,2560,1528]` == 工作区，
  任务栏条 72 px；抓屏该行 36 个不同色桶（任务栏在画），终端行 1 个（纯背景）。
  第一版判据用 `GetWindowRect` 误报"遮住任务栏"——最大化窗口的**边框**本来就外扩 11 px
  到屏幕外，必须比客户区（`GetClientRect` + `ClientToScreen`）。
- 自己破了自己的规矩：先往 `播放MV.cmd` 里写了中文注释，违反我自己在 WINDOWS.md 定的
  "cmd 文件保持纯 ASCII"（cmd 按控制台代码页解析该文件）。两个入口都重写为 ASCII。
- 一个没复现的异常：第一次窗口档抓屏拍到"已经在播的密集十六进制画面"，而它应当停在片头。
  受控复测（同样的 `cmd //c ... &` 调用方式，撒手 35 s）停在片头：PNG 64,218 字节、
  主体区亮样本 1941/176000（1.1%，稀疏片头特征）。判为"我先前那次 kill+WM_CLOSE 拆窗
  留下的串台"，**不是**启动器会自己起播；但这条我只做到"不复现"，没做到"解释清楚"，
  所以留在记录里。
- 顺带：我第三次写出 `os.environ['TEMP'] / 'x'`（str 除以 str）。这类"凭手感写的路径拼接"
  应当固定用 `pathlib.Path(os.environ['TEMP']) / 'x'`。

---

## 第四轮 · 2026-10-01 · 三路独立复核 + 我自己一条新读数

用户视觉验收通过后要求"再验收一遍双重保险"。做法：三路互不重叠 charter 的只读复核
（① player.py 与上游的契约/等价性、② 音频时钟与进程生命周期、③ 文档每条断言↔实物对账），
我自己走它们被禁止的运行时/像素通路。**每条复核结论我都自己复验后才落地。**

### 复核抓到、我确认成立并已修的

1. **`open_audio()` 在 `try:` 之外**（①②都抓到）。时钟起不来时 `audio` 根本没绑定，
   `finally` 里的 `close()/console.leave()/timer.release()` 全跳过 → 留孤儿 powershell，
   且控制台模式不回滚。改成：`Audio.__init__` 自己负责收尸（构造失败即 terminate+关管道+raise），
   `run()` 里 `audio=None` 并把开启挪进 try。新增用例：喂一个假 mp3，断言 `Audio()` 抛错后
   **那个 PID 已经不在**（为此错误消息必须带 pid，两处 raise 都补了）。
2. **运行时错误通道被我做没了**（①②都抓到）。上游 Swift 在 `player.play()` 失败时会发
   `{"error":"Audio output unavailable"}`；我的 PS 版五个 `Fail` 全在发报循环之前，
   于是 `player.py` 里那句 `if audio.error` 成了死支，设备中途失效=画面冻住不说话，
   而 WINDOWS.md 写着"不会静默无声"。补：循环整体 try/catch 发 error、`play` 后 1.5 s
   没进 Playing 判定为无输出、位置非有限值也发 error。
3. **`get_song.py` 的校验链有两个静默降级口**（②③都抓到）。`SHA256SUMS.txt` 拿不到对应条目时
   `expected=''`，于是"下载完整性"这一腿被整段跳过、缓存被无校验信任、而 verdict 照样 OK。
   改成：拿不到公布摘要就硬失败；缓存必须配 `.verified` 摘要文件且与当期公布值一致。
4. **时长交叉校验是死的**（①②③都抓到，我自己第一轮就看到 `mci_error: open failed: 277`
   却没处理它——这是本轮最该记的一笔）。第三段改用播放器同一套 Media Foundation 引擎实测，
   现在报 `engine_duration_s: 211.98365`、差 0.077 s，且校验通过才落盘（失败时写的是
   `.build` 里的临时件，`media/` 不会留下没验过的音频）。
5. **14/19 条音频用例可以静默 skip 而整体报 OK**（①抓到，正合我自己那条"防空绿"记忆）。
   去掉全部 `skipIf`，换成一条"缺 `media/song.mp3` 就红并给命令"的用例。
6. **`size()` 把可能说谎的那一路排在前面**（①抓到）。`os.get_terminal_size` 给的是
   `dwSize`（缓冲区，conhost 下含回滚行），视口应是 `srWindow`。改成先问 `srWindow`。
   现在报告里 `size_source = GetConsoleScreenBufferInfo(srWindow)`。
7. **子进程 stderr 在生产路径上没人读**（①抓到）：4 KB 就能把时钟噎住并被误判成"时钟停止更新"。
   测试里我本来就有 `_drain_stderr`，生产反而没做——补上，并保留最后 6 行用于报错。
8. **`--backend none` 仍然强制要求 mp3 存在**（①③抓到），等于把"只看画面"这个用途堵死；
   同时 `Silent` 忽略传入路径、自己重读 config。改成：该档跳过文件检查，`Silent(duration)` 显式收时长。
9. **一条我自己写的用例是空转的**（①抓到）：`test_ambiguous_knob_is_off_by_default` 断言的集合
   只有 `main()` 会填，测试从不走 `main()`，永远真。换成走 CLI 的行为断言：默认必须等于窄档、
   宽档必须至少在一帧上改变画面、并直接断 `cw()` 对名单里字形的读数。
   **它第一次跑就红了**——但红得是我错：宽字形是"盖掉邻格"而不是"把整行推走"，
   所以 `plain()` 在部分帧上逐字节不变（t=190 才看得出差异）。测试按真实语义重写后过。
10. 其余小项：launch 的批处理逻辑整体搬进 `win/launch.py`（`%ERRORLEVEL%` 在括号块里是解析期展开、
    `wt.exe` 之后没有 errorlevel 检查、LF-only `.cmd` 的标签风险一并消掉）；`Clock.last` 不再把
    启动耗时算进 gap（否则慢机器会假红）；扫描上界延到 config 时长 +0.6 s；`calibrate` 的字形名单
    改为直接问 `player.ambiguous_used()`（两份"从源码扫"的清单会漂）；`Console.notes` 与
    `write_png` 从"写了没人读"变成报告字段与证据产物；`close()` 补 kill 兜底并关三条管道；
    一次取多行命令（原来 seek+play 要吃两帧）。

### 我自己新加的一条读数（复核方被禁止跑运行时）

系统音频音量表（Core Audio `IAudioMeterInformation`）取不到：`Activate` 返回 E_NOINTERFACE，
两次尝试（含 CLSCTX_ALL）都没打通，**放弃**，没有拿它当结论用。
改用窗口几何与退出码两条能量化的：`full` 客户区 `[0,0,2560,1600]` 盖住任务栏、
`max` `[0,0,2560,1528]` 正好等于工作区、`win` `[65,76,1397,1012]` 且 `IsZoomed=False`；
正常收尾（码 0）窗口自动关、报错收尾（码 1）窗口留着。

### 复核里我推翻或暂缓的

- ①说 `player.py:322` 那条"位置回到 0 视为播完"的分支在 MF 下已失效，判为 cosmetic **保留**：
  它是上游收尾语义的一部分，删它属于动画面之外的行为，收益是零风险是非零。
- ①说 `min(h,85)` 能挡住畸形缓冲区高度——**不成立**（9999 行会被夹成 85 行照画），
  所以第 6 条按"换数据源"修而不是依赖这个上限。
- ③说"整轮改动一行都没提交"是 blocking：这是**已授权的用户决定**（我上一轮已说明删除只入索引），
  不是缺陷；但它的措辞建议成立，README/WINDOWS 已改成"已 `git rm` 入索引、尚未提交"。
- ③说"至少 64 列"差一（实测 64 列出提示画面、65 列正常）：成立，已改并注明是上游行为。
- ③说我记录里 `55043652a240…` 这个摘要前缀是错的：成立，官方值是 `55043652a24c…`，
  我凭手感抄错了一位（同一条记忆里就写着"凭记忆写短 hash"会咬人）。已在原文处改正并留此说明。

### 本轮结束时的门禁

`tests/test_win_audio.py` 21/21（无跳过）、`tests/test_win_render.py` 9/9
（426 帧 × `plain()`+`ansi()` 两路比较，852 次）、`win/get_song.py --force` 三段全绿、
10 秒真机实播 244 帧 / 24.32 fps / 最坏帧 18.8 ms / 179×56 / `size_source` 为视口读数、
`console_mode_changes = ['input mode 0x1f7 -> 0x191']`。

### 仍然没验的（别当已验）

- **声音是否真的从喇叭出来**：这是用户的耳朵，不是我的仪器；音量表那条路我没打通。
  （**已关闭**：2026-10-01 第五轮用户耳验"有声音，而且画面也不错"。见下方第五轮。）
- N 版 Windows 的 MP3 解码路径；legacy conhost 下的实际观感（只改了取尺寸的顺序）。
- 冷启动 2.45–2.95 s 无画面：要消掉得解耦"等时长"与"画首帧"，属于改结构，仍未做。

### 补记（同一轮内）：我那条修法是半对的，重跑才暴露

按①的第 7 条把 `Clock.last` 改成"就绪后再计时"之后，用例**仍然红**（2.05–2.66 s）。
没有当成抖动放过：单独测子进程 20 s，55 Hz、**零个** >0.2 s 的间隔 → 停滞不在子进程。
再用同一 Clock 打时间轴，发现 `max_gap`(2.44 s) 恰好等于就绪耗时(2.45 s)：
读线程在"等到时长"之前就把这段启动间隔记进了 `max_gap`，我只重置了 `last`，没管已入账的 `max_gap`。
改成显式的 `counting` 开关（见到时长之前不记间隔），并补一条负对照自证这把尺还活着：
实测 `max_gap=38 ms`、64 Hz，既不是恒 0，也不再被启动污染。

顺带确认父进程没有同类问题：`Audio.__init__` 的等待循环是被"带时长的那条消息"结束的，
那一刻 `last` 刚被刷新，所以帧循环里的 2 s 看门狗量的不是启动段。这条区别值得写下来，
否则下一次还会想当然。

---

## 第五轮 · 2026-10-01 · 听觉与画面由用户验收，最后一项未验清单关闭

用户回报：**有声音，画面也不错**。

- 这一条按结构就只能由用户的耳朵判：我试过系统音频表（`IAudioMeterInformation`），
  `Activate` 两次（含 CLSCTX_ALL）都返回 E_NOINTERFACE，仪器没打通，所以我当时写的是
  "未验证"而不是"通过"。现在它变成**已验证**，取证方式是用户实听，不是我的读数。
- 顺带确认：默认音量 0.75 走的是播放器内部音量（`player.Volume`），
  所以"有声音"同时说明 `volume` 命令链与 Core Audio 输出通路是通的。
- 仍未验的只剩两条，都不影响交付：N 版 Windows 的 MP3 解码路径（本机非 N 版）、
  legacy conhost 下的实际观感（只改了取尺寸的顺序，未在 conhost 里看过）。
- 状态：改动**仍未提交**（删除已 `git rm` 入索引，新文件未跟踪），等用户决定。

---

## 收尾 · 2026-10-01 · 提交，并复验"对照物没有变成被测物"

- 用户授权后提交为本地 commit `502c986`（父提交 `9d8e815`，上游）。25 个路径：
  15 新增 / 2 修改 / 8 删除。`media/song.mp3` 与 `.build/`（含 9.2 MB 缓存包）
  被上游 `.gitignore` 覆盖，未进库；工作树提交后干净。
- **提交后必须重验的一件事**：等价性对照物钉在 `9d8e815`，若它改读 HEAD 就会拿
  "我的 player.py" 和 "我的 player.py" 比，全绿而毫无意义。做法：删掉
  `.build/pristine/player_upstream.py` 让用例自愈重取，再跑一遍 →
  取回的是 `aac5c7b48f663013` / 17303 字节（上游），当前被测文件是
  `a3096810c13a243f` / 25403 字节，**两者不同**，9/9 仍过。
- 未做（有意）：单文件 `.pyz` Windows 包；N 版 Windows 与 legacy conhost 的实测。
