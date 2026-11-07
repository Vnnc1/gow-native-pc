# 《God of War（PS2）静态重编译原生移植》技术专著

> 由元宝（专家模式 / Hy4）按本仓库事实底稿生成，共十章，另附术语与决策索引。
> 文中“推断”“需补测”为生成方标注：涉及数字、路径与内部符号的断言，请以仓库当前状态为准。

## 第 1 章 为什么静态重编译

本章回答四个问题：把一份 PS2 可执行文件变成 Windows 原生程序，模拟器、高层模拟（HLE, high-level emulation）、静态重编译（static recompilation）与提前编译（AOT, ahead-of-time translation）各自的边界在哪；EE、VU1、GS、IOP、SPU2 五条流水线分别能被"提前编译"到什么程度、哪一部分只能靠解释器或原生服务兜底；本项目选择"重编译加原生服务"之后付了哪些可测量的代价；以及为什么呈现在读者面前的是一个不含 runtime 的编排层（orchestration layer）仓库。最后给出拿到仓库后最该先读的三个文件。

### 1.1 四条路线，不是四种性能等级

| 路线 | 输入 | 翻译发生的时机 | 对原始二进制的依赖 | 失效时暴露在哪一层 |
| --- | --- | --- | --- | --- |
| 逐指令解释／动态重编译的模拟器 | 光盘映像 + 完整硬件状态 | 运行期，按 PC 逐条或按块 | 弱：换一张盘只换数据 | 指令语义、时序、同步 |
| 高层模拟 HLE | 游戏调用的 API 语义 | 运行期，按调用点 | 中：需要先识别调用 | 某个 BIOS／库函数行为不符 |
| 静态重编译（本项目） | ELF 的 `.text` | 构建期，一次性 MIPS→C++ | 强：ELF 名、CRC、`.text` 摘要全进档案 | 生成代码编译不过，或生成代码跑偏 |
| 一般 AOT 二进制翻译（非本项目路径） | 任意可分析二进制 | 构建期 | 强，通常还依赖符号 | 间接跳转、自修改代码 |

表中"失效层"一列是**推断**：依据是 `recomp`、`build`、`verify`、`pgo-check` 四个阶段各自把守的入口，以及仓库说明对 60 Hz VBlank 与"掉帧而不减速"的表述；仓库没有逐路线写过失效对照表。
PS2Recomp 的翻译是字面式的（literal），每条 MIPS 指令映射成一个 C++ 操作，官方给出的例子是：

```mips
addiu $r4, $r4, 0x20
```

```cpp
ctx->r4 = ADD32(ctx->r4, 0X20);
```

这不是反编译成可读源码，而是把指令语义机械搬进宿主语言，再交给 clang／llvm-mingw 去做寄存器分配、LTO 与 PGO。好处是语义保真可逐条核对；代价是生成物体积与编译时间由指令数决定，运行时分层说明记为约 6,400 个函数——该数字本身是约数，此处保留约数，不折算成精确值。仓库 README 把这条线写得更直白：不再逐条模拟 PS2 指令，而是把原始可执行文件 `SCUS_973.99` 用 PS2Recomp 翻成 C++ 并编译成原生程序，"PS2 hardware is replaced by native code, not emulated"。
一条容易被误读的刻度：游戏逻辑绑在 PS2 的 60 Hz VBlank 上，游戏本身永不超过 60 FPS，移植体保持真实速度，掉帧而不减速。内部分辨率可以在 1×–8× 之间变，逻辑帧率不能变。所以性能讨论里"帧率上不去"未必是渲染 bug，测量点应当是 `frame_pc = "0x1837B8"`（`vid::Flip`）数出来的客机帧（guest frame），而不是宿主呈现率（host presentation rate）；这条测量纪律在第 3 章展开。

### 1.2 五条流水线的可静态化程度

| PS2 部件 | 原生替代（分层说明） | 构建期完成 | 运行期兜底 | 当前停在 |
| --- | --- | --- | --- | --- |
| EE（游戏代码） | 静态重编译出的 C++，约 6,400 个函数 | 全部指令翻译、函数地址绑定 | 无；覆盖层按构建作用域替换 EE 函数绑定 | 跑快 |
| VU1 | 由录制的 micro-memory 提前编译的微码 | 已录制块的微码、原生入口表 | 未录制的走解释器 | 跑快，边界未闭合 |
| GS | OpenGL 渲染器，GPU render target，内部分辨率 1×–8× | 无：GS 命令流不是 MIPS | 原生渲染器 + stage 队列 + 批／环／深度处理 | 跑稳 |
| IOP | 游戏自带 IRX 模块提前编译；HLE 内核 | IRX 模块、RPC/DMA transport 的形状 | `ps2xIOP` 与其 runtime transport 在处理 | 跑对 |
| SPU2／手柄／记忆卡／MPEG 影片 | 原生服务 | 无 | 全部 | 能跑 |

分层说明把 SPU2、手柄、记忆卡、MPEG 影片合在一行，不是漏列，而是它们在架构上同属"不进入重编译管线"的一类；下表按五条流水线的叫法保留这一行。表中"当前停在"一列同样是**推断**：依据为 2.2 的分层说明、08 号 register-locals 补丁约降 22% EE 线程时间、44／67／68／69 号补丁主题、23／55 号 IOP 补丁主题，以及 Linux GPU 路径"已编译但未验证"的原文措辞；仓库没有给部件打过成熟度标签。
几处需要提前钉住的细节：
**EE。**​ 游戏覆盖层（game override）是运行期侧、构建作用域（build-scoped）的补丁模块，在 `loadELF` 阶段按地址替换 EE 函数绑定，只作用于一个特定游戏构建；它与重编译输出分离，也与全局 runtime stubs／syscalls 分离。本作覆盖层落在 runtime 的 `src/`，档案点名 `gow_overrides.cpp`、`gow_pad2_packet.h`、`gow_gs_replay.h`。这是"能外部化的绝不内嵌"的第一处落地：改行为不改生成物。
**VU1。**​ `[runtime]` 的 `vu1_native_heads` 解决生成器找不到的块入口（寄存器间接跳转）。缺了它们，这些块只能留在解释器里跑，5 秒船战里进出原生代码约 120 万次，即约 24 万次／秒（120 万 ÷ 5，约数）。这不是算术吞吐问题，是边界问题——全书会反复回到这个句式，第 8 章展开。
**GS。**​ 不是"把 GS 编译掉"，而是把绘制命令交给 OpenGL 渲染器。运行期仍有队列与同步，因此 44 号补丁才去改 stage 队列（战斗 52.8 → 54.7 FPS，测法见第 7 章），67／68／69 号才去补环溢出、停顿与深度 ZBP。把 GS 写成"已 AOT"是错的：它属于原生服务，成熟度按"跑稳"计。
**IOP。**​ IRX 提前编译加 HLE 内核，RPC／DMA 行为由 `ps2xIOP` 与其 runtime transport 承担。23 号"IOP 稳定输出"与 55 号"IOP 分片"说明这一层的问题集中在输出确定性与分片，不在指令翻译。
深度轴（能跑／跑对／跑快／跑稳）上：EE 已用 08 号 register-locals 把 EE 线程时间约降 22%（`-Codegen classic` 可回退，见第 6、7 章），到"跑快"；VU1 到"跑快但边界靠 `vu1_native_heads` 补"；GS 到"跑稳"；IOP 到"跑对"；原生服务到"能跑"。Linux 的 GPU 路径不属于这四级中任何一级，它是横向矩阵里的一格缺口（见第 10 章）。

### 1.3 代价：这一次交换到底付了什么

**一，身份收窄。**​ `[executable]` 给出 `name = "SCUS_973.99"`、`serial = "SCUS-97399"`、`crc = "D6385328"`（PCSX2 语义：ELF 全部 32 位字异或）、`text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"`。重编译产物只依赖 `.text`，所以任何只改数据的翻译版光盘都会编译出同一个程序，翻译不必进白名单（见第 3 章）；反过来，USA 流水线至今拒绝不同代码的 ELF，日本 `SLPM_670.10`／`CA052D22`、欧洲 `SCES_531.33`／`FB0E6D72` 各有经"初始船战"验证的独立 Windows 构建。换一张盘不是换数据，是换一套构建根、一张记忆卡、一个版本选择器条目。
**二，运行期零分支换来磁盘占用。**​ 单次运行是：

```text
ps2EntryRunner.exe <disc 目录>/SCUS_973.99
```

ELF 所在目录即 CD 根，`.disc_layout` 按扇区列出每个文件（允许文件超出光盘实际末端），同目录 `mc0/` 是记忆卡，覆盖层按 ELF 名匹配。没有虚拟光驱、没有 ISO 挂载、没有运行期语言开关：每个语言一个光盘目录；原始影片在原盘可用时保持原样，16:9 影片缺失时映射到 `.PSS`。故障定位因此变成"哪个目录、哪个文件"，而不是"哪个开关没关"（见第 2、4 章）。
**三，产物训练产物。**​ `optimize` 用 `[optimize]` 的 240 秒手柄脚本在隐藏静音窗口里让游戏自己玩，录下 VU1 微码与 IOP 模块；`native` 只重建 VU1／IOP（16 号补丁）；`pgo` 产出 `data/<id>/pgo/gow.profdata` 后二次构建；`pgo-check` 校验 profile 真属于本次安装。90 个补丁或 runtime 任一变更都必须重训，否则 profile 指向不存在的形状。两条闭环（`optimize→native` 与 `pgo→pgo-check→tune`）的差别在第 5 章展开。这是静态重编译相较模拟器最不直观的一笔维护税：模拟器换版本只需重新载入，这里换版本要重新自举。
**四，硬件上限被继承。**​ 60 Hz VBlank 与 1×–8× 内部分辨率是两套正交刻度；提高内部分辨率不会提高逻辑帧率，掉帧而非减速。把它计入代价，是因为它决定了全书性能章节的分母是客机帧而非宿主帧。
**五，法律与工程是同一条约束。**​ 仓库不含游戏文件（ISO、可执行文件、IRX 模块、`.PAK` 数据），也不含由它们生成的代码；安装器在用户机器上从用户自己的光盘映像构建，"nothing derived from the game ever leaves it"：

```text
instalar.cmd -Iso "D:\path\God of War.iso"
```

`-SinOptimizar` 跳过优化步骤，`-Optimizar` 之后可补跑。runtime 与上游全部 GPL-3.0，`package` 阶段明确排除 runtime（见 1.4）。`C:\gow-build` 必须短、`data/pipeline.lock` 的单写者（single-writer）语义，同属这一层"在 Windows 上把不确定性关进笼子"的决策，第 5 章展开。

### 1.4 编排层仓库：不是选择，是约束收敛的结果

`engine/runtime.toml` 固定仓库 `https://github.com/YYOzcan/Tobiichi-Port` 与 commit `471c83180a8df575cff4abd3fae6c043b5096925`（2026-10-16），上游重编译器为 `https://github.com/ran-j/PS2Recomp`。`fetch` 阶段克隆该 commit，再按文件名顺序应用 `engine/patches/*.patch`，当前共 90 个补丁文件。runtime 内部分四块：`PS2Recomp/`（ran-j 的 MIPS R5900→C++ 静态重编译器 `ps2xRecomp`，与原生运行时 `ps2xRuntime`、`ps2xIOP`；经 Waffle565 扩展原生 GS 渲染器、原生 VU1／IOP 代码、声音、手柄、记忆卡，叠加 KIexster 的补丁栈与 YYOzcan 的 Tobiichi 改动）、`src/`（本作覆盖层）、`config/`（重编译配置与函数表）、`tools/`（VU1／IOP 原生代码生成器）。仓库实测 196 个 `.cpp`、195 个 `.h`；顶层含 `AGENTS.md`、`PS2_PROJECT_STATE.md`、`GODOFWAR.TOC`、`SYSTEM.CNF`、`port/`、`game/`、`tests/`、`tools/`、`launcher/` 等。
90 个补丁按序数命名，原因很直白：它们改的是别人的代码，必须能随时重放、随时丢弃。补丁头部的注释行写明"是什么、为什么"，`git apply` 会忽略它们，所以注释同时是文档。按主题分成工程、正确性、重编译质量、VU1、GS、产品与系统六类；逐条的问题—方案—代价—测量是第 7 章的任务，此处只立分组逻辑。
许可结构要单独算一段：runtime 与它的上游全部 GPL-3.0，本仓库自己写的编排层（Python／PowerShell／C++／QML）与之分离，`CREDITS.md` 逐个列出作者与来源。这不是法律脚注，是架构约束——它决定了本仓库不能把 runtime 抄进来改干净，只能打补丁、只能 pin commit、只能在 `fetch` 阶段重放；也决定了发布包里"不含 runtime"。讨论"为什么不 fork 一份改干净"，答案同时是工程的（重放成本、与上游同步）和许可的（派生边界与署名链）。
仓库自身只做五件事：游戏档案（profile）、光盘工具、构建流水线、启动器、安装器与文档。全书第一个论点在这里立住：**能参数化的绝不硬编码，能外部化的绝不内嵌**。游戏相关的一切——ELF 名、CRC、`.text` 的 SHA-1、runtime 内路径、光盘布局、版本与翻译、优化脚本、语言判据——全在 `games/gow1/game.toml`；`tools/pipeline/profile.py` 把它读成 Python 字典或 JSON，供 PowerShell 与启动器共用。档案是唯一事实源，任何一层重复写死一个游戏常量都视为缺陷。启动器侧 Qt 源码钉 6.8.3（qtbase、qtshadertools、qtdeclarative，按 SHA-256 校验），构建 SDK 前应用 `tools/pipeline/compat/` 的源码兼容适配；安装器则是 1352 行 Win32 + GDI+ 单文件自包含 exe，用 LZMS 块追加进自身、`/S` 静默契约，见第 9 章。
一个值得点破的对照：PS2Recomp 生态里存在可选的 `.recomp.json`，第三方清单（如 `recomp.board`）读它来判别游戏、系统与状态，而 PS2Recomp 本身不读、没有它也照常工作。也就是说，`games/gow1/game.toml` 不是上游强加的格式，是编排层自己加的契约；它的读者是 `profile.py`、PowerShell 与启动器，不是重编译器。把"描述文件"和"重编译器输入"分开，是这套仓库能同时服务 18 个阶段与两套平台的前提。

### 1.5 拿到仓库，先读这三个文件

> **工程判断（非仓库规定，可反驳）**
> 1. `games/gow1/game.toml` —— 唯一事实源。先读它，才知道后面所有路径、判据、脚本从哪来；`profile.py` 是它的读取器。
> 2. `engine/runtime.toml` —— 仓库与 runtime 的边界。一个 commit hash 加一个补丁目录，解释了为什么本地看不到那 196 个 `.cpp`。
> 3. `tools/pipeline/build.ps1` —— 86 行的入口。实现分给 `modules/`：`common` 62、`context` 77、`toolchain` 41、`process` 67、`runtime` 95、`game` 281、`optimize` 159、`verify` 33、`distribution` 100、`qt` 101、`build-progress` 27 行。它的价值不是代码，是 18 个阶段名：`tools`、`fetch`、`xdelta`、`discs`、`vu1disc`、`configure`、`recomp`、`sync`、`build`、`pgo`、`pgo-check`、`tune`、`optimize`、`native`、`verify`、`launcher`、`package`、`installer`（依赖图见第 5 章）。
> 第四眼我会放 `CREDITS.md`：在读 `src/` 任何一行之前先知道这行代码归谁。可反驳条件：若目标是修一个 VU1 边界 bug，前三个文件应换成 `config/` 的函数表、`vu1n_heads.txt` 与 `tools/vu1/` 下的生成器；上面的排序只对"第一次通读"成立。

### 1.6 三条对照轴的小结

**纵向**（档案 → 光盘 → 生成 → 构建 → 运行）：`game.toml` 是输入契约，`discfs.py` 把任意字节收敛成可校验中间态，`recompile.py` 用 `.text` 摘要决定复用（内容寻址（content-addressed），见第 6 章），`build.ps1` 把 18 个阶段串成单一写者，`ps2EntryRunner.exe` 只认一个目录。每一步的输出都是下一步的判据，没有一步靠"运行时再看看"。
**横向**（Windows／Linux，USA／欧洲／日本／亚洲）：`bash build.sh` 走 `tools/pipeline/linux.py`（262 行，Python 3.12+、原生 Clang、系统或 SDK Qt 6.5+、SDL2），共享同一份档案、光盘准备、事务式重编译器与序数补丁链，用 flock 持 `data/pipeline.lock`，产物在 `data/build-linux/<game>`；但 Windows 的构建根、便携工具、PGO profile 一律不复用。`C:\gow-build` 必须短、Linux 用 `data/build-root-linux.txt`，是同一条"归属校验"决策在两格里的不同写法（见第 5、10 章）。亚洲二版 `SCAJ_973.99` 的引导程序与日版逐字节相同，故 `code = "japan"` 直接复用日版构建、光盘数据仍归自己（见第 3 章）；USA 与异码 ELF 的关系则是区域矩阵里最硬的一格：宁可多一套构建，也不做"一套代码兼容所有区域"的赌博。Linux 的 PGO／自动录制、IOP 训练、便携依赖打包与二进制更新是**未实现**，GPU 路径是**已编译但未验证**，`vu1disc` 是**已实现但覆盖不全**，三种措辞不可互换（见第 10 章）。
**深度**（能跑／跑对／跑快／跑稳）：EE 到"跑快"，VU1 到"跑快但边界未闭合"，GS 到"跑稳"，IOP 到"跑对"，原生服务到"能跑"。下一级门槛分别是：VU1 补齐间接跳转入口、GS 继续压环溢出与深度一致性、IOP 把训练与输出确定性扩展到 Linux。

> **工程判断（非事实，带可反驳条件）**
> 如果让我重做，我会把 `engine/runtime.toml` 的单键 pin 升级成"commit + 补丁栈摘要"双键：90 个 `engine/patches/*.patch` 的文件名与内容摘要一并入档，`fetch` 在补丁增删或改序时立刻失败，而不是静默产出形状不同的 runtime。理由是 `pgo` 的 profile 已对源码形状敏感（`pgo-check` 校验清单、覆盖率、编译标志、无 profiling runtime 残留，见第 5 章），pin 却只锁住上游、没锁住本地补丁栈，两者强度不对等。代价：每次增删补丁都要多改一处元数据，且 `pgo-check` 的清单校验可能已部分覆盖这件事。可反驳条件：若 `pgo-check` 的清单字段已经逐文件覆盖补丁栈，双键就是冗余，正确做法是复用它的清单而不是再加一份真相源——那反而违反 1.4 立下的"唯一事实源"。

本章结论：这不是"更快的模拟器"，而是一次把 EE 指令在构建期搬进 C++、把其余四条流水线交给原生服务的分工；分工线由 GPL-3.0 边界、pin 住的 commit 和 90 个可重放补丁共同固定，因此仓库只能是不含 runtime 的编排层，`games/gow1/game.toml` 只能成为唯一事实源。代价可核查：身份收窄到 `.text` SHA-1、每语言一目录、优化产物必须重训、60 Hz 上限被继承。遗留疑问有三：约 6,400 个函数这一约数未按函数表核实；`vu1disc` 从 VIF MPG 上传抽取微码的覆盖率没有量化边界；Linux GPU 路径"已编译但未验证"缺一份可复现的验证路线（见第 8、10 章）。

## 第 2 章 仓库解剖与一次运行的全链路

本章回答五个问题：顶层每个目录各管哪一段、边界靠什么维持；一份用户自带的 ISO 从进入工具链到 `ps2EntryRunner.exe` 被拉起，中间每一步的输入输出契约是什么；`.disc_layout`、`mc0/` 与覆盖层匹配共同构成的运行目录物理约定如何生效；启动器上的一个勾选框最后怎样变成引擎读到的环境变量；以及失败时错误究竟从哪一层冒出来、该读哪一行日志。

### 2.1 目录职责表：边界比文件数更重要

顶层出现的名字有 `AGENTS.md`、`PS2_PROJECT_STATE.md`、`GODOFWAR.TOC`、`SYSTEM.CNF`、`port/`、`game/`、`tests/`、`tools/`、`launcher/`。它们不按"源码／资源"分类，而按"谁生成、谁消费"分类。

| 路径 | 职责 | 由谁写 | 由谁读 | 是否进发布包 |
| --- | --- | --- | --- | --- |
| `games/gow1/game.toml` | 游戏档案（profile），唯一事实源 | 维护者 | `tools/pipeline/profile.py`、PowerShell、启动器 | 随编排层 |
| `tools/pipeline/profile.py` | 把档案读成 Python 字典或 JSON | 维护者 | 流水线与启动器共用 | 是 |
| `engine/runtime.toml` | pin 仓库与 commit `471c83180a8df575cff4abd3fae6c043b5096925`（2026-10-16） | 维护者 | `fetch` 阶段 | 是（元数据） |
| `engine/patches/*.patch` | 90 个按文件名顺序应用的补丁 | 维护者 | `fetch` | 是 |
| `tools/disc/` | 格式层与导入层：`discfs.py`、`identify.py`、`prepare.py`、`iso_extract.py`、`chd.py`、`vu1_from_disc.py` | 维护者 | `discs`／`vu1disc` 阶段 | 是 |
| `tools/pipeline/` | 18 阶段编排，`build.ps1` 86 行 + `modules/` 共 11 个模块 | 维护者 | 启动器、安装器、终端 | 是 |
| `tools/pipeline/compat/` | 构建 Qt SDK 前的源码兼容适配，现有 `qt-sequence-sort.h` | 维护者 | `qt` 阶段 | 是 |
| `tools/test/` | 约 40 个测试脚本与 C++ 单测 | 维护者 | `verify` 阶段 | 是 |
| `launcher/` | Qt 6 启动器：播放侧与安装侧 | 维护者 | 用户 | 是 |
| `installer/setup.cpp` | 1352 行 Win32 + GDI+ 自包含安装器 | 维护者 | 用户 | 是（单 exe） |
| `docs/` | 契约：`architecture.md`、`disc-import.md`、`linux.md`、`saves.md`、`translations.md`、`adding-a-game.md`、`input-accessibility.md`、`reporting-bugs.md`、`tested-hardware.md` | 维护者 | 维护者 | 是 |
| `docs/research/` | 25 篇按日期归档的研究与交接文档 | 维护者 | 维护者 | 归档，不作契约 |
| `port/`、`game/`、`tests/`、`tools/`、`launcher/` | runtime 顶层可见的同名类别目录 | runtime（外部） | runtime | 否 |
| `GODOFWAR.TOC`、`SYSTEM.CNF` | 光盘侧元数据样本／引导配置 | 盘／runtime | 识别与档案比对 | 否 |
| `CREDITS.md` | runtime 及上游作者与 GPL-3.0 许可清单 | 维护者 | 发布合规 | 是 |
| `data/` | 全部中间态：`pipeline.lock`、`build-root.txt`、`_tmp`、`_tools`、`imports/chd`、`<id>/discs/*`、`languages.json`、共享 `mc0`、`<id>/pgo/gow.profdata` | 流水线独占写 | 启动器、卸载器、流水线 | 否 |

`package` 阶段明确排除 runtime，理由与许可结构在第 1 章已立（GPL-3.0 分离、pin commit、补丁重放），此处只重复一句结论：本地看到的 196 个 `.cpp` 与 195 个 `.h` 属于 fetch 之后才存在的外部 checkout，不属于本仓库。runtime 内部四块——`PS2Recomp/`（ps2xRecomp、ps2xRuntime、ps2xIOP 及各家扩展）、`src/`（`gow_overrides.cpp`、`gow_pad2_packet.h`、`gow_gs_replay.h` 等覆盖层）、`config/`（`recomp.template.toml`、`funcmap.csv`）、`tools/`（VU1／IOP 原生代码生成器）——的逐层分工见第 1 章与第 6 章。
目录职责表里最该被记住的一格是 `data/`：它同时是缓存、产物、锁、临时目录和构建根登记处。`build.ps1` 把 `$env:TEMP`／`$env:TMP` 指向 `data/_tmp`，便携工具一次下载并按 SHA-256 校验后落在 `data/_tools`；`data/pipeline.lock` 以独占方式打开，第二个流水线直接失败并提示"另一个流水线正在使用这个 checkout"（单写者语义见第 5 章）。把中间物全部收进一个目录，是"失败可定位"的前提：出问题时先看 `data/`，不要去系统盘找。

### 2.2 从 ISO 到 `ps2EntryRunner.exe`：逐步契约

纵向数据流是"档案 → 光盘 → 生成 → 构建 → 运行"。下表只列契约，不展开实现；阶段依赖图、工具链钉版本与输出协议属第 5 章，内容寻址与事务发布属第 6 章，TOC 24 字节条目与 CHD 导入属第 4 章。

| # | 阶段／工具 | 输入 | 输出 | 下一手是谁 |
| --- | --- | --- | --- | --- |
| 0 | 用户 | 自己合法持有的 PS2 美版盘 `SCUS-97399` | ISO／CHD 文件路径 | `instalar.cmd`／启动器 |
| 1 | `tools/disc/discfs.py` | ISO／已解包目录／TOC／ELF | 统一格式层视图，格式说明写在模块 docstring | `identify.py` |
| 2 | `identify.py` | 格式层视图 + `game.toml` | JSON：`{game, edition, language, compatible, problems}` | `prepare.py`、启动器 |
| 3 | `prepare.py` | 识别结果 | `data/<id>/discs/*`、`languages.json`、共享 `mc0` | `recomp`、运行 |
| 4 | `iso_extract.py`（Waffle565） | 光盘映像 | `.disc_layout`、`.disc_meta` | 运行期路径解析 |
| 5 | `fetch` | `engine/runtime.toml` + 90 个补丁 | pin 住的 runtime checkout | `configure`／`recomp` |
| 6 | `tools/pipeline/recompile.py`（254 行） | `.text` SHA-1、模板、函数表 | 内容寻址的 EE 生成物，成功以目录事务发布 | `sync` |
| 7 | `sync` | 生成物 + 档案里的 overrides | 只拷变化文件，把 overrides 送进 runner | `build` |
| 8 | `build`／`pgo`／`native`／`launcher` | 生成物、profile、原生 VU1／IOP 代码 | `ps2EntryRunner.exe` 与启动器 | `package`／`installer` |
| 9 | 运行 | `ps2EntryRunner.exe <disc 目录>/SCUS_973.99` | 游戏 | — |

第 0 步的入口在仓库说明里是真实命令：

```text
instalar.cmd -Iso "D:\path\God of War.iso"
```

`-SinOptimizar` 跳过优化步骤，`-Optimizar` 之后可补跑。README 还写明仓库 contains no game files（ISO、executable、IRX modules、`.PAK` data），也不含由它们生成的代码，安装器 builds everything on your computer from your own disc image。这条约束不是措辞客气：`identify.py` 的输出里带 `compatible` 与 `problems`，就是让"这张盘能不能进流水线"在写盘之前被判掉（两字段的区别见第 4 章）。
第 1 步之所以要单独一层，是因为输入不可信：ISO 是任意字节，CHDv5 DVD 与单 MODE1 轨又由 `chd.py` 处理，外部工具版本钉在 `toolchains.json[disc_import]`（chdman 0.289，带 exe 级 SHA-256，以及 7zr）。`discfs.py` 把它们收敛成同一种视图后，识别才是纯函数。"识别是纯函数、准备阶段才写盘"这个次序，是全书后面所有可重入性的来源（见第 4 章）。
第 3 步的 `languages.json` 值得单独点一句：它记录的是"哪些语言目录已经备好"，而不是一个运行期开关。因为整套运行模型没有运行期语言切换——每个语言一个光盘目录，切换语言等于换一个目录传给 runner（见 2.3）。
第 6 步的 docstring 就是设计声明：内容寻址（content-addressed）的 EE 生成、所有权感知（ownership-aware）同步、成功以目录事务（directory transaction）发布、失败保留上一份可用产物、复用由摘要而非时间戳决定；并且绝不把游戏数据缓存到 `data/` 之外。`replace_file` 对 Windows 扫描器／索引器的短暂占用做 6 次有界重试，仍失败才报错。第 6 章展开，此处只记它在这条链上的位置。

### 2.3 运行目录的物理约定

运行期命令行只有一行：

```text
ps2EntryRunner.exe <disc 目录>/SCUS_973.99
```

**ELF 所在目录即 CD 根**。这一句拆开有五层含义。
**一，没有挂载。**​ 没有虚拟光驱（virtual drive）、没有 ISO 挂载。runner 拿到的第一个参数是一个文件路径，它把该文件所在目录当成光盘根去做路径解析（path resolution）。所以"换语言"在物理上就是换目录，不是改配置。
**二，`.disc_layout` 是扇区表，不是 ISO 镜像的副本。**​ 它按扇区列出每个文件，且允许文件超出光盘实际末端。后半句是这条设计里最有信息量的一处：说明它不是对原盘元数据的镜像，而是一张供运行期解析用的表——准备阶段可以往里登记替换／新增文件而不必重刻映像（**推断**：依据是 `.disc_layout` 由 `iso_extract.py` 写出、与 `.disc_meta` 并列，且 `[disc]` 里存在 16:9 影片扩展名 `.PSW` 与 `.PSS` 的回退关系；仓库未直接写明"表可追加"）。`.disc_meta` 与之并列，承担盘级元数据；二者分工的精确边界此处事实不足，需在 `iso_extract.py` 处补测。
**三，记忆卡有两处呈现。**​ 同目录 `mc0/` 是记忆卡；README 另写 saves go to `game/Mcd001.ps2`，是 PCSX2 兼容的卡映像，可以把 PCSX2 记忆卡复制到那里。环境变量里同时存在 `GOW_SAVES_DIR` 与 `GOW_MC0`，`prepare.py` 又产出共享 `mc0`（**推断**：依据是这三个事实并列，且 `[disc]` 的共享记忆卡与 `data/<id>/discs/*` 同批产出）。据此我的读法是：共享卡放在准备产物层，运行时的 `mc0/` 与 `game/Mcd001.ps2` 是同一记忆卡服务在目录侧的两种入口，具体覆盖优先级需在 `saves.md` 处核实。可反驳条件：若 `GOW_MC0` 直接指向 `Mcd001.ps2` 而 `mc0/` 只是目录名，则"两种入口"的说法应改成"一个文件、一个目录别名"。
**四，覆盖层按 ELF 名匹配。**​ `src/` 里的 `gow_overrides.cpp` 等在 `loadELF` 阶段按地址替换 EE 函数绑定，只对这一份 `SCUS_973.99` 生效；区域构建的条件性覆盖层另放 `games/gow1/regions`，绝不能应用到 USA runtime，也不能进全局序数补丁链（见第 3、10 章）。按 ELF 名匹配而不是按 CRC 匹配，是这里的关键：档案里的 `crc = "D6385328"` 用于识别盘，运行期的覆盖层绑定用的是可执行文件名。两者作用域不同，混用会把区域隔离打穿。
**五，影片与布局的零分支。**​ 原始影片在原盘可用时保持原样，16:9 影片缺失时映射到 `.PSS`；`[disc]` 里还定义 `GODOFWAR.TOC` 的 24 字节条目（`name[12]`、`u32 part`（0 = PART1.PAK，1 = PART2.PAK）、`u32 size`、`u32 sector`）、两个 PAK、`IOP_MOD` 目录、`R_PERM.WAD` 与 `R_SHELL.WAD` 中的翻译文本，以及按精确字节识别的占位影片（`size = 16388` 加 sha256）——PT-BR 独立版的 `SEMO01.PSW` 是永远播不完的缩减版，用尺寸阈值会误杀合法短片，所以判据必须是"这一份字节"（见第 3、4 章）。
代价在磁盘：每语言一个完整目录，不做增量共享。收益在运行期：引擎不需要判断"当前是哪个语言、要不要换文件"，故障定位变成"哪个目录、哪个文件"，而不是"哪个开关没关"。这条交换的边界条件是：若某个语言目录只改了少数文件，磁盘放大倍数等于目录内文件数除以改动数；仓库没有给出该比值，此处事实不足，需在 `prepare.py` 产物上补测。
另外两条与运行体验直接相关、但不属于流水线的约定：键盘鼠标是默认布局、可在启动器里重映射；热键 F2 cheat menu、F11 fullscreen、F1 developer panel；DualShock 4、DualSense、Xbox 等手柄开箱即用（Windows 上有振动）。游戏逻辑绑 60 Hz VBlank，移植体保持真实速度，掉帧而不减速——所以 2.5 节里"帧率异常"的判定必须先看客机帧（见第 3 章）。

### 2.4 启动器如何把设置变成环境变量

启动器是 Qt 6，源码钉 6.8.3（qtbase、qtshadertools、qtdeclarative，按 SHA-256 校验，一次构建进 `data/_tools`，构建 SDK 前应用 `tools/pipeline/compat/` 的适配）。播放侧 `lanzador.cpp` 914 行用西班牙语命名，安装侧 `installer_backend.cpp` 547 行用英语命名，另有 `mods_model.cpp` 807 行、`session_diagnostics.cpp` 463 行、`main.cpp` 134 行、`mando.cpp` 147 行。QML 侧 `Main.qml` 是侧边栏加页面，`pagina` 0 主页、1 安装、2–6 设置、7 存档、8 无障碍；`AccessibilityPage.qml` 管输入辅助、纹理包与视觉 mod；配色集中在 `Tema.qml` 的 `oro*` 系列（承载绯红强调色）。页面细节属第 9 章，本节只讲一条映射：**页面上每个设置最终都变成 `GOW_*` 环境变量，UI 与引擎之间没有第二套配置系统**。
这个"没有第二套"是刻意的。若启动器自己维护一份配置、引擎再读一份，两份必然漂移；现在启动器的职责被压成"生成环境变量并拉起进程"，引擎只认环境变量，档案只由 `profile.py` 读成 Python 字典或 JSON 供 PowerShell 与启动器共用。三层的读者相同、写法不同，但事实源只有一个（第 1 章）。
环境变量按诊断面分组如下，全部来自基座，无一为杜撰：

```text
# 窗口与音频
GOW_WINDOW_HIDDEN  GOW_AUDIO  GOW_AUDIO_DEVICE  GOW_AUDIO_PCM
# VU1
GOW_VU1_FAST  GOW_VU1N_JIT  GOW_VU1N_DIAG  GOW_VU1_CAPTURE_MISSES
# GS 与呈现
GOW_GS_EARLY_FINISH  GOW_GS_FINISH_ASINCRONO  GOW_GS_STAGE_SPIN_US
GOW_SCALER  GOW_ANISO  GOW_SHARPEN
# mod 与纹理
GOW_TEXTURE_PACK  GOW_MOD_VFS_TABLE  GOW_MOD_PATCH_TABLE  GOW_MOD_VFS_LOG
# 输入辅助
GOW_QTE_HOLD  GOW_QTE_HOLD_HZ
# 路径与启动
GOW_SAVES_DIR  GOW_MC0  GOW_ISO  GOW_SKIP_FMV  GOW_FAST_BOOT
# 测量与诊断
GOW_PERF_DIAG  GOW_PERF_FRAME_PC  GOW_PGO_REVISION
GOW_DISPATCH_FULL  GOW_IOP_DRIFT  GOW_SYNC_DIAG
```

`optimize` 阶段用的是其中一组具体取值，可直接对照：

```text
GOW_WINDOW_HIDDEN=1
GOW_AUDIO=0
GOW_AUDIO_PCM=NUL
GOW_VU1_CAPTURE_MISSES=1
GOW_VU1N_X64=1
GOW_PAD_GUION=<脚本>
```

隐藏静音窗口里让游戏自己跑 240 秒，`[optimize]` 的手柄脚本是 `5:start,12:x,18:x,24:x,30:x,36:x,40:cuadrado,…`（西班牙语按键名，见第 3 章）。注意 `GOW_PAD_GUION` 与 `GOW_VU1N_X64` 出现在优化命令里、却不出现在上面那份通用诊断面清单里；这说明清单是"主要开关"而非全集（**推断**：依据是基座对环境变量表的措辞为"值得列成表"，未声明穷尽）。维护时若要据此写死配置校验，会漏项。
这些开关不是给玩家看的，是诊断面：出问题时通过"打开哪个开关、看哪一行日志"把范围二分。例如 `GOW_GS_STAGE_SPIN_US` 默认 50，0 表示立刻睡，配合 44 号补丁的字节环使用（见第 7 章）；`GOW_PERF_FRAME_PC` 与档案的 `frame_pc = "0x1837B8"` 对应 `vid::Flip`，用来数客机帧（见第 3 章）；`GOW_MOD_VFS_LOG` 对应 71 号 mod VFS 钩子与 84 号 mod 数据补丁（见第 7、8 章）。UI 上一个开关、引擎里一个环境变量、日志里一行可观测信号——三者是一件事的三种写法，这正是"没有第二套配置系统"的收益。

### 2.5 失败从哪一层冒出来

`build.ps1` 顶部的 `trap` 把异常打印成 `ERROR: <消息>` 并以退出码 1 结束，所以启动器只需要抓这一行就能区分"失败"与"仍在跑"。其余输出按一套纯文本协议分三类：

```text
=== <step> ===        # Step 输出的阶段边界，也是进度条的分母来源
@@progress <done> <all>   # 机器读的分子／分母
@@status <text>       # 人类可读的当前动作
```

`LoadingScreen.qml` 在长任务时覆盖全屏，按这套协议显示总进度、剩余时间与 `cargaDica1..N` 提示，还能读玩家自己放进 `data/<id>/loading` 的图片。协议是文本而不是 IPC，好处是"终端跑一遍"和"启动器跑一遍"共用同一条路径；代价是解析脆弱、文案即接口（第 5 章展开依赖图与进度模型，第 9 章展开 LoadingScreen 本身）。
按"症状—真实原因—判定方法—修复"四段式写三类最常见的误判：
**症状一：流水线一启动就报"另一个流水线正在使用这个 checkout"。**​ 真实原因是 `data/pipeline.lock` 的独占打开，另一个终端或启动器还在跑同一份 checkout，缓存与生成物不能并发更新；不是构建坏了。判定方法：看是否存在第二个 `build.ps1`／`LoadingScreen.qml` 进程，锁文件的持有者即写者。修复：等那一个结束，或换一份仓库副本（副本会拿到 `C:\gow-build-<hash>`，选择写进 `data/build-root.txt`）。把锁冲突当构建故障去改编译器参数，只会把 `-Toolchain` 的错误别名 `msvc` 也试一遍——组件一律用钉死的 llvm-mingw。
**症状二：链接／依赖阶段报路径过长。**​ 真实原因是 runtime 的 CMake 依赖是 git checkout，长路径必撞 MAX_PATH，不是编译器问题。判定方法：看构建根是否为 `C:\gow-build`（RelWithDebInfo 用 `C:\gow-build-dev`）。修复：换 `-BuildRoot`。同一台机器上第二份仓库副本用 `C:\gow-build-<hash>`，登记在 `data/build-root.txt`，启动器与卸载器都读它；启动器接受 runner 前还会核对 CMakeCache 的源目录，防止新副本误用旧副本的构建（第 5 章展开）。
**症状三：`pgo-check` 失败。**​ 真实原因是 profile 与本次编译标志或源码不匹配，不是"PGO 没效果"。判定方法：`pgo-check` 校验清单、覆盖率、编译标志、无 profiling runtime 残留；`data/<id>/pgo/gow.profdata` 是 `pgo` 的产物，二次构建才使用它。修复：重训。任何一次 runtime 或补丁变更都必须重训，否则 profile 指向不存在的形状（第 5、6 章）。
还有一类不属于误判、但常被混写的区分：`verify` 阶段不需要 ISO 也能跑，把"回归"从"要有光盘"里解耦；`tools/test/` 下约 40 个脚本与 C++ 单测（含 `pipeline_tests.py`、`guest_codegen_tests.cpp`、`guest_memory_tests.cpp`、`guest_calls.cpp`、`dma_worker_tests.cpp`、`qte_hold_test.cpp`、`sound_regression.cpp`、`vu1-equivalence.py`、`recompile-smoke.py`、`disc-import-ui.py`、`regional-play-ui.py`、`launcher-languages.py`、`loading-progress.py`、`verify_setup.py`、`perf-compare.ps1`、`build-progress-tests.ps1`、`patch-stack-tests.ps1`、`linux_pipeline_tests.py`）中，带 `-ui` 后缀的只能靠 UI 兜底（见第 10 章）。`GOW_SETUP_CAPTURE=<png>`、`TOBIICHI_CAPTURA=<png>` 与 `TOBIICHI_CAPTURA_PESTANA=<page>` 是截图自动化钩子，属于"让 UI 测试能被脚本判定"的接口，而非产品功能。

### 2.6 三条对照轴的小结

**纵向**：本章把 2.2 的九步压成一句契约链——`identify.py` 输出 JSON 契约，`prepare.py` 才写盘，`recompile.py` 用摘要决定复用，`sync` 只送变化文件，`ps2EntryRunner.exe` 只认一个目录。任何一步想"运行时再看看"，都会与"运行期零分支"冲突。
**横向**：Windows 侧 `instalar.cmd -Iso ...` 与 `data/build-root.txt`；Linux 侧 `bash build.sh` 走 `tools/pipeline/linux.py`（262 行，Python 3.12+、原生 Clang、系统或 SDK Qt 6.5+、SDL2），共享同一份档案、光盘准备、事务式重编译器与序数补丁链，用 flock 持 `data/pipeline.lock`，产物在 `data/build-linux/<game>`，启动器读 `data/build-root-linux.txt` 并按大小写敏感的 CMake 源目录归属校验——Windows 的构建根、便携工具、PGO profile 一律不复用。区域格上，本章只用到"每语言一个光盘目录"；`asia-97399` 的 `code = "japan"` 与 USA 拒绝异码 ELF 属第 3、10 章。
**深度**：本章覆盖的是"能跑"与"跑对"之间的接口层。下一级门槛是"跑快"：`optimize→native` 与 `pgo→pgo-check→tune` 两条闭环（第 5 章）、44 号字节环（第 7 章）、VU1 热入口（第 8 章）。运行目录本身没有性能优化空间，它的价值是把性能优化的基线固定成可复现的一个目录。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会给 `identify.py` 的 JSON 增加两个字段：一个 `layout_digest`，由 `.disc_layout` 的内容算出；一个 `profile_digest`，由 `game.toml` 的有效字段算出。理由是运行期把 `<disc 目录>` 当 CD 根、覆盖层按 ELF 名匹配，而目录是可被用户手工改动的——现在没有任何一层能证明"跑起来的这个目录就是 prepare 产出的那个目录"，于是 2.5 节的第二类误判会退化成玄学排查。代价：每次 `prepare.py` 都要多写一份摘要，启动器多一次校验，且摘要字段本身又变成需要维护的契约；`languages.json` 可能已经部分承担这个职责。可反驳条件：若 `GOW_ISO` 已经在启动时指向原始映像并隐含做了同等校验，加字段就是冗余，正确做法是把该校验显式写进 `docs/architecture.md` 而不是再加一份真相源——那与 1.4 立下的"唯一事实源"直接冲突。

本章结论：本仓库是一个目录职责清晰的编排层，`data/` 独占承接全部中间态；从 ISO 到 `ps2EntryRunner.exe` 的链路中，识别是纯函数、准备才写盘、生成按 `.text` 摘要复用、运行只认 ELF 所在目录，故没有虚拟光驱与运行期语言开关；启动器把每个设置坍缩成一个 `GOW_*` 环境变量，与引擎共用同一套配置；失败集中在 `trap` 的 `ERROR: <消息>`、`=== <step> ===`、`@@progress`／`@@status` 四个出口。条件是这套模型只在"目录不被外部改动"时成立。遗留疑问三处：`.disc_layout` 与 `.disc_meta` 的精确分工需在 `iso_extract.py` 处补测；`mc0/` 与 `game/Mcd001.ps2` 的覆盖优先级需在 `saves.md` 处核实；每语言一目录带来的磁盘放大倍数缺实测值，需在 `prepare.py` 产物上补测。

## 第 3 章 游戏档案的工程学

本章回答六个问题：`games/gow1/game.toml` 的每一节各自定义了什么契约、谁读它；`text_sha1` 为什么能当整套设计的身份支点、翻译版光盘凭什么自动兼容；`[[editions]]` 与 `[[regions]]` 怎样把"能不能识别"和"能不能跑"切开；`asia-97399` 的 `code = "japan"` 在什么条件下成立；整句语言判据、精确字节占位判据与 `frame_pc` 客机帧计数各自堵住了哪一类误判；以及 240 秒优化脚本里西班牙语按键名暴露了什么血统。

### 3.1 一份 TOML 如何吃掉所有分支

档案是唯一事实源（single source of truth）：游戏相关的一切——ELF 名、CRC、`.text` 的 SHA-1、runtime 内路径、光盘布局、版本与翻译、优化脚本、语言判据——全在 `games/gow1/game.toml`；`tools/pipeline/profile.py` 把它读成 Python 字典或 JSON，供 PowerShell 与启动器共用。第 1 章已立过这条边界，本章展开文件内部。
"吃掉所有分支"是字面意思：识别层判断这张盘是谁、准备层判断该写哪些目录、生成层判断能不能复用产物、运行层判断覆盖层绑不绑、UI 层判断版本选择器里放哪几项、优化层判断录多长与按什么键——六个消费者读同一份字典，没有一层另写一份常量。任何一层重复写死一个游戏常量都视为缺陷，这不是风格偏好，是因为这六个消费者里有两个（PowerShell 与启动器）连运行时都不共享，靠约定同步必然漂移。
读取链上有一处容易看漏：`profile.py` 输出的是字典或 JSON，而不是把 TOML 直接塞给各层。第 2 章写过 `identify.py` 输出 `{game, edition, language, compatible, problems}` 的 JSON 契约；两者不是同一份 JSON——前者是档案的静态投影，后者是某张具体光盘的识别结果（契约细节见第 4 章）。把这两份 JSON 混成一个，是接手这套代码时最常见的读错。
以下 TOML 片段均为事实基座给出的字段节选，非完整文件：

```toml
[executable]
name = "SCUS_973.99"
serial = "SCUS-97399"
crc = "D6385328"
text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"
```

```toml
[build]
unity_batch = 16

[diagnostics]
frame_pc = "0x1837B8"

[optimize]
seconds = 240
```

### 3.2 `[executable]`：身份四元组与 `.text` SHA-1 这个支点

四个字段不是四个并列属性，而是两个不同作用域的判据。
`name = "SCUS_973.99"` 是运行期匹配键：覆盖层按 ELF 名匹配（见第 2 章），单次运行写 `ps2EntryRunner.exe <disc 目录>/SCUS_973.99`。`serial = "SCUS-97399"` 是光盘序列号，README 用它标注"USA version, SCUS-97399"，也是用户判断自己那张盘对不对的第一道肉眼判据。`crc = "D6385328"` 采用 PCSX2 语义——ELF 全部 32 位字异或（XOR），用于识别"这张盘里的可执行文件是哪一份"。`text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"` 只覆盖 `.text` 段（section），用于决定"重编译产物是哪一份"。
支点在最后一个字段。`tools/pipeline/recompile.py` 从 `discfs` 借 `text_sha1`，用 sha256 做 key 做内容寻址（content-addressed）复用（见第 6 章）。因为重编译产物只依赖 `.text`，**任何只改数据的翻译版光盘都会编译出同一个程序**，翻译因此不必进白名单（allowlist）。把这条推到极限，得到一张判据表：

| 改动类型 | CRC（全 32 位字异或） | `.text` SHA-1 | 生成物 | USA 流水线 |
| --- | --- | --- | --- | --- |
| 只改数据：翻译文本、贴图、影片 | 变 | 不变 | 复用同一份 | 接受，不进白名单 |
| 改代码：日版 `CA052D22`、欧版 `FB0E6D72` | 变（与 `D6385328` 不同） | 变 | 需另一套 | 拒绝，走独立构建 |
| 改代码但代码与日版逐字节相同：亚洲二版 | 同日版 | 同日版 | 复用日版 | 经 `code = "japan"` 复用 |

第二行"`.text` SHA-1 变"是**推断**：依据是基座给出日版 `8ed48ca8…`、欧版 `FB0E6D72`，且声明"不同代码的 ELF 至今被 USA 流水线拒绝"；基座未逐版给出完整 `.text` 摘要值。第三行的"同 CRC、同 `.text` SHA-1、同尺寸"则是原文明确写出的三同。
条件必须写死：**在 `.text` 不变的条件下，翻译版不必进白名单；一旦某翻译版改了代码段（例如重写菜单逻辑），该结论立即失效**，USA 流水线会按异码 ELF 拒绝，而不是"翻译版优先兼容"。这条条件也是第 10 章讨论"支持第二款游戏"时的门槛之一。
CRC 与 SHA-1 的分工还解释了为什么两个字段都要留：CRC 便宜、PCSX2 语义现成，适合在 `identify.py` 里对一张任意字节的光盘做快速归类；SHA-1 精确到段，适合作为生成物的身份。若只留 CRC，改一个数据字节就会误判成"需要重编译 6,400 个函数"；若只留 SHA-1，识别层又失去了与 PCSX2 生态对齐的现成口径。

### 3.3 `[runtime]`：把外部 checkout 的路径也参数化

`[runtime]` 指向 runtime 内的模板 `config/recomp.template.toml`、函数表 `config/funcmap.csv`、三个覆盖层文件（2.1 给出的例子是 `gow_overrides.cpp`、`gow_pad2_packet.h`、`gow_gs_replay.h`）、VU1 生成器 `tools/vu1/generar_vu1.cpp` 与 `tools/vu1/vu1n_gen.py`、VU1 原生入口表 `vu1n_heads.txt`、IOP 生成器 `tools/iop/iopn_gen.py`。
这一节的工程价值不在"列了几个文件"，而在它把**别人的仓库内部路径**也变成了档案字段。runtime 由 `fetch` 阶段克隆 `https://github.com/YYOzcan/Tobiichi-Port` 的 commit `471c83180a8df575cff4abd3fae6c043b5096925`（2026-10-16）再按文件名顺序应用 90 个补丁得到（见第 1 章）；上游目录布局一旦调整，编排层只需要改这一节，不必去 11 个 `modules/` 里逐处改字符串。这正是"能外部化的绝不内嵌"在跨仓库边界上的落地。
`vu1_native_heads` 值得单列。它解决生成器找不到的块入口——寄存器间接跳转（register-indirect jump）：生成器能从录制到的 micro-memory 推出微码（microcode）块，但间接跳转的目标地址不在静态可分析范围里，必须靠入口表补。缺了它们，这些块只能在解释器里跑，5 秒船战里进出原生代码约 120 万次。把约数折算成两个刻度：

```text
1,200,000 ÷ 5 s          = 240,000 次／秒（约数，因为 120 万本身是约数）
5 s × 60 Hz              = 300 客机帧
1,200,000 ÷ 300 客机帧   = 4,000 次／客机帧（约数）
```

按 60 Hz 折算的第二个算式是本书第一次把"边界开销"钉到帧上：每个客机帧约四千次跨解释器／原生代码边界，问题不在算术吞吐，而在进出边界。第 8 章会接着讲热入口与链预热为何对船战关键；这里只记结论——**性能问题往往不是算术问题，而是边界问题**，而边界的补丁点就在档案的 `vu1_native_heads` 一行里。

### 3.4 `[disc]`：布局、翻译文本与"这一份字节"

`[disc]` 定义 `GODOFWAR.TOC` 的 24 字节条目、两个 PAK、IOP 模块目录 `IOP_MOD`、翻译文本所在 `R_PERM.WAD` 与 `R_SHELL.WAD`、16:9 影片扩展名 `.PSW` 与 `.PSS` 的回退关系，以及按精确字节识别的占位影片。TOC（table of contents）条目的字段宽度可以直接验算：

| 字段 | 宽度 | 含义 |
| --- | --- | --- |
| `name[12]` | 12 B | 文件名 |
| `u32 part` | 4 B | 0 = `PART1.PAK`，1 = `PART2.PAK` |
| `u32 size` | 4 B | 尺寸 |
| `u32 sector` | 4 B | 扇区 |
| 合计 | 12 + 4 + 4 + 4 = **24 B**​ | 与档案声明一致 |

格式层怎么读这 24 字节、PAK 怎么分片、ISO9660 扇区怎么对齐，是第 4 章的任务；本节只确认一件事：连"条目多宽"这种纯格式常数都写在档案里，而不是散在 `discfs.py` 的 docstring 之外。格式说明写在 `tools/disc/discfs.py` 的模块 docstring 里，档案负责声明本作用到的具体值，两层各管一半。
影片回退关系与第 2 章的运行模型对应：原始影片在原盘可用时保持原样，16:9 影片缺失时映射到 `.PSS`。档案里写的是"扩展名与回退关系"，运行期做的是"哪个目录、哪个文件"，中间不再有开关（见第 2 章）。
占位影片是本章最该精读的一处判据设计。PT-BR 独立版有一个永远播不完的缩减版 `SEMO01.PSW`，判据写成 `size = 16388` 加 sha256，而不是一个尺寸阈值：

```text
size = 16388        # 16384 + 4，仅作快速预筛
sha256 = <精确字节>  # 基座未给出原值，需在 game.toml 处补
```

理由是尺寸阈值会误杀合法短片：短片与占位片在"小"这一点上同形，只有字节内容能区分。于是判据必须是"这一份字节"，而不是"这一档尺寸"。这里能下一个带条件的判断：**在影片集合里同时存在合法短片与缩减占位片时，尺寸只能做预筛、不能做定案；若某张盘根本没有合法短片，尺寸阈值就够用，sha256 属于冗余校验**。基座只给了 PT-BR 独立版这一例，未提供其他盘的影片分布，因此"哪些盘可以省掉 sha256"此处事实不足，需在 `prepare.py` 产物上补测。
`[disc]` 还顺带把 `IOP_MOD`、`R_PERM.WAD`、`R_SHELL.WAD` 三个位置声明出来，使 `identify.py` 不必猜路径。**推断**：`R_PERM.WAD` 与 `R_SHELL.WAD` 是 3.7 节整句语言判据的搜索范围，依据是一节声明"翻译文本所在"、一节声明"判据用整句"，两者同属翻译识别；基座未写出二者的调用链。

### 3.5 `[build]` 与 `[diagnostics]`：一个旋钮和一条测量纪律

`[build]` 只有 `unity_batch = 16`。按统一构建（unity build）的通识，它决定每批合并的翻译单元数量（**推断**：依据是键名、以及第 5 章列出的 `-Config`、`-Ltcg`、`-CpuTarget portable|x86-64-v3`、`-Codegen locals|classic`、`-CompilerCache sccache|none` 全部由流水线参数掌握，档案未给出单位说明）。这个"只有一个键"本身就是判断：档案层不碰优化标志，优化标志归流水线参数与补丁栈（01 号 LTCG 默认不开、31 号 ThinLTO、32 号 AVX2 数学标志，见第 7 章）。把 `-Codegen classic` 之类的开关写进 `game.toml`，会让同一份档案在不同机器上产出不同程序，违背唯一事实源。
`[diagnostics]` 的 `frame_pc = "0x1837B8"` 是 `vid::Flip`，用来数客机帧（guest frame），与宿主呈现率（host presentation rate）区分开。第 1 章已交代游戏逻辑绑 60 Hz VBlank、移植体掉帧而不减速；这条配置背后是"帧率到底谁说了算"的测量纪律，本节展开。
测量链是：

```text
GOW_PERF_FRAME_PC / GOW_PERF_DIAG  →  vid::Flip 命中计数  →  客机帧率
客机帧率 = 命中次数 ÷ 墙钟秒数
例：60 s 内命中 N 次，则客机帧率 = N / 60（N 未给出，仅列算式）
```

`GOW_PERF_FRAME_PC` 与档案 `frame_pc` 的对应关系是**推断**：依据是两者同名片段、同属第 2 章列出的测量诊断面；基座未写明映射代码位置。宿主呈现率不进这个算式：它由呈现层决定（见第 8 章），`GOW_WINDOW_HIDDEN`、`GOW_SCALER` 都会改变它而不改变 `vid::Flip` 的语义。于是"隐藏静音窗口里跑 240 秒录微码"与"玩家全屏看到多少帧"是两个分母，不能互相折算。
这也解释了为什么 `perf-compare.ps1`、`build-progress-tests.ps1` 与 29a–29f 那族诊断补丁（会话帧计量、DMA 提交计量，见第 7 章）必须存在：没有统一的帧定义，44 号补丁那种"战斗 52.8 → 54.7 FPS"的对比就没有基线。**在把 `frame_pc` 固定为客机帧的前提下，跨机器、跨分辨率的帧率数字才可比较；一旦改用宿主呈现率，1× 与 8× 内部分辨率下的数字不可直接相减。**

### 3.6 `[[editions]]` 与 `[[regions]]`：识别与可跑性的分离

两个数组把"能不能识别"和"能不能跑"彻底分开。从条目字段看，`[[editions]]` 给的是"这张盘是谁"（ELF 名、CRC、`.text` 摘要），`[[regions]]` 给的是"用哪套构建跑它"（`code`、条件性覆盖层、基线源码哈希、函数区间与重编译入口提示）；这一分工是**推断**，依据是 `asia-97399` 的 `code = "japan"` 出现在区域条目里、而 CRC 出现在版本条目里，基座只用一句话点了"彻底分开"未逐字段指派。

| 条目 | 标识 | 判据 | 构建归属 |
| --- | --- | --- | --- |
| USA 原版 | `D6385328` | 与 `[executable].crc` 同值 | USA 流水线 |
| 日本 | `SLPM_670.10`／`CA052D22`／`8ed48ca8…` | 摘要以省略号截断 | 独立 Windows 构建，经"初始船战"验证 |
| 亚洲二版 | `SCAJ_973.99` | 引导程序与日版逐字节相同（同 CRC、同 `.text` SHA-1、同尺寸） | `code = "japan"`，复用日版构建；光盘数据仍归自己 |
| 欧洲 | `SCES_531.33`／`FB0E6D72` | 基座只给 CRC | 独立 Windows 构建 |
| `europe-alt`、两个 demo | 基座未展开字段 | — | 未给出 |

`asia-97399` 的 `code = "japan"` 为什么正确，要分两层答。**代码层**：三同意味着重编译输入逐字节相同，生成物、函数表、覆盖层绑定全部可复用；另起一套构建只会产出同一个程序，却多一个构建根要维护。**数据层**：光盘数据仍归自己，所以语言目录、贴图、影片按亚洲版走，不因复用构建而串味。首次启动时在日文 logo 上渲染出"新游戏／确定"，正好把两层切开给你看：本地化在贴图里，可执行文件仍是日文的。若把 `code = "japan"` 误读成"这张盘是日版"，就会把亚洲版的数据目录也并进日版目录，运行期零分支的前提当场破掉。
区域构建是独立子系统，不是 USA 流水线的参数分支。欧洲与日本各有经过"初始船战"验证的独立 Windows 构建；`games/gow1/regions` 存条件性 runtime 覆盖层、基线源码哈希、函数区间与重编译入口提示。这些覆盖层**绝不能**应用到 USA runtime，也不能进全局序数补丁链——90 个补丁改的是 `fetch` 出来的公共 checkout，区域覆盖层只对该区域构建生效，混进全局链等于给 USA 构建偷偷打了一份别人的补丁。`tools/pipeline/register_region.py` 把已验证的构建登记进 `data/<game>/regional-builds.json`，启动器校验归属、CMake 源目录与 ELF／runner 哈希后并入版本选择器（version selector）。
策略是硬的：不同代码的 ELF 至今被 USA 流水线拒绝——宁可多一套构建、多一个构建根、多一张记忆卡，也不做"一套代码兼容所有区域"的赌博。代价可以逐项算：每新增一个独立 `code`，至少增加一处构建根（`C:\gow-build-<hash>` 一类，见第 5 章）、一张 `mc0`、一条 `regional-builds.json` 校验记录、一组条件性覆盖层与基线源码哈希、一次"初始船战"验证路线；启动器的版本选择器与卸载器的 `/purge` 归属校验各多一个分支（见第 9 章）。测试矩阵按乘法增长：若每套 `code` 都要过 `verify`、区域回放与语言目录回放，用例数约为 `code 数 × 路线数 × 语言目录数`；基座未给语言目录总数与用例数，此处事实不足，需在 `data/<id>/discs/*` 与 `regional-play-ui.py` 处补测。

### 3.7 `[language_hints]`：整句而不是单词

`[language_hints]` 用整句（`"Novo Jogo"`、`"Nueva partida"`、`"Nouvelle partie"`…）而不是单词判断翻译语言，因为 `Difficulty` 这类词同时也是内部标识符，单词匹配必然误判。

| 判据 | 命中对象 | 误判来源 | 结果 |
| --- | --- | --- | --- |
| 单词 `Difficulty` | 本地化字符串 + 内部标识符 | 内部标识符与 UI 词同形 | 把非语言数据判成语言证据 |
| 整句 `"Nueva partida"` | 菜单项整串 | 需整串同时出现 | 只在真实本地化文本上命中 |

这是把"判据的特异性"提到与数据分布匹配：WAD 里既有给玩家看的句子，也有引擎自己用的标识符，二者的字符集重叠，只有句子长度能把它们分开（**推断**：依据是基座给出 `Difficulty` 这一反例与三个整句样例，未给出 WAD 内部布局）。判据输出进入 `identify.py` 的 `language` 字段，再影响 `prepare.py` 产出哪些语言目录（见第 2、4 章）。条件也清楚：**整句判据只在翻译确实改写了菜单整串时成立；若某语言版只替换了词库里的孤立词条而保留英文整句，整句匹配会漏判**，此时需要的是另一条判据而不是把整句放宽成单词——放宽会一次性把 `Difficulty` 那类误判全放回来。

### 3.8 `[optimize]`：240 秒、一个脚本、两种用途

`[optimize]` 给 `seconds = 240` 与一段手柄脚本：

```text
5:start,12:x,18:x,24:x,30:x,36:x,40:cuadrado,…
```

基座原文以省略号截断；脚本里另用西班牙语按键名 `triangulo`、`circulo`。它既用于录制，也用于 PGO（profile-guided optimization）训练：`optimize` 阶段在隐藏静音窗口里让游戏自己玩 240 秒，录下 VU1 微码与 IOP 模块（环境变量取值见第 2 章）；`pgo` 产出 `data/<id>/pgo/gow.profdata` 后二次构建；`tune` 用一次 `-O1` instrumented 构建同时收微码与 profile（闭环差别见第 5 章）。同一段脚本喂两条闭环，是为了让训练轨迹与录制轨迹同形——**产物训练产物**，因此任何一次 runtime 或补丁变更都必须重训。
按键名是本章最容易被当成笔误的细节：`cuadrado`（□）、`triangulo`（△）、`circulo`（○）是西班牙语，而脚本前缀里的 `start`、`x` 是英语／符号。这暴露了 runtime 的血统：它从南美社区项目长出来，命名不是英语。读代码的人必须知道这一点，否则会把 `cuadrado` 当成拼写错误去"修正"成 `square`，而 `GOW_PAD_GUION=<脚本>` 传的是原串，改一个词整段脚本就按不到键，`optimize` 会在 240 秒里录出一条空轨迹，`pgo-check` 随后以覆盖率不足失败（第 5 章）。

> **工程判断（非仓库规定，可反驳）**
> 我会给 `[optimize]` 的脚本加一个 `script_sha256` 字段，并让 `pgo-check` 的清单校验顺带核它。理由是 240 秒录制与 `gow.profdata` 都绑死在这串按键上，`pgo-check` 已经校验清单、覆盖率、编译标志、无 profiling runtime 残留，却没有任何一层能证明"这次训练跑的就是档案里那串脚本"；手改一个 `cuadrado` 不会立刻报错，只会在覆盖率上以间接方式暴露。代价：每次调脚本都要改两处，且又多一份需要维护的摘要——这恰好违反 1.4 立下的唯一事实源，所以更好的做法是把脚本本身收进 `pgo-check` 已有的清单，而不是另开字段。可反驳条件：若 `pgo-check` 的"清单"已经逐项包含 `[optimize]` 的有效字段，加字段就是纯冗余，正确动作只剩把它写进 `docs/architecture.md` 说清楚。

### 3.9 三条对照轴的小结与一处重做判断

**纵向**：档案 → 光盘 → 生成 → 构建 → 运行这条链上，本章补齐了每步的判据出处。`[executable].text_sha1` 进 `recompile.py` 的 sha256 key（第 6 章）；`[disc]` 的 TOC 24 字节与 WAD 位置进 `discfs.py`／`identify.py`（第 4 章）；`[runtime]` 的路径进 `fetch` 后的 checkout；`frame_pc` 进测量链；`[optimize]` 的脚本进 `optimize`／`pgo`／`tune`；`[[regions]]` 的 `code` 进版本选择器。每一步的输入都能在 `game.toml` 里找到字段，没有一步靠"运行时再看看"。
**横向**：Windows／Linux 共享同一份档案、光盘准备、事务式重编译器与序数补丁链（`bash build.sh` → `tools/pipeline/linux.py`，见第 2、10 章），但 `[build].unity_batch = 16` 与 `[diagnostics].frame_pc` 是平台无关的静态字段，Windows 的 `C:\gow-build`、便携工具与 PGO profile 一律不进 Linux 复用。区域格上，USA／欧洲／日本是三套 code，亚洲二版靠 `code = "japan"` 寄生在日版 code 上却保留自己的数据目录；这是四条区域条目里唯一一条"识别独立、构建复用"的格子，也是矩阵里最容易被误读成"日版"的一格。
**深度**：`[[editions]]` 停在"能跑"的入口判据，`[[regions]]` 停在"跑对"的归属判据，`[diagnostics].frame_pc` 与 `[runtime].vu1_native_heads` 已经指向"跑快"的门槛（约 4,000 次／客机帧的边界开销），`[disc]` 的精确字节占位判据则属"跑稳"——它防的不是算错，是某张盘上永远播不完的影片把流程挂住。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会把占位影片判据从"`size = 16388` 加 sha256"改成文档上明确的两段式：**尺寸只作预筛、sha256 定案**，并把 16388 从"判据"降级为"快速跳过用的提示值"。理由是现在两个字段并列写在档案里，维护者很容易把 `size` 当成第二判据去调阈值，而 3.4 节已经写明尺寸阈值会误杀合法短片。代价：多一段契约文字，`identify.py` 的实现要显式分两阶段，且若某个合法短片恰好也是 16388 字节，预筛会把它送进 sha256 计算——这只是多一次哈希，不产生错误。可反驳条件：若 `chd.py` 的校验缓存已经按尺寸做了原子发布、且对每个影片算 sha256 的 I/O 成本在实测里不可忽略，那么保留尺寸做硬预筛、把 sha256 只在预筛命中时计算才是对的；此时该改的不是判据，而是把"预筛命中不等于定案"写进 `docs/disc-import.md`。

本章结论：`game.toml` 用九个节把识别、生成、测量、优化、区域归属全部参数化，`text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"` 是支点——在 `.text` 不变的条件下翻译版自动兼容、不进白名单，改代码则被 USA 流水线拒绝；`[[editions]]` 与 `[[regions]]` 分离后，`asia-97399` 凭三同复用 `code = "japan"` 而保留自己的光盘数据；整句语言判据、精确字节占位判据、`vid::Flip` 客机帧计数各堵一类误判。条件是这些判据都只在档案被 `profile.py` 正确投影、且目录不被外部改动时成立。遗留疑问四处：日版 `8ed48ca8…` 是截断值，完整 `.text` SHA-1 与占位影片 sha256 原值需在 `game.toml` 处补；`europe-alt` 与两个 demo 的 `code` 归属未给出；`GOW_PERF_FRAME_PC` 到 `frame_pc` 的映射位置与 `GOW_PERF_DIAG` 输出格式需在 `perf-compare.ps1` 处补测；`unity_batch = 16` 的编译时间收益无实测值。

## 第 4 章 光盘工具链
本章回答五个问题：ISO9660、`GODOFWAR.TOC` 的 24 字节条目与两个 PAK 分片怎样被收敛成一种只读视图；CHDv5 DVD 导入为什么要把 chdman 0.289 钉到 exe 级 SHA-256；`identify.py` 那份 JSON 的五个字段各自被谁消费、缺字段时如何退化、`compatible` 与 `playable` 差在哪一层；`prepare.py` 写盘时的锁、校验与共享 `mc0` 如何保证可重入；以及 `vu1_from_disc.py` 从 VIF MPG 上传里抽微码能走到哪一步、为什么只能是实验性入口。

### 4.1 格式层：三层索引与一份不写盘的视图

`tools/disc/discfs.py` 是格式层，接受 ISO／已解包目录／TOC／ELF 四类输入，格式说明写在模块 docstring 里。ISO9660 的卷描述符、路径表与目录记录给出逻辑块地址（LBA, logical block address）和文件长度，这层是行业通识，不展开；本项目特有之处是它上面还摞了另外两层索引。

| 层 | 载体 | 给出什么 | 粒度 |
| --- | --- | --- | --- |
| 盘级 | ISO9660 目录记录 | 文件名、LBA、长度 | 光盘上的文件 |
| 容器内 | `GODOFWAR.TOC` 24 字节条目 | `name[12]`、`u32 part`、`u32 size`、`u32 sector` | PAK 内的内部文件 |
| 运行期 | `.disc_layout`（`iso_extract.py` 写出） | 按扇区列出每个文件，允许超出光盘实际末端 | runner 的路径解析 |

第 3 章已验算过条目宽度：12 + 4 + 4 + 4 = 24 B。本章要补的是 `part` 的语义：`u32 part` 只取两个值，0 = `PART1.PAK`，1 = `PART2.PAK`。也就是说两个 PAK 是数据容器，TOC 是容器内索引，`size` 与 `sector` 描述的是内部文件在某个 PAK 里的尺寸与扇区，而不是整张盘的 LBA——**推断**：依据是条目里存在 `part` 这一字段而 ISO9660 目录记录里没有对应概念，`GODOFWAR.TOC` 又与 `SYSTEM.CNF` 并列出现在顶层；仓库未写明两层地址之间的换算代码，此处事实不足，需在 `discfs.py` 处补测。
`u32 sector` 的宽度可以顺手验一次边界。MODE1 扇区的用户数据是 2048 B，则 32 位扇区号的寻址上限是 2^32 × 2048 B = 2^43 B = 8 TiB；DVD 双层约 8.5 GB，差三个数量级，所以这个字段不会溢出。真正值得注意的是 `.disc_layout` 那一层：ISO9660 目录记录不会允许文件超出卷末端，它却允许，因此它不是原盘元数据的镜像，而是一张供运行期解析用的表（第 2 章已立此判断，此处只引用）。三层索引里只有最下面一层是标准格式，上面两层全是本作约定，这正是"格式说明必须写在 docstring 里、具体值必须写进 `game.toml`"的原因——换一款游戏，ISO9660 不用改，TOC 条目宽度与 `part` 取值全要改。
格式层有一条硬纪律：**只读、不写盘、不做准入判定**。`discfs.py` 把任意字节收敛成同一种视图之后，识别（identification）才是纯函数（pure function）；准备（preparation）阶段才真正落盘。第 2 章用这张次序解释了整套可重入性，这里给出它的代价：格式层不能顺手"修"一个坏扇区，也不能把不认识的文件悄悄丢掉，否则 `identify.py` 的 `problems` 就失去了可核查的输入。

### 4.2 CHD 导入：钉到 exe 级哈希为什么不是洁癖

`tools/disc/chd.py` 处理 CHDv5 DVD 与单 MODE1 轨，做校验缓存（verification cache）与锁定的原子发布（atomic publication），落在 `data/imports/chd`。CHD 是压缩哈希盘映像格式，单 MODE1 轨意味着导入后得到的是一条 2048 B/扇区的数据轨，这两句属通识，不展开。
外部工具版本钉在 `toolchains.json[disc_import]`：

| 工具 | 版本／校验 | 基座是否给全 |
| --- | --- | --- |
| chdman | 0.289，带 exe 级 SHA-256 | 是 |
| 7zr | 基座只给出名字 | 否，版本与哈希未给出，需在 `toolchains.json[disc_import]` 处补 |

"exe 级 SHA-256"这五个字是本节的重点：校验对象是工具二进制本身，不是版本号字符串。理由可以写成一条可反驳的判断——**在导入链里，chdman 的输出是后续所有摘要的输入；同一版本号若换了构建（重编译、打了补丁、换了运行库），解包字节可能不同，于是 `identify.py` 的 CRC、`.text` SHA-1、`recompile.py` 的 sha256 key 全部会漂移，而没有任何一层会报"工具变了"**。钉 exe 哈希把这个变量关掉。同理，校验缓存的键应当覆盖"输入映像 + 工具身份"，而不只是输入映像；**推断**：依据是 `chd.py` 同时具备校验缓存与外部工具钉版本两件事、且第 6 章 `recompile.py` 明确用 sha256 做 key；仓库未给 `chd.py` 的缓存键公式，此处事实不足，需在 `chd.py` 处补测。
原子发布的语义要与另外两把锁分清：

| 锁／发布 | 作用域 | 保护什么 | 出处 |
| --- | --- | --- | --- |
| `chd.py` 的发布锁 | 单次导入 | 缓存目录不被半写状态污染 | 基座 2.4 |
| `data/pipeline.lock` | 整个 checkout | 缓存与生成物不能并发更新，第二个流水线直接失败并提示"另一个流水线正在使用这个 checkout" | 第 5 章展开 |
| `recompile.py` 的目录事务 | EE 生成物 | 失败保留上一份可用产物 | 第 6 章展开 |

三者作用域不同，不能互相替代（**推断**：依据是基座分别描述了三处，未声明复用同一文件；若 `chd.py` 实际直接取 `data/pipeline.lock`，则前两行应合并，需在 `chd.py` 处补测）。这也解释了为什么 `identify.py` 必须是纯函数：若识别阶段就写盘，上面三把锁要覆盖的临界区会立刻多出一段，而识别结果本身又是可重算的，没有必要付这个代价。
顺带一句用户可见层的对应：仓库说明写明"Only the files that changed are rebuilt; the extracted disc and the recorded VU1/IOP code are kept."——解包后的盘与录制的 VU1／IOP 代码保留，只重建变化的文件。这句与第 6 章的摘要复用是同一条纪律在 README 上的投影，本章不展开。

### 4.3 识别结果的 JSON 契约

`identify.py` 输出一份固定形状的 JSON：

```json
{ "game": "", "edition": "", "language": "", "compatible": false, "problems": [] }
```

上表只列字段与占位，不是真实返回值；真实契约是这五个键。消费者有两个：`prepare.py` 与启动器（基座 2.4："识别结果的数据契约（谁读、缺字段怎么办……）"）。`game` 对应本作标识，`edition` 对应 `[[editions]]` 里的 USA 原版 `D6385328`／日本 `CA052D22`／欧洲 `FB0E6D72` 一类条目（第 3 章），`language` 对应 `[language_hints]` 的整句判据 `"Novo Jogo"`、`"Nueva partida"`、`"Nouvelle partie"`（第 3 章），`compatible` 是准入布尔，`problems` 是结构化拒绝理由。

| 字段 | 语义（非仓库定义的部分标推断） | 消费者 | 缺失时 |
| --- | --- | --- | --- |
| `game` | 哪款游戏 | `prepare.py`、启动器 | 契约违背 |
| `edition` | 哪个版本／区域盘 | `prepare.py`、启动器 | 契约违背 |
| `language` | 翻译语言，整句判据命中结果 | `prepare.py`、启动器 | 契约违背 |
| `compatible` | 能否作为编排层输入（**推断**） | `prepare.py` | 契约违背 |
| `problems` | 拒绝理由清单，类型未给出 | 启动器、日志 | 契约违背 |

关于"缺字段怎么办"，基座没有给缺省行为，只能给一条设计判断并标注：**`problems` 存在的意义就是把"不可信输入"的理由结构化，因此其余四字段缺失应当按契约违背处理（报错、不进 `prepare.py`），而不是填空后继续——填空会把一张认不出来的盘伪装成一张能准备的盘**。依据是 2.4 的"把不可信输入收敛成可校验的中间态"与 `problems` 的命名；`identify.py` 实际是否抛异常、还是返回半份 JSON，此处事实不足，需在 `identify.py` 处补测。

### 4.3.1 `compatible` 与 `playable` 不是两个字段

任务要求讨论二者区别，先要钉住一个事实：基座给出的五个字段里有 `compatible`，**没有**​ `playable`。所以这里不是两个字段的对照，而是一次契约缺口的定位。

| 概念 | 判据所在层 | 具体判据 |
| --- | --- | --- |
| 能被识别／准入 | 识别层 | 序列号、ELF 名、`crc`（PCSX2 语义，ELF 全部 32 位字异或）、TOC 24 字节条目、`[language_hints]` 整句 |
| 能跑起来 | 构建归属层 | `[[regions]]` 的 `code`、条件性 runtime 覆盖层、基线源码哈希、`data/<game>/regional-builds.json` 归属校验、ELF／runner 哈希 |

二者不等价的实例就在第 3 章：`asia-97399` 的 `SCAJ_973.99` 被识别为亚洲二版（`compatible` 成立），但它的可跑性来自 `code = "japan"` 的日版构建，光盘数据仍归自己；反过来，`europe-alt` 与两个 demo 在基座里只给了名字，未给 `code` 归属，识别成立不等于有已验证构建可跑。第 3 章把"能不能识别"和"能不能跑"在档案层用 `[[editions]]`／`[[regions]]` 彻底分开，识别层却没有对应字段承接后半件事，于是映射只能由下游从 `edition` 反查 `[[regions]]`（**推断**：依据是 `[[regions]]` 存的是 `code` 与构建归属、`register_region.py` 登记进 `regional-builds.json` 后由启动器校验；仓库未写 `prepare.py` 的反查规则）。
由此下一条带条件的判断：**在识别层不持有构建归属的前提下，`compatible` 只能当准入布尔，不能当可跑性承诺；把它当 `playable` 用，启动器版本选择器会列出一条没有对应构建的条目，而失败要等到启动器校验 ELF／runner 哈希时才暴露**。修复方向见 4.3.2。`identify.py` 是否另输出 `playable`、或 `prepare.py` 是否把归属补写进产物元数据，基座未写明，此处事实不足，需在 `identify.py` 与 `prepare.py` 处补测。

### 4.3.2 一处重做判断

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会在五字段之外补一个 `build_code`，取值直接来自 `[[regions]]` 的 `code`（USA、japan、 europe 一类），由 `identify.py` 在识别时一次算出，`prepare.py` 与启动器都不再各自反查。理由是 4.3.1 已经证明识别层与构建归属层之间存在一次隐式反查，而 `asia-97399` 这种"`edition` 是亚洲、`code` 是 japan"的错位格子正是隐式规则最容易写错的地方；显式化之后，`regional-builds.json` 的归属校验多一条可直接比对的输入。代价：契约多一个字段，启动器版本选择器多一条输入，`game.toml` 改动时 `identify.py` 的映射表要同步——这又逼近 1.4 立下的唯一事实源，所以映射必须仍从 `game.toml` 读，不能在 `identify.py` 里写第二份。可反驳条件：若 `prepare.py` 已经把反查结果写进 `languages.json` 或 `data/<id>/discs/*` 的元数据，加字段就是冗余，正确动作是把反查规则写进 `docs/disc-import.md` 并在启动器里复用同一份结果，而不是再加一份真相源。

### 4.4 `prepare.py`：写盘布局、锁与共享记忆卡

`prepare.py` 产出三样东西，全部落在 `data/` 内：

```text
data/<id>/discs/*        # 每语言一个光盘目录，ELF 所在目录即 CD 根
data/<id>/languages.json # 已备语言清单（第 2 章已立：清单，非运行期开关）
data/<id>/mc0            # 共享记忆卡
```

基座把这一步的性质写得很直白：写盘有锁、有校验、可重入。三样产物的职责表：

| 产物 | 内容 | 读者 | 是否按语言复制 |
| --- | --- | --- | --- |
| `data/<id>/discs/*` | 完整光盘目录，含 `SCUS_973.99`、两个 PAK、`IOP_MOD`、`R_PERM.WAD`／`R_SHELL.WAD`、影片 | `ps2EntryRunner.exe`、`.disc_layout` | 是，每语言一份 |
| `languages.json` | 已备语言清单 | 启动器 | 一份 |
| 共享 `mc0` | 记忆卡 | 运行期记忆卡服务 | 否，共享 |

"共享"这个词要按字面读：切换语言换的是 `discs/*` 下的目录，不是记忆卡。这与第 2 章的推断一致——同目录 `mc0/`、`game/Mcd001.ps2`（PCSX2 兼容卡映像）、`GOW_SAVES_DIR`／`GOW_MC0` 之间是同一记忆卡服务在目录侧的几种入口，覆盖优先级需在 `saves.md` 处核实，本章不重复展开。
磁盘代价可以给一个算式框架：设单语言目录字节数为 S、语言数为 L、共享部分（记忆卡、公共元数据）为 C，则准备产物占用约 S × L + C。收益是运行期零分支——没有虚拟光驱、没有 ISO 挂载、没有运行期语言开关，16:9 影片缺失时按 `[disc]` 的 `.PSW` → `.PSS` 回退关系映射，PT-BR 独立版那个永远播不完的 `SEMO01.PSW` 按 `size = 16388` 加 sha256 的精确字节识别（第 3 章），引擎不需要判断"当前是哪个语言"。S、L、C 的实测值基座未给，此处事实不足，需在 `prepare.py` 产物上补测；仅从结构就能下的判断是：**当每语言目录只改动少数文件时，放大倍数约等于目录内文件数除以改动文件数，共享 `mc0` 只能省掉 C，省不掉 S × L**。
可重入性靠两点：写盘前的校验与写盘时的锁。校验的对象是 4.2 收敛出的可校验中间态，不是任意 ISO 字节；锁保证两个 `prepare.py` 不会交错写同一份 `discs/*`。覆盖层按 ELF 名匹配（第 2 章），因此准备阶段不必把 `gow_overrides.cpp` 一类文件复制进每个语言目录——运行期绑定的是可执行文件名，不是目录内容。

### 4.5 `vu1disc`：从 VIF MPG 上传里抽微码，以及它覆盖不到的部分

`tools/disc/vu1_from_disc.py` 从 VIF MPG 上传里抽出 VU1 微码，供"不玩游戏也能预编译"，属实验性、覆盖不全，配 `vu1_from_disc_test.py` 合成测试（synthetic test）。`vu1disc` 是 18 个阶段之一（第 5 章），这是全链上唯一一条"不跑游戏也要产出生成物"的旁路。
原理只需交代本项目特有的那一层：VU1 的微程序放在 VU1 的 micro-memory 里，EE 通过 VIF 的 MPG（microprogram upload）命令把微码写进去，这是 PS2 通识，不展开；本工具做的是反过来——扫描光盘数据里符合 MPG 上传格式的载荷，把其中的 VU 指令序列还原成可交给 `tools/vu1/vu1n_gen.py` 编译的微码块（**推断**：依据是工具名、"从 VIF MPG 上传里抽出"的描述、`[runtime]` 里 VU1 生成器与 `vu1n_heads.txt` 的分工；仓库未给抽取算法、载荷识别规则与输出格式，此处事实不足，需在 `vu1_from_disc.py` 处补测）。
三条微码来源路线必须并排看：

| 路线 | 阶段／工具 | 输入 | 覆盖 | 定位 |
| --- | --- | --- | --- | --- |
| 运行时录制 | `optimize`，240 秒脚本，`GOW_WINDOW_HIDDEN=1`、`GOW_AUDIO=0`、`GOW_AUDIO_PCM=NUL`、`GOW_VU1_CAPTURE_MISSES=1`、`GOW_VU1N_X64=1`、`GOW_PAD_GUION=<脚本>` | 游戏自己跑 | 跑到的路线 | 主线；`native`（16 号补丁）只重建 VU1／IOP |
| 静态抽取 | `vu1disc`／`vu1_from_disc.py` | 光盘数据里的 VIF MPG 上传 | 覆盖不全 | 实验性旁路 |
| 人工补入口 | `[runtime].vu1_native_heads`／`vu1n_heads.txt` | 已知的寄存器间接跳转目标 | 补生成器找不到的块 | 兜底 |

覆盖不全的原因可以列成两条带条件的推断：其一，运行时才由 EE 代码解压、拼接或按场景构造的微码，静态扫描抓不到；其二，寄存器间接跳转的块入口仍需 `vu1_native_heads` 补，抽取器拿不到目标地址（第 3 章）。**在"微码上传发生在运行期且可能经过动态构造"的前提下，静态抽取的上限就是光盘里以完整 MPG 载荷形式存在的那一部分；一旦某段微码只在特定场景由代码生成，它只能靠 240 秒录制或人工入口表补**。第 3 章给过一个刻度：缺 `vu1_native_heads` 时，5 秒船战里进出原生代码约 120 万次（约 24 万次／秒），抽取不全会把这类边界开销留在运行期。
量化覆盖率的算式框架很简单：设录制路线得到 R 个微码块、静态抽取得到 D 个，覆盖率 = D / R，且还要另算"抽取块中能直接编译的比例"，因为抽到不等于能用。R、D 基座都未给，此处事实不足，需在 `vu1_from_disc.py` 与 `optimize` 产物上补测。在没有这份测法之前，措辞必须停在"**已实现但覆盖不全**"，不能写成"已验证"或"未实现"——第 10 章会把这三种措辞分开，此处先引用一句。
`vu1_from_disc_test.py` 用合成输入验证抽取器，不依赖真实 ISO。这与 `verify` 阶段"不需要 ISO 也能跑"（第 2 章）是同一条纪律：把回归从"要有光盘"里解耦。区别只在粒度——`verify` 解耦的是整条流水线，合成测试解耦的是单个抽取器。

### 4.6 三条对照轴的小结与一处重做判断

**纵向**：本章把"档案 → 光盘 → 生成 → 构建 → 运行"里"光盘"这一格的输入输出契约补齐——`chd.py`／`discfs.py` 把任意字节收敛成可校验中间态，`identify.py` 输出五字段 JSON，`prepare.py` 才写盘并产出 `discs/*`／`languages.json`／共享 `mc0`，`iso_extract.py` 的 `.disc_layout` 供运行期解析。`vu1disc` 是这条链上唯一的旁路：它不经过"运行"却要产出"生成"阶段的输入，因此必须被单独标成实验性、且必须配合成测试。
**横向**：Windows／Linux 共享同一份档案、光盘准备、事务式重编译器与序数补丁链（`bash build.sh` → `tools/pipeline/linux.py` 262 行，flock 持 `data/pipeline.lock`，产物在 `data/build-linux/<game>`，第 2 章）；但 `toolchains.json[disc_import]` 钉的 chdman 0.289 与 7zr 属 Windows 便携工具链，Linux 侧基座写明"便携依赖打包未实现"（第 10 章），故不能假设 Linux 格上有同样的 exe 级校验。区域格上，每语言一目录对 USA／日本／欧洲都成立，`asia-97399` 复用 `code = "japan"` 的构建但光盘数据仍归自己，所以 `prepare.py` 仍要为它单独产一个 `discs/*` 目录（第 3 章）——识别与构建的错位不会传导到数据布局。
**深度**：格式层与识别层停在"跑对"（把不可信输入收敛成可校验中间态）；`prepare.py` 的目录契约停在"能跑"；`chd.py` 的校验缓存与原子发布是"跑稳"；`vu1disc` 停在"能跑但覆盖不全"。下一级门槛很具体：把它从实验性提升到"跑对"，需要的不是更多扫描规则，而是一份可复现的覆盖率测法（R、D 与可编译比例）。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会让 `vu1disc` 阶段在结束时强制输出一行机器可读的覆盖率摘要（抽取块数、与 240 秒录制块集合的交集、可编译块数），并让 `verify` 把它列为回归项。理由是现在"覆盖不全"只是文档里的形容词，维护者改了 `vu1_from_disc.py` 的扫描规则后，没有任何数字能回答"是变好了还是变坏了"；而 4.5 已经写明抽取不全会把约 24 万次／秒量级的边界开销留在运行期，这个代价值得被量化。代价：`vu1disc` 需要读一次录制产物才能算交集，于是这条"不玩游戏也能预编译"的旁路重新依赖上了录制产物，实验性的独立性被削弱；`verify` 也多一项需要合成数据兜底的断言。可反驳条件：若 `optimize` 的录制产物本来就不落盘、或只以 `native` 重建后的二进制形式存在，交集就算不出来，正确做法是让抽取器自己输出"命中／未命中"计数并写进 `vu1_from_disc_test.py` 的断言，而不是去耦合录制链。

本章结论：`discfs.py` 用三层索引（ISO9660 目录记录、`GODOFWAR.TOC` 24 字节条目、`.disc_layout`）把只读格式层与准入判定隔开；`chd.py` 用 chdman 0.289 的 exe 级 SHA-256、校验缓存与原子发布把外部工具钉成输入的一部分；`identify.py` 的五字段 JSON 里只有 `compatible`，`playable` 所代表的可跑性由下游从 `[[regions]]` 的 `code` 隐式反查，这是当前契约最值得补的一处缺口；`prepare.py` 以 `discs/*` ＋ `languages.json` ＋ 共享 `mc0` 兑现"每语言一目录、运行期零分支"；`vu1_from_disc.py` 只能覆盖光盘中以完整 VIF MPG 载荷存在的微码，属已实现但覆盖不全。条件是整条链都建立在"识别不写盘、准备才写盘"这一次序上。遗留疑问五处：`discfs.py` 中 TOC 扇区到 ISO9660 LBA 的换算规则、`chd.py` 的校验缓存键公式与是否与 `data/pipeline.lock` 复用、`identify.py` 缺字段时的实际行为与 `problems` 的类型、7zr 的版本与哈希、S／L／C 与 R／D 的实测值，均需在对应文件处补测。

## 第 5 章 构建流水线
本章回答六个问题：18 个阶段的依赖图长什么样、哪些能单跑哪些必须成对；`data/pipeline.lock` 的单写者语义、`C:\gow-build` 为什么必须短、`CMakeCache` 归属校验、`$env:TEMP` 重定向与文本输出协议这五条约束各自堵住了什么；工具链为什么钉到 SHA-256；`optimize→native` 与 `pgo→pgo-check→tune` 两条闭环的差别在哪；`@@progress` 怎样变成进度条；以及失败时该读哪一行、开哪个 `GOW_*` 开关。

### 5.1 入口 86 行，实现 1043 行

`tools/pipeline/build.ps1` 只有 86 行，因为实现分给 `modules/`。模块行数可直接相加：

```text
common 62 + context 77 + toolchain 41 + process 67 + runtime 95
+ game 281 + optimize 159 + verify 33 + distribution 100
+ qt 101 + build-progress 27 = 1043
86 + 1043 = 1129 行
```

`common` 62 行里放着 `Step` 与 `Write-PipelineMetrics`；`game` 281 行与 `optimize` 159 行占掉 440 行，是复杂度最集中的两块；`build-progress` 27 行与 `verify` 33 行最小。这组数字本身就是一条判断：入口薄、游戏相关与自举优化厚、进度协议薄——把"编排"和"做事"分开，代价是读一个阶段要跨两三个文件，收益是 `build.ps1` 本身可以当阶段清单来读。
参数共 15 个，按作用域列表：

| 参数 | 取值／语义 | 影响的层 |
| --- | --- | --- |
| `-Game` | 游戏标识 | `games/gow1/game.toml` 经 `profile.py` 投影后的字典（第 3 章） |
| `-Stages` | 阶段子集 | 允许单跑，但锁仍全局（见 5.3.1） |
| `-Discs` | 光盘目录 | `prepare.py` 产物 `data/<id>/discs/*`（第 4 章） |
| `-Config` | `Release｜RelWithDebInfo` | 决定短构建根用 `C:\gow-build` 还是 `C:\gow-build-dev` |
| `-Ltcg` | 开关 | 01 号补丁的 LTCG 开关，默认不开，链接以小时计（第 7 章） |
| `-Pdb` | 开关 | 调试符号；基座未给产物路径，需补测 |
| `-CpuTarget` | `portable｜x86-64-v3` | 与 32 号 AVX2 数学标志补丁的关系需补测（第 7 章） |
| `-Codegen` | `locals｜classic` | 08 号 register-locals，EE 线程时间约降 22%（第 6、7 章） |
| `-BuildRoot` | 路径 | MAX_PATH 逃生口（见 5.3.2） |
| `-Toolchain` | `msvc` 只是迁移别名 | 组件一律用钉死的 llvm-mingw |
| `-CompilerCache` | `sccache｜none` | sccache 0.19.0 |
| `-ForceRecomp` | 开关 | 与摘要命中的冲突处理见第 6 章 |
| `-NoReleaseProfile` | 开关 | 基座未给语义，需在 `optimize` 模块处补测 |
| `-Xdelta` | 开关 | 基座只给参数名，产物与阶段 `xdelta` 的对应关系需补测 |
| `-Seconds` | 数值 | **推断**：覆盖 `[optimize].seconds = 240`，依据是参数名与档案字段名一致；映射代码需补测 |

其中 `-Toolchain msvc` 值得单独钉一句：它是迁移别名，不是工具切换。若有人传了它并按 MSVC 的报错去查链接问题，方向从一开始就错了——真正参与构建的编译器始终是钉死的 llvm-mingw clang。这类"参数名暗示了它做不到的事"，是 5.8 节第四类误判的来源。

### 5.2 18 个阶段的依赖图

阶段全集按基座顺序是：`tools`、`fetch`、`xdelta`、`discs`、`vu1disc`、`configure`、`recomp`、`sync`、`build`、`pgo`、`pgo-check`、`tune`、`optimize`、`native`、`verify`、`launcher`、`package`、`installer`。按职责分四组，5 + 4 + 5 + 4 = 18：

| 组 | 阶段 | 输入 → 输出 | 能否单跑 | 必须配对 |
| --- | --- | --- | --- | --- |
| 准备（5） | `tools` | 网络 → `data/_tools` 便携工具，各下载一次并按 SHA-256 校验 | 能，一次性 | 无 |
|  | `fetch` | `engine/runtime.toml` + 90 个补丁 → pin 住的 runtime checkout | 能（git 已在） | 后接 `configure` |
|  | `xdelta` | 基座未给产物 | 事实不足 | 事实不足 |
|  | `discs` | ISO／CHD → `data/<id>/discs/*`、`languages.json`、共享 `mc0` | 能，需 ISO | 无 |
|  | `vu1disc` | 光盘数据里的 VIF MPG 上传 → 静态抽取的微码 | 能，旁路 | 依赖 `discs`；覆盖不全（第 4 章） |
| 生成与构建（4） | `configure` | checkout + 档案 → CMake 配置 | 能 | 依赖 `fetch` |
|  | `recomp` | `.text` SHA-1 + 模板 + 函数表 → 内容寻址的 EE 生成物 | 否 | 依赖 `configure` 与 `discs`；事务发布见第 6 章 |
|  | `sync` | 生成物 + overrides → 只拷变化文件 | 否 | 必须紧跟 `recomp` |
|  | `build` | 生成物 → `ps2EntryRunner.exe` | 否 | 必须跟 `sync` |
| 优化（5） | `optimize` | 可运行的 build + 240 秒脚本 → 录制的 VU1 微码与 IOP 模块 | 否 | 依赖 `build`；与 `native` 成对 |
|  | `native` | 录制产物 → 重建的 VU1／IOP（16 号补丁） | 否 | 必须跟 `optimize` |
|  | `pgo` | instrumented 构建 + 训练 → `data/<id>/pgo/gow.profdata` 后二次构建 | 否 | 自身即"两遍"，见 5.5.2 |
|  | `pgo-check` | profdata + 本次安装元数据 → 校验结果 | 否 | 必须跟 `pgo` |
|  | `tune` | 一次 `-O1` instrumented 构建 → 同时收微码与 profile | 能，替代路径 | 与上两条闭环二选一 |
| 验证与交付（4） | `verify` | `tools/test/` 约 40 个测试 → 回归结果 | 能，**不需要 ISO**​ | 无（第 2 章） |
|  | `launcher` | Qt SDK + build → 启动器 | 否 | 依赖 `qt` 与 `build` |
|  | `package` | build + launcher → 发布包，**明确排除 runtime**​ | 否 | 依赖 `build` |
|  | `installer` | package → 1352 行 Win32 单文件 exe | 否 | 依赖 `package`（第 9 章） |

这张依赖图整体是**推断**：基座给了阶段全集、四个优化阶段的描述、`verify` 不需要 ISO、`package` 排除 runtime，但没有在 `build.ps1` 里显式声明 DAG。可核查的反证点很明确：`-Stages` 允许任取子集，而锁是全局的，所以"能单跑"只表示"输入已齐备"，不表示"可与另一份流水线并发"。另有一处不对称：`verify` 被刻意设计成不需要光盘，把回归从"要有 ISO"里解耦；`discs` 与 `vu1disc` 却必须持有用户自己的盘——这正好把 18 个阶段划成"可 CI 化"与"只能在用户机器上跑"两半。
`qt` 不在这 18 个阶段名里，却是 `launcher` 的前置：Qt 源码钉 6.8.3，三个模块 qtbase、qtshadertools、qtdeclarative 按 SHA-256 校验，一次构建进 `data/_tools`，构建 SDK 前应用 `tools/pipeline/compat/` 的源码兼容适配（现有一个 `qt-sequence-sort.h`）。UI 侧细节见第 9 章，此处只记它在依赖图上的位置。

### 5.3 五条工程约束

### 5.3.1 单写者锁

`data/pipeline.lock` 以独占方式打开，第二个流水线直接失败并提示"另一个流水线正在使用这个 checkout"，因为缓存与生成物不能并发更新。Linux 侧 `bash build.sh` 走 `tools/pipeline/linux.py`（262 行），用 flock 持同一个 `data/pipeline.lock`——同一个语义、两种平台原语，这是横向矩阵里少见的"完全对齐"的一格。
独占的粒度是整个 checkout，不是某个阶段。所以 `-Stages verify` 与 `-Stages build` 也不能同时跑：前者不写生成物，但锁不区分读写意图。这是一条可反驳的设计取舍：**在"缓存与生成物不能并发更新"的前提下，把锁放粗一层比逐目录加锁简单得多；代价是明明只读的 `verify` 也要排队**。若哪天 CI 要并发跑回归，正确做法不是拆锁，而是给 `verify` 一份只读的 checkout 副本——那又会引出 `C:\gow-build-<hash>` 的归属问题（见 5.3.3）。
失败时机也确定：锁在任何 `=== <step> ===` 之前就被取，所以锁冲突的输出里没有阶段边界，只有 `trap` 的 `ERROR: <消息>`（见 5.8）。

### 5.3.2 短构建目录与 MAX_PATH

`C:\gow-build` 是默认构建根，`RelWithDebInfo` 用 `C:\gow-build-dev`。原因不是习惯：runtime 的 CMake 依赖是 git checkout，长路径必撞 MAX_PATH。Windows 传统 MAX_PATH 是 260 字符（通识），而 git checkout 的嵌套目录、CMake 生成物、对象文件与临时路径会层层拼接；根目录每多一个字符，整条链上所有路径同时变长。

```text
C:\gow-build       = 13 字符
C:\gow-build-dev   = 17 字符
C:\gow-build-<hash> = 13 + 1 + len(hash) 字符
```

13 字符的根把预算几乎全部留给下游。同一台机器上第二份仓库副本会拿到 `C:\gow-build-<hash>`，选择写进 `data/build-root.txt`，启动器与卸载器都读它；Linux 侧对应 `data/build-root-linux.txt`，产物在 `data/build-linux/<game>`。把 `-Config Release|RelWithDebInfo` 与两个短根绑定，还顺带避免了两个配置互相覆盖生成物。
`-BuildRoot` 是唯一的逃生口，但它不能随便指：指回一个长路径，MAX_PATH 立刻回来；指向另一份副本的根，则撞上 5.3.3 的归属校验。第 2 章已按"症状—真实原因—判定方法—修复"写过这一类误判，本章只补它在流水线上的归属：报错落在 `configure` 或 `build`，不在编译器。

### 5.3.3 归属校验

启动器接受 runner 前会核对 CMakeCache 的源目录，防止新副本误用旧副本的构建。Linux 侧按大小写敏感的 CMake 源目录归属校验，读 `data/build-root-linux.txt`。同一条判据有三个消费者：Windows 启动器、Linux 启动器、卸载器的 `/purge`——后者只在副本的 CMakeCache 确实指向 `<dir>` 时才删其构建目录（第 9 章）。
这条约束补的是短构建目录带来的新风险：`C:\gow-build-<hash>` 意味着一台机器上可能并存多份 checkout，而 `data/build-root.txt` 只是一个文本登记。若登记被覆盖或手工改错，启动器会拿着 A 副本的 runner 去跑 B 副本的 ELF，覆盖层按 ELF 名匹配（第 2 章）又恰好让这类错配不容易立刻报错。核对 CMakeCache 的源目录，是把"登记说了什么"换成"产物自己说了什么"。**推断**：依据是基座写"防止新副本误用旧副本的构建"，且 Linux 侧强调大小写敏感；仓库未给校验失败时的具体提示文案，需在 `modules/context`（77 行）处补测。

### 5.3.4 临时目录重定向

`build.ps1` 把 `$env:TEMP`／`$env:TMP` 指向 `data/_tmp`，避免构建中间物散落系统盘。它与 5.4 的 `data/_tools`、5.3.2 的 `data/build-root.txt`、5.3.1 的 `data/pipeline.lock` 一起，构成第 2 章那张目录职责表里"全部中间态收进 `data/`"的兑现。
代价是一个隐含前提：所有被调用的工具都得尊重这两个环境变量。若有工具硬编码系统临时目录，重定向对它无效，中间物仍会外泄（**推断**：依据是重定向只在进程环境层生效，属通识）。这条前提没有测试覆盖的证据，此处事实不足，需在 `modules/process`（67 行）处补测。

### 5.3.5 输出协议

第五条约束单列到 5.6，因为它是"终端与启动器共用同一条路径"的接口，值得单独一节。

### 5.4 工具链钉版本与 SHA-256

`tools` 阶段一次性下载并按 SHA-256 校验的组件共 6 项：

| 组件 | 版本 | 基座是否给版本 |
| --- | --- | --- |
| 便携 Git | 未给 | 否 |
| Python | 3.13.16 | 是 |
| CMake | 3.31.12 | 是 |
| Ninja | 1.13 | 是 |
| llvm-mingw clang | 未给 | 否 |
| sccache | 0.19.0 | 是 |

6 项里 4 项有显式版本、2 项缺；缺的两项需在 `modules/toolchain`（41 行）处补。三套钉版本机制要分清：`tools` 阶段这套管构建组件；`toolchains.json[disc_import]` 钉 chdman 0.289（带 exe 级 SHA-256）与 7zr，管光盘导入（第 4 章）；`qt` 阶段钉 Qt 6.8.3 三模块，管启动器 SDK。三套互不复用，但理由相同——**下游所有摘要都以这些工具的输出为输入，工具本身若不固定，摘要就失去可复现性**。第 4 章已用 chdman 的 exe 级哈希论证过一遍，此处不重复；只补一个构建侧的推论：`-CompilerCache sccache|none` 与 sccache 0.19.0 绑定后，缓存键里才可能含有确定的编译器身份，否则换一次 clang 就会命中一批语义不同的对象文件（**推断**：依据是 sccache 的缓存语义属通识，仓库未给缓存键公式，需在 `modules/toolchain` 处补测）。
`-CpuTarget portable|x86-64-v3`、`-Ltcg`、`-Codegen locals|classic` 三个参数与 01／31／32／08 号补丁都可能影响指令集或代码形状，于是出现一个真实的优先级问题：参数、档案、补丁栈三层都能改 codegen，冲突时以哪层为准？基座未给答案，此处事实不足，需在 `modules/game`（281 行）与 `engine/patches/` 处补测。这个缺口直接喂给 5.5.3 的"重训触发条件"。

### 5.5 两条闭环：`optimize→native` 与 `pgo→pgo-check→tune`

### 5.5.1 闭环 A：录制数据，只重建 VU1／IOP

`optimize` 用 `[optimize]` 的 240 秒脚本在隐藏静音窗口里让游戏自己玩：

```text
GOW_WINDOW_HIDDEN=1
GOW_AUDIO=0
GOW_AUDIO_PCM=NUL
GOW_VU1_CAPTURE_MISSES=1
GOW_VU1N_X64=1
GOW_PAD_GUION=<脚本>
```

脚本是 `5:start,12:x,18:x,24:x,30:x,36:x,40:cuadrado,…`（西班牙语按键名见第 3 章）。隐藏窗口由 15 号补丁做进 runtime，`GOW_VU1_CAPTURE_MISSES=1` 把没录到的块记下来；录下的是 VU1 微码与 IOP 模块。`native` 随后只重建 VU1／IOP（16 号补丁），不碰 EE 生成物、不碰编译器 profile。240 秒按 60 Hz VBlank 折算，理论客机帧上限是 240 × 60 = 14,400 帧；实际因掉帧而小于该值，且游戏掉帧不减速（第 1 章）。
这条闭环失效时不会报链接错误，只会静默回退：缺 `vu1_native_heads` 或录制没覆盖到某段微码时，块留在解释器里跑，5 秒船战里进出原生代码约 120 万次（第 3 章）。所以 A 的验收信号是边界次数，不是构建是否成功。

### 5.5.2 闭环 B：profile，以及为什么要跑第二遍

`pgo` 产出 `data/<id>/pgo/gow.profdata` 后二次构建。第二遍是 PGO 的固有结构（通识）：第一遍是 instrumented 构建，在代码里插计数点，跑训练轨迹把执行计数写成 profdata；第二遍编译器读 profdata 决定内联、基本块布局与分支权重，产出不含 profiling runtime 的发布二进制。只跑第一遍，得到的仍是插桩版——体积更大、更慢，而且训练轨迹本身就被插桩扭曲了。
`pgo-check` 校验 profile 真属于本次安装：清单、覆盖率、编译标志、无 profiling runtime 残留。第四项正是防"第二遍没跑或跑错了版本"；第三项防 `-Config`、`-CpuTarget`、`-Codegen` 或补丁栈变了却沿用旧 profile。`tune` 是另一条入口：用一次 `-O1` instrumented 构建同时收微码与 profile，把 A 的录制和 B 的插桩合成一遍。

### 5.5.3 两条闭环的差别

| 维度 | `optimize→native` | `pgo→pgo-check→tune` |
| --- | --- | --- |
| 训练对象 | 运行期数据：VU1 微码、IOP 模块 | 编译器决策：执行计数 → `gow.profdata` |
| 产物 | 原生 VU1／IOP 代码（16 号补丁只重建这两部分） | profdata + 二次构建的 runner |
| 是否改变 EE 生成物 | 否 | 否（改变的是编译决策，不是翻译结果） |
| 是否插桩 | 否 | 是，第一遍；第二遍必须去掉 |
| 守门阶段 | 无独立守门，靠 `GOW_VU1_CAPTURE_MISSES` 与解释器边界暴露 | `pgo-check`，四项校验 |
| 失效表现 | 边界回退到解释器，约 120 万次／5 秒船战 | `pgo-check` 失败，输出 `ERROR: <消息>` |
| 修复 | 补录 / 补 `vu1_native_heads` 后重跑 `native` | 重训 |
| 合并路径 | — | `tune` 一次 `-O1` instrumented 同时收两样 |

两闭环共有一句总纲：**产物训练产物**。因此任何一次 runtime 或 90 个补丁的变更都必须重训，否则 profile 指向不存在的形状；同理，改了 `[optimize]` 脚本却沿用旧录制，`native` 会产出与当前游戏行为不同的 VU1 代码。第 3 章已写过 `cuadrado` 被"修正"成 `square` 会让 240 秒录出空轨迹、`pgo-check` 以覆盖率不足失败，此处只引用。
一条容易被漏掉的差别：A 的产物是**数据**，可以只重建一部分而保留其余；B 的产物是**编译决策**，与本次编译标志一一绑定，不能"只重训一半"。所以 `native` 能靠 16 号补丁做增量，而 `pgo-check` 必须做四项全量校验。

### 5.6 输出协议与进度条的对偶

```text
=== <step> ===
@@progress <done> <all>
@@status <text>
```

`Step`（`common`，62 行）输出的 `=== <step> ===` 是阶段边界，也是进度条的分母来源；`@@status` 是人类可读的当前动作；`@@progress <done> <all>` 才是机器读的分子／分母；其余行是日志。`build-progress`（27 行）与 `Write-PipelineMetrics` 承担度量侧，具体分工基座未给，属**推断**。
把 18 阶段当分母，最自然的模型是 `all = 18`。给一个纯符号算例：若 `done = 7`、已耗时 `T` 秒，按均速外推的剩余时间是 `T × (18 − 7) / 7 ≈ 1.57 T`。这个算式显然只能当粗估——`tools` 是一次下载、`fetch` 要克隆并重放 90 个补丁、`optimize` 单阶段就占 240 秒，阶段耗时相差两个数量级。**推断**：`LoadingScreen.qml` 按这套文本协议算总进度与剩余时间、显示 `cargaDica1..N` 提示并读 `data/<id>/loading` 里的图片（第 9 章展开），但 `all` 究竟取 18 还是由 `build-progress` 重算的加权值，基座未写，需在 `modules/build-progress` 处补测。
协议是文本而不是 IPC，选择让"终端跑一遍"和"启动器跑一遍"共用同一条路径；代价是解析脆弱、文案即接口。两个具体失效模式：`@@status <text>` 里的 text 若被启动器按子串匹配，改一个词就静默失效；`=== <step> ===` 的 step 若与 18 个阶段名不一致，分母错位而没有任何一层报错。第 2 章已给出 `trap` 抓 `ERROR: <消息>` 区分"失败"与"仍在跑"的判定，本章不重复。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会保留三行文本协议不动，另加一行机器可读的结构化进度（例如带阶段名、耗时、加权分母的单行记录），启动器优先读新行、读不到才回退到 `@@progress`。理由是 240 秒的 `optimize` 与一次下载的 `tools` 在 `all = 18` 里权重相同，剩余时间必然误导；加一行不改变终端可读性，也不破坏现有解析。代价：多一条输出契约要维护，`build-progress` 的 27 行会膨胀，且结构化行与 `@@progress` 一旦不同步，启动器要决定信谁。可反驳条件：若 `Write-PipelineMetrics` 已经输出了阶段级耗时、启动器只是没用它，正确动作是复用那份度量而不是再加第三套输出——那会直接违反 1.4 立下的唯一事实源。

### 5.7 `GOW_*` 诊断面：按二分路径组织

完整变量表已在第 2 章列出（30 余个，UI 上每个设置最终变成一个 `GOW_*` 环境变量，UI 与引擎之间没有第二套配置系统），本章不重列，只给"症状 → 开关 → 看哪一层"的二分表：

| 症状 | 先开 | 关联阶段／补丁／配置 |
| --- | --- | --- |
| 船战里 VU1 边界回退 | `GOW_VU1_CAPTURE_MISSES`、`GOW_VU1N_DIAG`、`GOW_VU1N_JIT`、`GOW_VU1_FAST` | `optimize`、`vu1_native_heads`（第 3、8 章） |
| GS stage 唤醒过多 | `GOW_GS_STAGE_SPIN_US`（默认 50，0 表示立刻睡）、`GOW_SYNC_DIAG`、`GOW_GS_EARLY_FINISH`、`GOW_GS_FINISH_ASINCRONO` | 40／44／77 号（第 7 章） |
| 帧率口径对不上 | `GOW_PERF_DIAG`、`GOW_PERF_FRAME_PC` | `frame_pc = "0x1837B8"`（`vid::Flip`，第 3 章） |
| profile 形状可疑 | `GOW_PGO_REVISION` | `pgo-check` 四项校验 |
| 调度被裁剪 | `GOW_DISPATCH_FULL` | 29 号调度裁剪（第 7 章） |
| IOP 时序漂移 | `GOW_IOP_DRIFT` | 23／55 号（第 7 章） |
| QTE 长按异常 | `GOW_QTE_HOLD`、`GOW_QTE_HOLD_HZ` | 53 号、`qte_hold_test.cpp`、`verify` |
| mod 数据没生效 | `GOW_MOD_VFS_LOG`、`GOW_MOD_VFS_TABLE`、`GOW_MOD_PATCH_TABLE` | 71／84 号（第 7、8 章） |
| 录制／训练环境不对 | `GOW_WINDOW_HIDDEN`、`GOW_AUDIO`、`GOW_AUDIO_DEVICE`、`GOW_AUDIO_PCM` | 15 号、`optimize` |
| 启动路径异常 | `GOW_ISO`、`GOW_MC0`、`GOW_SAVES_DIR`、`GOW_SKIP_FMV`、`GOW_FAST_BOOT` | `prepare.py` 产物（第 4 章） |

表中除 `optimize` 的六个取值、`GOW_GS_STAGE_SPIN_US` 默认值、`pgo-check` 四项校验外，开关到日志行的映射均为**推断**，依据是变量命名与补丁主题；需在 `modules/` 与 runtime 日志输出处补测。`GOW_VU1N_X64` 与 `GOW_PAD_GUION` 出现在 `optimize` 命令里却不在第 2 章那份诊断面清单里，再次说明清单是"主要开关"而非全集（第 2 章已立）。这些开关不是给玩家看的：出问题时靠"打开哪个、看哪一行"把范围二分，而不是把 30 多个全打开——全开会让诊断面本身变成噪声源。

### 5.8 失败可观测性

出口只有四个，读者应当知道各自归谁：

| 出口 | 产生者 | 读者 | 语义 |
| --- | --- | --- | --- |
| `ERROR: <消息>` + 退出码 1 | `build.ps1` 顶部 `trap` | 启动器 | 失败终止，可与"仍在跑"区分 |
| `=== <step> ===` | `Step`（`common` 62 行） | 启动器／人 | 阶段边界、分母来源 |
| `@@progress <done> <all>` | 流水线 | `LoadingScreen.qml` | 分子／分母 |
| `@@status <text>` | 流水线 | 人 | 当前动作 |
| 其余行 | 各工具 | 日志 | 无协议语义 |

第 2 章已按四段式写过三类最常见误判（锁冲突当构建坏、MAX_PATH 当编译器问题、`pgo-check` 失败当 PGO 没效果），本章只补它们在流水线上的位置：锁冲突发生在任何 `=== <step> ===` 之前，因此输出里没有阶段边界；MAX_PATH 落在 `configure`／`build`；`pgo-check` 失败时 `gow.profdata` 其实已经产出，失败的是归属校验而非训练本身。
第四类是参数级误判：`-Toolchain msvc` 只是迁移别名，组件一律钉死 llvm-mingw；`-ForceRecomp` 与摘要命中的冲突由第 6 章处理；`-Xdelta`、`-NoReleaseProfile`、`-Pdb` 的语义基座未给，把它们当成"能修好某个失败"的开关去试，只会多跑一遍 18 阶段。
最后一句措辞纪律：Linux 的 PGO／自动录制、IOP 训练、便携依赖打包与二进制更新是**未实现**，GPU 路径是**已编译但未验证**，`vu1disc` 是**已实现但覆盖不全**；三者不可混用，严格区分见第 10 章。把"未实现"写成"有 bug"会引出根本不存在的排查方向。

### 5.9 三条对照轴的小结

**纵向**：18 个阶段就是"档案 → 光盘 → 生成 → 构建 → 运行"的显式化。`discs` 收第 4 章的产物，`recomp` 收第 3 章的 `text_sha1`，`sync` 与 `build` 交给第 6 章的产物治理，`optimize`／`pgo` 把运行结果回灌成下一轮输入，`package` 明确排除 runtime（第 1 章的许可边界）。每一步的输入都能在上一阶段的输出里找到，唯一例外是 `verify`——它故意不从这条链取水，才能不需要 ISO。
**横向**：Windows 侧 `C:\gow-build`／`C:\gow-build-dev`／`data/build-root.txt`、便携工具与 PGO profile；Linux 侧 `bash build.sh` → `tools/pipeline/linux.py`（262 行，Python 3.12+、原生 Clang、系统或 SDK Qt 6.5+、SDL2），共享同一份档案、光盘准备、事务式重编译器与序数补丁链，flock 持同一个 `data/pipeline.lock`，产物 `data/build-linux/<game>`，读 `data/build-root-linux.txt` 并按大小写敏感的 CMake 源目录归属校验——Windows 的构建根、便携工具、PGO profile 一律不复用。区域格上，18 阶段不随 `[[regions]]` 变化：`asia-97399` 的 `code = "japan"` 复用的是另一套构建（第 3 章），不是同一条流水线换个参数；USA 流水线至今拒绝异码 ELF（第 10 章）。
**深度**：`tools`／`fetch`／`configure`／`recomp`／`sync`／`build` 停在"能跑 → 跑对"；`verify` 与 `pgo-check` 是"跑对"的守门；`optimize`／`native`／`pgo`／`tune` 指向"跑快"，44 号字节环把战斗从 52.8 提到 54.7 FPS 的测法见第 7 章；`launcher`／`package`／`installer` 是"跑稳"的产品化。下一级门槛分别是：阶段耗时加权后的真实 ETA、A 闭环的覆盖率数字、以及 Linux 格上补齐 PGO 与 IOP 训练。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会把 `tune` 升为默认训练路径、`optimize→native` 降为兼容路径。理由是 `tune` 用一次 `-O1` instrumented 构建同时收微码与 profile，而 A＋B 两条闭环现在要分别跑一遍隐藏窗口录制和一遍插桩构建加二次构建，训练成本接近翻倍；合成一遍后"产物训练产物"只需重训一次，`pgo-check` 的清单也能同时锁住微码集合与 profile 形状。代价很实在：`-O1` 插桩版收集到的执行计数与 Release 优化级别下的分支布局未必同构，PGO 的收益可能低于 Release instrumented 路径；`native` 依赖的录制产物格式若与 `-O1` 产物不同，16 号补丁只重建 VU1／IOP 的增量优势会消失。可反驳条件：若实测表明 `-O1` profile 使二次构建的客机帧率低于现行 `pgo` 路径，或 `GOW_VU1_CAPTURE_MISSES` 在 `-O1` 下漏报解释器边界，那么"两遍分开"就是对的，正确动作只是把两条闭环的重训触发条件写进 `docs/architecture.md`，而不是合并它们。

本章结论：18 个阶段由 86 行入口与 1043 行模块承载，分准备 5、生成构建 4、优化 5、验证交付 4 组；五条约束把 Windows 上的不确定性关进 `data/`——单写者锁挡并发、短构建目录挡 MAX_PATH、CMakeCache 归属校验挡副本错配、`TEMP`／`TMP` 重定向挡中间物外泄、文本协议让终端与启动器共用一条路径；`optimize→native` 训练的是数据且可增量，`pgo→pgo-check→tune` 训练的是编译决策且必须第二遍去插桩，两者都因"产物训练产物"而在 runtime 或补丁变更后必须重训。条件是这套模型只在单写者、短路径、归属一致三者同时成立时可复现。遗留疑问六处：`xdelta` 阶段产物、`-Xdelta`／`-NoReleaseProfile`／`-Pdb` 语义、便携 Git 与 llvm-mingw clang 的版本号、`all` 的分母来源与加权方式、参数／档案／补丁栈三层的 codegen 优先级、以及 `GOW_*` 到日志行的映射，均需在对应 `modules/` 文件处补测。

## 第 6 章 重编译与产物治理
本章回答六个问题：`tools/pipeline/recompile.py`（254 行）的 docstring 逐句拆开各约束了什么；内容寻址（content-addressed）为什么必须取代时间戳；`text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"` 变成 sha256 key 之后，摘要命中与 `-ForceRecomp` 冲突时谁赢；目录事务（directory transaction）在断电、崩溃、并发三种情况下各自向读者暴露哪一套产物；"所有权感知"里生成物与用户改动冲突时怎么发现；以及 08 号 register-locals 约降 22% EE 线程时间、28 号直接 `jal` 的收益究竟从哪一层来。

### 6.1 一份 docstring 就是设计声明

`tools/pipeline/recompile.py` 254 行，docstring 本身就是设计声明，逐句列出六条：内容寻址的 EE 生成、所有权感知（ownership-aware）的同步、成功以目录事务发布、失败保留上一份可用产物、复用由摘要而非时间戳决定、绝不把游戏数据缓存到 `data/` 之外。另有两处实现细节落在正文：从 `discfs` 借 `text_sha1`，用 sha256 做 key；`replace_file` 对 Windows 扫描器／索引器的短暂占用做 6 次有界重试，仍失败才报错。

| 声明 | 保护的对象 | 违反时的症状 | 由谁守 |
| --- | --- | --- | --- |
| 内容寻址 | 生成物身份 | 改了数据却重编译，或改了代码却复用旧产物 | sha256 key |
| 所有权感知同步 | 用户改动 | `sync` 静默覆盖手改文件 | 文件归属清单（**推断**，见 6.5） |
| 目录事务发布 | 正在运行的构建 | 半套生成物被 `build` 读走 | 切换原语（**推断**，见 6.4） |
| 失败保留上一份可用产物 | 可用性 | 一次失败让整份 checkout 不可构建 | 事务 + 旧目录不删 |
| 摘要而非时间戳 | 可复现性 | 换机器、复制目录、碰过文件就误判 | key |
| 不缓存到 `data/` 之外 | 许可与可清理性 | 派生数据散落系统盘 | 路径约定 + `$env:TEMP` 重定向（第 5 章） |

最后一行不是洁癖。README 写明仓库 contains no game files（ISO、executable、IRX modules、`.PAK` data）也不含由它们生成的代码，安装器 builds everything on your computer from your own disc image，"nothing derived from the game ever leaves it"；`package` 阶段明确排除 runtime（第 1 章）。把 `data/` 当作唯一落点，法律边界、可清理性与 5.3.4 的 `TEMP`／`TMP` 重定向三者合成一条约束：中间物既不能外泄，也无需去系统盘找。
254 行对应约 6,400 个函数的 EE 生成物（该数字是约数，见第 1 章），两者不是同一量纲：脚本行数决定治理逻辑的复杂度，函数数决定下游 `build` 的编译时间。若把 `[build].unity_batch = 16` 当作每批合并的翻译单元数（**推断**，第 3 章已标注单位未确认），则可写 6,400 ÷ 16 = 400 批；这个算式只在"函数数近似等于翻译单元数"时成立，基座未给该对应关系，需在 `modules/game`（281 行）处补测。

### 6.2 内容寻址为何优于时间戳

时间戳比较的是 mtime：文件最后被写入的时刻。它的失效场景可以列全，且每一条都在这套流水线里真实存在：

| 场景 | 时间戳判定 | 内容寻址判定 |
| --- | --- | --- |
| 复制一份 checkout 到新目录 | 全部文件 mtime 变，全部重生成 | 摘要不变，复用 |
| `fetch` 重新克隆并应用 90 个补丁 | 文件 mtime 变，全部重生成 | 摘要不变，复用 |
| 杀毒软件／Windows 索引器碰过文件 | 可能刷新 mtime | 摘要不变，复用 |
| 只改数据的翻译版光盘 | 无法区分（生成输入没变，却可能触发重跑） | `.text` 摘要不变，复用 |
| 改了 `config/recomp.template.toml` 或 `config/funcmap.csv` | 生成物 mtime 未必变 → 漏判 | 取决于 key 是否包含它们（见 6.2.1） |
| 改了代码但生成器恰好没写盘 | 漏判 | 摘要变，重生成 |

第 3 章已立：`text_sha1` 只覆盖 `.text` 段，重编译产物只依赖 `.text`，因此任何只改数据的翻译版光盘都会编译出同一个程序，翻译不必进白名单（allowlist）。本章补的是机制层差异——**时间戳描述的是"文件被碰过没有"，内容寻址描述的是"输入是什么"；流水线要的是后者，因为 `fetch` 每次都把 runtime 重新铺一遍，碰过文件是常态而非事件**。
`recompile.py` 从 `discfs` 借 `text_sha1`，用 sha256 做 key。借而不是自己算，是为了让识别层（`identify.py`，第 4 章）与生成层读同一个字段：ELF 全部 32 位字异或得到 `crc = "D6385328"`（PCSX2 语义）用于快速归类，`.text` 的 SHA-1 用于身份，再经 sha256 变成缓存键。三级判据各管一段，不复用同一份摘要。

### 6.2.1 key 的构成是一处未闭合的缺口

基座只写"用 sha256 做 key"，没写 key 里除了 `text_sha1` 还有什么。这个缺口必须显式标注，因为它决定了一整类静默错误：**若 key 只含 `text_sha1`，那么改 `config/recomp.template.toml`、改 `config/funcmap.csv`、改三个覆盖层文件（`gow_overrides.cpp`、`gow_pad2_packet.h`、`gow_gs_replay.h`）、或增删 90 个 `engine/patches/*.patch` 中的任何一个，都不会触发重生成——生成物会沿用旧形状，而 `pgo-check`（第 5 章）却会因为编译标志或源码形状变化报失败**。两类错误在不同层暴露，中间没有任何一层说"重编译该重跑了"。
这与第 5 章留下的"参数、档案、补丁栈三层都能改 codegen，冲突时以哪层为准"是同一个问题的两面：codegen 的优先级决定产物长什么样，key 的构成决定产物要不要重生成。两者都得补测，位置在 `recompile.py` 与 `modules/game`（281 行）。
一个可写的相对式：设重生成耗时为 R、复用耗时为 r（r ≪ R），key 每多纳入一项输入，命中率下降但漏判率也下降。基座未给 R、r 与命中率，此处事实不足，需在 `modules/optimize`（159 行）的流水度量处补测；能直接下的判断只有一条带条件的：**在 `.text` 不变且生成输入（模板、函数表、覆盖层、补丁栈）都不变的条件下，复用是安全的；上述任一输入变化而 key 未感知，摘要命中就会从优化变成错误**。

### 6.3 摘要命中与 `-ForceRecomp` 的冲突

`-ForceRecomp` 是 `build.ps1` 的 15 个参数之一（第 5 章），语义是强制重生成。它与"复用由摘要决定"直接冲突，处理策略只有三种，基座未指定选了哪种：

| 策略 | 行为 | 可从外部发现吗 | 代价 |
| --- | --- | --- | --- |
| A：Force 优先，key 不变 | 忽略命中，重跑生成器，产物写入同一 key 的目录 | 能：产物内容哈希与旧目录一致，但编译时间与 `@@status` 会变 | 白付一次 R；若生成顺序受环境影响，`pgo-check` 可能因形状漂移失败 |
| B：摘要优先，Force 被忽略 | 参数形同虚设 | 能：加与不加 `-ForceRecomp` 输出完全一致 | 参数失去意义，维护者会误以为已强制 |
| C：Force 使 key 失效 | 把 Force 当输入的一部分（例如加一个 nonce），产出新 key 的新目录 | 能：key 变化、旧目录保留 | 缓存膨胀，每强制一次多一份约 6,400 函数的生成物 |

**推断**：依据是 `-ForceRecomp` 存在、`recompile.py` 复用由摘要决定、第 5 章 `-Stages` 允许单跑但 `data/pipeline.lock` 全局独占。策略 A 最可能，因为它保留了"失败保留上一份可用产物"的语义且不需要新目录；但这是推断，需在 `recompile.py` 处补测。
"谁赢、如何发现"要分开答。谁赢：若采用 A，流水线赢（用户要求重跑，流水线执行），摘要只是被旁路；若采用 C，用户赢（新 key 是新身份）。如何发现：策略 A 下，比较新旧生成物目录的内容 sha256——若完全相同，说明这次 `-ForceRecomp` 只是重付了编译成本、没有改变任何输入，那么真正该查的是 6.2.1 里那批"没进 key 的输入"；若不同，说明生成器本身有非确定性（例如依赖文件遍历顺序或时间戳），那才是需要修的 bug。**这个对比把 `-ForceRecomp` 从"重跑开关"变成"生成器确定性探针"**，是它在流水线里最被低估的用途。
顺带一条与第 5 章的呼应：`pgo` 产出 `data/<id>/pgo/gow.profdata` 后二次构建，任何 runtime 或补丁变更都必须重训（产物训练产物）。`-ForceRecomp` 若采用策略 A 且产物内容不变，profile 不该重训；若产物内容变了，profile 必须重训。两者之间没有自动连线，靠 `pgo-check` 的清单与编译标志校验兜底（第 5 章）。

### 6.4 目录事务发布：三种失效下的可见性

"成功以目录事务发布、失败保留上一份可用产物"合起来只承诺一件事：**任何时刻，读者看到的都是某一套完整产物，不会是半套**。具体原语基座未给（Windows 上没有 POSIX 式目录 rename 的通用保证，可能是暂存目录加 `MoveFileEx`、目录交换、或一份指向当前目录的清单指针），以下三种可见性分析均标注为**推断**，依据是"目录事务"这一措辞与"失败保留上一份"的结果承诺。

| 失效 | 发生在切换前 | 发生在切换后 | 残留物 |
| --- | --- | --- | --- |
| 断电 | 旧目录完整可见，暂存目录半写 | 新目录完整可见 | 暂存目录、可能未释放的锁 |
| 进程崩溃 | 旧目录完整可见 | 新目录完整可见 | 暂存目录、`data/pipeline.lock` 的残留持有 |
| 并发 | 由 `data/pipeline.lock` 单写者挡住，两个写者不同时进入事务 | 同左 | 无写者冲突，但读者可能在切换瞬间读到 |

三行里最值得展开的是"并发"这一格：它其实不需要事务自己处理写者——第 5 章的 `data/pipeline.lock` 以独占方式打开，第二个流水线直接失败并提示"另一个流水线正在使用这个 checkout"，所以临界区里从来只有一个写者。事务真正要面对的是**读者**：启动器、卸载器、以及下一次 `sync`。启动器接受 runner 前核对 CMakeCache 的源目录（第 5 章），卸载器读 `data/build-root.txt`，这两处都是"读目录登记、再读产物"的两步操作；若切换恰在两步之间发生，就会读到 A 登记配 B 产物。由此下一条带条件的判断：**在"目录切换是原子的、登记文件是独立写入的"前提下，归属校验能防副本错配，但防不住登记与产物之间的瞬时错位；把当前产物目录编号写进登记本身，才能让两步变成一步**。基座未给 `data/build-root.txt` 的内容格式，此处事实不足，需在 `modules/context`（77 行）处补测。
`replace_file` 处理的是完全不同的一类失败：Windows 扫描器／索引器对刚写出的文件做短暂占用，导致替换失败。它做 6 次有界重试，仍失败才报错——**"在 Windows 上写文件失败是常态，不是异常"的工程化承认**。设每次退避间隔为 d（基座未给），总等待上界为 6 × d；d 的取值与是否指数退避需在 `recompile.py` 处补测。有界（bounded）两个字是关键：无限重试会把一个可恢复的占用变成挂死的流水线，而 `trap` 的 `ERROR: <消息>` 与退出码 1（第 2、5 章）就永远等不到。
断电与崩溃两格里还有一处不对称：进程崩溃可能留下 `data/pipeline.lock` 的残留状态，而单写者锁的提示文案是"另一个流水线正在使用这个 checkout"——若锁没被正确释放，下一个流水线会把它误判成"真有另一个在跑"。基座未给锁的释放与过期机制，此处事实不足，需在 `modules/common`（62 行）与 `modules/process`（67 行）处补测。

### 6.5 所有权感知同步：谁的东西谁拿走

`sync` 只拷贝变化的文件，并把档案里的 overrides 送进 runner。第 2 章把它放在依赖图上"必须紧跟 `recomp`"，本章展开"所有权感知"这四个字。
先划清两类文件的归属：

| 归属 | 例子 | 谁写 | 能否被 `sync` 覆盖 |
| --- | --- | --- | --- |
| 生成物（流水线） | `recomp` 输出的 EE C++、`config/` 投影、`funcmap.csv` 的派生产物 | `recompile.py` | 应当可以 |
| 用户改动（人） | `games/gow1/game.toml`、`engine/patches/*.patch`、runtime `src/` 的 `gow_overrides.cpp` 等三个覆盖层、`data/<id>/loading` 里玩家放的图片、`GOW_MOD_VFS_TABLE`／`GOW_MOD_PATCH_TABLE` 指向的 mod 数据（第 2、5 章） | 维护者／玩家 | 不应当 |

"只拷贝变化的文件"本身不区分归属——按 mtime 或按哈希比对，用户手改过的生成目录内文件同样会被判成"变化"，然后被覆盖。所以所有权感知必然意味着流水线持有一份**归属清单**（manifest），记录哪些路径由它写、以及写入时的摘要；同步时先比对，遇到"流水线写过、但当前内容不是流水线写的那份"就停下来（**推断**：依据是 docstring 明写 ownership-aware、`sync` 只拷变化文件、以及第 5 章 `-ForceRecomp` 与摘要命中的冲突处理；仓库未给清单文件名与冲突策略）。
冲突时谁赢：我的判断是**流水线赢、但必须先报**。理由是生成物是可从 `text_sha1` 与模板重算的，用户手改生成物既不可复现也进不了版本控制，保留它没有工程价值；但"静默覆盖"会把一次手改变成一次难以回溯的丢失，所以"如何发现"比"谁赢"更重要——冲突应当输出一条带路径与摘要差异的 `@@status`，让维护者决定是放弃手改还是把它正式收进覆盖层。可反驳条件：若 `sync` 实际策略是"用户改动赢、跳过该文件的同步"，那么正确用法就变成"改生成物是受支持的临时调试手段"，此时必须配套一个"如何把改动提升为覆盖层"的流程，否则改动会在下一次 `recomp` 后无声消失。基座未给答案，需在 `recompile.py` 与 `modules/game` 处补测。
覆盖层本身是"用户改动不进生成物"的正规通道。PS2Recomp 文档把 game overrides 定义为 runtime 侧、构建作用域（build-scoped）的补丁模块：C++ 代码在 `loadELF` 阶段运行，按地址替换某一特定游戏构建的 EE 函数绑定；它与重编译输出分离，也与全局 runtime stubs／syscalls 分离；IOP 的 RPC／DMA 行为由 `ps2xIOP` 及其 runtime transport 处理。覆盖层按 ELF 名匹配（第 2 章），`[runtime]` 里三个覆盖层文件由档案声明（第 3 章），`sync` 把它们送进 runner——于是"改行为"和"改生成物"被彻底切开：前者走 `src/` 与档案，后者走 `recomp` 与 sha256 key。**条件**：这套分离只在覆盖层确实按地址绑定、且绑定发生在 `loadELF` 而非编译期时成立；若某处把覆盖层内容拼进了生成物，key 就必须把它算进去（回到 6.2.1）。
`GOW_SYNC_DIAG`（第 2、5 章）是这条边界上唯一被点名的诊断开关，用于把同步层的问题暴露出来；它到具体日志行的映射基座未给，需补测。

### 6.6 register-locals 与直接 `jal`：收益来自哪一层

第 7 章会逐条讲 08、15、16、44、52、71、84 号补丁的问题—方案—代价—测量，本节只讲 08 与 28 的**收益来源**，也就是编译器那一层发生了什么。
先看字面翻译（literal translation）。PS2Recomp 把每条 MIPS 指令映射成一个 C++ 操作，官方例子是：

```mips
addiu $r4, $r4, 0x20
```

```cpp
ctx->r4 = ADD32(ctx->r4, 0X20);
```

`ctx->r4` 是结构体成员，不是局部变量。于是约 6,400 个函数的生成物里，guest 寄存器（guest register）几乎全部以内存访问的形式出现：读一次要从 `ctx` 取，写一次要存回 `ctx`。这是语义保真最直接的写法，也把寄存器分配（register allocation）的活全推给了宿主编译器——而 clang 面对一个通过指针访问的结构体，必须保守地假设别名（aliasing），不能随便把 `ctx->r4` 提升到物理寄存器跨多条语句复用。
08 号 register-locals 代码生成把热 guest 寄存器改成宿主局部变量，让 clang 能在函数内做真正的寄存器分配，减少 `ctx` 往返。结果：EE 线程时间约降 22%，且可用 `-Codegen classic` 回到旧行为（**推断**：依据是补丁名 register-locals、上面的字面翻译例子、`-Codegen locals|classic` 参数、以及"EE 线程时间约降 22%"这一给定测量；仓库未给 08 号的实现细节与测量路线）。写成相对式：设基线 EE 线程时间为 T，则 locals 后约为 0.78 × T；T 的绝对值与测量窗口基座未给，不能折算成毫秒。
这里要下一个带条件的判断：**22% 不是"更好的指令"，而是"更少的内存往返"；它只在 guest 寄存器访问密集、且宿主编译器确实能把局部变量分配到物理寄存器时成立。一旦某个函数以 MMIO／DMA／scratchpad 访问为主，或 `-CpuTarget`、LTO 让编译器做了不同的别名判断，收益会缩水甚至消失**。29 号"调度裁剪"与 29a–29f 一族诊断补丁（调用诊断、codegen MMIO 测试、会话帧计量、原生内存回归、scratchpad 链完成、DMA 提交计量）恰好覆盖这些例外：改了代码生成与调度，就得逐项证明 MMIO、内存、scratchpad、DMA 没被改坏。第 7 章的 44 号补丁测法（单变量、交替、可复现路线、写明基线）是同一套纪律的范本，此处只引用一句。
28 号直接 `jal` 的收益来自另一层。MIPS 的 `jal`（jump and link）是直接调用，目标地址在指令里；字面翻译若统一走"查函数地址 → 间接跳转"的调度路径，每条调用都多一次查表与一次间接分支，且 clang 看不到调用图（call graph），无法内联，也无法做跨函数的寄存器与布局优化。把直接 `jal` 编译成直接调用，省掉的是查表与间接跳转，放开的是编译器的调用图优化（**推断**：依据是补丁名"直接 jal"、29 号"调度裁剪"、29a"调用诊断"、以及第 5 章 `GOW_DISPATCH_FULL` 这个"完整调度"开关；四个事实指向同一条调度路径）。`GOW_DISPATCH_FULL` 的存在反过来印证了裁剪是可回退的：诊断时打开它，看调用行为是否回到未裁剪的形状。
把 08、28、29 放在一张表里，收益层级就清楚了：

| 补丁 | 改动层 | 省掉什么 | 放开什么 | 回退手段 |
| --- | --- | --- | --- | --- |
| 08 register-locals | 代码生成 | `ctx` 内存往返 | clang 寄存器分配 | `-Codegen classic` |
| 28 直接 `jal` | 调用发射 | 查表 + 间接跳转 | clang 调用图／内联 | `GOW_DISPATCH_FULL`（**推断**） |
| 29 调度裁剪 | 调度路径 | 不必要的分发 | 更短的热路径 | 同上（**推断**） |
| 29a–29f | 诊断 | 不省，只证明 | 回归可核查 | `verify` 阶段（第 5 章） |

三者都不改 `.text` 摘要，因此都不影响 6.2 的复用判定——它们改的是"同一份输入怎么编译成宿主代码"，不是"输入是什么"。这也解释了为什么 `-Codegen` 归流水线参数而不归 `game.toml`（第 3 章）：把它写进档案会让唯一事实源随机器变化。但代价正是 6.2.1 那个缺口：codegen 变了而 key 没变，生成物可能沿用旧形状，`pgo-check` 才在下游报编译标志不匹配。

### 6.7 一条被反复用到的纪律：失败不破坏可用产物

把 6.3、6.4、6.5 收束成一句可核查的链路：`recomp` 失败 → 事务不切换 → 上一份生成物目录仍在 → `sync` 与 `build` 仍能跑 → `verify` 不需要 ISO 也能验（第 2 章）→ 启动器按 `data/build-root.txt` 与 CMakeCache 归属校验后接受 runner（第 5 章）。整条链上没有任何一步需要"清理现场后再重建"。
条件也明确：**"失败保留上一份可用产物"只在至少存在过一次成功发布时成立**。全新 checkout 的第一次 `recomp` 若失败，没有"上一份"可留，启动器应当直接报缺产物而不是拿半套去跑。基座未给首次失败的提示文案，需在 `modules/distribution`（100 行）与 `LoadingScreen.qml`（第 9 章）处补测。

### 6.8 三条对照轴的小结

**纵向**：`recomp` 在"档案 → 光盘 → 生成 → 构建 → 运行"里占"生成"一格。输入是第 3 章的 `text_sha1`、`config/recomp.template.toml`、`config/funcmap.csv` 与覆盖层声明；输出是约 6,400 个函数的 EE 生成物；`sync` 只拷变化文件并送 overrides；`build` 交给第 5 章的 llvm-mingw；`optimize`／`pgo` 把运行结果回灌成下一轮输入（产物训练产物，第 5 章），但不改变本层的身份判定。
**横向**：Windows 侧 `recompile.py` 254 行、`replace_file` 6 次有界重试、`data/build-root.txt`；Linux 侧 `bash build.sh` → `tools/pipeline/linux.py`（262 行）明确共享同一份档案、光盘准备、**事务式重编译器**与序数补丁链，用 flock 持 `data/pipeline.lock`，产物在 `data/build-linux/<game>`——事务发布是少数几项被基座点名"共享"的机制，而 Windows 的构建根、便携工具、PGO profile 一律不复用（第 2、5 章）。区域格上，本层是矩阵里最平的一格：身份只看 `.text`，所以改数据的翻译版复用同一生成物、`asia-97399` 凭三同复用日版构建（第 3 章）；异码 ELF 被 USA 流水线拒绝，发生在识别层而非生成层（第 10 章）。
**深度**：内容寻址、目录事务、所有权感知同步三者停在"跑对"（可复现、不破坏可用产物、不吞用户改动）；08／28／29 指向"跑快"（约 22% EE 线程时间）；29a–29f 与 `verify` 是"跑稳"的证据链。下一级门槛不是更快的生成器，而是两处可发现性：key 是否覆盖全部生成输入、以及所有权冲突时是否有一条带路径与摘要的显式报错。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会把 sha256 key 从"借 `text_sha1`"扩成**显式输入清单的摘要**：`text_sha1` 加上 `[runtime]` 声明的 `config/recomp.template.toml`、`config/funcmap.csv`、三个覆盖层文件、以及 `engine/patches/*.patch` 按文件名顺序拼出的栈摘要，全部从 `game.toml` 的 `[runtime]` 读，不在 `recompile.py` 里另写一份路径清单；同时让 `-ForceRecomp` 只改变一个显式 nonce，不改变 key 本身。理由是 6.2.1 已写明改模板或补丁栈不触发重生成、却会让 `pgo-check` 在下游报编译标志不匹配，两层错位；显式 nonce 还能让 6.3 的策略 A 变成可观测事件。代价：每次增删 90 个补丁或调覆盖层都要多算一次栈摘要，`fetch` 与 `recomp` 之间多一份必须同步的元数据，且若清单漏了某项输入，会得到"以为锁住了其实没锁住"的虚假安全感——这又逼近 1.4 立下的唯一事实源，所以清单必须复用 `[runtime]` 而不是新开文件。可反驳条件：若 `pgo-check` 的"清单"字段已经逐项覆盖模板、函数表、覆盖层与补丁栈，那么扩 key 就是冗余，正确动作是把该清单同时用作 `recomp` 的复用判据，让两层读同一份真相，而不是再加一份摘要。

本章结论：`recompile.py` 用 sha256(`text_sha1`…) 做 key，让"输入是什么"取代"文件被碰过没有"，从而在每次 `fetch` 重铺 runtime 的环境里保持可复现；目录事务把"失败保留上一份可用产物"兑现成任何时刻读者只看到完整的一套，6 次有界重试承认 Windows 上写文件失败是常态；所有权感知同步把生成物归流水线、用户改动归人，冲突必须先报再覆盖；08 号 register-locals 约降 22% EE 线程时间来自减少 `ctx` 往返，28 号直接 `jal` 来自省掉查表并放开调用图优化。条件是这些判断都建立在"key 覆盖全部生成输入"上，而这一条目前未被证实。遗留疑问六处：key 的完整构成、目录事务在 Windows 上的具体原语与登记文件切换的原子性、`-ForceRecomp` 的实际优先级策略、所有权冲突时谁赢、`replace_file` 的退避间隔 d 与 `data/pipeline.lock` 崩溃后的释放机制、`unity_batch = 16` 与约 6,400 个函数的对应关系，均需在 `recompile.py` 与对应 `modules/` 文件处补测。

## 第 7 章 补丁链精读

本章回答六个问题：90 个补丁为什么按序数命名、头部注释为什么同时是文档；工程／正确性／重编译质量／VU1／GS／产品与系统六类分组各自解决什么问题、代价落在哪一层；08、15、16、44、52、71、84 七个重点补丁逐条的问题—方案—代价—测量；44 号补丁的 52.8 → 54.7 FPS 究竟怎样被测出来、为什么它能当作范本；补丁顺序为什么敏感、区域覆盖层为什么不能混进全局链；以及补丁头注释为什么必须写测量而不是只写"是什么"。

### 7.1 90 个文件，一部按序数排列的性能史

`engine/runtime.toml` 固定仓库 `https://github.com/YYOzcan/Tobiichi-Port` 与 commit `471c83180a8df575cff4abd3fae6c043b5096925`（2026-10-16），`fetch` 阶段克隆该 commit，再按文件名顺序应用 `engine/patches/*.patch`，当前共 90 个补丁文件。第 1 章已立过结论：它们改的是别人的代码，必须能随时重放、随时丢弃；runtime 与上游全部 GPL-3.0，本仓库不能把 runtime 抄进来改干净，只能 pin commit、只能打补丁、只能在 `fetch` 阶段重放，`package` 阶段明确排除 runtime。本章展开这 90 个文件本身。
补丁头部的注释行写明"是什么、为什么"，`git apply` 会忽略它们，所以它们同时是文档。这是本项目最值得学的习惯之一，理由不在好看：`fetch` 每次都从 pin 住的 commit 重新克隆，补丁是唯一留下来的本地改动，若"为什么"只存在某次提交的 message 或某人的记忆里，重放一次就丢一次。注释随文件走，重放到哪就带到哪。
按主题分六类，下表是基座给出的举例清单逐类计数（不是全表）：

| 类 | 举例序号 | 举例数 |
| --- | --- | --- |
| 工程 | 01、04、31、32、42 | 5 |
| 正确性 | 03、06、12、24、40、47 | 6 |
| 重编译质量 | 08、28、29 + 29a–29f | 3 + 6 = 9 |
| VU1 | 02、09、10、13、17、18、20、22、27、33、34、35、37、43、45、50、51、60、63、76、78、79、81、82 | 24 |
| GS | 39、44、46、59、61、66、67、68、69、70、72、74、75、77、83 | 15 |
| 产品与系统 | 15、16、23、25、26、52、53、54、55、56、57、58、71、73、84 | 15 |
| 合计 | 最大序数 84 | **74**​ |

74 不等于 90，也不等于最大序数 84，这正是一处可以验算的可核查细节。把举例清单拆成"数字序数"与"字母后缀"两部分：29a–29f 是 6 个后缀文件，故数字序数举例为 74 − 6 = 68 个；若数字序数从 01 到 84 各占一个文件，则 84 + 6 = 90，与"当前共 90 个补丁文件"吻合，未被举例的数字序数为 84 − 68 = 16 个。**推断**：依据是基座给出总数 90、举例最大序数 84、以及 29a–29f 这一整族后缀；仓库未给 `engine/patches/` 的完整目录，需在列目录处补测。若该推断成立，则"按文件名顺序应用"用的是字符串序而非数值序——`29.patch` 之后是 `29a.patch`…`29f.patch`，再之后才到 `30.patch`（'.' 的码位小于 'a'，'2' 小于 '3'，属通识）；后缀族因此天然紧跟它的主补丁，这不是巧合而是命名设计。
六类不是按文件类型分，是按"改动的层"分：工程类动编译与链接期，正确性类动语义，重编译质量类动生成物与调度，VU1／GS 两类动运行期热路径，产品与系统类动 UI、输入、mod 与分发。这张分组表本身就是全书的深度轴索引：正确性类把部件从"能跑"推到"跑对"，重编译质量与 VU1／GS 类推向"跑快"，环溢出保护、加固、不变量类守"跑稳"。

### 7.2 工程类：把编译期的不确定性钉住

| 补丁 | 问题 | 方案 | 代价 | 测量／回退 |
| --- | --- | --- | --- | --- |
| 01 | Release 链接时间不可接受 | LTCG（link-time code generation）做成开关，默认不开 | 链接以小时计 | 默认关闭；`-Ltcg` 开启 |
| 31 | 01 的等价物太重 | ThinLTO | 仍需链接期跨单元优化时间 | 基座未给测值，需补测 |
| 32 | 数学路径想吃满指令集 | 至强 AVX2 数学标志 | 产物绑死 CPU，`portable` 目标下不可用 | 与 `-CpuTarget portable｜x86-64-v3` 的关系需补测（第 5 章） |
| 42 | runtime 的 CMake 依赖是 git checkout，全量 clone 慢且长路径易撞 MAX_PATH | 依赖浅克隆 | 历史被截掉，某些依赖操作无法回溯 | 与 `C:\gow-build` 短根（第 5 章）配套 |
| 04 | 从 Waffle 回合带过来的 CPU 补丁 | 回合合入 | 与 32 同改指令集假设，顺序敏感 | 基座未给测值，需补测 |

这一类的共同点是**不在运行期露面**：它们改的是"同一份 C++ 怎么变成 exe"，因此不触动 `text_sha1`、不触发 `recomp` 重生成（第 6 章的 key 构成缺口），也不会被 `identify.py` 的五个字段看见。代价却会在最下游一次付清——`pgo` 的 profdata 与"本次编译标志"一一绑定，`pgo-check` 四项校验里第三项就是编译标志（第 5 章）。于是产生一条具体的失效链：改了 31 或 32 → 生成物摘要不变、`recomp` 复用 → 编译标志变了 → `pgo-check` 失败 → 必须重训。中间没有任何一层说"这个补丁动了编译期，去把 profile 作废"。
01 的"默认不开，链接以小时计"是本章第一处带条件的判断素材：**LTCG 的收益（跨单元内联）与代价（小时级链接）在 90 个补丁的重放环境里不对称——每次 `fetch` 都可能重新链接一遍，所以默认关闭是对的；只有在出发布包、且该轮不再改补丁栈时才值得开 `-Ltcg`**。可反驳条件：若 `-CompilerCache sccache` 能把 LTCG 的链接结果缓存下来，小时级代价就退化成首次代价，默认关闭的判断需要重算；基座未给 sccache 对 LTCG 的命中情况，此处事实不足，需在 `modules/toolchain`（41 行）处补测。

### 7.3 正确性类：六条语义边界

| 补丁 | 问题 | 方案 | 代价 | 可核查点 |
| --- | --- | --- | --- | --- |
| 03 | 全屏崩溃 | 修全屏路径 | 基座未给根因 | 需补测 |
| 06 | `movn`／`movz` 的 64 位语义 | 修条件移动的位宽 | 字面翻译逐条保真，一处改错影响全生成物 | EE 约 6,400 个函数（约数）共用同一发射规则 |
| 12 | clang 下 GS 状态比较 | 修比较逻辑 | 与编译器绑定 | `-Toolchain msvc` 只是迁移别名，组件一律钉死 llvm-mingw（第 5 章） |
| 24 | 音频混音溢出 | 修溢出 | 属原生服务，不进重编译管线（第 1 章） | `sound_regression.cpp`（第 10 章） |
| 47 | GL 上下文回退 | 加回退路径 | 多一条渲染器初始化分支 | 与 `GOW_GS_*` 诊断面的关系需补测 |
| 40 | GS 提前结束 | 修提前结束 | 与 VU1 线 33／34／35 的"提前结束与自环"同名不同层 | `GOW_GS_EARLY_FINISH`（第 2、5 章） |

06 号值得单独一句。PS2Recomp 的翻译是字面式的（literal），每条 MIPS 指令映射成一个 C++ 操作，官方例子 `addiu $r4, $r4, 0x20` → `ctx->r4 = ADD32(ctx->r4, 0X20);`；这类发射规则由重编译器统一生成，一处 64 位语义写错，会同时污染约 6,400 个函数（约数）里所有用到 `movn`／`movz` 的地方，而不是只坏一个场景。所以正确性补丁的测量方式天然与性能补丁不同：**性能补丁可以用一段路线的帧率证明，语义补丁必须靠 `tools/test/` 下的 C++ 单测（`guest_codegen_tests.cpp`、`guest_memory_tests.cpp`、`guest_calls.cpp`、`dma_worker_tests.cpp`）逐项兜底**（第 2、10 章）。
40 与 33／34／35 都叫"提前结束"，却分属 GS 线与 VU1 线，是六类分组里最容易误读的一处：前者动的是 GS 命令流的结束判定（对应 `GOW_GS_EARLY_FINISH`），后者动的是 VU1 微码块的提前结束与自环。把两者当成同一件事去合并补丁，会把两条不相干的流水线打穿。

### 7.4 重编译质量类：08、28、29 与 29a–29f

### 7.4.1 08 号 register-locals（重点）

第 6 章已从编译器层拆过收益来源：字面翻译把 guest 寄存器写成 `ctx->r4` 这样的结构体成员，clang 面对指针别名必须保守，无法把值提到物理寄存器跨语句复用；08 号把热 guest 寄存器改成宿主局部变量，放开寄存器分配。本节只讲它作为补丁的四段。
**问题**：EE 线程时间被 `ctx` 内存往返吃掉，而不是被算术吃掉。
**方案**：改代码生成（codegen），产出 register-locals 形态的生成物。
**代价**：改动的是全局发射规则，不是某个函数；MMIO、DMA、scratchpad、原生内存这些"必须真的读写内存"的路径一旦被错误地提升成局部变量，语义就坏了。因此 29a–29f 一整族诊断补丁不是可选项，是 08 的配套验收：调用诊断、codegen MMIO 测试、会话帧计量、原生内存回归、scratchpad 链完成、DMA 提交计量，六项各守一条边界。
**测量**：EE 线程时间约降 22%（约数），可用 `-Codegen classic` 回到旧行为。写成相对式：设基线 EE 线程时间为 T，locals 后约 0.78 × T；T 的绝对值与测量窗口基座未给，不能折算成毫秒。
结论带条件：**22% 只在 guest 寄存器访问密集、且宿主编译器确实把局部变量分配到物理寄存器时成立；一旦某函数以 MMIO／DMA／scratchpad 为主，或 `-CpuTarget`、LTO 改变了别名判断，收益缩水甚至消失**。`-Codegen classic` 的存在让这个判断可反驳——同一份 `.text`、同一台机器，切换参数再跑一次 `perf-compare.ps1` 即可验（第 3、5 章）。

### 7.4.2 28、29 与诊断族

| 补丁 | 问题 | 方案 | 代价 | 回退／验收 |
| --- | --- | --- | --- | --- |
| 28 直接 `jal` | 字面翻译把直接调用走成"查函数地址 → 间接跳转"，多一次查表与间接分支，且 clang 看不到调用图 | 直接调用发射 | 只对目标地址静态已知的 `jal` 成立；寄存器间接跳转仍需 `vu1n_heads.txt` 一类入口表补（第 3 章） | 29a 调用诊断；`GOW_DISPATCH_FULL`（第 5 章） |
| 29 调度裁剪 | 热路径上不必要的分发 | 裁掉 | 调度形状变了，`pgo-check` 的编译标志／清单校验可能失配，必须重训 | `GOW_DISPATCH_FULL`（**推断**） |
| 29a–29f | 08／29 改了代码生成与调度，需要逐项证明没改坏 | 六族诊断补丁：调用诊断、codegen MMIO 测试、会话帧计量、原生内存回归、scratchpad 链完成、DMA 提交计量 | 不省时间，只增加可核查性 | `verify` 阶段，不需要 ISO（第 2 章） |

29a–29f 按字符串序紧跟 29，是"补丁顺序敏感"最直观的一例：它们读的是 29 裁完之后的调度形状，若被排到 29 之前，诊断对象就不是同一个程序了。这里也要区分"诊断补丁"与"功能补丁"在深度轴上的位置——前者不推动任何部件升级，只把 08／29 的收益钉成可复现的证据，属"跑稳"。

### 7.5 VU1 线：24 个补丁串成的六段演进

第 8 章会讲 VU1 从解释器到 AOT 微码再到 x64 JIT 的原理与 GS/VU1 协同；本节只按补丁层逐条记账，不重复机制。

| 段 | 补丁 | 问题 → 方案 | 代价 |
| --- | --- | --- | --- |
| 块链接 | 02、09、10、13 | 微码块各自进出解释器，边界开销大 → 块间直接链接 | 链接只对已识别的目标成立；寄存器间接跳转仍靠 `vu1_native_heads`（第 3 章） |
| 编译时机 | 17 后台编译、18 x64 JIT、20 emitter 预留、22 分析缓存 | 编译卡在运行路径上 → 移后台／上 x64／预留发射缓冲／缓存分析结果 | 17 引入并发；18 依赖 System V 的 x64 JIT 路径，Linux 侧"已编译但未验证"（第 10 章）；22 的缓存失效条件需补测 |
| 提前结束 | 27 速度、33／34／35 提前结束与自环、37 隔离任务重放 | 微码块结束判定与自环绕远路 → 修判定、隔离重放 | 与 40 号 GS 提前结束同名不同层（见 7.3） |
| 原生代码形状 | 43 更瘦的原生代码、45 惰性成对解码、50 小帧运行、51 快速模式、60 JIT 快速模式 | 生成代码体积／解码成本／小帧开销 | 43 是 44 号测量的基线（见 7.6.1）；45 惰性化后首次命中延迟需补测 |
| 热入口 | 63 热入口、76 链预热 | 船战里反复进出的块每次冷启动 | 与 `vu1_native_heads` 解决的约 120 万次／5 秒船战边界是同一问题的两个面（第 3 章） |
| 算术与时序 | 78 累加器、79 VF 前递、81 辅助函数去重、82 时序不变量 | 累加器／VF 前递／重复辅助函数／时序漂移 | 82 属"跑稳"，与 `GOW_IOP_DRIFT`、23／55 号 IOP 补丁的时序纪律同族（第 5 章） |

24 个补丁里唯一带跨章引用价值的是 43：44 号的测法明确"在 43 号之上跑"，所以 43 不只是"更瘦的原生代码"，它是 52.8 → 54.7 FPS 这组数字的基线定义。若单独重放 44 而不带 43，得到的帧率差不能与 44 号注释里的数字比较——这是"补丁顺序敏感"最硬的一处实证。
把边界开销折算一次：缺 `vu1_native_heads` 时 5 秒船战进出原生代码约 120 万次，即约 24 万次／秒；按 60 Hz 客机帧为 120 万 ÷ (5 × 60) = 4,000 次／客机帧（约数，第 3 章已列）。VU1 线 24 个补丁合起来要压的就是这个 4,000，而不是单条 VU 指令的算术周期——**性能问题往往不是算术问题，而是边界问题**，第 1 章立的句式在这里被 24 个文件逐条坐实。

### 7.6 GS 线：15 个补丁与一条队列

第 8 章讲 GS 环、GIF 零拷贝、图元批、深度与 ZBP、异步提交的机制；本节按补丁层记账。

| 补丁 | 问题 → 方案 | 代价／关联 |
| --- | --- | --- |
| 39 | 游戏菜单实时图形 | 菜单也要走渲染器，不再是静态页 |
| 44 | stage 队列每包抢锁 → SPSC 字节环 | 见 7.6.1，本章重点 |
| 46 | GIF 零拷贝 | 与 59 顶点环、61 shuffle 纹理复用同属"少搬一次"族 |
| 59、61 | 顶点环／shuffle 纹理复用 | 环与复用都引入生命周期约束 |
| 66、72 | 图元批／批前奏 | `afterBatch` 仍在每批后执行（44 号明确保留） |
| 67 | 环溢出保护 | 44 号 4 MB 上限的安全网 |
| 68、69 | 停顿与深度 ZBP／每 ZBP 深度 | 深度一致性属"跑稳" |
| 70 | GPU 帧计时 | 与 `frame_pc = "0x1837B8"`（`vid::Flip`）的客机帧是两套刻度（第 3 章） |
| 74、75 | 运行态与加固 | 74／75 成对 |
| 77 | 异步提交 | `GOW_GS_FINISH_ASINCRONO`（第 2、5 章） |
| 83 | 不变量 | 断言型补丁，属"跑稳" |

### 7.6.1 44 号精读：单生产者单消费者字节环（重点）

**问题**。船战时 worker 每秒约 24 万包；原实现每包都抢 mutex 与 vector，约 60% 的唤醒要走内核（kernel），每秒约 15 万次上下文切换（context switch）。三个数字可以互相验算：

```text
240,000 包／秒 × 60% = 144,000 ≈ 15 万次／秒（基座给"约 15 万"，保留约数）
240,000 ÷ 60 客机帧/秒 = 4,000 包／客机帧
150,000 ÷ 60 客机帧/秒 = 2,500 次上下文切换／客机帧
```

即每个客机帧约 4,000 包、约 2,500 次进内核。这不是算术吞吐问题，是同步原语的固定成本被乘上了 4,000。
**方案**。改成单生产者单消费者（SPSC, single-producer single-consumer）字节环：写入环、原地读取，只在真睡时用锁与条件变量（condition variable）；stage 先自旋（spin）至多 `GOW_GS_STAGE_SPIN_US`（默认 50，0 表示立刻睡）。队列字节上限仍是 4 MB，超过 1 MB 的包走堆拷贝，`afterBatch` 仍在每批后执行。两条环境变量原值：

```text
GOW_GS_STAGE_SPIN_US=50
GOW_GS_STAGE_SPIN_US=0
```

"只在真睡时用锁"是收益的全部来源：绝大多数包在生产者写、消费者读的环里就交接完了，锁与条件变量退化为"环空／环满且自旋耗尽"的慢路径。自旋 50 微秒（**推断**：变量名带 `US`，基座给默认 50 与 0 表示立刻睡，单位未明写）则是把短等待留在用户态。
**代价与条件**。4 MB 是硬上限，超过 1 MB 的单包走堆拷贝——于是可以写一条带条件的结论：**在 4 MB 队列上限内、且单包不超过 1 MB 时，字节环优于锁队列；一旦单包超过 1 MB，堆拷贝会把收益吃掉**。再给一个边界算式：4 MB ÷ 1 MB = 4，即连续四个超大包就足以顶到队列字节上限，此时生产者要么等、要么继续堆拷贝，SPSC 的零拷贝前提不再成立。`afterBatch` 保留在每批后执行，说明 66／72 的图元批语义没有被 44 改掉，这是"单变量"的一部分。
**测量**。在 43 号之上跑存档路线、全屏、4 组交替对比：战斗 52.8 → 54.7 FPS，4 组全胜。算式：

```text
54.7 − 52.8 = 1.9 FPS
1.9 ÷ 52.8 ≈ 3.6%
```

"4 组全胜"比 1.9 FPS 更重要：它排除了单次跑动的抖动。这一段要当作"如何证明一个优化真的有效"的范本，四个要素逐条可核查——**单变量**（基线定义在 43 号之上，只换 44）、**交替**（4 组 A/B 交替而非先跑 4 次旧再跑 4 次新，避开机器热状态与后台负载漂移）、**可复现路线**（存档路线，不用每次现打）、**写明基线**（52.8 与全屏这一呈现条件，与第 3 章 `frame_pc` 的客机帧口径一致）。
反面参照就是任务书里禁掉的那种句子："该项目采用了先进的技术架构，性能得到显著提升"——没有主语、没有基线、没有测量。44 号注释里能写出"在 43 号之上、存档路线、全屏、4 组交替、52.8 → 54.7"，是因为补丁头注释被当成文档写，而不是当成提交说明随手写。

### 7.7 产品与系统线：15 个补丁与三个重点

### 7.7.1 逐条记账

| 补丁 | 问题 → 方案 | 代价／关联 |
| --- | --- | --- |
| 23 | IOP 稳定输出 | 与 55 IOP 分片同属 IOP 线；`GOW_IOP_DRIFT`（第 5 章） |
| 25 | 独立启动档案 | 每语言一目录的运行模型（第 2 章）需要独立档案 |
| 26 | 存档页截图去重 | 与 `TOBIICHI_CAPTURA=<png>` 自动化钩子同族（第 2、9 章） |
| 53 | QTE 长按 | `GOW_QTE_HOLD`、`GOW_QTE_HOLD_HZ`；`qte_hold_test.cpp`、`qte_input_test.cpp`（第 10 章） |
| 54 | 影片陈旧包 | 与 `[disc]` 的 `.PSW` → `.PSS` 回退、占位影片精确字节判据（第 3 章） |
| 55 | IOP 分片 | 分片后输出确定性由 23 守 |
| 56 | 键盘摇杆手势 | 默认键鼠布局可在启动器重映射（第 2 章） |
| 57／58 | 和弦保持 | 成对，与 53 同属输入辅助（`AccessibilityPage.qml`，第 9 章） |
| 73 | 启动器 mod 管理器 | `mods_model.cpp` 807 行（第 9 章） |

### 7.7.2 15 号隐藏窗口（重点）

**问题**：`optimize` 要让游戏自己跑 240 秒录 VU1 微码与 IOP 模块，但这段训练不能弹窗抢焦点、不能出声，且必须真跑出客机帧而不是空转。
**方案**：隐藏窗口做进 runtime，靠环境变量组合驱动：

```text
GOW_WINDOW_HIDDEN=1
GOW_AUDIO=0
GOW_AUDIO_PCM=NUL
GOW_VU1_CAPTURE_MISSES=1
GOW_VU1N_X64=1
GOW_PAD_GUION=<脚本>
```

**代价**：窗口不可见后，人工看不见训练是否正常，截图自动化与诊断必须另开钩子（`TOBIICHI_CAPTURA=<png>`、`GOW_VU1N_DIAG`、`GOW_SYNC_DIAG`，第 2、5、9 章）；`GOW_AUDIO_PCM=NUL` 把 PCM 输出导到空设备，音频混音路径虽仍在跑，24 号补丁修过的溢出问题却不再有可听反馈。
**测量**：240 秒脚本 `5:start,12:x,18:x,24:x,30:x,36:x,40:cuadrado,…` 跑完产生录制的微码与 IOP 模块；`GOW_VU1_CAPTURE_MISSES=1` 记录没录到的块；`pgo-check` 的覆盖率校验是最终兜底（第 5 章）。脚本里 `cuadrado`、`triangulo`、`circulo` 是西班牙语按键名，暴露 runtime 从南美社区项目长出来的血统（第 3 章）——把它"修正"成 `square` 会让 240 秒录出空轨迹，`pgo-check` 以覆盖率不足失败。

### 7.7.3 16 号只重建 VU1（重点）

**问题**：`optimize` 录完新微码与 IOP 模块后，若全量重跑 18 个阶段，`recomp` 的约 6,400 个函数生成物、`build` 的全量编译、`pgo` 的二次构建都要再来一遍，而它们没有一行需要变。
**方案**：`native` 阶段只重建 VU1／IOP。
**代价**：16 号划的边界是"只重建这两部分"，因此 EE 生成物与 profdata 被假定不变；一旦 runtime 或 90 个补丁任一变更，`pgo-check` 的编译标志／清单校验会失配，仍必须重训（第 5 章"产物训练产物"）。也就是说 16 号的增量优势有前提：**变更必须是录制数据，不是代码形状**。
**测量**：`optimize→native` 成对出现在 18 阶段里（第 5 章），A 闭环训练的是数据、可增量；B 闭环训练的是编译决策、不能只重训一半。A 的验收信号不是构建成功，而是解释器边界次数是否下降（约 120 万次／5 秒船战，第 3 章）。

### 7.7.4 52 纹理包、71 mod VFS 钩子、84 mod 数据补丁（重点）

三者是一条链，必须连起来读。
**52 纹理包**：问题是纹理替换需要入口；方案是纹理包，对应 `GOW_TEXTURE_PACK`，由 `AccessibilityPage.qml` 管（第 2、9 章）。代价：纹理包与 mod VFS 的表驱动路径并存，替换优先级需补测。测量：基座未给，此处事实不足，需在 `engine/patches/` 对应补丁与 `tools/test/` 处补测。
**71 mod VFS 钩子**：问题是 mod 要读光盘数据必须挂到路径解析层；方案是 mod VFS（virtual file system）钩子；代价落在三个环境变量上：

```text
GOW_MOD_VFS_TABLE
GOW_MOD_PATCH_TABLE
GOW_MOD_VFS_LOG
```

`GOW_MOD_VFS_LOG` 是这一层唯一被点名的可观测出口——出问题时"打开哪个开关、看哪一行日志"的二分路径（第 2、5 章）在这里具体化为"打开 log，看哪张表里缺了哪个路径"。测量：`GOW_MOD_VFS_LOG` 的日志行；具体格式基座未给，需补测。
**84 mod 数据补丁**：问题是 mod 不只要替换文件，还要改数据内容；方案是 mod 数据补丁，与 71 的 VFS 层叠加、`GOW_MOD_PATCH_TABLE` 承接。代价：数据补丁与 `[executable].text_sha1` 的身份判定无关（它改的是数据，第 3 章），但会改 `.disc_layout` 指向的文件内容——第 4 章"目录可被用户手工改动"的缺口在这里被正式合法化，于是第 2 章那条"没有任何一层能证明跑起来的目录就是 prepare 产出的目录"的判断变得更需要一层摘要校验。测量：基座未给，此处事实不足，需在对应补丁与 73 号启动器 mod 管理器处补测。
三个补丁合起来的结论带条件：**在 mod 只改数据、不改 `.text` 的前提下，52／71／84 不触发重编译、不影响 `text_sha1` 复用；一旦某个 mod 替换了 `SCUS_973.99` 本身或 IRX 模块，它就从"数据 mod"越过身份边界，USA 流水线应当按异码 ELF 拒绝，而不是静默跑起来**。基座未写 71／84 是否校验 ELF 身份，需补测。

### 7.8 顺序为何敏感、区域覆盖层为何隔离、注释为何必须写测量

**顺序敏感**有四条实证，不止一条：

1. 44 号的测法"在 43 号之上"，43 定义基线，顺序错了数字不可比（7.6.1）。
2. 29a–29f 按字符串序紧跟 29，诊断对象必须是裁完之后的调度形状（7.4.2）。
3. 01／31／32 同动编译与链接期，04 又带 CPU 补丁，四者的先后顺序决定最终编译标志，进而决定 `pgo-check` 的编译标志校验是否通过（7.2）。
4. `fetch` 按文件名顺序应用，字母后缀族自然插在主补丁之后；若改成数值排序或按 mtime，`29a` 会被排到别处，整族诊断失效（7.1）。

再加一条跨层推论：补丁顺序变化会改变 runtime 源码形状，而 `pgo` 的 profdata 与本次编译标志、源码形状一一绑定，所以**任何一次补丁增删或改序都必须重训**，否则 profile 指向不存在的形状（第 5 章）。这把"顺序敏感"从写补丁的纪律提升成发布流程的硬条件。
**区域覆盖层不能混进全局链**的理由有三层。其一，作用域不同：90 个补丁改的是 `fetch` 出来的公共 checkout，对每个 `code` 都生效；区域覆盖层是条件性（conditional）的，只对某一区域构建生效，存于 `games/gow1/regions`，含基线源码哈希、函数区间与重编译入口提示（第 3 章）。混进全局链等于给 USA runtime 偷偷打了一份别人的补丁。其二，纯度不同：`fetch` 是"clone + 按序 apply"的纯重放，随时可丢弃；一个条件性文件会让重放结果依赖"当前是哪个区域"，破坏第 1 章立下的"随时重放、随时丢弃"。其三，验证路径不同：欧洲与日本各有经过"初始船战"验证的独立 Windows 构建，`tools/pipeline/register_region.py` 登记进 `data/<game>/regional-builds.json`，启动器校验归属、CMake 源目录与 ELF／runner 哈希后并入版本选择器（第 3 章）——这套校验的前提正是区域改动不在全局补丁栈里，否则哈希无从定义。
**补丁头注释必须写测量**，理由由 44 号反证给出。注释行写"是什么、为什么"，`git apply` 忽略它们，所以它们同时是文档；但 90 个补丁里，基座明确给出完整测法的只有 44 号（基线 43、存档路线、全屏、4 组交替、52.8 → 54.7、4 组全胜），08 号给出约 22% EE 线程时间与 `-Codegen classic` 回退，其余多数只给了主题名。**没有测量的"为什么"无法被复核**：后人重放补丁栈时，无法判断某条优化在当前 runtime 上是否仍有效、是否已被后续补丁抵消、是否只在那台机器上成立。于是注释里应当至少有四个字段：基线是谁（如 43 号）、测法是什么（路线／呈现条件／交替组数）、结果是多少（带单位与客机帧口径）、怎么回退（参数或开关）。44 号四个字段齐全，08 号缺测法与呈现条件，52／71／84 缺全部——这就是本章反复写"此处事实不足，需在 X 处补测"的原因。

### 7.9 三条对照轴的小结

**纵向**：补丁链作用在"生成 → 构建 → 运行"三格上，不碰"档案 → 光盘"两格。工程类（01／04／31／32／42）落在构建格，重编译质量类（08／28／29／29a–29f）落在生成格与构建格交界，VU1／GS 两类落在运行格，产品与系统类跨运行格与产品化格。`identify.py` 的五字段 JSON 与 `game.toml` 的九个节没有一个补丁需要改——补丁改的是"怎么处理已知输入"，不是"输入是什么"。
**横向**：Windows／Linux 共享同一份档案、光盘准备、事务式重编译器与**序数补丁链**（`bash build.sh` → `tools/pipeline/linux.py` 262 行，第 2 章），所以 90 个补丁的 `fetch` 重放在两格上形状相同；但 18 号 x64 JIT 依赖 System V 路径，Linux GPU 路径"已编译但未验证"，32 号 AVX2 数学标志与 `-CpuTarget portable|x86-64-v3` 的绑定在 Linux 侧是否同样成立未给（第 5、10 章）。区域格上，USA／欧洲／日本是三套 `code`，`asia-97399` 凭三同复用 `code = "japan"`（第 3 章）；四格共享同一条全局补丁链，差异全部锁在 `games/gow1/regions` 的条件性覆盖层里——这是横向矩阵里唯一被刻意做成"共享链 + 隔离层"的一处。
**深度**：正确性类（03／06／12／24／40／47）把部件从"能跑"推到"跑对"；08（约 22% EE 线程时间）、28、29、44（52.8 → 54.7 FPS）推向"跑快"；67 环溢出保护、68／69 深度 ZBP、74／75 加固、82 时序不变量、83 不变量与 29a–29f 诊断族守"跑稳"。下一级门槛不是再加补丁，而是给每条性能补丁补上 44 号那种可复现测法——没有测法，"跑快"无法与"跑稳"区分。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会把补丁头注释里的"测量"从自由文本升级成四个机器可读字段（基线补丁号、测法标识、结果数值与口径、回退开关），并让 `verify` 阶段读它做一次"该字段是否填齐"的断言，而不是去复跑 240 秒路线。理由是 7.8 已写明 90 个补丁里只有 44 号四字段齐全，`docs/research/` 的 25 篇归档又是按日期的证据而非按补丁的契约（第 10 章），两者之间缺一条"这个补丁还有效吗"的自动答案；断言只查字段是否填齐，不查优化是否仍有效，成本极低。代价：注释格式变成契约，`git apply` 虽仍忽略它，但解析工具要跟格式走，且每个存量补丁都得补一次测法才能填字段——52／71／84 这类没有测值的补丁会立刻暴露成"待补测"，反而增加维护压力。可反驳条件：若 `docs/research/` 已经建立了"补丁号 → 归档文档"的索引，正确做法是给补丁头加一个指向归档的字段、让证据留在归档里，而不是把测量结果塞进注释——那会与第 10 章"docs 是契约、research 是证据"的分层直接冲突，也会在 `fetch` 重放时把一份过期证据当成永久契约。

本章结论：90 个补丁按数字序数 01–84 加 29a–29f 六个字母后缀构成（**推断**，84 + 6 = 90），分工程、正确性、重编译质量、VU1、GS、产品与系统六类；08 用 register-locals 约降 22% EE 线程时间但必须配 29a–29f 验收，15／16 把 240 秒录制收敛成可增量重建的 A 闭环，44 号把每包一次的 mutex 换成 SPSC 字节环并在 43 号之上、存档路线、全屏、4 组交替下把战斗从 52.8 提到 54.7 FPS（4 组全胜），52／71／84 串成纹理包—VFS 钩子—数据补丁的 mod 链；顺序敏感有四条例证，区域覆盖层因作用域、纯度、验证路径三重隔离不得进全局链，补丁头注释必须写测量才能被复核。条件是这些结论都建立在"注释里的测量字段可核查"上，而目前多数补丁缺测值。遗留疑问六处：`engine/patches/` 的完整目录与 90 个文件的构成、31／32／04 的编译期测值与 sccache 对 LTCG 的命中、03／06／12／24／47 的根因、`GOW_GS_STAGE_SPIN_US` 的单位、52／71／84 的测量与 ELF 身份校验、以及 `afterBatch` 与图元批在 4 MB 上限附近的交互，均需在对应补丁与 `modules/` 文件处补测。

## 第 8 章 图形与 VU1
本章回答四个问题：GS 侧的字节环、GIF 零拷贝、图元批、深度 ZBP 与异步提交怎样串成一条流水线，而不是十五个孤立补丁；客机帧、宿主呈现率、GPU 帧计时三套刻度为什么不能互相折算；纹理包与 mod VFS 作用在上传路径的哪一段、与零拷贝如何相互约束；以及 VU1 从解释器到提前编译微码再到 x64 JIT 的演进里，热入口与链预热为何对 5 秒船战关键，最后落到"编译通过 ≠ GPU 验证"这条方法论上。

### 8.1 GS 侧：按数据流分段读十五个补丁

第 7 章按补丁层记过账：39、44、46、59、61、66、67、68、69、70、72、74、75、77、83 共 15 个 GS 补丁，44 号的 SPSC 字节环已在 7.6.1 精读，本节不重复其测法，只把它放回整条流水线里，看上下游各由谁守。
分层依据来自基座 2.2：GS 的原生替代是 OpenGL 渲染器，GPU render target，内部分辨率 1×–8×。它不进入重编译管线（第 1 章），所以这 15 个补丁动的都是"原生服务怎么把绘制命令搬到 GPU"，不是"EE 代码怎么翻译"。PS2 侧的数据路径是 EE 经 VIF 交给 VU1，再由 GIF（Graphics Interface）把图元数据送进 GS，这是通识；本项目特有之处是这条路径在 Windows 上被重写成"worker 打包 → stage 队列 → 渲染线程 → OpenGL"，每个补丁都卡在其中一段。

| 段 | 补丁 | 动的是什么 | 上下游约束 |
| --- | --- | --- | --- |
| 采集与搬运 | 46 GIF 零拷贝、59 顶点环、61 shuffle 纹理复用 | 少搬一次：GIF 数据不复制、顶点进环、纹理 shuffle 后复用 | 零拷贝后指针生命周期变长，纹理替换必须在上传前完成（见 8.3） |
| 排队 | 44 stage 字节环、67 环溢出保护 | 每包一次 mutex → SPSC 环；4 MB 上限的安全网 | 见第 7 章；`GOW_GS_STAGE_SPIN_US` 默认 50，0 表示立刻睡 |
| 成批 | 66 图元批、72 批前奏 | 把包攒成批再提交 | 44 号明确 `afterBatch` 仍在每批后执行，批语义未被环改掉 |
| 深度 | 68 停顿与深度 ZBP、69 每 ZBP 深度 | ZBP（Z buffer pointer，深度缓冲基址指针，通识）切换时的一致性 | 与 77 的异步提交共享同步点（见 8.1.2） |
| 提交与收口 | 77 异步提交、40 GS 提前结束、74／75 运行态与加固、83 不变量 | FINISH 与提交时机、运行态、断言 | `GOW_GS_FINISH_ASINCRONO`、`GOW_GS_EARLY_FINISH` |
| 测量 | 70 GPU 帧计时、39 游戏菜单实时图形 | 第三套时间刻度、菜单也走渲染器 | 与 `frame_pc = "0x1837B8"` 并列，见 8.2 |

### 8.1.1 从 24 万包到 4 MB 上限

第 7 章给过三个原值：船战时 worker 每秒约 24 万包，原实现约 60% 的唤醒要走内核、每秒约 15 万次上下文切换。本节补它们在这条流水线上的位置——这是**入队侧**的数字，不是 GPU 侧。

```text
240,000 包／秒 ÷ 60 客机帧/秒 = 4,000 包／客机帧
150,000 次上下文切换／秒 ÷ 60 = 2,500 次／客机帧
4 MB ÷ 1 MB = 4 个超大包即可顶到队列字节上限
```

第二个算式的 60 来自第 1 章：游戏逻辑绑在 PS2 的 60 Hz VBlank 上，移植体保持真实速度，掉帧而不减速。第三个算式是第 7 章"超过 1 MB 的包走堆拷贝、队列字节上限仍是 4 MB"的直接推论。把三行并起来看，44 号解决的其实是**入队侧放大**：每客机帧 4,000 包，每包一次 mutex 的固定成本被乘了 4,000 倍；改成 SPSC 环后，锁与条件变量只在环空／环满且自旋耗尽时才用，绝大多数包在用户态交接完。
出队侧的约束由 67 守：环是固定字节上限的，生产者写满必须等，溢出保护防的是"背压（backpressure）下丢包"。这里能下一条带条件的判断：**在 4 MB 上限内、单包不超过 1 MB 时，字节环优于锁队列；一旦单包超过 1 MB 走堆拷贝，或 GPU 背压让环长期接近满，收益会被拷贝与等待吃掉，此时瓶颈已经从入队侧移到 70 号测的 GPU 侧**。这是同一条优化在不同负载区间换主导项，不是补丁失效。

### 8.1.2 批、深度与同步点

66 图元批与 72 批前奏把包攒成批，44 号保留 `afterBatch` 在每批后执行，说明批是一个语义边界，不只是缓冲策略。68／69 处理的是另一类边界：ZBP 切换时的深度一致性——68"停顿与深度 ZBP"、69"每 ZBP 深度"，两者合起来读作"每次 ZBP 变化都要重新确认深度状态，必要时停顿"（**推断**：依据是补丁名的并列结构与 70／83 的测量／断言型补丁同处 GS 线；仓库未给 ZBP 切换的具体实现，需在对应补丁处补测）。
77 异步提交与 40 GS 提前结束都动提交时机，一个把 FINISH 往后挪、一个把结束判定提前，二者共享同一个同步点。由此得到一条可反驳的判断：**异步提交只在 FINISH 同步点被正确延后、且 40 号的提前结束不与它竞争时提高吞吐；若提前结束先于深度状态确认，68／69 守的一致性会先坏，表现是深度错误而非帧率下降**。诊断路径是 `GOW_GS_FINISH_ASINCRONO` 与 `GOW_GS_EARLY_FINISH` 二选一开关，加 `GOW_SYNC_DIAG`（第 2、5 章）——这正是"打开哪个开关、看哪一行日志"的二分法在 GS 线上的具体用法。74／75 运行态与加固、83 不变量属于"跑稳"层，它们不提高帧率，只让上面这些时序假设被断言钉住。

### 8.2 三套时间刻度：谁说了算

第 3 章已展开 `[diagnostics]` 的 `frame_pc = "0x1837B8"` 是 `vid::Flip`，用来数客机帧（guest frame），与宿主呈现率（host presentation rate）区分。本节补第三套，并给出三者的不可折算性。

| 刻度 | 由谁产生 | 关联补丁／变量 | 受什么影响 | 能否跨机器比 |
| --- | --- | --- | --- | --- |
| 客机帧 | `vid::Flip` 命中计数，`frame_pc = "0x1837B8"` | `GOW_PERF_FRAME_PC`、`GOW_PERF_DIAG`、29a–29f 会话帧计量 | 游戏逻辑、EE 与 VU1 的执行 | 能，前提是固定该 PC |
| 宿主呈现率 | 呈现层 | `GOW_WINDOW_HIDDEN`、`GOW_SCALER`、F11 fullscreen（见第 2 章） | 窗口是否可见、缩放、驱动呈现队列 | 不能 |
| GPU 帧计时 | 70 号 GPU 帧计时 | 70、`GOW_SCALER`、`GOW_ANISO`、`GOW_SHARPEN` | render target 尺寸、纹理过滤、锐化、GPU 负载 | 不能，需同档内部分辨率 |

三套刻度的算式各写一次：

```text
客机帧率 = vid::Flip 命中次数 ÷ 墙钟秒数
例：60 s 内命中 N 次 → N / 60（N 未给，仅列算式）
内部分辨率 1×→8×：像素量按线性倍数的平方增长，8× 档为 1× 档的 64 倍像素量
```

第二行是通识推算，不是仓库测值；基座只给范围 1×–8×，未给各档显存占用或帧时间，此处事实不足，需在 70 号补丁与 `GOW_SCALER` 的输出处补测。
为什么不能互相折算：`GOW_WINDOW_HIDDEN=1` 时宿主呈现率近乎为零，而 `optimize` 阶段恰恰要在隐藏静音窗口里跑满 240 秒录微码（第 5 章）；若拿宿主呈现率当分母，240 秒训练会被判成"没跑"。反过来，8× 内部分辨率下 GPU 帧计时变长，但游戏掉帧不减速，客机帧数不会因此变多——只可能变少。**44 号的 52.8 → 54.7 FPS 之所以能跨 4 组交替比较，是因为它写明了"全屏"这一呈现条件且落在客机帧口径上；换成宿主呈现率或 GPU 帧计时，1× 与 8× 的数字不可直接相减**（第 7 章已立，此处只补口径理由）。
70 号 GPU 帧计时的价值恰在"不混"：它让"入队侧已经优化完、但 GPU 侧仍是瓶颈"这类判断有独立证据，而不是靠客机帧率反推。29a–29f 里的会话帧计量与 DMA 提交计量（第 7 章）则把这两端之外的第三段——提交节奏——补上。三套刻度加一段提交计量，构成第 3 章说的"帧率到底谁说了算"的完整测量纪律。

### 8.3 纹理包、mod VFS 与上传路径的耦合

第 7 章已把 52 纹理包、71 mod VFS 钩子、84 mod 数据补丁串成一条链，本节只讲它们与 GS 上传路径的接口，不重复补丁层记账。
四个环境变量是这一层的全部对外面：

```text
GOW_TEXTURE_PACK
GOW_MOD_VFS_TABLE
GOW_MOD_PATCH_TABLE
GOW_MOD_VFS_LOG
```

52 对应 `GOW_TEXTURE_PACK`，由 `AccessibilityPage.qml` 管输入辅助、纹理包与视觉 mod（第 2、9 章）；71／84 对应两张表与一份日志；73 号启动器 mod 管理器配 `mods_model.cpp` 807 行（第 9 章）。呈现侧还有 `GOW_SCALER`、`GOW_ANISO`、`GOW_SHARPEN`，与内部分辨率 1×–8× 同属"已经进 GPU 之后"的参数，不参与替换判定。
接口位置由第 4 章定：`.disc_layout` 按扇区列出每个文件，`prepare.py` 产出 `data/<id>/discs/*`，运行期 ELF 所在目录即 CD 根。mod VFS 钩子挂在路径解析（path resolution）层，也就是说替换发生在"文件被读出来"这一步；而 46 GIF 零拷贝、61 shuffle 纹理复用动的是"数据被送进 GS"这一步。两段之间存在一个明确的先后：**替换必须在上传之前完成**。于是可以写一条推断并给出依据——**在零拷贝成立的前提下，上传路径持有的是指向数据的引用而非副本；若 VFS 表在上传之后才生效，环里已经持有了旧指针，替换不会体现在那一帧上，且 `afterBatch` 也不会重读**（推断：依据是 46 号"零拷贝"、61 号"纹理复用"、44 号保留 `afterBatch` 在每批后执行、以及 71 号"钩子"位于路径解析层；仓库未给 VFS 表的应用时点，需在 71／84 号补丁处补测）。
`GOW_MOD_VFS_LOG` 是这一层唯一被点名的可观测出口：出问题时打开它，看哪张表里缺了哪个路径，而不是去猜纹理有没有换。这与第 5 章"30 余个 `GOW_*` 是诊断面而非玩家设置"一致——诊断面的组织原则是二分，不是全开。
一条带条件的结论：**在 mod 只改数据、不改 `.text` 的前提下，52／71／84 不触发 `recomp` 重生成、不影响 `text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"` 的身份判定（第 3、6 章）；一旦某个 mod 替换了 `SCUS_973.99` 本身或 IRX 模块，它就越过身份边界，USA 流水线应当按异码 ELF 拒绝**。基座未写 71／84 是否校验 ELF 身份，需补测。另有一处与第 2、4 章的呼应：mod 让"目录可被外部改动"从隐患变成受支持功能，于是第 2 章那条"没有任何一层能证明跑起来的目录就是 prepare 产出的目录"的判断更需要一份摘要校验。

### 8.4 VU1：解释器 → AOT 微码 → x64 JIT

第 7 章按补丁层给 24 个 VU1 补丁记过账（02／09／10／13 块链接、17 后台编译、18 x64 JIT、20 emitter 预留、22 分析缓存、27 速度、33／34／35 提前结束与自环、37 隔离任务重放、43 更瘦的原生代码、45 惰性成对解码、50 小帧运行、51 快速模式、60 JIT 快速模式、63 热入口、76 链预热、78 累加器、79 VF 前递、81 辅助函数去重、82 时序不变量），本节讲三个阶段本身的边界，不逐条复述补丁。
基座 2.2 的原生替代表写得很克制：VU1 由**录制的 micro-memory 提前编译的微码**；**未录制的走解释器**。这一句已经把三个阶段里的两个钉住了。第三个（x64 JIT）来自 18 号与 2.9 的"System V 的 VU1 JIT 在 runtime 里已有 Linux 路径"。

| 阶段 | 输入 | 谁生成 | 运行期行为 | 回退条件 | 关联补丁 |
| --- | --- | --- | --- | --- | --- |
| 解释器 | 任意 VU1 微码块 | 无 | 逐条解释 | 默认兜底 | 02／09／10／13 块链接、27 速度 |
| AOT 微码 | `optimize` 录下的 micro-memory | `tools/vu1/generar_vu1.cpp`、`tools/vu1/vu1n_gen.py`，入口表 `vu1n_heads.txt` | 直接跑原生代码 | 未录制、或寄存器间接跳转找不到入口 | 43、45、50、51、33／34／35、37、78、79、81、82 |
| x64 JIT | 微码块 | 18 号 x64 JIT、20 emitter 预留、22 分析缓存 | 运行期发射宿主代码 | 平台路径不支持 | 17、18、20、22、60 |

三阶段的输入汇流在第 4 章那张表：运行时录制（`optimize`，240 秒脚本）、静态抽取（`vu1disc`／`vu1_from_disc.py`，已实现但覆盖不全）、人工补入口（`[runtime].vu1_native_heads`／`vu1n_heads.txt`）。三路产物都交给 `native` 阶段（16 号补丁只重建 VU1／IOP，第 5 章），不碰 EE 生成物。第 6 章已立：生成物身份只看 `.text`，所以这三条路线都不改变内容寻址的 key——它们改的是"同一份游戏的协处理器怎么执行"。
三个阶段的边界可以各下一个判断：
**解释器 → AOT。**​ 收益不是单条 VU 指令变快，而是跨过解释器边界（第 3 章已折算约 4,000 次／客机帧）。代价是覆盖率：录不到的块仍留在解释器里，`GOW_VU1_CAPTURE_MISSES=1` 就是把这个缺口显式记下来（第 5 章）。**在录制轨迹覆盖当前场景热路径的前提下，AOT 是净收益；一旦场景切换进入未录制块，边界开销立刻回到解释器量级**。
**AOT → x64 JIT。**​ 17 后台编译把发射移出运行路径，20 emitter 预留缓冲，22 分析缓存复用结果，45 惰性成对解码把解码摊到首次命中，60 JIT 快速模式与 51 快速模式给出热路径捷径。代价是引入并发与缓存失效条件：后台编译与主线程之间需要同步，惰性解码让首次命中变慢（**推断**：依据是"后台编译""惰性成对解码""分析缓存"三个补丁名；仓库未给同步原语与缓存键，需在对应补丁处补测）。18 号的 x64 JIT 还有平台条件——Linux 侧走 System V 路径，编译通过但 GPU 未验证（见 8.6）。
**算术与时序收口。**​ 78 累加器、79 VF（vector float）前递、81 辅助函数去重属"更瘦的原生代码"（43 号）一族；82 时序不变量与 23／55 号 IOP 补丁、`GOW_IOP_DRIFT`（第 5 章）同属"跑稳"。它们不推动阶段跃迁，只证明前面那些优化没把语义改坏。

### 8.5 热入口与链预热：船战为什么是试金石

第 3 章给过一个约数：缺 `vu1_native_heads` 时，这些块只能在解释器里跑，**5 秒船战里进出原生代码约 120 万次**。折算：

```text
1,200,000 ÷ 5 s            = 240,000 次／秒（约数）
5 s × 60 Hz                = 300 客机帧
1,200,000 ÷ 300 客机帧     = 4,000 次／客机帧（约数）
```

63 热入口与 76 链预热针对的正是这两个数字。热入口把反复进出的块标记出来；链预热把块间链接在冷启动阶段先建好，避免每次进入都重新解析目标（**推断**：依据是"热入口""链预热"的补丁名、02／09／10／13 的块链接族、以及 `vu1n_heads.txt` 专门解决寄存器间接跳转；仓库未给预热触发时机与热入口判据，需在 63／76 号补丁处补测）。
船战之所以是试金石，三条理由都可核查：其一，它是被基座点名给出边界次数的唯一场景（5 秒／约 120 万次）；其二，44 号的 52.8 → 54.7 FPS 测法用的存档路线、全屏、4 组交替也是战斗场景（第 7 章）；其三，欧洲与日本独立 Windows 构建的验证路线明确叫"初始船战"（第 3 章）。三处不约而同落在同一段，说明这段同时压到 VU1 边界、GS 入队侧与深度切换，是整条运行链上最密集的一段。
由此下一条带条件的判断：**在录制的微码块覆盖船战热路径、且 `vu1n_heads.txt` 补齐了寄存器间接跳转入口的前提下，63／76 能把 4,000 次／客机帧的边界开销压成编译期一次性成本；一旦某块只由运行期间接跳转进入且入口表未覆盖，它仍会回到解释器，此时再加热入口也无效，唯一兜底是补 `vu1_native_heads`**。这也解释了为什么第 3 章把"性能问题往往不是算术问题，而是边界问题"立成全书句式——78 累加器、79 VF 前递再快，也抵不掉一次进出边界。
`GOW_VU1_FAST`、`GOW_VU1N_JIT`、`GOW_VU1N_DIAG`、`GOW_VU1_CAPTURE_MISSES` 四个开关（第 2、5 章）是这条边界的诊断面：先开 `GOW_VU1_CAPTURE_MISSES` 看漏了哪些块，再开 `GOW_VU1N_DIAG` 看 JIT 路径，最后才动 `GOW_VU1_FAST` 或 `GOW_VU1N_JIT`。顺序反过来会把诊断面本身变成噪声源。

### 8.6 "编译通过 ≠ GPU 验证"：一条可核查的方法论

基座 2.9 的原话最值得整段钉住：渲染器与 System V 的 VU1 JIT 在 runtime 里已有 Linux 路径，但**编译通过不等于 GPU 验证通过**；Linux 的 PGO／自动录制、IOP 训练、便携依赖打包与二进制更新**仍未实现**，`package_linux.py` 只产出依赖宿主库的启动器加源码归档；Linux 手柄采集走 SDL2，玩法仍用 raylib。第 10 章会把"未实现／已编译但未验证／已实现但覆盖不全"三类措辞分开，本节只讲为什么这条区分不是文字游戏。
编译期能证明的与不能证明的，列成表：

| 编译期能证明 | 编译期不能证明 | 需要的验证信号 |
| --- | --- | --- |
| 符号解析、ABI、链接通过 | 驱动是否接受 render target 格式 | 70 GPU 帧计时 |
| 18 号 x64 JIT 的汇编发射被汇编器接受 | 1×–8× 各档内部分辨率下显存与带宽是否够 | `GOW_SCALER` + 客机帧 |
| C++ 模板实例化、线程原语存在 | SPSC 环在真实 GPU 背压下是否溢出 | 67 环溢出保护 + `GOW_SYNC_DIAG` |
| 生成物与 `text_sha1` 一致 | 异步提交与 FINISH 的时序、每 ZBP 深度一致性 | 77／68／69 + `GOW_GS_FINISH_ASINCRONO` |
| `verify` 阶段约 40 个测试无需 ISO 跑通 | 着色器在真实 GPU 上是否编译成功 | 全屏实际呈现 + `TOBIICHI_CAPTURA=<png>` |

第五行的截图钩子来自第 2、9 章：`TOBIICHI_CAPTURA=<png>` 与 `TOBIICHI_CAPTURA_PESTANA=<page>` 让 UI 测试能被脚本判定。把上表压缩成一句判断：**编译通过证明的是"代码形状合法"，GPU 验证证明的是"这段形状在真实驱动与负载下产生正确像素且不掉帧"；前者是后者的必要不充分条件，二者之间隔着驱动、显存、同步与时序四类变量**。
44 号的测法（第 7 章）是唯一一份现成的 GPU 验证范本：基线定义在 43 号之上，单变量只换 44，存档路线可复现，全屏这一呈现条件写明，4 组交替排除抖动，52.8 → 54.7 FPS 用客机帧口径，4 组全胜给出结论。把它移植到 Linux 格上，需要补齐的是同一套四要素：一个可复现路线、一个固定呈现条件、一组交替、一个写明单位的口径；再加 GPU 侧信号（70 号计时、`GOW_PERF_DIAG`、`GOW_MOD_VFS_LOG`）。`docs/research/` 里按日期归档的 25 篇文档中有 VU1 JIT 原型、渲染 worker、60fps 路线图、纹理替换、补丁 28／29 与 30–35 的集成评审（第 10 章），它们是证据而非契约——**过期的证据不删只归档，所以一份"当时跑通了"的研究文档不能当作当前 Linux 路径已验证的凭据**。
三类措辞在这条方法论里各自对应不同的动作：`vu1_from_disc.py` 是**已实现但覆盖不全**（第 4 章），动作是补覆盖率测法；Linux GPU 路径是**已编译但未验证**，动作是补上表右侧的信号；Linux 的 PGO、自动录制、IOP 训练、便携依赖打包与二进制更新是**未实现**，动作是实现，不是排查。把三者混写，会让维护者对着一个根本不存在的功能做二分，而 `ERROR: <消息>`（第 2 章）里根本没有那条路径。

### 8.7 三条对照轴的小结

**纵向**：本章覆盖"生成 → 构建 → 运行"里的运行格，以及运行格内部的入队侧与 GPU 侧。上游是第 3 章的 `text_sha1` 身份、第 4 章的 `discs/*` 与 `.disc_layout`、第 5 章的 `optimize`／`native` 录制产物、第 6 章的内容寻址生成物；下游是第 9 章启动器把 `GOW_TEXTURE_PACK`、`GOW_SCALER`、`GOW_ANISO`、`GOW_SHARPEN` 变成环境变量。整条链上，VU1 与 GS 都不改生成物身份，只改"怎么执行"。
**横向**：Windows 侧有 44 号字节环的 52.8 → 54.7 FPS 实测、有 `GOW_WINDOW_HIDDEN=1` 的 240 秒隐藏训练、有 `C:\gow-build` 短根与 PGO profile；Linux 侧 `bash build.sh` → `tools/pipeline/linux.py`（262 行）共享同一份档案、光盘准备、事务式重编译器与序数补丁链，`package_linux.py` 只产出依赖宿主库的启动器加源码归档，Windows 的构建根、便携工具、PGO profile 一律不复用（第 2、5 章）。所以 8.1 的十五个 GS 补丁与 8.4 的 24 个 VU1 补丁在 Linux 格上是"编译通过"，不是"测过"。区域格上，USA／欧洲／日本三套 `code` 共享同一条全局补丁链，`asia-97399` 凭三同复用 `code = "japan"`（第 3 章），差异锁在 `games/gow1/regions` 的条件性覆盖层里；"初始船战"作为欧洲与日本独立构建的验证路线，把 8.5 的场景选择从工程偏好变成了矩阵里的共同刻度。
**深度**：解释器兜底与 `verify` 停在"能跑"；68／69 深度 ZBP、82 时序不变量、83 不变量、67 环溢出保护、74／75 加固停在"跑稳"；08 号约 22% EE 线程时间（第 6、7 章）、44 号 1.9 FPS、63／76 热入口与链预热指向"跑快"。VU1 整体按第 1 章的判断停在"跑快但边界未闭合"，下一级门槛是 `vu1n_heads.txt` 覆盖全部寄存器间接跳转；GS 停在"跑稳"，下一级门槛是 4 MB 上限附近的背压与每 ZBP 深度在 8× 档下的实测。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会把 44 号那套测法固化成一份可由 `verify` 调用的最小 GPU 验收骨架：固定存档路线、固定全屏与 1× 档、固定 `frame_pc = "0x1837B8"` 客机帧口径，交替 4 组，同时采 70 号 GPU 帧计时与 67 号环溢出计数，输出一行"客机帧率 + GPU 帧时间 + 溢出次数"的机器可读结果；Linux 路径先在 1× 档跑通这同一份骨架，再逐档开到 8×。理由是 8.6 已写明"编译通过"与"GPU 验证"之间缺的正是可复现路线与固定口径，而 44 号注释里四要素齐全，是现成模板；把骨架放进 `verify` 还能复用它"不需要 ISO 也能跑"的解耦性质（第 2 章）——虽然骨架本身需要一份可复现存档，这恰恰是要补的那部分输入。代价：`verify` 从此不再是纯 CPU 回归，CI 需要 GPU 与驱动，且驱动版本会变成新的变量；4 组交替 × 8 档分辨率会让一次验收的时间成本上升一到两个数量级。可反驳条件：若 `docs/research/` 里"渲染 worker"或"60fps 路线图"已经给出等价的验收脚本，正确动作是把那份脚本提升为 `docs/` 契约并让 `verify` 调用它，而不是再写一份骨架——否则会与第 10 章"docs 是契约、research 是证据"的分层冲突，也会多出一份与 44 号注释互不相认的真相源。

本章结论：GS 侧十五个补丁按"采集搬运 → 排队 → 成批 → 深度 → 提交收口 → 测量"串成一条流水线，44 号解决入队侧每客机帧约 4,000 包的放大，68／69／77 守的是同一同步点上的深度与提交一致性；客机帧、宿主呈现率、GPU 帧计时三套刻度互不可折算，44 号的 52.8 → 54.7 FPS 之所以可比正因为写明了全屏与客机帧口径；纹理包与 mod VFS 必须赶在零拷贝上传之前生效；VU1 三阶段的收益全在边界而非算术，63／76 热入口与链预热把船战约 4,000 次／客机帧的进出压成编译期成本，前提是 `vu1n_heads.txt` 补齐间接跳转；"编译通过 ≠ GPU 验证"要求 Linux 格上补齐可复现路线、固定呈现条件、交替组数与客机帧口径。条件是上述判断都建立在 1×–8× 各档未被实测、且 `afterBatch` 语义未被 77 号改变这两个未闭合项上。遗留疑问六处：ZBP 切换的具体实现、VFS 表的应用时点与零拷贝指针生命周期、17／22 的同步原语与缓存键、63／76 的热入口判据与预热触发时机、`GOW_GS_STAGE_SPIN_US` 的单位与 8× 档显存占用、以及 77 与 40 是否竞争同一同步点，均需在对应补丁与 `GOW_SYNC_DIAG` 日志处补测。

## 第 9 章 启动器与安装器
本章回答五个问题：同一个产品为什么配两套前端技术栈、Qt 6.8.3 三模块与 `tools/pipeline/compat/` 适配各解决什么；`Main.qml` 的页面编号、`Tema.qml` 的配色与 `GOW_*` 环境变量之间怎样只留一套配置；`LoadingScreen.qml` 按文本协议算出的进度与剩余时间到底以什么为分母；存档页、无障碍页与 mod 管理器怎样把区域构建和诊断面收进 UI；以及 1352 行 Win32 安装器的 LZMS 自解包、按用户安装、`/S` 静默契约与 `/purge` 的安全条件各自堵住了哪一类事故。

### 9.1 两个前端，两套技术栈

启动器是 Qt 6，源码钉 6.8.3（qtbase、qtshadertools、qtdeclarative，按 SHA-256 校验，一次构建进 `data/_tools`），并在构建 SDK 前应用 `tools/pipeline/compat/` 的源码兼容适配，现有一个 `qt-sequence-sort.h`。安装器 `installer/setup.cpp` 1352 行，Win32 + GDI+，**不用 Qt**，单文件自包含（self-contained）exe。

| 维度 | 启动器 | 安装器 |
| --- | --- | --- |
| 技术栈 | Qt 6.8.3，qtbase／qtshadertools／qtdeclarative | Win32 + GDI+ |
| 依赖面 | 需 Qt 运行库，SDK 一次构建进 `data/_tools` | 系统自带，无运行库机器上双击就跑 |
| 体积约束 | 不作单文件要求 | 小到可以塞进 GitHub Release |
| 构建入口 | `qt` 阶段 + `launcher` 阶段（第 5 章） | `package` → `installer` 阶段 |
| 源码校验 | 三模块按 SHA-256 校验 | 基座未给，需补测 |
| 源码兼容适配 | `compat/qt-sequence-sort.h` | 不适用 |
| 行数 | 见 9.1.1 | 1352 行 |

"为什么不用 Qt"的答案有两条，都是产品约束而非偏好：安装器必须能在没有运行库的机器上双击就跑，且体积要小到可以塞进 GitHub Release。把这两条与启动器并排看，分界就清楚了——**启动器是装好之后才运行的东西，可以依赖一份已随包交付的 Qt；安装器是第一个被运行的 exe，它脚下除了 Windows 什么都没有**。这正好是横向矩阵里最尖锐的一格：Linux 侧 `package_linux.py` 只产出依赖宿主库的启动器加源码归档，便携依赖打包**未实现**（第 10 章），也就是说安装器"自包含"这条性质目前只在 Windows 格成立。
`qt-sequence-sort.h` 的存在说明钉版本还不够：Qt 6.8.3 的源码与钉死的 llvm-mingw clang（第 5 章：`-Toolchain msvc` 只是迁移别名，组件一律用钉死的 llvm-mingw）之间仍有编译期冲突，需要一份本地适配头在构建 SDK 之前打进去。适配放在 `tools/pipeline/compat/` 而不是直接改 Qt 源码，与第 1 章的 90 个补丁是同一条纪律——**改别人的代码就留一份可重放、可丢弃的增量**。该头具体解决哪一处的序列排序冲突，基座未给，需在 `compat/qt-sequence-sort.h` 处补测。

### 9.1.1 六份 C++ 的分工与行数

| 文件 | 行数 | 侧 | 命名 |
| --- | --- | --- | --- |
| `lanzador.cpp` | 914 | 播放侧 | 西班牙语 |
| `installer_backend.cpp` | 547 | 安装侧 | 英语 |
| `mods_model.cpp` | 807 | mod | — |
| `session_diagnostics.cpp` | 463 | 诊断 | — |
| `main.cpp` | 134 | 入口 | — |
| `mando.cpp` | 147 | 手柄 | 西班牙语 |
| 合计 | **3012**​ |  |  |

914 + 547 + 807 + 463 + 134 + 147 = 3012 行。命名分界值得单独一句：`lanzador.cpp`（播放侧）与 `mando.cpp`（手柄）用西班牙语，`installer_backend.cpp`（安装侧）用英语。这与第 3 章 `[optimize]` 脚本里的 `cuadrado`、`triangulo`、`circulo` 同源——runtime 从南美社区项目长出来，命名不是英语（第 3 章已立）。读代码的人若把 `lanzador` 当成拼写错误去"统一"成英文，会同时碰坏 UI 侧命名与 `GOW_PAD_GUION` 那串按键脚本的一致性；两处不是同一个文件，却是同一条血统。QML 侧的 `pagina`、`cargaDica1..N`、`Tema.qml` 的 `oro*` 也属这一族。
`session_diagnostics.cpp` 463 行是诊断面在 UI 侧的落点：`GOW_PERF_DIAG`、`GOW_SYNC_DIAG`、`GOW_MOD_VFS_LOG`、`GOW_IOP_DRIFT` 这些开关（第 2、5 章）产生的是日志，需要有人把它们收进一次会话里供 `reporting-bugs.md` 使用（**推断**：依据是文件名与 `docs/reporting-bugs.md` 并列出现；仓库未给该文件读哪些变量、输出到哪，需在 `session_diagnostics.cpp` 处补测）。

### 9.2 侧边栏、页面编号与唯一一套配置

`Main.qml` 是侧边栏（sidebar）加页面，`pagina` 编号如下：

| `pagina` | 页面 | 主要产物／对应开关 |
| --- | --- | --- |
| 0 | 主页 | 启动、版本选择器（见 9.4） |
| 1 | 安装 | `instalar.cmd -Iso "D:\path\God of War.iso"` 一类流程（见 9.6） |
| 2–6 | 设置（5 页） | `GOW_SCALER`、`GOW_ANISO`、`GOW_SHARPEN`、`GOW_AUDIO_DEVICE`、`GOW_TEXTURE_PACK` 等（第 2、8 章） |
| 7 | 存档 | `GOW_SAVES_DIR`、`GOW_MC0`；26 号存档页截图去重 |
| 8 | 无障碍 | `AccessibilityPage.qml` |

这里必须做一次验算：任务书成书结构写"8 个页面"，而基座 2.8 给出的是 `pagina` 0 主页、1 安装、2–6 设置、7 存档、8 无障碍。0–8 共 **9**​ 个编号，其中 2–6 是 5 个设置页，1 + 1 + 5 + 1 + 1 = 9。**按事实基座逐项计数应为 9 个页面，本文一律以 0–8 编号为准**；把"8 个页面"当成事实会漏掉一整页设置，也会让 `TOBIICHI_CAPTURA_PESTANA=<page>` 的取值集合少一项。该环境变量的 `page` 是否直接复用 `pagina` 编号，基座未写明，需在 `loading-progress.py` 与 QML 侧补测。
配色集中在 `Tema.qml`，`oro*` 系列承载绯红强调色。集中而不是散在各页，是 UI 层唯一一处与"唯一事实源"（第 1 章）同构的决策：改主题只动一处。
真正要紧的是配置的坍缩：**页面上每个设置最终都变成上节那串 `GOW_*` 环境变量——UI 与引擎之间没有第二套配置系统，这是刻意的**（第 2 章已立）。若启动器自己维护一份配置、引擎再读一份，两份必然漂移；现在启动器的职责被压成"生成环境变量并拉起进程"，引擎只认环境变量，档案只由 `tools/pipeline/profile.py` 读成 Python 字典或 JSON 供 PowerShell 与启动器共用（第 3 章）。三层的读者相同、写法不同，事实源只有一个。
这条设计的代价落在 9.3 的文本协议上：UI 与引擎之间没有第二套配置，UI 与流水线之间也没有第二套通信——两边都靠文本。`@@status <text>` 里的文案一旦被 QML 按子串匹配，改一个词就静默失效，而没有任何类型系统会报错（第 5 章已立"文案即接口"，此处只引用）。

### 9.3 `LoadingScreen.qml`：进度模型的分母从哪来

`LoadingScreen.qml` 在长任务时覆盖全屏，按流水线协议显示总进度、剩余时间与 `cargaDica1..N` 提示，还能读玩家自己放进 `data/<id>/loading` 的图片。协议三行（第 5 章已展开四出口，本节只讲 QML 侧如何消费）：

```text
=== <step> ===
@@progress <done> <all>
@@status <text>
```

`Step`（`modules/common` 62 行）输出的 `=== <step> ===` 是阶段边界，也是进度条的分母来源；`@@progress <done> <all>` 才是机器读的分子／分母；`@@status` 是人类可读的当前动作。`build.ps1` 顶部 `trap` 把异常打印成 `ERROR: <消息>` 并以退出码 1 结束，所以启动器只需要抓这一行就能区分"失败"与"仍在跑"（第 2、5 章）。四个出口在 QML 侧分别变成：阶段名、`done/all`、当前动作文案、以及"覆盖层该不该撤掉换错误态"。
分母若取 18 个阶段（第 5 章标注为**推断**，`all` 的加权方式需在 `modules/build-progress` 27 行处补测），均速外推的剩余时间是 `T × (18 − done) / done`。这个模型对 `optimize` 明显不准：它单阶段就占 240 秒（第 3、5 章），而 `tools` 只是一次下载，两者在 `all = 18` 里权重相同。第 5 章已从流水线侧给过重做判断，本节补 UI 侧的观察：**剩余时间误导不会让构建失败，只会让玩家在 240 秒的录制阶段反复以为卡死，而 `cargaDica1..N` 与 `data/<id>/loading` 的自定义图片正是为这个空窗准备的**——它不是装饰，是进度模型不可靠时的人因补偿。`cargaDica1..N` 的 N 与文案来源、`data/<id>/loading` 支持的图片格式与命名约束，基座均未给，需在 QML 与 `loading-progress.py` 处补测。
`loading-progress.py` 属于 `tools/test/` 下约 40 个测试里带 UI 性质的那一组（第 2、10 章）。它验证的正是"文本协议 → 进度条"这条纯文本链路，也因此只能靠 UI 测试兜底：协议是文本而不是 IPC，让终端与启动器共用同一条路径，代价是解析脆弱。

### 9.4 存档页、无障碍页、mod 管理器与版本选择器

**存档页（`pagina` 7）。**​ 26 号补丁"存档页截图去重"说明这一页会截图，且同一内容不重复出图。对应 `GOW_SAVES_DIR`、`GOW_MC0`；README 另写 saves go to `game/Mcd001.ps2`，是 PCSX2 兼容卡映像，可把 PCSX2 记忆卡复制到那里（第 2 章）。同目录 `mc0/`、`prepare.py` 的共享 `mc0` 与这两个变量之间的覆盖优先级，第 2 章已标注需在 `saves.md` 处核实，本章不重复展开。截图自动化钩子 `TOBIICHI_CAPTURA=<png>` 与 `TOBIICHI_CAPTURA_PESTANA=<page>` 让这一页能被脚本判定，而不是靠人眼（第 2、8 章）。
**无障碍页（`pagina` 8）。**​ `AccessibilityPage.qml` 管输入辅助、纹理包与视觉 mod，对应补丁链是 53 QTE 长按、56 键盘摇杆手势、57／58 和弦保持、52 纹理包（第 7 章），环境变量是：

```text
GOW_QTE_HOLD  GOW_QTE_HOLD_HZ
GOW_TEXTURE_PACK
GOW_MOD_VFS_TABLE  GOW_MOD_PATCH_TABLE  GOW_MOD_VFS_LOG
```

`qte_hold_test.cpp`、`qte_input_test.cpp` 是 C++ 侧单测（第 10 章）。默认键鼠布局可在启动器重映射，热键 F2 cheat menu、F11 fullscreen、F1 developer panel，DualShock 4／DualSense／Xbox 等手柄开箱即用（Windows 上有振动）——这些都从这一页或 `mando.cpp` 147 行走。**推断**：依据是 `mando.cpp` 的西班牙语命名（手柄侧）、`AccessibilityPage.qml` 管输入辅助、以及 README 提到的重映射能力；三者的具体调用链需在 `mando.cpp` 处补测。
**mod 管理器。**​ 73 号补丁配套 `mods_model.cpp` 807 行，是六个 C++ 文件里第二大的。它与 52／71／84 号补丁构成完整链路（第 7、8 章）：纹理包给入口，mod VFS 钩子挂到路径解析层，`GOW_MOD_PATCH_TABLE` 承接数据补丁，`GOW_MOD_VFS_LOG` 是唯一可观测出口。管理器的价值不在好看，而在把"哪张表里缺了哪个路径"从日志问题变成列表问题。
**版本选择器。**​ `tools/pipeline/register_region.py` 把已验证的构建登记进 `data/<game>/regional-builds.json`，启动器校验归属、CMake 源目录与 ELF／runner 哈希后并入版本选择器（第 3 章）。欧洲与日本各有经过"初始船战"验证的独立 Windows 构建（第 8 章），`asia-97399` 的 `code = "japan"` 复用日版构建而光盘数据仍归自己（第 3 章）。启动器接受 runner 前还会核对 CMakeCache 的源目录，防止新副本误用旧副本的构建，Windows 读 `data/build-root.txt`（第 5 章）。于是版本选择器不是一张静态菜单，而是"归属校验通过才出现"的动态列表——这与 9.5 的 `/purge` 共用同一条判据，是本章纵向轴上最值得记的一处复用。

### 9.5 1352 行 Win32 安装器：自解包、按用户安装与卸载

`installer/setup.cpp` 1352 行，Win32 + GDI+，不用 Qt，单文件自包含 exe。四组真实命令：

```text
setup.exe --pack <dir> <out>
setup.exe /S [/D=<dir>]
uninstall.exe /uninstall-from <dir> /S [/purge]
GOW_SETUP_CAPTURE=<png>
```

**打包与自解包。**​ `--pack <dir> <out>` 把 LZMS 块追加进自身并写 footer。由此可以写出单 exe 的三段结构：

```text
[ 可执行代码段 ][ 追加的 LZMS 块 ][ footer ]
```

这是从"追加进自身并写 footer"直接推出的结构，属**推断**：footer 至少要让解包端定位块的起点与长度，否则同一个 exe 无法既当程序又当容器；基座未给 footer 的字段布局、字节序与校验位，需在 `installer/setup.cpp` 处补测。LZMS 是 Windows 映像常用的压缩格式（通识），选它是为了 1352 行自己能解、不引第三方运行库。这一条正好兑现 9.1 的"无运行库机器上双击就跑"。
**按用户安装（per-user install）。**​ 装的是 HKCU Apps 条目、快捷方式、`uninstall.exe` 与 `uninstall.lst`。HKCU 意味着不需要管理员权限，卸载清单随用户走；`uninstall.lst` 记录装了什么，是 `/purge` 与常规卸载共用的依据。基座未给 `uninstall.lst` 的记录粒度（文件列表／尺寸／摘要），需在 `setup.cpp` 处补测。
**静默契约（silent install）。**​ `/S [/D=<dir>]` 支撑无点击测试；`/D=<dir>` 指定目录。卸载侧 `uninstall.exe /uninstall-from <dir> /S [/purge]` 同样支持 `/S`。`GOW_SETUP_CAPTURE=<png>` 出截图，与启动器侧 `TOBIICHI_CAPTURA=<png>` 是两套独立的截图钩子——一个给 Win32 安装器，一个给 Qt 启动器，因为两者不共享任何代码（9.1）。截图时序（何时抓、抓哪一帧）基座未给，需在 `verify_setup.py` 处补测。
**`/purge` 的安全条件。**​ 这是全章最该精读的一处：**`/purge` 只在副本的 CMakeCache 确实指向 `<dir>` 时才删其构建目录**。它防的是一类具体事故：一台机器上可能并存多份 checkout，各自有 `C:\gow-build-<hash>` 一类的构建根，登记在 `data/build-root.txt`（第 5 章）；若卸载器只按路径字符串去删，A 副本的卸载可能把 B 副本的构建目录抹掉。核对 CMakeCache 的源目录，是把"登记说了什么"换成"产物自己说了什么"——与启动器接受 runner 前的归属校验、版本选择器的 ELF／runner 哈希校验同源（第 3、5 章）。由此下一条带条件的判断：**在 CMakeCache 未被手工替换、且 `<dir>` 与登记文件一致的前提下，`/purge` 的删除是归属安全的；一旦缓存被覆盖或目录被外部改名，字符串比对与归属校验会给出不一致的答案，此时正确行为是拒绝删除而不是挑一个信**。基座未给拒绝时的提示文案，需在 `setup.cpp` 处补测。
`package` 阶段明确排除 runtime（第 1 章），所以安装器打包的是编排层产物与启动器，不是那 196 个 `.cpp`／195 个 `.h`；这与 README 的"仓库不含游戏文件，也不含由它们生成的代码，安装器在用户机器上从用户自己的光盘映像构建"合成同一条交付边界。

### 9.6 静默契约为什么等于可测试性

`/S` 不是给懒人用的开关，它把 UI 变成可被脚本判定的东西。`tools/test/` 下与本章直接相关的有 `verify_setup.py`、`disc-import-ui.py`、`regional-play-ui.py`、`launcher-languages.py`、`loading-progress.py`（第 2 章）。五个名字对应五条 UI 链路，逐条落到本章的某个页面或命令：

| 测试 | 覆盖的本层 | 依赖的钩子 |
| --- | --- | --- |
| `verify_setup.py` | `--pack`／`/S`／卸载 | `GOW_SETUP_CAPTURE=<png>` |
| `disc-import-ui.py` | `pagina` 1 安装页、光盘导入 | `instalar.cmd -Iso ...`（第 2 章） |
| `regional-play-ui.py` | 版本选择器、区域构建 | `regional-builds.json` 校验（第 3 章） |
| `launcher-languages.py` | 语言目录与 `languages.json` | `identify.py` 的 `language` 字段（第 4 章） |
| `loading-progress.py` | `LoadingScreen.qml` | `@@progress`／`cargaDica1..N` |

`instalar.cmd` 在 README 里的两个开关是 `-SinOptimizar`（跳过优化步骤）与 `-Optimizar`（之后可补跑），对应第 5 章的 `optimize`／`native` 闭环。安装页把它们变成可点选项，而无点击测试靠的仍是 `/S`——同一份流程两种驱动方式，与第 5 章"终端跑一遍和启动器跑一遍共用同一条路径"是同一条纪律在产品层的延伸。
`verify` 阶段不需要 ISO 也能跑（第 2 章），把回归从"要有光盘"里解耦；上表五个 UI 测试却都依赖真实安装或真实目录状态，属于第 10 章"哪些环节只能靠 UI 测试兜底"的那一半。两者不矛盾：前者解耦的是流水线回归，后者守住的是"人点下去之后到底发生了什么"。

### 9.7 三条对照轴的小结与一处重做判断

**纵向**：安装器在"档案 → 光盘 → 生成 → 构建 → 运行"之前，启动器在"运行"那一格的入口。`package` 明确排除 runtime → `installer` 用 `--pack` 把编排层产物打成单 exe → `/S` 在用户机器上触发 `instalar.cmd` 那条 18 阶段链 → 构建登记进 `data/build-root.txt` → 启动器按 CMakeCache 归属校验接受 runner → 页面设置坍缩成 `GOW_*` 环境变量 → `LoadingScreen.qml` 按文本协议显示进度 → 卸载器按同一份 CMakeCache 判据决定 `/purge`。一条链上两次用到归属校验，两次都读产物自述而非登记文本。
**横向**：Windows 格有 Qt 6.8.3 三模块 + `compat/qt-sequence-sort.h`、有 1352 行自包含 exe 的 LZMS 自解包与 `/S`、有 `data/build-root.txt`；Linux 格 `bash build.sh` → `tools/pipeline/linux.py`（262 行）共享同一份档案、光盘准备、事务式重编译器与序数补丁链，启动器读 `data/build-root-linux.txt` 并按**大小写敏感**的 CMake 源目录归属校验，手柄采集走 SDL2、玩法仍用 raylib，`package_linux.py` 只产出依赖宿主库的启动器加源码归档。措辞必须分开：Linux 的 PGO／自动录制、IOP 训练、便携依赖打包与二进制更新是**未实现**；Linux 的 GPU 路径是**已编译但未验证**（第 8 章）；`vu1disc` 是**已实现但覆盖不全**（第 4 章）。把"未实现"写成安装器在 Linux 上有 bug，会引出根本不存在的排查方向——那一格根本没有自包含 exe。
**深度**：安装器与启动器的基本流程停在"能跑"；`/purge` 的 CMakeCache 条件、版本选择器的 ELF／runner 哈希校验、`session_diagnostics.cpp` 停在"跑对"；`LoadingScreen.qml` 的进度模型是"跑稳"的产品化外衣；44 号那类性能优化（52.8 → 54.7 FPS，第 7 章）不经过这一层，UI 只负责把它们变成 `GOW_*` 开关。下一级门槛是三处可判定性：`pagina` 2–6 的开关映射、footer 的自校验、`cargaDica` 与自定义图片的可测性。

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会让 `--pack` 在 footer 里除了块定位信息，再附一份被打包目录的清单摘要（文件数 + 内容 sha256），安装时展开 LZMS 块之后先核这份摘要再落盘。理由是 `package` 明确排除 runtime、`uninstall.lst` 只按基座所述"记录装了什么"，而单 exe 自解包的尾部一旦被截断、被追加了别的东西、或打包目录在 `package` 与 `--pack` 之间被改过，现在没有任何一层能证明"解出来的就是 pack 进去的那份"；安装器又是整条链上唯一一个不带 Qt、不带日志诊断面、`/S` 静默执行的部件，错误要到启动器报 CMakeCache 归属失败时才会浮上来。代价：footer 变大，pack 端多一次全量哈希，静默安装启动多一次校验，1352 行里要多出一段摘要计算；在 GitHub Release 的体积约束下每一个字节都算数。可反驳条件：若 `uninstall.lst` 已经写入逐文件 sha256 且安装时校验过，正确动作是把那份清单复用为解压后的验收依据，而不是在 footer 里再存一份——否则又多一份与 1.4 立下的"唯一事实源"相冲突的真相源，且两份摘要不一致时还得决定信谁。

本章结论：启动器用 Qt 6.8.3（qtbase、qtshadertools、qtdeclarative，SHA-256 校验，构建 SDK 前应用 `compat/qt-sequence-sort.h`）换得 3012 行 C++ 与 0–8 共 9 个编号页的 UI 能力，安装器用 1352 行 Win32 + GDI+ 换得无运行库机器上的单文件自解包，两者分界由"谁是第一个被运行的 exe"决定；`LoadingScreen.qml` 以 `=== <step> ===` 为分母来源、`@@progress` 为分子，剩余时间因 240 秒的 `optimize` 而天然不匀，`cargaDica1..N` 与 `data/<id>/loading` 是人因补偿；`--pack <dir> <out>` 把 LZMS 块追加进自身并写 footer，`/S [/D=<dir>]` 支撑无点击测试，`/purge` 只在 CMakeCache 确实指向 `<dir>` 时才删构建目录，与启动器归属校验同源。条件是这些判断都建立在 CMakeCache 未被外部替换、且 footer 结构如基座所述之上。遗留疑问七处：`pagina` 2–6 五页各自的 `GOW_*` 映射、`TOBIICHI_CAPTURA_PESTANA` 的取值集、`cargaDica1..N` 的 N 与 `data/<id>/loading` 的格式约束、LZMS footer 的字段布局与 `uninstall.lst` 的记录粒度、`compat/qt-sequence-sort.h` 具体适配的源码冲突、`GOW_SETUP_CAPTURE` 的截图时序、以及 `all` 的分母来源与阶段加权，均需在对应 QML、`setup.cpp` 与 `modules/build-progress` 处补测。

## 第 10 章 可维护性、局限与路线
本章回答五个问题：`tools/test/` 下约 40 个测试里哪些能脱离光盘与 GPU 在 CI 上跑、哪些只能靠 UI 测试兜底；`docs/` 与 `docs/research/` 为什么必须分成契约与证据两层；Linux 的"未实现／已编译但未验证／已实现但覆盖不全"三类措辞各自对应什么动作、混写会误导谁；若要支持第二款游戏，`docs/adding-a-game.md` 能参数化到哪一层、哪一层必然要重写；最后把前九章的判断收成给维护者的十条硬规则。

### 10.1 测试金字塔：哪一层能脱离光盘

基座给出的测试规模是"约 40 个测试脚本与 C++ 单测"，其中被点名 19 个。逐项数一次：

| 层 | 被点名的测试 | 需要 ISO | 需要 GPU／真实窗口 | 守的深度级 |
| --- | --- | --- | --- | --- |
| 流水线与生成 | `pipeline_tests.py`、`recompile-smoke.py`、`patch-stack-tests.ps1`、`build-progress-tests.ps1`、`linux_pipeline_tests.py` | 否 | 否 | 跑对 |
| 语义等价与回归 | `guest_codegen_tests.cpp`、`guest_memory_tests.cpp`、`guest_calls.cpp`、`dma_worker_tests.cpp`、`vu1-equivalence.py`、`sound_regression.cpp`、`qte_hold_test.cpp`、`qte_input_test.cpp` | 否 | 否 | 跑对 |
| 性能对比 | `perf-compare.ps1` | 否（**推断**） | 是（**推断**） | 跑快 |
| UI 兜底 | `disc-import-ui.py`、`regional-play-ui.py`、`launcher-languages.py`、`loading-progress.py`、`verify_setup.py` | 部分是 | 是 | 跑稳 |
| 合成数据 | `vu1_from_disc_test.py`（第 4 章） | 否 | 否 | 跑对 |

5 + 8 + 1 + 5 = 19，另有 1 个合成测试；19 + 1 = 20，与"约 40 个"相差约 20 个未被基座点名，需在 `tools/test/` 列目录处补测。`perf-compare.ps1` 的两列标为推断，依据是它要比较帧率而第 3 章把帧率口径固定在 `frame_pc = "0x1837B8"` 的客机帧上；仓库未写它是否能在无显示环境跑。
`verify` 阶段不需要 ISO 也能跑，这是它存在的意义：把"回归"从"要有光盘"里解耦（第 2 章）。把这条与上表并起来看，可 CI 化的边界很清楚——**纯逻辑层、生成层、协议层能脱离光盘，但"人点下去之后到底发生了什么"不能**。五个 UI 测试各对应第 9 章的一条链路：`verify_setup.py` 对 `--pack`／`/S`／卸载，`disc-import-ui.py` 对 `pagina` 1 安装页，`regional-play-ui.py` 对版本选择器，`launcher-languages.py` 对 `languages.json` 与 `identify.py` 的 `language` 字段，`loading-progress.py` 对 `LoadingScreen.qml` 的 `@@progress`。
截图自动化是这个金字塔的判定层，三套钩子互不共享代码：

```text
GOW_SETUP_CAPTURE=<png>
TOBIICHI_CAPTURA=<png>
TOBIICHI_CAPTURA_PESTANA=<page>
```

第一套给 1352 行 Win32 安装器，后两套给 Qt 启动器（第 9 章）。它们存在的理由不是产品功能，而是**文本协议与 `/S` 静默契约都不会产出结构化断言**：`@@status <text>` 是文案即接口（第 5 章），`/S` 不弹窗（第 9 章），于是只能把屏幕像素当成返回值。代价是截图测试对分辨率、主题（`Tema.qml` 的 `oro*` 系列）与驱动敏感，同一份断言换一台机器可能就红。
深度轴上，这四层各守一级：`verify` 与语义单测守"跑对"，29a–29f 诊断族（调用诊断、codegen MMIO 测试、会话帧计量、原生内存回归、scratchpad 链完成、DMA 提交计量，第 7 章）与 `perf-compare.ps1` 把 08 号约 22% EE 线程时间、44 号 52.8 → 54.7 FPS 钉成可复现证据而守"跑快"，UI 测试守"跑稳"。下一级门槛是补一份覆盖率：第 3 章给过测试矩阵算式 `code 数 × 路线数 × 语言目录数`，其中语言目录总数与用例数基座未给，需在 `data/<id>/discs/*` 与 `regional-play-ui.py` 处补测。

### 10.2 `docs/` 是契约，`docs/research/` 是证据

`docs/` 下九篇是契约层，逐篇对应本书的一条链路：

| 文档 | 契约对象 | 本书位置 |
| --- | --- | --- |
| `architecture.md` | 编排层边界与分层 | 第 1、2 章 |
| `disc-import.md` | 识别 JSON 与导入流程 | 第 4 章 |
| `linux.md` | Linux 平台矩阵 | 第 2、5、10 章 |
| `saves.md` | 记忆卡覆盖优先级 | 第 2、9 章 |
| `translations.md` | 翻译语言判据与目录 | 第 3、4 章 |
| `adding-a-game.md` | 新增游戏的边界 | 10.4 节 |
| `input-accessibility.md` | 输入辅助与 QTE | 第 7、9 章 |
| `reporting-bugs.md` | 诊断面与会话日志 | 第 2、9 章 |
| `tested-hardware.md` | 已验证硬件范围 | 第 8 章 |

`docs/research/` 有 25 篇按日期归档的研究与交接文档，基座点名的有：VU1 JIT 原型、纹理替换、区域移植、渲染 worker、60fps 路线图、补丁 28／29 与 30–35 的集成评审。文档分层是刻意的：**`docs/` 是契约，`docs/research/` 是证据，过期的证据不删，只归档**。
这条规则的方法论价值在第 8 章已经显形：渲染器与 System V 的 VU1 JIT 在 runtime 里已有 Linux 路径，但编译通过不等于 GPU 验证通过。一份写着"当时跑通了"的研究文档，不能当作当前 Linux 路径已验证的凭据——驱动、显存、同步与时序四类变量都会变。同理，第 7 章 44 号补丁的测法（在 43 号之上、存档路线、全屏、4 组交替、52.8 → 54.7 FPS、4 组全胜）是写在补丁头注释里的证据，而 29a–29f 与 `verify` 才是契约化的验收。由此下一条判断：**证据可以过期，契约不能；把 `docs/research/` 的某篇提升为 `docs/` 契约，前提是它已被自动化验收复现，而不是它写得足够详细**。`reporting-bugs.md` 与 `session_diagnostics.cpp` 463 行（第 9 章）是这一层的用户侧出口：诊断面产生日志，契约规定该交什么。
`docs/research/` 是否建立"补丁号 → 归档文档 → 验证状态"的索引，基座未给，此处事实不足，需在 `docs/research/` 处补测；第 7 章已就同一缺口给过重做判断，本节不重复。

### 10.3 已知局限：三类措辞加一类设计取舍

措辞纪律不是文字游戏，它决定维护者接下来做什么动作。四类必须分开写：

| 类别 | 具体项 | 正确动作 | 误写成的措辞 | 判定方法 |
| --- | --- | --- | --- | --- |
| 未实现 | Linux 的 PGO、自动录制、IOP 训练、便携依赖打包、二进制更新 | 实现 | "Linux 有 bug" | Linux 侧 `package_linux.py` 只产出依赖宿主库的启动器加源码归档；Windows 的构建根、便携工具、PGO profile 一律不复用（第 5 章） |
| 已编译但未验证 | Linux 的 GPU 路径（渲染器与 System V 的 VU1 JIT 在 runtime 里已有 Linux 路径） | 补可复现路线 + 固定呈现条件 + 交替组数 + 客机帧口径（第 8 章） | "Linux 已支持" | 对照 44 号四要素；`GOW_PERF_FRAME_PC` 与 70 号 GPU 帧计时是否同时有输出 |
| 已实现但覆盖不全 | `vu1disc`／`vu1_from_disc.py`，配 `vu1_from_disc_test.py` 合成测试 | 补覆盖率测法（R 录制块数、D 抽取块数、可编译比例，第 4 章） | "已验证"／"未实现" | 静态抽取只能覆盖光盘里以完整 VIF MPG 载荷存在的微码 |
| 设计取舍（非缺陷） | USA 流水线拒绝异码 ELF；无运行期语言切换；每语言一个光盘目录 | 接受代价 | "待修复" | 见下方代价核算 |

第三类的措辞最容易被两头误写：它既不是"没做"，也不是"做完了"。第 4 章已写明它属实验性旁路，覆盖不全的原因之一是运行时才由 EE 代码动态构造的微码静态扫描抓不到，之二是寄存器间接跳转仍需 `vu1n_heads.txt` 补。
第四类要单独算代价，因为它常被当成"以后修一下就好"。USA 流水线至今拒绝不同代码的 ELF，欧洲与日本各有经过"初始船战"验证的独立 Windows 构建，`games/gow1/regions` 存条件性 runtime 覆盖层、基线源码哈希、函数区间与重编译入口提示，这些覆盖层绝不能应用到 USA runtime、也不能进全局序数补丁链（第 3 章）。每新增一个 `code`，至少增加：一处构建根（`C:\gow-build-<hash>` 一类，第 5 章）、一张记忆卡、一条 `data/<game>/regional-builds.json` 校验记录、一组条件性覆盖层与基线源码哈希、一次"初始船战"验证路线；启动器版本选择器与卸载器 `/purge` 各多一个分支（第 9 章）。测试矩阵按 `code 数 × 路线数 × 语言目录数` 增长，基座未给三项乘数，需在 `regional-play-ui.py` 处补测。
无运行期语言切换的代价同样可算：设单语言目录字节数 S、语言数 L、共享部分（`mc0`、公共元数据）C，则准备产物约 `S × L + C`；共享 `mc0` 只省掉 C，省不掉 `S × L`（第 4 章）。收益是运行期零分支、故障定位变成"哪个目录、哪个文件"（第 2 章）。**在磁盘预算允许、且语言目录数不大时，这笔交换划算；一旦 L 增长到几十，`S × L` 会成为主要成本，届时正确做法是引入只读共享层而不是加运行期语言开关**——后者会把第 1 章立下的"运行期零分支"整体推翻，代价远大于磁盘。
三类措辞在动作上的差别可以压成一句：`vu1disc` 要补测法，Linux GPU 路径要补验证，Linux 的 PGO／IOP 训练／打包要从零实现。把"未实现"写成"有 bug"，会让维护者对着一个根本不存在的代码路径做二分，而 `build.ps1` 的 `ERROR: <消息>`（第 2 章）里根本没有那条分支。

### 10.4 支持第二款游戏：`adding-a-game.md` 的边界

先钉一处事实缺口：**`docs/adding-a-game.md` 的内容基座未提供，此处事实不足，需在该文档处补测**。以下三层划分是**推断**，依据是前九章已核实的契约——`game.toml` 九个节（第 3 章）、18 阶段流水线（第 5 章）、`recompile.py` 的内容寻址（第 6 章）、90 个补丁的分组（第 7 章）、Linux 平台矩阵（第 2、5 章）；不把推断写成文档规定。

| 层 | 能／不能复用 | 依据 |
| --- | --- | --- |
| 档案层：能参数化 | `[executable]` 的 `name`／`serial`／`crc`／`text_sha1`，`[runtime]` 的模板、函数表、三个覆盖层文件、两个 VU1 生成器、`vu1n_heads.txt`、`iopn_gen.py`，`[disc]` 的 TOC 24 字节条目、两个 PAK、`IOP_MOD`、`R_PERM.WAD`／`R_SHELL.WAD`、`.PSW`／`.PSS` 回退、占位影片 `size = 16388` 加 sha256，`[build].unity_batch = 16`，`[diagnostics].frame_pc`，`[optimize]` 的 `seconds = 240` 与手柄脚本，`[[editions]]`／`[[regions]]`，`[language_hints]` 整句 | 第 1 章"游戏相关的一切全在 `game.toml`"，`profile.py` 读成字典或 JSON 供 PowerShell 与启动器共用 |
| 编排层：不动 | 18 个阶段名与依赖图、`data/pipeline.lock` 单写者、`C:\gow-build` 短根与 `data/build-root.txt` 归属校验、`$env:TEMP`／`$env:TMP` 重定向到 `data/_tmp`、文本输出协议三行、`tools` 阶段 SHA-256 钉版本、内容寻址与目录事务发布、`replace_file` 6 次有界重试、`package` 排除 runtime、1352 行 Win32 安装器的 LZMS 自解包与 `/S` | 这些机制不读游戏常量，只处理"任意一份已参数化的输入" |
| 必然重写 | `config/funcmap.csv`、`config/recomp.template.toml`、`vu1n_heads.txt` 的入口集合、`src/` 下 `gow_overrides.cpp`／`gow_pad2_packet.h`／`gow_gs_replay.h` 一类覆盖层、`tools/vu1/` 与 `tools/iop/` 生成器的输出、`regions` 覆盖层与基线源码哈希、约 6,400 个函数这个约数、`frame_pc = "0x1837B8"` 对应的 `vid::Flip`、占位影片判据与整句语言判据、`[optimize]` 的 240 秒脚本 | 它们全部由具体 ELF 的代码形状与数据布局决定（第 3、6、8 章） |

最难的一格是**90 个补丁**。按第 7 章的六类分组逐类判断：工程类 01／04／31／32／42 与重编译质量类 08／28／29 动的是编译期与发射规则，可能通用；正确性类里 06（`movn`／`movz` 的 64 位语义）属全局发射规则，03／12／24／40／47 却绑定本作的全屏、GS 状态、音频与 GL 上下文；VU1 与 GS 两类的机制（块链接、后台编译、SPSC 环、图元批、深度 ZBP）可能通用，但 44 号的基线定义在 43 号之上、测的是船战存档路线，63／76 热入口针对的是 5 秒船战约 120 万次边界；产品与系统类里 15／16、25、26、39、52／53／54／56、71／73／84 基本都是本作专有（**推断**：依据是补丁主题名与 `gow_*` 覆盖层、`pagina` 页面、`GOW_*` 开关的一一对应；仓库未标注补丁的通用性，需在 `engine/patches/` 处补测）。
由此下一条带条件的判断：**`engine/patches/*.patch` 是《God of War》这一作的性能史，不是可复用的通用补丁库；整链套到第二款游戏会把 `gow_*` 覆盖层、船战假设与 240 秒西班牙语按键脚本一起带过去，而 `fetch` 又是"clone pin 住的 commit + 按文件名顺序 apply"的纯重放（第 1 章），没有条件分支可跳过某几条**。代价是每款游戏要维护一份独立的序数补丁栈与一份 `regions` 目录，单写者锁与短构建根仍可共用。可反驳条件：若 `adding-a-game.md` 已经定义了"公共补丁前缀 + 游戏专有补丁段"的两段式 apply，那么正确做法是复用前缀而不是复制整栈——但基座未提供该文档内容，这一条目前只能作为待核实项。
许可边界不随游戏变：runtime 与它的上游全部 GPL-3.0，本仓库自己写的编排层（Python／PowerShell／C++／QML）与之分离，`CREDITS.md` 逐个列出作者与来源；仓库不含游戏文件也不含由它们生成的代码，安装器在用户机器上从用户自己的光盘映像构建，`package` 阶段明确排除 runtime（第 1 章）。**"能参数化的绝不硬编码"覆盖的是数据，覆盖不了代码形状**：第二款游戏换的是档案值与函数表，不是把 `game.toml` 改一改就能跑起来。

### 10.5 三条对照轴的全书收束

**纵向**（档案 → 光盘 → 生成 → 构建 → 运行）：五步的输入输出契约分别在 `game.toml`（第 3 章）、`identify.py` 五字段 JSON 与 `prepare.py` 三产物（第 4 章）、`recompile.py` 的 sha256 key 与目录事务（第 6 章）、18 阶段与两条自举闭环（第 5 章）、`ps2EntryRunner.exe <disc 目录>/SCUS_973.99`（第 2 章）。"这一步的输入输出契约是什么"在全书没有一步回答不了，也没有一步靠"运行时再看看"。
**横向**（Windows／Linux，USA／欧洲／日本／亚洲）：Windows 格有 `C:\gow-build`、便携工具、PGO profile、Qt 6.8.3 三模块 + `compat/qt-sequence-sort.h`、1352 行自包含 exe；Linux 格 `bash build.sh` → `tools/pipeline/linux.py`（262 行，Python 3.12+、原生 Clang、系统或 SDK Qt 6.5+、SDL2），共享同一份档案、光盘准备、事务式重编译器与序数补丁链，flock 持 `data/pipeline.lock`，产物 `data/build-linux/<game>`，读 `data/build-root-linux.txt` 并按大小写敏感的 CMake 源目录归属校验，手柄采集走 SDL2、玩法仍用 raylib——Windows 的构建根、便携工具、PGO profile 一律不复用（第 2、5、9 章）。区域格四行：USA／欧洲／日本三套 `code`，`asia-97399` 凭引导程序与日版逐字节相同（同 CRC、同 `.text` SHA-1、同尺寸）复用 `code = "japan"` 而光盘数据仍归自己（第 3 章）。同一决策在另一格是否成立，本书每章都问过一次；答案最不对称的就是 Linux 格的能力边界与区域格的"共享链 + 隔离层"。
**深度**（能跑／跑对／跑快／跑稳）：把第 1 章那张表收束，不重复展开。

| 部件 | 现停在哪级 | 下一级门槛 | 出处 |
| --- | --- | --- | --- |
| EE | 跑快 | 08 号 register-locals 约 22% EE 线程时间的收益需在 MMIO／DMA 密集函数上复核 | 第 6、7 章 |
| VU1 | 跑快，边界未闭合 | `vu1n_heads.txt` 覆盖全部寄存器间接跳转；补 5 秒船战约 120 万次边界的覆盖率 | 第 3、8 章 |
| GS | 跑稳 | 4 MB 上限附近的背压、每 ZBP 深度在 8× 档下的实测 | 第 7、8 章 |
| IOP | 跑对 | 把训练与输出确定性扩展到 Linux | 第 1、5、10 章 |
| SPU2／手柄／记忆卡／MPEG | 能跑 | 无独立门槛，随原生服务走 | 第 1 章 |
| Linux 格 | 不在这四级内 | 先补 GPU 验证，再谈成熟度 | 第 8、10 章 |

### 10.6 给维护者的十条硬规则

每条都给可核查位置与违反时的症状，不写"要注意"这类空话。

| # | 规则 | 可核查位置 | 违反时的症状 |
| --- | --- | --- | --- |
| 1 | 游戏常量只写 `games/gow1/game.toml`，任何一层重复写死即缺陷 | `tools/pipeline/profile.py` 读成字典或 JSON（第 3 章） | PowerShell 与启动器读到不同值，且 `pgo-check` 不会报 |
| 2 | 改 runtime 只加 `engine/patches/*.patch`，按序数命名，头部写"是什么、为什么"并补齐基线／测法／结果／回退四字段 | `fetch` 按文件名顺序应用，共 90 个（第 1、7 章） | 补丁重放后形状变了，`pgo-check` 报编译标志或清单失配 |
| 3 | pin commit 或补丁栈任一变更必须重训 | `optimize→native`、`pgo→pgo-check→tune`（第 5 章） | profile 指向不存在的形状；`native` 产出与当前游戏行为不同的 VU1 代码 |
| 4 | 构建根必须短；副本用 `C:\gow-build-<hash>`；归属校验不可跳过 | `data/build-root.txt`、CMakeCache 源目录（第 5 章） | MAX_PATH 报错被误判成编译器问题；新副本误用旧副本 runner |
| 5 | 锁冲突不是构建故障 | `data/pipeline.lock` 独占打开（第 2、5 章） | 去改 `-Toolchain` 参数，而 `msvc` 只是迁移别名 |
| 6 | 帧率只用 `frame_pc = "0x1837B8"` 的客机帧口径，写明呈现条件与交替组数 | 44 号 52.8 → 54.7 FPS、4 组全胜（第 7 章） | 1× 与 8× 的数字被直接相减，宿主呈现率被当成分母 |
| 7 | "未实现／已编译但未验证／已实现但覆盖不全"三态分开写 | 10.3 节四行表 | 对着不存在的功能做二分；`vu1disc` 被当成已验证 |
| 8 | 区域覆盖层绝不进全局序数补丁链 | `games/gow1/regions`、`register_region.py`（第 3 章） | USA runtime 被偷偷打上别人的补丁，`regional-builds.json` 哈希无从定义 |
| 9 | 生成物不手改；改行为走 `src/` 覆盖层与档案 | 所有权感知同步、按 ELF 名匹配（第 2、6 章） | 手改在下一次 `recomp` 后无声消失 |
| 10 | 不在 `data/` 之外缓存游戏数据；`package` 排除 runtime；`/purge` 只在 CMakeCache 确实指向 `<dir>` 时删 | `recompile.py` docstring、`installer/setup.cpp`（第 1、6、9 章） | 派生数据散落系统盘；卸载抹掉另一份副本的构建目录 |

十条里第 3、8、10 条是发布流程的硬条件而非建议：它们各对应一条已经写明的失效链（第 5 章的"产物训练产物"、第 3 章的三重隔离、第 9 章的归属安全）。第 6 条看起来只是测量习惯，实际决定了 90 个补丁里绝大多数性能结论能不能被复核（第 7 章已写明目前多数补丁缺测值）。

### 10.7 一处重做判断

> **工程判断（非仓库规定，带可反驳条件）**
> 如果让我重做，我会把 10.3 的三态写成随构建产物登记的机器可读字段——例如每个 `code` 与每个平台格各带 `implemented`／`compiled_unverified`／`partial_coverage` 之一，由 `verify` 阶段输出一行摘要，启动器版本选择器与 CI 直接读它显示能力边界。理由是三类措辞目前只存在于文档与本书正文里，而 Linux 格恰好同时占着"便携打包未实现""GPU 路径已编译但未验证"两态，最容易被一句"Linux 已支持"抹平；`package` 阶段排除 runtime、`pgo-check` 校验清单与编译标志（第 5 章）说明流水线本来就会产出这类"本次安装能做什么"的清单，加一个能力位不改变架构。代价：多一份状态清单要在每次实现进展后同步，逼近第 1 章立下的唯一事实源；且字段一旦过期，比没有字段更误导。可反驳条件：若 `pgo-check` 的清单或 `data/<game>/regional-builds.json` 已含等价能力位，正确动作是复用那份清单并在 `docs/linux.md` 里写明读法，而不是新增第三份真相源。

### 10.8 本章结论与遗留疑问

本章结论：约 40 个测试里被点名 19 个加 1 个合成测试，纯逻辑、生成与协议层可由 `verify` 脱离光盘回归，安装页、版本选择器、语言目录、`LoadingScreen` 与 `/S` 静默链只能靠五组 UI 测试与三套截图钩子兜底；`docs/` 九篇是契约、`docs/research/` 25 篇是证据，过期证据不删只归档；Linux 的五项未实现、GPU 路径已编译但未验证、`vu1disc` 已实现但覆盖不全，各对应实现、验证、补测三种动作，USA 拒绝异码 ELF 与无运行期语言切换则是按代价接受的设计取舍；支持第二款游戏能参数化的是档案九节与编排层，必然重写的是函数表、覆盖层、生成器输出与本作专有的补丁族。条件是上述划分都建立在 `docs/adding-a-game.md` 未被核实这一缺口上。遗留疑问五处：该文档的实际边界、`tools/test/` 未被点名的约 20 个测试、`docs/research/` 是否建立补丁号索引、S／L／C 与 `code 数 × 路线数 × 语言目录数` 的实测乘数、以及 90 个补丁中通用与本作专有的确切切分，均需在对应文件处补测。

## 全书术语与决策索引

按"决策—理由—代价"三列收束全书，每行只在最合适的章节展开过，此处不重复论证。

| 决策 | 理由 | 代价 |
| --- | --- | --- |
| 仓库定位为编排层，不含 runtime | `engine/runtime.toml` pin commit `471c83180a8df575cff4abd3fae6c043b5096925`（2026-10-16），`fetch` 克隆后按文件名顺序 apply | 本地看不到 196 个 `.cpp`／195 个 `.h`，读一个行为要跨仓库 |
| runtime 与上游全 GPL-3.0，`CREDITS.md` 列作者 | 派生边界与署名链；不能 fork 一份改干净 | 只能打补丁、pin、重放；`package` 明确排除 runtime |
| 90 个补丁按序数命名，头部注释写"是什么、为什么" | `git apply` 忽略注释行，注释随重放走，是唯一留存的本地文档 | 顺序敏感：43 定义 44 基线，29a–29f 必须紧跟 29 |
| `game.toml` 为唯一事实源，`profile.py` 投影字典或 JSON | 六个消费者（识别、准备、生成、运行、UI、优化）不共享运行时 | 任何一层写死游戏常量即缺陷 |
| `text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"` 作身份 | 重编译产物只依赖 `.text`；`recompile.py` 借它用 sha256 做 key | 改代码即需另一套构建；USA 流水线拒绝异码 ELF |
| 翻译版不进白名单 | 只改数据的盘编译出同一个程序 | 条件：一旦翻译改了代码段，结论立即失效 |
| `[[editions]]` 与 `[[regions]]` 分离 | "能不能识别"与"能不能跑"是两件事 | 识别层缺 `playable` 类字段，可跑性由下游隐式反查 |
| `asia-97399` 用 `code = "japan"` | 引导程序与日版逐字节相同（同 CRC、同 `.text` SHA-1、同尺寸） | 光盘数据仍归自己；易被误读成"这张盘是日版" |
| `[language_hints]` 用整句 | `Difficulty` 同时是内部标识符，单词匹配必然误判 | 只替换孤立词条的翻译版会漏判 |
| 占位影片按 `size = 16388` 加 sha256 精确字节判据 | 尺寸阈值会误杀合法短片（PT-BR 独立版 `SEMO01.PSW`） | 判据绑死"这一份字节"，换盘要重取摘要 |
| `frame_pc = "0x1837B8"`（`vid::Flip`）数客机帧 | 游戏绑 60 Hz VBlank，掉帧不减速 | 宿主呈现率、GPU 帧计时三套刻度互不可折算 |
| 每语言一个光盘目录，无运行期语言开关 | 运行期零分支，故障定位变成"哪个目录、哪个文件" | 磁盘约 `S × L + C`；共享 `mc0` 只省 C |
| `.disc_layout` 按扇区列出文件、允许超出盘末端 | 供运行期路径解析，不是原盘元数据镜像 | 目录可被外部改动，缺一份摘要证明"跑的就是 prepare 那份" |
| chdman 0.289 钉 exe 级 SHA-256 | 工具输出是后续所有摘要的输入 | 换构建要重取哈希；7zr 版本与哈希未给 |
| 识别是纯函数，准备才写盘 | 把不可信输入收敛成可校验中间态，写盘有锁、有校验、可重入 | 格式层不能顺手修坏扇区 |
| `data/pipeline.lock` 单写者独占 | 缓存与生成物不能并发更新 | 只读的 `verify` 也要排队；锁冲突常被误判成构建坏 |
| `C:\gow-build`（RelWithDebInfo 用 `C:\gow-build-dev`） | runtime 的 CMake 依赖是 git checkout，长路径必撞 MAX_PATH | 副本要 `C:\gow-build-<hash>` 并登记 `data/build-root.txt` |
| 启动器／卸载器核对 CMakeCache 源目录 | 防新副本误用旧副本构建；Linux 侧大小写敏感 | 缓存被手工替换时字符串比对会失效 |
| `$env:TEMP`／`$env:TMP` 指向 `data/_tmp` | 中间物全部收进 `data/`，不外泄、可清理 | 依赖被调用工具尊重这两个环境变量 |
| 文本输出协议 `=== step ===`／`@@progress`／`@@status` | 终端与启动器共用同一条路径 | 解析脆弱、文案即接口；`all = 18` 时 240 秒的 `optimize` 权重失真 |
| 工具链钉 Python 3.13.16、CMake 3.31.12、Ninja 1.13、sccache 0.19.0 并按 SHA-256 校验 | 下游摘要以工具输出为输入 | 便携 Git 与 llvm-mingw clang 版本号未给 |
| `optimize→native`：240 秒隐藏静音录制，16 号只重建 VU1／IOP | 训练的是数据，可增量 | 验收信号是解释器边界次数，不是构建成功 |
| `pgo→pgo-check→tune`：profdata 后二次构建，四项校验 | 第一遍插桩、第二遍必须去 profiling runtime | runtime 或补丁任一变更必须重训 |
| 内容寻址取代时间戳 | `fetch` 每次重铺 runtime，mtime 变是常态 | key 是否覆盖模板／函数表／覆盖层／补丁栈未被证实 |
| 目录事务发布 + 失败保留上一份可用产物 | 任何时刻读者只看到完整的一套 | 首次 `recomp` 失败没有"上一份"可留 |
| `replace_file` 6 次有界重试 | Windows 扫描器／索引器短暂占用是常态 | 有界才不会把可恢复占用变成挂死流水线 |
| 所有权感知同步，改行为走 `src/` 覆盖层 | 生成物可从摘要重算，用户手改不可复现 | 冲突必须先报再覆盖，否则手改无声消失 |
| 08 号 register-locals，`-Codegen classic` 可回退 | 把 `ctx->r4` 式内存往返交给 clang 寄存器分配 | 约 22% EE 线程时间收益需 29a–29f 六项验收 |
| 28 号直接 `jal`、29 号调度裁剪 | 省掉查表与间接分支，放开调用图优化 | 寄存器间接跳转仍需 `vu1n_heads.txt` |
| 44 号 SPSC 字节环，4 MB 上限、超 1 MB 走堆拷贝 | 每客机帧约 4,000 包，每包一次 mutex 放大固定成本 | 43 号之上、存档路线、全屏、4 组交替：52.8 → 54.7 FPS |
| 区域覆盖层锁在 `games/gow1/regions`，不进全局链 | 作用域、纯度、验证路径三重隔离 | 每 `code` 多一套构建根、记忆卡、哈希与"初始船战"验证 |
| Qt 6.8.3 三模块 + `compat/qt-sequence-sort.h` | 启动器装好之后才跑，可依赖随包交付的 Qt | 源码与钉死 clang 的冲突仍需一份适配头 |
| 1352 行 Win32 + GDI+ 安装器，LZMS 追加自身 + footer、`/S` | 第一个被运行的 exe，无运行库也要双击就跑 | 不用 Qt；单文件体积受 GitHub Release 约束 |
| `/purge` 只在 CMakeCache 确实指向 `<dir>` 时删 | 防 A 副本卸载抹掉 B 副本构建目录 | 缓存被覆盖时应拒绝删除，而不是挑一个信 |
| `docs/` 九篇契约、`docs/research/` 25 篇证据，过期不删只归档 | 证据会随驱动与时序过期，契约不能 | 研究文档不能当"Linux 已验证"的凭据 |
| `verify` 不需要 ISO | 把回归从"要有光盘"里解耦 | 五个 UI 测试仍依赖真实安装或目录状态 |
| Linux 三态分开：五项未实现／GPU 已编译但未验证／`vu1disc` 已实现但覆盖不全 | 三者对应实现、验证、补测三种动作 | 混写会让维护者对着不存在的路径做二分 |

三列合起来只说明一件事：这套系统把不确定性一律关进可核查的边界——pin、摘要、锁、事务、协议、验收；每一条边界都换来一项明确的代价，没有一条是免费的。
