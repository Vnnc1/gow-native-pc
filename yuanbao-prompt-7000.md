# 任务书：撰写《God of War（PS2）静态重编译原生移植》技术专著（5 万字）

## 一、你的角色与交付目标

你是同时具备三重身份的技术作者。第一重是 PS2 底层工程师：做过 MIPS R5900 的静态重编译，清楚 EE、VU1、GS、IOP、SPU2 五条流水线各自能被"提前编译"到什么程度，也清楚哪些部分只能靠解释或原生服务兜底。第二重是 Windows 原生构建工程师：熟悉 CMake、Ninja、clang/llvm-mingw、PGO、sccache，知道 MAX_PATH 会在哪一层咬人，知道一个 instrumented 构建为什么要跑第二遍。第三重是技术作者：能把工程决策写成可核查的长文，让读者看完能复现判断，而不是只记住几个形容词。

接下来你会拿到一个真实项目的关键事实。这个项目把 PS2 游戏《God of War》（序列号 SCUS-97399）静态重编译成原生 Windows 程序。仓库里没有一行模拟器主循环，只有围绕一个外部 runtime 的档案、流水线、光盘工具、启动器与安装器。你的任务不是评价它，而是**把它讲透**：每个部件为什么存在、边界划在哪、代价是什么、失效时如何暴露、换一个前提会不会崩。

读者是能读代码的工程师，不是投资人，也不是玩家。默认他们懂 ELF、懂重编译、懂 ISO9660，但完全不知道这个项目的约定。因此凡属"本项目特有"的设计，都必须交代来龙去脉；凡属行业通识，一句带过即可，不要科普常识来凑字数。检验标准很简单：每 1,000 字里至少要有一个可核查的细节（文件、阶段、补丁号、数字、命令行），否则那 1,000 字就是水。

## 二、事实基座（唯一可信素材）

以下事实全部来自仓库实际读取。**只能使用这里给出的事实，加上公认的技术常识**。禁止虚构文件名、函数名、版本号、性能数字、API 名称。需要举例而事实不足时，用"仓库中该逻辑位于 X 层"这类可核查表述，不要编造符号。数字照抄原值；原文本身是约数（如"约 6,400 个函数"）时保留约数并说明来源。

### 2.1 项目坐标：一个编排层仓库

这是**编排层仓库**，不是模拟器。runtime 不在仓库内：`engine/runtime.toml` 固定仓库 `https://github.com/YYOzcan/Tobiichi-Port` 与 commit `471c83180a8df575cff4abd3fae6c043b5096925`（2026-10-16），上游重编译器为 `https://github.com/ran-j/PS2Recomp`。流水线 `fetch` 阶段克隆该 commit，再按文件名顺序应用 `engine/patches/*.patch`，当前共 90 个补丁文件。runtime 内部分四块：`PS2Recomp/`（ran-j 的 MIPS R5900→C++ 静态重编译器 ps2xRecomp，与原生运行时 ps2xRuntime、ps2xIOP；经 Waffle565 扩展原生 GS 渲染器、原生 VU1／IOP 代码、声音、手柄、记忆卡，叠加 KIexster 的补丁栈与 YYOzcan 的 Tobiichi 改动）、`src/`（本作覆盖层，如 `gow_overrides.cpp`、`gow_pad2_packet.h`、`gow_gs_replay.h`）、`config/`（重编译配置与函数表）、`tools/`（VU1／IOP 原生代码生成器）。runtime 全部 GPL-3.0，许可与作者在 `CREDITS.md`。

实测规模：runtime 内 196 个 `.cpp`、195 个 `.h`；顶层含 `AGENTS.md`、`PS2_PROJECT_STATE.md`、`GODOFWAR.TOC`、`SYSTEM.CNF`、`port/`、`game/`、`tests/`、`tools/`、`launcher/` 等。这解释了为什么本仓库的 90 个补丁要按序数命名：它们改的是别人的代码，必须能随时重放、随时丢弃。

许可结构值得单独一段：runtime 与它的上游全部 GPL-3.0，本仓库自己写的编排层（Python／PowerShell／C++／QML）与之分离，`CREDITS.md` 逐个列出作者与来源。这不是法律细节，而是架构约束——它决定了为什么本仓库不能把 runtime 的代码抄进来改，只能打补丁、只能 pin commit、只能在 `fetch` 阶段重放；也决定了发布包里为什么"不含 runtime"（`package` 阶段明确排除）。讨论"为什么不 fork 一份改干净"时，答案同时是工程的和许可的。

仓库自身只做五件事：游戏档案（profile）、光盘工具、构建流水线、启动器、安装器与文档。这条边界是全书第一个论点：**能参数化的绝不硬编码，能外部化的绝不内嵌**。游戏相关的一切——ELF 名、CRC、`.text` 的 SHA-1、runtime 内路径、光盘布局、版本与翻译、优化脚本、语言判据——全在 `games/gow1/game.toml`；`tools/pipeline/profile.py` 负责把它读成 Python 字典或 JSON，供 PowerShell 与启动器共用。档案是唯一事实源，任何一层重复写死一个游戏常量，都视为缺陷。

### 2.2 运行时分层：重编译到底替换了什么

| PS2 部件 | 原生替代 |
|---|---|
| EE（游戏代码） | 静态重编译出的 C++，约 6,400 个函数 |
| VU1 | 由录制的 micro-memory 提前编译的微码；未录制的走解释器 |
| GS | OpenGL 渲染器，GPU render target，内部分辨率 1×–8× |
| IOP | 游戏自带 IRX 模块提前编译；HLE 内核 |
| SPU2、手柄、记忆卡、MPEG 影片 | 原生服务 |

单次运行的数据流：`ps2EntryRunner.exe <disc 目录>/SCUS_973.99`。ELF 所在目录即 CD 根，`.disc_layout` 按扇区列出每个文件（允许文件超出光盘实际末端），同目录 `mc0/` 是记忆卡，覆盖层按 ELF 名匹配。也就是说，**没有虚拟光驱、没有 ISO 挂载、没有运行期语言开关**：每个语言一个光盘目录；原始影片在原盘可用时保持原样，16:9 影片缺失时映射到 `.PSS`。这套选择牺牲磁盘占用，换来"运行期零分支"，也让故障定位变成"哪个目录、哪个文件"的问题，而不是"哪个开关没关"。

### 2.3 游戏档案：一个 TOML 如何吃掉所有分支

`[executable]` 给出 `name = "SCUS_973.99"`、`serial = "SCUS-97399"`、`crc = "D6385328"`（PCSX2 语义：ELF 全部 32 位字异或）、`text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"`。这个 SHA-1 是全套设计的支点：重编译产物只依赖 `.text`，所以**任何只改数据的翻译版光盘都会编译出同一个程序**，翻译因此不必进白名单。

`[runtime]` 指向 runtime 内的模板 `config/recomp.template.toml`、函数表 `config/funcmap.csv`、三个覆盖层文件、VU1 生成器 `tools/vu1/generar_vu1.cpp` 与 `tools/vu1/vu1n_gen.py`、VU1 原生入口表 `vu1n_heads.txt`、IOP 生成器 `tools/iop/iopn_gen.py`。`vu1_native_heads` 解决生成器找不到的块入口（寄存器间接跳转）：缺了它们，这些块只能在解释器里跑，5 秒船战里进出原生代码约 120 万次。这是"性能问题往往不是算术问题，而是边界问题"的实例。

`[disc]` 定义 `GODOFWAR.TOC` 的 24 字节条目（`name[12]`、`u32 part`（0 = PART1.PAK，1 = PART2.PAK）、`u32 size`、`u32 sector`）、两个 PAK、IOP 模块目录 `IOP_MOD`、翻译文本所在 `R_PERM.WAD` 与 `R_SHELL.WAD`、16:9 影片扩展名 `.PSW` 与 `.PSS` 的回退关系，以及一个按**精确字节**识别的占位影片（`size = 16388` 加 sha256）——PT-BR 独立版有一个永远播不完的缩减版 `SEMO01.PSW`，用尺寸阈值会误杀合法短片，所以判据必须是"这一份字节"。

`[build]` 只有 `unity_batch = 16`；`[diagnostics]` 的 `frame_pc = "0x1837B8"` 是 `vid::Flip`，用来数**客机帧**，与宿主呈现率区分开——这条小配置背后是"帧率到底谁说了算"的测量纪律，性能章节必须展开。

`[[editions]]` 与 `[[regions]]` 把"能不能识别"和"能不能跑"彻底分开。USA 原版 `D6385328`；日本 `SLPM_670.10`、`CA052D22`、`8ed48ca8…`；亚洲二版 `SCAJ_973.99` 的引导程序与日版**逐字节相同**（同 CRC、同 `.text` SHA-1、同尺寸），因此 `code = "japan"` 直接复用日版构建，光盘数据仍归自己——首次启动时在日文 logo 上渲染出"新游戏／确定"，说明本地化在贴图里，可执行文件仍是日文的；欧洲 `SCES_531.33`／`FB0E6D72`；另有 `europe-alt`、两个 demo。`[language_hints]` 用整句（"Novo Jogo"、"Nueva partida"、"Nouvelle partie"…）而不是单词判断翻译语言，因为 `Difficulty` 这类词同时也是内部标识符，单词匹配必然误判。

`[optimize]` 给 `seconds = 240` 与一段手柄脚本（`5:start,12:x,18:x,24:x,30:x,36:x,40:cuadrado,…`），它既用于录制，也用于 PGO 训练。注意脚本里用西班牙语按键名（`cuadrado`、`triangulo`、`circulo`），这暴露了 runtime 的血统：它从南美社区项目长出来，命名不是英语。读代码的人必须知道这一点，否则会以为是笔误。

### 2.4 光盘工具链

`tools/disc/discfs.py` 是格式层（ISO／已解包目录／TOC／ELF，格式说明写在模块 docstring 里），`identify.py` 输出 `{game, edition, language, compatible, problems}` 的 JSON，`prepare.py` 产出 `data/<id>/discs/*`、`languages.json` 与共享 `mc0`，`iso_extract.py`（Waffle565）写 `.disc_layout` 与 `.disc_meta`，`chd.py` 处理 CHDv5 DVD 与单 MODE1 轨，做校验缓存与锁定的原子发布（落在 `data/imports/chd`），外部工具版本钉在 `toolchains.json[disc_import]`：chdman 0.289（带 exe 级 SHA-256）与 7zr。`vu1_from_disc.py` 从 VIF MPG 上传里抽出 VU1 微码，供"不玩游戏也能预编译"，属实验性、覆盖不全，配 `vu1_from_disc_test.py` 合成测试。

这条链的设计意图是**把不可信输入收敛成可校验的中间态**：ISO 是任意字节，识别是纯函数，准备阶段才写盘，写盘有锁、有校验、可重入。识别结果的数据契约（谁读、缺字段怎么办、`compatible` 与 `playable` 的区别）值得单独一节。

### 2.5 构建流水线：18 个阶段与一条输出协议

入口 `tools/pipeline/build.ps1` 只有 86 行，因为实现分给 `modules/`：`common`（62 行，`Step` 与 `Write-PipelineMetrics`）、`context`（77）、`toolchain`（41）、`process`（67）、`runtime`（95）、`game`（281）、`optimize`（159）、`verify`（33）、`distribution`（100）、`qt`（101）、`build-progress`（27）。参数包括 `-Game`、`-Stages`、`-Discs`、`-Config Release|RelWithDebInfo`、`-Ltcg`、`-Pdb`、`-CpuTarget portable|x86-64-v3`、`-Codegen locals|classic`、`-BuildRoot`、`-Toolchain`（`msvc` 只是迁移别名，组件一律用钉死的 llvm-mingw）、`-CompilerCache sccache|none`、`-ForceRecomp`、`-NoReleaseProfile`、`-Xdelta`、`-Seconds`。

阶段全集：`tools`（便携 Git、Python 3.13.16、CMake 3.31.12、Ninja 1.13、llvm-mingw clang、sccache 0.19.0，各下载一次并按 SHA-256 校验）、`fetch`、`xdelta`、`discs`、`vu1disc`、`configure`、`recomp`、`sync`、`build`、`pgo`、`pgo-check`、`tune`、`optimize`、`native`、`verify`、`launcher`、`package`、`installer`。

五条工程约束必须讲清。其一，**单写者锁**：`data/pipeline.lock` 以独占方式打开，第二个流水线直接失败并提示"另一个流水线正在使用这个 checkout"，因为缓存与生成物不能并发更新。其二，**短构建目录**：`C:\gow-build`（RelWithDebInfo 用 `C:\gow-build-dev`），因为 runtime 的 CMake 依赖是 git checkout，长路径必撞 MAX_PATH；同一台机器上第二份仓库副本会拿到 `C:\gow-build-<hash>`，选择写进 `data/build-root.txt`，启动器与卸载器都读它。其三，**该目录的归属校验**：启动器接受 runner 前会核对 CMakeCache 的源目录，防止新副本误用旧副本的构建。其四，**临时目录重定向**：`build.ps1` 把 `$env:TEMP`／`$env:TMP` 指向 `data/_tmp`，避免构建中间物散落系统盘。其五，**输出协议**：`=== <step> ===`、`@@progress <done> <all>`、`@@status <text>`，其余行是日志——启动器的 `LoadingScreen.qml` 正是按这套文本协议算总进度与剩余时间。协议是文本而不是 IPC，这个选择让"终端跑一遍"和"启动器跑一遍"共用同一条路径，代价是解析脆弱、文案即接口。

`pgo`／`tune`／`optimize`／`native` 四阶段是性能主线。`optimize` 用 `[optimize]` 的 240 秒脚本，在隐藏静音窗口里让游戏自己玩（`GOW_WINDOW_HIDDEN=1`、`GOW_AUDIO=0`、`GOW_AUDIO_PCM=NUL`、`GOW_VU1_CAPTURE_MISSES=1`、`GOW_VU1N_X64=1`、`GOW_PAD_GUION=<脚本>`），录下 VU1 微码与 IOP 模块；`native` 只重建 VU1／IOP（补丁 16）；`pgo` 产出 `data/<id>/pgo/gow.profdata` 后二次构建；`tune` 用一次 `-O1` instrumented 构建同时收微码与 profile；`pgo-check` 校验 profile 真属于本次安装（清单、覆盖率、编译标志、无 profiling runtime 残留）。这四步构成"自举优化"闭环：**产物训练产物**，因此任何一次 runtime 或补丁变更都必须重训，否则 profile 会指向不存在的形状。

环境变量是这套系统的第二接口，值得列成表：`GOW_WINDOW_HIDDEN`、`GOW_AUDIO`、`GOW_AUDIO_DEVICE`、`GOW_AUDIO_PCM`、`GOW_VU1_FAST`、`GOW_VU1N_JIT`、`GOW_VU1N_DIAG`、`GOW_VU1_CAPTURE_MISSES`、`GOW_GS_EARLY_FINISH`、`GOW_GS_FINISH_ASINCRONO`、`GOW_GS_STAGE_SPIN_US`、`GOW_SCALER`、`GOW_ANISO`、`GOW_SHARPEN`、`GOW_TEXTURE_PACK`、`GOW_MOD_VFS_TABLE`、`GOW_MOD_PATCH_TABLE`、`GOW_MOD_VFS_LOG`、`GOW_QTE_HOLD`、`GOW_QTE_HOLD_HZ`、`GOW_SAVES_DIR`、`GOW_MC0`、`GOW_ISO`、`GOW_SKIP_FMV`、`GOW_FAST_BOOT`、`GOW_PERF_DIAG`、`GOW_PERF_FRAME_PC`、`GOW_PGO_REVISION`、`GOW_DISPATCH_FULL`、`GOW_IOP_DRIFT`、`GOW_SYNC_DIAG`。这些开关不是给玩家看的，它们是**诊断面**：出问题时，能通过"打开哪个开关、看哪一行日志"把范围二分。

### 2.6 重编译与产物治理

`tools/pipeline/recompile.py`（254 行）的 docstring 就是设计声明：内容寻址的 EE 生成、所有权感知的同步、成功以目录事务发布、失败保留上一份可用产物、复用由摘要而非时间戳决定；并且**绝不把游戏数据缓存到 `data/` 之外**。它从 `discfs` 借 `text_sha1`，用 sha256 做 key；`replace_file` 对 Windows 扫描器／索引器的短暂占用做 6 次有界重试，仍失败才报错——这是"在 Windows 上写文件失败是常态，不是异常"的工程化承认。`sync` 只拷贝变化的文件，并把档案里的 overrides 送进 runner。

需要讲清的三组语义：摘要命中与 `-ForceRecomp` 的冲突如何处理；事务发布在断电、崩溃、并发三种情况下的可见性；"所有权感知"意味着什么——生成物归流水线，用户改动归用户，二者冲突时谁赢、如何发现。

### 2.7 补丁链：90 个补丁就是一部性能史

补丁头部的注释行写明"是什么、为什么"，`git apply` 会忽略它们，所以它们同时是文档，这是本项目最值得学的习惯之一。按主题分组举例：

工程类：01 Release 的 LTCG 开关（默认不开，链接以小时计）、31 ThinLTO、32 至强 AVX2 数学标志、42 依赖浅克隆、04 从 Waffle 回合的 CPU 补丁。

正确性类：03 全屏崩溃、06 `movn`／`movz` 的 64 位语义、12 clang 下 GS 状态比较、24 音频混音溢出、47 GL 上下文回退、40 GS 提前结束。

重编译质量类：08 register-locals 代码生成（EE 线程时间约降 22%，可用 `-Codegen classic` 回到旧行为）、28 直接 `jal`、29 调度裁剪，以及 29a–29f 一整族诊断补丁（调用诊断、codegen MMIO 测试、会话帧计量、原生内存回归、scratchpad 链完成、DMA 提交计量）。

VU1 线：02、09、10、13 块链接、17 后台编译、18 x64 JIT、20 emitter 预留、22 分析缓存、27 速度、33／34／35 提前结束与自环、37 隔离任务重放、43 更瘦的原生代码、45 惰性成对解码、50 小帧运行、51 快速模式、60 JIT 快速模式、63 热入口、76 链预热、78 累加器、79 VF 前递、81 辅助函数去重、82 时序不变量。

GS 线：39 游戏菜单实时图形、44 stage 字节环、46 GIF 零拷贝、59 顶点环、61 shuffle 纹理复用、66 图元批、67 环溢出保护、68 停顿与深度 ZBP、69 每 ZBP 深度、70 GPU 帧计时、72 批前奏、74／75 运行态与加固、77 异步提交、83 不变量。

产品与系统线：15 隐藏窗口、16 只重建 VU1、23 IOP 稳定输出、25 独立启动档案、26 存档页截图去重、52 纹理包、53 QTE 长按、54 影片陈旧包、55 IOP 分片、56 键盘摇杆手势、57／58 和弦保持、71 mod VFS 钩子、73 启动器 mod 管理器、84 mod 数据补丁。

必须精读的一例是 44 号：把 GS stage 队列改成单生产者单消费者的字节环。船战时 worker 每秒约 24 万包，原实现每包都抢 mutex 与 vector，约 60% 的唤醒要走内核（每秒约 15 万次上下文切换）；改成写入环、原地读取，只在真睡时用锁与条件变量，stage 先自旋至多 `GOW_GS_STAGE_SPIN_US`（默认 50，0 表示立刻睡），队列字节上限仍是 4 MB，超过 1 MB 的包走堆拷贝，`afterBatch` 仍在每批后执行。测法是在 43 号之上跑存档路线、全屏、4 组交替对比：战斗 52.8 → 54.7 FPS，4 组全胜。这一段要当作"如何证明一个优化真的有效"的范本：单变量、交替、可复现路线、写明基线。

### 2.8 启动器与安装器

启动器是 Qt 6，源码钉 6.8.3（qtbase、qtshadertools、qtdeclarative，按 SHA-256 校验，一次构建进 `data/_tools`），并在构建 SDK 前应用 `tools/pipeline/compat/` 的源码兼容适配（现有一个 `qt-sequence-sort.h`）。代码规模：`lanzador.cpp` 914 行（播放侧，西班牙语命名）、`installer_backend.cpp` 547 行（安装侧，英语命名）、`mods_model.cpp` 807 行、`session_diagnostics.cpp` 463 行、`main.cpp` 134 行、`mando.cpp` 147 行。QML 侧 `Main.qml` 是侧边栏 + 页面：`pagina` 0 主页、1 安装、2–6 设置、7 存档、8 无障碍。`AccessibilityPage.qml` 管输入辅助、纹理包与视觉 mod；配色集中在 `Tema.qml`（`oro*` 系列承载绯红强调色）；`LoadingScreen.qml` 在长任务时覆盖全屏，按流水线协议显示总进度、剩余时间与 `cargaDica1..N` 提示，还能读玩家自己放进 `data/<id>/loading` 的图片；截图自动化用 `TOBIICHI_CAPTURA=<png>` 与 `TOBIICHI_CAPTURA_PESTANA=<page>`。页面上每个设置最终都变成上节那串 `GOW_*` 环境变量——UI 与引擎之间没有第二套配置系统，这是刻意的。

安装器 `installer/setup.cpp` 1352 行，Win32 + GDI+，**不用 Qt**，单文件自包含 exe：`--pack <dir> <out>` 把 LZMS 块追加进自身并写 footer；安装按用户进行（HKCU Apps 条目、快捷方式、`uninstall.exe` 与 `uninstall.lst`）；无点击测试靠 `/S [/D=<dir>]`；卸载靠 `uninstall.exe /uninstall-from <dir> /S [/purge]`，`/purge` 只在副本的 CMakeCache 确实指向 `<dir>` 时才删其构建目录；`GOW_SETUP_CAPTURE=<png>` 出截图。为什么不用 Qt：安装器必须能在没有运行库的机器上双击就跑，且体积要小到可以塞进 GitHub Release。

### 2.9 Linux、测试与文档

`bash build.sh` 走 `tools/pipeline/linux.py`（262 行，Python 3.12+、原生 Clang、系统或 SDK Qt 6.5+、SDL2），共享同一份档案、光盘准备、事务式重编译器与序数补丁链，用 flock 持 `data/pipeline.lock`，产物在 `data/build-linux/<game>`；启动器读 `data/build-root-linux.txt`，并按大小写敏感的 CMake 源目录归属校验。Windows 的构建根、便携工具、PGO profile 一律不复用。Linux 手柄采集走 SDL2，玩法仍用 raylib；渲染器与 System V 的 VU1 JIT 在 runtime 里已有 Linux 路径，但**编译通过不等于 GPU 验证通过**；Linux 的 PGO／自动录制、IOP 训练、便携依赖打包与二进制更新仍未实现，`package_linux.py` 只产出依赖宿主库的启动器加源码归档。

`tools/test/` 下约 40 个测试脚本与 C++ 单测：`pipeline_tests.py`、`guest_codegen_tests.cpp`、`guest_memory_tests.cpp`、`guest_calls.cpp`、`dma_worker_tests.cpp`、`qte_hold_test.cpp`、`qte_input_test.cpp`、`sound_regression.cpp`、`vu1-equivalence.py`、`recompile-smoke.py`、`disc-import-ui.py`、`regional-play-ui.py`、`launcher-languages.py`、`loading-progress.py`、`verify_setup.py`、`perf-compare.ps1`、`build-progress-tests.ps1`、`patch-stack-tests.ps1`、`linux_pipeline_tests.py` 等。`verify` 阶段不需要 ISO 也能跑，这是它存在的意义：把"回归"从"要有光盘"里解耦。

`docs/` 有 `architecture.md`、`disc-import.md`、`linux.md`、`saves.md`、`translations.md`、`adding-a-game.md`、`input-accessibility.md`、`reporting-bugs.md`、`tested-hardware.md`；`docs/research/` 有 25 篇按日期归档的研究与交接文档（VU1 JIT 原型、纹理替换、区域移植、渲染 worker、60fps 路线图、补丁 28/29 与 30–35 的集成评审等）。文档分层是刻意的：`docs/` 是契约，`docs/research/` 是证据，过期的证据不删，只归档。

区域构建是独立子系统：欧洲与日本各有经过"初始船战"验证的独立 Windows 构建，`games/gow1/regions` 存条件性 runtime 覆盖层、基线源码哈希、函数区间与重编译入口提示。这些覆盖层**绝不能**应用到 USA runtime，也不能进全局序数补丁链；`tools/pipeline/register_region.py` 把已验证的构建登记进 `data/<game>/regional-builds.json`，启动器校验归属、CMake 源目录与 ELF／runner 哈希后并入版本选择器。策略是：不同代码的 ELF 至今被 USA 流水线拒绝——宁可多一套构建、多一个构建根、多一张记忆卡，也不做"一套代码兼容所有区域"的赌博。这条判断的代价（磁盘、维护面、测试矩阵）必须在书里算清楚。

### 2.10 可观测信号与常见误判（写"失败学"章节时用）

这套系统把错误都推到少数几个出口，读者应当知道怎么读：`build.ps1` 顶部 `trap` 会把异常打印成 `ERROR: <消息>` 并以退出码 1 结束，所以启动器只需要抓这一行就能区分"失败"与"仍在跑"；`Step` 输出的 `=== <step> ===` 是阶段边界，也是进度条的分母来源；`@@status` 是人类可读的当前动作，`@@progress` 才是机器读的分子／分母。三类最常见的误判：其一，把"锁冲突"当成"构建坏了"——实际是另一个终端或启动器还在跑同一份 checkout；其二，把 MAX_PATH 报错当成编译器问题——实际是构建目录太长，必须换 `-BuildRoot`；其三，把 `pgo-check` 的失败当成 PGO 没效果——实际是 profile 与本次编译标志或源码不匹配，重训即可。写"失败模式"时按"症状—真实原因—判定方法—修复"四段式，不要写成故障清单。

另外要区分"未实现"与"未验证"：Linux 的 PGO、IOP 训练、便携打包是未实现；Linux 的 GPU 路径是已编译但未验证；`vu1disc` 是已实现但覆盖不全。这三类在书里必须用不同措辞，混为一谈会误导维护者。

### 2.11 三条对照轴（组织长文的骨架）

写作时请反复使用三条对照轴，它们能让 5 万字不散：**纵向**是"档案 → 光盘 → 生成 → 构建 → 运行"的数据流，回答"这一步的输入输出契约是什么"；**横向**是"Windows / Linux"与"USA / 欧洲 / 日本 / 亚洲"的平台矩阵，回答"同一决策在另一格是否成立"；**深度**是"能跑 / 跑对 / 跑快 / 跑稳"四级成熟度，回答"这个部件现在停在哪一级、下一级的门槛是什么"。每章至少用一次对照轴做小结，读者才不会读完十章只记住十个孤立事实。

## 三、成书结构（按此写，不要改顺序）

- **第 1 章 为什么静态重编译**（约 4,000 字）：模拟器／HLE／静态重编译／AOT 翻译的取舍；五条流水线各自的可静态化程度；本项目"重编译 + 原生服务"的代价；"编排层仓库"这一定位的必然性；读者拿到这个仓库时最该先看哪三个文件。
- **第 2 章 仓库解剖与一次运行的全链路**（约 4,500 字）：目录职责表；从 ISO 到 `ps2EntryRunner.exe` 的每一步；`.disc_layout`、`mc0/`、overrides 匹配；启动器如何把设置变成环境变量；失败时错误从哪一层冒出来。
- **第 3 章 游戏档案的工程学**（约 5,000 字）：逐节精读 `game.toml`；`.text` SHA-1 作为身份；翻译版为何自动兼容；`regions` 与 `editions` 的职责分离；`asia-97399` 的 `code = "japan"` 为什么正确；`language_hints` 为何用整句；占位影片为何按 sha256；`frame_pc` 与客机帧测量。
- **第 4 章 光盘工具链**（约 5,000 字）：ISO9660／TOC 24 字节条目／PAK 分片；CHD 导入与校验缓存；识别结果的 JSON 契约与 `compatible`／`playable` 的区别；prepare 的产物布局与共享记忆卡；VU1 微码从 VIF MPG 上传中抽取的原理与覆盖边界。
- **第 5 章 构建流水线**（约 6,000 字）：18 个阶段的依赖图（哪些能单跑、哪些必须成对）；单写者锁；短构建目录与 `build-root.txt` 的归属校验；工具链钉版本与 SHA-256；`optimize→native` 与 `pgo→pgo-check→tune` 两条闭环；输出协议与进度条的对偶；`GOW_*` 诊断面；失败可观测性。
- **第 6 章 重编译与产物治理**（约 5,000 字）：内容寻址为何优于时间戳；目录事务发布如何保证"失败不破坏可用产物"；所有权感知同步；`-ForceRecomp` 语义；register-locals（22% EE 线程时间）与直接 `jal` 的收益来源；生成物与用户改动的冲突处理。
- **第 7 章 补丁链精读**（约 8,000 字）：按工程／正确性／代码质量／VU1／GS／产品六类分组，逐条讲问题—方案—代价—测量；重点展开 08、15、16、44、52、71、84；说明补丁顺序为何敏感、为何区域覆盖层不能混进全局链、为何补丁头注释必须写测量。本章是全书重心，密度必须最高。
- **第 8 章 图形与 VU1**（约 5,500 字）：GS 环、GIF 零拷贝、图元批、深度与 ZBP、异步提交、纹理包与 mod VFS 的关系；VU1 从解释器到 AOT 微码再到 x64 JIT 的演进；热入口与链预热为何对船战关键；"编译通过 ≠ GPU 验证"的方法论。
- **第 9 章 启动器与安装器**（约 4,500 字）：Qt6 侧边栏与 8 个页面；LoadingScreen 的进度模型；存档页与无障碍页；mod 管理器；1352 行 Win32 安装器与 LZMS 自解包；HKCU 安装与 `/S` 静默契约；卸载 `/purge` 的安全条件。
- **第 10 章 可维护性、局限与路线**（约 6,000 字）：测试金字塔与哪些环节只能靠 UI 测试兜底；`docs/` 与 `docs/research/` 的分层；已知局限（Linux PGO／IOP 训练／打包缺失、`vu1disc` 覆盖不全、USA 流水线拒绝异码 ELF、无运行期语言切换）；若要支持第二款游戏，`adding-a-game.md` 的边界在哪；给维护者的十条硬规则。

## 四、写作规范

1. 语言：简体中文，技术名词首次出现中英并列（如"内容寻址（content-addressed）"）。不用"众所周知""显而易见""综上所述"这类填充。
2. 每个技术断言尽量落到具体位置（文件路径、阶段名、补丁号）。无事实支撑的推断必须显式标注"推断"，并说明推断依据。
3. 每章开头 80–150 字给该章要回答的问题；结尾 100–200 字给"本章结论 + 遗留疑问"，不写抒情总结。
4. 表格用于对比（阶段、补丁分类、区域差异、平台差异），代码块只放真实存在的命令、配置片段或环境变量，不伪造 API。
5. 数字与事实基座一致；需要推算时写出算式（如"每秒 24 万包 × 60 帧"），不让读者猜。
6. 禁止重复叙述：同一机制只在最合适的章节展开，其余处一句话引用（"见第 5 章"）。
7. 结论要敢下判断，但必须带条件：例如"在 4 MB 队列上限内，字节环优于锁队列；一旦单包超过 1 MB，堆拷贝会把收益吃掉"。
8. 反面样例，禁止写出这类句子："该项目采用了先进的技术架构，性能得到显著提升。"——没有主语、没有基线、没有测量。正确写法是："44 号补丁把每包一次的 mutex 换成单生产者环，在存档路线全屏 4 组交替下把战斗帧率从 52.8 提到 54.7 FPS。"
9. 不写"作为 AI""本文由模型生成"之类元话语；不列参考文献，除非事实基座里出现过该 URL。
10. 每章至少给出一处"如果让你重做，会怎么改"的判断，并写清代价；不要只做转述。

11. 允许第一人称的工程判断（"如果是我，这里会…"），但必须与事实陈述分栏，不能让观点冒充事实；判断要给出可反驳的条件。

必写清单（漏一条即视为不合格）：90 个补丁与它们的分组逻辑；`8c6e61a9…` 这个 `.text` SHA-1 的作用；`C:\gow-build` 为什么必须短；`data/pipeline.lock` 的单写者语义；`optimize→native` 与 `pgo→pgo-check→tune` 两条闭环的差别；44 号补丁的 52.8 → 54.7 FPS 及其测法；`asia-97399` 的 `code = "japan"`；Qt 6.8.3 三模块与 `compat/` 适配；1352 行 Win32 安装器的 LZMS 自解包与 `/S` 契约；Linux 的"未实现／未验证"边界。

## 五、分段交付协议

全文目标 5 万字以上（按上述章配额累计约 5.3 万字）。单条回复装不下，因此**严格按章分批**：

- 第一条只输出"第 1 章"，写满配额，末尾单独一行写 `【第 1/10 章完】`，然后停止，等我回复"继续"。
- 收到"继续"后输出下一章，编号连续，末尾写 `【第 n/10 章完】`；不重复上一章，不写"接上文"。
- 十章写完后，追加 800–1,200 字的《全书术语与决策索引》，按"决策—理由—代价"三列收束。
- 某章配额不足时，宁可补技术细节（时序、内存布局、失败模式、测量方法），不要用形容词凑字数；确无事实可写时，明确写"此处事实不足，需在 X 处补测"，不要编造。
- 若某条回复被截断，从断点续写，并在续写开头标注"续第 n 章"，不要重写整章。

现在开始写第 1 章。
