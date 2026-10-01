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

---

## 收尾第二轮 · 2026-10-01 · 工作区整理、文档合一、死代码清除

- **文档合一**：`WINDOWS.md` 删除，内容并入 `README.md`，README 重写为唯一的 Windows 文档
  （上游出处与 commit、双击用法、键位、三档窗口、音频三段校验、目录结构、排障表、
  实测数、重跑门禁、已知边界、版权）。上面几处提到 `WINDOWS.md` 的条目是**当时的事实**，
  该文件现已不存在——按历史口径保留，不改写。
- **`.gitignore` 按本机重写**：删掉 macOS/已消失的东西（`.DS_Store`、`/audio-clock`、`dist/`、
  `*.log`、`*.mp4`、`*.jpg/jpeg`、`*.zip`），保留并加注说明真正需要的
  （`.build/`、`/media/` 与音频扩展名、`*.pyz`、`*.png` + 封面单行放行），
  补 Windows 自身落在目录里的东西（`Thumbs.db`、`Desktop.ini`、`$RECYCLE.BIN/`、`*.lnk`）。
  规则改成一句话：**只忽略"跑出来的"和"受版权的"**。
- **清中间件**：删 `.build/` 下已用完的验证产物（shotA/B/C 的 5 张 png 与 4 份报告 JSON、
  `close_test.json`、`final.json`、`wt.json`）与两份没人读的 upstream 副本
  （`lyrics_upstream.json`、`scenes_upstream.py`，删前 grep 确认零引用）。
  **保留** `.build/pristine/player_upstream.py`（等价性对照物）与 `.build/cache/`
  （`get_song` 的可用缓存，且缓存命中路径本身是被测过的）。
- **死代码**：`player.py` 里 `TAU = math.tau`（唯一引用就是定义）连带 `math` 导入、
  `ESC = '\x1b['`、`RED`（只在解包元组里出现，全仓零引用）一并删除；
  删前用 AST 扫过 win/ 与 tests/ 的全部函数与类，除 unittest 测试类（由 runner 按名发现）
  外无未引用定义；`screenctl` 里早先删掉的 `brightness_rows`/`ink_columns` 确认已不存在。
- 三条判据的自证：删死代码后 `tests/test_win_render.py` 仍 9/9、852 次比较与上游逐字节相同
  （证明删的确实与画面无关）；AST 复扫 `imported but unused` 为空；
  `.gitignore` 重写后用 `git check-ignore -v` 复核 `media/song.mp3` 与
  `.build/cache/world-execute-mv.pyz` 仍被挡住。

### 收尾补记 · 又拆掉两处我自己加的东西

- `win/launch.py` 的 `--player-arg` 透传：实测 `--player-arg --autoplay` 会被 argparse
  当成"缺参数"而直接退出（以 `-` 开头的值必须写 `--player-arg=…`）。它没进文档、没有别的调用方，
  属于我多加的功能，**删**，而不是给它写一条更别扭的用法说明。
- `screenctl.write_bmp` 与 calibrate 里的 BMP 落盘：12 MB 的 BMP 与 19 KB 的 PNG 存的是同一帧，
  而 PNG 编码器的正确性已经由"我真的打开看过四张抓屏"证明过，BMP 只是冗余。删函数 + 删证据字段，
  `docs/win-glyph-metrics.json` 的 `grab` 现在只指一个真实存在的 png。
- 删完复跑同一台同一字体：`ALL_NARROW / self_check ok / 34 个字形 / 控制组 1.98 /
  cell_px 六批恒 14.2927`，与删除前逐项一致；真机 8 秒实播 198 帧 / 24.73 fps / 最坏帧 18.2 ms；
  `win\launch.cmd max` 起窗口客户区 `[0,0,2560,1528]`，任务栏未被遮。

---

## 第六轮 · 2026-10-01 · README 分层（首页 vs 工程档案）

- 用户只说"优化 README"，追问方向时未选，按既定习惯自己定一个并讲清取舍：
  **把 README 收成项目首页，工程细节整体下沉到新文件 `docs/windows-notes.md`**。
  诊断依据：旧 README 184 行 / 12 个平级章节里有一半是维护者内容（实测数、重跑门禁、
  平台边界、目录结构、与 macOS 差异），而 3 MB 封面图压在首屏，"怎么播"被推到折叠线以下。
- 动手前先确认 README **不是任何门禁的输入**：`grep -rn README --include=*.py --include=*.ps1
  --include=*.cmd --include=*.json` 在代码侧零命中（含变量拼路径的写法也一并扫了）。
- 结果：README 184→91 行（10.8 KB→4.7 KB），章节 12→7，首屏就是"三步播起来"，
  封面图移到"它长什么样"。新 README 只留：三步 / 键位（改成单栏两列，去掉撑歪列的长格）/
  画面 / 出问题怎么办 / 来历与版权 / 想改它看哪里。
- **"信息一条不丢"是当判据来验的，不是当口号说的**：把旧 README 里所有反引号标识符
  （74 个）与数字（55 个）逐个在新 README ∪ notes 里查存在性。第一轮抓到 4 处真丢：
  `%ERRORLEVEL%` 的取舍理由、"426 帧 × 2 = 852 次比较"这个证明量级、本机 Python 3.14.4、
  `.gitignore` 里的 `/media/` 模式——全部补回。复扫只剩 2 项非丢失：
  `tests/test_win_render.py`（新文件用反斜杠写法，同一文件）与 `24.32`
  （被有意写成区间 24.3～24.8）。
- 结构自检：两份文件代码块配对、表格列数一致、无断头表格；内链按**各自所在目录**解析后
  6 条全部命中（第一版自检按仓库根解析，误报两条"死链"，是尺子错不是文件错）。
- 顺手把两句只在当时语境成立的话移出 README："第 3 段以前用的是 MCI…现在换成活的"
  （历史，本就在上一轮记过）与"有人把 encoding 改回去了"（假设性指责，改成事实句）。

## 第七轮 · 2026-10-01 · 发布前：gitignore 复核、安全检查、README 一行并入上一提交

- 用户要去发 GitHub，四件事：`.gitignore` 对不对、安全性、README 新加的一行并入上一次提交、
  上线前核验。
- **`.gitignore` 的判据不是"读一遍觉得对"，是干净房重跑 `git add`**：在 `.build/ignore-lab`
  `git init` 一份空仓库、只放这份 `.gitignore`，铺出 `media/song.mp3`、`.build/cache/*.pyz`、
  `__pycache__/*.pyc`、`Thumbs.db`、`setup.lnk`、`stray.wav`、根目录 `root-shot.png`、
  `docs/other-shot.png` 与被放行的 `docs/images/mv-cover.png`。`git add -A --dry-run` 只收
  `.gitignore / mv-cover.png / player.py / tests/t.py / 双语歌词.lrc`——音频、发布包、抓屏证据、
  Windows 自身的 junk 一个没进来，`!` 例外确实生效。这条值得记是因为
  `git check-ignore -v` 对**否定模式**也返回 0，只看 rc 会把"放行成功"读成"被忽略"。
  再交叉核 `git ls-files -i -c --exclude-standard`（被跟踪又同时被忽略）为空。
- 历史面：全量枚举"曾经出现在任何提交里的路径"，无任何音频/发布包扩展名；
  `git count-objects -H` 报 size-pack 6.05 MiB（大头是上游那两个 PNG 的历史版本）。
- **我自己差点交出一条假绿**：第一版历史扫描把 `git cat-file --batch $(cat blobs)` 重定向落盘，
  结果是 **0 字节语料**，于是所有模式都"命中 0 次"——看着全干净，其实尺子量的是空集。
  改法：先证实语料非空（8,061,811 字节），再加**必须命中的阳性对照**
  （`System32`=4、`Windows.Media.Playback`=11、`world.execute`=195）；同一批对照也顺带证了
  上一版 `git grep` 里 `[/\\]+` 与 `\\+` 不是一回事（后者漏了单反斜杠写法）。
- 真找到的两处：
  1. `docs/win-glyph-metrics.json` 的 `grab.png` 是本机绝对路径
     `F:\AllProjects\playground\world.execute(me); —ascii\.build\calibrate-screen.png`，
     而证据文件本来就在被忽略的 `.build/` 里——它对读者唯一的增量信息是那台机器的目录结构。
     生产端 `win/calibrate.py:130` 改 `png.relative_to(ROOT).as_posix()`，测量值一行没动；
     改完用 `json.load` 与生产端重算的字符串逐位相比对，并确认 `.build/calibrate-screen.png`
     既是新值也真的存在。测试侧无人读这个键（`git grep win-glyph-metrics` 只有文档命中）。
  2. `win/audioclock.ps1` 有一行中文注释，而该文件**无 BOM**——PowerShell 5.1 对无 BOM 的
     .ps1 按 ANSI 码页解码，中文 Windows 上等于拿 cp936 读 UTF-8 字节。它落在注释里、行末是
     `.` 不是反引号，所以既没改解析也没改行为（实测 `PSParser::Tokenize` 0 个解析错误，
     音频门禁 21 项照绿），但它违反本仓库自己立的"这条链路上的脚本一律纯 ASCII"。
     改完四个脚本的非 ASCII 行数全为 0。
- README 那一行按用户要求并进上一次提交：先证实 `d90db2d` **不被任何远端包含**
  （`git log --branches --not --remotes` 列出全部 4 个本地提交），才动 `--amend`；只 stage
  `README.md`，`git diff d90db2d 8aa1fc1` 证明这次重写只动了那一行（+1/-1）。
- 安全面结论：跟踪内容里机器路径 / 用户名 / 邮箱 / 密钥形状 0 命中（阳性对照先证尺子活着）；
  所有 subprocess 调用都是 argv 列表、无 `shell=True`、无字符串拼命令；唯一的网络点是
  `get_song.py` 里硬编码的 HTTPS Release 地址，且它**只从下载的包里读字节**（清单 JSON 与 mp3），
  不 import 也不执行 `.pyz` 里的代码——下载物拿不到代码执行路径，也没有 zip 条目名落盘
  （固定成员名 `archive.read(MEMBER)`，不存在 Zip Slip 面）。
- 交给用户决定、我没有动的三件（都不是代码缺陷）：
  1. `origin` 指向上游作者的仓库，`main` 跟踪 `origin/main` 且**领先 6 个提交**；此时
     `git push` 会把这 6 个提交推别人的项目。`gh` 已登录为 AlexPeng07，发之前要先建自己的
     仓库再把 remote 指过去。
  2. 提交身份邮箱是 `alexpeng07@outlook.com`，推上去即永久可被抓取；换 GitHub noreply 要
     重写这 6 个提交的身份。
  3. `lyrics.json` / `双语歌词.lrc` / `双语字幕.srt` 是 Mili 歌词与译文的副本（上游本来就在
     公开分发）；`.lrc`/`.srt` 程序不读、只为人服务，想缩小暴露面可以只把这两个移出跟踪。
- 门禁当场重跑（不引用旧读数）：`test_win_render.py` 9 项 OK、852 次比较 3.8 s、对照物仍从固定
  commit `9d8e815` 现取；`test_win_audio.py` 21 项 OK、**0 skipped**；`wt --fullscreen` 实播
  60→68.04 s 共 196 帧、最坏一帧 12.1 ms（预算 41.7 ms）、179×56 由
  `GetConsoleScreenBufferInfo(srWindow)` 报、backend=winrt、host=windows-terminal、
  控制台模式 `0x1f7→0x191`。第二遍重跑两套件再次 9/21 全 OK。
- 一条读数差异留着别糊：那次实播 `audio_ready_seconds` 读到 **3.54 s**，文档里的 2.45 s 是
  安静机器上的数，当时同一台机器上并发跑着另一个进程；第二遍实播没重测这个字段。
  文档不改（约 2.5 秒的量级仍成立），但"就绪时间会随并发上浮"记在这儿。
- 一桩"看着像项目的错、其实是环境的"：门禁跑到一半工作区冒出字面名叫 `%SystemDrive%` 的目录，
  里面是 Windows shell 缓存库（`cversions.2.db` 与几个 `{GUID}.2.ver…db`，共 984 KB）。
  没有直接删——整体移到 `.build/stray-kept/` 留着。归因靠重跑：渲染门禁、单条音频用例、
  完整音频门禁、`wt` 实播四步各跑一遍、每步之后查一次，**四次都没再出现**；
  `win/launch.py` 的 `child_env()` 只抄 `os.environ` 再加 `PYTHONDONTWRITEBYTECODE`，
  本机 `SYSTEMDRIVE`/`ProgramData` 都正常展开。判定：那是那一轮里并发的另一个进程留下的，
  不是本项目门禁的行为，所以 `.gitignore` 不为它加规则。
- 顺手把 README 的 `--report f.json` 改成 `--report .build\f.json`：文档教的落点正好在忽略规则
  管不到的仓库根（`*.json` 不能整体忽略，`config.json` 要跟踪）。改完"跑出来的东西一律落在
  被忽略的地方"这条规则没有反例了。`README` 与 `.gitignore` 本身都不是门禁的输入
  （`git grep -IE "gitignore|README" -- '*.py' '*.ps1' '*.cmd'` 只命中 `get_song.py` 的一句
  文档串，不是读文件）。
- 追加（同轮）：**"别人克隆下来到底能不能播"是当判据跑的**，不是当常识跳过的。
  `git clone . .build/fresh-clone`，在那份干净副本里从空 `.build/` 起走完访客路径：
  1. `win/get_song.py --json` → `verdict=OK`、`package_origin=download`（真下载，没走缓存）；
     包 9,205,195 字节与当期公布摘要 `55043652a24c…` 一致，音频 8,620,427 字节与包内清单摘要
     `2da5fb306fc8…` 一致，引擎时长 211.98365 s 对配置 211.906667 s 差 0.077 s。
     顺带记一条脆弱点：这条链子上游 Release v1.0.0 是单点依赖，2026-10-01 实测仍在且摘要未变，
     作者哪天删掉 release，所有新克隆的首次运行都会红着失败（不会静默播错）。
  2. `test_win_render.py` 9 项 OK，对照物 `git show 9d8e815:player.py` 在克隆里可达。
     这条有发布含义：**若把这 7 个提交 squash 成孤儿初始提交，等价性门禁会当场红**——
     发布必须连上游历史一起推，不是风格问题。
  3. `test_win_audio.py` 21 项 OK、0 skipped（克隆里没有缓存，音频是第 1 步真取回来的）。
  4. `wt --fullscreen` 实播 158.7→163.043 s：110 帧、最坏一帧 8.3 ms、就绪 2.04 s、
     backend=winrt、host=windows-terminal、179×56 由 `GetConsoleScreenBufferInfo(srWindow)` 报。
- 文档里教的两个排障开关也实测：`--snapshot 159.85 --plain` 在非终端环境下输出 40 行画面 rc=0；
  把克隆里的 `media/` 改名后 `--backend none --snapshot 10 --plain` 仍 rc=0——
  "这一档不需要音频文件"那句成立。
- 读数同步进"本机实测读数"表：音频就绪改成 2.04～2.45 s（并注明并发另一进程时读到 3.54 s）；
  实播那行不再写推算出来的 fps，改成三对原始读数（110 帧/4.34 s、196 帧/8.04 s、244 帧/10.0 s）。
- "未验证"新增一条：README 的"Python 3.9 以上"本机证不了（只装了 3.14.4，没有 3.9 可实跑）。
  把全部源码 AST 扫过，未见 `match`、未见 PEP 604 union 这类 3.10+ 专有写法——
  但这只是"没找到反证"，不等于"3.9 上跑通过"，所以记在未验证而不是写进要求。
- 安全审查口径：L3 深度审查在 `7b8632c` 与 `9e2bf82` 两个提交集上各跑一次，两次都 0 findings；
  最后一次提交只是这两条文档读数改动，门禁不读文档（上面 grep 实测过），故不再重跑第三遍。
- **判据替换（同轮，推翻上面那条"`.gitignore` 不为它加规则"）**：那个 `%SystemDrive%` 目录
  后来又出现了一次。新旧两句都要留着——旧句是"单独重跑四步门禁不复现，所以是并发进程留下的，
  不加规则"；新事实是"第二次出现同样落在并发跑着同一把安全审查工具的时间窗内，
  而我把四步门禁单独重跑的那一遍没有它"。相关性 2:0，但**这只是相关性，不是定论**，
  所以我没有去指认某个工具，而是改了处置方式：`.gitignore` 加一条 `/%SystemDrive%/`。
  理由不是"这算本项目的产物"，而是"只要它可能出现在工作区，发布前的清洁判据
  （未跟踪未忽略为空）就不该依赖我猜对了谁干的"。
  加完实测三件事：规则确实命中真实路径（`git check-ignore -v` 指到 `.gitignore:35`）、
  `git status` 里那棵树消失、`git add -A --dry-run` 只收 `.gitignore` 本身、
  `git ls-files -i -c` 仍为空（没有任何被跟踪文件被新规则误伤）。
  删掉的这份工作区副本是可再生的 shell 缓存，真身在 `C:\ProgramData\Microsoft\Windows\Caches`，
  没有被碰。
- **判据作废与重跑**：上面"两次都 0 findings，故不再重跑第三遍"那句已经不成立——加完
  `/%SystemDrive%/` 之后终端提交集又前进了两个（`8188168`、`e33ee2d`）。"覆盖到哪"不能靠推断，
  所以在 `e33ee2d` 上真跑了第三遍 L3，仍 0 findings。教训写在这儿：口径里写"不重跑"必须同时写清
  它成立的条件；条件一变，旧句子立刻变成假陈述，宁可重跑一次也别留一句过期的"已覆盖"。
- 第八轮 · 发布：用户给出目标仓库 `https://github.com/AlexPeng07/win-world.execute-me.git`。
  推之前实测四件事：仓库存在且 `isEmpty=true`（不会覆盖别人的东西）、`viewerPermission=ADMIN`、
  gh 的 git 凭据助手已配好（不需要弹窗认证）、本地工作树干净。
  remote 处理成 `origin`=用户仓库、`upstream`=原作者仓库（改名保留出处，不丢可取回的历史）。
- 发布后对账拿的是**发出去的东西**本身，不是本地状态：
  `git ls-remote` 的 `refs/heads/main` == 本地 HEAD（`e33ee2d2…`）；
  远端 recursive tree 共 25 个 blob，与本地 `git ls-files` **逐行相同**（多一个少一个都会红），
  其中无 `media/`、无 `.build/`、无 `__pycache__`、无任何 `mp3/wav/flac/m4a/pyz`；
  最大两块是封面图 3,048,987 字节与 `spectrum.json` 1,778,342 字节；
  远端 `commits` 列表 20 条与本地 `git rev-list --count main`=20 一致，且对照物
  `9d8e815`（作者 2026-09-28）在远端可达——这条是硬约束：等价性门禁要 `git show 9d8e815:player.py`，
  squash 成孤儿初始提交会让它当场红（干净克隆那一步已经把整个链路跑通了）。
  远端 README 第 5 行确实带着用户新加的"改编者AlexPeng07"。
- 发布面留给用户知道的三件事，都不是缺陷：仓库 `private=false`（GitHub 显示 PUBLIC），
  `lyrics.json`/`双语歌词.lrc`/`双语字幕.srt` 是 Mili 歌词与译文副本并随仓库公开分发；
  仓库**没有任何 LICENSE 文件**（上游本来也没给），README 的"来历与版权"是唯一立场声明；
  提交身份邮箱 `alexpeng07@outlook.com` 随 9 个提交公开（上游历史里另有作者自己的
  `408207212@qq.com`，那是 GitHub 上原本就公开的东西）。
- 发布之后另一次账号侧变更（记在这儿，免得将来有人对着 `git log` 困惑"作者邮箱怎么中途换了"）：
  GitHub 账号开启 "Keep my email addresses private" 与 "Block command line pushes that expose my
  email"，本机 `git config --global user.email` 改为 `309235349+AlexPeng07@users.noreply.github.com`。
  上面那句"随 9 个提交公开"是当时口径，实际本仓库带旧邮箱的提交已随收尾提交涨到 10 个，
  按追加不改写的规矩旧句留着。**已公开的这些提交不做重写**——GitHub 设置页自己写着
  "Previously authored commits associated with a public email will remain public"，重写只是止损。
  从本条之后的提交都应带 noreply 地址；若某次推送被 GitHub 拒，先查提交里带的是哪个邮箱。





