# 《战神》原生 PC 移植版 Mod 管理器：设计与实现手册

> **工程**：`gow-native-pc`（God of War, PS2 SCUS-97399 → 静态重编译 C++ 原生版）
> **文档状态**：设计方案，尚未实现。文中「已实现」与「规划」严格分开标注。
> **撰写日期**：2026-11-05
> **篇幅**：约 4 万字（按 Word 口径约 41,900 字：汉字 25,360 + 中文标点 4,118 + 英文词 10,054 + 数字串 2,359），共 6 卷 27 章 + 8 个附录，约 2,450 行
> **主线约束**：**针对静态重编译后的 C++ 原生版本做 Mod，不改光盘（ISO 只读）、不改 ELF、不改 `.text`。**

---

## 路径与记号约定

本文档所有相对路径以工程根为基准：

```
ROOT = <repo>
```

运行时工作树另设缩写：

```
RT    = ROOT/engine/runtime                     （fetch 阶段克隆，不在仓库里）
PS2R  = RT/PS2Recomp/ps2xRuntime                （原生运行时主体）
PS2I  = RT/PS2Recomp/ps2xIOP                   （IOP 模拟层）
PIPE  = ROOT/tools/pipeline                     （构建流水线）
```

另有两处简写：文中 `modules/xxx.ps1` 一律指 `PIPE/modules/xxx.ps1`；单独出现的 `gow_overrides.cpp` 一律指 `RT/src/gow_overrides.cpp`。`GOW_*` / `PS2X_*` / `TOBIICHI_*` 则是环境变量前缀，不是路径缩写。

引用格式 `[实证]` 表示该结论来自当前磁盘上真实存在的代码或文件；`[规划]` 表示只出现在文档/roadmap 里；`[缺失]` 表示被文档引用但当前副本里没有实体。三者不可混用——这份工程里有大量「文档说有、实际没有」或「文档说没实现、实际已实现」的倒挂，第 2 章专门盘点。

---

## 目录

**卷 0　速览与读法**

- 0.1 这份文档解决什么、不解决什么
- 0.2 一页结论
- 0.3 五个铁律
- 0.4 按角色阅读的路径

**卷 I　现状盘点：你要管的到底是什么**

- 第 1 章　工程不是模拟器，是一份被编译出来的程序
- 第 2 章　现有能力的真实清单（实证 / 规划 / 缺失）
- 第 3 章　不可违反的硬约束

**卷 II　总体架构**

- 第 4 章　设计目标与非目标
- 第 5 章　三层注入模型
- 第 6 章　组件架构与数据流
- 第 7 章　技术选型论证
- 第 8 章　目录布局与文件所有权

**卷 III　数据模型：Mod 包格式**

- 第 9 章　设计原则
- 第 10 章　`mod.toml` 完整规范
- 第 11 章　目标指纹与兼容性判定
- 第 12 章　能力声明与最小权限
- 第 13 章　Payload 类型规范
- 第 14 章　冲突模型与确定性排序
- 第 15 章　Profile、状态文件与锁

**卷 IV　实现：从包到进程**

- 第 16 章　安装与导入
- 第 17 章　Planner：解析、依赖、冲突求解
- 第 18 章　Applier：三层注入的具体落地
- 第 19 章　事务、回滚与崩溃恢复
- 第 20 章　Launch Bridge：与 launcher / pipeline 集成
- 第 21 章　诊断与可观测性

**卷 V　质量、合规与路线图**

- 第 22 章　测试策略
- 第 23 章　性能预算
- 第 24 章　安全、供应链与版权
- 第 25 章　分阶段路线图 P0–P6
- 第 26 章　风险登记册
- 第 27 章　反模式与常见问题

**附录**

- A　`mod.toml` 完整示例（四类 Mod）
- B　`plan.json` / `state.json` / `mod-report.json` schema
- C　C++ 代码骨架
- D　Python 代码骨架
- E　CLI 命令表与错误码表
- F　真实可用的环境变量速查表
- G　术语表
- H　与现有文档的偏差登记

---

# 卷 0　速览与读法

## 0.1 这份文档解决什么、不解决什么

`README.md` 的 Roadmap 第 4 项写着「Mods and texture packs」，`docs/input-accessibility.md` 又明确写着「**This is a home for future mod controls, not a claim that a general mod manager is implemented**」。也就是说，工程里现在有一个纹理包开关、一个 xdelta 补丁 stage、一个只读的 Accessibility 页面，但**没有**一个统一的 Mod 管理器。

这份文档要回答的问题只有一个：

> 在**不修改光盘镜像、不修改 ELF、不修改 `.text`**的前提下，怎样为一份静态重编译出来的 C++ 程序，做一个可安装、可启用/禁用、可排序、可冲突检测、可回滚、可诊断的 Mod 管理器？

它**不**回答：

- 怎样破解、绕过或分发游戏资源；
- 怎样做一个跨游戏通用的 Mod 管理器（本方案深度绑定 `gow-native-pc` 的目录、补丁链与运行时符号，通用化只在 7.3 节讨论代价）；
- 怎样实现纹理替换算法本身（那是 `engine/patches/52-gs-texture-packs.patch` 已做的事，本方案只负责把多个包喂给它）；
- 怎样修渲染器、VU1、音频等与 Mod 无关的性能问题。

读者应当带着一个基本判断来读：**Mod 管理器 90% 的复杂度不在「把文件放到哪里」，而在「判断这份 Mod 能不能用于这台机器上的这份二进制」以及「多个 Mod 抢同一个资源时谁赢、怎么撤退」**。文件复制是最简单的一步，第 16 章只占很小篇幅；第 11 章（指纹）、第 14 章（冲突）、第 19 章（事务）才是主体。

## 0.2 一页结论

**一句话定义**：Mod 管理器 = 以「目标二进制指纹」为键，把一组声明式 Mod 包编译成一份**确定性启动计划**，再以事务方式把这份计划投射到宿主 C++ 运行时上的规划器 + 执行器。它不是文件管理器，也不是安装器。

**架构一句话**：三层注入、一个规划器、一份计划、一次事务。

| 层 | 时机 | 落点 | 代价 | 典型 Mod |
|---|---|---|---|---|
| L1 编译期 | `build.cmd -Stages fetch,configure,recomp,sync,build` | `engine/patches/NN-*.patch` 链尾、`runtime.overrides`、`funcmap.csv` | 需要重编译（分钟～小时级） | 新增宿主 C++ 功能、改 GS/SPU2 行为 |
| L2 启动期 | 玩家点「开始游戏」之前 | 环境变量、`gow-native.boot`、VFS 覆盖表、纹理包目录 | 每次启动重算，毫秒级 | 参数档、画质档、资源包开关 |
| L3 运行时 | 进程已起来 | `PS2Vfs::resolveHostPath`、`PS2Runtime::replaceFunction`、纹理 `TexturePack` | 每帧零额外 IO | 文件覆盖、函数装饰、纹理替换 |

**取舍**：绝大多数 Mod 应落在 L2/L3。只有确实需要新增宿主 C++ 能力的 Mod 才走 L1，而且**绝不直接编辑 `engine/runtime/`**——那棵树被 `fetch` 严格管控，手改会在下次构建时被拒绝或冲掉（见 3.1）。

**五个最关键的真实注入点**（第 2 章会展开，这里先给结论）：

1. `PS2R/src/lib/ps2_vfs.cpp` 的 `PS2Vfs::resolveHostPath()` —— EE 侧唯一集中的「guest 路径 → 宿主路径」映射，`cdrom0:` / `host0:` / `mc0:` 全走它。
2. `PS2R/include/ps2_runtime.h` 的 `replaceFunction(uint32_t, RecompiledFunction)` —— 不动 ELF 就能把某个 guest 函数整体换成宿主 C++ 实现，`RT/src/gow_overrides.cpp` 里已有约 40 处范例。
3. `RT/src/gow_overrides.cpp` 的 `applyGowOverrides()` 与 `PS2R/src/lib/gow_integracion.cpp` 的 `gowIntegracionInstalar()` —— 现成的「按 ELF 名注册 + 装饰器链」范式。
4. `engine/patches/52-gs-texture-packs.patch` 的 `GOW_TEXTURE_PACK` —— 已实现且兼容 PCSX2 命名的纹理包，含异步解码与 LRU。
5. `PS2R/src/main.cpp` 的 `gow-native.boot`（`GOW_NATIVE_BOOT_V1`）—— 无参数启动时唯一的启动期配置入口，只接受 `TOBIICHI_` / `PS2X_` / `GOW_` 三种前缀。

## 0.3 五个铁律

这五条不是建议，是从工程代码里反推出来的硬边界。后续所有设计都以满足它们为前提。

**铁律一：ISO 只读，ELF 只读，`.text` 只读。** 这是本方案的首要约束。光盘镜像只作为资源来源与身份输入，Mod 不写回任何扇区；`tools/disc/prepare.py` 产出的 `data/<id>/discs/` 是只读基线。改 `.text` 会让 `identify.py` 的 `.text SHA-1` 校验、`recompile.py generate()` 的 ELF 校验、`register_region.py` 的三重身份校验全部失效，也会让按 guest 地址绑定的 override 全部错位。`engine/patches/52` 之外的第三方 ISO Mod（例如研究文档里提到的 Definitive Edition 2.0 `.xdelta`，其加载器用 `host0:/mod/%s.wad`）当前不受支持，本方案把它归入「来源校验」而非「执行路径」。

**铁律二：不直接编辑 `engine/runtime/`。** `modules/runtime.ps1` 在 `fetch` 时要求工作树无本地改动，先 `git checkout` 到 `runtime.toml` 钉住的 commit，再用临时 `GIT_INDEX_FILE` 做前缀树推演，逐个 `git apply` 补丁链；链外改动会报 `engine/runtime differs from the patch chain`。编译期注入只能以**追加一个新的 `NN-*.patch`** 形式存在，并交给 `tools/pipeline/patches.ps1` 的补丁栈工作流管理。

**铁律三：帧循环零磁盘 IO。** GS worker 独占 GL 上下文（`gs_texture_store.h:7`、`gs_gl.cpp` 的 `Context::CreateWorker`），`gs_stage.cpp` 的字节环是单生产者单消费者、对延迟极敏感。patch 52 的做法是范本：启动时递归扫一次目录只建索引，PNG 在 worker 线程解码，render 线程只做上传与 LRU，未就绪时**继续画原纹理、绝不等待**。任何「在 `resolveHostPath` 里读 manifest」「在 `replaceFunction` 包装里查表文件」的设计都是错的——表必须在启动前建好，运行时只做内存哈希查找。

**铁律四：身份不匹配就拒绝，不做「尽力而为」。** 工程已经有三套强校验：`identify.py` 比对 ELF CRC 与 `.text SHA-1`、`recompile.py` 比对 `recompile_elf`、`register_region.py` 比对 `elf.name / text_sha1 / pcsx2_crc`。Mod 管理器要沿用这个性格：指纹不符直接给出可读错误和「哪些字段不一致」，绝不悄悄降级或猜测。静默降级在原生重编译版里的后果比模拟器严重得多——地址会错位，表现是随机崩溃而不是画面小瑕疵。

**铁律五：只发机制与配置，不发游戏衍生数据。** `CREDITS.md:30-33` 写明「No game files (disc images, executables, data, the C++ generated from them, recorded microcode) are part of this repository」；`AGENTS.md:299-303` 写明纹理包、dump、第三方补丁、ISO 一律不得提交或打包；`modules/distribution.ps1:59` 的白名单只有 10 项且不含 `data/`。因此 Mod 管理器可分发的是 `mod.toml`、TOML/JSON 配置、补丁文本、脚本、代码，**不可**分发纹理 PNG、WAD、FMV、存档、ISO、生成的 C++、VU1 录制或 PGO profdata。

## 0.4 按角色阅读的路径

| 你是 | 建议路径 |
|---|---|
| 只想先看可行性 | 0.2 → 第 1 章 → 第 5 章 → 第 25 章 |
| 要写 `mod.toml` / 做 Mod 包 | 卷 0 → 第 9–13 章 → 附录 A → 附录 E |
| 要实现管理器本体 | 卷 I → 卷 II → 卷 III → 卷 IV（重点 17、18、19 章） |
| 要接进 launcher | 第 20 章 → 第 22 章 → 附录 C（ModsModel） |
| 要做质量/发布把关 | 第 3 章 → 第 22–24 章 → 附录 H |
| 要排查「装了 Mod 就崩」 | 第 21 章 → 19.4 → 附录 F → 第 27 章 |

文档里的代码片段是**可编译骨架**，不是伪代码占位：C++ 片段使用工程里真实存在的类型名（`PS2Runtime`、`RecompiledFunction`、`PS2VfsMounts`），Python 片段沿用 `tools/` 下现有脚本的风格（`pathlib`、`tomllib`、`atomic_json`、`python -I` 调用方式）。凡是需要你自行补全的业务逻辑，都会用 `// TODO(impl)` 显式标出。

---

# 卷 I　现状盘点：你要管的到底是什么

## 第 1 章　工程不是模拟器，是一份被编译出来的程序

### 1.1 从 ISO 到 `ps2EntryRunner.exe`

绝大多数人对「游戏 Mod」的心智模型来自模拟器：一个 ISO、一个补丁文件、一个纹理包目录，模拟器在运行时解释它们。这个工程不是那样。`docs/architecture.md` 给的链路是：

```
ISO(s)
  └─ tools/disc/identify.py      校验 BOOT2 / ELF CRC / .text SHA-1 / 语言
      └─ tools/disc/prepare.py   解包到 data/<id>/discs/*，写 .disc_layout、
                                 languages.json、共享 mc0
          └─ games/<id>/game.toml + engine/runtime.toml
              └─ build.ps1 : fetch     克隆 Tobiichi-Port 到 pin commit
                          : configure CMake/Ninja（C:\gow-build*）
                          : recomp    ps2xRecomp 把 ELF → ~6400 个 C++ 函数
                          : sync      生成物并入 runtime 的 src/runner 与 include
                          : build      clang Release → ps2EntryRunner.exe
                              └─ launcher 选语言 ELF + 环境变量 → 启动
```

关键转折在 `recomp`：**游戏代码在这一步变成了宿主 C++**。`PS2R/include/ps2_runtime.h` 里有一张按 4 字节对齐的稠密函数表 `g_ps2RecompiledFunctionTable`，由生成的 `register_functions.cpp` 在进程启动时填充（`engine/patches/41-register-functions-o1.patch` 说明这个文件约 155k 条 store、12.8 MB，单独以 `-O1` 编译）。运行的是这张表里的 C++ 函数指针，不是 MIPS 指令。

这意味着：

- 「改游戏代码」在本工程里等价于**改 C++ 并重新编译**，或**在运行时替换表项**（`replaceFunction`），而不是给 ROM 打补丁；
- 「改游戏资源」在本工程里等价于**改 `data/<id>/discs/` 下解包目录里的文件**，或**在 VFS 层把路径指到别处**，而不是改 ISO 扇区；
- 「游戏版本」不再只由 ISO CRC 决定，而是由 **ELF `.text` + runtime commit + 补丁链 + 生成配置**共同决定。

一句话：**Mod 管理器面对的不是一张光盘，而是一份被反复生成、且生成结果依赖七八个输入的二进制。** 这正是第 11 章要把指纹做成多元组的原因。

### 1.2 三份「真相」

工程里有三处并列的真相来源，Mod 管理器必须同时尊重，不能只挑一个。

| 真相源 | 路径 | 管什么 | 谁读 | 改动后果 |
|---|---|---|---|---|
| 游戏档案 | `games/<id>/game.toml` | ELF 名、CRC、`.text SHA-1`、`regions`、`paks`、`text_files`、`editions`、`runtime.overrides`、`funcmap` | `tools/pipeline/profile.py`（`tomllib`）、`identify.py`、`prepare.py`、`recompile.py` | 改了会变 `recompile.py` 内容寻址 key，触发重新生成 |
| 运行时基线 | `engine/runtime.toml` | 上游仓库 URL + pin commit（`471c8318…`，2026-10-16） | `modules/runtime.ps1` 的 `fetch`、`distribution.ps1` 的 PGO 身份 | 换 commit 等于换整个运行时，所有 Mod 指纹失效 |
| 补丁链 | `engine/patches/NN-*.patch` | 72 个补丁，按 `Ordinal` 字符串序 `git apply` | `modules/common.ps1:Get-RuntimePatches()`、`modules/runtime.ps1`、`patches.ps1` | 追加/改动补丁会变 `Get-ProfileIdentity()` 的补丁集 SHA-256 |

`modules/game.ps1:Get-ProfileIdentity()` 已经把后两者与 `games/<id>`、`ELF .text` 的 SHA-256 合成 PGO 身份，`distribution.ps1:65-73` 会在打包时校验 manifest 匹配，不匹配就拒绝发布。**这不是巧合，而是本方案第 11 章指纹模型的现成原型**：工程自己早就在用「多输入哈希」来判定「这份二进制是不是我认识的那份」。Mod 管理器要做的是把这个思路从 PGO 扩展到 Mod，并加上「补丁链哈希」与「区域构建身份」。

`game.toml` 里与 Mod 最相关的字段（`games/gow1/game.toml`，134 行）：

```toml
id = "gow1"                      # 目标 game id
status = "playable"              # context.ps1 会拒绝 status="planned"
[executable]
name = "SCUS_973.99"            # override 按这个文件名匹配，改名即失效
serial = "SCUS-97399"
crc = "D6385328"
text_sha1 = "8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00"
[runtime]
overrides = ["src/gow_overrides.cpp", "src/gow_pad2_packet.h", "src/gow_gs_replay.h"]
function_map = "config/funcmap.csv"
[disc]
toc = "GODOFWAR.TOC"
paks = ["PART1.PAK", "PART2.PAK"]
text_files = ["R_PERM.WAD", "R_SHELL.WAD"]
movie_ext = ".PSS"
widescreen_movie_ext = ".PSW"
[[editions]]  # usa / …；[[regions]] 共 8 条，含 japan / europe / demo
[language_hints]  # 6 语言整句提示，identify.py 用来猜语言
```

注意 `text_sha1` 的注释：「重编译代码只依赖 `.text`，纯数据翻译会重编译成同一程序」。这句话是 Mod 兼容性的第一块基石：**只要 `.text` 相同，不同语言的盘可以共用同一套代码级 Mod**；反过来，任何改了 `.text` 的东西（某些第三方 ISO Mod 会做）都不属于本方案的支持范围。

### 1.3 为什么「改光盘」是错的方向

这一节专门回答本次需求里那句「**c++ 编译版本，不是改光盘**」。它不只是偏好，而是六条工程事实共同推出的结论。

**事实 1：代码已经不在光盘里了。** 重编译之后，`SCUS_973.99` 这个 ELF 的作用只剩两件事——提供 `.text` 作为身份与生成输入，以及作为 `cdRoot` 的定位锚点（`AGENTS.md:192-195`：ELF 所在目录即光盘根目录）。玩家按下的每一个动作，执行的是 `ps2EntryRunner.exe` 里的 C++。往 ISO 里写代码补丁，对运行中的程序毫无影响。

**事实 2：运行时读的是解包目录，不是 ISO 扇区。** `tools/disc/prepare.py` 把 ISO 解成 `data/<id>/discs/<edition>/`，并写 `.disc_layout`（每行 `file <lsn> <size> <name>`）与 `.disc_meta`。`PS2I/src/disc_source.cpp` 的 `ExtractedDisc::openExtracted()` 靠这两个文件工作，`fileAt(sector)` 二分定位、`handle(Entry)` 缓存 `ifstream`。`GOW_ISO` 环境变量可以显式指定原盘镜像，但那是 `configureGowCdImage()` 的兜底路径，不是常态。所以「资源覆盖」的正确落点是解包目录里的文件，或 VFS 映射，而不是光盘镜像。

**事实 3：改 ISO 会连锁破坏身份校验。** `identify.py` 比对 BOOT2 ELF 名、`known_crc`、`known_text_sha1`，并计算 `compatible = code_ok and status != 'planned'`；`recompile.py generate()` 比对 `recompile_elf` 的名字与 `.text SHA-1`；`register_region.py` 比对 `elf.name / text_sha1 / pcsx2_crc` 三项。任何写回 ISO 的行为都会让这三层校验中的至少一层失败，且失败点分散在不同 stage，排查成本极高。工程自己的 `audio-standalone-mods-2026-10-26.md:85-95` 也写得很清楚：「改了可执行代码/区域的补丁需要新的 port/profile 和回归测试，**不要绕过 `.text` 检查**」。

**事实 4：改 ISO 的成本是「重新准备 + 可能重新编译」。** `discs` stage 会重跑 `prepare.py`，生成 `languages.json`、`mc0` 与解包目录；若 ELF 变了，`recomp` 的内容寻址 key（含 ELF、funcmap、template、profile、`PS2X_*` 环境变量）随之变化，触发整轮生成。一次几十分钟到数小时，换来一个「随时可以关掉」的 Mod 本该有的体验，完全不划算。

**事实 5：区域版本各有独立构建，改盘覆盖不到 C++ 侧。** `games/gow1/regions/` 里 Europe / Japan 各有 `entries.json`（4093 / 4020 个 entry point）、`functions.csv`、`runtime.patch`、`baseline.json`，`data/gow1/regional-builds.json` 注册独立的 runner / ELF / dataDir / framePc。这些差异是**编译期**的（函数地址、override 集合、frame probe 都不同）。一个只改了 ISO 的 Mod 无法为三个区域提供一致行为，反而会因为 `.text` 不同而踩中地址错位。

**事实 6：版权与发行。** ISO 与提取出的 WAD / PAK / FMV 都不能进仓库或发行包（`CREDITS.md`、`AGENTS.md:299-303`、`distribution.ps1:59` 的 10 项白名单）。Mod 如果要能分发，就只能是「声明 + 差分 + 代码」，天然指向宿主侧而不是镜像侧。

**结论**：本方案把 ISO 定位为**只读来源与身份输入**。已有 `xdelta` stage（`modules/runtime.ps1:56-76`，用 `tools/disc/vcdiff.py` 逐窗口 adler32 校验，产出 `data/mods/isos/<name>.iso`）保留为「玩家自有镜像的离线辅助能力」，但**不作为 Mod 执行主线**；第 13 章会把它降级为「来源类 Mod」，仅用于生成只读基线，且默认禁用。第 18 章所有 Applier 逻辑都作用在 L2/L3，不写任何扇区。

### 1.4 与模拟器 Mod 生态的七个差异

做设计最容易犯的错，是把 PCSX2 / RPCS3 那套经验直接搬过来。下表逐条对照，右列是本方案必须做的调整。

| # | 维度 | 模拟器生态 | 本工程（实证） | 本方案的调整 |
|---|---|---|---|---|
| 1 | 代码补丁 | `.pnach` 在运行时改 guest 内存 | 代码已是 C++；`replaceFunction()` 换表项，或改 C++ 重新编译 | 代码级 Mod 走「宿主函数替换」或「链尾 patch」，不做内存补丁 |
| 2 | 纹理 | dump → 编辑 → replacements 目录 | **patch 52 已兼容 PCSX2 命名**（`<tex>-<pal>-<bits>.png` / `<tex>-<bits>.png`），可直接用现成包；但这是唯一兼容项 | 纹理 Mod 只需做「多包目录合并 + 预算分配」，不重造 hash |
| 3 | 文件覆盖 | hostfs / 覆盖目录，单一路径层 | **两层**：EE 侧 `PS2Vfs::resolveHostPath` 按路径；IOP 侧 `sceCdRead` 按 LSN 读 TOC/PAK | 覆盖表按「EE 路径」建模；PAK 内资源必须走离线 TOC 重指（`prepare.py:225-240` 的 `TR_*` 做法），不能假装能按路径覆盖 |
| 4 | 存档 | savestate、即时读写 | **无 savestate**；只有 8 MB（8,650,752 字节）PCSX2 `.ps2` 卡镜像，运行中常驻内存 | 存档 Mod = 启动前用 `GOW_MC0` 指向一份卡镜像；禁止热替换 |
| 5 | 版本身份 | CRC / serial | ELF CRC + `.text SHA-1` + runtime commit + 补丁链 + codegen/环境变量 + 区域构建 | 指纹做成多元组，分 exact / code-compatible / any 三档（第 11 章） |
| 6 | 参数热更新 | 多数设置可随时改 | `gow_ajustes_vivo.h` 的 header-only atomics 由 `cargar()` 用函数内 `static const bool` **只读一次环境变量**；F1 菜单改的是 atomic，仅本会话有效 | 参数 Mod 是「启动期」概念；运行期改 env 无效，必须在 Launch Bridge 合成 |
| 7 | 发行 | Mod 包常含资源 | 严格白名单，游戏衍生数据一律不得打包 | Mod 包只能是声明 + 差分 + 代码；资源由玩家本机生成或自备 |

还有一条容易被忽略的差异：**本工程没有统一的「Mod 加载点」**。模拟器的纹理替换、文件覆盖、代码补丁都在同一个进程初始化路径上；这里分散在 `recompile.py`（生成期）、`build.ps1`（构建期）、`launcher`（启动期）、`PS2Runtime::loadELF`（运行期）四个时刻。第 5 章的三层模型就是为这件事而存在的——不是因为三层更优雅，而是因为工程本来就有四个时刻，硬压成一层会处处碰壁。

---

## 第 2 章　现有能力的真实清单（实证 / 规划 / 缺失）

这一章是整份文档的「地基校验」。工程里存在大量**文档与代码倒挂**：`README.md:304` 说「纹理 dump 与替换是设计、未实现」，但 `engine/patches/52-gs-texture-packs.patch` 其实已经落地并在工作树里生效；反过来 `docs/input-accessibility.md` 说 Accessibility 页「是未来 Mod 控件的家」，容易被误读成已有管理器。做设计前必须把两者分开，否则会重复实现已存在的能力，或依赖不存在的接口。

### 2.1 已实现：纹理包（patch 52）

`engine/patches/52-gs-texture-packs.patch` [实证] 只改了 4 个文件：

| 文件 | 改动 |
|---|---|
| `PS2R/CMakeLists.txt` | `FetchContent_Declare(xxhash v0.8.3)`，header-only，用 `SOURCE_SUBDIR gow-header-only` 避免构建其 CMake 项目 |
| `PS2R/src/lib/gs/gpu/gs_gl.h` / `gs_gl.cpp` | `Api` 增加 `void (*GenerateMipmap)(GLenum)` 并 `load` 到 `glGenerateMipmap` |
| `PS2R/src/lib/gs/gpu/gs_hw_backend.cpp` | 主体，约 440 行新增：`pcsx2TextureHash` / `pcsx2PaletteHash` / `parsePackName` / `class TexturePack` / `replacementFor` |

运行机制（工作树 `gs_hw_backend.cpp` 行号）：

- `TexturePack::open()`（`:1195`）读 `GOW_TEXTURE_PACK=<folder>` 与 `GOW_TEXTURE_PACK_MB`（默认 1024，最小 64 MB），用 `recursive_directory_iterator` 递归扫目录，**只取文件名 stem 作为键**，子目录路径不参与身份；解析成功者存进 `m_entries[key].path`，然后起一个 `m_worker` 线程。
- `lookup()` 命中 Ready 直接返回 GL texture id；命中 Idle 则置 Queued、投递队列、**返回 0**（继续画原纹理，绝不等待）。
- `work()` 在 worker 线程用 raylib 的 `LoadImage` → `ImageFormat(RGBA8)` → `UnloadImage`；故意不 `#include <raylib.h>`，用 `extern "C"` 声明避开 Win32 的 `LoadImage` 宏。
- `service()` 每帧在 render 线程调用，做 `GenTextures/TexImage2D/GenerateMipmap`、按 `m_budget` 做 LRU 淘汰；`GOW_TEXTURE_PACK_STATS` 每 300 帧打印 `hits/loads/evictions/resident`。
- 绘制路径 `:2871-2880`：替换存在时 `indexed = false`，走 direct-colour 路径，`BindTexture` 用 replacement id，min filter 为 `LINEAR_MIPMAP_LINEAR`。
- `textureFor()` / `indexTextureFor()` 各只加一行 `tex.pcsx2Hashed = false`，保证重解码时重算 hash；**`invalidateBlocks` 与 `gs_texture_store.cpp` 均未被 patch 52 修改**。

命名规则（PCSX2 格式，直接兼容现成包）：

```
索引/调色板：  <texhash>-<palhash>-<bits>.png
直接色：       <texhash>-<bits>.png
texhash / palhash = XXH3-64；bits = psm | tw<<6 | th<<10（+TEXA 位），8 位十六进制
```

几个必须记住的细节：`bits` 里的旧 TCC 位 `0x4000` 被 `& ~0x4000u` 忽略；`parsePackName` 要求 `sscanf` 扫到字符串结尾，所以 `-r<w>x<h>` 区域后缀、`-mip<n>` 后缀**不被支持**；PNG 的 alpha 直接用 GS 单位，**128 = 不透明**，不做 0–128 ↔ 0–255 转换；depth 格式 `pcsx2TextureHash` 直接 `return false`，渲染目标 / FMV 帧永不替换（靠 `uploaded = !(src||rsrc||zsrc)` 判定）。

实测数据（patch 头部与 `docs/research/texturas-e-mods-2026-11-01.pt-BR.md:74-85`）：船上战斗场景，PCSX2 包命中 **81 张 / 73 MB / 零 eviction / FPS 在 run-to-run 噪声内**。原型版本（同步解码）曾出现可见卡顿，最终版靠异步消除。这个数字是第 23 章性能预算的基线。

开发者开关 `GOW_TEX_PCSX2_NAMES=<file>` 把本局被 draw 采样的纹理名写成清单（含 `tbp/tbw/psm/cpsm/csa` 与可选的 `in-pack`），**只写名字不写图像**——这正是 Mod 作者制包与第 21 章诊断该复用的入口。

### 2.2 与设计文档的倒挂（重要）

`docs/research/texture-replacement.md` 首行自称 `Status: design only, nothing implemented`，并说「roadmap 的 42-43 号已被占用，补丁写的时候取下一个空号」。实际落地的是 **52 号**，且设计几乎全被改写：

| 维度 | `texture-replacement.md`（未实现） | 真实 patch 52 |
|---|---|---|
| 兼容性 | 「不要假设已有 PCSX2 包能用」，PCSX2 导入列为 later | **完全兼容 PCSX2 命名**，直接吃现成包 |
| 哈希 | 自定义 `XXH3_64(version byte + psm/TW/TH + 反 swizzle texel + CLUT)`，`<16 hex>.png`，`-any.png` | PCSX2 原样：整块 GS 内存优先，否则反 swizzle 行；无 version byte、无 `-any` |
| 挂钩 | `textureFor` / `indexTextureFor` 作主钩子，要求 `invalidateBlocks` 联动 | 主逻辑在 draw 路径 `replacementFor` + `TexturePack`；两个入口各只加 1 行；**未改 `invalidateBlocks`** |
| 环境变量 | `GOW_TEX_DUMP` / `GOW_TEX_REPLACE` / `GOW_TEX_DIAG` / `GOW_TEX_PRELOAD` / `GOW_TEX_DUMP_MIN` | `GOW_TEXTURE_PACK` / `_MB` / `_STATS` / `GOW_TEX_PCSX2_NAMES`（**名字全不同**） |
| dump | 要求写 PNG（含 alpha 转换、writer 线程、有界队列） | **无 dump**，只有名字清单 |
| 尺寸约束 | 整倍数、≤8×、≤4096；后续 BC7 DDS | 无尺寸校验，按 PNG 自身分辨率；无 DDS |
| F1 菜单 | 要把 Texture pack 做进 `gow_ajustes_vivo.h` | `gow_ajustes_vivo.h` 里**没有**该 atomic；开关在 launcher 的 Accessibility 页 |

**给设计的直接结论**：不要再按 `texture-replacement.md` 设计 `pack.toml`、dump 流程或 `-any` 规则。纹理这一层的正确抽象是「**一个 `GOW_TEXTURE_PACK` 目录 = 一组 PCSX2 命名的 PNG**」，管理器的工作是把多个 Mod 包合并成**一个**符合该格式的目录（或按优先级生成符号链接树），并分配 `GOW_TEXTURE_PACK_MB` 预算。附录 H 会把这条列为「需要回写现有文档」的偏差。

### 2.3 已实现：代码级注入（`replaceFunction`）

这是本方案最 powerful 的一层，且**完全不需要改 ELF、不需要重新编译**。

注册宏与匹配 [实证]：

```cpp
// PS2R/include/game_overrides.h:40-53
PS2_REGISTER_GAME_OVERRIDE(NAME, ELF_NAME, ENTRY, CRC32, APPLY_FN)
// RT/src/gow_overrides.cpp:2175
PS2_REGISTER_GAME_OVERRIDE("God of War (SCUS-97399)", "SCUS_973.99",
                           0x00100008u, 0u, applyGowOverrides)
```

`PS2R/src/lib/game_overrides.cpp:122-182` 的 `applyMatching()` 用 `basenameFromPath(elfPath)` 取文件名，大小写不敏感比对 `descriptor.elfName`，再可选比对 entry / crc32，命中就调 `descriptor.apply(runtime)`。调用点在 `PS2R/src/lib/ps2_runtime.cpp:1160` 的 `loadELF()` 内。

替换 API [实证]：

```cpp
// PS2R/include/ps2_runtime.h:295,321-324
using RecompiledFunction = void (*)(uint8_t*, R5900Context*, PS2Runtime*);
bool replaceFunction(uint32_t address, RecompiledFunction func);
bool registerFunction(uint32_t address, RecompiledFunction func); // = replaceFunction
RecompiledFunction lookupFunction(uint32_t address);
```

实现 `ps2_runtime.cpp:1228-1265`：`slot = (address - tableBase) >> 2`，写 `g_ps2RecompiledFunctionTable[slot]`。`applyGowOverrides()`（`:2039-2172`）里已有约 40 处 `replaceFunction`，覆盖 `gowIpuInit`、`gowRand`、`gowPad2*`、电影函数族、`gowSnd989SendCommand`、`gowCdReadDvdDualInfo` 等。

**装饰器链范式** [实证]（`PS2R/src/lib/gow_integracion.cpp:425-463`）：先 `lookupFunction` 保存原实现到全局指针，再 `replaceFunction` 装上 wrapper，wrapper 内部调用原实现。注释明确顺序敏感（`:459`「cancelar 在 fijar 之后：链接它的 wrapper」）。这对 Mod 管理器极其重要——**多个 Mod 抢同一个 guest 地址时，正确做法不是「后者覆盖前者」，而是按优先级串成一条装饰链**，第 14、18 章会据此设计。

四条硬限制，必须写进 Mod 校验器：

1. 地址必须 4 字节对齐且落在生成的稠密表范围内；否则 `replaceFunction` 返回 `false` 并打印 `[function-table] cannot replace guest PC ...`。
2. 签名固定 `(uint8_t* rdram, R5900Context* ctx, PS2Runtime* runtime)`，Mod 作者须自己遵守 guest ABI（`$a0..`、返回 `$v0`、必要时 `ctx->pc = $ra`）。
3. 时机必须在 `loadELF` 的 `applyMatching` **之后**、且 `gow-native.boot` 恢复环境**之后**（`engine/patches/29a-call-diagnostics-init.patch` 的教训：静态初始化太早）。
4. override 按 **ELF 文件名**匹配；`game.toml:8` 要求所有 prepared disc 目录保留原名 `SCUS_973.99`，改名 ELF 会让整套 override 失效。

另有两个「按名字绑地址」的辅助：`ps2_game_overrides::bindAddressHandler(runtime, 0x00296C48, "sceSifInitRpc")`，内部走 `PS2_SYSCALL_LIST` / `PS2_STUB_LIST`。`config/funcmap.csv`（6414 个函数边界）与 `entries.json` 的 `entry_points` 是**生成期**配置，改了必须重跑 `recomp`；运行时注入不要碰它们。

### 2.4 已实现：VFS、启动配置、路径与存档

**VFS 是两层，别只盯 IOP。**

- **EE 侧按路径**：所有 `sceOpen` / `fioOpen` / `sceGetstat` 汇聚到 `PS2R/src/lib/ps2_vfs.cpp:270-302` 的 `PS2Vfs::resolveHostPath(path, mounts, result)`。设备映射 `Host → hostRoot`、`Cdrom → cdRoot`、`MemoryCard0 → memoryCard0Root`、`NativeHost → 直接 lexically_normal`、`Rom0 → false`（另走 ROM）。`stat()`（`:235`）也调它，所以覆盖表只要作用于这一个函数，`open` 与 `stat` 自动一致。`PS2R/src/lib/ps2_iop_host.cpp:289-297` 的 `translateGuestPath` 同样转发到这里。
- **IOP 侧按 LSN**：`PS2I/src/emulator/imports/iop_cdvd.cpp` 的 `sceCdRead`（case 6）→ `readSectors(lsn, sectors, dst)`，`sceCdSearchFile`（case 10）→ `searchFile`；`PS2I/src/disc_source.cpp` 的 `ImageDisc` / `ExtractedDisc` 提供 `readSectors` / `findFile`。smpd 用绝对 LSN 流式读 `GODOFWAR.TOC`（24 字节条目：`name[12]` + part + size + PAK 内扇区偏移）与 `PART1/2.PAK`，**不按路径**。所以「按路径覆盖」无法覆盖 PAK 内的 WAD；这类资源要走离线 TOC 重指（`prepare.py:225-240` 把翻译文本写成 `TR_<name>` 追加到盘尾并重指 TOC 条目），或在 `DiscSource::readSectors` 做扇区重映射。

`iop_ioman.cpp` 只有 `AddDrv` / `DelDrv`（ordinal 20/21），**不是**文件 I/O 挂钩点；`iop_imports.cpp` 是 import/export 表链接，也与 VFS 无关。这两个名字很容易被误当成注入点，特此标注。

**启动配置** [实证]：`PS2R/src/main.cpp:150-189` 只在 **`argc >= 2`（有显式 ELF 参数）时完全不读** `gow-native.boot`；无参数双击 runner 时才从 `argv[0]` 同目录读它。格式：

```
GOW_NATIVE_BOOT_V1
<绝对路径的 ELF>
GOW_VU1N_X64=1
PS2X_GS_WORKER=1
...
```

首行必须是魔数，第二行必须是绝对路径且文件存在，之后每行 `KEY=VALUE`，**只接受 `TOBIICHI_` / `PS2X_` / `GOW_` 三种前缀**（`:179`），Windows 用 `_wputenv_s`。写入者是 `modules/game.ps1:216-221`（仅当文件不存在时写默认），launcher 会话会用所选盘与设置覆盖它。它是机器相关文件，`AGENTS.md:374` 明确「**Never package this machine-specific profile**」。

**运行时参数** [实证]：`PS2R/include/runtime/gow_ajustes_vivo.h` 是 49 行的 header-only `inline std::atomic<>` 集合（`fxaa` / `nitido` / `nitidez` / `aniso` / `estirar` / `mostrarFps` / `copiarSave`），`cargar()` 用函数内 `static const bool` 保证**只读一次**环境变量，之后 F1 菜单改的是 atomic，仅本会话有效、不写回 launcher。消费者是 `gs_host_present.cpp:400-440`、`gs_hw_backend.cpp:2897-2900`、`gow_trucos.cpp:616-721`。

**存档** [实证]：`PS2I/src/emulator/iop_emulator.cpp:134-145` 的 path provider 读 `GOW_MC0` / `GOW_MC1`（`=0` 表示空槽），否则用 ELF 同目录 `Mcd001.ps2`。`docs/saves.md:8-28` 说明静态重编译**没有 savestate**，卡是 8,650,752 字节的 PCSX2 `.ps2` 镜像，运行中常驻内存，**不能热替换**；F1 > Saves 的 `snapshotCard` 写 `GOW_SAVES_DIR/<yyyyMMdd-HHmmss>/{Mcd001.ps2, save.json}`。

**语言** [实证]：`prepare.py:295-312` 写 `data/<id>/languages.json`（`{game, title, recompile_elf, languages:[{language,label,edition,quality,elf}]}`，`quality = original|full|standalone`）。消费者不是运行时 C++，而是 launcher 与 `recompile.py` / `linux.py`。**选择结果决定 ELF 路径，ELF 所在目录即 `cdRoot`**，从而一起决定 `.disc_layout` / TOC / PAK、电影、`mc0` 与文本语言变体。`TOBIICHI_IDIOMA` 只控 F1/作弊菜单 UI 语言，不是游戏文本语言。

### 2.5 已实现但不作为主线：xdelta stage

`modules/runtime.ps1:56-76` [实证] 提供了 `-Stages xdelta -Xdelta <patch> -Discs <base ISO>`：调用 `python -I tools/disc/vcdiff.py apply`，先写 `data/mods/isos/<name>.iso.partial`，逐窗口 `zlib.adler32` 校验（首窗不符报 `the patch was made for a different ISO`），全部通过才 `Move-Item` 成正式 `.iso`；失败删 partial。`tools/disc/vcdiff.py` 是 132 行的 RFC 3284 解码器（xdelta3 扩展：app header、adler32、默认码表），`windows()` / `apply()` / `info` 三个入口。

`AGENTS.md:302-303` 明确：「**Never ship third-party patches or ISOs**」。`data/mods/` 当前**不存在**，只在 stage 运行时由 `:65-67` 创建。

本方案的处理：`xdelta` 保留为「玩家自有镜像 → 只读基线」的**来源类能力**，但它写的是 ISO，与「不改光盘」的主线冲突，因此：

- 默认禁用，且 Mod 包里不得声明 `source_patch` 之外的 ISO 写入能力；
- 若启用，产物必须落在 `data/mods/isos/`（gitignore 的生成数据），且后续仍须经 `identify.py` / `prepare.py` 的完整身份校验；
- 管理器**不**把这一步纳入「启用 Mod」的常规事务，而是列为「导入来源」的一次性离线操作，单独记录 base/delta/output 哈希；
- 第 24 章会把它列为最高风险能力，要求二次确认与磁盘空间预检。

### 2.6 仅规划 / 仅文档（不要当成可用接口）

| 项 | 出处 | 状态 |
|---|---|---|
| Roadmap「Mods and texture packs」 | `README.md:304`、`:33` | [规划]，且「texture replacement is designed, not implemented」已过时 |
| 通用 Mod 管理器 | `docs/input-accessibility.md:61-62` | 明确「not a claim that a general mod manager is implemented」 |
| `pack.toml` manifest、PCSX2 导入映射、BC7 DDS、`GOW_TEX_PRELOAD`、F1 集成、dump 流程 | `texture-replacement.md:8, 168-175` | [规划]，且与 patch 52 冲突 |
| Phase 4「ISO mods and texture packs」、补丁 42-43 | `docs/research/roadmap-2026-10-27.md:17, 408, 531` | [规划]，编号已被占用 |
| 60fps 目标 | `docs/research/roteiro-60fps.pt-BR.md`、`AGENTS.md:115` | [规划]，**不存在**名为 60fps 的补丁 |
| `GSSwBackend` 软件光栅器 | `docs/RENDER-PIPELINE-HANDOFF-2026-11-04.zh-CN.md:143` | [缺失]，补丁链缺 49，工作树无此类 |
| `PS2X_GS_ESCALA` / `PS2X_GS_HW` / `PS2X_GS_NITIDO` / `PS2X_GS_ESCALA_DINAMICA` / `PS2X_GS_SHADER_CACHE_DIR` | Tobiichi `lanzador.cpp:429-434` 仍设置 | **死变量**：`ps2xRuntime` 工作树无任何 `getenv` 读者；`AGENTS.md:144-145` 说主 launcher 已删 |
| `launcher → Graphics → Texture pack` 设 `GOW_TEXTURE_PACK` | `engine/README.md:67`、葡语研究文档 | 主 launcher 二进制有；checked-in `engine/runtime/launcher/src/lanzador.cpp` **无**该设置 |
| 运行时有 `R_PERM.WAD` / `R_SHELL.WAD` 读取函数 | — | [缺失]，只有离线 `identify.py` / `prepare.py` 处理它们 |
| savestate | `docs/saves.md:8-13` | 明确不存在 |
| Definitive Edition 2.0 `.xdelta`（`host0:/mod/%s.wad`） | 葡语研究文档 §2 | 研究记录，**未支持**；`identify.py` 拒绝该 ISO |

### 2.7 本工作副本的特殊性（必须写进风险登记）

调研确认，用户当前这份 `C:/Users/nb/Desktop/1` 是一个**发布包式裁剪副本**，不是完整开发仓库：

- `launcher/` 下只有 `bin/` 与 `bin-backup-20261104/`，**没有** `CMakeLists.txt` / `src/` / `qml/` / `pruebas/`；但 `launcher/bin/gow-launcher.exe`（5,112,126 字节，2026-11-04 22:12）内嵌 23 个 QML 资源名，可反证完整仓库里那套 UI 确实存在并被编译进去了。
- `engine/runtime/launcher/` 是**另一套** Tobiichi 上游源码（TabBar 六页、西语命名），不是 `AGENTS.md` 描述的 sidebar + `pagina` 那套，不能拿它当主 launcher 源码改。
- `installer/setup.cpp` 与 `installer/` 目录 [缺失]，但 `modules/distribution.ps1:88-99` 引用它。
- `data/` 只有 `build-root.txt`（内容 `C:\gow-build-a2b263b9`）、0 字节 `pipeline.lock`、`_tmp/` 历史快照、`_tools/` 便携工具、`gow1/logs/` 四个 pipeline json 与 `regional-builds.json`；`discs/`、`languages.json`、`mc0/`、`recomp/`、`mods/` **均不存在**（都是按需生成物）。
- 仓库根**不是 git 仓库**，也没有根 `.gitignore`；`AGENTS.md:57-58` 说的「`data/` git-ignored」在此副本里没有对应规则文件。
- `engine/runtime/` 存在且是独立 clone，但**补丁链缺 49、`GSSwBackend` 不存在**；`docs/RENDER-PIPELINE-HANDOFF-2026-11-04.zh-CN.md:143` 警告「不要用 01–58 重放补丁复原工作树」。

由此产生的实施前提：**第 20 章的 launcher 集成、第 22 章的 QML 测试，都需要先取得/恢复完整仓库的 `launcher/` 源码**，否则 `tools/test/{disc-import-ui,regional-play-ui,qte-controls,loading-progress}.py` 会在 `shutil.copytree(root/'launcher/qml', ...)` 处直接 `FileNotFoundError`。本方案把这些步骤写成前置条件（P0），而不是假装它们能跑。

### 2.8 能力矩阵总表

| 能力 | 现状 | 管理器要做的 |
|---|---|---|
| 纹理替换（PCSX2 格式） | 已实现（patch 52） | 多包合并成一个目录、预算分配、命中统计、禁用时完全不设 `GOW_TEXTURE_PACK` |
| 按路径文件覆盖 | 有中心函数 `resolveHostPath`，无覆盖表 | 新增一张启动期建好的只读映射表 + 校验 |
| PAK 内资源覆盖 | 无按路径入口 | 离线 TOC 重指（复用 `prepare.py` 的 `TR_*` 思路），列为高级能力 |
| 代码/函数替换 | 已实现 `replaceFunction` + 装饰链范式 | 新增 Mod 声明的地址表、优先级链、ABI 校验、编译期 patch 生成 |
| 启动参数 | 已实现 env + `gow-native.boot` | 前缀白名单、键冲突检测、按 profile 合成 |
| 运行时参数热更 | `gow_ajustes_vivo.h`（只读一次 env） | 归入启动期；不承诺运行中改 env 生效 |
| 存档 | 8 MB 卡镜像 | 按 profile 指定 `GOW_MC0`，启动前切换、禁止热替换 |
| FMV / 音频 / 文本 | 有零散入口（`GOW_MOVIE_OVERRIDE`、VAG 累积、离线 TOC） | 归入 VFS 覆盖 / 函数覆盖 / 离线重指三类，见 18.6 |
| ISO 补丁 | xdelta stage 已实现 | 降级为「来源导入」，默认禁用、不进常规事务 |
| 通用 Mod 管理器 | **没有** | 本方案全部内容 |

---

## 第 3 章　不可违反的硬约束

第 0.3 的五条铁律是价值判断，这一章给出它们的**代码依据**与「违反时会发生什么」，并把每条约束映射到后续章节的设计决策。

### 3.1 `fetch` 对 runtime 工作树的管控

`modules/runtime.ps1:12-17` 先 `git fetch --quiet origin` + `git checkout --quiet $runtimeCommit`，有本地改动即 throw；`:26-33` 用临时 `GIT_INDEX_FILE` 做只读前缀树推演，逐个 `git -C $rt apply --cached <patch>` 累积 `trees[]`，任一失败报 `patch X does not apply to runtime commit <commit>`；`:47` 用 `[array]::IndexOf($trees, $current)` 求已应用前缀；`:49-53` 对剩余补丁执行真实 `git apply`。注释解释为何不能用逐补丁反向检查：01 与 07 都改 `ReleaseMode.cmake`，会误判。

`tools/pipeline/patches.ps1` 还明确排除 `git apply --3way`：「most patch files have no `index` lines」，改用 `start | export | drop` 把补丁栈转成 git commits（worktree `engine/runtime-patches`、分支 `gow-patches`），`-Onto` 触发 rebase 做三方合并；`export` 会校验名字按 `Ordinal` 有序并回写 `runtime.toml` 的 commit。

补丁链现状 [实证]：72 个 `*.patch`，命名 `NN-<slug>.patch`，有 `29a`–`29f` 字母后缀、**两个 52 号**（`52-gs-texture-packs` 与 `52-renderer-failure-message`）、**缺 49**、最大 66。排序由 `modules/common.ps1:Get-RuntimePatches()` 用 `[StringComparer]::Ordinal` 保证（Windows PowerShell 5.1 的标点排序不同）。补丁头部是自由文本（做什么/为什么/测量结果），`git apply` 会忽略；`patches.ps1` 用 `--cleanup=verbatim` 保留以 `#` 开头的头部行。

**违反后果**：手改 `engine/runtime/` → 下次 `fetch` 报 `engine/runtime differs from the patch chain`，或直接被 checkout 冲掉；新增一个编号重复的 patch → 前缀树推演失败，整条链停摆。

**设计映射**：L1 注入（第 18.5 节）只能「追加链尾新编号」，且编号由管理器统一分配（取当前最大 +1 并避开重复/字母后缀），补丁文本由模板生成、头部写明来源 Mod 与 plan id；绝不编辑既有补丁。

### 3.2 内容寻址、事务发布与 ownership

`tools/pipeline/recompile.py` 的 docstring 就是设计原则：「Content-addressed EE generation and ownership-aware synchronization」「a successful generation is published as a directory transaction; failed generation leaves the last usable output intact. **Digests, not timestamps, decide reuse.**」

- `generate()` 的 key = `sha256(json.dumps(dict(files={elf, compiler, function_map, template, profile, __file__, PS2X_CODEGEN_FUNCS}, environment={PS2X_* + PS2X_CODEGEN}), sort_keys=True))`；命中则打印 `@@status recompiler inputs and output hashes unchanged; generation skipped`。
- `validate_report()` 用正则抓 decode failures / Unhandled instructions / correctness-critical fallbacks / Warnings/errors 四个计数，必须唯一且为 0，且无 `^\s*\[error\]`。
- `publish()` 要求 pending/output 是普通同级目录（拒 symlink/junction），`files` 必须含 `register_functions.cpp` 与 `ps2_recompiled_functions.h`；`retired = old.previousOutputs | previous` 跨多次 recomp 保留迁移所有权；`output → output.previous → pending → output → 删 backup`，失败回滚。
- `sync_owned()`（`:178-205`）删除前先校验 `digest(path) != old[name]` → `Refusing to remove modified generated file`，注释「Never delete a hand-edited or foreign file」。写入用 `<name>.gow-tmp` + `replace_file`（Windows `winerror` 5/32/33 六次指数退避）。
- `synchronize()` 把 `.cpp → src/runner`、`.h → include` 两组同步到 runtime，并把 `profile['runtime']['overrides']` 里的 `.cpp` 并入 sources；state 文件 `sync.cpp.json` / `sync.h.json`。
- `PS2R/.../src/runner/` 的 CMakeLists 用 `file(GLOB ... CONFIGURE_DEPENDS)` 自动收编新 `.cpp`，`add_executable(ps2EntryRunner ${RUNNER_SRC_FILES})`。

**违反后果**：手改 `data/<game>/recomp/out/` → `inventory(out) != state['outputs']`，sync 直接失败；在 `src/runner/` 放同名文件 → 被 `desired` 覆盖；放异名文件 → 不会被删但会被 GLOB 编进去（可能引发难以解释的行为）。

**设计映射**：第 16 章的包发布、第 19 章的事务与 WAL，**直接照抄 `publish()` / `atomic_json()` / `replace_file()` 的模式**（temp → replace → 失败回滚），不另造一套。第 8 章把 Mod 数据全部放 `data/mods/`，绝不混入 `data/<game>/recomp/` 或 `engine/runtime/`。

### 3.3 帧循环与 GL 上下文归属

- `PS2R/src/lib/gs/gpu/gs_texture_store.h:7`：「Single-threaded: it is only used from the thread that drives GSHwBackend (the GS worker).」
- `PS2R/src/lib/gs/gpu/gs_gl.cpp:420-432`：`Context::CreateWorker()` 用 `wglCreateContextAttribsARB` 建共享上下文，`MakeWorkerCurrent` 切 `wglMakeCurrent`。
- `PS2R/src/lib/gs/gs_stage.cpp:17-25`（patch 44）：单生产者单消费者字节环，船上战斗约 240k packets/s；旧 mutex+vector 方案让 worker 每包取锁，占约 15% 时间。
- patch 52 自身注释：`// Uploaded here (the render thread owns the GL context)`、`// once per frame on the render thread: upload what the worker decoded`。
- `texture-replacement.md:100-111`（设计文档，但陈述的是事实）：有界队列丢最旧并计数，「so the GS worker never waits on the disk」；启动时只列目录名建 map，「**No disk reads in the frame loop after that**」。

**违反后果**：在 `resolveHostPath` 里读 TOML / 做 `std::filesystem::exists` 之外的事情 → 每次文件打开都多一次磁盘访问；在 `replaceFunction` wrapper 里做日志写文件 → 每帧抖动；在 GS worker 调 GL → 未定义行为或崩溃。

**设计映射**：所有 Mod 决策在 **Planner 阶段一次性算完**，产物是一份内存里的 `plan.json`；运行时只读三张预建好的内存表（VFS 映射、函数地址表、纹理目录索引）。第 23 章会给出一条静态检查规则：`resolveHostPath` 钩子内只允许 `unordered_map::find` 与一次 `fopen`，出现 `ifstream`/`toml`/`sleep`/`mutex` 即判失败。

### 3.4 身份校验链

| 校验点 | 位置 | 比对内容 | 失败信息 |
|---|---|---|---|
| 光盘识别 | `tools/disc/identify.py:114-163` | BOOT2 ELF 名、`known_crc` / `known_text_sha1`、`.text SHA-1` | `unknown game` / `region_not_ported` / `the executable is not the game code the port was built for` |
| 代码生成 | `recompile.py generate():133-140` | `recompile_elf` 名 + `.text SHA-1` | `Executable does not match this game profile; a regional function map and runtime port are required…` |
| 编译报告 | `recompile.py validate_report():76-90` | 四类错误计数为 0 | `RuntimeError` + 「Previous generated code was preserved」 |
| 翻译盘 | `prepare.py translated_elf():171-178` | ELF 长度/节表、`.text` | `the translated executable has another layout` / `the translation changes the game code` |
| 区域注册 | `register_region.py:29-55` | `elf.name` / `text_sha1` / `pcsx2_crc`、CMake source、`gow_overrides.cpp` 内容、owner、data 不复用 | `Regional ELF identity mismatch` / `A regional ELF must never use the USA build` |
| 发布身份 | `game.ps1:Get-ProfileIdentity()` + `distribution.ps1:65-73` | runtime.toml SHA-256 + 补丁集 SHA-256 + `games/<id>` SHA-256 + ELF `.text` SHA-256 | manifest 不匹配则 throw |

**违反后果**：任何一个字段不一致而管理器仍照常加载 Mod，最可能的症状不是「Mod 没生效」，而是 `replaceFunction` 打到错误的 guest 地址 → 随机崩溃、存档损坏、VU1 校验失败。

**设计映射**：第 11 章的七元组指纹与三档兼容策略、第 17.2 节的「不匹配即拒绝 + 差异报告」、第 22 章的「指纹错配」测试用例。

### 3.5 发行与版权边界

`modules/distribution.ps1:59` 的 package 白名单**精确 10 项**：

```powershell
foreach ($item in @('README.md','README.pt-BR.md','CREDITS.md','LICENSE','AGENTS.md',
                    'CLAUDE.md','build.cmd','docs','games','tools')) { ... }
```

再加 `engine/runtime.toml`、`engine/README.md`、`engine/patches/`，以及 `launcher/build-clang/deploy` 里的编译产物；**不含** `data/`、不含 `launcher/` 源码、不含 `engine/runtime/`。`tools/pipeline/update.ps1:76` 用 `robocopy /XD data /XD engine\runtime` 保证更新不覆盖用户数据与运行时检出。`CREDITS.md:30-33` 与 `AGENTS.md:299-303, 353, 367, 374` 反复强调：ISO、生成 C++、录制微码、纹理包、dump、截图、第三方补丁、PGO profdata、`gow-native.boot` 一律不得提交或打包。

**设计映射**：第 8 章把所有 Mod 数据放 `data/mods/`（生成数据）；第 13 章规定 Mod 包只能含声明与差分；第 24 章规定会话报告的白名单（可导出开关状态与命中计数，**不可**导出包路径、ISO 路径、完整环境 dump、截图）。`docs/input-accessibility.md:56-62` 已给出一个可参照的先例：纹理包开关只持久化 `usarPacoteTexturas` 与 `pacoteTexturas`，且「目录路径因隐私不进会话报告」。

### 3.6 已知陷阱清单（实现时逐条对照）

| # | 陷阱 | 后果 | 规避 |
|---|---|---|---|
| 1 | 用 01–58 重放补丁复原工作树 | 缺 49、`GSSwBackend` 不存在，得到错误运行时 | 只用当前工作树；`HANDOFF:143` 明确禁止 |
| 2 | 改 ELF 文件名 | override 按 `SCUS_973.99` 匹配，整套失效 | 保持原名；区域版用独立构建 |
| 3 | 认为 `PS2X_GS_ESCALA` 等变量有效 | 无 reader，是死变量 | 只用附录 F 里标「有 reader」的变量 |
| 4 | 在有 ELF 参数的启动里写 `gow-native.boot` | `main.cpp:150` 直接跳过读取 | 由 launcher 自己设环境变量，不依赖 boot |
| 5 | 运行中替换 `Mcd001.ps2` | 卡在内存，热替换无效且可能损坏 | 只在启动前用 `GOW_MC0` 指定 |
| 6 | 运行时改环境变量期待生效 | `gow_vivo::cargar()` 只读一次 | 参数 Mod 归 L2 |
| 7 | 以为 `-Stages` 按传参顺序执行 | 各 stage 执行体写在模块顶部 `if`，按**模块加载顺序**执行 | 不要新增 stage 依赖顺序的技巧 |
| 8 | 把 `qt` / `distribution` / `runtime` / `game` 当 stage 名 | 它们是模块文件名，不在 `$allowedStages` 里 | 只允许 17 个：`tools,fetch,xdelta,discs,vu1disc,configure,recomp,sync,build,pgo,tune,optimize,native,verify,launcher,package,installer` |
| 9 | 在 `launcher/qml/` 缺失的副本上跑 UI 测试 | 4 个测试 `copytree` 直接 FileNotFoundError | P0 先恢复源码 |
| 10 | 把补丁编号写成重复或字母后缀 | Ordinal 排序/前缀树推演失败 | 由管理器分配最大+1 的纯数字编号 |
| 11 | 打包纹理 PNG / ISO / WAD | 违反 `CREDITS.md` 与白名单 | 只发 `mod.toml` + 补丁/脚本 |
| 12 | 用 `git apply --3way` 管理补丁栈 | 多数补丁无 `index` 行 | 用 `patches.ps1 start/export/drop` |

### 3.7 约束 → 设计决策映射表

| 约束 | 来源 | 决策 | 章节 |
|---|---|---|---|
| runtime 被 fetch 管控 | `runtime.ps1:12-53` | L1 只追加链尾 patch；L3 用 `replaceFunction` 免重编译 | 5.2 / 18.5 |
| 生成物有 ownership | `recompile.py:178-225` | Mod 数据独立放 `data/mods/`，不碰 `recomp/out` 与 `src/runner` | 8.2 / 16.2 |
| 帧循环敏感 | `gs_stage.cpp`、`gs_texture_store.h:7` | 规划期算完，运行时只读内存表 | 6.3 / 23.2 |
| 身份强校验 | `identify.py` 等六处 | 七元组指纹 + 三档兼容 + 差异报告 | 11 / 17.2 |
| 发行白名单 | `distribution.ps1:59` | Mod 包只含声明；报告导出白名单 | 13 / 21.3 / 24 |
| 补丁链有序且缺号 | `common.ps1:33-39` | 编号集中分配、记录 `patchChainHash` | 11.2 / 18.5 |
| 无 savestate、卡在内存 | `docs/saves.md` | 存档 Mod = 启动前指定卡镜像 | 13.6 / 18.6 |
| 两层 VFS | `ps2_vfs.cpp` / `disc_source.cpp` | 覆盖模型分「EE 路径」与「LSN 重指」两类 | 13.2 / 18.2 |

---

# 卷 II　总体架构

## 第 4 章　设计目标与非目标

### 4.1 功能目标

按优先级排列，前四条是 P0 必须，后四条是 P3+ 增强：

1. **可安装**：从本地目录 / zip 导入一个 Mod 包，校验完整性与声明合法性，落到 `data/mods/`，不改动仓库内任何受版本管理的文件。
2. **可选择**：为每个「profile」勾选一组 Mod，支持启用/禁用、排序、优先级，改动立即体现在下一次启动，不需要重新构建游戏。
3. **可判定**：在启用前明确告知「这个 Mod 能不能用于当前这份二进制」，不匹配时给出逐字段差异，不静默降级。
4. **可撤退**：任何启用操作都是事务；失败、崩溃、中途取消都能回到操作前的状态；「禁用全部 Mod」必须与「从未装过 Mod」在行为上字节等价。
5. **可诊断**：每次启动产出 `mod-report.json`，记录生效的 plan、每个 Mod 的命中统计、VFS 覆盖次数、纹理包 hits/evictions，以及崩溃时的最小复现信息。
6. **可协作**：Mod 包可声明依赖、冲突、加载顺序；多个 Mod 抢同一资源时有确定性结果和用户可读的冲突报告。
7. **可演进**：新增一种 Mod 类型只需加一个 `PayloadHandler` 实现，不改 Planner / Applier 主流程。
8. **可移植**：Mod 包不含本机绝对路径、不含游戏衍生数据，可在同指纹的另一台机器上复现。

### 4.2 非目标（明确不做）

| 不做 | 原因 |
|---|---|
| 在线 Mod 仓库、账号、云同步 | 工程无后端，`CREDITS.md` 要求用户自备游戏；引入网络会扩大供应链面 |
| 自动下载/更新 Mod | 同上；且 `AGENTS.md:123-124` 明确「never add … automatic uploads」 |
| Mod 包内嵌游戏资源（PNG/WAD/FMV/ISO） | 版权与白名单（3.5） |
| 运行时动态加载任意 DLL / 脚本 | 原生进程内执行第三方机器码风险过高；只接受声明式配置与经过编译的宿主代码 |
| 修改 `games/<id>/game.toml` 或 `engine/runtime.toml` | 两者是工程真相源，改了会触发重新生成/换基线 |
| 通用跨游戏框架 | 深度绑定 `gow1` 的 ELF 名、funcmap、补丁链；通用化的代价见 7.3 |
| 游戏内 Mod 菜单（F1 页） | `gow_ajustes_vivo.h` 只读一次 env，且 F1 菜单属于 runtime 补丁；UI 放 launcher 更稳 |
| 存档编辑器 | 已有 Saves 页（`AGENTS.md:171`）；本方案只做「启动前选哪张卡」 |

### 4.3 验收口径（先写死，避免后期扯皮）

- **A1 零影响**：未启用任何 Mod 时，管理器不设置任何 `GOW_*/PS2X_*/TOBIICHI_*` 变量、不写 `gow-native.boot`、不建 VFS 覆盖表、不追加补丁链；`build.cmd -Stages verify` 结果与基线一致。
- **A2 可复现**：同一份 `state.json` + 同一指纹，两次 `plan` 产出的 `plan.json` 逐字节相同（除时间戳字段）。
- **A3 可回滚**：`apply` 过程中任意一步失败，`rollback` 后 `data/mods/` 树与 `state.json` 的 SHA-256 与操作前一致。
- **A4 帧率**：启用 1 个纹理包 + 3 个 VFS 覆盖 + 1 个函数装饰后，船上战斗 100 秒会话的 guest FPS 与基线差在 run-to-run 噪声内（对照 patch 52 的实测口径）。
- **A5 帧循环零 IO**：静态检查 + `GOW_PERF_DIAG` 采样，确认 `resolveHostPath` 钩子内无磁盘访问。
- **A6 合规**：`data/_package/gow-native-pc-windows.zip` 中不含任何 Mod 资源、ISO、生成 C++ 或 `gow-native.boot`。

## 第 5 章　三层注入模型

### 5.1 为什么必须是三层

1.4 节说过，工程有**四个时刻**：生成期（recompile）、构建期（build）、启动期（launcher）、运行期（loadELF 之后）。把它们硬压成一层会出现三种典型失败：

- 只做「运行时 VFS」：无法覆盖 GS/SPU2 的 C++ 行为，也无法新增宿主函数；
- 只做「编译期 patch」：装一个画质档要重编译几十分钟，且无法按 profile 快速切换；
- 只做「环境变量」：无法做文件级覆盖，也无法处理多个 Mod 抢同一路径。

三层模型的划分依据是**「改动生效所需的最小代价」**，而不是技术偏好：能靠一次启动解决的，绝不动二进制；必须改 C++ 的，才走重编译。

### 5.2 三层对照

| | L1 编译期 | L2 启动期 | L3 运行时 |
|---|---|---|---|
| 触发 | 明确点击「应用并重建」，或 `plan` 检测到需要 L1 | 每次点「开始游戏」 | 进程初始化（`loadELF` 之后） |
| 输入 | `mod.toml` 的 `source_patch` / `function_override` 编译型 | `env`、`boot`、`texture_pack`、`vfs_override`（路径表）、`save` | 由 L2 生成的内存表 + 已编译进 runner 的钩子 |
| 产物 | 新的 `engine/patches/NN-*.patch`；必要时 `runtime.overrides` 追加 | 环境变量集合、合成后的纹理包目录、VFS 覆盖表文件、启动命令 | 三层表被 C++ 读入 |
| 是否需重建 | **是**（`fetch,configure,recomp,sync,build` 或其子集） | 否 | 否 |
| 是否可即时开关 | 否 | 是 | 是（下次启动） |
| 失败代价 | 高（构建失败、产物回退） | 低（改回 env 即可） | 中（可能崩溃，需诊断） |
| 指纹影响 | 改 `patchChainHash`，**所有 Mod 需重新校验** | 不改指纹 | 不改指纹 |
| 主要风险 | 补丁冲突、编号重复、链断裂 | 环境变量键抢占、路径穿越 | 地址错位、帧循环 IO、ABI 违规 |

**关键设计决策**：L1 与 L2/L3 之间有一道**明确的隔离**。任何含 `source_patch` 的 Mod 被启用时，Planner 会把 plan 标为 `requires_rebuild=true`，Launch Bridge 禁止直接「开始游戏」，而是提示先执行重建并重新计算指纹。这避免了「用户以为启用了、其实补丁没进二进制」的静默失败。

### 5.3 三层如何协同：一个完整例子

假设玩家勾选三个 Mod：`HD-UI`（纹理包）、`Alt-Movie`（FMV 换片）、`No-Blur`（改一个 guest 函数）。

```
L2  Planner 合成：
      GOW_TEXTURE_PACK = data/mods/.staging/<planId>/textures
      GOW_TEXTURE_PACK_MB = 768
      GOW_MOVIE_OVERRIDE = "OPENING_ALT"        （已有 override 支持）
      VFS 表：{}（本例无文件覆盖）
L3  进程启动后：
      TexturePack::open() 扫 staging 目录 → worker 异步解码 → render 线程上传
      applyGowOverrides() 读到 GOW_MOVIE_OVERRIDE → 替换 0x00188CA0
      No-Blur 若声明 function_override：
          在 gowIntegracionInstalar 之后按优先级串装饰链
L1  本例不需要；若 No-Blur 改为「新增一个 C++ 宿主函数」，
      则生成 67-no-blur.patch，标记 requires_rebuild，走重建流程
```

注意 `Alt-Movie` 走的是**已实现**的 `GOW_MOVIE_OVERRIDE`（`gow_overrides.cpp:1115-1136` 的 `movieOverrideList()`，名字 ≤31 字符），不需要新代码。这正是「先盘点现有能力」的价值：四类 Mod 里有相当一部分可以直接映射到现成开关，第 18 章会给出完整映射表。

## 第 6 章　组件架构与数据流

### 6.1 组件图

```
┌──────────────────────────────────────────────────────────────────────┐
│ launcher (Qt 6 / QML)                                                 │
│   ModsPage.qml  ←→  ModsModel (QObject, Q_PROPERTY / Q_INVOKABLE)     │
│   pagina = 9（追加，不动 0..8）                                        │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ 进程内调用 / CLI 二选一
┌───────────────────────────▼──────────────────────────────────────────┐
│ Mod Manager Core（C++，静态库 gow_mods）                               │
│  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │ Registry   │ │ Fingerprint│ │ Planner  │ │ Applier (事务)       │  │
│  │ 包索引/元数据│ │ 七元组/哈希 │ │ 依赖/冲突 │ │ stage→commit→activate│
│  └─────┬──────┘ └─────┬──────┘ └────┬─────┘ └──────────┬─────────┘  │
│        │              │             │                   │             │
│  ┌─────▼──────────────▼─────────────▼───────────────────▼─────────┐  │
│  │ PayloadHandlers: Texture / Vfs / Function / Env / Patch / Save   │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│  ┌──────────────┐ ┌───────────▼──────────┐ ┌────────────────────┐   │
│  │ Validator    │ │ Journal / WAL        │ │ Diagnostics        │   │
│  └──────────────┘ └──────────────────────┘ └────────────────────┘   │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ 生成 plan.json / 覆盖表 / 纹理 staging 目录
┌───────────────────────────▼──────────────────────────────────────────┐
│ Launch Bridge                                                         │
│   env 合成 → gow-native.boot（可选）→ 启动 ps2EntryRunner.exe          │
│   与 modules/game.ps1 的 boot 写入、launcher 的 lanzador 启动路径对齐    │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│ ps2EntryRunner.exe（已由 patch 链注入 3 个只读钩子）                    │
│   PS2Vfs::resolveHostPath  → 查预建覆盖表                              │
│   PS2Runtime 装饰链        → 按 plan 装 function_override              │
│   TexturePack::open        → GOW_TEXTURE_PACK                          │
└──────────────────────────────────────────────────────────────────────┘
```

三个只读钩子由 L1 一次性加入（一个 `67-mod-hooks.patch`），之后**所有 Mod 都只改数据、不改 C++**。这是本方案的核心杠杆：把「每种 Mod 都要改运行时」压缩成「一次改运行时，之后无限扩展」。

### 6.2 组件职责与接口

**Registry**（`ModRegistry`）：扫描 `data/mods/packages/<id>@<version>/`，读 `mod.toml`，维护内存索引；负责包的增删与元数据查询。只读，不写用户状态。

```cpp
struct ModMeta {
    QString id, version, title;
    QVector<Capability> capabilities;   // 见第 12 章
    TargetSelector target;              // 见第 11 章
    QVector<QString> requires, conflicts, loadAfter;
    int priority = 100;
    QMap<QString, QString> payloadHashes;  // 相对路径 → SHA-256
};
class ModRegistry {
public:
    bool scan(const QDir& root, QString* err);
    QVector<ModMeta> all() const;
    std::optional<ModMeta> find(const QString& id, const QString& ver) const;
};
```

**Fingerprint**（`TargetFingerprint`）：采集当前安装身份，产出七元组与 `fingerprintId`（SHA-256）。只读 `games/<id>/game.toml`、`engine/runtime.toml`、`engine/patches/*.patch`、`data/build-root.txt`、`data/<id>/regional-builds.json`、所选 ELF 的 `.text`。接口：

```cpp
struct Fingerprint {
    QString gameId, edition, region;
    QString elfCrc, textSha1;
    QString runtimeCommit, patchChainHash, buildRoot;
    QString codegen;                 // classic | locals
    QString id() const;              // 规范化 JSON 的 SHA-256
};
Fingerprint collect(const QDir& root, const QString& elfPath, QString* err);
QString diff(const Fingerprint& a, const TargetSelector& want); // 逐字段差异，供 UI 展示
```

**Planner**：纯函数，`(Registry, Fingerprint, Profile) → Plan` 或 `PlanError`。不写文件、不启动进程、不接触网络。可独立做成 CLI `gow-mods plan`，便于测试与复现（A2）。

**Applier**：把 Plan 变成磁盘/环境变更，带 WAL。接口只有两个动作：

```cpp
enum class ApplyResult { Ok, NeedsRebuild, RolledBack };
ApplyResult apply(const Plan&, Journal&, QString* err);   // stage → commit → activate
bool rollback(const QString& planId, Journal&, QString* err);
```

**PayloadHandlers**：每种 payload 类型实现三个方法 `validate()` / `collect()` / `emit()`。`validate` 在导入时跑，`collect` 把资源键登记进冲突表，`emit` 生成 plan 中的具体条目。新增类型不动 Planner 主流程（目标 7）。

**Diagnostics**：写 `data/mods/reports/<session>/mod-report.json`，并在崩溃时导出「最小复现包」（只含 plan、指纹、启用的 Mod id/version 与命中计数，不含路径与资源）。

### 6.3 数据流：从勾选到进程启动

1. **采集**：`collect()` 读六处真相源，算 `fingerprintId`；若 `data/mods/fingerprint.json` 中记录的上次指纹不同，标记 `stale=true` 并在 UI 上提示「构建已变化，部分 Mod 需重新校验」。
2. **校验**：对每个启用的 Mod，Planner 调 `TargetSelector.match(fingerprint)`，得 `exact` / `code-compatible` / `incompatible`；`incompatible` 直接进错误报告，附 `diff()` 结果。
3. **建图**：按 `requires` / `loadAfter` / `conflicts` 建 DAG；环检测；缺失依赖报错。
4. **收键**：每个 Handler 的 `collect()` 登记资源键（纹理 hash、VFS guest 路径、guest 地址、env 键…）；同键多主时按 14.3 的确定性规则求解。
5. **求解**：产出线性 `order[]` 与 `overrides[]`（键 → 获胜 Mod），以及 `requires_rebuild` 标志。
6. **落计划**：写 `data/mods/plans/<planId>/plan.json`（原子），`planId` = 规范化 plan 内容 + 指纹 id 的 SHA-256 前 16 位。
7. **应用**：Applier 按 stage → commit → activate 三步执行；L2 产物包括合成纹理目录、VFS 覆盖表、env 集合；L1 产物是新 patch 文件（并触发重建提示）。
8. **启动**：Launch Bridge 用 env 集合启动 `ps2EntryRunner.exe <elf>`；**不依赖 `gow-native.boot`**（因为 `main.cpp:150` 在有 ELF 参数时会跳过它），避免踩 3.6 陷阱 #4。
9. **报告**：会话结束后收集纹理 `GOW_TEXTURE_PACK_STATS`、VFS 命中计数、override 命中计数，写 `mod-report.json`。

**关键性质**：第 1–6 步都是纯计算或只读，只有第 7 步写盘且可回滚；第 8 步不修改任何工程受管文件；第 9 步只写 `data/`。这就是为什么「禁用全部」能做到 A1。

## 第 7 章　技术选型论证

### 7.1 候选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. 纯 Python CLI（沿用 `tools/` 风格） | 与 `profile.py` / `recompile.py` / `vcdiff.py` 完全一致；`python -I` 可跑；无新依赖；测试最易写 | 与 Qt launcher 集成要跨进程；UI 要另做；C++ 侧钩子仍需单独写 | **作为 planner/validator CLI 保留** |
| B. C++ Core + Qt/QML UI | 与 launcher 同进程、同构建系统（`launcher` stage 已有 Qt 6.8.3）；`ModsModel` 可直接 `setContextProperty`；性能与类型安全最好 | 需要 `launcher/` 完整源码（当前副本缺失）；C++ 迭代慢 | **主体选它** |
| C. Electron / Tauri + Web UI | 界面现代、开发快 | 引入 Node/Rust/WebView 新依赖，与 `toolchains.json` 的六件便携工具冲突；发行包变大；与现有 Qt 二进制割裂 | 否决 |
| D. 全部塞进 `build.ps1` 新 stage | 复用 pipeline 协议与 `LoadingScreen` 进度 | `-Stages` 按模块加载顺序执行（3.6 #7）；stage 是构建概念，而 Mod 是启动概念；每次勾 Mod 都走 pipeline 太重 | 否决（仅 L1 重建借用 pipeline） |

### 7.2 推荐：混合双层

**C++ 静态库 `gow_mods` + Qt QML 页面 + 一个 Python CLI 作为可测试的纯核心镜像。**

- `gow_mods`（C++17，与 runtime 同工具链 llvm-mingw / clang）：Registry / Fingerprint / Planner / Applier / Handlers / Journal / Diagnostics。编进 `gow-launcher.exe`。
- `ModsPage.qml` + `ModsModel`（`QObject` + `Q_PROPERTY` + `Q_INVOKABLE` + signals），仿 `engine/runtime/launcher/src/main.cpp:94-95` 的 `engine.rootContext()->setContextProperty(...)` 注册。全仓没有 `qmlRegisterType` / `QAbstractListModel`，照抄 `setContextProperty` 是最小改动。
- `tools/mods/gow_mods_cli.py`：Python 版 Planner/Validator，与 C++ 版共用同一份 `plan.json` schema。用途：① `build.cmd -Stages verify` 里跑纯逻辑单测（不需 Qt、不需游戏数据）；② 无 UI 环境下的批处理；③ 作为 C++ 实现的「可执行规范」，两边对同一输入必须产出相同 plan（A2 的交叉校验）。

这个双层不是过度设计：工程已有 `tools/pipeline/profile.py` + `modules/context.ps1` 的「Python 读 profile → PowerShell 消费 JSON」先例，也已有 `recompile.py` 与 `build.ps1` 的双语言协作。沿用同样模式，学习成本最低。

**不引入新依赖**：TOML 用 C++ 侧已有的 `toml` 解析能力（runtime 依赖里已有）或 Python 侧 `tomllib`；哈希用 SHA-256（工程到处在用）；XXH3 只由 patch 52 在 runtime 内部使用，管理器不需要重新实现；JSON 用 Qt `QJsonDocument` / Python `json`；不引入数据库，状态就是原子写的 JSON 文件（照抄 `atomic_json()`）。

### 7.3 为什么不通用化

若做成跨游戏通用管理器，需要抽象掉：`game.toml` 的字段、ELF 名与 `.text SHA-1`、`replaceFunction` 的地址表、`GOW_*` 变量前缀、补丁链编号、`languages.json` 的 quality 概念……抽象完剩下的只是一个「包管理器 + 冲突求解器」，而这部分工程量里最值钱的（指纹、三层注入、事务）全都变成插件。对本工程而言，通用化带来的收益接近零，却会让每个校验都变成可选、每个错误都变成「由插件决定」。因此本方案**显式绑定到 `gow1` 及其区域变体**；若将来 `gow2`（`status="planned"`）落地，做法是把 `TargetSelector` 的 `gameId` 与 `runtime.overrides` 参数化，而不是重做架构。

### 7.4 与现有构建系统的边界

- **不新增 `-Stages` 值**。17 个 stage 一个不动；L1 重建复用 `build.cmd -Stages fetch,configure,recomp,sync,build`（或按实际需要的最小子集），由 Launch Bridge 调起并复用 `installer_backend` 已有的 `=== <step> ===` / `@@progress` / `@@status` 协议（`AGENTS.md:131-137`）。
- **不新增 `-Xdelta` 参数行为**。xdelta 保留原样。
- **不新增 pipeline 模块**。Mod 逻辑全部在 `tools/mods/` 与 `launcher/` 里，`tools/pipeline/` 只读不改。
- **`data/pipeline.lock` 要尊重**：若 L1 重建与 pipeline 并发，Applier 必须先尝试获取同一把锁（`PIPE/build.ps1:70-73` 用 `[IO.File]::Open(..., 'OpenOrCreate','ReadWrite','None')`），拿不到就排队，不并行写 `engine/patches/`。

## 第 8 章　目录布局与文件所有权

### 8.1 完整目录树

```
ROOT/
├── engine/patches/
│   ├── 01-…66-*.patch                  【工程受管，只读】
│   └── 67-mod-hooks.patch             【L1 一次性注入，由管理器生成，需纳入版本管理】
├── tools/mods/                        【新增，工程受管】
│   ├── modspec.md                     mod.toml 规范（本文档第 10 章的精简版）
│   ├── gow_mods_cli.py                Python CLI：validate / plan / verify-report
│   ├── fingerprint.py                 七元组采集
│   ├── handlers/                      texture / vfs / function / env / patch / save
│   └── tests/                         unittest，接进 verify.ps1
├── launcher/
│   ├── src/ModsModel.{h,cpp}          【新增】
│   ├── src/mods/                      【新增】C++ Core（或独立静态库）
│   ├── qml/ModsPage.qml               【新增】
│   ├── qml/Textos.js / idiomas/*.js   【改】新增文案键
│   ├── CMakeLists.txt                 【改】追加 QML + 源文件
│   └── src/main.cpp                   【改】一行 setContextProperty
└── data/mods/                         【生成数据，gitignore，永不打包】
    ├── packages/<id>@<version>/       导入后的只读包副本
    │   ├── mod.toml
    │   ├── payload/…
    │   └── .installed.json           安装时写入的哈希清单
    ├── profiles/<name>.toml           profile：启用的 Mod、排序、覆盖裁决
    ├── state.json                     当前激活的 planId、上次指纹、journal 指针
    ├── fingerprint.json               最近一次采集结果（含各输入哈希）
    ├── plans/<planId>/plan.json       确定性计划（只读，可存档复现）
    ├── staging/<planId>/
    │   ├── textures/                  合成后的 PCSX2 命名 PNG 目录（硬链接/符号链接）
    │   ├── vfs/<guest-path>           覆盖文件
    │   └── env.list                   启动期环境变量清单
    ├── hooks/vfs-overrides.tsv        L3 只读覆盖表（启动时一次性读入）
    ├── hooks/function-overrides.tsv   L3 地址→宿主函数名表
    ├── journal/<planId>.wal           事务日志
    ├── reports/<session>/mod-report.json
    └── isos/                           xdelta 产物（沿用现有 stage，默认禁用）
```

### 8.2 所有权规则（照抄 `sync_owned` 的精神）

| 区域 | 谁拥有 | 规则 |
|---|---|---|
| `engine/patches/*.patch` | 工程 + L1 管理器 | 既有补丁只读；管理器只追加新编号；追加前校验链完整性 |
| `games/`、`engine/runtime.toml`、`tools/pipeline/` | 工程 | **管理器永不写** |
| `engine/runtime/` | `fetch` stage | **管理器永不写**；只读其文件算哈希 |
| `data/<game>/recomp/`、`src/runner/` | `recompile.py` | **管理器永不写** |
| `data/mods/packages/` | 导入器 | 安装后只读；更新包 = 新版本目录 + 原子切换，不原地改 |
| `data/mods/staging/` | Applier | 每次 plan 全量重建；旧 staging 在 commit 成功后按 LRU 清理（保留最近 3 份） |
| `data/mods/plans/` | Planner | 只追加，不修改；内容寻址，同输入同文件名 |
| `data/mods/state.json`、`journal/` | Applier | 唯一可写状态，全部原子写 + WAL |
| `data/mods/reports/` | Diagnostics | 只追加；导出白名单见 21.3 |
| `gow-native.boot` | pipeline / launcher | 管理器**不写**（3.6 #4）；只通过 env 影响启动 |

**为什么 `staging/` 而不是原地覆盖**：`GOW_TEXTURE_PACK` 只接受**一个**目录，多个纹理 Mod 必须合成；合成若直接写进各自包目录，会把「包」变成「可变状态」，破坏哈希校验与回滚。staging 是 plan 的物化结果，天然具备「换 plan = 换目录」的原子性。Windows 上优先用硬链接（`CreateHardLink`）避免复制 PNG；跨卷时退化为复制，并在 `plan.json` 里记录 `linkMode` 以便诊断。

**为什么不把状态放进 `QSettings` / 注册表**：工程所有生成状态都在 `data/` 下的 JSON（`languages.json`、`regional-builds.json`、`.gow-recomp.json`），且 `update.ps1` 用 `/XD data` 保证升级不覆盖。沿用同一位置，备份/迁移/排障都只需拷贝一个目录。

---

# 卷 III　数据模型：Mod 包格式

## 第 9 章　设计原则

### 9.1 六条原则

**P1 声明式，不是可执行。** `mod.toml` 只描述「我要什么」，不含任何可执行脚本、不引用任意 DLL、不写绝对路径。所有行为由管理器的 PayloadHandler 解释。这条是供应链安全的地基：一个 Mod 包能做什么，读它的 `capabilities` 就一目了然。

**P2 一切皆有哈希。** 包内每个 payload 文件在 `mod.toml` 里登记 SHA-256；安装时重算，运行时可抽查；`plan.json` 记录所有输入哈希。工程里 `recompile.py` 的 `digest()`、`toolchains.json` 每项的 `sha`、`distribution.ps1` 的 manifest 都是同一套习惯。

**P3 身份先行。** 任何 Mod 在 `validate` 阶段就声明 `target`；不匹配时不进入 Planner，更不进入 Applier。「先试装看看会不会崩」在这个工程里代价太高。

**P4 确定性。** 相同输入必须产出逐字节相同的 `plan.json`：排序用显式键（不用文件系统遍历顺序）、时间戳不进 plan、哈希用规范化 JSON（`sort_keys=True`）。这条直接对应 A2。

**P5 只读包 + 可变 staging。** 包目录一旦安装即只读；所有可变状态在 `data/mods/` 下的独立区域。这样「卸载」= 删目录，「回滚」= 换 planId 指针，不需要记录逐文件逆操作（但 WAL 仍保留，见第 19 章）。

**P6 最小权限。** 每个 Mod 声明所需能力，能力有危险等级；高危能力需 UI 二次确认并写进会话报告。默认拒绝一切未声明行为。

### 9.2 一个 Mod 包的生命周期状态机

```
imported ──validate──▶ validated ──enable(profile)──▶ staged ──apply──▶ active
   │                      │                            │                  │
   └──(校验失败)▶ rejected └──(指纹不符)▶ incompatible  └──(失败)▶ rolled_back
                                                              │
active ──disable──▶ inactive ──(staging 保留 3 代)──▶ gc
active ──uninstall──▶ (删除 package 目录 + 从所有 profile 移除)
```

`active` 不是一个文件属性，而是 `state.json` 里指向某个 `planId` 的指针。判断「当前生效了什么」，只读 `state.json` + `plans/<planId>/plan.json` 两个文件即可，不需要扫全盘。

## 第 10 章　`mod.toml` 完整规范

### 10.1 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema` | int | 是 | 规范版本，当前 `1`；不认识的版本直接拒绝 |
| `id` | string | 是 | 全局唯一，`[a-z0-9][a-z0-9._-]{1,63}`，小写；建议 `作者.名称` |
| `version` | string | 是 | 语义化版本 `MAJOR.MINOR.PATCH`，可带 `+build`；同 id 多版本可共存 |
| `title` / `description` | string | 是 / 否 | UI 展示；`title` ≤ 80 字符 |
| `authors` | array[string] | 否 | 仅展示，不做身份验证 |
| `license` | string | 否 | SPDX id；声明但不校验 |
| `homepage` | string | 否 | 仅展示，管理器**不访问网络** |
| `target` | table | 是 | 目标选择器，见 11.3 |
| `capabilities` | array[string] | 是 | 见第 12 章；空数组非法 |
| `requires` | array[string] | 否 | `"id@>=1.2.0"` 形式，见 17.1 |
| `conflicts` | array[string] | 否 | 显式互斥的 id 或 id@range |
| `loadAfter` / `loadBefore` | array[string] | 否 | 顺序提示，不隐含依赖 |
| `priority` | int | 否 | 0–999，默认 100；同资源键时**数值大者胜** |
| `payload` | array[table] | 是 | 见 10.2；每项声明一类资源 |
| `settings` | table | 否 | 用户可配置项（枚举/布尔/整数），见 10.4 |
| `diagnostics` | table | 否 | 作者提供的排障提示、已知不兼容项 |

### 10.2 `[[payload]]` 通用字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `texture_pack` / `vfs_override` / `function_override` / `env` / `boot` / `source_patch` / `save` / `pak_remap` / `external_injector` |
| `path` | string | 包内相对目录；必须位于包根之内，禁止 `..`、绝对路径、符号链接 |
| `capability` | string | 必须与本项 `type` 对应的能力一致（见 12.1 映射表） |
| `files` | array[table] | 逐文件 `{path, sha256, size}`，可缺省但强烈建议；凡声明了 `sha256` 的必须匹配 |
| `options` | table | 类型专属参数，见第 13 章 |

**路径校验规则**（导入器强制执行，防穿越）：

```python
def safe_member(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ModError("E_PATH_TRAVERSAL", rel)
    if p.is_symlink() or p.is_absolute():
        raise ModError("E_UNSAFE_PATH", rel)
    return p
```

Windows 上还要额外拒绝 `\\?\`、UNC 路径、驱动器相对路径 `C:foo`、以及 `CON`/`NUL` 等保留设备名；解压 zip 前先遍历 `ZipInfo` 做一遍检查，再落盘。

### 10.3 完整示例（最小可用：一个画质参数档）

```toml
schema = 1
id = "acme.clean-look"
version = "1.0.0"
title = "Clean Look（关闭锐化与 FXAA）"
description = "通过启动期环境变量调整后处理；不改任何游戏文件。"
license = "CC0-1.0"
capabilities = ["env"]

[target]
game_id = "gow1"
compatibility = "code-compatible"
regions = ["usa", "asia", "europe", "japan"]
editions = ["original", "full", "standalone"]
runtime_commit = "any"
patch_chain = "any"

[[payload]]
type = "env"
capability = "env"
path = "."

  [[payload.options]]
  key = "GOW_SHARPEN"
  value = "0"
  strategy = "set"

  [[payload.options]]
  key = "TOBIICHI_FXAA"
  value = "0"
  strategy = "set"

  [[payload.options]]
  key = "GOW_ANISO"
  value = "4"
  strategy = "set_if_unset"

[settings]
# 允许玩家在 UI 上覆盖 GOW_ANISO 的值，范围 1..16
aniso = { kind = "int", default = 4, min = 1, max = 16, maps_to = "GOW_ANISO" }
```

注意 `GOW_SHARPEN` / `TOBIICHI_FXAA` / `GOW_ANISO` 都是 `gow_ajustes_vivo.h` 里**真实有 reader** 的变量（附录 F）。`strategy = set_if_unset` 用于「我不抢别人的设置」；`set` 用于「我明确要这个值」，抢占时按第 14 章求解。

### 10.4 `settings` 与用户覆盖

`settings` 的每一项声明 `kind`（`bool` / `int` / `enum`）、`default`、范围、`maps_to`（映射到哪个 `env` 键或 payload 选项）。用户覆盖存在 `profiles/<name>.toml`：

```toml
name = "daily"
enabled = ["acme.clean-look@1.0.0", "acme.hd-ui@2.1.0"]
order_override = ["acme.hd-ui@2.1.0", "acme.clean-look@1.0.0"]
[settings."acme.clean-look@1.0.0"]
aniso = 8
[resolutions]           # 用户对冲突的人工裁决，优先于自动求解
"texture:9a1c…-b3e2…-0000c1" = "acme.hd-ui@2.1.0"
```

`resolutions` 是 14.4 的落点：**自动求解给出建议，人工裁决可以覆盖，但裁决本身要记进 plan 并参与哈希**，否则就破坏了 P4 确定性。

### 10.5 包内禁止出现的内容

导入器遇到以下任一情况直接 `rejected`，并给出具体文件：

- 任何 `.iso` / `.bin` / `.img` / `.pak` / `.wad` / `.toc` / `.pss` / `.psw` / `.ps2` / `SCUS_*` / `SYSTEM.CNF` — 游戏衍生数据，违反 `CREDITS.md` 与 `AGENTS.md:299-303`；
- 任何可执行文件（`.exe` / `.dll` / `.so` / `.bat` / `.ps1` / `.py` / `.js`）— 管理器不执行第三方脚本；
- 任何 `*.png` 之外的图像资源用于非纹理用途；纹理 PNG 只允许出现在 `texture_pack` payload 内，且**必须是 Mod 作者自制/合法授权的替换图**，不得是原盘 dump；
- 绝对路径、UNC、`..`、符号链接、硬链接指向包外；
- `mod.toml` 里出现 `[target]` 之外的 `exec` / `command` / `script` / `url` 字段；
- 单包解压后总大小 > 512 MiB、单文件 > 64 MiB、文件数 > 20000（防压缩包炸弹）。

最后一条的资源例外：纹理包可能很大，但按铁律五，PNG 不能随 Mod 包分发——它们应由玩家本机用自己的工具生成，或由管理器从**玩家自己已有的** PCSX2 包目录「登记」进来（只登记路径，不复制进包）。第 16.1 节会区分「导入包」与「登记本机资源目录」两种入口。

## 第 11 章　目标指纹与兼容性判定

### 11.1 七元组（实际是九个字段）

指纹不是「游戏 CRC」，而是「这份二进制是怎么被造出来的」的完整描述：

| # | 字段 | 采集来源 | 变化意味着 |
|---|---|---|---|
| 1 | `gameId` | `game.toml:id` | 换了游戏，全部 Mod 失效 |
| 2 | `edition` | `languages.json` 所选条目的 `edition` / `quality` | 语言盘不同；`.text` 相同则代码级 Mod 仍可用 |
| 3 | `region` | `game.toml:[[regions]]` 或 `regional-builds.json` 的 `region`/`code` | 函数地址、frame probe、overrides 可能不同 |
| 4 | `elfCrc` | `tools/disc/discfs.py:pcsx2_crc()` | ELF 变了（哪怕 `.text` 没变） |
| 5 | `textSha1` | `tools/disc/discfs.py:text_sha1()` | **代码级 Mod 的生死线**；变了所有地址都可能错 |
| 6 | `runtimeCommit` | `engine/runtime.toml:commit` | 换了运行时，宿主符号可能变 |
| 7 | `patchChainHash` | `engine/patches/*.patch` 的 Ordinal 有序内容哈希 | 补丁链变了，钩子位置与行为可能变 |
| 8 | `buildRoot` | `data/build-root.txt` | 机器相关；只用于报告与诊断，**不参与兼容判定** |
| 9 | `codegen` | `build.ps1` 的 `$Codegen`（`classic` / `locals`） | 生成物布局不同，影响函数地址表 |

`fingerprintId = sha256(canonical_json(前 7 项 + codegen))`。`buildRoot` 与 `region` 里的本机路径绝不进 id（否则同一份二进制在两台机器上会被判成不同目标）。

### 11.2 `patchChainHash` 怎么算

照抄 `modules/common.ps1:Get-RuntimePatches()` 的排序语义，不能直接用文件系统顺序：

```python
def patch_chain_hash(root: Path) -> str:
    paths = sorted((root / "engine/patches").glob("*.patch"),
                   key=lambda p: p.name.encode("utf-8"))   # Ordinal ≈ 字节序
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode("utf-8")); h.update(b"\0")
        h.update(p.read_bytes());          h.update(b"\0")
    names = [p.name for p in paths]
    if len(set(n.split("-")[0] for n in names)) != len(names):
        # 允许 29a–29f 这类后缀，但纯数字编号重复要报警
        pass  # TODO(impl): 只检查纯数字编号是否重复
    return h.hexdigest()
```

Python 侧要注意：Windows PowerShell 5.1 的 `Ordinal` 是 UTF-16 码元序，与 UTF-8 字节序在 ASCII 文件名下等价；工程补丁名全为 ASCII + 连字符，所以上面的实现安全。若将来出现非 ASCII 补丁名，改为按 UTF-16LE 编码排序。

`Get-ProfileIdentity()` 已经用「补丁集 SHA-256」参与 PGO 身份；`distribution.ps1:65-73` 打包时校验 manifest。**Mod 管理器应直接复用同一个概念但独立计算**，并在 `fingerprint.json` 里同时记录 `patchChainHash` 与 `profileIdentityHash`，便于和 pipeline 日志对账。

### 11.3 `target` 选择器语法

```toml
[target]
game_id = "gow1"                     # 必填，精确匹配
compatibility = "exact"             # exact | code-compatible | any（默认 exact）
regions = ["usa", "asia"]           # 缺省 = 全部
editions = ["original", "full"]     # 缺省 = 全部
elf_crc = ["D6385328"]              # 精确值列表；缺省 = 不约束
text_sha1 = "8c6e61a9..."           # 单个或 "*"
runtime_commit = "471c83180a8d..."  # 或 "any"
patch_chain = "any"                 # "any" | 具体 sha256 | "contains:<patch 名>"
codegen = ["locals"]                # 缺省 = 全部
min_chain = 52                      # 可选：要求补丁链已含某编号（用于「需要 patch 52 的纹理 Mod」）
```

`min_chain` 是个实用字段：纹理类 Mod 依赖 patch 52 的 `GOW_TEXTURE_PACK` 支持，函数类 Mod 依赖 `67-mod-hooks.patch`。比起让作者写 `patch_chain = "any"` 然后运行时报错，不如在导入期就检查「链里有没有这个编号」。

### 11.4 三档兼容策略

| 档 | 判定 | 允许的能力 | UI 表现 |
|---|---|---|---|
| `exact` | 前 7 项 + codegen 全等 | 全部 | 正常启用 |
| `code-compatible` | `textSha1`、`runtimeCommit`、`patchChainHash` 全等；`elfCrc` / `edition` / `region` 可不同 | `texture_pack` / `vfs_override` / `env` / `boot` / `save`；**禁止** `function_override` / `source_patch` | 黄色提示「已按代码兼容放行」 |
| `any` | 仅 `gameId` 匹配 | 仅 `env` / `texture_pack`（且必须声明 `min_chain`） | 橙色警告 + 二次确认 |

设计依据：`.text SHA-1` 相同 ⇒ 重编译出的函数地址表相同 ⇒ `replaceFunction` 的地址有效；`patchChainHash` 相同 ⇒ 钩子位置相同。反之，`elfCrc` 变化但 `.text` 不变是**翻译盘的真实情况**（`audio-standalone-mods-2026-10-26.md:14-16`：原盘 CRC `D6385328`、PT-BR 盘 CRC `5444DDCB`，`.text SHA-1` 相同），这类盘完全可以共用纹理与参数 Mod。这就是 `code-compatible` 档存在的理由——它不是放松校验，而是把「哪些字段真正影响哪类 Mod」讲清楚。

**`any` 档要慎用且默认关闭**：它只适合「纯参数档」这类零风险的 Mod。管理器应在设置里提供 `allowAnyCompatibility`（默认 `false`）。

### 11.5 区域构建的额外身份

`data/gow1/regional-builds.json` 的每条 build 含 `region` / `code` / `elf` / `runner` / `source` / `dataDir` / `framePc` / `elf_crc` / `text_sha1` / `runner_sha256` / `elf_sha256` / `quality`。`register_region.py:29-55` 还要求 CMake source 不等于 USA 的 `engine/runtime/PS2Recomp`，并检查 `gow_overrides.cpp` 里含区域 ELF 名、不含 USA ELF 名。

因此区域版 Mod 的指纹要额外带上：

```
regionBuildId = sha256(canonical_json({
    region, code, runner_sha256, elf_sha256, framePc, source_basename
}))
```

并且 **`function_override` 类型的 Mod 在区域版上必须提供单独的地址表**。Europe/Japan 的 `entries.json` 有各自的 4093 / 4020 个 entry point，`framePc` 分别是 `0x1838A8` / `0x183BB8`（USA 是 `0x1837B8`）——同一逻辑函数在三份构建里地址不同。`mod.toml` 支持按区域给地址：

```toml
[[payload]]
type = "function_override"
capability = "function_override"
path = "func"
  [payload.options.addresses]
  usa   = "0x00188CA0"
  europe = "0x001891F0"
  japan  = "0x00189500"
```

Planner 按当前 `region` 选表；缺失该区域则判 `incompatible`，**绝不回退到 usa 地址**（这是第 3.4 节「地址错位 = 随机崩溃」的直接应用）。

### 11.6 指纹变化时的行为

`state.json` 记录上次激活 plan 的 `fingerprintId`。每次启动重新采集：

- 相同 → 直接复用 plan（但仍重跑一次轻量校验：包哈希抽查、staging 目录完整性）。
- 不同 → 标 `stale=true`，UI 显示「构建已变化」，列出 `diff()` 的逐字段差异，**不自动重新启用**；用户确认后重跑 Planner 生成新 plan。
- 若变化来自 `patchChainHash`（例如刚追加了 L1 补丁）→ 强制所有 `function_override` / `source_patch` Mod 重新校验；纹理/参数类可保留。

这条规则防止一个很隐蔽的坑：玩家重建了运行时，旧的 `function_override` 地址表还留在 plan 里，启用后打到错地址。工程自己用 `data/pgo-stale.txt` 与 `data/needs-rebuild.txt`（`update.ps1:88-93`）表达同类信号，管理器沿用这个思路即可。

## 第 12 章　能力声明与最小权限

### 12.1 能力枚举与 payload 映射

| capability | 对应 payload type | 层 | 危险级 | 说明 |
|---|---|---|---|---|
| `texture_pack` | `texture_pack` | L2/L3 | 低 | 只影响 `GOW_TEXTURE_PACK` 目录与预算 |
| `env` | `env` | L2 | 低 | 只写白名单内的 `GOW_*/PS2X_*/TOBIICHI_*` 键 |
| `vfs_override` | `vfs_override` | L3 | 中 | 按 guest 路径覆盖主机文件 |
| `boot` | `boot` | L2 | 中 | 写 `gow-native.boot` 风格的键值（仍受前缀白名单） |
| `save` | `save` | L2 | 中 | 指定 `GOW_MC0` 卡镜像 |
| `function_override` | `function_override` | L3 | **高** | 替换 guest 函数表项，ABI 错误会崩溃 |
| `pak_remap` | `pak_remap` | L1/L2 | **高** | 离线 TOC / `.disc_layout` 重指，触碰解包目录 |
| `source_patch` | `source_patch` | L1 | **高** | 追加补丁链，触发重编译，改变指纹 |
| `external_injector` | `external_injector` | L2 | **高** | ReShade 类外部注入器，需显式路径与用户确认 |

**一致性校验**：`capabilities` 必须是所有 `payload[].capability` 的超集，且每个 payload 的 `capability` 必须与 `type` 匹配（上表第一、二列）。多声明能力（例如一个纯 env Mod 声明了 `function_override`）直接判 `rejected`——这是最小权限原则的机械 enforcement。

### 12.2 危险级与用户确认

| 级别 | 导入 | 启用 | 会话报告 | 备注 |
|---|---|---|---|---|
| 低 | 自动 | 直接启用 | 记录 id/version/开关 | 无额外提示 |
| 中 | 自动 | 显示「此 Mod 会覆盖 N 个游戏文件」 | 记录覆盖键数量（不记路径） | 首次启用需确认一次 |
| 高 | 显示能力清单 | 二次确认 + 勾选「我了解可能导致崩溃」 | 记录能力、地址数量、planId | 高危 Mod 启用时自动创建一个还原点 |

**高危能力的额外约束**：

- `function_override`：必须声明 `addresses`（按区域）、`signature = "ps2_recompiled"`、以及 `chain = "decorate" | "replace"`。优先 `decorate`；`replace` 会覆盖他人 wrapper，需更高优先级且必须写进冲突表。
- `source_patch`：必须声明 `patch_number = "auto"`、`patch_header`（做什么/为什么，照 `AGENTS.md:41` 的约定）、`requires_rebuild = true`，且补丁内容只允许是**统一 diff 文本**，不得含二进制。
- `pak_remap`：只允许作用在 `data/<id>/discs/` 下由 `prepare.py` 生成的文件，且必须声明来源文件的 SHA-256；产物写到 `data/mods/staging/`，**不写回原解包目录**（保持只读基线）。
- `external_injector`：只登记路径与参数，不自动启动；文档明确 ReShade 在此 OpenGL 构建上「未测试」（`audio-standalone-mods-2026-10-26.md:66-74`），不得声称兼容。

### 12.3 环境变量白名单

`env` / `boot` 能力只能写附录 F 中标记「有 reader」的键。校验器逻辑：

```python
ALLOWED_PREFIX = ("GOW_", "PS2X_", "TOBIICHI_")   # 与 main.cpp:179 一致
def check_env_key(key: str, allowed: set[str]) -> None:
    if not key.startswith(ALLOWED_PREFIX):
        raise ModError("E_ENV_PREFIX", key)
    if key not in allowed:
        raise ModError("E_ENV_UNKNOWN", key)   # 死变量也在此被拒绝
```

特别要拒绝 `PS2X_GS_ESCALA` / `PS2X_GS_HW` / `PS2X_GS_NITIDO` / `PS2X_GS_ESCALA_DINAMICA` / `PS2X_GS_SHADER_CACHE_DIR` 这五个**死变量**（3.6 #3）——它们看起来很像正常设置，但工作树里没有 reader，写进去只会给用户「我改了却没效果」的困惑。白名单由 `tools/mods/env_allowlist.json` 维护，生成方式是静态扫描 `PS2R/` 下所有 `getenv` / `_wgetenv` / `qEnvironmentVariable` 调用，人工复核后提交；`tools/test/mod_manager_tests.py` 会校验白名单与扫描结果一致，防止运行时升级后出现漂移。

### 12.4 能力互斥

某些能力组合天然不合理，导入期直接拒绝：

| 组合 | 原因 |
|---|---|
| `source_patch` + 任何 `any` 兼容档 | 改了补丁链还敢说不挑版本 |
| `function_override` + `compatibility = "any"` | 地址表无从校验 |
| `pak_remap` + `vfs_override` 同一包 | 两类覆盖作用于同一资源层，语义混乱；拆成两个包 |
| `save` + `env` 里含 `GOW_MC0` | 卡路径应由 `save` 统一管理，避免两个来源抢一个键 |
| `external_injector` + 任何 L1 能力 | 注入器与重编译组合无法验证 |

---

## 第 13 章　Payload 类型规范

本章逐个给出每种 payload 的**目录布局、`options` 字段、导入期校验、以及映射到哪个真实运行时接口**。这张表就是 PayloadHandler 的实现清单。

### 13.1 `texture_pack`

```toml
[[payload]]
type = "texture_pack"
capability = "texture_pack"
path = "textures"
  [payload.options]
  naming = "pcsx2"            # 目前唯一支持；对应 patch 52 的 parsePackName
  budget_mb = 768             # 合并后统一写 GOW_TEXTURE_PACK_MB
  alpha = "gs-128"            # 固定值，只是提醒作者 128=不透明
  min_chain = 52              # 要求补丁链含 52
```

包内布局：`textures/<texhash>-<palhash>-<bits>.png` 或 `textures/<texhash>-<bits>.png`，可含任意子目录（patch 52 递归扫描且只用 stem 作键）。

**导入期校验**：

- 文件名 stem 必须能被 `parsePackName` 的规则解析：`%llx-%llx-%x%n` 或 `%llx-%x%n`，且扫描到结尾，尾部不允许 `-r...` / `-mip...`；
- 扩展名 `.png`（大小写不敏感）；
- PNG 头合法、尺寸 ≤ 4096×4096（防护，patch 52 本身不校验）；
- **不得包含原盘 dump**：与 `GOW_TEX_PCSX2_NAMES` 生成的名字清单比对无意义（那正是替换图应有的名字），因此靠包级声明 + 作者授权 + 发行边界保证，管理器不做内容判定，只在 UI 上提示「请确认你有权分发这些图片」。

**合并语义**：多个纹理 Mod 按优先级合成到 `staging/<planId>/textures/`。同名文件（同一个 `PackKey`）即资源键冲突，按 14.3 求解；落盘优先硬链接，跨卷退化为复制。`budget_mb` 取所有启用 Mod 中的**最大值**（不是求和），因为 patch 52 的 LRU 是单一预算。

**映射**：`GOW_TEXTURE_PACK=<staging>/textures`、`GOW_TEXTURE_PACK_MB=<budget>`、`GOW_TEXTURE_PACK_STATS=1`（诊断会话）。

**禁用语义**：不设 `GOW_TEXTURE_PACK`。patch 52 的 `TexturePack::open()` 读不到变量就不启用，`texPack.enabled()` 为 false，绘制路径只多一个布尔判断——这就是 A1「零影响」能成立的原因。

### 13.2 `vfs_override`

```toml
[[payload]]
type = "vfs_override"
capability = "vfs_override"
path = "files"
  [[payload.options.mappings]]
  guest = "cdrom0:\\MOD\\ALT.PSS;1"     # guest 侧路径
  file  = "files/alt.pss"               # 包内相对路径
  sha256 = "…"
  mode = "read-only"
```

导入期校验：

- `guest` 必须能被 `PS2I/src/ps2_path.cpp:parsePs2Path()` 解析；允许的设备：`cdrom0:` / `cdrom:` / `host0:` / `host:` / `mc0:` / `rom0:`（`rom0:` 特殊，`resolveHostPath` 返回 false 走 ROM，故本能力**禁止** `rom0:`）；
- `guest` 不得含 `..`（`ps2_vfs.cpp:135-146` 的 `safeRelativePath` 本就拒绝，但导入期先挡住更清楚）；
- `file` 必须存在且哈希匹配；
- **禁止**覆盖以下基线文件：`SYSTEM.CNF`、`SCUS_973.99`（及区域 ELF 名）、`.disc_layout`、`.disc_meta`、`GODOFWAR.TOC`、`PART1.PAK`、`PART2.PAK`、`Mcd001.ps2`。这些是身份与构建输入，覆盖它们等于绕过校验。

映射：Applier 生成 `data/mods/hooks/vfs-overrides.tsv`（两列：规范化 guest key → 绝对路径），由 `67-mod-hooks.patch` 在 `PS2Vfs::resolveHostPath()` 开头查表：

```
cdrom0:\MOD\ALT.PSS;1 → C:/.../data/mods/staging/<planId>/vfs/alt.pss
```

规范化规则沿用 `ps2_path.cpp` 的 `normalizeSuffix`（`\`→`/`、去 `;1`）与 `ps2PathLeafKey` 的大小写不敏感语义，保证表里用的键和运行时查的键是同一个。

**`host0:` 的特殊价值**：葡语研究文档 §2 提到第三方 ISO Mod 用 `host0:/mod/%s.wad` 加载，当前不支持是因为 `host0:` 没有映射到目录。`PS2VfsMounts.hostRoot` 默认也回到 `elfDirectory`，但 `resolveHostPath` 的 Host 分支会拼 `mounts.hostRoot`。因此 `vfs_override` 可以直接把 `host0:/mod/foo.wad` 指到 staging 里的文件，**无需改 ISO**——这恰好是「不改光盘」主线能兼容某些第三方 Mod 内容的钥匙。但要注意：这类 WAD 内容仍是游戏衍生数据，不能随包分发，只能玩家自备。

### 13.3 `function_override`

```toml
[[payload]]
type = "function_override"
capability = "function_override"
path = "func"
  [payload.options]
  signature = "ps2_recompiled"     # void (*)(uint8_t*, R5900Context*, PS2Runtime*)
  chain = "decorate"               # decorate | replace
  symbol = "gowModAltMovieLoad"    # 宿主函数名，必须与编译进 runner 的符号一致
  [payload.options.addresses]
  usa = "0x00188CA0"
  europe = "0x001891F0"
  japan = "0x00189500"
```

导入期校验：地址 4 字节对齐、落在 `[tableBase, tableEnd)` 范围（范围可从 `register_functions.cpp` 的 `g_ps2RecompiledFunctionTableBase/End/SlotCount` 解析）、每个声明的 region 都有地址、`symbol` 符合 C 标识符、`chain` 合法。

**这里有一个重要的现实约束**：宿主函数 `gowModAltMovieLoad` 必须**已经编译进 `ps2EntryRunner.exe`**。管理器不能运行时加载任意机器码（4.2 非目标）。因此 `function_override` 有两种合法来源：

1. **指向 `67-mod-hooks.patch` 里预置的通用宿主函数**（例如「按名字换电影」「跳过某段绘制」「记录命中」），Mod 只提供参数；
2. **由 `source_patch` 提供 C++ 源码**，走 L1 重建把新函数编进 runner —— 此时该包必须同时声明 `source_patch` 能力，Planner 标 `requires_rebuild=true`。

换句话说，`function_override` 单独出现时是「配置已有的钩子」，与 `source_patch` 一起出现时才是「注入新代码」。这个区分让绝大多数 Mod 停留在 L2/L3，符合 5.2 的取舍。

映射：`hooks/function-overrides.tsv`（`address → symbol → chain → params`），钩子在 `gowIntegracionInstalar()` 之后按优先级串链。装饰器链的实现要点见 18.4。

### 13.4 `env` / `boot`

两者区别只在于**传递通道**：

| | `env` | `boot` |
|---|---|---|
| 通道 | 启动时进程环境变量（launcher 的 `QProcess::setProcessEnvironment` 等价物） | 写入 `gow-native.boot` 风格的键值 |
| 适用 | 常规（**默认**） | 仅当玩家用「无参数双击 runner」的独立启动方式 |
| 风险 | 低 | 中：`main.cpp:150` 在有 ELF 参数时**完全不读** boot，容易「设了没生效」 |

因此 `boot` 能力默认关闭，且 UI 必须提示「仅在无参数启动方式下生效；通过 launcher 启动请用 env」。两者都受 12.3 的前缀与白名单约束，且都不允许设置 `GOW_TEXTURE_PACK`（由纹理 Handler 独占）、`GOW_MC0`（由 save Handler 独占）、`GOW_NATIVE_BOOT_V1`（那是文件魔数不是变量）。

`env` 的 `strategy`：

| 值 | 语义 | 冲突时 |
|---|---|---|
| `set` | 我要这个值 | 参与 14.3 抢占 |
| `set_if_unset` | 没人设就设我 | 自动让位，不产生冲突 |
| `append` | 追加到以 `,` 分隔的列表 | 仅允许 `GOW_MOVIE_OVERRIDE` 这类已声明可append 的键 |
| `forbid` | 禁止其他 Mod 设置该键 | 直接产生硬冲突 |

### 13.5 `source_patch`

```toml
[[payload]]
type = "source_patch"
capability = "source_patch"
path = "patch"
  [payload.options]
  patch_number = "auto"        # 由管理器分配（最大+1，避开重复与字母后缀）
  requires_rebuild = true
  header = "GOW Mod hooks: add a read-only VFS override table and a function decorator chain. Why: lets mods change data without rebuilding. Off = byte-identical."
  files = ["patch/67-mod-hooks.patch"]
```

导入期校验：补丁是纯文本 unified diff；`diff --git` / `---` / `+++` 目标路径**必须**落在 `PS2R/` 之内；不得修改 `games/` / `tools/pipeline/` / `engine/runtime.toml` / `game.toml`；不得含二进制块；头部符合 `AGENTS.md:41`（自由文本，说明做什么和为什么）；`git apply --check` 在**当前工作树的副本**上预演通过。

**注意**：不能真的在 `engine/runtime/` 上试 apply（3.1）。做法是复制相关目标文件到临时目录建一个最小 git 仓库，或直接用 `tools/pipeline/patches.ps1 start/export` 的栈工作流做校验。第 18.5 节会给完整流程。

**L1 的代价必须显眼**：启用含 `source_patch` 的 Mod 后，`patchChainHash` 变化 ⇒ 所有 Mod 需重新校验（11.6）；需要 `build.cmd -Stages fetch,configure,recomp,sync,build`（或最小子集）；构建期间 `data/pipeline.lock` 必须被持有；失败时链尾补丁要能自动摘除。

### 13.6 `save`

```toml
[[payload]]
type = "save"
capability = "save"
path = "card"
  [payload.options]
  card = "card/Mcd001.ps2"
  sha256 = "…"
  size = 8650752              # docs/saves.md 的固定大小
  slot = 0                    # → GOW_MC0；1 → GOW_MC1
```

导入期校验：文件大小必须正好 8,650,752 字节、哈希匹配、`.ps2` 格式头合法；**卡镜像属于玩家个人数据，不得随包分发**，因此 `save` 类型的包只能由玩家本机「登记」自己已有的卡文件（16.1 的第二种入口），导入器对分发包一律拒绝该 payload 类型。

映射：启动期设 `GOW_MC0=<绝对路径>`。`GOW_SAVES_DIR` 保持原值，让 F1 > Saves 的快照仍写进玩家原有目录。**禁止热替换**（3.6 #5）；每次切换卡都要求游戏已退出，Launch Bridge 检查进程状态。

### 13.7 `pak_remap`（高级）

针对 2.4 节说的「PAK 内资源按 LSN 读、无法按路径覆盖」。`prepare.py:225-240` 已给出范例：把翻译文本写成 `TR_<name>` 追加到盘尾，用 `struct.pack_into('<III', patched, i+12, 1, len(data), lsn-part2)` 重指 TOC 条目，并重写 `.disc_layout` 的 `file` 行。

`pak_remap` 的声明：

```toml
[[payload]]
type = "pak_remap"
capability = "pak_remap"
path = "remap"
  [payload.options]
  toc = "GODOFWAR.TOC"
  toc_sha256 = "…"           # 基线 TOC 哈希，不匹配即拒绝
    [[payload.options.entries]]
    name = "R_PERM.WAD"
    file = "remap/R_PERM.WAD"    # 玩家自备的替换内容
    sha256 = "…"
```

Applier **不写回** `data/<id>/discs/`，而是在 `staging/<planId>/disc/` 生成一份「影子解包目录」：复制 `.disc_layout` 并改写相关 `file` 行、生成新的 TOC 与追加文件内容，然后启动期把 `cdRoot` 指到影子目录。代价是可能要复制几 GB 的 PAK —— 用硬链接 + 只替换差异文件来避免。这是全流程里最重的一类 Mod，P5 阶段才实现，且必须提示磁盘空间预检。

### 13.8 `external_injector`

```toml
[[payload]]
type = "external_injector"
capability = "external_injector"
path = "."
  [payload.options]
  exe = ""                     # 由玩家在 UI 里填本机绝对路径，包内不得预置
  args = ""
  note = "ReShade on this OpenGL build is untested; color-only effects only."
```

管理器**只登记、不启动、不验证兼容**，并在 UI 上原样显示 `audio-standalone-mods-2026-10-26.md:66-74` 的结论：ReShade 的 OpenGL 支持在上游项目里有，但「this build/injector combination is not yet tested」；NVIDIA Smooth Motion、OptiScaler、DLSS 5 均无支持路径。任何声称「兼容 DLSS」的 Mod 包都应在导入期被人工复核拦截（这属于内容审核，不是技术校验）。

### 13.9 类型 → 真实接口总表

| type | 层 | 真实落点 | 是否需要重建 | 禁用时的影响 |
|---|---|---|---|---|
| `texture_pack` | L2/L3 | `GOW_TEXTURE_PACK`（patch 52 `TexturePack::open`） | 否 | 不设变量，零影响 |
| `vfs_override` | L3 | `PS2Vfs::resolveHostPath`（`ps2_vfs.cpp:270`） | 否（钩子由 67 号补丁一次性提供） | 空表，一次哈希查找 |
| `function_override` | L3 | `PS2Runtime::replaceFunction`（`ps2_runtime.cpp:1228`） | 视 symbol 来源 | 不装链 |
| `env` | L2 | `getenv` 各处 / `gow_vivo::cargar()` | 否 | 不设变量 |
| `boot` | L2 | `main.cpp:162-185` | 否 | 不写 boot |
| `save` | L2 | `GOW_MC0`（`iop_emulator.cpp:138`） | 否 | 用默认卡 |
| `source_patch` | L1 | `engine/patches/NN-*.patch` + `git apply` | **是** | 链尾补丁需摘除并重建 |
| `pak_remap` | L1/L2 | `prepare.py` 的 TOC/`.disc_layout` 机制 | 否（但重） | 用原 cdRoot |
| `external_injector` | L2 | 仅登记 | 否 | 不登记 |

## 第 14 章　冲突模型与确定性排序

### 14.1 资源键（Resource Key）

冲突的本质是「两个 Mod 想写同一个东西」。先把所有可写对象统一成字符串键：

| 资源 | 键格式 | 例子 |
|---|---|---|
| 纹理 | `texture:<PackKey>` | `texture:9a1c…-b3e2…-0000c1` |
| VFS 文件 | `vfs:<normalized guest path>` | `vfs:cdrom0:/mod/alt.pss` |
| guest 函数 | `fn:<region>:<addr8>` | `fn:usa:00188CA0` |
| 环境变量 | `env:<KEY>` | `env:GOW_ANISO` |
| 内存卡槽 | `save:slot<N>` | `save:slot0` |
| 补丁编号 | `patch:<NN>` | `patch:67` |
| cdRoot | `root:cd` | 只能有一个赢家 |

`normalized guest path` 必须与 `ps2_path.cpp` 的规范化完全一致，否则「看起来不同」的两个键在运行时其实指向同一文件，冲突检测会漏。为此 `tools/mods/` 里要有一份与 C++ 语义对齐的规范化函数，并用 `tools/test/mod_manager_tests.py` 做双向用例覆盖（`\` vs `/`、`;1` 后缀、大小写、`host0:` vs `host:`）。

### 14.2 四类冲突

| 类型 | 例子 | 默认策略 | 可否人工裁决 |
|---|---|---|---|
| **C1 同键覆盖** | 两个 HD 包都提供同一张纹理 | 优先级大者胜；同优先级按 `id` 字典序（确定性） | 可以，`resolutions` 覆盖 |
| **C2 地址抢占** | 两个 Mod 都替换 `0x00188CA0` | `decorate` 可共存并串链；出现 `replace` 则退化为 C1 | 可以指定链顺序 |
| **C3 键抢占** | 两个 Mod 都 `set` `GOW_ANISO` | 优先级大者胜；`forbid` 直接失败 | 可以 |
| **C4 能力互斥** | 一个 `pak_remap` 与一个 `vfs_override` 抢同一路径 | **硬失败**，不自动求解 | 否，必须拆包或禁用其一 |

`requires` / `conflicts` / `loadBefore` 属于**声明层**冲突，在建图阶段处理，不进资源键表。

### 14.3 确定性求解算法

```
输入: enabled mods M, profile.resolutions R, fingerprint F
输出: order[], winners{key→mod}, requires_rebuild, errors[]

1. 过滤: 对每个 m ∈ M:
      c = match(m.target, F)
      if c == incompatible: errors += diff(m.target, F); 从 M 移除
      if c == "any" 且 !allowAny: errors += ...; 移除
2. 依赖闭包: 反复把 m.requires 指向的包加入集合（按版本区间选最高兼容版本）
      缺失 → error E_MISSING_DEPENDENCY
3. 环检测: 对 requires + loadAfter + loadBefore 建有向图，DFS 找环 → E_DEPENDENCY_CYCLE
4. 拓扑排序: Kahn 算法；同层按 (priority DESC, id ASC, version DESC) 排序
      ⇒ 得到 order[]，与文件系统遍历顺序无关
5. 收键: for m in order: handler.collect(m) → (key, mode, weight)
      mode ∈ {own, decorate, forbid}
6. 求解:
      for key in sorted(keys):
          claims = [c for c in claims if c.key == key]
          if key in R: winner = R[key] 并检查该 winner 确实声明了此键
          elif any forbid: error E_HARD_CONFLICT (C4)
          elif all decorate (C2): winner = None; chain = claims 按 order
          else: winner = max(own claims, key=(priority, -order_index, id))
7. 标记: 任一 m 含 source_patch ⇒ requires_rebuild = True
8. 输出 plan（不含时间戳；settings 覆盖值按 key 排序后写入）
```

**第 4 步的 `id ASC` 很关键**：不确定性最常见的来源是「两个 Mod 优先级相同」，如果按文件遍历顺序决胜负，同一份 state 在两台机器上可能产出不同 plan，A2 就破了。所有排序都必须有全序比较键。

**第 6 步的 `-order_index`**：优先级相同时，让**拓扑序靠后**的 Mod 胜（语义上「后加载的覆盖先加载的」符合玩家直觉），再退到 `id` 字典序。这个规则要写进 `modspec.md`，因为 Mod 作者会依赖它。

**C2 装饰链**：`decorate` 模式的多个声明不产生唯一赢家，而是生成 `chain[]`，运行时按 `order` 依次包装（18.4）。若链里出现 `replace`，则该 Mod 必须赢得整个地址，其余 `decorate` 挂在其外层——这样既保留「后覆盖前」直觉，又不会静默丢掉别人的 wrapper。

### 14.4 冲突报告与人工裁决

Planner 输出 `conflicts[]`，每条含：

```json
{
  "key": "texture:9a1c…-b3e2…-0000c1",
  "kind": "C1",
  "claimants": ["acme.hd-ui@2.1.0", "foo.ui-fix@1.3.0"],
  "winner": "acme.hd-ui@2.1.0",
  "reason": "priority 200 > 100",
  "resolved_by": "auto"
}
```

UI 展示为「这两个 Mod 都想替换同一张贴图，当前由 X 生效」，并提供下拉框改判。改判写进 `profiles/<name>.toml` 的 `[resolutions]`，参与 plan 哈希。若用户从未裁决，报告里 `resolved_by = "auto"`，可随时重算。

**绝不做的事**：静默丢弃一个 claim 而不报告；用「文件时间戳」决定胜负；把冲突留到运行时由 C++ 钩子自己解决（那样就不可复现、也无法诊断）。

## 第 15 章　Profile、状态文件与锁

### 15.1 Profile

`profiles/<name>.toml` 是用户意图的唯一表达：启用了哪些 Mod、顺序覆盖、settings 覆盖、冲突裁决、以及 `allowAnyCompatibility` / `allowHighRisk` 两个开关。一个工程可有多个 profile（例如 `daily` / `streaming` / `vanilla`），但**同一时刻只有一个 active**，由 `state.json` 指向。

Profile 不记录指纹、不记录 planId、不记录 staging 路径——那些是派生状态。这样把 profile 拷给同指纹的另一台机器就能复现，符合目标 8。

### 15.2 `state.json`

```json
{
  "schema": 1,
  "activeProfile": "daily",
  "activePlanId": "9f2a…c71b",
  "lastFingerprintId": "b81e…04da",
  "stale": false,
  "lastApply": { "at": "2026-11-05T08:12:33+08:00", "result": "Ok" },
  "journal": "9f2a…c71b.wal",
  "restorePoints": ["8c10…", "7b22…"]
}
```

写入一律用 `atomic_json()`（`recompile.py:29-53` 的模式）：写 `<name>.tmp` → `Path.replace`；Windows 上对 `winerror` 5/32/33 做六次指数退避。禁止「先 truncate 再写」——那会在崩溃时留下半截 JSON。

**`restorePoints`**：高危 Mod 启用前自动记录当前 `activePlanId`，保留最近 5 个。用户点「一键回到上次可用状态」就是把指针换回去，不需要重新计算 plan。

### 15.3 `fingerprint.json`

记录最近一次采集的**全部原始字段与各输入文件哈希**（不只是最终的 `fingerprintId`），用途是 11.6 的 `diff()` 与排障：

```json
{
  "schema": 1,
  "collected_at": "...",
  "fields": { "gameId": "gow1", "textSha1": "8c6e61a9…", "...": "..." },
  "inputs": {
    "games/gow1/game.toml": "sha256:…",
    "engine/runtime.toml": "sha256:…",
    "engine/patches/*.patch": "sha256:…(aggregate)",
    "data/build-root.txt": "sha256:…",
    "data/gow1/regional-builds.json": "sha256:…"
  },
  "fingerprintId": "b81e…04da"
}
```

### 15.4 锁与并发

三类并发要处理：

1. **两个 launcher 实例同时改 state** → `data/mods/state.lock`，用独占文件句柄（照 `build.ps1:70-73` 的 `[IO.File]::Open(..., 'OpenOrCreate','ReadWrite','None')` / `fcntl.flock`）。拿不到就报错「另一个管理器正在操作」，不排队等待（交互操作不该静默卡住）。
2. **Applier 与 pipeline 重建并发** → 必须先拿 `data/pipeline.lock`（7.4），否则补丁链可能写到一半被 `fetch` 冲掉。L1 操作期间 UI 显示「构建进行中，Mod 操作已暂停」。
3. **游戏进程仍在运行** → `state.json` 里记录 `activeSession`，Launch Bridge 在启动前检查 runner 进程；若仍在运行，禁止 apply（`GOW_MC0` 热替换、env 变化都不会对已运行进程生效，做了只会造成「以为改了」）。

三者都是「宁可拒绝、不可猜测」，与工程整体性格一致。

### 15.5 状态可重建性

`data/mods/` 里除 `packages/` 与 `profiles/` 外，**全部可以删除并重建**：`plans/` 由 Planner 重算、`staging/` 由 Applier 重建、`hooks/` 由 plan 生成、`reports/` 是历史、`journal/` 只用于未完成的回滚。因此备份只需两份：`profiles/` + `packages/`（后者若来自玩家本机资源，实际上也不需要）。UI 应提供「重建全部派生状态」按钮，作用等价于把 `state.json` 之外的生成物清空后重跑 `plan` + `apply`——这是排障的第一板斧，也呼应 `recompile.py` 的「digests, not timestamps, decide reuse」。

---

# 卷 IV　实现：从包到进程

## 第 16 章　安装与导入

### 16.1 两种入口

**入口 A：导入 Mod 包（声明 + 差分）**。来源为本地 zip / 目录，内容受 10.5 的禁止清单约束。步骤：

```
1. 解到临时目录 data/mods/_incoming/<uuid>/
2. 结构预检：zip 条目逐个过 safe_member，拒绝绝对路径/符号链接/设备名/炸弹
3. 读 mod.toml：schema、字段类型、id 正则、version 语义化、capabilities 一致性
4. 逐 payload 校验：类型/能力映射、路径、sha256、专属 options（第 13 章）
5. 目标预检：target 语法合法、min_chain 与当前补丁链比对
6. 原子发布：临时目录 → data/mods/packages/<id>@<version>（Path.replace / MoveFileEx）
7. 写 .installed.json：包根哈希、每文件 sha256、导入时间、来源类型
8. 清理 _incoming
```

第 6 步照抄 `recompile.py:publish()`：目标目录必须不存在或为空普通目录，拒绝 symlink/junction；若目标已存在同名同版本，比较内容哈希——相同则视为重导入（no-op），不同则报错「版本已存在且内容不同，请先卸载」，**绝不覆盖已安装包**。

**入口 B：登记本机资源目录**。用于纹理 PNG、卡镜像、`host0:` WAD 这类不能随包分发的资源。用户给一个本机目录，管理器：

- 扫描并生成资源清单（文件名 → sha256、size）；
- 写 `data/mods/local-assets/<assetId>.json`，**不复制文件**；
- 生成一个「本地包」`mod.toml`，`capabilities` 按资源类型推断，payload 的 `file` 指向登记清单里的绝对路径；
- UI 明确标注「本机资源，不可分发」，导入报告里不含绝对路径（只含 assetId 与数量）。

入口 B 是铁律五与「确实需要大文件」之间的折中：机制可分发，数据留在玩家机器上。

### 16.2 校验器分层

| 层 | 检查 | 失败码前缀 |
|---|---|---|
| 结构层 | 文件树、路径安全、大小上限、扩展名黑名单 | `E_PATH_*` / `E_SIZE_*` |
| 语法层 | TOML 可解析、字段类型、必填、正则、枚举值 | `E_SCHEMA_*` |
| 语义层 | capabilities ⊇ payload、能力互斥、target 合法、地址对齐 | `E_CAP_*` / `E_TARGET_*` |
| 内容层 | sha256、PNG 头、卡大小、补丁 `git apply --check` | `E_HASH_*` / `E_PATCH_*` |
| 合规层 | 游戏衍生数据黑名单、可执行文件黑名单、URL/脚本字段 | `E_FORBIDDEN_*` |

每层独立、可单独跑（`gow-mods validate --level=content <path>`），错误信息必须包含「哪个文件、哪一行、期望什么」。工程现有的 `validate_report()` 就是这种风格（四类计数必须唯一且为 0），沿用它的严格性。

### 16.3 索引与缓存

Registry 在启动时扫 `packages/` 建内存索引；包数量通常几十个，不需要数据库。为避免每次都重算所有文件哈希，用 `.installed.json` 里的 `(mtimeMs, size, sha256)` 三元组做缓存——**但这里有个必须避开的坑**：用户级记忆里记过 DSH 插件的「缓存判据经典坑」——`(mtime,size)` 是文件时钟，不能替代内容时钟。因此规则是：

- 缓存命中也要校验 `.installed.json` 里的 `packageRootHash` 与当前重算值；
- 任何 `plan` 都重新抽查启用的 Mod（默认全量重算，包内文件数 < 20000，成本可接受）；
- 只有在「纯 UI 列表刷新」时才允许用 `(mtime,size)` 快速路径。

## 第 17 章　Planner：解析、依赖、冲突求解

### 17.1 依赖表达式

`requires` 元素形如 `"acme.base@>=1.2.0,<2.0.0"`，解析成 `(id, versionRange)`；版本比较按语义化版本三段数字 + 预发布标识符。匹配时从 Registry 里选**满足区间且兼容当前指纹的最高版本**。若存在两个同版本不同 build metadata，按 `version` 字典序取确定值。

`loadAfter` / `loadBefore` **不隐含依赖**：仅当两个包都在启用集合里时才影响顺序；若指向的包未启用，静默忽略（不报错），因为「顺序提示」不该变成安装要求。这条要在文档里讲清楚，否则 Mod 作者会误用。

### 17.2 指纹匹配与差异报告

```python
def match(selector: TargetSelector, fp: Fingerprint, cfg: Config) -> Decision:
    if selector.game_id != fp.gameId: return reject("game_id", ...)
    if selector.runtime_commit != "any" and selector.runtime_commit != fp.runtimeCommit:
        return reject("runtime_commit", (selector.runtime_commit, fp.runtimeCommit))
    if selector.patch_chain not in ("any", fp.patchChainHash): ...
    if selector.min_chain and not chain_contains(selector.min_chain): ...
    if selector.compatibility == "exact":
        for f in ("elfCrc", "textSha1", "region", "edition", "codegen"): ...
    elif selector.compatibility == "code-compatible":
        require_equal(("textSha1", "runtimeCommit", "patchChainHash"))
        forbid_capabilities(("function_override", "source_patch", "pak_remap"))
    else:  # any
        if not cfg.allowAnyCompatibility: return reject(...)
        forbid_capabilities_except(("env", "texture_pack"))
    return accept(level=...)
```

`reject()` 必须返回**逐字段差异**，UI 展示成表格：

```
字段            期望                          实际
textSha1       8c6e61a9…                     706831f2…   ← 不匹配
runtimeCommit  471c8318…                     471c8318…   ✓
patchChain     3fa0…                         8c11…       ← 不匹配
建议：该 Mod 声明 exact，且当前构建可能是 Europe 区域版；请改用对应区域的版本。
```

这种「说清楚哪里不对」的设计，直接来自工程自身的错误风格（`Executable does not match this game profile; a regional function map and runtime port are required…`）。

### 17.3 冲突求解的实现要点

14.3 的算法在 C++ 与 Python 两侧各实现一次，用**同一批黄金用例**做交叉校验（`tools/mods/tests/golden/`）：每个用例给一组 `mod.toml` + profile + fingerprint，断言两边产出的 `plan.json` 逐字节相同。这是 A2 最硬的保障，也是防止「C++ 和 CLI 行为漂移」的护栏。

实现细节：

- 图的节点用 `id@version` 字符串，边用 `std::map` / `sorted()` 保证遍历有序；
- Kahn 算法的就绪队列用 `std::priority_queue`，比较键 `(priority DESC, id ASC, version DESC)`；
- 所有输出数组在序列化前按 key 排序；
- `plan.json` 不含 `collected_at` 等时间字段；时间只写在 `fingerprint.json` 与报告里；
- `settings` 覆盖、人工裁决都按 key 排序写入；
- `planId = sha256(canonical_json(plan_without_id))[:16]`。

### 17.4 `plan.json` 的结构（摘要）

```json
{
  "schema": 1,
  "planId": "9f2a…c71b",
  "fingerprintId": "b81e…04da",
  "profile": "daily",
  "order": ["acme.hd-ui@2.1.0", "acme.clean-look@1.0.0"],
  "incompatible": [],
  "conflicts": [ { "key": "...", "kind": "C1", "winner": "...", "resolved_by": "auto" } ],
  "winners": { "texture:9a1c…": "acme.hd-ui@2.1.0" },
  "chains":  { "fn:usa:00188CA0": ["foo.a@1.0", "bar.b@2.0"] },
  "env":     { "GOW_TEXTURE_PACK": "...", "GOW_TEXTURE_PACK_MB": "768", "GOW_ANISO": "8" },
  "vfs":     [ { "guest": "cdrom0:/mod/alt.pss", "host": "staging/.../vfs/alt.pss" } ],
  "textures": { "dir": "staging/.../textures", "budgetMb": 768, "linkMode": "hardlink" },
  "functions": [ { "addr": "0x00188CA0", "symbol": "...", "chain": "decorate" } ],
  "patches": [],
  "requires_rebuild": false,
  "capabilities": ["env", "texture_pack"],
  "high_risk": false
}
```

完整 schema 见附录 B。**`plan.json` 一旦写入就是只读的**；任何修改都生成新 planId。这让「回到上次的 plan」变成一次指针切换。

## 第 18 章　Applier：三层注入的具体落地

这是全篇最核心的一章。每个小节对应一个真实运行时接口，给出可直接改写的代码骨架。

### 18.1 L2：环境变量合成

Launch Bridge 从 `plan.env` 生成最终环境：

```cpp
// launcher/src/mods/LaunchBridge.cpp
QProcessEnvironment LaunchBridge::compose(const Plan& plan,
                                          const QProcessEnvironment& base) const {
    QProcessEnvironment env = base;                 // launcher 原有的变量
    if (plan.env.empty()) return env;              // A1：零 Mod 时原样返回
    for (auto it = plan.env.constBegin(); it != plan.env.constEnd(); ++it) {
        if (!EnvAllowlist::contains(it.key()))
            return fail("E_ENV_UNKNOWN", it.key());
        env.insert(it.key(), it.value());
    }
    if (plan.textures) {
        env.insert("GOW_TEXTURE_PACK", plan.textures->dir);
        env.insert("GOW_TEXTURE_PACK_MB", QString::number(plan.textures->budgetMb));
        if (diagnosticsEnabled) env.insert("GOW_TEXTURE_PACK_STATS", "1");
    }
    // 不写 gow-native.boot：main.cpp:150 在有 ELF 参数时会跳过它
    return env;
}
```

三条纪律：① 从 launcher 原有环境**复制**而不是重建（工程有大量 `GOW_*` 诊断变量由 Performance 页设置，不能丢）；② 白名单校验在启动时再跑一次（防 plan 被人手改）；③ 不写 `gow-native.boot`，避免 3.6 #4。

若玩家坚持用无参数独立启动（双击 runner），Launch Bridge 提供一个「生成独立启动配置」的显式按钮，写 `gow-native.boot` 到 runner 同目录，并在 UI 上标注「机器相关文件，请勿提交/分发」（`AGENTS.md:374`）。这条路径与 `modules/game.ps1:216-221` 的默认 boot 格式保持兼容，首行 `GOW_NATIVE_BOOT_V1`、第二行绝对 ELF 路径、之后只写三前缀变量。

### 18.2 L3：VFS 覆盖表与 `67-mod-hooks.patch`

一次性 L1 注入的核心，就是在 `PS2Vfs::resolveHostPath()` 开头加一张只读表查找：

```cpp
// PS2R/src/lib/ps2_vfs.cpp —— 67-mod-hooks.patch 新增（示意）
#include "runtime/mod_vfs_table.h"

namespace {
// 启动时一次性读入 data/mods/hooks/vfs-overrides.tsv，之后只读
ModVfsTable& modTable() {
    static ModVfsTable t = ModVfsTable::loadFromEnv("GOW_MOD_VFS_TABLE");
    return t;                       // 函数内 static：只初始化一次
}
} // namespace

bool PS2Vfs::resolveHostPath(const std::string& path, const PS2VfsMounts& mounts,
                             std::string& result) {
    // ---- mod hook: 一次内存哈希查找，无磁盘 IO、无锁、无分配 ----
    if (const char* override = modTable().lookup(path)) {
        result.assign(override);
        return true;
    }
    // ---- 以下为原有逻辑，一行不改 ----
    const ParsedPs2Path parsed = parsePs2Path(path);
    ...
}
```

`ModVfsTable::loadFromEnv` 在**进程启动阶段**（`main.cpp` 构造 runtime 之前、`gow-native.boot` 恢复之后，见 2.3 与 3.6 #3 的时机约束）读一个 TSV，把规范化 guest key 存进 `unordered_map<string, string>`，之后 `lookup()` 只做 `normalizeSuffix` + `find`。`normalizeSuffix` 复用 `ps2_path.cpp` 已有函数，避免两套规范化语义。

**这张表必须同时覆盖 `stat`**：好在 `PS2Vfs::stat()`（`:235`）也调 `resolveHostPath`，所以一处注入自动生效。`translateGuestPath`（`ps2_iop_host.cpp:289`）同样汇聚于此。

**关闭时零影响**：`GOW_MOD_VFS_TABLE` 未设置 → 表为空 → `lookup` 返回 nullptr → 走原逻辑，只多一个分支。A1 的「字节等价」在这里靠「空表 + 无条件短路」保证，验证方法是固定输入会话对比 `GOW_HOST_SHOT` 截图（`texture-replacement.md:153-154` 的 off=unchanged 测试思路）。

### 18.3 L3：纹理包合并

```python
def materialize_textures(plan, staging: Path) -> None:
    out = staging / "textures"; out.mkdir(parents=True, exist_ok=True)
    for key, mod_id in sorted(plan.winners.items()):
        if not key.startswith("texture:"): continue
        src = package_dir(mod_id) / payload_path(mod_id, key)
        dst = out / src.name
        try:
            os.link(src, dst)            # 同卷硬链接，零拷贝
        except OSError:
            shutil.copy2(src, dst)      # 跨卷退化
            plan.textures.linkMode = "copy"
```

要点：

- **只放获胜文件**：冲突在 Planner 阶段已解决，staging 目录里每个 `PackKey` 只有一个文件，patch 52 的 `m_entries[key]` 不会被后来的覆盖。
- **目录层级扁平化**：patch 52 只用 stem 作键，所以扁平即可；若保留原包的子目录也无害，但扁平更好排查。
- **预算取最大值**（13.1）；`GOW_TEXTURE_PACK_MB` 最小 64 MB（patch 52 的 `max(64, …)`），Planner 要 clamp。
- **诊断**：会话开启 `GOW_TEX_PCSX2_NAMES` 时，把输出的 names 文件与 staging 目录做差集，得出「本会话实际用到但包里没有」的纹理清单，写进 `mod-report.json`——这是 Mod 作者最需要的信息。
- **不预加载**：patch 52 没有 `GOW_TEX_PRELOAD`（那是设计文档里的规划项），不要凭空设置。

### 18.4 L3：函数装饰链

`67-mod-hooks.patch` 还要在 `gowIntegracionInstalar()` 之后（因为顺序敏感，见 `gow_integracion.cpp:459`）加一段：

```cpp
// PS2R/src/lib/mod_function_hooks.cpp —— 67-mod-hooks.patch 新增
struct ModFnEntry {
    uint32_t addr;
    RecompiledFunction host;      // 必须是已编译进 runner 的符号
    bool replace;                 // false = decorate
};

void installModFunctionHooks(PS2Runtime& runtime) {
    const auto& table = ModFnTable::loadFromEnv("GOW_MOD_FN_TABLE");  // 启动期建好
    for (const auto& group : table.byAddressSorted()) {                // 地址升序，确定性
        RecompiledFunction original = runtime.lookupFunction(group.addr);
        if (!original) { log("[mod-fn] no function at %08x", group.addr); continue; }
        // 装饰链：按 plan.order 依次包装，最外层最后装
        std::vector<RecompiledFunction> chain;
        for (const auto& e : group.entries) {
            if (e.replace) { chain.clear(); chain.push_back(e.host); }
            else           { chain.push_back(e.host); }
        }
        // 每个 host 通过线程局部/静态表拿到「下一层」，避免动态分配
        ModFnDispatcher::bind(group.addr, original, chain);
        runtime.replaceFunction(group.addr, &ModFnDispatcher::trampoline);
    }
}
```

`trampoline` 用 `(rdram, ctx, runtime)` 签名，从 `ctx` 或一张以 addr 为键的静态表里取出当前链与索引，逐层调用，最后调 `original`。**关键约束**：链查找必须在 `loadELF` 之后、`gow-native.boot` 恢复之后完成（2.3），且 trampoline 内不得做任何 IO、分配或日志写盘（3.3）。命中计数用 `std::atomic<uint64_t>` 累加，由 Diagnostics 在会话结束时读取。

`replace` 语义与 14.2 的 C2 一致：它清空之前的装饰，但 Planner 已保证只有唯一赢家能声明 `replace`，其余 `decorate` 由 `chain` 顺序表达。

### 18.5 L1：补丁链追加与重建触发

流程：

```
1. Planner 标 requires_rebuild=true，plan.patches[] 列出待追加的 diff 文本哈希
2. Applier 检查 data/pipeline.lock 可获取；不可用 → E_PIPELINE_BUSY
3. 分配编号：扫描 engine/patches/*.patch 的纯数字前缀，取 max+1；
   若已有 67 同号（含字母后缀）则继续 +1；写入 plan 固定下来
4. 生成补丁：头部自由文本（含 Mod id、planId、做什么/为什么），
   主体是包内提供的统一 diff；文件名 NN-<slug>.patch
5. 预演：复制到临时最小 git 仓库，git apply --check；
   绝不直接在 engine/runtime/ 上试（3.1）
6. 原子写入 engine/patches/NN-*.patch，记进 WAL
7. 触发 build.cmd -Stages fetch,configure,recomp,sync,build
   （复用 installer_backend 的 ===step=== / @@progress / @@status 协议）
8. 构建成功 → 重新采集指纹 → 重跑 Planner → 新 plan（patchChainHash 已变）
   构建失败 → 按 WAL 摘除链尾补丁 → 回滚 state → 报告失败原因
```

第 7 步要特别注意 `AGENTS.md:190-191` 与 `:286`：`LoadingScreen.qml` 与 `InstallPage.qml` 按**前缀匹配** `build.ps1` 的 step 文本，所以不要为 Mod 重建新增 step 名，直接复用现有 stage 的文本。

第 8 步的「重新采集」是 11.6 的强制路径；`data/needs-rebuild.txt` / `data/pgo-stale.txt`（`update.ps1:88-93`）这类工程既有信号也可用于提示「PGO profile 已过期」。

**为什么不建议把 L1 做成默认能力**：每次启用都改 `patchChainHash`，会让所有 Mod 重新校验，还会让 `distribution.ps1` 的 PGO manifest 失配（`Get-ProfileIdentity()` 含补丁集哈希）。因此 UI 上 `source_patch` 应显示为「高级 / 需要重建 / 影响其他 Mod」，并在确认框里列出后果。

### 18.6 音频、FMV、文本、存档的落地映射

| 资源 | 推荐路径 | 真实接口 | 备注 |
|---|---|---|---|
| FMV 换片 | `env` → `GOW_MOVIE_OVERRIDE` | `gow_overrides.cpp:1115-1136` `movieOverrideList()`，名字 ≤31 字符 | 现成能力，零开发量 |
| FMV 文件替换 | `vfs_override` 覆盖 `.PSS` / `.PSW` 路径 | `resolveHostPath` | 若走 LSN 流式读取则需 `pak_remap` |
| 跳过 FMV / 快速启动 | `env` → `GOW_SKIP_FMV` / `GOW_FAST_BOOT` | `gow_overrides.cpp:2105, 2099` | 现成 |
| 音频 bank（VAG） | `vfs_override` 覆盖 WAD / `.VAG`；或 `pak_remap` | `Kernel/Syscalls/FileIO.cpp:129-156` 的 `g_vagAccum` 按 `0x56414770` 累积 | `Kernel/Stubs/Audio.cpp` 是 libsd stub，**不读文件**，不要在那里挂钩 |
| 音频设备/诊断 | `env` → `GOW_AUDIO_DEVICE` / `GOW_AUDIO_STATS` / `GOW_AUDIO_PCM` | `ps2_audio_device.cpp:41` 等 | 现成 |
| 文本 `R_PERM.WAD` / `R_SHELL.WAD` | `pak_remap`（TOC 重指） | `prepare.py:225-240` 的 `TR_*` 做法 | **没有**运行时 `LoadText()` 可 hook（2.6） |
| 存档 | `save` → `GOW_MC0` | `iop_emulator.cpp:134-145` | 8,650,752 字节卡镜像；`GOW_SAVES_DIR` 保持原值 |
| 语言 | **不由 Mod 改** | `languages.json` → ELF → `cdRoot` | 语言是启动选择，不是 Mod；改它会连带改变整个资源根 |
| 外部注入器 | `external_injector` 仅登记 | — | 不声称兼容（13.8） |

**一个反复出现的教训**：这四类资源里，只有 FMV 与音频有「现成开关」；文本和 PAK 内资源都落在**离线层**。设计 Mod 包时若作者想做「中文补丁」，正确做法不是找运行时文本函数（不存在），而是 `pak_remap` 或 `host0:` VFS 覆盖。第 27 章会把这条列为反模式之一。

---

## 第 19 章　事务、回滚与崩溃恢复

### 19.1 三阶段：stage → commit → activate

照抄 `recompile.py:publish()` 的事务形状：

```
stage:   所有产物写到 data/mods/_stage/<planId>/
         （纹理 staging、vfs.tsv、fn.tsv、env.list、待追加的 patch 文本）
         此阶段不触碰任何生效路径，不写 state.json
commit:  逐项原子发布：
         _stage/<planId>/hooks/* → data/mods/hooks/*（temp + replace）
         _stage/<planId>/staging → data/mods/staging/<planId>
         engine/patches/NN-*.patch（仅 L1，且持 pipeline.lock）
         每一步写 WAL 记录 (op, from, to, sha256Before, sha256After)
activate: 原子写 state.json：activePlanId = <planId>
          state.json 落盘成功即视为生效
```

**状态点的选择很重要**：只要 `state.json` 还没写，无论前面做了多少，重启后都按旧 plan 运行；一旦写了，所有产物必须已经就位。因此 `activate` 必须是最后一步且只有一次原子写。

### 19.2 WAL 设计

`data/mods/journal/<planId>.wal` 是行式 JSONL：

```json
{"seq":1,"op":"mkdir","path":"staging/9f2a…","undo":"rmdir"}
{"seq":2,"op":"link","path":"staging/9f2a…/textures/a.png","undo":"unlink"}
{"seq":3,"op":"replace","from":"_stage/…/vfs.tsv","to":"hooks/vfs-overrides.tsv","undo":"restore","shaBefore":"…","shaAfter":"…"}
{"seq":4,"op":"patch_add","path":"engine/patches/67-mod-hooks.patch","undo":"patch_remove","shaAfter":"…"}
{"seq":5,"op":"state","from":"8c10…","to":"9f2a…","undo":"state_restore"}
```

每条记录在执行**之前**追加并 `flush`，崩溃后按 `seq` 倒序执行 `undo`。`replace` 类操作保留旧文件副本在 `_stage/<planId>/backup/`，直到事务结束且稳定期（默认 60 秒）过后才清理——这样即使 `undo` 本身失败，也能人工从 backup 恢复。

### 19.3 失败回滚矩阵

| 失败点 | 已完成的操作 | 回滚动作 | 用户看到 |
|---|---|---|---|
| 导入校验失败 | 临时目录 | 删 `_incoming/<uuid>` | 「包不合法：E_HASH_MISMATCH: textures/a.png」 |
| Planner 报错 | 无写盘 | 无需回滚 | 冲突/依赖/指纹差异表 |
| stage 中磁盘满 | 部分 staging | 删 `_stage/<planId>` | 「空间不足，需要 X MiB」+ 预检建议 |
| commit 某步失败 | 前几步已发布 | 按 WAL 倒序 undo，恢复 hooks 与 patch 链 | 「已回滚到 plan 8c10…」 |
| L1 构建失败 | 链尾补丁已写入 | 摘除补丁 + 恢复 state + 重新采集指纹 | 「构建失败，补丁已自动摘除」+ build.log 路径 |
| 游戏进程崩溃 | activate 已完成 | **不自动回滚**（可能是偶发）；生成崩溃报告并建议「禁用最近启用的 Mod」 | 最小复现包 + 建议 |
| 管理器进程被杀 | WAL 未完成 | 下次启动检测未完成 WAL → 自动 rollback | 「检测到未完成的事务，已恢复」 |

最后一行是崩溃恢复的核心：**启动时先扫 `journal/*.wal`，找没有 `{"op":"done"}` 结尾的文件，自动执行倒序 undo**。这与 `recompile.py` 的 `finally` 清理 `out.pending-*` 是同一种思路。

### 19.4 「禁用全部 = 从未装过」的验收

A1 要求字节等价。验证步骤（应做成自动化用例 `tools/test/mod_manager_tests.py::test_vanilla_byte_identical`）：

1. 在干净安装上跑一次固定输入会话（`GOW_PAD_TEST` 脚本 + `GOW_HOST_SHOT` 截图 + 100 秒），记录输出哈希与截图哈希；
2. 启用 3 个 Mod（纹理 / VFS / 参数），跑同样会话，确认行为确实变化（否则测试无效）；
3. 禁用全部 Mod，重跑同样会话；
4. 断言：环境变量集合与基线一致（无 `GOW_MOD_*` / `GOW_TEXTURE_PACK`）、`hooks/vfs-overrides.tsv` 为空、`hooks/function-overrides.tsv` 为空、截图逐字节相同、`ps2EntryRunner.exe` 未重新编译。

这个测试直接借用了 `texture-replacement.md:153-154` 的「Off = unchanged」验收思路，把它从「单个补丁」提升到「整个管理器」。

## 第 20 章　Launch Bridge：与 launcher / pipeline 集成

### 20.1 集成位置的选择

两个候选：**A. 新增 `-Stages mods`**（走 pipeline）／**B. launcher 侧预启动**（走 ModsModel）。7.4 已否决 A，理由是 stage 按模块加载顺序执行、且 Mod 是启动概念不是构建概念。B 的具体形态：

```
玩家点「开始游戏」
  → Lanzador::iniciar(settings) 之前插入 ModsModel::prepareSession()
  → 采集指纹 → 若 stale 则提示 → plan → apply（必要时回滚）
  → compose(env) → 交给原有启动路径
  → 会话结束 → Diagnostics::writeReport()
```

只有 `source_patch` 触发的重建才借道 pipeline（18.5 第 7 步），且复用 `installer_backend` 已有的进度协议，不新增 stage。

### 20.2 `ModsModel` 接口

```cpp
// launcher/src/ModsModel.h
class ModsModel : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString activeProfile READ activeProfile WRITE setActiveProfile NOTIFY profileChanged)
    Q_PROPERTY(bool stale READ stale NOTIFY fingerprintChanged)
    Q_PROPERTY(int enabledCount READ enabledCount NOTIFY planChanged)
    Q_PROPERTY(bool requiresRebuild READ requiresRebuild NOTIFY planChanged)
public:
    Q_INVOKABLE QVariantList listMods() const;             // id/version/title/capabilities/compatible
    Q_INVOKABLE QVariantList conflicts() const;             // 给 UI 展示冲突表
    Q_INVOKABLE QString setEnabled(const QString& id, bool on);  // 返回 error 或空串
    Q_INVOKABLE QString importPackage(const QString& path);
    Q_INVOKABLE QString registerLocalAssets(const QString& path);
    Q_INVOKABLE QString plan();                            // 重算，返回 planId
    Q_INVOKABLE QString apply();                           // 事务应用
    Q_INVOKABLE QString rollback();
    Q_INVOKABLE QString rebuild();                         // 仅 L1
    Q_INVOKABLE QVariantMap lastReport() const;
signals:
    void profileChanged(); void fingerprintChanged(); void planChanged();
    void rebuildProgress(const QString& step, int done, int total);
    void error(const QString& code, const QString& detail);
};
```

注册照 `engine/runtime/launcher/src/main.cpp:94-95`：

```cpp
ModsModel modsModel;
engine.rootContext()->setContextProperty(QStringLiteral("mods"), &modsModel);
```

全仓搜索没有 `qmlRegisterType` / `QAbstractListModel` 的使用，所以 `setContextProperty` + `QVariantList` 是与现有代码最一致的做法，不需要引入新的注册机制。

### 20.3 QML 页面与最小改动面

| 文件 | 改动 | 说明 |
|---|---|---|
| `launcher/qml/Main.qml` | sidebar 追加一个 `NavItem`，`pagina = 9` | **不重排 0..8**：`AGENTS.md:44-46` 的编号表、`pestanaInicial` 截图页号、既有测试都依赖原编号 |
| `launcher/qml/ModsPage.qml` | 新增 | 列表、开关、优先级拖动、冲突表、指纹差异表、报告查看 |
| `launcher/CMakeLists.txt` | `ARCHIVOS_QML` 追加 `ModsPage.qml`；`launcher/src/mods/*` 加入 target | `AGENTS.md:237-239`：新增文案键也要登记 |
| `launcher/qml/Textos.js` | 新增键（tr/en/es/pt 四语内联） | `tools/test/launcher-languages.py` 会检查键与 `%1/%2` 占位符一致性，且**已在 verify 里** |
| `launcher/qml/idiomas/{fr,de,it,ru,zh}.js` | 补齐键 | 缺失时回退英文，但测试会报错 |
| `launcher/src/main.cpp` | 一行 `setContextProperty` | 见上 |
| `AGENTS.md` | 页面编号表、`data/mods/` 说明、契约 | 工程约定要求「keep it current when you change the architecture」 |
| `docs/architecture.md` | 数据流图补一条 ModsModel | 可选但推荐 |

`ModsPage.qml` 的视觉沿用 `Tema.qml` 的配色（`fondo #0a0605`、`panel #cc140c0a`、`oro #d4a857`、`rojo #b0221a` 等，`engine/runtime/launcher/qml/Tema.qml:11-29` 可参照），文字用 `Tema.t(key)` 走多语言，不要硬编码中文。

**当前副本的前置条件**（2.7）：`launcher/qml/`、`Textos.js`、`idiomas/`、`pruebas/` 全部缺失，只有 `launcher/bin/gow-launcher.exe`。因此 P0 必须先取得完整仓库的 `launcher/` 源码；否则四个 UI 测试会在 `shutil.copytree(root/'launcher/qml', ...)` 处失败，`build.cmd -Stages verify` 里的 `launcher-languages.py` 也会失败。**不要试图从 exe 里反编译 QML 来凑合**。

### 20.4 与 `AccessibilityPage.qml` 的关系

现有 Accessibility 页已有 `pacoteTexturas` / `usarPacoteTexturas` 两个设置（`tools/test/qte-controls.py:46-47, 82-88`），把纹理包目录传给 `GOW_TEXTURE_PACK`。为了避免两套 UI 抢同一个变量：

- **迁移**：Mods 页上线后，纹理包开关由 ModsModel 统一管理；Accessibility 页保留为「快捷入口」，点击跳转到 Mods 页，不再自己写 `GOW_TEXTURE_PACK`。
- **兼容**：旧设置若存在，导入为一个「本地包」（16.1 入口 B），保证升级后玩家原有的纹理包不失效。
- **契约不变**：`qte-controls.py` 的断言仍要能过（它检查的是 UI 控件存在与设置持久化），所以不要直接删掉这两个 property，改为由 ModsModel 代理读写。

### 20.5 会话报告与导出白名单

`tools/test/session-game-smoke.py:107` 已断言导出报告不含 `.ps2/.iso/.ppm`；`AGENTS.md:123-124` 要求「Export only the explicit allowlist; never add ISOs, saves, full environment dumps or automatic uploads」；葡语研究文档也说明纹理包「开关进会话报告，目录不进（隐私）」。Mod 报告沿用同一纪律：

| 允许导出 | 禁止导出 |
|---|---|
| Mod id / version / 启用状态 / 能力 | 包目录绝对路径、纹理包路径 |
| `planId` / `fingerprintId` / 兼容档 | ELF / ISO / 解包目录路径 |
| 冲突数量、裁决方式（`auto`/`manual`） | 完整环境变量 dump（只导出键名白名单内的键与是否为 Mod 设置） |
| 纹理 hits / loads / evictions / resident MB | 任何 PNG / WAD / FMV / 卡镜像内容 |
| VFS 覆盖命中次数、函数链命中次数 | 玩家截图、存档、日志全文 |

## 第 21 章　诊断与可观测性

### 21.1 三层日志

| 层 | 位置 | 内容 | 生命周期 |
|---|---|---|---|
| 管理器日志 | `data/mods/logs/manager.log` | 导入、plan、apply、回滚、错误码 | 轮转 2 代，仿 launcher 的 `ultimo.log` → `anterior.log` |
| 会话报告 | `data/mods/reports/<session>/mod-report.json` | 生效 plan、命中统计、节奏数据 | 保留最近 20 份 |
| 游戏内诊断 | `GOW_TEXTURE_PACK_STATS`、`GOW_TEX_PCSX2_NAMES`、`GOW_CD_TRACE`、`GOW_PERF_DIAG` | 运行时原始计数 | 由现有工具产生，管理器只收集 |

`GOW_CD_TRACE=1` 会打印每次 `sceCdRead` 的 `lsn/sectors/dst/ok`（`iop_cdvd.cpp:238`），对排查 `pak_remap` 极有用，但**不要默认开启**（每帧大量输出，违反 3.3）。只在「诊断会话」里显式打开，并限时。

### 21.2 `mod-report.json` 关键字段

```json
{
  "schema": 1,
  "session": "20261105-081233",
  "planId": "9f2a…c71b",
  "fingerprintId": "b81e…04da",
  "active": [ {"id":"acme.hd-ui", "version":"2.1.0", "capabilities":["texture_pack"]} ],
  "texture": { "hits": 81, "loads": 81, "evictions": 0, "residentMb": 73 },
  "vfs":     { "lookups": 1284, "hits": 37 },
  "functions": { "chains": 1, "hits": 6021 },
  "exit":    { "code": 0, "graceful": true },
  "warnings": []
}
```

`exit.graceful=false` 时自动标记 `suspect=true`，并把最近启用/变更的 Mod 列进 `warnings`，供「一键回到上次可用状态」使用。

### 21.3 崩溃时的最小复现包

只含四样东西，且全部是文本：`plan.json`、`fingerprint.json` 的 `fields` 部分（去掉 `inputs` 里的路径）、`mod-report.json`、`manager.log` 的最后 200 行。打包为 `data/mods/reports/<session>/repro.zip`，**不含任何资源文件**，可以直接贴到 issue 而不违反 `AGENTS.md:299-303`。

### 21.4 命中统计怎么来

- 纹理：patch 52 的 `GOW_TEXTURE_PACK_STATS` 每 300 帧打印 `[gs-texpack] hits=… loads=… evictions=… resident=… MB`，解析该行即可。
- VFS：`ModVfsTable::lookup()` 用两个 `std::atomic<uint64_t>` 累加 lookups/hits，进程退出前由 Diagnostics 写一次文件。
- 函数链：`ModFnDispatcher::trampoline` 同理，按 addr 累加。
- **绝不逐条打日志**：这三个计数器都是热路径，累加用 `relaxed` 内存序，且只在会话结束写一次盘。

### 21.5 「Mod 导致崩溃」的排查顺序

给支持者/玩家的标准流程，写进 `modspec.md`：

1. 打开 `mod-report.json`，确认 `exit.graceful` 与最后启用的 Mod；
2. 禁用全部 Mod → 跑同一场景 → 若不复现，确认与 Mod 相关；
3. 二分法启用（按 `plan.order` 前一半/后一半）→ 定位到单个 Mod；
4. 检查该 Mod 的 `capabilities`：含 `function_override` / `source_patch` 时，先看 `fn:` 冲突表与地址是否属于当前 `region`；
5. 检查 `fingerprintId` 是否与 plan 记录一致（不一致 = 构建变了没重新 plan，见 11.6）；
6. 纹理类问题先看 `evictions` 与 `residentMb`，再看 `GOW_TEX_PCSX2_NAMES` 差集；
7. 仍无结论则导出 `repro.zip`，附 `build.cmd -Stages verify` 结果。

---

# 卷 V　质量、合规与路线图

## 第 22 章　测试策略

### 22.1 与现有测试框架对齐

工程 **没有 pytest**（`tools/test/*.py` 里零命中 `import pytest`）。5 个脚本用 `unittest`（`pipeline_tests.py`、`linux_pipeline_tests.py`、`regional-overlays.py`、`register-region-tests.py`、`session_diagnostics.py`），其余是「脚本式」：头部 docstring 写用法、`root = Path(__file__).resolve().parents[2]`、`errors` 计数 + `print("PASS: …")` + `sys.exit(1 if errors else 0)`。四个 UI 测试完全同构：`tempfile.TemporaryDirectory` + `shutil.copytree(root/'launcher/qml', work/'ui')` + 写 `qmldir` + 写 `test.qml`，QML 里 `function check(ok,msg){ if(!ok) throw new Error(msg) }` + `console.log("PASS: …")` + `Qt.exit(0)`；Python 侧用 `qml.exe` offscreen 跑，判定 `returncode`、`"PASS:" in output`、无 `ReferenceError/TypeError`。

**新增测试必须沿用这个风格**，不要引入 pytest 或新框架。统一调用形式：

```
python -I tools/test/mod_manager_tests.py
python -I tools/mods/gow_mods_cli.py validate --level=all <path>
python -I tools/test/mod-manager-ui.py <Qt SDK bin/qml.exe> <llvm-mingw bin>
```

### 22.2 新增测试清单

| 测试 | 类型 | 断言要点 |
|---|---|---|
| `mod_manager_tests.py` | unittest | schema 校验、路径穿越、能力一致性、sha256、死变量拒绝、黑名单 |
| `mod_planner_golden.py` | unittest | C++ 与 Python 双实现同一批 golden 用例产出逐字节相同 plan（A2） |
| `mod_fingerprint_tests.py` | unittest | Ordinal 排序、缺号/重复编号、区域地址表选择、`diff()` 输出 |
| `mod_conflict_tests.py` | unittest | C1–C4、环检测、优先级全序、人工裁决参与哈希 |
| `mod_transaction_tests.py` | unittest | stage/commit/activate、WAL 倒序 undo、崩溃恢复、A3 |
| `mod-manager-ui.py` | QML 脚本式 | ModsPage 能实例化、开关持久化、冲突表渲染、无 ReferenceError |
| `mod_vanilla_equivalence.py` | 会话级 | 19.4 的字节等价（需真实游戏数据，标 `@slow`，不进 verify） |
| CTest `gow_mod_vfs_hooks` | C++ 单测 | `ModVfsTable` 规范化、空表短路、`resolveHostPath` 无额外 IO |
| CTest `gow_mod_fn_chain` | C++ 单测 | 装饰链顺序、`replace` 清空语义、地址越界返回 false |

CTest 用例注册到 `tools/test/guest-calls.cmake`（现有 10 个 `gow_*` 用例都在 `:44-94`），并把名字加进 `modules/verify.ps1:28` 的 `-R` 正则里。新增 `mod_manager_tests.py` / `mod_planner_golden.py` 加进 `verify.ps1` 的调用列表——注意 `verify` 的定位是「Regression gate independent of copyrighted game data」（`verify.ps1:1`），所以这些测试**不能依赖 ISO 或游戏数据**，全部用合成 fixture。

### 22.3 现有必跑清单（`AGENTS.md` 要求）

| 场景 | 必跑 |
|---|---|
| pipeline 改动 | `python -I tools/test/pipeline_tests.py`；Linux 侧另加 `linux_pipeline_tests.py` |
| runtime / codegen 改动（含 `67-mod-hooks.patch`） | `build.cmd -Stages verify`（13 步，含 10 个 CTest、VU1 等价、guest-call 检查） |
| patch 栈改动 | `tools/test/patch-stack-tests.ps1`（已在 verify 内） |
| launcher 文案 | `python -I tools/test/launcher-languages.py`（已在 verify 内） |
| launcher 页面/路由改动 | `regional-play-ui.py`、`disc-import-ui.py`、`qte-controls.py`、`loading-progress.py`、`gow_region_tests` target |
| 区域路由改动 | `register-region-tests.py` + 上述 UI 测试 |
| 纹理包相关 | `tools/test/session-game-smoke.py --texture-pack`（`--detailed` 不能当 FPS 基准） |
| 光盘导入改动 | `tools/disc/import_test.py`、`prepare_test.py`、`disc-import-ui.py` |

`build.cmd -Stages verify` 的 13 步见 `modules/verify.ps1:5-32`；它**不建立帧等价或 FPS 结论**（`AGENTS.md:274`），所以 A4 的帧率验收必须另跑 100 秒可见会话，不能拿 verify 通过冒充性能合格。

### 22.4 本副本的运行障碍与恢复步骤

如 2.7 所述，当前副本缺 `launcher/qml/`、`Textos.js`、`idiomas/`、`pruebas/`、`installer/setup.cpp`，且根不是 git 仓库。因此：

1. P0 先取得完整仓库的 `launcher/` 源码与 `installer/`，或用 `update.ps1 -Check` 指向的 release 包补齐；
2. 在此之前，只跑**不依赖 launcher 源码**的纯 Python 测试（schema / planner / fingerprint / conflict / transaction）与 CTest；
3. UI 测试标 `skip`，CI/本地输出里明确写「SKIP: launcher/qml missing」，不要伪装成 PASS；
4. 不要用 01–58 重放补丁来「复原」工作树（3.6 #1）。

### 22.5 验收矩阵（把第 4.3 节变成可执行项）

| 编号 | 验收 | 自动化 | 数据依赖 |
|---|---|---|---|
| A1 | 零 Mod 字节等价 | `mod_vanilla_equivalence.py` | 需游戏数据，@slow |
| A2 | plan 可复现 | `mod_planner_golden.py` | 无，进 verify |
| A3 | 事务可回滚 | `mod_transaction_tests.py` | 无，进 verify |
| A4 | FPS 在噪声内 | `session-game-smoke.py` 100 s ×3 | 需游戏数据 |
| A5 | 帧循环零 IO | 静态检查 + `GOW_PERF_DIAG` 采样 | 需游戏数据 |
| A6 | 发行包合规 | `verify_setup.py` + zip 内容断言 | 无 |

---

## 第 23 章　性能预算

### 23.1 分层预算

| 阶段 | 预算 | 依据 | 超限处理 |
|---|---|---|---|
| 管理器启动（Registry 扫描 + 指纹采集） | < 200 ms | 几十个包、6 个输入文件；纯本地 | 延迟到首次打开 Mods 页 |
| `plan` 计算 | < 50 ms | 纯内存图算法 | 缓存 planId，输入不变直接复用 |
| `apply`（无 L1） | < 2 s（纹理包硬链接） | 硬链接零拷贝；跨卷复制按实际磁盘 | 进度条 + 可取消 |
| `apply`（含 L1） | 构建时长（可能数十分钟） | `build.cmd` 决定，不由管理器控制 | 复用 `LoadingScreen` 进度协议 |
| 进程启动额外开销 | < 10 ms | 读两张 TSV + 建两张哈希表 | 表项过多时告警（> 5000） |
| 帧循环额外开销 | **0 次磁盘 IO、0 次动态分配** | 3.3 | 静态检查拦截 |
| VFS 每次 `lookup` | 一次字符串规范化 + 一次哈希查找 | `unordered_map` | 表为空时短路到原逻辑 |
| 纹理显存 | `GOW_TEXTURE_PACK_MB` 默认 1024，最小 64 | patch 52 实测 81 张 / 73 MB | 由 LRU 淘汰，报告 `evictions` |

**验收口径 A4**：以 patch 52 的实测为基线（船上战斗、100 秒、guest FPS 与截帧），开启 1 个纹理包 + 3 个 VFS 覆盖 + 1 个函数装饰后重测三次，差值需落在 run-to-run 噪声内。`AGENTS.md:274` 提醒 `verify` 不能证明 FPS，所以这项必须单独跑可见会话；`docs/research/regional-port-2026-11-02.md:129-134` 也强调「functional tests are not controlled A/B performance measurements」，不要拿功能测试当性能结论。

### 23.2 帧循环零 IO 的静态检查

在 `tools/mods/check_hotpath.py` 里对 `67-mod-hooks.patch` 的新增代码做词法检查，禁止出现：

```
std::ifstream / std::ofstream / fopen / std::filesystem::exists
toml:: / QFile / LoadImage / sleep / std::mutex / new / malloc
```

允许出现：`unordered_map::find`、`std::string_view` 比较、`std::atomic::fetch_add(relaxed)`、`parsePs2Path` 已有的规范化函数、`result.assign`。这条检查接进 `verify`，作为 A5 的自动化部分。

补丁头部还应写明「**Off = unchanged**」：空表时 `resolveHostPath` 只多一个 `if`，与 `texture-replacement.md:153-154` 对纹理补丁的要求一致。

### 23.3 显存与内存

- 预算取所有启用纹理 Mod 的最大值，不求和（13.1）；Planner 计算时 clamp 到 `[64, 4096]`。
- 多包合并后文件总数超过 20000 时告警（patch 52 的 `recursive_directory_iterator` 启动时全量扫描，包越大启动越慢）。
- staging 保留最近 3 代（15.5），每代含硬链接不占额外空间；若用了复制，按 LRU 清理并在报告里记 `linkMode=copy`。
- 不要把纹理预加载进内存：patch 52 没有 `GOW_TEX_PRELOAD`，那是设计文档里的规划项。

## 第 24 章　安全、供应链与版权

### 24.1 威胁模型

| 威胁 | 入口 | 缓解 |
|---|---|---|
| 压缩包炸弹 / 路径穿越 | 导入 | 条目预检、大小/数量上限、`safe_member`、`is_relative_to` |
| 伪装成配置的脚本 | 导入 | 可执行文件黑名单、`mod.toml` 禁 `exec/script/url` 字段、不执行第三方代码 |
| 声明低能力做高能力的事 | 导入 | capabilities ⊇ payload 一致性校验、能力互斥表（12.4） |
| 死变量 / 不存在的接口 | 启用 | 环境变量白名单（12.3）、`min_chain`、指纹匹配 |
| 抢同一资源导致静默覆盖 | plan | 资源键 + 冲突报告 + 确定性求解（第 14 章） |
| 覆盖身份文件 | 启用 | 13.2 基线文件黑名单（`SYSTEM.CNF` / ELF / TOC / PAK / `.disc_layout`） |
| 篡改已安装包 | 运行期 | `.installed.json` 哈希、每次 plan 抽查、只读包目录 |
| 隐私泄露 | 报告 | 20.5 导出白名单 |
| 供应链（第三方 Mod 包） | 分发 | 无自动下载、无网络访问、签名可选、UI 显示能力与来源 |

**签名**：`mod.toml` 可选 `[signature]`（`algo = "ed25519"`, `pubkey`, `sig`），覆盖包内所有 payload 文件的规范化哈希列表。P0 不强制，P4 起对 `high risk` 能力强制要求签名或二次确认。工程本身没有 PKI，不要引入在线验签；公钥由玩家自行导入并本地保存。

### 24.2 沙箱边界

管理器能做的：写 `data/mods/`、追加 `engine/patches/NN-*.patch`、设置启动时环境变量、生成 staging 目录、调 `build.cmd`。

管理器**绝不**做的：改 ISO / 解包目录基线 / ELF / `.text`；改 `games/` / `engine/runtime.toml` / `tools/pipeline/`；直接编辑 `engine/runtime/`；加载任意 DLL 或执行脚本；写 `gow-native.boot` 作为常规路径；运行中替换内存卡；联网。

### 24.3 版权边界（再确认）

`CREDITS.md:30-33`：镜像、可执行文件、游戏数据、由它们生成的 C++、录制微码都不属于本仓库。`AGENTS.md:299-303, 353, 367, 374`：纹理包 / dump / 截图 / 第三方补丁 / ISO / VU1 分析缓存 / task corpora / `gow-native.boot` 一律不得提交或打包。`distribution.ps1:59` 的白名单只有 10 项且不含 `data/`。

因此 Mod 管理器的可分发物是：源码、`mod.toml` 规范、示例包（**只含声明，不含资源**）、测试 fixture、文档、补丁文本。玩家自备的资源通过 16.1 入口 B 登记，路径不进任何报告。

### 24.4 `xdelta` 的特殊处理

再强调一次 2.5 的结论：`-Stages xdelta` 写的是 ISO，与主线冲突。把它保留为「导入来源」的一次性离线操作，默认禁用，并加四道闸：① 二次确认「此操作会生成一份新的 ISO 文件」；② 磁盘空间预检（输出 ISO 约 8 GiB 量级）；③ 校验 base 的 `.text SHA-1` 与 `game.toml` 一致；④ 记录 base/delta/output 三个哈希到 `data/mods/reports/`，产物只留在 `data/mods/isos/`，`update.ps1` 用 `/XD data` 保证升级不碰它。任何把 xdelta 产物塞进发行包的行为都应由 `verify_setup.py` 拦截。

## 第 25 章　分阶段路线图 P0–P6

| 阶段 | 目标 | 改动文件 | 验收 | 主要风险 |
|---|---|---|---|---|
| **P0　地基** | 取得完整 `launcher/` 源码；登记现状偏差；建立 `data/mods/` 骨架与 `tools/mods/` 目录 | `docs/`（偏差登记）、`AGENTS.md`、`tools/mods/modspec.md` | 4 个 UI 测试不再 `FileNotFoundError`；`AGENTS.md` 页面编号表更新 | 当前是裁剪副本（2.7）；缺 49 号补丁，不可重放 |
| **P1　只读核心** | 实现 Fingerprint + Registry + Validator + Planner（Python CLI 版），产出 `plan.json` | `tools/mods/*.py`、`tools/test/mod_*_tests.py` | A2；golden 用例全绿；接进 `verify.ps1` | Ordinal 排序与 PowerShell 不一致；区域地址表漏项 |
| **P2　钩子和最小 UI** | 写 `67-mod-hooks.patch`（VFS 表 + 函数装饰链），新增 `ModsModel` + `ModsPage`，`pagina=9` | `engine/patches/67-*.patch`、`launcher/*`、`tools/test/mod-manager-ui.py` | A1、A5；`build.cmd -Stages verify` 全绿；`launcher-languages.py` 通过 | 钩子时机必须在 `applyMatching` 之后；QML 文案键同步 |
| **P3　事务与诊断** | Applier 三阶段、WAL、崩溃恢复、`mod-report.json`、最小复现包 | `launcher/src/mods/*`、`tools/mods/journal.py` | A3；崩溃注入测试；报告白名单检查 | Windows 文件占用导致 replace 失败（沿用 `replace_file` 退避） |
| **P4　四类 Mod 全覆盖** | `texture_pack` 多包合并、`vfs_override`、`env`、`save`、FMV/音频映射；旧 Accessibility 设置迁移 | `tools/mods/handlers/*`、`AccessibilityPage.qml` | A4（100 s ×3 会话）；纹理 hits/evictions 报告；旧设置不丢失 | 多包同名键；死变量被误写；`GOW_MC0` 热替换 |
| **P5　高级能力** | `function_override` 带区域地址表、`pak_remap` 影子解包目录、`external_injector` 登记 | handlers + `pak_remap` 影子目录生成 | 地址越界/区域缺失用例；磁盘预检；不写回基线 | 影子目录几 GB；LSN 重指容易出错 |
| **P6　L1 与发布** | `source_patch` 链尾追加 + 重建触发 + 指纹重采集；示例包、文档回写、发行合规检查 | `tools/mods/patch_handler.py`、`README.md`、附录 H 清单 | 构建失败自动摘除补丁；A6；`README.md` 的「planned」措辞更新 | `patchChainHash` 变化导致所有 Mod 需重校验；PGO manifest 失配 |

**每个阶段的共同门槛**：`build.cmd -Stages verify` 必须通过；`data/_package/gow-native-pc-windows.zip` 内容断言必须不含任何 Mod 资源；`AGENTS.md` 随架构变化同步更新（`AGENTS.md:3` 的明示要求）。

**依赖顺序**：P1 的 Planner 不依赖 P2 的钩子（纯 Python，可先跑）；P2 的钩子是 P4/P5 的前提；P6 必须最后做，因为它会改变指纹并牵动所有已启用 Mod。

## 第 26 章　风险登记册

| # | 风险 | 概率 | 影响 | 缓解 | 触发信号 |
|---|---|---|---|---|---|
| R1 | 裁剪副本缺 `launcher/` 源码，UI 与部分 verify 无法跑 | 高 | 高 | P0 前置；测试诚实标 SKIP | `copytree` 报 FileNotFoundError |
| R2 | 补丁链缺 49 / 两个 52，重放补丁得到错误运行时 | 中 | 高 | 只用当前工作树；`patchChainHash` 记录现状 | `git apply` 失败、`GSSwBackend` 相关符号缺失 |
| R3 | `replaceFunction` 地址因区域/重建而错位 | 中 | **严重** | 七元组指纹 + 按区域地址表 + 不匹配即拒绝 | 随机崩溃、VU1 比对失败 |
| R4 | 帧循环里做了磁盘 IO | 中 | 高 | 规划期算完 + 静态检查 `check_hotpath.py` | FPS 抖动、`GOW_PERF_DIAG` 异常 |
| R5 | 多个 Mod 静默互相覆盖 | 高 | 中 | 资源键 + 冲突报告 + 确定性排序 | 玩家反馈「装了没效果」 |
| R6 | 死变量被写进 env | 中 | 低 | 白名单 + 静态扫描一致性测试 | 设置无效果 |
| R7 | L1 重建失败留下链尾坏补丁 | 中 | 高 | WAL 自动摘除 + 重新采集指纹 | `patch X does not apply` |
| R8 | 把游戏衍生数据打进发行包 | 低 | **严重**（法律） | 导入黑名单 + zip 内容断言 + 白名单复核 | zip 里出现 `.png`/`.wad`/`.iso` |
| R9 | 隐私路径进会话报告 | 中 | 中 | 20.5 导出白名单 | 报告里出现 `C:/Users/…` |
| R10 | 两个 launcher 实例并发改状态 | 低 | 中 | `state.lock` 独占句柄 | state.json 半截 |
| R11 | 玩家改了构建但没重新 plan | 高 | 高 | 11.6 `stale` 标记，UI 阻断启动 | `fingerprintId` 不一致 |
| R12 | `pak_remap` 影子目录耗尽磁盘 | 中 | 中 | 空间预检 + 硬链接 | 复制阶段失败 |
| R13 | 旧 Accessibility 纹理开关与新 Mods 页抢 `GOW_TEXTURE_PACK` | 中 | 中 | 20.4 迁移 + 代理读写 | 开关状态与实际生效不符 |
| R14 | `gow-native.boot` 被误当常规配置入口 | 中 | 低 | `main.cpp:150` 事实写进文档；Launch Bridge 不写它 | 设置了却没生效 |

## 第 27 章　反模式与常见问题

1. **「先复制文件试试看」** — 没有指纹与冲突求解的复制，在本工程里等于把随机崩溃交给玩家。先 `validate` → `plan` → 再 `apply`。
2. **改 ISO / 解包目录基线** — 违反铁律一；会连锁破坏 `identify.py`、`recompile.py`、`register_region.py` 三处校验。
3. **直接编辑 `engine/runtime/`** — `fetch` 会拒绝或冲掉；编译期注入只能追加链尾 patch。
4. **在 `resolveHostPath` 里读 TOML / 查文件** — 帧循环零 IO 是硬约束；表必须启动期建好。
5. **把 F1 菜单当 Mod 开关** — `gow_vivo::cargar()` 只读一次 env；参数 Mod 是启动期概念。
6. **用 `gow-native.boot` 传 Mod 参数** — 有 ELF 参数启动时它根本不被读取。
7. **找「运行时文本函数」来做中文补丁** — 不存在；`R_PERM.WAD` 由 TOC/LSN 离线读取，走 `pak_remap` 或 `host0:` VFS 覆盖。
8. **让多个纹理 Mod 各自设 `GOW_TEXTURE_PACK`** — 该变量只接受一个目录；必须合并到 staging。
9. **假设 PCSX2 的 dump 规则、dump 环境变量、`-any.png` 存在** — 那是 `texture-replacement.md` 的设计，patch 52 用的是另一套命名与变量。
10. **把 `PS2X_GS_ESCALA` 等死变量写进参数档** — 无 reader。
11. **用 `--3way` 应用补丁** — 多数补丁无 `index` 行；用 `patches.ps1 start/export/drop`。
12. **把 `data/mods/` 加进发行白名单** — 直接违反 `distribution.ps1:59` 与 `CREDITS.md`。
13. **认为 `verify` 通过就证明 FPS 没问题** — `AGENTS.md:274` 明说它不建立帧等价或 FPS 结论。
14. **在同一个补丁编号上追加 Mod** — Ordinal 排序与前缀树推演会失败；编号由管理器集中分配。

**Q：为什么不做成游戏内 Mod 菜单？** 因为 F1 菜单属于 runtime 补丁，且 `gow_ajustes_vivo.h` 只读一次环境；改它要重编译，还把 UI 与游戏线程耦合。launcher 侧做，改一次编译一次，之后全靠数据。

**Q：装了 Mod 但没效果，先查什么？** ① `mod-report.json` 里该 Mod 是否在 `active`；② `fingerprintId` 是否与 `state.json` 一致（R11）；③ 冲突表里它是不是输家；④ 该能力对应的环境变量是否在白名单且有 reader；⑤ 纹理类看 `GOW_TEX_PCSX2_NAMES` 差集。

**Q：能不能热切换 Mod？** 不能。env 只在启动读、纹理包只在 `TexturePack::open()` 扫一次、卡在运行中常驻内存、函数表在 `loadELF` 时装。所有切换都要求「下次启动生效」，UI 必须如实标注。

---

# 附录

## 附录 A　`mod.toml` 完整示例

### A.1 纹理包（本地资源登记）

```toml
schema = 1
id = "acme.hd-ui"
version = "2.1.0"
title = "HD HUD（PCSX2 格式）"
capabilities = ["texture_pack"]
priority = 200
[target]
game_id = "gow1"
compatibility = "code-compatible"
runtime_commit = "any"
patch_chain = "any"
min_chain = 52
[[payload]]
type = "texture_pack"
capability = "texture_pack"
path = "textures"
  [payload.options]
  naming = "pcsx2"
  budget_mb = 768
  alpha = "gs-128"
```

### A.2 VFS 覆盖（含 `host0:`）

```toml
schema = 1
id = "acme.alt-movie"
version = "1.2.0"
title = "替换开场 FMV"
capabilities = ["vfs_override", "env"]
[target]
game_id = "gow1"
compatibility = "code-compatible"
regions = ["usa", "asia"]
[[payload]]
type = "vfs_override"
capability = "vfs_override"
path = "files"
  [[payload.options.mappings]]
  guest = "cdrom0:\\MOVIE\\OPEN.PSS;1"
  file = "files/open.pss"
  sha256 = "…"
[[payload]]
type = "env"
capability = "env"
path = "."
  [[payload.options]]
  key = "GOW_MOVIE_OVERRIDE"
  value = "OPEN_ALT"
  strategy = "append"
```

### A.3 函数覆盖（按区域地址表）

```toml
schema = 1
id = "acme.no-blur"
version = "0.9.0"
title = "关闭动态模糊（实验）"
capabilities = ["function_override"]
priority = 300
[target]
game_id = "gow1"
compatibility = "exact"
[[payload]]
type = "function_override"
capability = "function_override"
path = "func"
  [payload.options]
  signature = "ps2_recompiled"
  chain = "decorate"
  symbol = "gowModNoBlur"
    [payload.options.addresses]
    usa = "0x00188B80"
    europe = "0x001891F0"
    japan = "0x00189500"
```

> 启用前需确认 `gowModNoBlur` 已由 `source_patch` 编进 runner，否则只能选用 `67-mod-hooks.patch` 预置的通用钩子。

### A.4 参数档（低风险）

见 10.3 的 `acme.clean-look`，是唯一允许 `compatibility = "any"` 的类型。

## 附录 B　状态文件 schema 摘要

| 文件 | 关键字段 | 写入者 | 原子性 |
|---|---|---|---|
| `profiles/<name>.toml` | `enabled[]`, `order_override[]`, `settings`, `resolutions`, `allowAnyCompatibility`, `allowHighRisk` | UI | `atomic_json` 同款 |
| `state.json` | `activeProfile`, `activePlanId`, `lastFingerprintId`, `stale`, `journal`, `restorePoints[]` | Applier | `.tmp` + `replace` |
| `fingerprint.json` | `fields{}`, `inputs{}`, `fingerprintId`, `collected_at` | Fingerprint | 同上 |
| `plans/<id>/plan.json` | 见 17.4；**无时间字段** | Planner | 只追加 |
| `journal/<id>.wal` | JSONL `{seq,op,from,to,undo,shaBefore,shaAfter}` | Applier | append + flush |
| `reports/<session>/mod-report.json` | 见 21.2 | Diagnostics | 只追加 |
| `.installed.json` | `packageRootHash`, `files{}`, `imported_at`, `source` | 导入器 | 只写一次 |

## 附录 C　C++ 代码骨架清单

| 文件 | 内容 |
|---|---|
| `launcher/src/mods/Fingerprint.{h,cpp}` | 七元组采集、`patch_chain_hash`、`diff()` |
| `launcher/src/mods/Registry.{h,cpp}` | 包索引、`ModMeta` |
| `launcher/src/mods/Planner.{h,cpp}` | 14.3 算法、plan 序列化 |
| `launcher/src/mods/Applier.{h,cpp}` | 三阶段事务、WAL |
| `launcher/src/mods/handlers/*.cpp` | 九个 `PayloadHandler` 实现 |
| `launcher/src/mods/Journal.{h,cpp}` | WAL 读写与倒序 undo |
| `launcher/src/mods/Diagnostics.{h,cpp}` | 报告与最小复现包 |
| `launcher/src/mods/LaunchBridge.cpp` | 18.1 env 合成 |
| `launcher/src/ModsModel.{h,cpp}` | 20.2 QObject 接口 |
| `PS2R/include/runtime/mod_vfs_table.h` + `PS2R/src/lib/mod_vfs_table.cpp` | 18.2 只读覆盖表 |
| `PS2R/src/lib/mod_function_hooks.cpp` | 18.4 装饰链 |
| `engine/patches/67-mod-hooks.patch` | 上述 C++ 的统一 diff + 头部说明 |

所有 C++ 用工程现成的 clang / C++17；不引入新第三方库；JSON 用 `QJsonDocument`（launcher 侧）与手写极简解析（runtime 侧，避免给运行时加依赖）；TOML 解析复用 runtime 已有的 `toml` 头或由 Python CLI 预转换成 JSON 后交给 C++。

## 附录 D　Python CLI 命令表

```
python -I tools/mods/gow_mods_cli.py validate <path> [--level=all|schema|content|compliance]
python -I tools/mods/gow_mods_cli.py import <path> [--as=<id@version>]
python -I tools/mods/gow_mods_cli.py register-assets <dir> --type=texture_pack|save
python -I tools/mods/gow_mods_cli.py fingerprint [--json] [--diff <selector.toml>]
python -I tools/mods/gow_mods_cli.py plan [--profile=daily] [--out=<plan.json>]
python -I tools/mods/gow_mods_cli.py apply <planId> [--dry-run]
python -I tools/mods/gow_mods_cli.py rollback [<planId>]
python -I tools/mods/gow_mods_cli.py report <session> [--repro]
python -I tools/mods/gow_mods_cli.py check-hotpath <patch>
```

`plan/apply` 与 C++ 版共用同一 schema；`--dry-run` 只跑 stage 不 commit，用于排障。

## 附录 E　错误码表（摘要）

| 前缀 | 含义 | 例子 |
|---|---|---|
| `E_SCHEMA_*` | TOML 字段/类型/枚举错误 | `E_SCHEMA_UNKNOWN_CAPABILITY` |
| `E_PATH_*` | 路径穿越、符号链接、绝对路径 | `E_PATH_TRAVERSAL` |
| `E_SIZE_*` | 包/文件超上限 | `E_SIZE_BOMB` |
| `E_HASH_*` | sha256 不匹配 | `E_HASH_MISMATCH` |
| `E_FORBIDDEN_*` | 游戏数据/可执行文件黑名单 | `E_FORBIDDEN_ISO` |
| `E_CAP_*` | 能力不一致、互斥、高危未确认 | `E_CAP_MUTEX` |
| `E_TARGET_*` | 指纹不匹配、区域地址缺失、min_chain 不满足 | `E_TARGET_TEXT_SHA1` |
| `E_ENV_*` | 前缀非法、死变量、键被 forbid | `E_ENV_UNKNOWN` |
| `E_DEP_*` | 依赖缺失、版本区间不可满足、环 | `E_DEPENDENCY_CYCLE` |
| `E_CONFLICT_*` | 硬冲突（C4） | `E_HARD_CONFLICT` |
| `E_PATCH_*` | `git apply --check` 失败、编号冲突 | `E_PATCH_NO_APPLY` |
| `E_PIPELINE_BUSY` | `data/pipeline.lock` 被占用 | — |
| `E_STATE_*` | state.lock 占用、WAL 未完成 | `E_STATE_LOCKED` |

错误输出格式统一为 `CODE: <人类可读原因> | file=<路径> | expected=… | actual=…`，与工程现有的长错误信息风格一致。

## 附录 F　真实可用的环境变量速查表（节选）

**只列工作树里确有 `getenv` reader 的键**；完整表由 `tools/mods/env_allowlist.json` 静态扫描生成并人工复核。

| 变量 | 作用 | 读者 |
|---|---|---|
| `GOW_TEXTURE_PACK` / `_MB` / `_STATS` | 纹理包目录 / 显存预算 / 统计 | `gs_hw_backend.cpp:1197,1200,1287` |
| `GOW_TEX_PCSX2_NAMES` | 写出被采样纹理名清单 | `gs_hw_backend.cpp:1152` |
| `GOW_SCALER` / `GOW_SHARPEN` / `GOW_ANISO` / `TOBIICHI_FXAA` / `TOBIICHI_ASPECTO` / `TOBIICHI_FPS_GOSTER` | 后处理与显示 | `gow_ajustes_vivo.h:27-43` |
| `TOBIICHI_VSYNC` / `TOBIICHI_VENTANA_FPS` | VSync / 窗口帧率上限 | `gow_trucos.cpp:730`、`gow_integracion.cpp:416` |
| `GOW_AUDIO` / `GOW_AUDIO_DEVICE` / `GOW_AUDIO_PCM` / `GOW_AUDIO_RAW` / `GOW_AUDIO_STATS` | 音频 | `ps2_runtime.cpp`、`ps2_audio_device.cpp:41`、`sound_engine.cpp` |
| `GOW_SKIP_FMV` / `GOW_FAST_BOOT` / `GOW_MOVIE_OVERRIDE` / `GOW_BONUS_MOVIE` / `GOW_MPEG_DIAG` | FMV | `gow_overrides.cpp:1119,1171,2105,2099` |
| `GOW_ISO` / `GOW_CD_TRACE` | 光盘来源 / 扇区读跟踪 | `gow_overrides.cpp:1833`、`iop_cdvd.cpp:238` |
| `GOW_MC0` / `GOW_MC1` / `GOW_SAVES_DIR` | 内存卡 / 存档快照 | `iop_emulator.cpp:138`、`ps2_debug_panel.cpp:2233` |
| `PS2X_GS_WORKER` / `PS2X_GS_HW_SCALE` / `GOW_GS_*` | GS 线程与分辨率 | `ps2_memory.cpp:281`、`gs_hw_backend.cpp` |
| `GOW_VU1N_X64` / `GOW_VU1_CAPTURA` / `GOW_VU1_CAPTURE_MISSES` | VU1 JIT / 录制 | runtime 多处 |
| `GOW_PERF_DIAG` / `GOW_FRAME_DIAG` / `GOW_IOP_DRIFT` / `GOW_VU1N_DIAG` | 诊断 | `ps2_perf.h` 等 |

**明确不可用（死变量 / 设计文档虚构）**：`PS2X_GS_ESCALA`、`PS2X_GS_HW`、`PS2X_GS_NITIDO`、`PS2X_GS_ESCALA_DINAMICA`、`PS2X_GS_SHADER_CACHE_DIR`、`GOW_TEX_DUMP`、`GOW_TEX_REPLACE`、`GOW_TEX_DIAG`、`GOW_TEX_PRELOAD`、`GOW_TEX_DUMP_MIN`、`GOW_TEX_REPLACE_DIR`。

**非环境变量**：`GOW_NATIVE_BOOT_V1`（`gow-native.boot` 文件头魔数）。

## 附录 G　术语表

| 术语 | 含义 |
|---|---|
| EE / IOP / GS / VU1 / SPU2 | PS2 的主 CPU / 协处理器 IO / 图形合成器 / 向量单元 / 声音处理器 |
| 静态重编译 | PS2Recomp 把 MIPS R5900 ELF 转成 C++，再由 clang 编成 `ps2EntryRunner.exe` |
| ordinal 补丁链 | `engine/patches/NN-*.patch` 按文件名 Ordinal 序 `git apply` 的补丁序列 |
| `replaceFunction` | 运行时替换生成函数表表项的 API，签名 `(uint8_t*, R5900Context*, PS2Runtime*)` |
| `resolveHostPath` | EE 侧 guest 路径 → 宿主路径的唯一集中映射 |
| LSN / TOC / PAK / `.disc_layout` | 光盘扇区号 / 24 字节条目索引表 / 大包文件 / 解包目录的扇区清单 |
| `PackKey` | patch 52 的纹理身份 `(texHash, palHash, bits)` |
| 指纹 / `fingerprintId` | 描述「这份二进制怎么造出来的」七元组及其哈希 |
| plan / `planId` | 一次确定性求解的产物 / 其 SHA-256 前 16 位 |
| staging | plan 的物化目录（合成纹理、VFS 文件、影子解包目录） |
| WAL / 还原点 | 事务日志 / 可一键切回的旧 `activePlanId` |
| profile | 用户意图（启用哪些 Mod、settings、裁决），不含派生状态 |

## 附录 H　与现有文档的偏差登记（需回写）

| # | 现有文档 | 当前说法 | 实际 | 建议回写 |
|---|---|---|---|---|
| 1 | `README.md:304` | 「texture dump and replacement is designed, not implemented」 | patch 52 已实现 PCSX2 格式纹理包 | 改为「texture packs implemented (patch 52); general mod manager planned」 |
| 2 | `README.md:33` / `README.pt-BR.md` / `docs/releases/v0.3.0–v0.4.0` | 「texture packs / ISO mods planned」 | 纹理包已落地；xdelta stage 已存在但只做 ISO 导入 | 拆分措辞，区分「已实现」与「规划」 |
| 3 | `docs/research/texture-replacement.md` | 自称 design only，定义自定义 hash、`GOW_TEX_*`、`pack.toml`、dump | 与 patch 52 全面不一致 | 在文件头加「Superseded by patch 52」并保留作为历史设计记录 |
| 4 | `docs/research/README.md:8` | 同上 | 同上 | 同步标注 |
| 5 | `docs/input-accessibility.md:61-62` | 「not a claim that a general mod manager is implemented」 | 仍准确，但需给新方案留链接 | 追加指向本文档 |
| 6 | `AGENTS.md:44-46` | `pagina` 0..8 | 新增 Mods 页应为 9 | 更新编号表 |
| 7 | `AGENTS.md:57-58` | `data/` generated list | 需加入 `data/mods/` 与 `data/mods/isos/` | 补两行 |
| 8 | `AGENTS.md:299-303` | 纹理包 / xdelta 合规条款 | 需要补「Mod 包只含声明与差分」 | 增加一段 |
| 9 | `docs/research/roadmap-2026-10-27.md` | Phase 4 补丁 42-43 用于纹理 | 实际用了 52；42-43 已占用 | 标注废弃编号 |
| 10 | `engine/README.md:67` | launcher Graphics 页设 `GOW_TEXTURE_PACK` | checked-in `lanzador.cpp` 无此设置；开关在 Accessibility | 更正页面名与源码位置 |
| 11 | `docs/architecture.md` | 数据流图 | 需加 ModsModel / `data/mods/` 一条 | 补图 |
| 12 | `docs/RENDER-PIPELINE-HANDOFF-2026-11-04.zh-CN.md:143,173` | 缺 49、别破坏纹理包路径 | 仍准确，且是 P0 的重要前提 | 在本文档 P0 引用 |

---

## 结语

这套方案的全部复杂度都花在一件事上：**让「装了什么」与「正在运行的这份 C++ 二进制」之间保持可验证的对应关系**。文件放哪里、开关怎么画、纹理怎么合并，都是简单部分；真正决定成败的是指纹、冲突求解与事务回滚这三块，以及「ISO 只读、runtime 由 fetch 管控、帧循环零 IO」这三条不能商量的边界。

如果你要动手，建议的顺序是：**先按附录 H 把文档偏差改掉，再跑通 P0 的完整源码环境，然后只实现 P1 的 Python Planner 并用 golden 用例把确定性钉死**——后面所有 C++ 与 QML 工作，都是在这份确定性之上加壳。反过来先做 UI，很容易做成一个好看但不可复现、一崩就查不出来的开关集合。

---

*本文档为设计方案，尚未实现。文中所有「已实现」结论均基于 2026-11-05 对 `<repo>` 工作副本的只读调研；工程升级后请重新核对附录 H 与真实代码。*







