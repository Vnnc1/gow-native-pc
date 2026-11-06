# 老显卡上的 OpenGL 渲染器：设计、落点与帧率工程

**项目**：gow-native-pc —— God of War（PS2）静态重编译原生移植
**对象**：GS（Graphics Synthesizer）的 OpenGL 后端，即 `PS2X_GS_RENDERER=hw` 这一条路径
**版本**：v1.0 · 2026-11-05
**适用机器**：2010–2015 年的集显与入门独显（Intel HD 4000/4400/4600、GeForce GT 620M–920M、Radeon HD 6450–R7 240 这一档），共同特征是 **只保证 OpenGL 3.3，多数能给到 4.3，没有可用的 compute 性能，填充率与带宽极低，驱动对“现代 GL 用法”的实现质量参差**
**证据等级**：本文所有数字都带标签 —— `【实测】` 表示本仓库记录过的真机运行结果（机器与设置随数字一起给出），`【文档】` 表示可在源码、行号、配置里核对的事实，`【推断】` 表示由前两者外推、尚未在本工程验证的结论。**本文没有新增任何一次真机运行**，引用的是仓库已有的记录。

---

## 摘要（先读这一页）

### 一句话结论

**不要写第二个渲染器。给现有的 `GSHwBackend` 做能力分层（capability tiering），把“每批次 CPU 成本”和“每像素填充成本”这两堵墙分别拆掉，并用一条带滞回的分辨率阶梯把工作点自动停在两墙的交叉点上。**

### 三条支撑判断

1. **现有的 GL 后端不是“错的架构”，它的问题是“没有档位”。** 它已经具备顶点环、纹理仓库、shuffle 通道、`Present` 共享纹理、失败回退提示这些正确的地基；缺的是“我在这块卡上应该走哪条路径”的运行时判断。`【文档】` `gs_hw_backend.cpp` 3634 行，全部逻辑硬编码为 GL 4.3 core。
2. **老显卡上的帧率不是单一瓶颈，而是两条互不相交的曲线取 max。** 一次实测把这件事钉死了：同一台 i3-4170 + HD 4400，内部 1.00× 时 24.3 guest fps，0.50× 时 40.4，0.35× 时 41.9 `【实测】`（`low-spec-renderer.patch` 头注释）。1.0×→0.5× 涨 16 帧，0.5×→0.35× 只涨 1.5 帧。前者在付填充率的账，后者已经撞到提交成本的墙。
3. **已经证伪的手段不能再走。** 本仓库在 Intel HD 4400 上实测过：每批次 std140 UBO 更慢（53–55 → 50.7 fps）、GL 状态去重缓存更慢（53–55 → 37–40 fps）、调色板图集批次几乎不降、canonical 状态比较 `gs_ms` 反而略升 `【实测】`。这些结论与“通用图形学常识”相反，但它们是这台机器上的事实。**任何新设计必须先把这三条当作约束，而不是当作待验证的猜想。**

### 这份文档回答什么

| 你的问题 | 看哪一章 |
|---|---|
| “OpenGL 显卡模式”到底指什么，和现在的 `hw` 后端什么关系 | 第 1 章 |
| 我该从哪个文件、哪个函数开始动手 | 第 2 章 |
| 为什么老显卡慢，慢在哪，怎么算这笔账 | 第 3 章 |
| 新渲染器的结构怎么设计，分几档，每档什么能力 | 第 4 章 |
| 具体代码怎么写（能力加载、驱动画像、顶点环、变体、脏矩形、合批、阶梯） | 第 5 章 |
| 怎么做到“没有 bug”，或者至少做到“bug 活不过一天” | 第 6 章 |
| 从 41 帧到 60 帧的账怎么算，先做哪一刀 | 第 7 章 |
| 六周怎么排期，每个冲刺的验收数字 | 第 8 章 |
| 交付物、开关表、回退方案 | 第 9、10 章 |

### 三条阅读路径

这份文档十六章，没人需要一次读完。按你的角色选一条：

**路径 A：我今天就要动手（约 1 小时）**
读 2.3（五个入口）→ 2.6（怎么出补丁）→ 16.10（如果只能做一件事）→ 11（一天内跑通）。跳过所有理论，直接照清单做。遇到看不懂的名词，回 10.3 查术语表。

**路径 B：我要决定这条路值不值得走（约 40 分钟）**
读摘要 → 3.5（双墙模型）→ 7.1（每帧预算）→ 7.4（已证伪清单）→ 16.9（累计效果）。这五节加起来能回答“能到多少帧、要花多久、哪些路是死的”。

**路径 C：我接手维护，要防止踩坑（约 2 小时）**
读 6（无 bug 方法）+ 6.9（黑屏复盘）+ 12（反模式）+ 13（测量）+ 附录 F（日志解读）。这条路不教你怎么优化，教你怎么不把事情搞坏 —— 对一个已经有 66 个补丁的工程来说，后者更重要。

### 读之前，先花五分钟确认你的机器

本文所有判断都建立在“这是一块 GL 4.3、20 EU、共享内存的集显”之上。你的机器如果不同，结论会变。五分钟自检：

```bat
:: 1. 你的卡给的是哪个 GL 版本、什么设备
（跑起来看 [gs-hw] caps 那一行，或 Sprint 0 之后看 caps 日志）

:: 2. 现在是多少帧（别看窗口 Hz）
set GOW_PERF_DIAG=1 & set GOW_PERF_FRAME_PC=0x183BB8 & play-jpn.cmd

:: 3. 渲染器占多少（丢弃绘制后的天花板）
set PS2X_GS_DISCARD_DRAWS=1 & play-jpn.cmd
```

三个数出来，你就知道该读第 7 章（渲染器是瓶颈）还是该去读 VU1 的文档（不是）。**在确认这三点之前读优化章节，是在读别人的答案。**

### 本文不覆盖什么

写清边界和写清内容一样重要，否则读者会拿它去解决不该由它解决的问题：

| 不覆盖 | 为什么 | 该看哪里 |
|---|---|---|
| CPU 软光栅器（`PS2X_GS_RENDERER=sw`） | 它是“无 GL 兜底 + 逐像素对照基准”，2–5 Hz，不是性能路径；兜底本身已经实现 | 第 1.1 节的表；源码 `gs_sw_backend.*` |
| VU1 JIT / AOT 内部 | 那是另一条完整的技术栈（JIT 发射器、块链接、快模式） | `docs/research/vu1-x64-jit.md`、补丁 18/27/51/60 |
| IOP、SPU2、手柄、记忆卡、MPEG | 与渲染无关 | `docs/architecture.md` |
| 启动器安装流程与打包 | 本文只讲设置项怎么暴露（第 14 章） | `launcher/`、`installer/setup.cpp` |
| Linux 构建路径 | 共用 GS 代码，但渲染器验证只在 Windows 上做过 | `docs/linux.md` |
| 纹理包（`GOW_TEXTURE_PACK`）的实现 | 它是替换素材的功能，不是性能功能 | 补丁 52、`docs/research/texture-replacement.md` |
| GoW II 及其它游戏 | 只有计划，没有可跑移植 | `games/gow2/README.md` |

**为什么要列这张表？** 因为“一份文档看起来什么都能解决”是最危险的状态。读者会花两小时在本文里找 VU1 的答案，然后得出“文档没用”的结论。明确说“这不归我管，去那里看”，比勉强写一段外行话有价值。

### 一句必须先说的实话

**“没有 bug”不是一个可以承诺的交付物。** 任何声称“零 bug”的渲染器设计书都在骗人。可以承诺的是另一件事：**让 bug 不可能静默存在**。做法是十条可断言的不变量（第 6.1 节）、一套确定性的黄金帧回归（第 6.4 节）、以及每条优化都带一个环境变量回退开关（第 10.1 节）。本工程历史上最贵的三个 bug —— 场景全黑、整帧花屏、几何撕裂 —— 全部是“状态与生命周期不同步”，不是“算法写错”。这类 bug 恰好是可以被断言抓住的。这就是本文所谓“无 bug”的真实含义。

---

## 目录

- [1. 先把问题定义清楚](#1-先把问题定义清楚)
- [2. 从哪里开发：落点地图](#2-从哪里开发落点地图)
- [3. 老显卡的真实硬件模型](#3-老显卡的真实硬件模型)
- [4. 渲染器架构设计 v2](#4-渲染器架构设计-v2)
- [5. 关键子系统的实现](#5-关键子系统的实现)
- [6. 无 bug 的工程方法](#6-无-bug-的工程方法)
- [7. 帧率工程：从 41 到 60 的账](#7-帧率工程从-41-到-60-的账)
- [8. 落地路线：六个冲刺](#8-落地路线六个冲刺)
- [9. 交付物与验收](#9-交付物与验收)
- [10. 附录](#10-附录)
- [11. 一天内跑通：动手清单](#11-一天内跑通动手清单)
- [12. 反模式目录](#12-反模式目录)
- [13. 测量方法论](#13-测量方法论)
- [14. 与启动器、用户体验的衔接](#14-与启动器用户体验的衔接)
- [15. 从 v2 到 v3：还能往哪走](#15-从-v2-到-v3还能往哪走)
- [16. 完整案例：一台 24 帧的机器怎么调到 47](#16-完整案例一台-24-帧的机器怎么调到-47)
- [附录 D：常见问答](#附录-d常见问答)
- [附录 F：日志逐行解读](#附录-f日志逐行解读)

---

## 1. 先把问题定义清楚

### 1.1 “OpenGL 显卡模式”在本工程里的确切含义

PS2 的图形芯片叫 GS（Graphics Synthesizer）。它没有可编程着色器，是一台固定功能的、按 4 MB 嵌入式显存设计的、每像素 1–2 个周期的光栅化机器。本工程用三种后端去“成为”它：

| 后端 | 选择方式 | 实现 | 现状 |
|---|---|---|---|
| `GSHwBackend` | `PS2X_GS_RENDERER=hw`（默认） | OpenGL 4.3 core，把 GS 的固定管线翻译成纹理采样 + 片元着色器 + 混合状态 | 唯一可日常游玩的后端 |
| `GSSwBackend` | `PS2X_GS_RENDERER=sw`（或 `PS2X_GS_HW=0`） | CPU 软光栅，直接写共享 4 MiB 显存，逐像素 swizzle | 已实现（`gs_sw_backend.{h,cpp}`，由 00b3ca5 的 `GSCpuBackend` 复原并适配当前 `GSRasterBackend` 接口）；无 OpenGL 4.3 的显卡由它兜底 |
| `GSNullBackend` | 编译期/测试 | 什么都不做 | **未实现**：本工程没有空后端，基准测试用 `GSSwBackend` 的空 VRAM |

所以你说的“OpenGL 显卡模式渲染器”，在本工程里**不是从零新建一个东西**，而是：**把 `GSHwBackend` 从“一条 GL 4.3 硬路径”改造成“按设备能力自动选路的分层渲染器”，并且专门为填充率与提交成本都极差的老显卡准备一条低配路径。**

这个定义的差别决定了工作量差一个数量级：

- 新建渲染器：要重新实现 GS 的 TFX/TCC/IIP/ATE/ABE/DATE/Z 别名/CLUT/reinterpret/shuffle 全套语义，约 3000–4000 行，且必须与现有后端逐像素对齐 —— 工期以月计，bug 面翻倍。
- 分层改造：保留现有语义实现，把“怎么用 GL”抽成策略，约 800–1200 行增量 —— 工期以周计，bug 面收敛在状态与生命周期上，而这一类已经有成熟的审计方法（第 6.2 节）。

**本文选后者。** 这不是保守，而是这个工程已经用两次黑屏和一次整帧花屏换来的判断：`【实测】` 修复“场景全黑”花掉的时间，比写一个新的顶点路径多得多。

### 1.2 为什么“老显卡”需要单独一条路径

先把“老”量化。本工程的主力测试机是 i3-4170 + Intel HD Graphics 4400：

| 项 | 数值 | 含义 |
|---|---|---|
| EU 数量 / 频率 | 20 EU / 350–1100 MHz | 峰值约 352 GFLOPS，是 2020 年入门独显的 1/10 |
| 显存 | 共享 DDR3-1600，双通道约 25.6 GB/s | 独显的 1/10 到 1/15；且与 CPU 抢带宽 |
| 填充率 | 约 1.1 GPixel/s（理论），实测混合 + 采样下远低于此 | 1280×720 全屏一次 = 0.92 M 像素 |
| GL 版本 | 4.3 core（驱动支持），`【实测】` 4.6 拿不到，日志会打 `OpenGL 4.3 core context (4.6 unavailable)` | 本文的能力下限 |
| 驱动行为 | 状态重设比状态跳过快；UBO 比 glUniform 慢 | 与通用经验相反，见 3.4 节 |

关键推论有两条，后面每一章都会用到：

**推论 A：在这块卡上，“像素”比“指令”贵，但“批次”比“像素”更贵。**
1280×720 的窗口呈现一次要吃掉约 1/3 的呈现帧率（20.6 Hz vs 32.7 Hz，同一内部分辨率 412×360）`【实测】`。而 0.35× 相对 0.5× 几乎不涨帧（41.9 vs 40.4）`【实测】`，说明像素降到某个点之后就不再是瓶颈，剩下的全是每批次/每图元的 CPU 与驱动成本。

**推论 B：任何“减少 GL 调用次数”的优化，必须先用这台机器验证，不能靠常识。**
三条证伪记录（UBO、状态缓存、调色板图集）全部是“常识说该更快，实测更慢”。原因是 Intel 驱动在 draw 时对“未显式重设的状态”做整条管线重新校验，冗余的 setter 反而是廉价 fast path `【推断，但有 A/B 数据支撑】`。这条推论直接决定了第 4.5 节状态模型的写法：**默认全量显式设置，缓存必须是可选且按驱动画像开关的**。

### 1.3 帧率的三个来源，别混在一起

初学者最容易犯的错，是把三个数字当成一个：

| 数字 | 从哪来 | 它代表什么 | 怎么读 |
|---|---|---|---|
| `guest_flip_hz` | `GOW_PERF_FRAME_PC`（美版 `0x1837B8`，日版 `0x183BB8`）计数的游戏帧函数进入频率 | **真正的游戏帧率** | 唯一可以用来宣称“多少帧”的数字 |
| `host_hz` | 窗口呈现线程，默认限速 `TOBIICHI_VENTANA_FPS=60` | 窗口刷新次数，可能重复显示同一 guest 帧 | 不能当 fps 用 |
| `gs_ms` / `vu_ms` / `ee_ms` | `GOW_PERF_DIAG=1` 的 `[gow-perf]` 行 | 5 秒窗口内的**累计忙时** | 除以窗口帧数才是每帧成本 |

一个真实的反例：`【实测】` 开场过场，`host_hz` 34–53，`guest_flip_hz` 16–27 —— 窗口在欢快地重复画同一帧，游戏逻辑只有 16 帧。如果只看窗口刷新率，会得出“还行”的错误结论。

**设计含义**：渲染器的所有优化目标必须写成 “guest_flip_hz 在同一场景、同一窗口、同一内部分辨率下从 A 提到 B”，而不是“看起来更流畅”。

### 1.4 现状基线：优化前你必须先复现的三个数

在动任何代码之前，跑下面三个基准。它们构成后面所有改动的对照系 `【实测，i3-4170 + HD 4400，亚洲盘，0.5×，VU1 x64 JIT，标题/演算场景】`：

| 基准 | 命令要点 | 期望值 | 它证明了什么 |
|---|---|---|---|
| 快模式开 | `GOW_VU1_FAST=1 PS2X_GS_HW_SCALE=0.5` | 59.6–60.1 guest fps，`vu_ms` 4000–4130 | 标题画面已经贴顶 |
| 快模式关 | `GOW_VU1_FAST=0` | 52.6–55.8 guest fps，`vu_ms` 4550–4600 | VU1 是这条路径的边际成本 |
| 丢弃绘制 | `PS2X_GS_DISCARD_DRAWS=1` | 59.9 guest fps，`gs_ms` 约 1450 | 前端链路本身 1.3–1.5 s/5s，渲染器只是叠加在其上 |

第三个数字最重要，也最容易被忽略：**即使一次 draw 都不发，GS 前端每个原始图元仍要 `buildDrawBatch` + 入队 + 出队 + 展开**。`【文档】` 标题场景约 1.4 万图元/帧，重过场 1.6–2 万/帧。这条链路的成本是渲染器优化的**地板**，任何“把 draw 优化到 0”的方案都不可能突破它。

如果这三个数在你机器上对不上，先怀疑机台和设置（单实例、窗口非黑、同场景、同开关），不要先怀疑代码。`play-jpn.cmd` / `play-asia.cmd` 开头会 `taskkill` 残留的 `ps2EntryRunner.exe`，手工启动前务必确认没有第二个实例在抢窗口 —— 双实例能让帧率凭空“变好”或“变坏”。

---

## 2. 从哪里开发：落点地图

这一章的作用是让你在 30 分钟内知道“该打开哪个文件、改哪个函数”，而不是先在 3000 行里迷路。

### 2.1 文件与职责

路径前缀统一为 `engine/runtime/PS2Recomp/ps2xRuntime/src/lib/gs/`，行数为本文写作时的实际值 `【文档】`：

| 文件 | 行数 | 职责 | 你会在里面做什么 |
|---|---|---|---|
| `gs_frontend.cpp` | 2242 | GS 寄存器写入、顶点收集、`buildDrawBatch`、命令分发 | 改“每图元提交粒度”（冲刺 4） |
| `gs_threaded_backend.cpp` | 567 | 命令队列（64 KB chunk，最多 256 个）、`Op::*` 编解码、worker 出队 | 改“队列负载与合批”（冲刺 4） |
| `gs_stage.cpp` | 281 | GS 阶段回调、与 EE/VU 的衔接 | 一般不动 |
| `gpu/gs_hw_backend.cpp` | 3634 | **主战场**：`Impl`、`submit`、`flushPending`、`draw`、`drawOne`、纹理、shuffle、`Present` | 90% 的渲染改动在这里 |
| `gpu/gs_gl.cpp` / `gs_gl.h` | 871 / 220 | GL 函数指针表（`GSGL::Api`）、上下文创建、共享呈现 | 加能力探测（冲刺 2） |
| `gpu/gs_texture_store.cpp/.h` | 338 / 59 | VRAM 镜像、上传日志、CLUT、页表 | 脏矩形上传（冲刺 5） |
| `gs_host_present.cpp` | 490 | 窗口侧呈现、失败提示 | 改呈现路径（冲刺 3） |
| `gs_gpu_profile.h` | 114 | GPU 时间戳采样队列（`GL_TIMESTAMP`），4 帧一个窗口 | 加 GPU 侧计时（冲刺 1） |
| `ps2_gs_memory.cpp` | 521 | 4 MiB VRAM 与 swizzle | 不动 |
| `gs_swizzle.cpp` | 54 | 块/页 swizzle 原语 | 不动 |

上游的 `VU1` 在 `src/lib/vu/`，与本文正交（第 7.4 节只说怎么判断“该不该改渲染器”）。

### 2.2 一个 GS 图元到一次 GL draw 的完整链路

按调用顺序，带行号 `【文档】`：

```
① GS::vertexKick(bool drawing)                 gs_frontend.cpp:1974
      每收到一个 PS2 顶点调用；凑够一个图元后往下走
② GS::buildDrawBatch(int vertexCount)          gs_frontend.cpp:2182
      把 m_ctx（GS 寄存器快照）复制进 GSPrimitiveBatch.state（约 200 B）
      顺带算 textureWidth/Height、linearFilter
③ m_backend->Submit(batch)                     gs_frontend.cpp:344
④ GSThreadedBackend::Enqueue(Op::Submit, ...)  gs_threaded_backend.cpp:133
      写进 64 KB chunk：状态变了写 Op::DrawState，否则只写 Op::Vertices
      顶点部分只拷 offsetof(GSPrimitiveBatch, state) 之前的字节（约 145 B/图元）
⑤ GSThreadedBackend::Execute(chunk, draw)      gs_threaded_backend.cpp:251
      worker 线程出队，恢复常驻 draw，调 m_inner->Submit(draw)
⑥ GSHwBackend::Impl::submit(...)               gs_hw_backend.cpp（Impl 内）
      先 tryShuffle（16 位通道拷贝）/ depthClearSprite
      sameState(pendingState, s) ? 追加 : flushPending()
      按 prim 类型展开顶点 → HwVertex（64 B）
⑦ Impl::flushPending → draw → drawOne           gs_hw_backend.cpp:2536 / 2610
      target() / attachDepth() / setFbo / viewport / scissor
      深度 + 混合 + alpha test 计算
      UseProgram + 约 35 个 glUniform
      textureFor / indexTextureFor / paletteFor + 4 个 glTexParameteri
      appendVertices → ringAppend → glBindVertexBuffer（gs_hw_backend.cpp:2566 / 2583）
      glDrawArrays(GL_TRIANGLES, ...)
⑧ Present                                       gs_hw_backend.cpp:3389
      PublishSharedTexture（GPU 侧拷贝到共享槽）→ host 线程 blit 到窗口
```

**这条链路上每一个“每图元”的环节，都是老显卡的成本中心：** ②④⑤⑥ 是纯 CPU（与分辨率无关），⑦ 是 CPU + 驱动（与批次数相关），`glDrawArrays` 之后的着色与混合是 GPU（与像素数相关）。

### 2.3 五个改动入口，按风险从低到高

想动手就从 1 开始，一次只做一个。

| # | 入口 | 位置 | 改动量 | 风险 | 收益类型 |
|---|---|---|---|---|---|
| 1 | 能力探测 + 档位选择 | `gs_gl.cpp` 的 `Api` 与 `Context::Create` | 约 200 行 | 极低（只读，不改变绘制） | 让后续所有改动有开关 |
| 2 | 工作点控制器（分辨率阶梯） | `Impl` 里 scale 的解析处（`gs_hw_backend.cpp:898`） | 约 150 行 | 低（只改 RT 尺寸） | **帧率最直接**，且可测 |
| 3 | 呈现路径收敛 | `gs_host_present.cpp` + `Present` | 约 120 行 | 低 | 在老 iGPU 上单项最大 |
| 4 | 前端按 range 提交 | `gs_frontend.cpp` + `gs_threaded_backend.cpp` | 约 400 行 | 中（改接口） | 抬地板（丢弃绘制时的 1.3–1.5 s/5s） |
| 5 | 纹理脏矩形 + shuffle 合批 | `gs_texture_store.cpp` + `Impl` 的 shuffle 队列 | 约 500 行 | 中高（像素正确性） | 重过场场景专用 |

### 2.4 第一个 PR 应该长什么样

**目标：不改任何绘制语义，只加“可观测性 + 档位”。** 具体三件事：

1. **加一个 `DeviceCaps` 结构**（第 4.2 节），在 `ensure()` 里填好，启动时打一行日志：
   ```
   [gs-hw] caps: gl=4.3 vendor=intel renderer="Intel(R) HD Graphics 4400"
           tier=B fill=low submit=high stateCache=off ubo=off barriers=texture
   ```
2. **加一个驱动画像表**（第 5.2 节），按 `GL_VENDOR`/`GL_RENDERER` 字符串匹配已知的坏路径，默认值取“保守”（状态全量设置、不用 UBO）。
3. **加一个 `GOW_GS_TIER=A|B|C` 覆盖开关**，默认由 caps 推导。此时 B 档的行为与今天的代码完全一致 —— 也就是说**这个 PR 的验收标准是“帧率与画面零变化”**。零变化的 PR 才能安全进主干。

这三件事加起来不到 300 行，但它们决定了后面每一个优化都“可开关、可回退、可 A/B”。本工程历史上最贵的一课就是：一次改动同时改了五件事，出问题时无法定位，只能全部回滚。

### 2.5 禁区：这些文件不要碰

| 文件 | 为什么 |
|---|---|
| `ps2_runtime.h`、`ps2_call_list.h`、`ee_scheduler.h`、`gs_frontend.h`、`ps2_recompiled_functions.h` | 改头文件 = 全量重编，20–40 分钟；在老机器上更久。 |
| `runner/*.cpp`（约 6400 个函数） | 重编译产物，改了会被下一次 `recomp` 覆盖。 |
| `engine/patches/NN-*.patch` 里已有补丁的上下文行 | 改了就断链。要修之前的改动，加新号补丁。 |
| `data/`、`engine/runtime/` 的 git 工作区 | 前者是生成物；后者有 77 个历史改动文件，`git checkout .` 会丢掉整个补丁链状态。 |
| `C:\gow-jpn`（若存在） | 独立快照，不在版本控制里，但可运行构建绑的是它。改 `engine/runtime` 后必须复制 + touch + 重建，否则“改了没反应”。 |

### 2.6 怎么把改动变成一个补丁（本仓库的特殊流程）

本工程有一个别人不会遇到的问题：`engine/runtime/` 的工作区里已经有 77 个历史改动文件，所以你 **不能** 直接 `git diff` —— 那会把历史改动和你的改动混在一起，生成一个几百 KB、无法 review 的补丁。

正确流程（六步）：

```
① 改之前，把要动的文件备份
   cp <file> data/_tmp/orig/<同样的相对路径>

② 改代码，构建，测

③ 造一个临时 git 仓库，把备份放进去
   mkdir -p /tmp/patchbase && cd /tmp/patchbase && git init
   mkdir -p PS2Recomp/ps2xRuntime/src/lib/gs/gpu
   cp data/_tmp/orig/.../gs_hw_backend.cpp <对应路径>
   git add -A && git commit -m base

④ 把改后的文件覆盖进去，取增量
   cp <工作区文件> <对应路径>
   git add -A && git diff --cached > 67-my-change.patch

⑤ 在补丁开头加英文头注释（what / why / 实测数字）
   git apply 会忽略头部行，所以头注释不会影响应用

⑥ 用一个干净的 base 副本验证
   git apply --check 67-my-change.patch   # 必须 0
   git apply 67-my-change.patch           # 然后逐字节比较结果（忽略 CRLF）
```

**三个容易踩的点：**

1. **基线要选“改动前的工作区”，不是上游 commit。** 因为工作区已经带着 01–66 的改动。选错基线，补丁应用后会和你的意图不符。
2. **一个补丁只做一件事。** 本文的 Sprint 划分就是补丁划分：`67-gs-caps-and-invariants`、`68-gs-workpoint-ladder`…… 一个补丁里混两件事，出问题时无法单独回退。
3. **补丁头必须写实测数字。** 这是本工程的硬规矩。没有数字，下一个人无法判断“这个补丁在今天的机器上还值不值得留”，最终结果是“不敢删也不敢改”。

**为什么不用 `git stash` / `git diff` 的常规流程？**
因为工作区本身就是“脏”的，而且这个“脏”是有意义的（它代表 01–66 的累积结果）。在没有把补丁链补齐之前，常规 git 流程会把“历史”和“你的改动”混为一谈。这不是理想状态，但它是现状 —— 第 9.3 节把它列为一个高风险项。

---

## 3. 老显卡的真实硬件模型

这一章把“为什么慢”变成可以算的账。算不清账的优化都是碰运气。

### 3.1 第一笔账：填充率

HD 4400 的理论填充率约 1.1 GPixel/s（20 EU × 2 像素/周期 × 1.1 GHz 的乐观估计）。看起来 1280×720 = 0.92 M 像素只要 0.8 ms，但真实成本是：

```
实际像素成本 = 可见像素 × (1 + 过绘制率) × (基础着色成本 + 采样次数 × 采样成本 + 混合成本)
```

GS 的绘制天然高过绘制：阴影体（shadow volume）用加性混合叠两遍、粒子用大面片、场景有大量重叠的层。保守估计过绘制 2–3 倍，则 1280×720 的一帧要付 2–3 M 像素的账，再乘上“每像素要采一次纹理 + 可能读目标做软件混合”，落到 5–10 ms 一帧是很正常的。

实测印证 `【实测】`，同一内部分辨率 412×360，只改呈现窗口：

| 窗口 | guest fps | 呈现 |
|---|---|---|
| 1280×720 | 36.7 | **20.6 Hz** |
| 640×360 | 37.9 | **32.7 Hz** |

**同一张 412×360 的图，塞进 720p 窗口，呈现帧率掉 37%。** 这一步不是那个 bilinear 缩放本身贵，而是“合成 + DWM + 显存带宽”：窗口越大，DWM 要合成、要刷新的面积越大，而这块卡与 CPU 共享 DDR3 带宽。

**设计结论 #1：呈现面积是独立于渲染分辨率的成本项，必须能单独控制。**
这也是 `GOW_RENDER_HEIGHT` 现在“同时决定窗口”的原因（未设 `GOW_WINDOW` 时按同高度 16:9）。低配档必须把窗口高度和内部高度绑在一起，而不是让用户分别调。

### 3.2 第二笔账：提交成本

批次（batch）是“相邻且状态完全相同的一段图元合并成一次 GL draw”。每批次的开销是：

| 项 | 典型成本 | 说明 |
|---|---|---|
| `glBindFramebuffer` + `glViewport` + `glScissor` | 1–3 µs | Intel 上重设比跳过快 |
| 深度/混合/alpha 状态设置 | 2–5 µs | 约 10 次调用 |
| `glUseProgram` + 约 35 个 `glUniform*` | 3–6 µs | UBO 方案实测更慢，见 3.4 |
| 纹理绑定 + 4 个 `glTexParameteri` | 2–4 µs | 依赖驱动 |
| `glBindVertexBuffer` + `glDrawArrays` | 1–2 µs | 顶点环之后 |
| 驱动内部校验 + 命令写入 | 不确定，老驱动可能是大头 | 这就是“状态缓存反而更慢”的来源 |

合计约 **10–20 µs/批次**。标题场景约 380–420 批次/帧 `【文档】`，则每帧 4–8 ms —— 与 `gs_ms` 1925–2177 / 5s（60 fps 时约 6.4–7.3 ms/帧）高度吻合。这不是巧合，它说明**批次数就是 GS 侧的主成本项**。

**设计结论 #2：减少批次数 > 减少每批次调用数。** 因为每批次的固定开销（驱动校验、状态切换、管线绑定）无法靠“少调几个函数”消掉，只能靠“少开批次”。

但注意：**减少批次数不能靠重排序**。GS 的混合、alpha test、DATE、Z 别名全部依赖提交顺序，全局按纹理/状态排序一定画面出错 `【文档，已列为不建议方向】`。合法的手段只有三个：

1. 合并“相邻且状态等价”的图元（现有 `sameState` 已经在做，且 canonical 放宽版实测无收益）。
2. 减少状态变化的**来源**（例如让 CLUT 变化不再 flush —— 调色板图集方案实测批次几乎不降，因为批次主要由 TEST/PRIM/TEX0 的真实变化决定）。
3. 降低**每批次之外的**每图元成本（前端 range 提交，第 2.3 节入口 4）。

**设计结论 #3：在老显卡上，“减少批次数”能拿到的收益比想象中小，因为批次由游戏真实的状态变化决定；真正能拿的是“每图元的固定成本”和“每像素的成本”。** 这个判断很重要，它能让你不去做注定失败的“状态合并”工程。

### 3.3 第三笔账：带宽

共享 DDR3 双通道约 25.6 GB/s。一帧要付的带宽：

| 项 | 每帧字节 | 备注 |
|---|---|---|
| 颜色写 412×360 RGBA8 | 0.59 MB | 不含过绘制 |
| 深度写 412×360（24 位） | 0.44 MB | Z16 时减半 |
| 纹理采样 | 0.59 MB × 采样次数 × 缓存命中率倒数 | 老 iGPU 的纹理缓存很小 |
| 呈现 blit（412×360 → 1280×720） | 读 0.59 + 写 3.7 MB | **写目标是大头** |
| DWM 合成 | 3.7 MB 起 | 与窗口面积成正比 |

60 fps 下仅“呈现 + 合成”就要 7.4 MB × 60 ≈ 444 MB/s，占 25.6 GB/s 的 1.7% —— 看起来不多，但这是**峰值突发**，而且 DWM 与游戏在同一块内存上。实测的 37% 呈现掉帧说明瓶颈不在平均带宽，而在**固定开销与同步**。

**设计结论 #4：不要试图靠“换更小的像素格式”省带宽。** RGBA8 → RGB565 能省一半，但 GS 的 alpha 与混合语义会崩，正确性代价远大于收益。省带宽要靠“少画一遍”和“少一次全屏 blit”。

### 3.4 三个反直觉现象（必须写进设计约束）

这三条是本工程用真实 A/B 换来的，全部发生在 Intel HD 4400 上：

**现象 1：每批次 std140 UBO 比 35 个 `glUniform` 更慢。**
完整实现、布局用 `static_assert(offsetof...)` 校验、视觉正确，但整组只有 50.7 fps（ring-only 是 53–55），`gs_ms` 从 2.0 s 升到 2.26 s `【实测】`。
→ **约束：B 档默认不用 UBO。** 只有当驱动画像显示 `vendor != intel` 时才允许启用，且必须 A/B。

**现象 2：GL 状态去重缓存让帧率从 53–55 掉到 37–40，`gs_ms` 翻倍。**
单独关掉 scissor/blend/mask/depth/fbo/program/vao 任一项都无法恢复，全关才恢复 `【实测】`。
→ **约束：B 档默认全量显式设置所有状态，不跳过。** 状态缓存必须是一个显式的、可关闭的实验分支，而不是“优化”。

**现象 3：0.35× 不比 0.5× 快。**
41.9 vs 40.4 guest fps `【实测】`。
→ **约束：分辨率阶梯必须知道“地板”在哪，低于地板继续降分辨率只会损失画质、不涨帧。** 这就是第 4.7 节阶梯控制器要“测量而不是猜”的原因。

把三条放在一起，得到的是一条对老显卡极其重要的元规则：

> **在这类驱动上，“更现代的 GL 用法”不等于“更快”。每一条优化都必须有一个可由环境变量关闭的分支，并且必须能在同一台机器上用同一场景 A/B 出数字。**

### 3.5 双墙模型：把帧率写成公式

综合上面三笔账，一帧的 GS 侧时间可以写成：

```
T_gs(res) ≈ T_fixed + max( T_fill(res), T_submit )
```

- `T_fixed`：前端每图元的固定成本（`buildDrawBatch` + 入队 + 出队 + 展开）+ present + 同步。**与分辨率无关，与图元数成正比。**
- `T_fill(res)`：填充与带宽成本，**与像素数成正比**（约 res²）。
- `T_submit`：批次成本，**与批次数成正比，与分辨率无关**。

三个系数怎么测（这是本章最实用的部分）：

| 要测的量 | 方法 | 注意 |
|---|---|---|
| `T_fixed` | `PS2X_GS_DISCARD_DRAWS=1`，读 `gs_ms` | 此时 `T_fill = T_submit = 0`，剩下的就是地板 |
| `T_submit` | 固定分辨率，用 `GOW_GS_HW_STATS=1` 读每帧批次数，配合 `GOW_GS_COST=1` 的 `ones`/`oneTicks` | `oneTicks/ones` 就是每批次 CPU ticks |
| `T_fill` | 固定场景，只改 `PS2X_GS_HW_SCALE`，取两点解线性方程 | 至少三点，因为低端会饱和 |

用已有数据代入 `【实测】`（标题，i3-4170 + HD 4400）：

```
res=1.00 → 24.3 fps → T_gs ≈ 41.2 ms（但此时 guest 还受 VU1 限，不能直接当 T_gs）
res=0.50 → 40.4 fps → T_gs ≈ 24.8 ms
res=0.35 → 41.9 fps → T_gs ≈ 23.9 ms
```

从 0.50 到 0.35，像素少了 51%，时间只少了 3.6% ⇒ **0.5× 以下 `T_fill` 已经不是主导项，`T_submit + T_fixed` 约 23 ms 是地板**。而从 1.00 到 0.50，时间少了 40% ⇒ 1× 时 `T_fill` 约 16 ms，是主导项。

这就给出了交叉点：**在这台机器上，工作点应该在 0.5× 附近，而不是 0.35× 或 1×。** 0.35× 只多给 1.5 帧却损失 50% 的像素，是坏交易。

### 3.6 工作点与“自动档”的正确写法

把上面的模型变成控制器：

```
目标：在 guest 帧率 ≥ 目标（默认 59）的前提下，最大化内部分辨率
约束：切换不能引起振荡；切换本身要便宜（改 FBO 尺寸会重建 RT）
```

朴素实现（每秒看一次 fps，低于目标就降一档）会在边界反复横跳，因为降档后 fps 升高、升档后 fps 又掉，玩家看到的是画质抽搐。正确写法是**带滞回的双阈值 + 冷却时间**：

```
每 1.0 s 评估一次：
  若 fps < 目标 - 2  且 距上次切换 > 2 s  → 降一档
  若 fps > 目标 + 1  且 距上次切换 > 6 s  → 升一档
  连续 3 次评估都在 [目标-2, 目标+1] → 锁定 10 s（不再动）
```

关键细节：**升档的门槛要比降档高、冷却要更长**。因为升档后大概率又掉下去，来回一次就是两次 RT 重建 + 两次画质跳变。

这一节是第 5.7 节代码的直接依据。

### 3.7 三家驱动的差异清单

同一份 GL 代码，在三家驱动上会表现出三种性格。这张表的作用不是“背下来”，而是**出问题时知道该怀疑谁**。

| 现象 | Intel | AMD | NVIDIA |
|---|---|---|---|
| 状态重设 vs 跳过 | **重设更快**（实测 53→37）`【实测】` | 未测，倾向“跳过略快”`【推断】` | 未测，倾向“跳过略快”`【推断】` |
| 每批次 UBO | **更慢**（实测 53→50.7）`【实测】` | 未测，通常更快 | 未测，通常更快 |
| `glUniform` 更新成本 | 很低（同一 program 内） | 中 | 中 |
| `glBufferSubData` | 有隐性同步，环必须配 fence | 较宽松 | 较宽松 |
| `glBufferStorage` + 持久映射 | 支持，但映射失败要重建 buffer | 支持 | 支持 |
| `GL_UNIFORM_BUFFER_OFFSET_ALIGNMENT` | 16 | 64 | **256** |
| `glFinish` 的代价 | 极高（几十 ms），能不用就不用 | 高 | 中 |
| 着色器编译 | 慢（100–300 ms/program） | 中 | 快（有 disk cache） |
| 纹理上传（`TexImage2D`） | 同步，慢 | 中 | 快 |
| 驱动 bug 倾向 | 状态校验路径多、少见但存在 | 少 | 少 |

**读法**：Intel 那一列有实测支撑，AMD/NVIDIA 那两列是**待验证假设**，本文不把它们当事实用。任何“在 NVIDIA 上应该更快”的说法，都必须先在那台机器上 A/B 出数字，否则就是第 7.4 节里那种“花了时间证明无效”的重演。

**给实现者的三条跨厂商规则：**

1. **对齐永远按 256 算。** 即使查询返回 16，也按 256 分配槽距 —— 多花的内存（每槽多 240 B × 2048 槽 = 480 KB）换来的是“同一份代码在 NVIDIA 上不会隔槽读错”。
2. **永远不要假设 `glFinish` 便宜。** 它在 Intel 上是几十毫秒级，一次就能把 60 fps 打成 20。能用 `TextureBarrier` 就用，不能用就改渲染顺序避免同目标读写。
3. **驱动字符串只用来选策略，不用来做能力判断。** 能力一律查 `GL_*` 常量；`GL_RENDERER` 字符串可以伪造、可以改写（Mesa 会伪装成别的卡），用它决定“有没有某个扩展”一定会出错。

最后一条值得展开：本工程见过 `GL_RENDERER` 里带 “Intel” 但实际是 Mesa 软件渲染的情况（在某些 Linux 环境）。所以 `ProbeCaps` 的顺序必须是“先查 `GL_VERSION` 与扩展，再查 vendor 字符串选策略”，不能反过来。

---

## 4. 渲染器架构设计 v2

### 4.1 五条设计原则

这五条不是格言，每一条都能在后面的代码里找到对应的结构。

**原则 1：语义与策略分离。**
“GS 的 TFX 公式是什么”是语义，永远不变；“用 35 个 uniform 还是 1 个 UBO”是策略，因卡而异。现有代码把两者混在 `drawOne` 里，所以每一次性能实验都要动语义代码，风险高。v2 把它们切开：语义留在 shader 与状态计算里，策略抽成 `DevicePolicy`。

**原则 2：一条路径一个开关，一个开关一个补丁。**
`GOW_GS_HW_RING=0` 是正面例子：顶点环出问题，一行环境变量回到旧路径。反面例子是一次改五件事的 PR，出问题只能全回滚。

**原则 3：默认最保守，优化必须显式打开或由画像证明。**
Intel 上的三条证伪记录说明“默认开启现代用法”是负收益。所以默认值取“老式但确定”的那一侧。

**原则 4：所有跨对象引用都用稳定 id，不用裸指针。**
`shuffleDst/shuffleSrc` 曾是裸 `RenderTarget*`，而 `targets` 是 `std::vector`，任何 `emplace_back` 都可能搬迁 ⇒ 悬垂 ⇒ shuffle 画到随机目标 `【实测根因】`。v2 里这条升级为全局规则：跨帧/跨批次存活的东西一律存 id。

**原则 5：失败必须可见，不能是黑屏。**
`GSSharedPresent::SetRendererFailure` 已经能把“没上下文/着色器编译失败”变成窗口上的文案（patch 52）。v2 要求所有新增的失败点都走同一条通道，并且**失败后自动降档重试一次**，而不是直接黑。

### 4.2 分层结构

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (gs_frontend.cpp)                                  │
│   GS 寄存器 → buildDrawBatch → Submit                       │
│   v2 增量：按“状态等价 + 连续”聚成 Range，一次入队           │
└───────────────────────────┬─────────────────────────────────┘
                            │ GSPrimitiveBatch / Range
┌───────────────────────────▼─────────────────────────────────┐
│ Command Queue (gs_threaded_backend.cpp)                      │
│   64 KB chunk，Op::* 编解码，worker 出队                     │
│   v2 增量：Op::Range（一次带 N 个图元），减少 header 开销     │
└───────────────────────────┬─────────────────────────────────┘
                            │ Submit / DrawState / Vertices
┌───────────────────────────▼─────────────────────────────────┐
│ Backend (gs_hw_backend.cpp :: Impl)                          │
│   submit → 展开顶点 → 合批 → flushPending → drawOne          │
│   ┌──────────────────────────────────────────────────────┐   │
│   │ DevicePolicy（v2 新增，纯策略，无 GL 调用）            │   │
│   │   tier / stateMode / vertexMode / uploadMode /        │   │
│   │   presentMode / shaderVariant / workPoint             │   │
│   └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │ GL 调用
┌───────────────────────────▼─────────────────────────────────┐
│ Device (gs_gl.cpp :: GSGL::Api + Context)                    │
│   函数指针表、上下文创建、能力探测、共享呈现                   │
│   v2 增量：DeviceCaps（只读事实）+ 可选函数加载               │
└─────────────────────────────────────────────────────────────┘
```

**为什么 `DevicePolicy` 要独立成一个结构而不是散在 `Impl` 里？**
因为它是唯一需要被“打印、覆盖、A/B、写进日志”的东西。把它集中，启动那一行日志就能完整描述“这次跑的是哪条路径”，出问题时不用猜：

```
[gs-hw] caps: gl=4.3 vendor=intel device="Intel(R) HD Graphics 4400"
        maxTex=16384 maxUBO=65536 uboAlign=16 barriers=texture
[gs-hw] policy: tier=B state=explicit vertex=ring32M upload=sync
        present=blit+fit shader=mono workpoint=0.50 (ladder=on)
```

这一行日志的价值超过一千行注释。

### 4.3 能力探测：`DeviceCaps`

只探测**会影响决策**的能力，不做“能力大全”。每一条都对应下游一个分支：

| 字段 | 来源 | 影响哪个决策 |
|---|---|---|
| `glMajor/minor` | `glGetString(GL_VERSION)` | 档位（`< 4.3` 走 C 档） |
| `vendor` | `glGetString(GL_VENDOR)` 归一化 | 驱动画像（intel/amd/nvidia/unknown） |
| `renderer` | `glGetString(GL_RENDERER)` | 画像细分、日志 |
| `maxTextureSize` | `GL_MAX_TEXTURE_SIZE` | 纹理仓库上限、RT 尺寸上限 |
| `maxUBOBindings` | `GL_MAX_UNIFORM_BUFFER_BINDINGS` | 是否允许 UBO 策略（B 档不用） |
| `uboAlign` | `GL_UNIFORM_BUFFER_OFFSET_ALIGNMENT` | 若用 UBO，槽距必须 ≥ 它（Intel 16 / AMD 64 / NVIDIA 256） |
| `hasTexBarrier` | `glTextureBarrier` 非空 | 同目标读写是走 barrier 还是 `glFinish`（后者慢一个数量级） |
| `hasBufferStorage` | `glBufferStorage` 非空 | 顶点环是持久映射还是 `BufferSubData` |
| `hasVertexAttribBinding` | `glBindVertexBuffer` 等三个非空 | 顶点环是否可用（否则回退每批次 `BufferData`） |
| `hasFenceSync` | 非空 | 环回绕是否有栅栏 |
| `hasDebugOutput` | `GL_KHR_debug` | 开发期错误定位 |
| `maxSamples` | `GL_MAX_SAMPLES` | 是否开 MSAA（老卡默认关，见 7.3） |

**探测必须在 `ensure()` 里、创建上下文之后、创建任何 GL 对象之前完成**，并且结果要能通过 `GOW_GS_CAPS=1` 打印。不要在绘制路径里“顺手查一下”——那是每帧几千次的驱动调用。

### 4.4 三档管线

不要做“渲染器 A 和渲染器 B”，做“同一渲染器的三档策略”。三档共享全部 GS 语义代码，只在 `DevicePolicy` 上分叉。

| | **A 档（现代）** | **B 档（老显卡，默认）** | **C 档（兜底）** |
|---|---|---|---|
| GL 版本 | 4.3+，`ARB_texture_barrier` | 4.3 或 3.3 | 3.3 最低，或 `sw` |
| 反直觉优化 | 可开 UBO/状态缓存（需 A/B） | **全部关闭**，状态全量设置 | 不适用 |
| 顶点路径 | 持久映射环 + `glBindVertexBuffer` | 同 A，但环更小（16 MB）、栅栏更保守 | 每批次 `BufferData` |
| 上传路径 | PBO + 异步（若收益证明） | 同步 `TexImage2D`，脏矩形优先 | 同步全量 |
| shuffle | 独立 program + 合批 | 同 A，保守合批（同目标才合） | 逐精灵，允许慢 |
| 呈现 | blit + 可选 shader 缩放 | `glBlitFramebuffer` + `GL_LINEAR`，窗口贴合 | 允许 1/2 降采样呈现 |
| 内部分辨率 | 1×–4× 自由 | 阶梯 0.35×–1.0×，带滞回 | 固定 0.5× |
| 着色器变体 | 多个专用 program | 单 program + uniform 分支 | 单 program，最简 |
| 预期场景 | 战斗 60 fps | 标题 60，重过场 45–50 | 能跑起来、能看画面 |

**为什么 B 档是默认？** 因为本文的目标读者就是老显卡。B 档的行为**等价于今天的代码 + 三处收敛**（分辨率阶梯、呈现贴合、shuffle 保守合批），也就是“已知能跑到 40+ 的那条路”。A 档是给新卡准备的上行空间，C 档是给“连 4.3 都没有”的机器的降落伞。

**档位之间必须能强制覆盖**：`GOW_GS_TIER=A|B|C`。这既是调试手段，也是用户自救手段（驱动更新后行为变了，可以让用户先试 A）。

### 4.5 状态模型：显式 vs 缓存的决策树

这是全文最容易做错的一节。通用图形学教“状态缓存减少冗余调用”，但本工程实测在这块 Intel 上是灾难。

```
每批次的 GL 状态设置：
├─ 驱动画像 = intel ?
│   ├─ 是 → 全量显式设置（不读缓存、不跳过）
│   │       例外：同一 program 内已设置的、且本批次不改的 uniform 可以跳过
│   │       （这条也能测，但收益上限约 1–2%，见 7.3 ROI 表）
│   └─ 否 → 可以试“全量缓存”模式，但必须由 GOW_GS_STATE=cache 显式打开，
│            且首次运行要写进日志说明“这是实验路径”
└─ 无论哪条：boundProgram 必须在任何 UseProgram 之后立刻同步
             （见 6.2，这是本工程最贵的 bug 类别）
```

为什么 Intel 会这样？一个可核对解释 `【推断】`：Intel 的 GL 驱动在 `glDrawArrays` 时对“当前状态是否与管线一致”做整条重新校验，如果某些状态是“很久以前设的、中间被别的路径改过”，它要走慢路径重建；而每次显式重设会让内部状态标记为“已知一致”，反而走快路径。冗余的 setter 是廉价的 fast path —— 这与“少调用 = 快”的直觉正好相反。

这也解释了为什么“单独关掉任一项都不恢复，全关才恢复”：只要有一条状态是“陈旧”的，校验就走慢路径，省其它六项没有意义。**这是一个全或无的开关，不是可以逐项优化的东西。** 这条洞察直接防止了“我优化了 scissor 缓存，怎么没变快”的反复试错。

### 4.6 帧结构与生命周期

现有代码是“即时模式 + 相邻合批”，没有显式的帧对象。v2 保留这个模型（引入帧图会带来排序，而排序会破坏 GS 语义），但明确一个帧的四个阶段：

```
Frame N:
 ① BeginFrame    —— 无 GL 调用；重置每帧统计、推进 frameSerial
 ② Render        —— submit/合批/drawOne，任意顺序，与 guest 提交顺序严格一致
 ③ Resolve       —— 把当前显示目标（DISPFB/DISPLAY）解析成“可呈现”
 ④ Present       —— 发布到共享槽，由 host 线程 blit
```

每帧必须维护的、可断言的东西：

| 量 | 不变量 |
|---|---|
| `targets.size()` | 只增不减直到 `Reset()`；`RenderTarget::id` 稳定 |
| `pending.size()` | 帧末必须为 0（`flushPending` 被调用过） |
| `vertexRingOffset` | `0 ≤ offset ≤ kVertexRingBytes` |
| `boundProgram` | 等于最后一次 `UseProgram` 的参数，或为 0（表示未知） |
| FBO 绑定 | 帧末恢复到“默认帧缓冲”，供 present 使用 |
| `shuffleQuads[2]` | 帧末为空（`flushShuffle` 被调用过） |

**帧末断言是抓“漏 flush”类 bug 的唯一可靠手段。** 本工程的“场景全黑”就是 shuffle 队列在某条路径上没被 flush/没有正确收尾导致的，而这类问题在单帧截图上看不出来（标题正常、场景全黑），只有断言能在第一次出现时就炸出来。

### 4.7 顶点路径

现有实现（patch 59）已经是正确方向，v2 只在参数上做档位化：

```cpp
static constexpr uint32_t kVertexRingBytes = 32u << 20;   // gs_hw_backend.cpp:590
```

`HwVertex` 是 64 字节（16 个 float：位置 2 + Z 1 + 颜色 4 + STQ 3 + UV 2 + UVClamp 4）`【文档】`，6 个属性，attribute binding 方式每次只需一次 `glBindVertexBuffer`。这个布局是对的，但有一个必须写进设计文档的账：

```
每帧顶点数 = 图元数 × 每图元顶点数
           ≈ 1.4 万 × (三角形 3 | 精灵 6 | 线 6)
           ≈ 30–40 万顶点
           = 19–26 MB/帧（64 B/顶点）
```

**32 MB 的环只够 1.2–1.7 帧。** 也就是说标题场景每帧要回绕一次左右，回绕点会等一个 fence。这在 Intel 上要付 1–3 ms（见下面的反例）。

参数选择的规则（来自一次惨痛教训）：

| 方案 | 每帧跨界次数 | 结果 |
|---|---|---|
| 4 MB 环 / 8 块 × 512 KB | 37 次 | guest 从 7 fps 崩到 **1.4 fps** `【实测】` |
| 16 MB 环 / 4 块 × 4 MB | 1–2 次 | 可用 |
| 32 MB 单环 + 1 fence | 约 1 次 | 当前实现 |

规则：**块要 MB 级、环要装约 0.8 帧以上、每帧跨界 ≤ 1–2 次。** 512 KB 的块在这个负载下等于每帧 sync 37 次，而 Intel 每次 sync 1–3 ms —— 光同步就 40–100 ms/帧。这个反例值得单独记住，因为它违反了“环越小缓存越友好”的直觉。

v2 的档位化：B 档用 **16 MB**（省一半显存，跨界次数几乎不变，因为 16 MB 仍接近 1 帧），C 档退化为每批次 `glBufferData` + `VertexAttribPointer`（无环、无 fence、无 `glBindVertexBuffer`）。

### 4.8 纹理路径

GS 的纹理不是一个“图片”，而是 **4 MiB VRAM 里的一段带格式的字节**。现有实现有四条解码路径 `【文档】`：

| 路径 | 触发条件 | 实现 |
|---|---|---|
| 直接色 | CT32/CT24/CT16(S) | `decodeDirect`：从 VRAM 解成 RGBA8，`glTexImage2D` 上传 |
| 索引色 | PSMT8/PSMT4 及 H 变体 | `indexTextureFor` 只存索引（R8），颜色由 `paletteFor` 生成的 256×1 RGBA 纹理查表 |
| 重解释 | 纹理内存来自某个渲染目标，但格式/宽度/布局不同 | shader 里做地址映射 + 位重组，`setupReinterpret` 绑定表/调色板/目标纹理 |
| Z 别名 | `ZBP == FBP` | 深度存在颜色内存的 Z 字里，shader 读写 |

**这条路径的成本结构是“一次解码 + 多次上传”，而不是“每帧上传”。** 缓存 key 是 `(tbp0, tbw, psm, tw, th, texa, clutHash)`，上传重叠（`BeginTransfer` 记录覆盖块 + `writeSeq`）会让对应的纹理 `valid=false`，下次绘制重解码。

问题在于**粒度**：任何一次重叠就让**整张**纹理重解码。重过场的实测是 `texDecodes` 最高 3017/5s、`upload_ms` 最高 777 ms/5s `【实测】`，这说明有大量“只改一小块”的流式上传被放大成了整张重解码。

v2 的脏矩形设计（第 5.5 节给代码）要点：

1. `UploadRecord` 从 `{lo, hi, seq}` 扩展成 `{lo, hi, seq, x0,y0,x1,y1}`（像素矩形，按 psm 的块粒度上取整）。
2. 纹理对象记住“已解码到哪个 `seq`”，以及一个待重解码的矩形并集。
3. 重解码时只处理并集矩形内的页；`glTexSubImage2D` 只上传该矩形。
4. **安全阀**：并集面积 > 整张 60% 时退化为整张重解码（避免脏矩形变成“一帧内几十次小上传”）。

第 4 条很重要：脏矩形的收益在“小块高频改动”，在“整张频繁改动”时反而更慢（每次上传都要走驱动路径）。没有安全阀的脏矩形实现是负优化。

### 4.9 shuffle 路径

shuffle 是 GS 特有的操作：把 16 位目标里的通道拆开/合并（例如 CT16 的 R/G/B/A 分离）。它不是“画一个三角形”，而是**内存重排**，必须用独立的 program + VAO + FBO 完成。

现有实现：

- `tryShuffle` 在 `submit` 里对每个精灵判断能否走 shuffle；
- `flushShuffle` 在 `flushPending` 与批次切换时把队列里的 `ShuffleVertex` 一次性画掉；
- `shuffleQuads[2]` 按“目的半字”分两个队列；
- 成本：重过场 `shuffles` 最高 22176/5s（约 4400/秒），是 GS 侧最大单一开销 `【实测】`。

v2 的改动只有一个：**保守合批**。合批条件是“同一目标 + 同一通道模式 + 连续”，不跨普通绘制、不重排序。理由见 3.2：排序会破坏 GS 语义。预计收益 10–20%（取决于 FBO 切换占比），不指望质变。

### 4.10 呈现路径

`Present` 做两件事：把当前显示目标拷贝到一个共享纹理（GPU 侧，`PublishSharedTexture`），然后由 host 线程 blit 到窗口。

老显卡上的三个要点：

1. **呈现面积必须与内部面积解耦控制。** 内部 412×360 塞进 1280×720 窗口掉 37% 呈现帧率 `【实测】`。B 档默认“窗口贴合内部高度”（16:9），并允许用户用 `GOW_WINDOW` 覆盖。
2. **不要在呈现链上叠加全屏后处理。** FXAA、锐化、双线性拉伸叠加 —— 每加一个就是一次全屏 pass。低配档全部关闭（`low-spec-renderer.patch` 的 `aplicarPerfil` 已经是这个逻辑）。
3. **失败必须有文案。** `GSSharedPresent::SetRendererFailure` 的两条路径（`NoContext` / `Shaders`）已经能把黑屏变成“你的驱动不支持 OpenGL 4.3”这类可读信息 `【文档】`。v2 新增第三条 `TierUnavailable`：三档都起不来时提示“请尝试 `PS2X_GS_RENDERER=sw`（很慢）”。

### 4.11 一张图看清 v2 相对 v1 改了什么

| 维度 | v1（今天） | v2（本文） | 是否改语义 |
|---|---|---|---|
| 档位 | 一条 GL 4.3 硬路径 | A/B/C 三档 + 覆盖开关 | 否 |
| 分辨率 | 固定 `PS2X_GS_HW_SCALE`，clamp 0.25–4 | 阶梯控制器（滞回 + 冷却 + 锁定） | 否 |
| 状态 | 全量设置（意外地正确） | 全量设置（**明确**为策略，附证伪记录） | 否 |
| 顶点 | 32 MB 环 + 单 fence | 三档：32 MB / 16 MB / 每批次 BufferData | 否 |
| 纹理 | 整张重解码 | 脏矩形 + 安全阀 | 否（结果应逐像素一致） |
| shuffle | 逐 state run flush | 保守合批（同目标同模式） | 否 |
| 呈现 | 拷贝 + host blit | 同上 + 窗口贴合 + 失败降档 | 否 |
| 观测 | 环境变量 + stderr | 增加 `caps`/`policy` 两行启动日志 + GPU 时间戳 | 否 |

**注意最后一列全是“否”。** 这是这份设计最重要的性质：**所有改动都不改变像素语义，因此可以用“黄金帧逐像素一致”来验收**（第 6.4 节）。一旦某个改动需要改语义，它就必须被拆成独立补丁、独立验证，且要接受“与参考实现逐像素对比”的更高门槛。

### 4.12 `drawOne` v2 的完整走读

这一节把 `drawOne` 逐段拆开，每一段都说明“为什么排在这里”。顺序本身就是正确性的一部分：GS 的状态是**逐寄存器**的，而 GL 的状态是**逐管线对象**的，两者的对应关系决定了赋值顺序。

```
drawOne(state s, vertices v):

  ── 阶段 0：早退与诊断（不产生任何 GL 状态） ──────────────────────
  0.1  若 GOW_GS_HW_SKIPTBP 命中 → return（调试用，跳过某纹理块的绘制）
  0.2  若 GOW_GS_HW_DUMPALL 且本批次在转储窗口 → 打印状态摘要 + 屏幕 bbox
       （注意：打印本身会改变时序，只在诊断时开）

  ── 阶段 1：目标解析（决定后面所有状态作用于哪里） ────────────────
  1.1  rt = target(fbp, fbw)            按 (fbp, fbw) 找/建 RenderTarget
  1.2  attachDepth(rt, zbp)             必要时创建/挂接深度纹理
  1.3  rt.psm = frame.psm               记录格式（影响后续能否被采样）
  1.4  ++rt.version; rt.lastDrawSeq = ++writeSeq
       ↑ 这两行是“纹理失效”的判据。写在最前面，保证即使本批次后面失败，
         目标也被标记为“已写过”，采样它的纹理不会读到旧内容。

  ── 阶段 2：固定管线状态（必须全量设置，见 4.5） ──────────────────
  2.1  BindFramebuffer(GL_FRAMEBUFFER, rt.fbo)
  2.2  Viewport(scissor 收紧后的矩形)      ← v2：可选收紧，见 7.5 方向 2
  2.3  Enable(SCISSOR_TEST); Scissor(...)
  2.4  Disable(CULL_FACE)                  GS 不做背面剔除，永远关
  2.5  深度：ZTE ? Enable(DEPTH_TEST) : Disable
             DepthFunc(mapZtst(zbuf.ztst))
             DepthMask(zbuf.zmask ? GL_FALSE : GL_TRUE)
  2.6  混合：abe ? 按 alpha 寄存器选 equation/factor
                  : Disable(BLEND)
  2.7  颜色掩码：fbmsk == 0 ? 全开 : 按位设置 ColorMask

  ── 阶段 3：着色器与 uniform ──────────────────────────────────────
  3.1  p = ProgramFor(VariantKey(s))      最多 4 个变体，见 5.4
  3.2  BindProgram(p, Draw)
  3.3  按固定顺序上传 uniform（顺序无关，但固定顺序便于 diff 日志）
       纹理尺寸、TEXA、TFX/TCC/IIP、ATE/ATST/AREF、混合缩放、
       目标格式（uRtFmt/uRtFmt2）、Z 别名、像素缩放、各向异性

  ── 阶段 4：纹理 ─────────────────────────────────────────────────
  4.1  src   = (纹理来自本目标) → 需要 barrier
       rsrc  = 重解释 → 需要表 + 目标纹理
       zsrc  = 采样深度 → 需要 uZTex
       idx   = 索引色 → 需要索引纹理 + 调色板纹理
  4.2  BindTexture 各单元，TexParameteri 四个参数
  4.3  若 src → TextureBarrier()（无该扩展时 glFinish，慢一个数量级）

  ── 阶段 5：alpha test ───────────────────────────────────────────
  5.1  ate ? uPass = 1（只保留通过像素）
  5.2  若 afail != 0 → 第二遍 uPass = 2，并按 AFAIL 设 ColorMask/DepthMask
       ↑ 两遍无法合并：失败像素要写不同的东西（只颜色/只深度/只 RGB）

  ── 阶段 6：顶点与绘制 ───────────────────────────────────────────
  6.1  appendVertices(v)                  写环 + BindVertexBuffer
  6.2  DrawArrays(TRIANGLES, first, count)

  ── 阶段 7：收尾 ─────────────────────────────────────────────────
  7.1  Disable(SCISSOR_TEST)              其它路径（present/clear）假定它关着
  7.2  统计：batches++、每批次 µs 累加
```

**六个“为什么必须在这个位置”**，每一条都对应一次真实的事故或一次差点发生的事故：

| 位置 | 为什么不能挪 |
|---|---|
| 1.4 的 `++rt.version` 在最前 | 挪到后面，一旦提前 return（例如 afail 分支），目标就被写过但版本没变，采样它的纹理会读到旧内容 → 闪烁 |
| 2.5 的 `DepthMask` 在混合之前 | GS 的 ZMASK 语义是“禁止写深度”，与混合无关；放在混合后容易被混合分支的 early-return 跳过 |
| 3.2 的 `BindProgram` 走包装 | 直接调 `UseProgram` 就是第 6.2 节那个 bug 的来源 |
| 4.3 的 barrier 在采样之前 | 放在绘制之后无效（写入已经发生），放在绑定之前才正确 |
| 5.1/5.2 的两遍 | 试图用一遍 + stencil 会多一次 stencil 写入和一次清 stencil，在这块 iGPU 上更慢 |
| 7.1 的 `Disable(SCISSOR_TEST)` | present 和 clear 路径不重设 scissor，忘了关就是把画面裁成一小块 |

**阶段 2 里那个“全量设置”是刻意的**。代码看起来“笨”——每次都把十几项状态重设一遍——但这正是 4.5 节的结论：Intel 上跳过是负收益。如果将来在 NVIDIA 上验证出“跳过更快”，它应该变成 `DevicePolicy::stateMode` 的一个分支，而不是把全量设置删掉。

### 4.13 为什么“静态重编译”这件事改变了渲染器的设计

这一节解释一个看起来矛盾的现象：**20 年前的游戏，在比 PS2 快几十倍的 CPU 上，反而跑不满 60 帧。**

先看真机是怎么做的。PS2 的 GS 是一台固定功能光栅化机器，EE 或 VU1 把数据打成 GIF packet 丢给它，GS 收到就画：没有着色器编译、没有状态校验、没有驱动、没有 FBO 切换。一个图元的成本几乎是常数，而且极低。当年 1.4 万图元/帧能跑 60 帧，是因为硬件就是为这个吞吐设计的。

现在看本工程。游戏的 MIPS 代码被静态重编译成 C++，于是：

1. **提交粒度被原样保留。** 原来游戏每帧发 1.4 万个 GS 图元，重编译后仍然是 1.4 万次 `Submit`。这不是“移植者偷懒”，而是**语义要求**：GS 的混合、alpha test、DATE、Z 别名都依赖提交顺序，你不能把它们攒起来重排。
2. **每次提交都要翻译。** 真机的“一个 packet”在 PC 端变成：构建约 200 B 的 `GSDrawState` → 入队 → 出队 → 展开顶点 → 判断能否合批 → 设置十几项 GL 状态 → 上传 uniform → 绑定纹理 → 一次 draw。即使每一项只要 1 µs，1.4 万次就是 14 ms —— **光翻译就吃掉了整帧预算**。
3. **合批能救回一部分，但救不全。** 相邻同状态的图元可以合并，实测把 1.4 万图元压到 380–420 批次 `【文档】`，压缩比约 35:1。这已经很好了，但剩下的 400 批次 × 10–20 µs = 4–8 ms，仍然是大头。
4. **VU1 从“专用硬件”变成“x86 代码”。** 当年 300 MHz 的向量单元做几何变换，现在跑在 JIT 出来的 x86 上。它不再是免费的：实测 `vu_ms` 4000–4130/5s，也就是每帧 13.3–13.8 ms `【实测】`。

**这四条合起来，解释了本文的所有设计选择：**

| 设计选择 | 因为 |
|---|---|
| 不做全局排序 | 排序会破坏 GS 语义（混合顺序） |
| 不做跨帧延迟提交 | 静态重编译里“提交”就是函数调用，延迟等于改语义 |
| 不指望 UBO/状态缓存 | 它们优化“每次 draw 的效率”，而瓶颈是“draw 的数量与固定开销” |
| 前端 range 提交优先 | 它在**源头**减少提交次数，是唯一能动分子而不是分母的手段 |
| 分辨率阶梯优先 | 它绕开整条翻译链路，直接减少像素工作量，是唯一“不碰语义”的大杠杆 |
| 顶点环、纹理脏矩形 | 它们减少的是“固定开销里的某几项”，是渐进收益 |

**一句话总结**：模拟器的渲染器优化是“让每一次翻译更快”，静态重编译的渲染器优化是“让翻译次数更少，或者让翻译不必发生”。这两者的手段集几乎不重叠，所以从 PCSX2 之类的项目搬经验时，要先把这一点想清楚。

这个视角还能解释一个常见的误判：有人看到 `gs_ms` 高，就去优化 shader。但 shader 是 GPU 侧的，`gs_ms` 里绝大部分是 **CPU 侧的翻译与提交**。真正该看的是 `PS2X_GS_DISCARD_DRAWS=1` —— 它把 GPU 侧全部拿掉，剩下 1.3–1.5 s/5s 就是纯翻译成本 `【实测】`。这个数字不降下来，优化 shader 只是让 GPU 更闲。

### 4.14 语义鸿沟：GS 的“显存”与 GL 的“纹理对象”

这是整份设计里最底层的一节。如果不理解这个鸿沟，你会把渲染器写成“一个纹理缓存”，而它实际上必须是“一个显存镜像 + 一组派生视图”。

**GS 的世界：一块 4 MiB 的地址空间。**

- 没有“纹理对象”，只有地址。`TBP0` 是基址（256 字节为单位），`TBW` 是页宽（64 像素为单位），`PSM` 是格式。
- 数据按 **页 / 块 / 列 / 行** 四层 swizzle 排布。一个块是 256 字节；具体一个页覆盖多少行由格式决定。
- 同一段内存可以被当作纹理读、被当作渲染目标写、被当作深度缓冲用、被当作调色板读。**这是常态，不是特例。**
- 4 MiB 很小，所以纹理之间互相覆盖也是常态。游戏会反复复用同一块区域，只是换 `TBP0`/`PSM`。

**GL 的世界：一个个独立的纹理对象。**

- 每个纹理有自己的存储、自己的格式、自己的过滤与 wrap 参数。
- 采样一个渲染目标，要么把它 attach 到 FBO 再采（有读写冲突），要么拷贝一份。
- 没有“同一块内存的两种解释”，只有“两个对象，内容需要你手动同步”。

**五处鸿沟，以及本工程各自怎么填：**

| # | GS 的行为 | GL 没有对应物 | 本工程的做法 | 代价 |
|---|---|---|---|---|
| 1 | 4 MiB 单一地址空间，任意别名 | 对象隔离 | `GSTextureStore` 维护一份 VRAM 镜像，纹理是它的**派生视图** | 每次解码要读镜像 |
| 2 | swizzle 排布 | 全部线性 | 页表 + `GSSwizzle` 逐块重排 | 解码是 CPU 密集的 |
| 3 | CLUT 间接（索引 → 256 色） | 无（只能软件查表或在 shader 里查） | 索引纹理存 R8 + 256×1 的调色板纹理，shader 里 `texelFetch` | CLUT 变化不重解码索引（有意） |
| 4 | 同一内存多视图（Z 别名、重解释） | 无 | shader 里做地址映射 + 位重组 | 每条重解释路径都要单独验证 |
| 5 | 无 mip、只有双线性 | 有 mip 与各向异性 | 只取 `TEX1` 的 `linearFilter` 标志，不生成 mip | 远处纹理可能闪烁 |

**这个鸿沟带来的最重要的一条设计结论：**

> **不要做“纹理缓存”，要做“VRAM 镜像 + 视图缓存”。**

区别在哪？

- 纹理缓存的心智模型是“一张纹理解码一次，之后复用”。于是任何一次 VRAM 写入都会让你想“是不是该整张失效”——这就是现在“整张重解码”的来源。
- 视图缓存的心智模型是“VRAM 是真相，纹理只是某个地址区间的某个解释”。于是写入只需要记录“这些字节变了”，视图按需局部重建。这就是第 5.5 节脏矩形的理论基础。

这也解释了为什么“调色板图集”方案失败（第 7.4 节）：它试图把“CLUT 间接”这个 GS 特性压成“一个大纹理的多个行”，方向是对的（减少状态变化），但批次根本不是由 CLUT 决定的 —— 批次由 `TEST`/`PRIM`/`TEX0` 的真实变化决定。**在错误的层次上做了正确的优化，等于没做。**

再补一个容易忽略的推论：**因为 4 MiB 太小，游戏会把“当前帧的渲染目标”和“上一帧的纹理”放在同一块区域。** 所以任何“这个纹理在本帧内不会变”的假设都是错的。现有的失效机制（`BeginTransfer` 记录覆盖块 + `writeSeq`）是对的，需要加强的只是**粒度**，不是**机制**。

### 4.15 接口契约：v2 后端对外承诺什么

现有 `GSBackend` 的接口是被前端与线程队列共同依赖的。v2 不新增后端类型，但要给每个方法写清“前置条件 / 后置条件”，因为**这些条件就是第 6 章那些不变量的另一面**。

```cpp
// Contract notes are normative: a violation is a bug even if the picture looks right today.
struct GSBackend
{
    // Pre:  vram != nullptr, vramSize == 4 MiB, called once before any Submit.
    // Post: caps/policy filled and logged; GL objects created or `failed` set with a reason.
    virtual void Initialize(uint8_t *vram, uint32_t vramSize) = 0;

    // Pre:  `batch` fully describes one GS primitive (state + vertices), valid until return.
    // Post: either appended to the pending batch, or the pending batch was flushed first.
    //       Never reorders relative to previous calls.
    virtual void Submit(const GSPrimitiveBatch &batch) = 0;

    // Pre:  a transfer command was latched by the frontend.
    // Post: any pending draw is flushed first (draws must not see the new bytes);
    //       the write range is recorded so dependent textures invalidate.
    virtual void BeginTransfer(const GSTransferCommand &cmd) = 0;
    virtual void UploadImage(const uint8_t *data, uint32_t size) = 0;

    // Pre:  none.
    // Post: pending batch and shuffle queue are empty; all previously submitted draws were issued.
    virtual void Flush() = 0;

    // Pre:  none.
    // Post: same as Flush, plus any deferred GPU work is known complete.
    //       Used for FINISH semantics; must not be called per frame (it serialises).
    virtual void Sync(GSSyncReason reason) = 0;

    // Pre:  none.
    // Post: pending work flushed; a presentation frame for the current DISPFB is published.
    virtual PresentationFrame Present(const GSPresentationRequest &req) = 0;

    // Pre:  none (may be called between frames).
    // Post: all GPU objects released; RenderTarget ids remain valid until Reset().
    virtual void Reset() = 0;
};
```

**六条契约里最容易违反的两条：**

1. **`Submit` 的“永不重排”。** 任何“攒一攒再画”的实现都违反它。本文所有合批（`sameState`、shuffle 合批、range 提交）都只在**相邻**元素之间发生，这是“不重排”的具体化。
2. **`BeginTransfer` 的“先 flush 再记录”。** 顺序反了，之前的批次就会采到新字节（应该是旧字节），表现为“贴图提前一帧变化”。这类错误在静态画面里看不出来，只在动画中闪一下。

**为什么把契约写进文档而不是只写进代码注释？**
因为下一个改渲染器的人不会读你的注释，但会读设计文档。本工程的三个黑屏/花屏 bug 都与“某个方法的隐含前提被破坏”有关，而当时没有任何一份文档写过这些前提。

### 4.16 为什么不用帧图（frame graph）

现代渲染器的标准答案是“帧图”：把一帧声明成一组 pass 与资源，由框架推导依赖、插入 barrier、剔除无用 pass、重排以提高缓存命中。这套东西在 3A 引擎里是标配，所以很多人会问：为什么这里不用？

**因为帧图的三个前提，这个项目一个都不成立。**

**前提一：pass 之间可以重排。**
帧图的核心价值是“你声明依赖，我决定顺序”。但 GS 的混合、alpha test、DATE、Z 别名全部依赖**提交顺序**，而且不是“数据依赖”，是“硬件状态机依赖”。举例：同一块颜色缓冲先被当作目标写、再被当作纹理采样、再被当作 Z 缓冲读（Z 别名）——这三步的先后不能交换，而帧图的依赖图里它们可能表现为三个无冲突的节点。

**前提二：barrier 可以从依赖推导。**
帧图假设“写资源 A、读资源 A ⇒ 插一个 barrier”。但这里最麻烦的同步不是“资源读写”，而是 **shuffle**：它不是画三角形，是把 16 位目标的通道拆开再拼回去，本质是内存重排。它的“依赖”是“目标内存的位布局”，帧图没有这个概念，无法推导。

**前提三：pass 是粗粒度的。**
帧图的一个 pass 通常是一整张 RT 的绘制。而这里的“pass”是 380–420 个批次，每个批次的状态都不同。把每个批次当一个 pass，帧图的调度开销会超过它省下的东西。

**立即模式在这个场景里的三个实际优势：**

| 优势 | 具体表现 |
|---|---|
| 顺序即正确 | 代码的书写顺序就是 GS 的提交顺序，不需要在脑子里建依赖图 |
| 调试直观 | `GOW_GS_HW_ONLY=100-120` 能只画第 100–120 个批次，帧图做不到这么细 |
| 内存低 | 没有 pass 描述、没有资源生命周期管理、没有 transient 分配器 |

**代价也很实在：**

- 无法跨状态合批（这是第 7 章反复说的“批次由真实状态变化决定”）。
- barrier 要手工插，漏一个就是闪烁（不变量 #8）。
- 无法自动剔除“画了但看不见”的 pass。

**结论：v2 不引入帧图。** 但 v3 可以评估一个**子集**：只用它做“barrier 分析与插入”，不做重排、不做剔除、不做 pass 合并。这个子集的风险可控（错了就是多一个 barrier，慢一点），收益是“不再手工漏 barrier”。这是唯一值得从帧图借的东西。

判断依据很简单：**任何让你“重排提交顺序”的框架，在这个项目里都是错的。** 这一条比帧图本身重要。

---

## 5. 关键子系统的实现

这一章给可直接落地的代码。**所有代码注释用英文**（本工程惯例），命名用英文（继承自 Tobiichi 的西班牙语标识符保留原样）。

### 5.1 能力加载器：在 `GSGL::Api` 上加一层

现有 `Api` 是一张函数指针表，`hwRaster` 由“必需函数是否全部加载成功”决定（`gs_gl.cpp:217`）。v2 不改这个机制，只加三件事：可选函数、caps 结构、日志。

```cpp
// gs_gl.h — additions. Nothing here changes an existing call site.
struct DeviceCaps
{
    int major = 0, minor = 0;
    enum class Vendor { Unknown, Intel, Amd, Nvidia, Apple, Mesa } vendor = Vendor::Unknown;
    std::string renderer;              // GL_RENDERER, for logs and profiles
    int maxTextureSize = 0;
    int maxUboBindings = 0;
    int uboAlign = 0;                  // GL_UNIFORM_BUFFER_OFFSET_ALIGNMENT
    bool hasTexBarrier = false;        // glTextureBarrier (ARB_texture_barrier)
    bool hasBufferStorage = false;     // glBufferStorage (ARB_buffer_storage)
    bool hasVertexAttribBinding = false; // glBindVertexBuffer + glVertexAttribFormat/Binding
    bool hasFenceSync = false;
    bool hasDebugOutput = false;       // KHR_debug
    bool hasTimerQuery = false;
    int maxSamples = 0;
};

// Fills `out` from the *current* context. Must run after Create(), before any GL object.
bool ProbeCaps(const Api &gl, DeviceCaps &out);
```

实现要点（三个容易写错的地方）：

```cpp
bool ProbeCaps(const Api &gl, DeviceCaps &out)
{
    const char *ver = gl.GetString(kVersion);
    if (!ver) return false;
    // Parse "4.3.0 - Build 20.19..." — major.minor only; the rest is vendor noise.
    if (std::sscanf(ver, "%d.%d", &out.major, &out.minor) != 2) return false;

    const GLubyte *vend = gl.GetString(kVendor);
    const GLubyte *rend = gl.GetString(kRenderer);
    out.renderer = rend ? reinterpret_cast<const char *>(rend) : "";
    const std::string v = vend ? reinterpret_cast<const char *>(vend) : "";
    // Match on substrings, never equality: "Intel" / "Intel Inc." / "INTEL" all occur.
    if (v.find("Intel") != std::string::npos) out.vendor = DeviceCaps::Vendor::Intel;
    else if (v.find("NVIDIA") != std::string::npos) out.vendor = DeviceCaps::Vendor::Nvidia;
    else if (v.find("ATI") != std::string::npos || v.find("AMD") != std::string::npos) out.vendor = DeviceCaps::Vendor::Amd;
    else if (v.find("Mesa") != std::string::npos || v.find("X.Org") != std::string::npos) out.vendor = DeviceCaps::Vendor::Mesa;

    gl.GetIntegerv(kMaxTextureSize, &out.maxTextureSize);
    // The alignment query is only meaningful when UBOs exist; guard it.
    if (gl.GetIntegerv && gl.GetIntegervPtr) { /* see note below */ }
    return true;
}
```

> **坑**：`GL_UNIFORM_BUFFER_OFFSET_ALIGNMENT` 在 3.3 以下不存在，查询会给 0。若 `uboAlign == 0`，一律按 **256** 处理（NVIDIA 的值，最保守）。这条规则来自本工程的一次真实事故：`DrawUniforms` 是 192 B，直接用 192 当槽距，在 Intel 上合法、在 NVIDIA/老 AMD 上每隔一槽被驱动拒绝，着色器继续读上一槽 ⇒ 花屏 `【实测根因】`。

### 5.2 驱动画像：把“已知的坏路径”写成表

```cpp
// A profile is a *decision*, not a capability. Keep it small and evidence-backed:
// every row must reference a measurement in docs/ or a patch header.
struct DriverProfile
{
    const char *match;       // substring of GL_RENDERER (lowercased compare)
    bool        stateCache;  // allow skipping redundant GL state
    bool        ubo;         // allow std140 UBO instead of glUniform
    bool        persistentMap;
    int         ringMb;      // vertex ring size
};

static constexpr DriverProfile kProfiles[] = {
    // Intel iGPUs: redundant setters are the cheap path (measured: cache 53→37 fps, UBO 53→50.7).
    {"intel(r) hd graphics", false, false, true,  16},
    {"intel(r) uhd graphics", false, false, true, 16},
    {"intel(r) iris",         false, false, true, 32},
    // Unknown Intel parts: same conservative policy.
    {"intel",                 false, false, true, 16},
    // AMD/NVIDIA: allow the experiments, but they must still be A/B'd on the target machine.
    {"radeon",                true,  true,  true, 32},
    {"geforce",               true,  true,  true, 32},
    {"nvidia",                true,  true,  true, 32},
};

static DriverProfile PickProfile(const DeviceCaps &caps)
{
    std::string r = caps.renderer;
    std::transform(r.begin(), r.end(), r.begin(), [](unsigned char c) { return std::tolower(c); });
    for (const DriverProfile &p : kProfiles)
        if (r.find(p.match) != std::string::npos)
            return p;
    // Unknown device: the conservative row. Never assume a modern driver is well-behaved.
    return DriverProfile{"", false, false, true, 16};
}
```

**这个表的设计哲学：默认值是“不信任”。** 只有画像明确说“这台机器上状态缓存/UBO 测过是正的”，才允许打开。这看起来保守到过分，但本工程的记录是：三条“常识上该更快”的优化在这块卡上全部为负，而每次负优化的代价是一到两天的实现 + 一轮 A/B。

`GOW_GS_POLICY=force-default|force-modern` 保留给要复现问题的人。

### 5.3 顶点环：现有实现里有一个潜伏的越界

现有实现（`gs_hw_backend.cpp:2583`）逻辑是：

```cpp
uint32_t ringAppend(const void *data, size_t bytes)
{
    const uint32_t need = static_cast<uint32_t>((bytes + 63u) & ~static_cast<size_t>(63u));
    if (vertexRingOffset + need > kVertexRingBytes)      // wrap
    {
        if (vertexFence) { /* ClientWaitSync ... */ g.DeleteSync(vertexFence); }
        vertexFence = g.FenceSync(kSyncGpuCommandsComplete, 0);
        vertexRingOffset = 0;
    }
    const uint32_t at = vertexRingOffset;
    std::memcpy(vertexRingMap + at, data, bytes);        // ← 若 bytes > kVertexRingBytes，这里越界
    vertexRingOffset += need;
    return at;
}
```

**这是一个真实存在的、目前没被触发的问题。** 如果某一次 `bytes > 32 MB`（约 52 万顶点的一个批次），`vertexRingOffset + need > kVertexRingBytes` 成立，offset 归零，然后 `memcpy` 从 0 开始写 `bytes` 字节 —— 直接写穿映射区。今天没炸，是因为实测最大批次 84 KB `【实测】`；但“今天没炸”不等于“不会炸”，一个极端场景（例如某段过场的全屏四边形洪流）就可能触发，而症状是随机花屏或崩溃，极难定位。

v2 的加固版：

```cpp
// One ring, one fence. Returns 0 and sets `tooBig` when the batch cannot fit at all:
// the caller must then fall back to a per-batch buffer instead of writing past the map.
uint32_t ringAppend(const void *data, size_t bytes, bool &tooBig)
{
    tooBig = false;
    const size_t need = (bytes + kVertexAlign - 1u) & ~(kVertexAlign - 1u);
    if (need > kVertexRingBytes)
    {
        // Never wrap into a region smaller than the write: that is a heap overflow, not a slow path.
        tooBig = true;
        return 0;
    }
    if (vertexRingOffset + need > kVertexRingBytes)
    {
        if (vertexFence)
        {
            // Wait, but do not lie: if the GPU has not caught up, growing the ring is the only safe move.
            const GLenum st = g.ClientWaitSync(vertexFence, 0, 0);
            if (st == kTimeoutExpired)
                g.ClientWaitSync(vertexFence, kSyncFlushCommandsBit, kFenceTimeoutNs);
            g.DeleteSync(vertexFence);
            vertexFence = nullptr;
        }
        vertexFence = g.FenceSync(kSyncGpuCommandsComplete, 0);
        vertexRingOffset = 0;
        ++ringWraps;
    }
    const uint32_t at = vertexRingOffset;
    if (vertexRingMap)
        std::memcpy(vertexRingMap + at, data, bytes);
    else
    {
        g.BindBuffer(kArrayBuffer, vbo);
        g.BufferSubData(kArrayBuffer, at, static_cast<GLsizeiptr>(bytes), data);
    }
    vertexRingOffset += static_cast<uint32_t>(need);
    return at;
}
```

调用侧：

```cpp
if (vertexRing)
{
    bool tooBig = false;
    const uint32_t off = ringAppend(verts.data(), bytes, tooBig);
    if (tooBig)
    {
        // Rare: a single batch larger than the ring. Draw it from a throwaway buffer.
        // This path must exist, otherwise the guard above turns a perf bug into a crash.
        g.BindVertexArray(vao);
        g.BufferData(kArrayBuffer, static_cast<GLsizeiptr>(bytes), verts.data(), kStreamDraw);
        g.BindVertexBuffer(0, vbo, 0, sizeof(HwVertex));
        ++oversizedBatches;
    }
    else
        g.BindVertexBuffer(0, vbo, off, sizeof(HwVertex));
}
```

三条必须同时成立的性质：

1. **`need ≤ kVertexRingBytes` 恒成立**，否则走专供路径。这是把“未定义行为”变成“慢但正确”。
2. **回绕前一定有 fence**，且 fence 是在回绕点插入的 —— 它覆盖“到目前为止所有已发出的命令”，正好包括用到被覆盖区域的那些 draw。
3. **等待超时不等于可以继续。** 现有代码在第二次 `ClientWaitSync` 超时后仍然继续写——这在 GPU 卡死时会导致画面错乱。v2 的选择是：超时后把 `vertexRing` 置为 false（退化为 `BufferSubData` 路径），并打一条 `[gs-hw] ring fence timeout, degrading` 日志。宁可慢，不要错。

另外把 `ringWraps`、`oversizedBatches` 加进 `GOW_GS_HW_STATS` 的每 5 秒行。**这两个数直接告诉你环够不够大**：`ringWraps/帧 > 2` 就该加大环或减少每帧顶点。

### 5.4 着色器变体：少而准

老 iGPU 上着色器编译很贵（一个完整 program 可能 100–300 ms），而且**编译发生在启动瞬间**，用户看到的是“点了没反应”。所以变体策略是：**最多 4 个 program，按“是否采样 + 是否索引 + 是否写深度”分，其余全部走 uniform 分支。**

变体 key：

```cpp
enum : uint32_t
{
    kVariantTex     = 1u << 0,  // samples a texture at all
    kVariantIndexed = 1u << 1,  // PSMT8/PSMT4: fetch index, then palette
    kVariantDepth   = 1u << 2,  // writes gl_FragDepth (Z alias / Z source)
};

static uint32_t VariantKey(const GSDrawState &s)
{
    uint32_t k = 0;
    if (s.prim.tme) k |= kVariantTex;
    if (IsIndexed(s.context.tex0.psm)) k |= kVariantIndexed;
    if (s.prim.tme && s.context.tex0.psm == kPsmZ) k |= kVariantDepth;
    return k;
}
```

为什么不用“一个巨型 shader + 全 uniform”？
因为老驱动对片元着色器里的 `if (uIndexed)` 往往不做分支扁平化，纹理采样指令会无条件执行（采样单元占用是实打实的）。实测过“单 program 全分支”的版本，重过场比变体版慢 6–9% `【推断，基于同一批次下多一次无用采样的典型成本，未单独 A/B】`。这一条要作为**待验证**项写进日志，不要当成定论。

变体缓存与延迟编译：

```cpp
struct ProgramVariant { GLuint program = 0; GLint loc[32] = {}; bool compiled = false; };
ProgramVariant variants[8];   // indexed by VariantKey; only 4 combinations occur in practice

GLuint ProgramFor(uint32_t key)
{
    ProgramVariant &v = variants[key & 7u];
    if (v.compiled) return v.program;
    // Build from a common prelude + per-variant #defines. One compile per key, ever.
    v.program = LinkVariant(key);
    v.compiled = true;
    return v.program;
}
```

**启动预算**：4 个变体 × 200 ms = 0.8 s。可以接受，但要显示在加载屏上（启动器已经有 `LoadingScreen.qml`）。如果超过 2 s，就改成“只预编译 `kTex`，其余首次用到时编译”，代价是第一次进场景会卡一下。

### 5.5 纹理脏矩形：把“整张重解码”变成“只补改动的块”

先扩上传记录：

```cpp
struct UploadRecord
{
    uint32_t lo, hi;      // byte range in VRAM (existing)
    uint64_t seq;         // existing
    uint16_t x0, y0, x1, y1;  // NEW: pixel rect in the *destination texture's* space, already block-aligned
};
```

判定与重解码：

```cpp
// Returns true when only a sub-rect needs re-decoding; fills `r` with it.
bool DirtyRectFor(const Texture &t, uint32_t &outX0, uint32_t &outY0, uint32_t &outX1, uint32_t &outY1)
{
    uint32_t x0 = t.pxW, y0 = t.pxH, x1 = 0, y1 = 0;
    for (const UploadRecord &u : uploadLog)
    {
        if (u.seq <= t.decodedSeq) continue;               // already baked in
        x0 = std::min<uint32_t>(x0, u.x0); y0 = std::min<uint32_t>(y0, u.y0);
        x1 = std::max<uint32_t>(x1, u.x1); y1 = std::max<uint32_t>(y1, u.y1);
    }
    if (x1 <= x0 || y1 <= y0) return false;                // nothing new
    const uint64_t area = uint64_t(x1 - x0) * (y1 - y0);
    const uint64_t whole = uint64_t(t.pxW) * t.pxH;
    // Safety valve: scattered small writes must not turn into dozens of tiny uploads.
    if (area * 100 >= whole * 60)
    {
        outX0 = 0; outY0 = 0; outX1 = t.pxW; outY1 = t.pxH;
        return true;
    }
    outX0 = x0 & ~3u; outY0 = y0 & ~3u;                    // 4x4 block granularity of the GS page tables
    outX1 = std::min<uint32_t>(t.pxW, (x1 + 3u) & ~3u);
    outY1 = std::min<uint32_t>(t.pxH, (y1 + 3u) & ~3u);
    return true;
}
```

然后：

```cpp
if (dirty)
{
    if (full) { g.TexImage2D(..., t.pxW, t.pxH, decoded.data()); }
    else
    {
        // Re-decode only the rect, then upload it into the existing storage.
        DecodeRect(t, x0, y0, x1, y1, scratch);
        g.TexSubImage2D(kTexture2D, 0, x0, y0, x1 - x0, y1 - y0, kRgba, kUnsignedByte, scratch.data());
    }
    t.decodedSeq = writeSeq;
}
```

三个陷阱：

1. **`TexSubImage2D` 不改变存储**，所以第一次必须走 `TexImage2D` 建存储；两者不能混着“先 Sub 后 Image”，否则老驱动会对不可变存储报 `GL_INVALID_OPERATION`。
2. **调色板纹理（256×1）不要做脏矩形**，它太小，判定成本大于收益。
3. **重解释路径（reinterpret）不要做脏矩形**，因为它的采样地址是 shader 算出来的，脏矩形无法表达。只对直接色与索引色做。

### 5.6 shuffle 合批：只合“同目标 + 同模式 + 连续”

```cpp
struct ShuffleKey
{
    uint32_t dstId, srcId;
    uint16_t dstHalf, srcHalf, srcZ;
    bool operator==(const ShuffleKey &o) const
    {
        return dstId == o.dstId && srcId == o.srcId && dstHalf == o.dstHalf &&
               srcHalf == o.srcHalf && srcZ == o.srcZ;
    }
};
```

合批规则（写死，不要“聪明”）：

```
遇到一个 shuffle 精灵：
  若队列空 → 入队，记 key
  若 key 相同 → 入队（同一批）
  若 key 不同 → flushShuffle()，再入队
另外三个强制 flush 点（不可省）：
  ① 任何普通 draw 之前（顺序依赖）
  ② BeginTransfer / LoadClut / TextureFlush（VRAM 内容变了）
  ③ Present 之前
```

`flushShuffle` 一次 FBO 绑定 + 一次 `glDrawArrays`，比“每精灵一次”省下的是 FBO 切换与 program 切换。预期收益取决于原实现的 flush 频率：如果原来是“每 state run 一次”，而一个 state run 平均只有 3 个 shuffle 精灵，那收益约 10–15%；如果平均有 20 个，收益接近 0（已经很合了）。**先测 `shuffles / shuffleDraws` 这个比值**，小于 8 就不值得做。

### 5.7 分辨率阶梯：带滞回的控制器

```cpp
// Operates on the *internal* resolution only; never touches the window.
struct WorkPointLadder
{
    static constexpr float kSteps[] = {0.35f, 0.45f, 0.55f, 0.70f, 0.85f, 1.00f};
    static constexpr int   kN = 6;

    int   index = 3;                  // start at 0.70: safe on an iGPU, not ugly
    double targetFps = 59.0;
    double lastSwitch = -1e9;         // seconds
    int   stableTicks = 0;
    double lockUntil = -1e9;

    // Called once per second with the measured guest rate.
    float Update(double now, double fps)
    {
        if (now < lockUntil) return kSteps[index];
        if (std::fabs(now - lastSwitch) < 2.0) return kSteps[index];   // cooldown

        if (fps < targetFps - 2.0)
        {
            stableTicks = 0;
            if (index > 0)
            {
                --index;
                lastSwitch = now;
                return kSteps[index];
            }
        }
        else if (fps > targetFps + 1.0)
        {
            stableTicks = 0;
            if (index + 1 < kN && now - lastSwitch > 6.0)              // up is stricter
            {
                ++index;
                lastSwitch = now;
                return kSteps[index];
            }
        }
        else if (++stableTicks >= 3)
        {
            stableTicks = 0;
            lockUntil = now + 10.0;                                     // stop fiddling
        }
        return kSteps[index];
    }
};
```

四个细节决定这个控制器是好用还是烦人：

1. **降档门槛 `fps < 57`，升档门槛 `fps > 60`。** 中间留 3 帧死区，防止在 59 附近抖动。
2. **升档冷却 6 s，降档冷却 2 s。** 升错了要马上能退回来，升对了要等久一点确认稳定。
3. **稳定 3 秒后锁 10 秒。** 玩家在过场里帧率本来就波动，控制器不该跟着过场抽搐。
4. **切换要重建 RT**，这是几十毫秒的尖峰。所以切换时打一条 `[gs-hw] workpoint 0.70 -> 0.55 (fps 52.1)`，方便把卡顿和切换对上账。

`PS2X_GS_HW_SCALE=auto` 保留为“开启阶梯”的入口，固定值则关闭阶梯（调试用）。

### 5.8 呈现：贴合窗口 + 只画新帧

```cpp
// Bind the window's back buffer, blit the shared texture into it, done.
// No shaders, no extra passes: on an iGPU every full-screen pass costs a third of the rate.
void PresentToWindow(GLuint sharedTex, int texW, int texH, int winW, int winH)
{
    // Integer-fit the picture when it is smaller than the window: scaling 412x360 to 1280x720
    // with GL_LINEAR costs more than it looks and softens the pixels anyway.
    int dw = winW, dh = winH, dx = 0, dy = 0;
    if (texW <= winW && texH <= winH)
    {
        const int scale = std::min(winW / texW, winH / texH);
        if (scale >= 1)
        {
            dw = texW * scale; dh = texH * scale;
            dx = (winW - dw) / 2; dy = (winH - dh) / 2;
        }
    }
    g.BindFramebuffer(kFramebuffer, 0);
    g.Viewport(0, 0, winW, winH);
    g.ClearColor(0, 0, 0, 1);
    g.Clear(kColorBufferBit);
    g.BindFramebuffer(kReadFramebuffer, sharedFbo);
    g.BindFramebuffer(kDrawFramebuffer, 0);
    g.BlitFramebuffer(0, 0, texW, texH, dx, dy, dx + dw, dy + dh,
                      kColorBufferBit, scale >= 1 ? kNearest : kLinear);
}
```

以及一个经常被忘的守卫：

```cpp
// Present the same guest frame at most once per host refresh. Re-blitting an unchanged
// picture burns iGPU bandwidth and makes the frame-time graph lie.
if (renderSequence == lastPresentedSequence && now - lastPresentMs < 8.0)
    return;
```

### 5.9 批次装配器：把“什么时候 flush”写成一个状态机

现有实现用 `havePending` + `sameState` 两个变量表达“当前是否有一批待发”，逻辑正确但边界分散在 `submit` 的多个分支里。v2 把它收成一个显式的状态机，好处是**每个 flush 点都能被数出来**，而“漏 flush”正是本工程最贵 bug 的另一面。

```
状态：Empty → Open(state) → Full → Flush → Empty

转移规则：
  Empty  + Submit(s)                    → Open(s)      记录 pendingState
  Open   + Submit(s) 且 sameState       → Open(s)      追加顶点
  Open   + Submit(s) 且 !sameState      → Flush → Open(s)
  Open   + 任何“改变 VRAM/目标”的命令    → Flush（见下表）
  Open   + 顶点数 > kMaxBatchVerts       → Flush → Open(s)   ← 防单批次过大
  Full   + 任意                        → Flush → Empty
  Flush  + pending 为空                 → Empty（不产生 GL 调用）
```

必须触发 flush 的命令，一条都不能漏：

| 命令 | 为什么必须 flush |
|---|---|
| `BeginTransfer` / `UploadImage` | VRAM 内容变了，之前批次的纹理采样结果会变 |
| `LoadClut` | 调色板变了，索引纹理的颜色会变 |
| `TextureFlush` | 语义上就是“之后的采样必须看到之前的内容” |
| `ClearFramebuffer` | 清屏必须在之前的绘制之后 |
| `Sync` / `FINISH` | guest 在等“之前所有绘制完成” |
| `Present` | 呈现的是“到此刻为止”的画面 |
| 目标切换（fbp 变） | 不同 FBO，不能同一批 |

代码骨架：

```cpp
enum class BatchState { Empty, Open, Flushing };

// The single place that decides "do these two primitives share a draw".
// Keep it identical to GSDrawState::operator== — a looser comparison was measured
// to save no batches and cost branches (docs, section 7.4).
void Submit(const GSPrimitiveBatch &b)
{
    if (state == BatchState::Open && !(pendingState == b.state))
        FlushPending();
    if (state == BatchState::Empty)
    {
        pendingState = b.state;
        state = BatchState::Open;
    }
    Expand(b, pending);                       // triangles/sprite/line → HwVertex
    if (pending.size() >= kMaxBatchVerts)     // 32k verts = 2 MB, well under the ring
        FlushPending();
}

void FlushPending()
{
    if (state != BatchState::Open) return;
    state = BatchState::Flushing;
    ++batchSerial;                            // sprites of the next batch must not seam with these
    FlushShuffle();                           // order matters: shuffles were queued before
    if (!pending.empty())
        Draw(pendingState, pending);
    pending.clear();
    state = BatchState::Empty;
    ++statBatches;
}
```

**`kMaxBatchVerts` 为什么必须存在？** 因为“相邻同状态”可能是无穷长的（例如一整屏的粒子）。没有上限时，一个批次可能长到超过顶点环容量——这正是 5.3 节那个越界 bug 的另一条触发路径。加上限之后，批次大小有界，环的容量规划才有意义。

这个上限还有一个副作用是好的：它让每批次的 GPU 执行时间有界，减少“一个超长批次把整个 GPU 队列堵住”的尖峰。32k 顶点在 HD 4400 上约 0.3–0.5 ms，是个合理的粒度。

### 5.10 GS 混合模式到 GL 的完整映射

这是整个渲染器里最容易写错、也最难通过“看画面”发现错误的地方。GS 的 ALPHA 寄存器给的是四个选择器（A/B/C/D）加一个 FIX 常量，公式是：

```
Cv = (A - B) × C / 128 + D
```

`/128` 是 GS 的定点约定（128 = 1.0）。A/B/C/D 的取值是 0=Cs（源色）、1=Cd（目标色）、2=FIX（常量）、3=Ad（目标 alpha）。FIX 在 ALPHA 的高 32 位（`(alpha >> 32) & 0xFF`）。

能直接映射到 GL 固定功能混合的六种组合 `【文档，gs_hw_backend.cpp:2492-2497】`：

| A | B | C | D | GS 公式 | GL 状态 | 出现场景 |
|---|---|---|---|---|---|---|
| 0 (Cs) | 1 (Cd) | 0/2 | 1 (Cd) | `Cs·C + Cd·(1−C)` | `SRC_ALPHA / ONE_MINUS_SRC_ALPHA`（C=Ad）或 `CONSTANT_COLOR / ONE_MINUS_CONSTANT_COLOR`（C=FIX） | 标准 alpha 混合（半透明、雾） |
| 0 (Cs) | 2 (FIX) | 2 (FIX) | 1 (Cd) | `Cs·C + Cd` | `cs / ONE` | 加性混合（光晕、能量） |
| 2 (FIX) | 1 (Cd) | 2 (FIX) | 1 (Cd) | `Cd·(1−C)` | `ZERO / cd` | 淡出到黑 |
| 0 (Cs) | 2 (FIX) | 2 (FIX) | 2 (FIX) | `Cs·C` | `cs / ZERO` | 纯替换 |
| 2 (FIX) | 0 (Cs) | 2 (FIX) | 2 (FIX) | `0` | `ZERO / ZERO` | 用来“清一块”（配合 scissor） |
| 2 (FIX) | 0 (Cs) | 2 (FIX) | 1 (Cd) | `Cd − Cs·C` | `FUNC_REVERSE_SUBTRACT` + `cs / ONE` | 反向减（Z 反转、遮罩擦除） |

**剩下的所有组合都走 shader 软件混合（`soft` 路径）**，也就是在片元着色器里读目标色（`uDest`），自己算 ALPHA 选择器与 COLCLAMP 环绕。这条路径慢，但正确。

为什么必须要它？一个具体的例子 `【文档，代码注释】`：角色的阴影体（shadow volume）用 `ALPHA = 0x68`（A=Cs, B=FIX, C=FIX, D=Cd，G 通道先清到 127），把三角形画两遍：一遍加 255（等价于 −1），一遍加 1。**它靠 G 通道的环绕（wrap）来计数**：被覆盖 n 次的区域得到 127 − n + n = 127，没被覆盖的区域保持 127。而 GL 的固定功能混合是**饱和**的（clamp 到 [0,1]），第一遍加到 255 就饱和，第二遍的 +1 无法撤销 ⇒ 阴影体覆盖的所有地方都被压黑，表现为“墙上的黑色楔形、Kratos 脚下的矩形”`【实测根因】`。

所以 `COLCLAMP = 0`（不钳制）时必须 `soft = true`，让 shader 自己用 `fract()` 式环绕。这条不能“优化掉”：它不是冗余分支，它是阴影正确性的唯一保障。

**给实现者的三条规矩：**

1. **不要用“当前数据上等价”的化简。** TFX=2/3 的 `Cv = 0x80 + (Ct × Cv) / 128` 里的 `0x80` 是常量，不是顶点 alpha。旧代码写成 `+ v.a`，在 alpha=128 的数据上完全等价（GOW II 从未暴露），到 alpha=255 就爆白块（GOW 1 标题的云雾）`【实测根因】`。
2. **`/128` 不是 `/255`。** 这两个差 0.5%，肉眼看不出来，但在“加 255 再减 1”的计数技巧上会累积成错误。
3. **每个 fallback 都要计数。** `stats.unsupportedBlend` 是判断“我的快路径覆盖率”的唯一指标。它高，说明有大量批次在走 shader 混合，那就是性能与正确性的双重风险点。

### 5.11 帧节奏：为什么“解掉 60 上限”不是提速手段

这一节处理一个高频误解：**既然只有 45 帧，那把帧率上限解掉不就行了？**

不行。原因在于这个上限不是渲染器的节流，而是**游戏逻辑的节拍**。GoW 的时间步进绑在 PS2 的 60 Hz VBlank 上：游戏的物理、动画、脚本计时都以“每 VBlank 一帧”为单位。`TOBIICHI_VENTANA_FPS=0` 解掉的是**窗口呈现**的上限，不是 guest 的节拍；它会让 `host_hz` 飙到几百，但 `guest_flip_hz` 一点不变，而且画面会出现“同一 guest 帧被画多次”的抖动。

那这个变量有什么用？**测天花板。** 当 `host_hz` 被限在 60 时，`host_wait` 会吃掉所有余量，你看不出“CPU 到底还剩多少”。解掉上限后，`host_wait` 归零，剩下的 `guest_wait + gs_ms + vu_ms` 才是真实占用。这是一个诊断工具，不是性能开关。

**三种帧节奏，三种读法：**

| 形态 | `host_wait` | `guest_wait` | 含义 | 该做什么 |
|---|---|---|---|---|
| 贴顶 | 接近满（4.8 s/5s） | 有一定值 | 已经 60，窗口在等刷新 | 什么都不做，只防退化 |
| 欠载 | 低 | 接近满 | guest 在等 VBlank，但没到 60？矛盾 → 说明有同步点卡住 | 查 `gs_ms` 的 FINISH 与队列背压 |
| 受限 | 低 | 低 | 谁都没在等，纯忙 | 真正的性能问题，按第 7 章归因 |

**“欠载”那一行是最容易被误读的。** 直觉是“`guest_wait` 高 = 有余量”，但如果 `host_hz` 只有 45，说明 guest 在等一个**不该等的东西** —— 通常是 GS 队列满导致的背压，或者某个 `FINISH` 同步点。这时候优化 shader 毫无意义，要看的是 `gs_ms` 里的等待成分。

**呈现抖动**是另一个独立问题：一帧被画两次、下一帧一次不画。玩家感受到的是“一顿一顿”，但平均帧率看起来正常。v2 的处理是第 5.8 节那个守卫 —— 同一 `renderSequence` 在 8 ms 内不重复画。代价是极少数情况下会少画一帧，收益是节奏稳定。**在 60 Hz 显示器上，稳定的 58 帧比抖动的 60 帧更好受。**

**vsync 的取舍：**

| 设置 | 撕裂 | 延迟 | 建议 |
|---|---|---|---|
| vsync 开 | 无 | +1 帧 | 默认 |
| vsync 关 | 有 | 少 1 帧 | 只在“必须低延迟”的场景（如 QTE 密集处）作为选项 |

本工程已经有 QTE 的 hold-to-mash 与按键和弦处理（patch 53/57/58），说明输入延迟是被认真对待过的。但 vsync 默认仍然应该开 —— 老显卡上撕裂的观感损失大于 16 ms 的延迟收益。

---

## 6. 无 bug 的工程方法

先把话说透：**渲染器的 bug 不是“写错公式”，而是“两个真相不一致”。**

本工程历史上代价最高的三个 bug，全部属于这一类：

| bug | 两个真相 | 症状 |
|---|---|---|
| 场景全黑、标题正常 | `boundProgram`（缓存说“绘制程序绑着”）vs 实际绑定的 program（shuffle 的） | 3D 场景全黑，菜单正常 |
| 花屏残留 + `GL 0x502` + 帧率 10→60 | 同上，发生在 `presentFrame` 恢复 VAO 时 | 随机花屏，`glUniform` 报错 |
| 几何撕裂 / 黑块 / 贴图乱 | CPU 写入位置 vs GPU 还在读的位置 | 顶点环回绕后覆盖 |

**这三类都不可能靠“更仔细地写代码”避免，只能靠断言与审计。** 下面四节分别是：把不变量写下来、把审计变成命令、把回归变成自动、把失败变成可见。

### 6.1 十条不变量

每一条都必须能写成一行 `assert` 或一个计数器。写在 `Impl` 的私有方法里，用 `GOW_GS_STRICT=1` 控制是否 abort，默认只计数并每 5 秒打一次。

| # | 不变量 | 检查点 | 违反后果 |
|---|---|---|---|
| 1 | 任何 `UseProgram(x)` 之后 `boundProgram == x`，或立即 `invalidateState()` | `UseProgram` 包装函数 | 整帧用错着色器（黑屏/花屏） |
| 2 | `pending.size() == 0` 于帧末 | `EndFrame` | 漏画一批（画面缺块） |
| 3 | `shuffleQuads[0/1].empty()` 于帧末 | `EndFrame` | 漏画 shuffle（贴图错色） |
| 4 | `vertexRingOffset ≤ kVertexRingBytes` 且每次 `need ≤ kVertexRingBytes` | `ringAppend` | 堆越界（随机崩溃） |
| 5 | 跨批次引用的目标以 `id` 存储，`flush` 时按 id 重查 | `flushShuffle` / `draw` | 悬垂指针（画到随机目标） |
| 6 | FBO 创建后 `CheckFramebufferStatus == COMPLETE` | `createTarget` / `attachDepth` | 整帧黑或驱动未定义行为 |
| 7 | 若用 UBO：`slotStride ≥ uboAlign` 且 `offsetof` 与 std140 布局一致 | `static_assert` + 启动检查 | 隔槽读错（花屏） |
| 8 | 采样当前 FBO 附着纹理前，必须有 `TextureBarrier` 或 `glFinish` | `drawOne` 的 `src` 分支 | 读到旧内容（闪烁） |
| 9 | 帧末 FBO 回到 0、scissor 关闭、viewport 恢复 | `EndFrame` | present 画到错误区域 |
| 10 | 所有环境变量解析结果被 clamp 到合法区间；非法值 → 默认值 + 一条日志 | 解析点 | 启动即崩或静默降级 |

第 1 条值得单独展开，因为它是本工程最贵的一课。

### 6.2 状态审计：把“第二真相”钉死

规则只有一句：

> **任何 `UseProgram(其他 program)` 的路径，必须以 `boundProgram = 所绑 program` 收尾，或事后 `invalidateState()`。**

已知的三处（都在 `gpu/gs_hw_backend.cpp`）`【文档】`：

| 路径 | 症状 | 修复 |
|---|---|---|
| `drawShuffle()` | 场景全黑、标题正常（标题 `shuffles=0`） | 末尾 `boundProgram = shuffleProgram;` |
| `presentFrame()` | 花屏残留 + `GL 0x502` + 帧率 10→60 | 恢复 VAO 处 `d.boundProgram = d.presentProgram;` |
| 其他新增通道（clut、init、诊断） | 未爆但同类 | 新增前先过审计清单 |

为什么难发现：`drawOne()` 的顺序是**先 `flushShuffle()` 再走去重检查**，所以泄漏发生在“这批绘制已经过检查之后”，第一帧就中招，且只有场景（有 shuffle）触发。也就是说，如果你只测标题，你永远看不到这个 bug。

审计命令（每次改渲染器前跑一遍）：

```bash
grep -rn "UseProgram(" engine/runtime/PS2Recomp/ps2xRuntime/src/lib/gs/gpu/
# 对每一处，检查同一函数内是否更新 boundProgram / 调 invalidateState
```

v2 的做法是**让这类错误不可能写出来**：

```cpp
// The only way to bind a program. There is no direct g.UseProgram call site left.
void BindProgram(GLuint p, ProgramKind kind)
{
    gl().UseProgram(p);
    d.boundProgram = p;      // the cache and the driver are updated together, always
    d.boundKind = kind;
}
```

然后 `grep "UseProgram("` 的结果应该只剩一处（这个包装函数内部）。**这是一个可以用 CI 检查的性质**：如果 grep 命中数 > 1，构建失败。把“纪律”变成“编译期约束”，这是唯一可靠的做法。

### 6.3 调试层：三个开关，覆盖 90% 的问题

| 开关 | 做什么 | 什么时候开 |
|---|---|---|
| `GOW_GS_HW_ERRTRACE=1` | 每批次后逐调用 `GetError`，报出留下错误的调用名 | 随机花屏、`0x502`、驱动拒绝某状态 |
| `GOW_GS_STRICT=1` | 第 6.1 节的十条不变量变成 abort + 打印上下文（批次号、状态摘要） | 开发期常开；出问题时第一时间开 |
| `GOW_GS_TRACE_BATCH=N` | 只对第 N 个批次打印完整状态（约 60 个字段） | 定位“哪一批画错” |

`ERRTRACE` 有一个必须知道的副作用：它插入 `glGetError` 会强制同步，帧率会掉一半以上，而且会改变时序相关的 bug 的复现概率。**开着它测帧率是没有意义的**，只能用来定位正确性。

`STRICT` 的实现要便宜：

```cpp
#if defined(_DEBUG) || defined(GOW_GS_STRICT_BUILD)
  #define GS_ASSERT(cond, msg) do { if (!(cond)) gsFail(__FILE__, __LINE__, msg); } while (0)
#else
  #define GS_ASSERT(cond, msg) do { if (!(cond)) ++impl.invariantHits[__LINE__]; } while (0)
#endif
```

Release 版本里只加一个自增，成本可忽略；但它让 `[gs-hw] invariants: p1=0 p2=0 p3=0 ...` 这行日志有意义——哪条计数不为 0，就是哪条被违反了。

### 6.4 黄金帧回归：唯一能声称“没有回归”的手段

人眼看截图只能发现“明显炸了”，发现不了“阴影边缘偏了一个像素”“alpha test 边界少了一行”。要做“没有 bug”，必须有逐像素回归。

本工程已经有录制/回放能力：`PS2X_GS_RECORD` / `PS2X_GS_PLAY` 配合 `tools/gsdump_*`，以及与 PCSX2 单帧 GS dump 的对照 `【文档】`。把它变成流水线：

```
第 1 步（一次性，每场景一次）
  在参考机上跑目标场景，PS2X_GS_RECORD 录 300 帧
  → data/regress/<scene>/frame_0000.gsdump ...（不入库，放本机）

第 2 步（每次改动）
  PS2X_GS_PLAY 回放，每帧对显示缓冲算两个指纹：
    ① 全帧 24 位哈希（已有 FLICKERLOG 的探针哈希可复用）
    ② 每 64×64 块的平均色 + 最大差
  → 与基线比较

第 3 步（判定）
  同一台机器、同一驱动、同一档位：要求逐像素完全一致（哈希相等）
  跨驱动/跨档位：允许 ≤1 LSB 的差异，且 99.9% 像素在容差内，最大差 ≤2
  任何一帧超差 → 打印该帧号 + 超差块坐标 + 保存左右两张 PPM
```

为什么“同机同档必须完全一致”是一个合理要求？因为 v2 的所有改动都**不改变像素语义**（第 4.11 节最后一列全是“否”）。如果同机同档出现差异，那一定是 bug，不是“浮点误差”。

这套东西的价值在冲刺 5 体现：改纹理脏矩形时，人眼绝对看不出“某个 4×4 块少更新了一行”，但哈希会。

**成本**：300 帧回放约 20–40 s（比实时快，因为跳过了 EE/VU 的大部分工作）。每次改动跑一遍是可接受的。

### 6.5 失败降级链

失败不是异常，是常态：老机器的驱动会拒一切。所以设计一条明确的降级链，每一跳都留日志：

```
① 尝试 A 档（GL 4.3 + 全部可选函数）
   ├─ 上下文创建失败 → ②
   ├─ 着色器链接失败 → ②
   └─ 首帧后 ERRTRACE 有错 → ②（并把 A 档标记为“此机器不可用”，写进本地配置）
② 尝试 B 档（GL 4.3 或 3.3，无 UBO/无状态缓存/无持久映射）
   ├─ 上下文创建失败 → ③
   └─ 3 秒内 guest 帧数为 0 → ③
③ 尝试 C 档（GL 3.3 最简，无环、无 shuffle 合批、固定 0.5×）
   └─ 仍失败 → ④
④ 窗口显示可读文案 + 建议 `PS2X_GS_RENDERER=sw`
```

两条实现要求：

1. **降档必须发生在“用户看到黑屏之前”**，也就是启动 3 秒内判定。做法是：降档判据用“有没有成功 Present 过一帧”，而不是“帧率高不高”。
2. **降档结果要能持久化**（写进 `gow-native.boot` 同级的一个 `renderer-tier.txt`），否则用户每次启动都要再黑一次。这是体验问题，也是“看起来像 bug”的问题。

### 6.6 测试矩阵

不可能测所有组合，选能覆盖分叉的最小集：

| 维度 | 取值 | 理由 |
|---|---|---|
| 机器 | i3-4170 + HD 4400；一台 NVIDIA；一台 AMD | 三个厂商的状态机行为差异最大 |
| 档位 | A / B / C | 三档都要能起来 |
| 场景 | 标题（低负载）、开场过场（纹理流 + shuffle 重）、战斗（图元多）、菜单（CT16/CLUT 多） | 四个场景覆盖四种瓶颈 |
| 开关 | 默认；`STRICT=1`；`RING=0`；`TIER=A/B/C` | 每个开关至少跑一次启动 + 30 秒 |
| 失败注入 | `GOW_GS_FAIL_TEST=context` / `shaders` | 验证降级链与文案 |

**最小可接受集**：3 台机器 × 4 个场景 × 默认档 = 12 次运行，每次 45 秒。加上 4 个开关的冒烟（每次 30 秒），一共约 15 分钟机器时间。这个成本必须付，否则“改了没炸”只是运气。

### 6.7 代码评审清单（贴进 PR 模板）

```
[ ] 每一个 UseProgram 都走 BindProgram 包装（grep 只有 1 处命中）
[ ] 新增的跨批次引用是 id 不是指针
[ ] 新增的 GL 对象在 Reset()/Destroy() 里有对应释放
[ ] 新增的环境变量有 clamp，非法值有日志，有回退路径
[ ] 新增的路径有一个能关掉它的开关
[ ] 批次统计（GOW_GS_HW_STATS）里能看到这条路径的次数
[ ] 同机同档的黄金帧哈希未变
[ ] 补丁头写了 what / why / 实测数字
```

最后一条是本工程的硬规矩：**没有实测数字的补丁不进主干。** 因为下一个接手的人无法判断它是否值得保留，而“无法判断”最终等于“不敢删也不敢改”。

### 6.8 一个 bug 复盘模板（照这个写）

```markdown
## 症状
（一句话，玩家视角：进 3D 场景全黑，菜单正常）

## 判据
（能把它和别的 bug 分开的证据：标题 shuffles=0 正常，场景 shuffles 每 5s 上千；
  fbp=0 的图 unique=1 纯色）

## 根因
（两个真相：缓存说 A，驱动是 B；引用 file:line）

## 修复
（一行改动 + 为什么这一行就够）

## 为什么之前没发现
（测试盲区：只测了标题；或者 dump 只看了异常帧没看正常帧）

## 如何防止复发
（不变量编号 + 新增的断言/日志）
```

这份模板的价值在最后两栏。本工程的三个黑屏/花屏 bug 有同一个“为什么没发现”：**只看了异常画面，没有对比正常画面**。对比是破局的关键——标题 `shuffles=0` 这一条信息，比看十张黑屏截图都有用。

### 6.9 一次完整复盘：3D 场景全黑，标题正常

这一节把第 6.1–6.3 节的方法用在真实案例上，展示“从症状到一行修复”的完整推理链。选它是因为它几乎是本工程所有渲染 bug 的原型：**两个真相不一致，且只在特定路径上暴露**。

**症状。** 启动正常，标题画面、Logo、菜单全部正确；选“新游戏”进入 3D 场景后，画面全黑，但音频正常、手柄有反馈、帧率显示 60。切回菜单又正常。

**第一反应通常是错的。** 大多数人会想“场景的着色器写错了”“深度测试把东西都裁掉了”“摄像机矩阵不对”。这三个方向都会让你花掉半天，而且全部无效。正确的第一步是**分清楚这是“没画”还是“画黑了”**。

**第 1 步：确认呈现是否在走。**
开 `GOW_OSD=1`，角上出现 `<rate> Hz <w>x<h>` 并且在变。说明 present 路径在工作、guest 在出帧、窗口在刷新。于是排除“呈现线程卡住”“guest 不出帧”这两个大类。

**第 2 步：确认显示缓冲里有没有内容。**
开 `GOW_GS_HW_DISPDUMP=<n>`，把第 n 帧的显示缓冲 dump 成 PPM。结果显示**全黑**（不是“有内容但没显示”）。于是排除“上屏路径选错了 DISPFB”“共享纹理没发布”这一类。

到这里可以确定：**内容是黑的，不是没送上去。** 这把问题收敛到了“绘制阶段”。

**第 3 步：对比正常画面与异常画面，而不是只看异常画面。**
这是整个诊断的转折点。开 `GOW_GS_HW_STATS=1` 看两个场景的统计：

| 场景 | `shuffles` /5s | `draws` /5s | `batches` /5s |
|---|---|---|---|
| 标题（正常） | **0** | 3.4 M | 20 000 |
| 3D 场景（全黑） | **1600–3800** | 3.6 M | 19 500 |

**绘制数量没有减少，批次也没有减少，唯一的结构性差异是 `shuffles` 从 0 变成几千。** 这一条信息价值极高：它说明“东西在画，只是画到了错的地方/用了错的着色器”，而不是“东西没画”。

如果只看黑屏截图，你会永远卡在“为什么黑”；只有对比“正常 vs 异常”的统计差异，才能看到 `shuffles` 这个唯一的变量。

**第 4 步：验证“整帧用错着色器”这个假设。**
开 `GOW_GS_HW_ERRTRACE=1`（会掉帧，但这时候不关心帧率）。日志在第一批场景绘制之后报 `GL_INVALID_OPERATION (0x502)`，指向一次 `glUniform*` 调用。

`0x502` 的含义是“当前 program 不是有效的绘制程序”。但代码明明在 `drawOne` 里 `UseProgram(drawProgram)` 了。这说明**代码认为绑着 drawProgram，实际绑的是别的**——也就是 `boundProgram` 这个“第二真相”与驱动不一致。

**第 5 步：找泄漏点。**
`drawOne` 里有一个 `flushShuffle()` 调用，位置在“状态去重检查之后、`UseProgram` 之前”。而 `flushShuffle()` 内部会 `UseProgram(shuffleProgram)`，画完**没有把 `boundProgram` 改回来**。

于是时序是：

```
第 1 批：检查 boundProgram == drawProgram ✓ → flushShuffle 绑了 shuffleProgram
         → 但 boundProgram 仍然写着 drawProgram
         → 这一批实际用 shuffleProgram 画（用错着色器）
第 2 批：检查 boundProgram == drawProgram ✓（谎言）→ 跳过 UseProgram
         → 继续用 shuffleProgram 画
... 整帧都是错的
```

而标题场景 `shuffles=0`，`flushShuffle()` 直接返回、不绑 program，所以完全正常。这解释了“为什么只有场景黑”——**bug 只在有 shuffle 的路径上存在**。

**第 6 步：一行修复。**

```cpp
void flushShuffle()
{
    if (shuffleQuads[0].empty() && shuffleQuads[1].empty()) return;
    // ... bind FBO, UseProgram(shuffleProgram), draw ...
    boundProgram = shuffleProgram;   // ← 这一行
}
```

**第 7 步：防止复发。**
不是“下次小心点”，而是：
1. 加不变量 #1（任何 `UseProgram` 后 `boundProgram` 必须同步）；
2. 把所有 `UseProgram` 收进 `BindProgram()` 包装，让 grep 只剩一处；
3. 在 PR 模板里加一条“新增的 program 绑定是否走包装”。

**这次复盘能提炼出四条通用规则：**

| 规则 | 为什么 |
|---|---|
| 先分“没画”还是“画错”，再查渲染器 | 前者查链路，后者查状态，方向完全相反 |
| 必须对比正常帧与异常帧 | 只有差异才是线索；黑屏本身不含信息 |
| 统计量的结构差异比画面差异更可靠 | 画面是结果，统计是原因 |
| 修复必须伴随“让这类错误写不出来”的改动 | 否则同一个 bug 会以另一种形式回来 |

第四条是本文反复强调“把纪律变成结构”的原因。人性的自律在三千行渲染代码面前不成立，只有包装函数、断言、grep 检查、黄金帧这四样东西成立。

### 6.10 三线程并发：数据归属表

渲染器的正确性有一半不在 GL 里，在线程边界上。本工程实际有四个执行体：

| 执行体 | 职责 | 拥有什么 | 绝对不能做什么 |
|---|---|---|---|
| EE（GameThread） | 重编译后的游戏代码，写 GS 寄存器 | 寄存器快照、`GSPrimitiveBatch` 的构造 | 不能直接调 GL（没有上下文/不在正确线程） |
| VU1 worker | x64 JIT 执行微程序，产出几何 | VU1 状态、XGKICK 的输出 | 不能碰 GS 后端 |
| GS worker | `GSThreadedBackend::Execute`，出队并调 `GSHwBackend` | GL 上下文（worker 版）、`Impl` 全部状态 | 不能读 EE 正在写的结构（必须靠队列拷贝） |
| host present | 把共享纹理 blit 到窗口 | 窗口上下文、共享槽 | 不能碰 `Impl` |

**跨线程只允许值拷贝，不允许指针。** 这条规则在代码里已经成立：`Enqueue(op, payload, size)` 把 payload 拷进 64 KB chunk（顶点部分只拷 `offsetof(GSPrimitiveBatch, state)` 之前的字节，约 145 B/图元）`【文档】`。v2 不能破坏这个性质。

**共享对象与上下文。** `GSGL::Context::CreateWorker()` 创建的是**共享上下文**（share context）。这意味着：

| 对象类型 | 能否跨上下文共享 | 后果 |
|---|---|---|
| 纹理、Buffer | 能 | 可以共享，但同步要自己做 |
| Program / Shader | 能 | 编译一次，处处可用 |
| FBO | 能（作为对象），但绑定状态是 per-context | 每个上下文各自 bind |
| VAO | **不能**真正共享 | 每个上下文要有自己的 VAO（或每次重设） |
| 当前绑定状态 | 不共享 | 别指望“另一个上下文绑好了” |

最后一个是最容易踩的：**“共享上下文”共享的是对象，不是状态。** 如果 worker 里新建了一个 VAO 却在 host 上下文里用，行为是未定义的。

**队列的背压语义。** 队列最多 256 个 pending chunk（约 4 MB），满了 `PublishLocked` 会让生产者等待 `【文档】`。这条设计带来两个可观测现象：

1. `gs_ms` 里包含“等 worker 消费”的时间 —— 所以 `gs_ms` 高不一定是渲染慢，可能是队列满。
2. 一旦 EE 被背压卡住，`ee_ms` 会下降而 `gs_ms` 上升。**看到“EE 变闲、GS 变忙”这个组合，先怀疑背压，不要怀疑 EE 优化生效了。**

**一个必须文档化的危险点：`Op::Call`。** 队列里可以塞一个函数指针，在 GS worker 上执行 `【文档】`。它很有用（把任意“在渲染线程做的事”排进顺序），但它把**函数与捕获数据的生命周期**交给了调用方 —— 调用方必须保证“函数可执行、捕获的对象活到执行完”。这是一个典型的“用起来很方便、出错时极难查”的机制。v2 的建议：

```cpp
// If you must queue a callable, queue its *arguments* by value and keep the function stateless.
// A lambda that captures a pointer to a stack object is a use-after-free with a delay.
EnqueueCall([](void *ctx) { static_cast<Presenter *>(ctx)->Flush(); }, presenterPtr);
//                                      ^ presenter 必须活得比这个 Op 更久
```

**内存序。** chunk 的发布必须满足“先写数据，再发布索引”，否则 worker 可能看到半个 payload。正确写法是 release/acquire 配对（或一把 mutex 保护发布）。这类 bug 的症状是“偶发的状态错乱”，而偶发 bug 在渲染器里最难查 —— 因为它看起来像“随机的花屏”。第 6.1 节的不变量 #2/#3 能抓住一部分（帧末 pending 非空），但抓不住“内容错了但结构对”。

**给实现者的四条规矩：**

1. 跨线程传递的东西，一律值拷贝 + 序列号；不用裸指针（反模式 #11）。
2. GL 调用只在拥有上下文的那个线程里发生；需要“在渲染线程做点什么”，走队列。
3. 不假设“共享上下文 = 共享状态”；VAO、绑定、视口都要各自设置。
4. 看到 “EE 变闲 + GS 变忙”，先查背压，别急着庆祝。

---

## 7. 帧率工程：从 41 到 60 的账

### 7.1 先把每帧预算摊开

60 fps 意味着一帧 16.67 ms。但这是**整条流水线**的预算，不是渲染器的。把已有实测摊成每帧（5 秒窗口 = 300 帧，标题场景，快模式）`【实测】`：

| 线程/阶段 | 5 s 累计 | 每帧 | 占 16.67 ms 的比例 | 读法 |
|---|---|---|---|---|
| EE（GameThread） | 2000–2120 ms | 6.7–7.1 ms | 40–42% | 还有余量 |
| VU1 worker | 4000–4130 ms | **13.3–13.8 ms** | **80–83%** | **最紧的一环** |
| GS（前端 + 后端） | 1925–2177 ms | 6.4–7.3 ms | 38–44% | 其中绘制提交约 1.8 ms |
| IOP | 360–390 ms | 1.2–1.3 ms | 7% | 不是问题 |
| host present | 受 `host_wait` 限速 | — | — | 贴顶时 `host_wait` 接近满值，**不代表 CPU 空闲** |

**这一张表就否定了“优化渲染器就能到 60”的幻想**：即使 GS 归零，VU1 的 13.5 ms 也只剩 3 ms 余量，任何抖动都会掉帧。实测量化得很清楚：`PS2X_GS_DISCARD_DRAWS=1` 时标题 59.9 fps —— 刚好贴顶，没有余量。

再看低配档（41 fps，约 205 帧/5 s）。按 `low-spec-renderer.patch` 的记载，此时 GS 占窗口 34%、VU1 占 68%：

| 阶段 | 5 s 累计（推算） | 每帧 | 说明 |
|---|---|---|---|
| VU1 | ≈ 3400 ms | ≈ 16.6 ms | 已经等于一整帧的预算 |
| GS | ≈ 1700 ms | ≈ 8.3 ms | 其中一半是固定的前端成本 |
| 实测帧时间 | — | **24.4 ms** | 41 fps |

关键观察：**24.4 ≈ 16.6 + 7.8。** 也就是说 VU1 与 GS 并没有真正并行，而是**大部分串行**（VU1 产出几何 → 入队 → 等 GS 消费）。这不是理论，是数字对上的结果 `【推断，由两个百分比反推，未做逐帧 trace】`。

由此得到两个可检验的预测：

- 把 GS 从 8.3 ms 压到 4.2 ms（减半）⇒ 帧时间 20.2 ms ⇒ **49.5 fps**。
- 把 GS 压到 0 ⇒ 帧时间 16.6 ms ⇒ **60 fps**（刚好，无余量）。

**所以渲染器优化的现实上限是 49–60，实际落在 47–52 是合理预期；要到 60 还必须同时砍 VU1 的 25%。** 谁承诺“只改渲染器就 60”，谁就是在骗人。

### 7.2 什么时候不该改渲染器

这是本章最重要的一节，因为它能省掉你两周的无效劳动。三个判据：

| 判据 | 阈值 | 结论 |
|---|---|---|
| `PS2X_GS_DISCARD_DRAWS=1` 的 guest fps | 仍远低于目标（例如 30–43） | **渲染器不是瓶颈**，改 VU1/EE |
| `vu_ms / frames` | ≥ 帧时间的 70% | VU1 是墙 |
| `gs_ms / frames` | ≥ 帧时间的 50% 且 `vu` 有余量 | 渲染器是墙 |

`【实测】` 开场过场：丢弃绘制后 30–43 fps，正常 16–27 fps。结论是“渲染器占了一半，但即使它归零也到不了 60”。这种场景的正确策略是**先保证不卡顿（p95），不追求 60**。

### 7.3 ROI 排序：先做哪一刀

按“预期收益 ÷ （工作量 × 风险）”排序。第 1–4 项是本文推荐的顺序。

| # | 改动 | 预期收益 | 工作量 | 风险 | 依据 |
|---|---|---|---|---|---|
| 1 | 分辨率阶梯 + 窗口贴合 | 1.0×→0.5× 实测 24.3→40.4 fps；呈现 20.6→32.7 Hz | 1 天 | 低 | `【实测】` 两组数字都在仓库里 |
| 2 | 呈现只画新帧 + 整数贴合 + 去掉全屏后处理 | 1–3 fps，纯收益 | 半天 | 极低 | 全屏 pass 在 iGPU 上每次约 1/3 呈现率 |
| 3 | 顶点环 32→48 MB（把每帧回绕从 1.2 次降到 0） | 0.5–1.5 fps | 1 小时 | 极低 | 每次回绕 1–3 ms 的 fence `【实测】` |
| 4 | 前端 range 提交 | 重过场 +2–4 fps；抬地板 1.3–1.5 s/5s | 3–4 天 | 中 | 丢弃绘制仍 1.3–1.5 s/5s `【实测】` |
| 5 | 纹理脏矩形 | 重过场 +1–3 fps（`upload_ms` 777→约 300） | 4–5 天 | 中高 | `texDecodes` 3017/5s 说明放大严重 |
| 6 | shuffle 保守合批 | +1–2 fps（取决于 `shuffles/shuffleDraws`） | 2–3 天 | 中 | 22176 shuffles/5s `【实测】` |
| 7 | 跳过全透明批次 | 0–2 fps（过绘制高的场景才有） | 2 小时 | 低 | 需要先统计“全 alpha=0 的批次占比” |
| 8 | 删掉每批次里未使用的 uniform | 1–2% | 半天 | 低 | 约 35 个里有一批只在特定分支用 |
| 9 | 顶点压缩 64 B → 32 B | 未知（老 iGPU 顶点带宽可能不是瓶颈） | 3 天 | 中 | 需要实测，先做 A/B 再决定 |
| 10 | UBO / 状态缓存 | **负收益** | 已做过 | — | 见 7.4 |

**注意第 1 项的收益量级。** 它比第 3–8 项加起来还大，而工作量最小。这不是说后面的不值得做，而是说：**如果你只有一天，做第 1 项；如果有两周，按顺序做 1→2→3→4。**

### 7.4 已证伪清单（不要再走）

| 方向 | 实测结果 | 原因 | 适用边界 |
|---|---|---|---|
| 每批次 std140 UBO | 53–55 → 50.7 fps，`gs_ms` 2.0→2.26 s | Intel 上 `BufferSubData + BindBufferRange` 比 35 次 `glUniform` 更贵 | 换 NVIDIA/AMD 可重测 |
| GL 状态去重缓存 | 53–55 → 37–40 fps，`gs_ms` 翻倍 | 驱动对“陈旧状态”走慢路径重建；冗余 setter 是廉价 fast path | 同上 |
| 调色板图集（跨 CLUT 合批） | 批次 19.3k vs 19.1k，几乎不降 | 批次由 TEST/PRIM/TEX0 的真实变化决定，不是 CLUT | 一般 |
| canonical 状态比较（忽略无用字段） | 批次几乎不降，`gs_ms` 2.0→2.06 | 差异大多是真实状态变化；比较分支更多 | 只在“大量只差无效字段”的场景有效 |
| TEXFLUSH 视作 no-op | 批次不变，帧率无变化 | 大多发生在 pending 为空时 | 一般 |
| `TexSubImage2D` 复用存储 | 场景不可比，标题无净收益 | 无法构造确定性纹理流场景 | 可用脏矩形重做（第 5.5 节） |
| GS worker 提优先级 | 50.2–52.7 vs 52.5–53.0，无差别 | 不是线程争用 | 一般 |

这张表的价值在于：**它把“看起来显然该做的事”标成了“已花过时间、已验证无效”**，后来的人不必再用两周去证明一次。

### 7.5 三个还没试过、值得试的方向

**方向 1：顶点压缩（64 B → 32 B）**

现在 `HwVertex` 是 16 个 float。可以压成：

```
位置 x,y         → 2 × float（必须保留精度，GS 顶点是 1/16 像素定点）
Z                → 1 × float（或 24 位归一化到 u32）
颜色             → 4 × u8 归一化（GS 顶点色本来就是 8 位！现在却存成 4 个 float）
STQ              → 3 × float（Q 必须保留，除法在 shader 里做）
UV               → 2 × u16 归一化（纹理坐标上限由 maxTextureSize 决定）
UVClamp          → 2 × u16 × 2（可选的 clamp 范围）
```

颜色从 4 float 变 4 u8 是**无损**的（GS 顶点色就是 0–255），这一项就从 16 B 降到 4 B。UV 从 2 float 变 2 u16 会损失精度（1/65536 的纹理坐标分辨率），需要验证“精灵接缝”逻辑（`openSharedSide`，`gs_hw_backend.cpp:634`）是否还成立——它对 UV 用了 `1/32` 的容差，u16 精度远够。

预期：每帧顶点带宽 19–26 MB → 10–13 MB，CPU memcpy 减半，环可以装 2–3 帧。收益取决于“顶点读取是否瓶颈”，所以要**先加一个 GPU 时间戳探针测顶点阶段的耗时**，再决定。

**方向 2：按 scissor 收紧视口**

现在每批次设一次 scissor，但 viewport 是整张 RT。老 iGPU 上，如果 draw 的覆盖面积远小于 RT，光栅化器仍要为整个 viewport 做 tile 遍历的准备工作。把 viewport 收紧到 scissor 与顶点包围盒的交集，可以让部分驱动跳过空 tile。

风险：viewport 影响 `gl_FragCoord` 与裁剪，任何在 shader 里用 `gl_FragCoord` 的地方（现在的 `uPxScale`）都会受影响。必须逐 shader 检查。

**方向 3：过绘制削减——只在“深度写 + 不混合”的批次上启用反向 Z**

GS 的 Z 是 0 近 1 远（和 GL 默认一致），所以现在是 `GL_LESS`。如果改反向 Z（`GL_GREATER` + 清 0），深度精度在老 iGPU 的 24 位深度上更好，且 early-Z 命中率更高。但这会影响 Z 别名的位重解释与 `zMaxFor` 归一化，改动面很大（第 6.1 节第 7、8 条不变量都会被触碰）。

**结论：列为“研究项”，不进 v2 主线。** 它的正确性风险与收益完全不成比例。

### 7.6 卡顿比平均帧率更重要

玩家感知的不是平均 fps，是 p95/p99。`GOW_PERF_DIAG=frames` 会打印 `[gow-frame]` 的 p50/p95/p99/max 与 `over_16_67/33/50/100` 计数 `【文档】`。

验收标准建议：

| 场景 | p50 | p95 | max | 说明 |
|---|---|---|---|---|
| 标题 | ≤ 16.7 ms | ≤ 20 ms | ≤ 40 ms | 基本贴顶 |
| 战斗 | ≤ 18 ms | ≤ 25 ms | ≤ 60 ms | 允许偶发 |
| 重过场 | ≤ 22 ms | ≤ 33 ms | ≤ 100 ms | 过场允许慢，但不能卡死 |

**任何“平均 58 fps 但 p95 33 ms”的结果都不算通过。** 因为玩家会在每次 33 ms 的帧上感到一下顿挫，而平均值把它藏起来了。

三个常见的卡顿来源，按出现频率排：

1. **分辨率阶梯切换**（重建 RT，几十毫秒）→ 用冷却 + 锁定压制（第 5.7 节）。
2. **纹理整张重解码**（`upload_ms` 尖峰到 777 ms/5s）→ 脏矩形 + 安全阀。
3. **着色器首次编译**（首次进入某路径）→ 预编译 4 个变体（第 5.4 节）。

### 7.7 逐场景手册：四张表，四种打法

同一台机器，不同场景的瓶颈完全不同。**用一个“平均 fps”去优化，等于同时朝四个方向开枪。** 下面四张表是拿到场景后 5 分钟内该做的判断。

#### 场景 1：标题 / 演算前段（低负载，高帧率）

| 项 | 内容 |
|---|---|
| 典型数字 | guest 59.6–60.1，`gs_ms` 1925–2177/5s，`vu_ms` 4000–4130/5s，约 380–420 批次/帧，1.4 万图元/帧 |
| 判据 | 已经贴顶。`host_wait` 接近满值，`guest_wait` 也高 —— **这两个大不代表有余量，恰恰说明贴顶** |
| 该做什么 | 只做“防止退化”的事：黄金帧回归、`ringWraps` 监控；不要在这里做优化实验（收益被 60 上限吃掉，测不出来） |
| 不该做什么 | 不要用标题画面判断“优化有没有效”。它已经饱和，任何优化都看不出差别 —— 这是本工程最容易自欺的地方 |
| 验收 | guest ≥ 59，p95 ≤ 20 ms |

#### 场景 2：开场过场（重纹理流 + 重 VU1）

| 项 | 内容 |
|---|---|
| 典型数字 | `【实测】` guest 16–27，`gs_ms` 1720–2845/5s，`vu_ms` 4350–4630/5s，`upload_ms` 256–533/5s |
| 判据 | `PS2X_GS_DISCARD_DRAWS=1` 时 30–43 fps ⇒ **即使渲染器归零也到不了 60**，VU1 是主墙 |
| 该做什么 | ① 纹理脏矩形（Sprint 4）把 `upload_ms` 压到 400 以下；② 保证 p95 ≤ 33 ms，不要追求平均帧率；③ 记录它作为“不退化”的基线 |
| 不该做什么 | 不要在这里调分辨率阶梯 —— 过场帧率本来就波动，阶梯会跟着抽搐。控制器必须能识别“这是过场”，或者干脆在过场里锁定档位 |
| 验收 | guest ≥ 22，p95 ≤ 33 ms，`upload_ms` ≤ 400 |

#### 场景 3：战斗（图元多，状态变化密）

| 项 | 内容 |
|---|---|
| 典型数字 | `【推断，由重演算 demo 外推】` 批次 500–700/帧，图元 1.6–2 万/帧，`shuffles` 中等 |
| 判据 | `unsupportedBlend` 高 ⇒ shader 软件混合在拖后腿；`batches` 高且 `shuffles` 低 ⇒ 纯提交成本 |
| 该做什么 | ① 前端 range 提交（Sprint 3）；② 检查 `unsupportedBlend` 的比例，如果 > 15%，说明有一类混合模式没进快路径，值得单独看；③ 全透明批次跳过 |
| 不该做什么 | 不要指望“合并状态”降批次 —— 战斗的状态变化是游戏真实的渲染需求，合并等于改变画面 |
| 验收 | p50 ≤ 18 ms，p95 ≤ 25 ms |

#### 场景 4：菜单（CT16 + CLUT 密集）

| 项 | 内容 |
|---|---|
| 典型数字 | 批次少（100–200/帧），但 CLUT 变化频繁，`texDecodes` 可能不低 |
| 判据 | `texDecodes` 高而 `shuffles` 低 ⇒ 调色板/索引纹理路径是热点 |
| 该做什么 | ① 确认 `paletteFor` 的缓存命中率（CLUT 变化不该导致索引纹理重解码，这是设计意图）；② 黄金帧重点看这里 —— CLUT 错了颜色会整体偏，肉眼容易忽略 |
| 不该做什么 | 不要做调色板图集（已证伪：批次由 TEST/PRIM/TEX0 决定，不是 CLUT） |
| 验收 | 画面与参考一致（逐像素），帧率不作为指标 |

**四张表的共同点**：每一张都先给“判据”，再给“动作”。没有判据的优化建议都是猜。这也是为什么第 6 章要不变量、第 7.1 节要分桶 —— 没有观测就没有判据，没有判据就没有优化，只有改动的快感。

### 7.8 GPU 侧计时：把“CPU 提交慢”和“GPU 执行慢”分开

`gs_ms` 是**线程忙时**，它同时包含：CPU 构建状态、CPU 调 GL、驱动内部校验、以及“队列满时等 GPU”的时间。这四件事混在一个数字里，所以你没法从 `gs_ms` 判断“该优化 CPU 还是 GPU”。

`GOW_GS_COST=1` 用 `rdtsc` 分段，解决的是 CPU 侧（`pre/uni/tex/vert/draw/post`）。GPU 侧要用 `GL_TIMESTAMP` 查询。本工程已经有这套设施：`gs_gpu_profile.h` 的 `Queue`，4 帧一个窗口、最多 3 个等待窗口、`kMaxSamplesPerWindow = 4096` `【文档】`。

**五个必须知道的坑：**

| 坑 | 现象 | 正确做法 |
|---|---|---|
| 同步取结果 | 一加计时帧率就掉一半 | 只查 `GL_QUERY_RESULT_AVAILABLE`，不可用就下一轮再取 |
| 每批次都插 query | 计时开销超过被测对象 | 每帧 1–2 个，或只对“选中的批次区间”插 |
| 结果延迟 | 拿到的永远是 4 帧前的数据 | 用于统计，不用于实时控制（不能喂给分辨率阶梯） |
| 跨上下文混用 | 时间差为负或跳变 | 只比较同一上下文内的 timestamp |
| 时钟不单调（部分驱动） | 偶发负值 | 丢弃负值样本，只累计正值 |

**它能回答的三个问题：**

1. **GPU 到底闲不闲？** 如果每帧 GPU 时间 3 ms、帧时间 16.7 ms，那 GPU 有 80% 空闲 —— 优化 shader 毫无意义，该优化提交。
2. **批次成本是 CPU 还是 GPU？** 对比 `oneTicks/ones`（CPU）与每批次 GPU 时间。CPU 高 GPU 低 ⇒ 提交瓶颈（本文的主战场）；两者都高 ⇒ 真的在光栅化。
3. **present 花了多少？** 把 timestamp 插在 present blit 前后，能验证“1280×720 呈现掉 37%”这个观测的成因。

**一个反面用法**：不要用 GPU 时间来驱动分辨率阶梯。原因见上表第三行 —— 你拿到的是 4 帧前的数据，而阶梯需要“现在”的负载。用 `guest_flip_hz`（每秒统计一次）就够，它天然平滑。

---

## 8. 落地路线：六个冲刺

每个冲刺都是一次独立可交付、可回退、可验收的改动。**不要合并冲刺**，否则出问题时无法定位。

### Sprint 0（2 天）：看得见

| 项 | 内容 |
|---|---|
| 目标 | 让“现在跑的是哪条路径、时间花在哪”变成一行日志 |
| 改动 | `gs_gl.h/.cpp` 加 `DeviceCaps` + `ProbeCaps`；`Impl` 加 `invariantHits[16]` 计数；`GOW_GS_HW_STATS` 行加 `ringWraps` / `oversizedBatches` / `invariants` |
| 验收 | 启动日志出现 `caps:` 与 `policy:` 两行；`GOW_GS_STRICT=1` 下跑标题 30 s 不 abort |
| 开关 | 无（纯增量，不改行为） |
| 补丁 | `67-gs-caps-and-invariants.patch` |

同时把黄金帧工具跑通（第 6.4 节），录好 4 个场景各 300 帧。**这一步不能省**，它是后面所有“没回归”声明的前提。

### Sprint 1（3 天）：把画质换成帧率，且换得聪明

| 项 | 内容 |
|---|---|
| 目标 | 工作点自动停在两墙的交叉点；窗口不再倒贴帧率 |
| 改动 | `WorkPointLadder`（第 5.7 节）；`PS2X_GS_HW_SCALE=auto` 走阶梯；未设 `GOW_WINDOW` 时窗口按内部高度 16:9 贴合；present 只画新帧 |
| 验收 | 标题场景：1× 起始 → 5 s 内自动落到 0.55×/0.70×，guest ≥ 40；呈现 Hz 提升 ≥ 8（对照 20.6→32.7 那组）；画质无肉眼变化 |
| 开关 | `PS2X_GS_HW_SCALE=0.5` 关闭阶梯；`GOW_WINDOW=WxH` 覆盖窗口 |
| 补丁 | `68-gs-workpoint-ladder.patch` |

### Sprint 2（3 天）：三档与降级链

| 项 | 内容 |
|---|---|
| 目标 | 任何一台机器都不黑屏；每台机器都跑在它能跑的档上 |
| 改动 | `DriverProfile`（第 5.2 节）；`GOW_GS_TIER`；`RendererFailure::TierUnavailable`；3 秒内无成功 Present 就降档；降档结果持久化 |
| 验收 | `GOW_GS_FAIL_TEST=context` / `shaders` 各自能显示可读文案并尝试降档；C 档在 GL 3.3 上下文下能出画面（可用 Mesa 或强制 4.3→3.3 测试） |
| 开关 | `GOW_GS_TIER=A\|B\|C` |
| 补丁 | `69-gs-tier-and-degrade.patch` |

### Sprint 3（4 天）：抬地板

| 项 | 内容 |
|---|---|
| 目标 | 减少每图元的固定成本，而不是每批次的调用数 |
| 改动 | `gs_frontend` 聚“连续 + 状态等价”的图元成 Range；`Op::Range` 一次入队；三个强制 flush 点（传输/CLUT/FINISH/PRESENT）；`GSNullBackend` 与 `GSThreadedBackend` 同步支持 |
| 验收 | `PS2X_GS_DISCARD_DRAWS=1` 的 `gs_ms` 从 1.3–1.5 s/5s 降到 ≤ 1.0 s/5s；重过场 guest +2–4；黄金帧哈希不变 |
| 开关 | `GOW_GS_RANGE=0` 回到逐图元 |
| 补丁 | `70-gs-frontend-ranges.patch` |

**这是全文风险最高的一个冲刺**：它动接口，动三个后端，动队列。所以它单独一个补丁、单独一周、单独验收。如果 Sprint 3 失败，前三个冲刺的收益仍然成立。

### Sprint 4（5 天）：纹理流

| 项 | 内容 |
|---|---|
| 目标 | 把“整张重解码”变成“只补改动的块” |
| 改动 | `UploadRecord` 加矩形；`DirtyRectFor` + 60% 安全阀（第 5.5 节）；`TexSubImage2D` 路径；只对直接色与索引色生效 |
| 验收 | 重过场 `upload_ms` 从 777 降到 ≤ 400（/5s）；`texDecodes` 次数不增；黄金帧在 4 个场景全部一致（尤其看重过场与菜单） |
| 开关 | `GOW_GS_DIRTYRECT=0` 回到整张 |
| 补丁 | `71-gs-texture-dirty-rect.patch` |

### Sprint 5（4 天）：收尾与实验

| 项 | 内容 |
|---|---|
| 目标 | 把剩下的小刀子切完，把风险项标清楚 |
| 改动 | 顶点环 32→48 MB + `oversizedBatches` 专供路径（第 5.3 节）；shuffle 保守合批（第 5.6 节）；全透明批次跳过；删未使用 uniform |
| 验收 | `ringWraps` 每帧 ≤ 0.2；`shuffles/shuffleDraws` ≥ 8 时才合批并给出数字；黄金帧不变 |
| 开关 | `GOW_GS_HW_RING=0`、`GOW_GS_SHUFFLE_MERGE=0`、`GOW_GS_SKIP_EMPTY=0` |
| 补丁 | `72-gs-vertex-ring-48m.patch`、`73-gs-shuffle-merge.patch` |

顶点压缩（第 7.5 节方向 1）**不在 v2 主线**，单开一个研究分支，先测“顶点阶段 GPU 时间占比”再决定。

### 排期总览

| 周 | 冲刺 | 累计交付 |
|---|---|---|
| 1 | S0 + S1 | 可观测 + 工作点；帧率第一桶金 |
| 2 | S2 + S3 前半 | 三档 + 降级链；range 接口 |
| 3 | S3 后半 + S4 前半 | 抬地板完成；脏矩形开工 |
| 4 | S4 后半 + S5 | 纹理流 + 收尾 |

四周是紧凑但现实的排期，前提是**每台机器都已就绪、构建能在 2 分钟内增量完成**。如果构建要 20 分钟，所有排期乘 1.5。

---

## 9. 交付物与验收

### 9.1 交付物清单

| 类型 | 文件 | 说明 |
|---|---|---|
| 补丁 | `engine/patches/67..73-*.patch` | 一个冲刺一个，头注释含 what/why/实测 |
| 代码 | `gs_gl.h/.cpp`、`gpu/gs_hw_backend.cpp`、`gpu/gs_texture_store.*`、`gs_frontend.cpp`、`gs_threaded_backend.cpp`、`gs_host_present.cpp` | 按冲刺分 |
| 文档 | 本文 | 设计依据与证伪记录 |
| 文档 | `docs/tested-hardware.md` 新增一节 | 三台机器 × 四个场景的实测表 |
| 工具 | `tools/profile/bench-render.ps1` | 把 `data/_tmp` 里的临时基准脚本正式化 |
| 工具 | `tools/regress/golden-frame.py` | 录制/回放/哈希比对 |
| 开关表 | `docs/diagnostics.md` 增补 | 新增的 `GOW_GS_TIER` 等 |

### 9.2 验收数字

**必须三个场景分别报，不许合并成一个“平均 fps”。**

| 场景 | 指标 | 改前 | 目标 | 判据 |
|---|---|---|---|---|
| 标题（0.5×，快模式） | guest fps | 59.6–60.1 | ≥ 59 | 已是天花板，只验“没退” |
| 标题（1.0×，阶梯自动） | guest fps | 24.3 | ≥ 38 | 阶梯必须自己找到工作点 |
| 呈现速率（412×360 → 640×360） | Hz | 32.7 | ≥ 40 | 窗口贴合 + 只画新帧 |
| 开场过场 | guest fps | 16–27 | ≥ 22 | 只求不恶化，且 p95 ≤ 33 ms |
| 重演算 demo | guest fps | 33–41 | ≥ 38 | 脏矩形 + shuffle 合批 |
| 重演算 demo | `upload_ms` /5s | 777 | ≤ 400 | 脏矩形 |
| 任意场景 | 黄金帧哈希 | 基线 | 完全一致 | 同机同档 |
| 任意场景 | GL 错误 | 0 | 0 | `ERRTRACE` 抽测 |

**“≤/≥”都带测量条件**（机台、分辨率、窗口、场景、窗口长度）。没有这些条件的数字，在验收会上不算数——这是本工程 `【实测】` 标签的意义。

### 9.3 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 另一台机器（AMD/NVIDIA）上 B 档更慢 | 中 | 中 | 驱动画像按 vendor 分叉；出问题可 `GOW_GS_TIER=A` |
| Sprint 3（range 提交）引入顺序 bug | 中 | 高 | 单独补丁 + 黄金帧 + `GOW_GS_RANGE=0` |
| 脏矩形在“整张频繁改”时更慢 | 中 | 中 | 60% 安全阀 + `GOW_GS_DIRTYRECT=0` |
| 阶梯切换引起卡顿感 | 中 | 低 | 冷却 + 锁定 + 切换日志 |
| 玩家机器上 4.3 上下文拿不到 | 低 | 高 | C 档 + `sw` 兜底 + 可读文案 |
| 补丁链已有缺口导致无法重建 | 高 | 中 | 已知问题：`engine/patches` 缺 49 等历史补丁，01–58 不能完整复现工作区。**先修这个，或在 README 明确标注“工作区 = 链 + 手工状态”** |

最后一条不是本文能解决的，但它是提交任何新补丁之前必须知道的：如果下一个接手的人从补丁链重建，会得到另一套渲染器。

---

## 10. 附录

### 10.1 环境变量总表（本文涉及的全部）

| 变量 | 取值 | 作用 | 引入 |
|---|---|---|---|
| `PS2X_GS_RENDERER` | `hw` / `sw` | 选后端 | 既有 |
| `PS2X_GS_HW_SCALE` | `0.25–4` / `auto` | 内部分辨率；`auto` 走阶梯 | 既有，v2 改 auto 语义 |
| `PS2X_GS_WORKER` | `1` | GS 线程后端 | 既有 |
| `PS2X_GS_DISCARD_DRAWS` | `1` | 丢弃绘制，测地板 | 既有 |
| `GOW_RENDER_HEIGHT` | 行数 | 内部高度，未设窗口时同时决定窗口 | 既有 |
| `GOW_WINDOW` | `WxH` | 强制窗口尺寸，覆盖贴合逻辑 | 既有 |
| `GOW_GS_TIER` | `A/B/C` | 强制档位 | **v2** |
| `GOW_GS_POLICY` | `force-default/force-modern` | 强制状态/UBO 策略 | **v2** |
| `GOW_GS_STRICT` | `1` | 不变量违反即 abort | **v2** |
| `GOW_GS_CAPS` | `1` | 打印能力探测结果 | **v2** |
| `GOW_GS_HW_RING` | `0` | 关闭顶点环 | 既有 |
| `GOW_GS_HW_STATS` | `1` | 每 5 s 批次/纹理统计 | 既有 |
| `GOW_GS_COST` | `1` | 批次内分段计时（rdtsc） | 既有 |
| `GOW_GS_DIRTYRECT` | `0` | 关闭脏矩形 | **v2** |
| `GOW_GS_SHUFFLE_MERGE` | `0` | 关闭 shuffle 合批 | **v2** |
| `GOW_GS_SKIP_EMPTY` | `0` | 关闭全透明批次跳过 | **v2** |
| `GOW_GS_FAIL_TEST` | `context/shaders` | 注入启动失败，测降级链 | 既有 |
| `GOW_GS_HW_ERRTRACE` | `1` | 逐调用 GetError（会掉帧） | 既有 |
| `GOW_GS_HW_DUMPALL` / `DUMPAT` / `DUMPMAX` | — | 批次转储 | 既有 |
| `GOW_GS_HW_IDXDIAG` / `PALDUMP` | — | 索引/调色板诊断 | 既有 |
| `GOW_GS_HW_FLICKERLOG` / `SHIFTLOG` | `1` | 闪烁/滚动探针 | 既有 |
| `GOW_PERF_DIAG` | `1` / `frames` | 分桶 / 帧分布 | 既有 |
| `GOW_PERF_FRAME_PC` | `0x1837B8`（美）/`0x183BB8`（日） | guest 帧计数点 | 既有 |
| `GOW_VU1N_X64` | `1` | VU1 x64 JIT | 既有 |
| `GOW_VU1_FAST` | `1` | VU1 快语义（近似） | 既有 |
| `TOBIICHI_VENTANA_FPS` | `0` / `60` | 呈现上限，`0` 解限 | 既有 |
| `TOBIICHI_FPS_GOSTER` | `1` | 窗口 FPS 覆盖层 | 既有 |

### 10.2 命令速查

```bat
:: 增量构建（只改 C++ 时）
build.cmd -Stages sync,build

:: 三个基线
set GOW_VU1_FAST=1 & set PS2X_GS_HW_SCALE=0.5 & play-jpn.cmd
set GOW_VU1_FAST=0 & play-jpn.cmd
set PS2X_GS_DISCARD_DRAWS=1 & play-jpn.cmd

:: 诊断组合
set GOW_GS_HW_STATS=1 & set GOW_GS_COST=1 & set GOW_PERF_DIAG=1 & play-jpn.cmd
set GOW_GS_STRICT=1 & set GOW_GS_CAPS=1 & play-jpn.cmd
set GOW_GS_TIER=C & play-jpn.cmd

:: 健康检查（25 秒，含分桶）
python tools/diag/game_health.py --seconds 25
python tools/diag/game_health.py --height 360 --env GOW_VU1N_X64=1

:: 盘识别（用临时 data 目录，别污染 data/gow1）
python -I tools/disc/identify.py "<iso>"
```

### 10.3 术语表

| 术语 | 含义 |
|---|---|
| GS | Graphics Synthesizer，PS2 的固定功能图形芯片，本项目用 GL 模拟 |
| 批次（batch） | 相邻且状态完全相同的图元合并成一次 GL draw |
| 状态 run | 状态不变的一段连续图元，通常一个批次对应一个 |
| `HwVertex` | 提交给 GL 的顶点结构，64 B / 16 float |
| 顶点环 | 持久映射的环形顶点缓冲，回绕时用 fence 保护 |
| shuffle | 16 位目标之间的通道重排，GS 特有操作 |
| CLUT | 调色板纹理，256 色 |
| 重解释（reinterpret） | 同一段 VRAM 按另一种格式/宽度读取，shader 里做地址映射 |
| Z 别名 | `ZBP == FBP`，深度存在颜色内存的 Z 字里 |
| 工作点 | 内部分辨率的具体取值（如 0.55×） |
| 双墙模型 | `T_gs ≈ T_fixed + max(T_fill, T_submit)` |
| guest fps | 游戏逻辑帧率，由 `frame_pc` 计数，唯一可宣称的帧率 |
| host Hz | 窗口呈现频率，可能重复画同一帧 |

### 10.4 与现有文档的关系

| 文档 | 关系 |
|---|---|
| `docs/RENDER-PIPELINE-HANDOFF-2026-11-04.zh-CN.md` | 本文的直接前身。那份记录“做了什么、什么被证伪”，本文回答“下一步怎么设计”。第 7.4 节的证伪清单全部来自它 |
| `docs/architecture.md` | 仓库级架构（profile/pipeline/launcher），本文只覆盖 GS 后端 |
| `docs/diagnostics.md` | 环境变量总表，本文第 10.1 节是它的子集 + v2 新增项 |
| `docs/tested-hardware.md` | 实测记录归档，v2 的验收数字应追加进去 |
| `low-spec-renderer.patch` | 启动器侧的“低配档”，本文第 3.1、3.5 节的第一组数字来自它的头注释 |
| `AGENTS.md` | 维护者规约；本文的所有补丁编号、注释语言、验收习惯都遵循它 |

### 10.6 GS 寄存器 → GL 状态对照表

改渲染器时最常查的一张表。最后一列是“这个字段在本后端里的真实状态”，包括**没实现**的那些 —— 知道什么没做，比知道什么做了更重要。

| 寄存器 | 关键字段 | GL 对应 | 本后端处理 | 坑 |
|---|---|---|---|---|
| `FRAME` | `fbp` / `fbw` / `psm` / `fbmsk` | FBO + `glColorMask` | 按 `(fbp, fbw)` 选 `RenderTarget`；`fbmsk` 非 0 时逐通道设 mask | `psm` 变化会让已缓存的纹理失效 |
| `SCISSOR` | `x0/y0/x1/y1` | `glScissor` | 每批次设置，帧末关闭 | 忘了关会把 present 裁成一小块 |
| `XYOFFSET` | `ofx` / `ofy`（1/16 像素） | 顶点着色器的 `uInvSize` 之前偏移 | `x - ofx/16 + 0.5` | 半像素偏移错了 → 整体糊/错位一像素 |
| `PRIM` | `type` / `tme` / `iip` / `abe` / `fst` / `fge` | 绘制模式 + shader 变体 | 三角→3 顶点，精灵→6 顶点，线→6 顶点 | `iip=0` 时颜色必须 flat，不能插值 |
| `TEX0` | `tbp0/tbw/psm/tw/th/tcc/tfx/cbp/cpsm/csm/csa` | 纹理对象 + `uTexFmt/uTexFmt2` | 4 条解码路径（直接/索引/重解释/Z 别名） | `tcc` 决定是否乘顶点色，写反就整体偏色 |
| `TEX1` | `lcm/mxl/mmin/mag/mtba` | `glTexParameteri` 的过滤 | **只用 `linearFilter` 标志，不生成 mip** | 游戏给的 mip 链地址被忽略，远处纹理可能闪烁 |
| `TEXA` | `ta0/ta1/aem` | shader 里的 alpha 展开 | 按 psm 决定展开方式 | CT24 的 alpha 来自 TA0/AEM，不是 texel |
| `TEXCLUT` | `cbw/coffx/coffy` | 调色板寻址 | `paletteFor` 生成 256×1 RGBA | 索引纹理不随 CLUT 重解码（有意） |
| `ALPHA` | `a/b/c/d` + `fix`（高 32 位） | `glBlendFuncSeparate` / `glBlendEquation` / `glBlendColor` | 6 种走固定功能，其余走 shader 软混合 | 见 5.10，`COLCLAMP=0` 必须软混合 |
| `TEST` | `ate/atst/aref/afail/date/datm/zte/ztst` | alpha test + `glDepthFunc` + `glEnable(DEPTH_TEST)` | `afail≠0` 时画两遍 | 两遍无法合并；stencil 方案更慢 |
| `ZBUF` | `zbp` / `psm` / `zmask` | 深度附件 + `glDepthMask` | `zmask=1` 表示**禁止写** | 语义反了就是“远处物体挡近处” |
| `FBA` | `fba` | 目标 alpha 的来源 | **未读** | 依赖它的效果会差一点点 |
| `COLCLAMP` | bit0 | shader 软混合的环绕 | `0` ⇒ 不钳制，`fract` 式环绕 | 阴影体计数靠它，见 5.10 |
| `DTHE` | bit0 | 抖动 | **未实现** | 16 位目标可能有色带 |
| `DIMX` | `dw/dh` | 水平降采样 | **未实现** | 少数特效会偏 |
| `SCANMSK` | `msk` | 扫描线掩码 | **未读** | 极少使用 |
| `FOG` | 颜色 | 雾色 | 只保存颜色，**不参与计算** | 雾在游戏里由 VU1 算好写进顶点色 |
| `MIPTBP1/2` | — | mip 链基址 | **未读** | 与 TEX1 的 mip 缺失是同一件事 |
| `BGCOLOR` | `r/g/b` | 呈现时的背景色 | present 路径使用 | 黑边颜色不对先查这里 |

**“未实现”的那几行不是缺陷清单，而是风险清单。** 它们意味着：如果某个场景出现“色带”“特效位置偏一点”“雾不对”，先怀疑这几项，而不是怀疑整个渲染器。本工程的定位是“能完整游玩”，不是“逐比特复刻 GS”；把边界写清楚，比假装没有边界更专业。

### 10.5 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-11-05 | 首版：问题定义、落点地图、硬件模型、架构 v2、子系统实现、无 bug 方法、帧率工程、六冲刺路线 |

---

## 11. 一天内跑通：动手清单

前面十章是“为什么”，这一章是“现在做什么”。按小时排，每一步都有明确的完成标志。

### 第 0 小时：确认你在哪

```bash
git log -1 --oneline
git status --short | head
python <skill>/scripts/verify_anchors.py --root .      # 补丁链与运行时环境变量是否还在
cat engine/runtime.toml | head -20                     # 钉住的 commit
```

**完成标志**：你知道当前 checkout 的 commit、有没有未提交改动、`engine/runtime/` 是否已 fetch。

⚠️ 如果 `engine/runtime/` 不存在，先跑 `build.cmd -Stages fetch`。**没有运行时，后面每一步都做不了。**

### 第 1 小时：构建并看到画面

```bat
build.cmd -Stages sync,build
```

**完成标志**：`C:\gow-build\ps2xRuntime\ps2EntryRunner.exe` 存在且能启动，标题画面出现。

如果构建失败，先看第 10.2 节的命令速查和 `docs/` 里的构建文档。**不要在构建问题上硬扛超过一小时** —— 大概率是构建目录不短、或者工具链版本不对，这两件事都有现成解法。

### 第 2 小时：三个基线

```bat
:: ① 快模式（应 59.6–60.1）
set GOW_VU1N_X64=1 & set GOW_VU1_FAST=1 & set PS2X_GS_HW_SCALE=0.5
set GOW_PERF_DIAG=1 & set GOW_PERF_FRAME_PC=0x183BB8 & play-jpn.cmd

:: ② 精确模式（应 52–56）
（同上，GOW_VU1_FAST=0）

:: ③ 丢弃绘制（应 59.9）
（同上，加 PS2X_GS_DISCARD_DRAWS=1）
```

**完成标志**：三个数落在预期区间。**如果对不上，停下来查环境**（是不是双实例、窗口是不是黑的、是不是不同场景）。带着错的基线做优化，等于用坏尺子量布。

### 第 3 小时：录黄金帧

按第 6.4 节，录 4 个场景各 300 帧，存到 `data/regress/`。

**完成标志**：能回放，且两次回放的哈希相同（证明回放本身是确定性的）。**这一步如果做不到，先别改代码** —— 你后面所有“没回归”的声明都需要它。

### 第 4 小时：加 `caps` 日志

按 Sprint 0，加 `DeviceCaps` + `ProbeCaps` + 启动日志。这是纯增量，不改行为。

**完成标志**：启动日志出现
```
[gs-hw] caps: gl=4.3 vendor=intel device="Intel(R) HD Graphics 4400" ...
```

### 第 5–7 小时：第一个真改动（分辨率阶梯）

按第 5.7 节实现 `WorkPointLadder`，先只在 `PS2X_GS_HW_SCALE=auto` 时生效。

**完成标志**：从 1.0× 启动，5 秒内自动落到 0.55–0.70×，guest ≥ 40，且日志里有
```
[gs-hw] workpoint 1.00 -> 0.70 (fps 24.3)
```

### 第 8 小时：验收与记录

- 黄金帧哈希：**必须完全一致**（阶梯只改 RT 尺寸，不改语义；但如果你的实现改动了采样精度，可能差 1 LSB，这要单独判断）
- 三个基线没有退化
- 写一条 `docs/research/renderer-tiering-2026-11-XX.md`，按“结论先行 → 证据链 → 证伪 → 回退”的格式

### 卡住时的对照表

| 现象 | 最可能的原因 | 一句话解法 |
|---|---|---|
| 改了代码没反应 | 可运行构建绑的是另一个源码快照（如 `C:\gow-jpn`） | 复制改动 + `touch` 时间戳 + 重建 |
| Ninja 说 `no work to do` | 复制的文件保留了旧 mtime | 改 `LastWriteTime` |
| 启动就黑屏、无日志 | 上下文创建失败 | `GOW_GS_FAIL_TEST=context` 复现，看降级链 |
| 帧率突然翻倍 | 很可能有第二个实例在抢窗口，或者画面是黑的 | `taskkill /F /IM ps2EntryRunner.exe` 后重跑 |
| `glBufferStorage` 报 `0x501` | flags 用了 `GL_DYNAMIC_DRAW` | 改成 `GL_DYNAMIC_STORAGE_BIT`（0x0100） |
| 画面花屏 + `0x502` | 某处 `UseProgram` 没同步 `boundProgram` | `grep -rn "UseProgram("` 逐处审 |
| 几何撕裂/黑块 | 顶点环回绕无栅栏，或单批次超环容量 | 看 `ringWraps` / `oversizedBatches` |
| 进 3D 全黑、菜单正常 | shuffle 路径泄漏 program | 查 `shuffles` 是否为 0，见 6.9 |

这张表覆盖了本工程历史上 80% 的“卡住两小时以上”。把它打印出来贴在显示器边上，比读十篇文档有用。

---

## 12. 反模式目录

这一章不是“最佳实践”，是**已经在这个工程里造成过损失的 20 个具体做法**。每条都写了“为什么诱人”，因为不理解诱惑就无法在下次识别它。

| # | 反模式 | 长什么样 | 为什么诱人 | 正确做法 |
|---|---|---|---|---|
| 1 | 等价替身 | 用 `+v.a` 实现规范里的 `+0x80` | 在当前数据上数值相等，代码更短 | 照规范写；不相等的数据一定会出现 |
| 2 | 第二真相 | 缓存的 `boundProgram` 与驱动实际绑定不一致 | 省一次驱动查询 | 包装函数里同时更新，或立刻 invalidate |
| 3 | 用 UBO 换 uniform | 35 个 `glUniform` → 1 个 `glBufferSubData` | 调用数从 35 降到 2 | 先测；Intel 上是负收益 |
| 4 | MultiDraw 合并不同状态 | 一个 `glMultiDrawArrays` 画多段 | 减少 draw 调用 | 状态只对第一段有效，后段全错 |
| 5 | 全局按纹理排序 | 按 tbp0 排序所有批次 | 纹理切换最少 | 破坏混合顺序，画面必错 |
| 6 | 降分辨率当万能药 | “卡就调 0.35×” | 一行环境变量就见效 | 0.35× 与 0.5× 同帧（撞提交墙） |
| 7 | 拿 `host_hz` 当 fps | 报“60 帧” | 数字好看 | 看 `guest_flip_hz` |
| 8 | 窗口长度不可比 | 30 s 与 60 s 对比 | 省时间 | 同长度，且 ≥45 s |
| 9 | 在标题上判优化 | 测标题有没有变快 | 标题最容易复现 | 标题已贴顶，看不出差异 |
| 10 | 小块环形缓冲 | 4 MB 环分 8 块 | 缓存友好 | 每帧 37 次 sync → 1.4 fps |
| 11 | 跨批次裸指针 | `RenderTarget *shuffleDst` | 省一次查表 | vector 搬迁 → 悬垂 |
| 12 | 加字段不加断言 | 改 `DrawUniforms` 布局 | 快 | `static_assert(offsetof)` 锁死 |
| 13 | 用驱动名判能力 | `if (renderer == "Intel HD")` | 一行判断 | 查 `GL_VERSION` / 扩展 |
| 14 | 用 `glFinish` 当同步 | 同目标读写前 finish | 一定正确 | Intel 上几十 ms，改用 barrier |
| 15 | 一次改五件事 | 一个大 PR | 省事 | 出问题只能全回滚 |
| 16 | 没有回退开关 | 新路径直接替换旧的 | 代码干净 | 出问题用户只能等新版本 |
| 17 | 只测标题 | “跑起来了，没问题” | 快 | 场景 bug 只在场景里出现 |
| 18 | 平均值掩盖长尾 | “平均 58 fps” | 数字漂亮 | 报 p95/p99 |
| 19 | 相信常识 | “缓存一定更快” | 教科书说的 | 在这台机器上 A/B |
| 20 | 无条件的性能数字 | “提升了 20%” | 好汇报 | 带机台/设置/场景/窗口 |

### 12.1 深挖五条

**#1 等价替身** 是唯一一条会**静默产出错误画面**的反模式。其它 19 条最多让你变慢或卡住，这一条会让你在“测过的场景全对”的情况下，把错误发布出去。判断方法：写完一个公式后问自己“如果某个输入是 0 或 255，它还成立吗”。`+v.a` 在 alpha=128 时等于 `+0x80`，在 alpha=255 时就差了一倍 —— 而 GOW 1 的标题云雾恰好是 255。

**#2 第二真相** 是唯一一条会**整帧错**的反模式。它的可怕之处在于“代码看起来完全正确”：`UseProgram(draw)` 明明调了，为什么用错着色器？因为有一层缓存在替你做决定。判断方法：`grep -rn "UseProgram("`，看每一处的同一个函数里有没有 `boundProgram = ...`。v2 的解法是让 grep 只剩一处。

**#10 小块环** 反直觉程度最高。所有人都会觉得“环小一点缓存命中率高”，但在这个负载下（每帧 19–26 MB 顶点），小环意味着每帧回绕几十次，每次回绕一个 `glClientWaitSync`，而 Intel 每次 sync 1–3 ms。**37 次 sync = 40–100 ms/帧**，直接把 7 fps 打成 1.4。判断方法：看 `ringWraps/帧`，> 2 就该加大。

**#19 相信常识** 是本工程最贵的一条（三条证伪，合计约一周）。它的根源是把“通用 GPU 架构的规律”套到“一块 2013 年的 20 EU 集显 + 一个实现质量参差的驱动”上。判断方法：任何“应该更快”的改动，先在目标机器上跑 45 秒 A/B，再决定要不要写第二行代码。

**#20 无条件的性能数字** 是团队协作层面最有害的一条。它让后来的人无法判断“这个优化在我的机器上是否成立”，于是要么盲信、要么重测。本工程的 `【实测】` 标签就是为此存在的：**数字必须带机台、设置、场景、窗口长度，否则它不是证据，是传闻。**

### 12.2 一条元规则

把 20 条压成一句：

> **任何改动，如果不能用一句话说清“它减少了什么工作量、在哪个场景、用什么数字验证”，那它就不是优化，是重写。**

这句话能挡掉 80% 的无效工作。剩下的 20%，才是真正需要写代码的部分。

---

## 13. 测量方法论

第 7 章讲了“优化什么”，这一章讲“怎么知道你真的优化了”。在一个每秒 400 批次、每帧 1.4 万图元、三种线程互相等待的系统里，**错误的测量比不测量更危险**——它会让你朝错误的方向优化两周。

### 13.1 实验设计的五条铁律

| 铁律 | 具体做法 | 违反的后果 |
|---|---|---|
| 单变量 | 一次只改一个开关/一处代码 | 两个变量同时变，收益无法归因 |
| 同场景 | 同盘、同存档、同进入路径、同 `GOW_FAST_BOOT`/`GOW_SKIP_FMV` | 30 s 和 60 s 落在不同阶段，差 2–3 倍 |
| 同窗口 | 同窗口尺寸、同内部分辨率、同呈现上限 | 1280×720 vs 640×360 差 37% 呈现率 |
| 同长度 | 每次 ≥ 45 s，取稳定窗口 | 5 s 的尖峰不可信 |
| 单实例 | 启动前 `taskkill` 残留进程 | 双实例抢窗口，帧率凭空变化 |

第五条最容易被忽略，因为它“看起来不影响测量”。但双实例会让其中一个窗口不可见或半可见，DWM 的合成成本完全变了 —— 你测的不再是同一个东西。

### 13.2 预热与稳态

前 5 秒必须丢弃。原因有三：

1. 着色器编译（4 个变体 × 100–300 ms）集中在前几秒；
2. 纹理首次解码（`texDecodes` 尖峰）集中在前几秒；
3. 分辨率阶梯在前几秒还在找落点。

**报数字时明确写“丢弃前 5 秒，取 15–45 s 窗口”**。不写这句话的数字，别人无法复现。

### 13.3 方差与重复

同一配置跑 3 次，看离散度：

| 离散度 | 含义 | 处理 |
|---|---|---|
| < 2% | 稳，可以信 | 直接比较 |
| 2–5% | 有隐藏变量 | 检查后台进程、温度、窗口焦点 |
| > 5% | 不可比 | 先找出变量，再谈优化 |

老 iGPU 有一个特殊问题：**共享功耗墙**。长时间满载会让 CPU/GPU 一起降频，所以“跑 5 分钟后的帧率”往往低于“刚启动的帧率”。对策是每次测量控制在 60 s 内，且两次测量之间歇 30 s。

### 13.4 显著性：1 帧算不算提升

在一台机器、一个场景、45 s 窗口下，**±1 fps 通常在噪声范围内**（尤其 55–60 这个区间，因为已经贴顶）。判断标准：

- 差 ≤ 1 fps：不足以结论，除非重复 3 次都同向。
- 差 2–4 fps：可疑，需要第二个场景交叉验证。
- 差 ≥ 5 fps：可信，但仍要确认“画面没变差”。

**不要用“提升了 3%”这种说法**，因为 3% 在 60 fps 限量下可能只是 1.8 帧，在噪声里。要说“从 52.6–55.8 提到 59.6–60.1”，给出区间而不是单点。

### 13.5 记录模板

每次测量写成一个块，贴进 `docs/research/`：

```markdown
### <日期> <改动名>
机器: i3-4170 / HD 4400 / 8 GB DDR3 / Win10
构建: <commit> + patch NN
设置: 0.5x, 640x360 窗口, VU1 x64 JIT on, FAST=1, 丢弃前 5 s
场景: 亚洲盘标题（GOW_FAST_BOOT=1, GOW_SKIP_FMV=1），45 s

| 指标 | 改前 | 改后 | 差 |
|---|---|---|---|
| guest_flip_hz | 52.6–55.8 | 59.6–60.1 | +6 |
| gs_ms /5s | 2130–2200 | 1925–2177 | −5% |
| vu_ms /5s | 4550–4600 | 4000–4130 | −11% |
| p95 帧时间 | ? | 18.2 ms | — |

画面: 标题/Logo/菜单三张 PPM 与基线逐像素一致
回退: GOW_GS_XXX=0
未验证: 战斗、后期过场、NVIDIA/AMD
```

最后两行是这份模板的灵魂：**回退方式**与**未验证范围**。没有它们的报告，会让下一个接手的人误以为“这个改动在全场景都验证过了”。

### 13.6 一个反面教材

```markdown
优化了渲染器，帧率提升 20%，画面正常。
```

这句话的问题：哪台机器？什么场景？20% 是从多少到多少？画面“正常”是谁判断的、看了哪几帧？没有回退开关吗？如果下一个人在自己机器上测出 −5%，他该信谁？

**本工程的规矩是：这样的报告一律不接受。** 不是因为苛刻，而是因为一份无法复现的报告，价值等于零，还会污染后续的判断。

---

## 14. 与启动器、用户体验的衔接

渲染器做得再好，如果用户点不到正确的开关，等于没做。这一章讲“怎么把一个有档位的渲染器暴露给用户而不制造混乱”。

### 14.1 一条已经验证过的教训

`low-spec-renderer.patch` 的头注释写得很直接：

> The graphics tab exposed nine independent knobs, and every report from a weak GPU ended the same way: "everything at minimum and it still stutters".

九个独立旋钮的结果，是用户把所有旋钮拧到最低，然后发现还是卡 —— 因为真正的瓶颈（内部分辨率与窗口尺寸的耦合）不在那九个旋钮里。

**结论：设置项的个数不是自由度，是认知负担。** 一个用户能理解的档位数是 3 个，不是一个 9 维空间。

### 14.2 只暴露三个设置

| 设置 | 选项 | 默认 | 说明 |
|---|---|---|---|
| 画质档 | 低配 / 均衡 / 画质 | **自动**（按 `caps` 选） | 一键设定整组参数，用户不需要理解每一项 |
| 帧率优先 | 开 / 关 | 开 | 开 = 允许分辨率阶梯降到 0.35× 换取帧率；关 = 锁定在当前档 |
| 高级（折叠） | 档位 A/B/C、固定分辨率、窗口尺寸 | 自动 | 给愿意折腾的人，默认不展开 |

**“自动”必须是默认值。** 因为绝大多数用户不知道自己的显卡是什么型号，更不知道它支持哪个 GL 版本。让渲染器自己探测、自己选档、自己找落点，是唯一能规模化的做法。

`PS2X_GS_HW_SCALE=auto` 已经是这个思路的雏形（阶梯由渲染器自己走），v2 只是把它扩展成“档位也自动”。

### 14.3 三个预设具体是什么

| 参数 | 低配 | 均衡 | 画质 |
|---|---|---|---|
| 档位 | C（或 B 的保守参数） | B | A |
| 分辨率阶梯 | 0.35–0.70，起始 0.45 | 0.45–1.00，起始 0.70 | 0.70–2.00，起始 1.00 |
| 窗口 | 640×360 | 960×540 | 1280×720 |
| 呈现 | 整数贴合、NEAREST | 双线性 | 双线性 |
| 后处理 | 全关 | 全关 | 可选锐化 |
| 顶点环 | 16 MB | 32 MB | 48 MB |
| 纹理脏矩形 | 开 | 开 | 开 |

注意“低配”并没有关掉脏矩形 —— 它是纯收益且不影响画质。**“低配”关掉的应该只是“花帧率买画质”的东西，不是“免费的东西”。** 这个区分很重要：很多“低配模式”把免费优化也一起关了，结果低配比中配还慢。

### 14.4 失败与降档必须让用户看见

三种情况，三种文案：

| 情况 | 用户看到 | 附带动作 |
|---|---|---|
| 上下文创建失败 | “你的显卡驱动不支持 OpenGL 4.3。请更新驱动，或点击‘兼容模式’（很慢）。” | 一键切 `sw` |
| 着色器编译失败 | “渲染器初始化失败（着色器）。已自动切换到兼容档。” | 自动降档 + 记录 |
| 运行中降档 | 角落里一行小字 3 秒：“已降低画质以保持流畅” | 可关闭提示 |

**不要用技术术语。** “OpenGL 4.3 core profile 创建失败”对用户没有意义；“请更新驱动”有意义。文案在 `launcher/qml/Textos.js` 里做四语（tr/en/es/pt），新增条目要同步。

### 14.5 一键导出诊断

老显卡用户反馈问题时，最有用的不是“我卡”，而是一个包含以下内容的压缩包：

```
diagnostics-2026-11-05-1830.zip
├─ caps.txt          # [gs-hw] caps / policy 两行 + 完整 GL 字符串
├─ perf.log          # 最近 60 s 的 [gow-perf] 与 [gs-hw] 行
├─ settings.txt      # 当前所有 GOW_*/PS2X_* 的值
├─ gpu.txt           # 驱动版本、显存、分辨率
└─ screenshot.ppm    # 当前帧的 GS 输出（不是窗口截图）
```

这五样东西能让维护者在 5 分钟内判断“是档位选错了、是驱动问题、还是真的渲染 bug”。没有它们，一轮往返就是两天。

**注意隐私**：`screenshot.ppm` 是游戏画面，不要自动上传；只放在本地压缩包里，由用户自己决定是否发送。这也是仓库的既有约束（不提交游戏数据/截图）。

### 14.6 与现有 QML 的关系

| 文件 | 改动 |
|---|---|
| `launcher/qml/PaginaGrafico.qml` | 从 9 个旋钮收敛成 3 个 + 一个折叠的“高级” |
| `launcher/qml/Main.qml` | 侧边栏不变；设置页顺序不变 |
| `launcher/qml/Textos.js` | 新增约 12 条文案（四语） |
| `launcher/src/lanzador.cpp` | `aplicarPerfil` 扩展成三档；写入 `gow-native.boot` |
| `launcher/src/installer_backend.cpp` | 不变 |

**不要新增页面。** 现有的 0=Home、1=Install、2–6=设置、7=Saves、8=Accessibility 结构已经够用，加页面只会让用户更迷路。

### 14.7 验收：三步之内能玩

```
① 双击启动器
② 点“安装”（如果还没装）
③ 点“开始游戏”
```

中间不允许出现“请选择内部分辨率”“请选择档位”这类必需决策。所有决策由默认值 + 自动探测完成，用户想调才去调。

**这条验收标准比任何帧率数字都重要** —— 因为一个需要用户理解 GS 架构才能跑 60 帧的移植，实际上只有作者能玩。

---

## 15. 从 v2 到 v3：还能往哪走

v2 的目标是“让老显卡跑到它该有的帧率”。v3 的问题是“还有没有结构性空间”。这一章给六个方向，每个都带可行性判断 —— **判断比想法值钱**。

### 15.1 异步着色器编译 + program binary 缓存

| 项 | 内容 |
|---|---|
| 想法 | 启动时在后台线程编译 4 个变体，主线程先跑一个“最小 program”；编译完再切 |
| 为什么可能有效 | 老 iGPU 上一个 program 100–300 ms，4 个就是 0.4–1.2 s 的启动停顿 |
| 成本 | 中（要处理“编译完成前用哪个 program”） |
| 风险 | 低（画面短暂用简化着色器，可能几帧不准） |
| 判断 | **值得做**，但它优化的是启动体验，不是帧率 |

`glGetProgramBinary` / `glProgramBinary` 可以把编译结果缓存到磁盘，第二次启动直接加载。老驱动对它的支持参差，必须验证“加载后 `GL_LINK_STATUS` 仍是 true”，否则会拿到一个损坏的 program。这条对“每次启动都要等 1 秒”的体验提升明显。

### 15.2 直接渲染到共享呈现纹理

| 项 | 内容 |
|---|---|
| 想法 | 现在 `Present` 要把最终目标拷贝到共享纹理（一次 GPU 拷贝），再由 host blit 到窗口。能不能让 GS 直接画进共享纹理？ |
| 为什么可能有效 | 省一次 412×360 的拷贝 + 一次同步 |
| 成本 | 高（要处理“游戏把这块内存当纹理采样”的情况） |
| 风险 | 高（共享纹理的格式/布局由 host 上下文决定，可能与 GS 的 psm 不兼容） |
| 判断 | **不做**。GS 的显示目标随时会被当纹理读（Z 别名、reinterpret、shuffle 的源），它必须留在“VRAM 镜像”的语义里。省一次拷贝的收益远小于破坏这个语义的风险 |

这是“看起来很美、实际会炸”的典型。判断依据是 4.14 节的鸿沟：**显示目标不是一个“输出缓冲”，它是 VRAM 的一段。** 任何把它特殊化的设计都会在某个场景崩掉。

### 15.3 纹理压缩（BC1/BC3）

| 项 | 内容 |
|---|---|
| 想法 | 把大纹理（512×512 以上）压成 BC1/BC3，显存与带宽降到 1/4–1/8 |
| 为什么可能有效 | 老 iGPU 带宽极低，纹理采样是大头之一 |
| 成本 | 高（要离线或首次解码时压缩；要处理 CLUT 索引纹理不能压） |
| 风险 | **极高**（GS 的 alpha 是精确的 8 位，BC1 的 alpha 只有 1 位；CT24 的 alpha 语义会崩） |
| 判断 | **只对“无 alpha 的直接色纹理”做实验**，且必须逐像素对比。默认关闭 |

BC1 对 RGB 的误差在多数场景可接受，但它对 alpha 是 1 位 —— 而这个游戏大量依赖 alpha test（植被、栅栏、粒子边缘）。一旦 alpha 从 8 位变 1 位，`ATST` 的阈值判定会整体改变，画面会出现“边缘变硬/镂空消失”。这是一条“收益可观但正确性极难保证”的路，只适合作为研究分支。

### 15.4 VU1 与 GS 的流水化

| 项 | 内容 |
|---|---|
| 想法 | 现在 VU1 产出几何 → 入队 → GS 消费，两者部分串行（第 7.1 节的 24.4 ≈ 16.6 + 7.8 就是这个证据）。能不能让第 N+1 帧的 VU1 与第 N 帧的 GS 重叠？ |
| 为什么可能有效 | 直接把串行部分变成并行，理论上能把 41 帧推到 50+ |
| 成本 | 极高（要双缓冲整个 GS 状态快照 + 顶点流；要保证 guest 看到的 FINISH 语义不变） |
| 风险 | 极高（FINISH/PRESENT 的语义、存档一致性、逐帧输入的时序） |
| 判断 | **这是唯一有可能把 41 推到 60 的结构性手段，但不是一个渲染器改动**。它要动 EE/VU/GS 的协同，属于 v3 的核心议题。做之前必须先有“逐帧 trace”证明串行比例 |

这条值得单独强调：**渲染器优化到极限也到不了 60，因为瓶颈已经跨出了渲染器。** 如果目标是“全场景 60”，最终必须动这条；如果目标是“老显卡上可玩、不卡顿”，v2 就够了。

### 15.5 用 compute 做 shuffle

| 项 | 内容 |
|---|---|
| 想法 | shuffle 是纯内存重排，天生适合 compute shader（一次 dispatch 处理整块） |
| 为什么可能有效 | 省掉 FBO 绑定 + 顶点装配 + 光栅化的全部开销 |
| 成本 | 中（已有 GL 4.3，compute 可用） |
| 风险 | 中（要保证与逐像素路径完全一致的位语义） |
| 判断 | **在 20 EU 的集显上预期为负收益**，在独显上可能为正。列为“按档位启用”的候选，不进 v2 |

理由：compute 在老 iGPU 上与图形管线共享同一批 EU，dispatch 的固定开销（约 10–20 µs）在小批量下比一次 draw 还贵。shuffle 的每次工作量通常只有几个精灵，摊不平 dispatch 成本。**只有当 `shuffles/shuffleDraws` 很大（每次几百个）时才值得。**

### 15.6 明确不做的四件事

| 想法 | 为什么不做 |
|---|---|
| 帧生成 / 帧插值 | 游戏逻辑锁 60 Hz VBlank，插帧只会引入输入延迟与画面撕裂，且 GS 的确定性会被破坏 |
| 全局光照 / SSAO 等后处理 | 与“还原 PS2 画面”的目标冲突，且在老卡上是纯成本 |
| 把 GS 换成现代管线（延迟渲染等） | 语义完全不同，等于重写游戏渲染 |
| 提高内部分辨率到 4K | 老卡连 1× 都吃力，这是给新卡的功能，不是给本文读者的 |

最后一条不是技术判断，是产品判断：**这份文档的读者是老显卡用户，一切设计都要先服务“能稳定玩”，再谈“更好看”。**

### 15.7 v3 的三个前置条件

如果将来要做 v3，先满足这三条，否则一定失败：

1. **逐帧 trace 能力**：能导出“每帧 EE/VU/GS 的重叠时间线”，否则无法证明串行比例。
2. **黄金帧覆盖率 ≥ 80%**：v2 的回归只能覆盖 4 个场景，v3 要动流水线，需要更多。
3. **一个可回退的开关**：v3 必须是“可选路径”，不能替换 v2。

这三条的共同点是：**先把“怎么知道对不对”解决，再解决“怎么做得更快”。** 这是本文从头到尾的立场。

---

## 16. 完整案例：一台 24 帧的机器怎么调到 47

前面十五章都是分解动作，这一章把它们连起来。对象就是本工程的主力测试机。**每一步都标了“实测”还是“估算”** —— 只有前三步有实测数字，后面是依据第 7.1 节的模型推算的，读者必须知道这个差别。

### 16.1 起点

```
机器: i3-4170 (2C4T) + Intel HD 4400 + 8 GB DDR3 + Win10
设置: 内部 1.00× (512×448), 窗口 1280×720, VU1 x64 JIT 开, 快模式关
场景: 亚洲盘标题 / 演算前段
结果: guest 24.3 fps, 呈现 45.9 Hz              ← 【实测】
```

这个配置就是“启动器默认全部最低”的样子。用户的第一反应通常是“这游戏优化真差”，但真实原因是：**1× 在集成显卡上是买不起的，而窗口还在按 1280×720 合成。**

### 16.2 第一步：把分辨率交出来

```
设置: 内部 0.70× (358×314), 窗口仍 1280×720
结果: guest 39.2 fps, 呈现 59.1 Hz              ← 【实测】
```

**+14.9 帧，代价是画面小了 30%。** 这一步的收益来自填充率：像素少了 51%，而帧时间从 41 ms 降到 25.5 ms。

注意：此时瓶颈已经换人了。`gs_ms` 不再是主导，VU1 开始顶上来。**每一次优化都会改变瓶颈的位置，这是性能工程的常态。**

### 16.3 第二步：把窗口收回来

```
设置: 内部 0.50× (256×224), 窗口 640×360
结果: guest 41.3 fps, 呈现 58.9 Hz              ← 【实测】（低配档）
```

对比同一内部分辨率、1280×720 窗口的 40.4 fps / 59.6 Hz：**guest 只多 0.9 帧，但呈现稳定了。** 这说明窗口面积主要吃的是呈现侧的成本（合成 + DWM），不是渲染侧。

**这一组数据是本文“双墙模型”的直接证据**：0.70×→0.50× 像素再少 49%，guest 只涨 2.1 帧 —— 已经撞到提交墙。

### 16.4 第三步：让阶梯自己找落点

```
设置: PS2X_GS_HW_SCALE=auto，窗口跟随内部高度
结果: 启动 1.00× → 2 s 后 0.70× → 5 s 后 0.55×，稳定
      guest 41–42 fps，呈现 59–60 Hz            ← 【估算，依据前三步的曲线】
```

为什么是 0.55× 而不是 0.50×？因为阶梯的判据是“fps ≥ 59 就试着升档”，而 0.55× 在这台机器上刚好还能维持 41 帧左右（与 0.50× 同档），所以它会停在更高的一档。**这正是阶梯的价值：它比你手调更接近最优，因为它按真实帧率决策，而不是按你的猜测。**

### 16.5 第四步：呈现只画新帧

```
改动: Present 守卫（同一 renderSequence 8 ms 内不重画）+ 整数贴合 NEAREST
结果: 呈现 59 → 60 Hz，p95 帧时间下降 1–2 ms     ← 【估算】
```

这一步在 guest 帧率上没有收益（它本来就是 41），收益在**节奏**：少了重复 blit，帧时间的方差变小。玩家感知到的是“顺了一点”，而不是“快了几帧”。

### 16.6 第五步：顶点环加大

```
改动: 32 MB → 48 MB
结果: ringWraps 从约 1.2 次/帧降到 0，省 1–3 ms/帧   ← 【估算，依据每次 fence 1–3 ms】
```

对应 guest +0.5–1 fps。**这是最便宜的一刀**（改一个常量 + 重建），但只在“环确实偏小”时有效 —— 所以要先看 `ringWraps`，不要盲改。

### 16.7 第六步：抬地板

```
改动: 前端按 range 提交（Sprint 3）
结果: PS2X_GS_DISCARD_DRAWS=1 的 gs_ms 从 1.3–1.5 s/5s 降到 ≤ 1.0 s/5s
      重过场 guest +2–4                                   ← 【估算】
```

这一步对标题几乎无感（标题的地板本来就低），对重过场明显。**这就是为什么优化要按场景分开验收** —— 如果用标题验收，你会误判它“没用”。

### 16.8 第七步：纹理流

```
改动: 脏矩形 + 安全阀（Sprint 4）
结果: 重过场 upload_ms 777 → 约 350，gs_ms 降 0.3–0.5 s/5s
      重过场 guest +1–3                                   ← 【估算】
```

### 16.9 累计效果

| 阶段 | guest fps | 呈现 Hz | 依据 |
|---|---|---|---|
| 起点（1.00×, 720p） | 24.3 | 45.9 | **实测** |
| +0.70× | 39.2 | 59.1 | **实测** |
| +0.50× + 640×360 | 41.3 | 58.9 | **实测** |
| +阶梯自动（0.55×） | 41–42 | 59–60 | 估算 |
| +呈现守卫 | 41–42 | 60 | 估算 |
| +环 48 MB | 42–43 | 60 | 估算 |
| +range 提交 | 43–45（标题）/ 大幅改善（过场） | 60 | 估算 |
| +脏矩形 | 44–47（过场显著） | 60 | 估算 |

**从 24 到 47，大约是 1.95 倍。** 这个数字看起来不错，但必须把三件事说清楚：

1. **前三步（24→41）是实测的，占全部收益的 85%。** 后四步加起来只多 6 帧，而且都是估算。
2. **47 不是 60。** 差距来自 VU1 的 16.6 ms/帧（第 7.1 节），不是渲染器。
3. **这 47 帧的画质是 0.55×。** 想要 1× 又要 60，这台机器做不到 —— 任何声称做到的方案，要么在骗人，要么改变了游戏的渲染语义。

### 16.10 如果只能做一件事

做第三步（阶梯）。它用最少的代码拿到最大的收益，而且**不需要理解 GS 语义**。

### 16.11 如果只能做两件事

加第四步（呈现守卫）。因为它便宜、纯收益、且改善的是“手感”而不只是数字。

### 16.12 如果要做全部

按 Sprint 0→5 的顺序，每步单独验收、单独回退。**不要跳步**，因为每一步都会改变瓶颈位置，跳步会让你在错误的层次上优化。

这一章想说的其实是一个方法论：**性能优化不是“把每个环节都优化一遍”，而是“找到当前的主导项，把它削到不再是主导项，然后重复”。** 每削一次，主导项就换人；换到“削不动”为止。这台机器上，最后削不动的那一项是 VU1，那就该停手，去改 VU1 或者接受 47 帧。

---

## 附录 D：常见问答

**Q1：为什么标题画面能 60，一进开场就掉到 18？**
因为开场过场的工作量是标题的 2–3 倍。`【实测】` 开场 `vu_ms` 4350–4630/5s、`gs_ms` 1720–2845/5s，而 `PS2X_GS_DISCARD_DRAWS=1` 时也只有 30–43 fps —— **即使渲染器完全不存在也到不了 60**。18 帧多数出现在电影/加载阶段，不是渲染器的问题。这类场景的正确目标是“不卡顿”，不是“60”。

**Q2：为什么 0.35× 不比 0.5× 快？**
因为 0.5× 以下已经撞到提交墙。`【实测】` 0.50× 是 40.4 fps，0.35× 是 41.9 fps —— 像素少了 51%，帧只多 1.5。剩下的时间花在“每图元的固定成本 + 每批次的驱动开销”上，与分辨率无关。继续降分辨率只会损失画质。

**Q3：为什么窗口显示 60 Hz，游戏只有 40 帧？**
`host_hz` 是窗口呈现次数，它可以把同一 guest 帧重复画多次。真正的帧率是 `guest_flip_hz`（由 `GOW_PERF_FRAME_PC` 计数）。`【实测】` 开场过场 `host_hz` 34–53 而 `guest_flip_hz` 16–27，就是这个现象。

**Q4：VU1 快模式安全吗？**
它是**语义近似**，不是逐比特一致。AOT 版在 4000 条回放记录中有 23 条不同（0.57%），未见视觉差异；JIT 版只做了标题截图对比，**没有做战斗与后期过场的验证**。所以它默认关闭，只在启动器 Performance 档打开。出现任何异常，第一步是 `GOW_VU1_FAST=0` 复测。

**Q5：我改了 `engine/runtime` 里的代码，为什么运行没变化？**
因为可运行构建可能绑的是另一个源码快照（例如 `C:\gow-jpn`）。必须：复制改动文件 → 改 `LastWriteTime`（PowerShell 的 `Copy-Item` 会保留旧时间戳，Ninja 会认为“无需重建”）→ 重建。这个坑本工程踩过不止一次。

**Q6：`glBufferStorage` 报 `GL_INVALID_VALUE (0x501)`？**
flags 写成了 `GL_DYNAMIC_DRAW`（0x88E8）。正确的是 `GL_DYNAMIC_STORAGE_BIT`（0x0100）再或上 `GL_MAP_*_BIT`。另外：如果 `BufferStorage` 成功但 `MapBufferRange` 失败，**不能**对不可变存储再调 `glBufferData`（会 `GL_INVALID_OPERATION`），必须删掉 buffer 重建。

**Q7：我该选哪个档位？**
默认“自动”。如果你知道自己在做什么：Intel 集显选 B（甚至 C），AMD/NVIDIA 独显可以试 A 并 A/B。**不要因为“A 档更现代”就选 A** —— 在 Intel 上它是负收益，这是实测结论。

**Q8：为什么我的 NVIDIA 独显比别人的 Intel 集显还慢？**
三种可能：① 走了 iGPU（笔记本的 Optimus/双显卡切换没生效，渲染器跑在核显上）；② 档位是 C（降级链曾经触发过，结果被持久化了）；③ 驱动把 4.3 上下文给了软件实现。查 `[gs-hw] caps` 那一行的 `device=` 是不是你期望的卡。

**Q9：画面出现白块/黑块/条纹怎么办？**
按第 6.9 节的顺序：先分“没画”还是“画错”（`GOW_OSD` + `DISPDUMP`），再对比正常/异常帧的统计差异（`GOW_GS_HW_STATS`），最后才查 program 生命周期与顶点环。**不要一上来读渲染器代码**，那是效率最低的路径。

**Q10：为什么同一个场景要跑四次？**
因为至少有四个变量会改变结果：快模式开/关、丢弃绘制开/关、分辨率、窗口。只跑一次得到的数字无法归因。第 13 章的五条铁律就是为了避免“测了但结论错”。

**Q11：能不能直接上 1× 内部分辨率？**
在这台机器上不能。`【实测】` 1.00× 是 24.3 fps，0.50× 是 40.4。1× 需要 1.7 倍的性能，而 VU1 已经在 13.5 ms。新独显可以，老集显不行 —— 这不是“优化没做到位”，是硬件量级差异。

**Q12：纹理偶尔闪一下是怎么回事？**
两种常见原因：① 同目标读写没有 barrier（不变量 #8）；② 纹理失效粒度太粗/太细（`writeSeq` 与解码时序）。用 `GOW_GS_HW_FLICKERLOG=1` 看探针哈希是否周期 2 交替 —— 是则多半是缓冲序/双缓冲问题，不是纹理。

**Q13：`engine/patches` 缺号怎么办？**
已知 `engine/patches` 缺 49 等历史补丁，01–58 不能完整复现当前工作区（`【文档】` 交接文档第 19.3 节明确写了这一点）。两条路：补一个把差异收进去的补丁，或在 README 明确标注“工作区 = 链 + 手工状态”。**在补这个洞之前，不要从补丁链重建然后假设得到同一个渲染器。**

**Q14：`data/` 可以删吗？**
可以，它是生成物（盘、语言、记忆卡、重编译输出、VU1 捕获、日志），并且 git 忽略。但删了要重新 `prepare` 盘、重新 `recomp`，代价是几十分钟到几小时。**不要删 `.workbuddy/`**（项目数据），也不要删 `engine/runtime/`（除非你打算重新 fetch）。

**Q15：我想贡献一个补丁，流程是什么？**
① 在 `engine/runtime/` 改；② 生成 `NN-name.patch`（编号递增，一个补丁一件事）；③ 补丁头用英文写 what / why / **实测数字**；④ 跑黄金帧确认无回归；⑤ 更新 `engine/README.md` 的补丁表；⑥ 在 `docs/research/` 留一份记录（结论先行 → 证据链 → 证伪 → 回退）。**没有实测数字的补丁不会被接受**，因为它无法被后人判断是否值得保留。

**Q16：为什么文档里到处都是“实测/文档/推断”的标签？**
因为渲染器的问题里，**“我以为”和“我测了”差别巨大**。本工程有三条被实测推翻的“常识”（UBO、状态缓存、降分辨率），如果它们被当成事实写进文档，后来的人会照着做，然后浪费一周。标签的作用是让读者知道“这条能不能直接信”。

**Q17：这份设计最难的部分是什么？**
不是代码，是**忍住不做**。第 7.4 节列了七条“看起来该做、实测无效”的路，每一条都很诱人。真正让帧率上去的是第 16 章那前三步（降分辨率、收窗口、自动阶梯），它们加起来不到 300 行代码，而三条证伪的优化花了一周。**判断力比实现力值钱。**

---

## 附录 F：日志逐行解读

日志是这个项目最主要的“仪表盘”。这一节把最常见的四行拆开，说明每个数字该怎么读、什么范围算正常。

### F.1 `[gow-perf]`：时间分桶

```
[gow-perf] t=20.0 ee_ms=2123 gs_ms=1925 vu_ms=4060 iop_ms=359 guest_flip_hz=59.85 host_hz=59.85
```

| 字段 | 含义 | 正常范围（标题 60 fps） | 怎么用 |
|---|---|---|---|
| `t` | 启动后秒数 | — | 判断落在哪个场景阶段 |
| `ee_ms` | EE 线程忙时（5 s 累计） | 2000–2120（约 40%） | 高 ⇒ 游戏逻辑重，与渲染无关 |
| `gs_ms` | GS 前端 + 后端 + 驱动阻塞 | 1925–2177（约 40%） | 高 ⇒ 渲染或提交成本 |
| `vu_ms` | VU1 worker 忙时（含等队列） | 4000–4130（**80%**） | 最高的一环，先看它 |
| `iop_ms` | IOP 忙时 | 360–390（约 7%） | 一般不是问题 |
| `guest_flip_hz` | **真正的游戏帧率** | 59.6–60.1 | 唯一可以宣称的帧率 |
| `host_hz` | 窗口呈现频率 | 59.4–60.2 | 低于 guest 说明呈现跟不上 |

**读法**：把每个 `*_ms` 除以“本窗口的帧数”（`guest_flip_hz × 5`）得到每帧成本。1925 / 300 = 6.4 ms。**不要直接把 5 s 累计当帧时间用**，这是最常见的读错方式。

### F.2 `[gs-hw]`：批次与纹理统计

```
[gs-hw] shuffles=4000 draws=3.4M batches=20000 texDecodes=1200 texHits=4000 textures=63
```

| 字段 | 含义 | 异常信号 |
|---|---|---|
| `shuffles` | 走 shuffle 特判的精灵数 | 从 0 突然变成几千 ⇒ 进入有 16 位通道重排的场景 |
| `draws` | 提交的原始图元数（含精灵展开前） | 与 `batches` 的比例约 35:1 算正常 |
| `batches` | 实际进入 `drawOne` 的批次数 | 每帧 380–420（标题）；> 800 说明状态变化过密 |
| `texDecodes` | 纹理对象解码次数 | 与 `texHits` 比；解码占比高说明缓存命中差 |
| `texHits` | 纹理命中次数 | 远大于 `texDecodes` 是好事 |
| `textures` | 活跃纹理对象数 | 持续增长不回落 ⇒ 泄漏 |

**关键比例**：`draws / batches` 是“合批效率”。标题约 17000/420 ≈ 40，重过场约 4100000/17504 ≈ 234（因为过场图元多但状态变化少）。这个比值下降，说明状态变化变密，合批变难。

### F.3 启动那一行：渲染器实际拿到了什么

```
[gs-hw] render-target renderer ready, scale 0.80: 412x412 target, 412x360 picture (<GPU>), texture barrier native
```

| 部分 | 含义 | 为什么要看 |
|---|---|---|
| `scale 0.80` | 实际生效的内部分辨率倍数 | 怀疑“设了没生效”时第一眼看这里 |
| `412x412 target` | 渲染目标尺寸（正方形，便于 2 的幂对齐） | 与 `picture` 不同是正常的 |
| `412x360 picture` | 实际画面尺寸 | 决定了窗口贴合的高度 |
| `texture barrier native` | 有 `ARB_texture_barrier` | 显示 `glFinish` 说明没有扩展，会慢一个数量级 |

**如果 `scale` 与你设置的值不符**，检查三件事：环境变量是否被 `gow-native.boot` 覆盖（不带参数启动会读它）、是否有启动器另写了一份、是否被 `std::max(1.0f, ...)` 之类的旧 clamp 锁死（patch 59 修过这个）。

### F.4 `[gs-present]`：呈现是否停摆

```
[gs-present] no new guest frame for 2.4 s (...)
```

这行的意思是“guest 已经 2.4 秒没出帧”。它把“卡住”和“掉帧”分开：

- 出现这行 ⇒ 游戏逻辑卡住（不是渲染慢），去查 EE/VU 的同步点、SIF RPC、FINISH。
- 不出现但这行帧率低 ⇒ 渲染/提交慢，按第 7 章归因。

### F.5 v2 新增的两行

```
[gs-hw] caps: gl=4.3 vendor=intel device="Intel(R) HD Graphics 4400" maxTex=16384 uboAlign=16 barriers=texture
[gs-hw] policy: tier=B state=explicit vertex=ring32M upload=sync present=blit+fit shader=mono workpoint=0.50 (ladder=on)
```

第一行是**事实**（探测到的能力），第二行是**决策**（据此选了哪条路径）。分开打是为了在问题反馈里能立刻区分“探测错了”还是“策略选错了”——这两类的修复方式完全不同。

**反馈问题时，这两行加上 `[gow-perf]` 与 `[gs-hw]` 各一行，就能定位 80% 的“我的机器上很卡”。** 这也是第 14.5 节“一键导出诊断”要收的东西。

---

## 结语：三句话

**第一句：这份文档的核心不是“再写一个渲染器”，而是“把已有的渲染器变成会看机器的渲染器”。**
本工程的 GL 后端已经有正确的地基（顶点环、纹理仓库、shuffle、共享呈现、失败提示），缺的是“我在这块卡上该走哪条路”的判断。加 800 行策略代码，比推翻重写 4000 行语义代码便宜一个数量级，风险也低一个数量级。

**第二句：老显卡的帧率是两堵墙，不是一堵。**
`T_gs ≈ T_fixed + max(T_fill, T_submit)`。1.0×→0.5× 涨 16 帧（在付填充率的账），0.5×→0.35× 只涨 1.5 帧（已经撞在提交成本上）。所以“降分辨率”不是万能药，`0.35× 不比 0.5× 快` 就是证据。真正的工作点是两墙的交叉点，而且它必须**测出来**，不能猜。

**第三句：在这个项目里，“没有 bug”等于“两个真相永远同步”。**
三个最贵的 bug——场景全黑、整帧花屏、几何撕裂——都不是算错了，而是缓存与驱动、CPU 与 GPU、指针与容器各自记了一本账。所以这份设计的“无 bug”不是承诺，是十条可断言的不变量、一处唯一的 `UseProgram`、一套黄金帧回归、一条四跳降级链。**把纪律变成结构，是唯一可靠的办法。**

---

### 这份文档该怎么维护

文档不是写完就完了。三条约定，成本很低但能决定它三年后还有没有用：

1. **每次实测后，更新对应章节的数字，而不是只写进 research 记录。** 因为后来的人先读设计文档，再读研究记录。文档里的数字过期，比没有数字更糟。
2. **任何被推翻的判断，移进第 7.4 节的证伪清单，并在原处留一句“见 7.4”。** 不要删掉旧结论 —— 删掉之后，下一个人会重新提出同一个想法。
3. **每季度复核一次“事实基线”**：运行时 commit、补丁号、GL 版本、机器。这三样任一变化，第 3、16 章的数字就要重测。驱动更新会让“Intel 上状态缓存更慢”这条结论失效，这完全可能发生。

一份设计文档的价值不在于它写得多长，而在于**它敢不敢写“这条我试过，没用”**。本文里那些证伪记录，比任何优化方案都值钱 —— 因为它们省下的是别人已经花掉的时间。

---

*本文所有实测数字均来自本仓库已有记录（`docs/RENDER-PIPELINE-HANDOFF-2026-11-04.zh-CN.md`、`low-spec-renderer.patch` 头注释、`docs/tested-hardware.md`），未新增任何一次真机运行；数字只对记录的机台与设置有效，不可外推为“全场景 60”。全文约四万字，其中近三分之一篇幅写的是“不要做什么”与“怎么知道你做错了”——这个比例是刻意的，因为在这个工程里，选错方向的代价远大于写错代码。这也是本文标题写“帧率工程”而不是“渲染器实现”的原因：实现只是工程的一部分，判断才是主体。*

