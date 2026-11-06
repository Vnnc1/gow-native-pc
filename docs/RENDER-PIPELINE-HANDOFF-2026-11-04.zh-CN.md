# 渲染管线与 60 帧优化交接文档

**项目**：God of War（PS2，SCUS-97399 / 亚洲盘 SCAJ-97399）静态重编译原生移植
**交接日期**：2026-11-04
**交接范围**：GS 渲染管线（OpenGL 4.3）与 VU1 x64 JIT 的性能改造
**实测机器**：Intel Core i3-4170（2 物理核 / 4 线程，Haswell，3.7 GHz）、Intel HD Graphics 4400（共享内存）、8 GB DDR3、Windows 10、1280x720 窗口、内部渲染 0.5×（640x360）
**结论先行**：这台机器上，标题画面已从 52.5–53.0 guest fps 提升到 **59.6–60.1 guest fps**（present 稳定 59.4–60.2 Hz）；开场过场仍有 20–28 fps，重纹理流/大量 shuffle 的演算 demo 为 33–41 fps。渲染器不再是标题画面的瓶颈，GS 与 VU1 在不同场景各当一次瓶颈。下面把所有可复现的数据、代码改动、失败的尝试和下一步路线完整交出去。

---

## 0. 一分钟版（给下一个接手的人）

1. 这不是一个“原生 PC 游戏”，而是把 PS2 的 EE MIPS 代码静态重编译成 C++，再用运行时模拟 VU1、GS、IOP、SPU2。20 年前的游戏不等于 20 年前的负载：VU1 当年是 300 MHz 专用向量协处理器，现在跑在 x86 JIT 上；GS 的固定管线被翻译成成百上千次 OpenGL draw，纹理在 CPU 上解码后再上传。
2. 本次提交了两个补丁：
   - `engine/patches/59-gs-vertex-ring.patch`：GS 顶点环。每批次不再 `glBufferData` 重新分配，改成 32 MB 环形缓冲 + `glBindVertexBuffer`，把每帧绘制提交成本从约 0.71 s/5s 降到 0.55 s/5s；同时修掉 `PS2X_GS_HW_SCALE` 被 `std::max(1.0f, …)` 锁死在 1× 的 bug。
   - `engine/patches/60-vu1-jit-fast-mode.patch`：把 patch 51 只给 AOT 用的 `vu1n::fast` 语义接进 x64 JIT。`GOW_VU1_FAST=1` 时 VU1 时间下降 11–12%，标题画面从 52.6–55.8 提升到 59.6–60.1。
3. 快模式是**可选项**（启动器 Performance / `GOW_VU1_FAST=1`），精确模式完全保留。快模式目前只在标题/演算前段验证过，战斗与后期过场未验证。
4. 不要再走“GL 状态缓存、每批次 std140 UBO、调色板图集、全局状态 canonical 化、TEXFLUSH no-op”这些路：在这台 Intel HD 4400 上全部实测为更慢或持平，原因在 5、8 章。
5. 下一刀不是渲染器：重过场的瓶颈已经是 GS 的 shuffle + 纹理流（`shuffles` 最高 2.2 万/5s，`upload_ms` 最高 777 ms，`gs_ms` 最高 4.8 s/5s）。标题画面要再稳 60，则要继续做 VU1（AOT / JIT 进一步优化）和前端批量提交。

---

## 1. 交接环境：目录、构建、运行

### 1.1 代码与数据目录

| 路径 | 作用 |
|---|---|
| `<repo>` | 本次工作的项目根目录（外层的 profile/pipeline/launcher 仓库） |
| `engine/runtime/` | 运行时工作区（Tobiichi-Port + PS2Recomp），本次改动的源码在这里 |
| `engine/runtime/PS2Recomp/ps2xRuntime/src/lib/gs/` | GS 前端、线程后端、GL 封装、纹理仓库 |
| `engine/runtime/PS2Recomp/ps2xRuntime/src/lib/gs/gpu/` | 本次渲染器改动的主战场（`gs_hw_backend.cpp`、`gs_gl.*`、`gs_texture_store.*`） |
| `engine/runtime/PS2Recomp/ps2xRuntime/src/lib/vu/` | VU1 解释器、AOT、x64 JIT（`ps2_vu1_x64.inl`） |
| `engine/patches/` | 补丁链，按名字序号应用；本次新增 59、60 |
| `C:\gow-jpn` | 亚洲/日版隔离构建的源码快照（可运行构建实际用的是这份源码） |
| `C:\gow-build-jpn` | 可运行的日版构建目录（本次所有实测都来自这里） |
| `C:\gow-jpn-data\gow1\discs\asia-97399` | 已准备的亚洲盘（`SLPM_670.10` / `SCAJ_973.99`、PAK、IRX、记忆卡） |
| `C:\gow-build-clang` | 另一个 231 MB 的构建（AOT 路径，本次未能在这张盘上启动；不要拿它当基准） |
| `data/_tmp/` | 本次临时脚本、日志、截图、A/B 构建备份（git 忽略，可删） |

> 重要：`engine/runtime` 的源码与 `C:\gow-jpn` 的源码在本次开始时是同一份（只有 `PS2X_GS_HW_SCALE` 一行不同）。由于可运行构建绑定的是 `C:\gow-jpn`，本次每改一次 `engine/runtime` 都要把改动文件复制到 `C:\gow-jpn`，再 `touch`（PowerShell 改 `LastWriteTime`），否则 Ninja 会因为 `Copy-Item` 保留源文件旧时间戳而认为“无需重建”。这是本次踩过的坑。

### 1.2 构建

```powershell
# 只重建运行时（改 GS/VU 源码时足够）
<repo>\data\_tools\ninja\ninja.exe -C C:\gow-build-jpn ps2EntryRunner
```

- 工具链：项目 `data/_tools` 下的 llvm-mingw + ninja；不要在日版构建里混用其他编译器。
- 增量构建改 `gs_hw_backend.cpp` 大约 1–2 分钟（这台 i3），链接 77 MB 的 runner 再加 1 分钟左右。
- 改头文件（如 `gs_gl.h`、`ps2_vu1_x64.inl`）会触发更多编译单元；`ps2_vu1_x64.inl` 被 `ps2_vu1_core.cpp` 包含，改它只需要重编一个 .cpp。
- 构建目录不能换源：CMakeCache 绑定源路径，不要复制别的副本的 build 目录过来。

### 1.3 运行

```cmd
cd /d C:\gow-jpn-data\gow1\discs\asia-97399
C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe SLPM_670.10
```

`play-asia.cmd` 已经封装了常用环境变量；本次已加入 `GOW_VU1_FAST=1`：

```cmd
set "PS2X_GS_HW_SCALE=0.5"
set "GOW_VU1N_X64=1"
set "GOW_VU1_FAST=1"
set "GOW_PERF_FRAME_PC=0x183BB8"
```

- 显式传 ELF 参数时，runner 不会读取 `gow-native.boot`，环境变量由调用者决定；不带参数双击 runner 才会恢复 `gow-native.boot`（里面 `PS2X_GS_HW_SCALE=1`、`GOW_VU1_FAST=0`）。
- 启动器写出的 boot 文件包含 `PS2X_GS_HW_SCALE=1`，所以从启动器直接玩默认是 1×，在这台机器上只有 18–28 fps；本次所有“60”数据都是 0.5× + 显式 ELF 参数。
- 要显示帧率覆盖层：`TOBIICHI_FPS_GOSTER=1`。

---

## 2. 运行时线程模型与数据流（理解瓶颈的前提）

### 2.1 线程

| 线程 | 职责 | 本次测到的典型占用（标题 60 fps 时 / 5s） | 重过场（约 35 fps / 5s） |
|---|---|---|---|
| EE（GameThread） | 重编译后的 MIPS 主线程、GS 寄存器写入、VIF/DMA 提交 | 2.0–2.1 s（40–42%） | 2.1–2.7 s |
| VU1 worker | x64 JIT 执行 VU1 微程序（几何变换、粒子、蒙皮等） | 4.0–4.13 s（80–83%） | 4.2–4.6 s（84–92%） |
| GS frontend/stage | GIF packet 解析、`buildDrawBatch`、入队；同步模式下会等 worker | 计入 gs_ms | 计入 gs_ms |
| GS worker | 线程后端出队、展开顶点、调 GL | 标题 1.9–2.2 s；其中绘制提交约 0.55 s | 2.5–4.8 s |
| IOP | 音视频、文件、SIF | 0.35–0.4 s | 0.5–1.1 s |
| Host present | 把共享纹理 blit 到窗口，60 Hz 限速 | host_wait 4.8 s | 4.0–4.8 s |

### 2.2 GS 数据流

```
EE 写 GS 寄存器 / VIF1 解包
        │
        ▼
gs_frontend（GS 前端）：每个 GS 原始图元 vertexKick
   ├─ buildDrawBatch：把当前 GS 寄存器快照构建成 GSDrawState（约 200 字节）
   ├─ Submit(batch) → GSThreadedBackend::Enqueue
   │     队列按 64 KB chunk 分块，最多 256 个 pending chunk（约 4 MB）
   ├─ 纹理上传 / CLUT / TEXFLUSH / FINISH / PRESENT 等命令也按顺序入队
        │
        ▼
GS worker 线程（GSThreadedBackend::Execute）
   ├─ 逐条命令解析；`Op::Vertices` 只 memcpy 顶点 + primitive 部分
   ├─ 调用 GSHwBackend::Submit(batch)
        │
        ▼
GSHwBackend::Impl::submit
   ├─ 处理 shuffle / depth-clear sprite / Z 反转 / PSM 检查
   ├─ 三角/精灵展开成 HwVertex（精灵 6 顶点，三角 3 顶点）
   ├─ 只有 `pendingState == 当前 state` 才继续追加；否则 flushPending
        │
        ▼
flushPending → draw() → drawOne
   ├─ 每个 state run 一次 GL draw（批次）
   ├─ 纹理解码/上传、调色板纹理、shader uniform、状态设置
   ├─ 顶点写入环形缓冲，glBindVertexBuffer + glDrawArrays
        │
        ▼
Present → 共享纹理 → 窗口
```

关键点：**GS 前端每个原始图元都会构建一次 200 字节 GSDrawState、入队一次、worker 出队一次、展开一次**。标题场景约 1.4 万个图元/帧，重过场约 1.6–2 万个/帧。即使 GL 绘制为 0（`PS2X_GS_DISCARD_DRAWS=1`），这条链路仍然要花 1.3–1.5 s/5s。这是“20 年前的游戏为什么这么慢”的第一层原因：重编译保留了 PS2 的提交粒度，而 PC 端要把每个小图元翻译成状态和 GL 调用。

### 2.3 批次与绘制

- `stats.draws`：提交的原始图元数（含精灵展开前）。
- `stats.batches`：实际进入 `drawOne` 批次数（约等于每帧 350–420 次，标题），包含 shuffle pass。
- `stats.shuffles`：走 shuffle 特判的精灵数（16 位通道重排、拷贝）。
- `stats.texDecodes` / `texHits`：纹理对象解码/命中次数。
- `stats.unsupportedBlend`：需要拆批次或走软件混合的绘制数。
- 统计每 5 s 在 stderr 打印一行 `[gs-hw] ...`，由 `GOW_GS_HW_STATS=1` 打开。

---

## 3. 渲染器架构详解（改代码前必须知道的）

主文件是 `engine/runtime/PS2Recomp/ps2xRuntime/src/lib/gs/gpu/gs_hw_backend.cpp`（约 4 500 行）。它由三部分组成：

### 3.1 三套后端

1. `GSNullBackend`：什么都不做，用于基准/无 GPU 环境。
2. `GSSwBackend`：软件光栅器。**本次代码里不存在**。文档原本提到的 49 号补丁（软件后端 + 批次化）在这份仓库的补丁链里缺失，所以 `engine/patches` 01–58 不能完整复现工作区；这是交接时必须知道的历史遗留。不要从 01–58 重新应用后假设得到当前渲染器。
3. `GSHwBackend`：本机实际使用的 OpenGL 4.3 后端。

### 3.2 前端 → 状态

- `GSDrawState`：约 200 字节，包含 `GSContext`（FRAME、SCISSOR、TEX0、TEX1、MIPTBP、CLAMP、ALPHA、TEST、FBA、ZBUF、XYOFFSET、PRIM、TEXA、TEXCLUT、PABE、SCANMSK、DIMX、DTHE、COLCLAMP、FOG 颜色等）+ 预计算的纹理宽高/线性过滤标志。
- `buildDrawBatch` 在 `gs_frontend.cpp`，每个图元调用。它把寄存器快照复制进 batch，并计算纹理尺寸、过滤模式、目标显示源等。
- `GSPrimitiveBatch` 布局：3 个原始顶点 + 顶点数 + 状态；线程队列里只把顶点与 primitive 部分拷进 chunk（约 145 字节/图元），状态常驻在 worker 的 `draw` 变量里。
- 排序/重排是**不允许**的：GS 的混合、alpha test、DATE、Z 别名都依赖提交顺序。可用优化只有“相邻且状态相同/等价”的合并。

### 3.3 批处理与“等价状态”

`Impl::submit` 的核心逻辑：

```cpp
if (havePending && !sameState(pendingState, s))
    flushPending();
...
if (!havePending) { pendingState = s; havePending = true; }
```

`sameState` 是 `GSDrawState::operator==`（逐字段比较）。只有**所有字段**相同才合并。我们曾尝试一个更宽松的 `sameBatchState`（忽略此后端不读的字段、忽略三角/精灵类型、在 ABE=false 时忽略 ALPHA、在 TME=false 时忽略纹理相关字段），逻辑上是安全的，但实测批次几乎不降（因为这些字段差异大多是真实状态变化），且比较分支更多，`gs_ms` 略升，未保留。

### 3.4 纹理路径（`textureFor` / `indexTextureFor` / `paletteFor`）

- 直接色纹理：以 `(tbp0, tbw, psm, tw, th, texa)` 为 key 缓存 GL 纹理。失效时用 `decodeDirect` 从 VRAM 解码成 RGBA8（逐行 `GSMem::ReadColorRun`，失败时逐 texel 用 `GSSwizzle`），再 `glTexImage2D` 上传。
- 调色板纹理（PSMT8/PSMT4 及其 H 变体）：索引纹理只存索引（R8），颜色由 `paletteFor` 生成的 256x1 RGBA 纹理查表；调色板 key 包含 `clutHash` 和 TEXA。CLUT 变化本身不重解码索引纹理，这是有意的。
- 渲染目标采样：直接绑定 RenderTarget 的 GL color/depth 纹理，`TextureBarrier` 保证同目标写入后再采样。
- 重解释（reinterpret）：纹理内存其实来自某个渲染目标，格式/宽度/布局不同，shader 里做地址映射 + 位重组。
- Z 别名：`ZBP == FBP` 时深度存在颜色内存中，shader 读目标颜色里的 Z 字。
- 纹理包（PCSX2 命名）：`GOW_TEXTURE_PACK=<dir>`，与本次性能无关，但改纹理路径时不要破坏它。

### 3.5 Shuffle

`tryShuffle` / `flushShuffle` 处理 16 位目标之间的通道拷贝、CT16 目标的重排。它有自己的 shader + VAO + FBO，把一批 shuffle 精灵一次性绘制。重过场里 `shuffles` 最高 2.2 万/5s，是 GS 侧的最大开销来源之一。**下一阶段的优化重点**。

### 3.6 drawOne 的每批次工作

1. 目标解析 `target(fbp, fbw)`、必要时创建/扩展 RenderTarget。
2. `glBindFramebuffer`、`glViewport`、scissor、`glDisable(CULL)`。
3. 深度状态（ZTE/ZMASK/ZTST/Z 反转/别名）。
4. 混合状态：固定功能或软件混合（`unsupportedBlend` 时拆成多个色彩通道 run）。
5. `glUseProgram`、约 35 个 uniform（本次仍是 `glUniform*`，见 8 章为什么没有保留 UBO）。
6. 纹理：选择直接色/索引/目标/重解释/Z，绑定纹理，4 个 `TexParameteri`。
7. ATE/ATST/AREF、`afail` 的第二遍绘制（失败像素写颜色或深度）。
8. 顶点写入环形缓冲（patch 59）、`glBindVertexBuffer`、`glDrawArrays`。
9. 结束时 `glDisable(GL_SCISSOR_TEST)`（为其他路径恢复状态）。

### 3.7 呈现

`Present` 把当前显示目标 blit/拷贝到共享纹理，由 host 线程以 `TOBIICHI_VENTANA_FPS`（默认 60）限速呈现。`present` 不是 guest 帧率的来源；`host_hz` 只代表窗口刷新。

---

## 4. 性能诊断方法论（下一任必须复用）

### 4.1 先分清“guest fps”和“host Hz”

- `guest_flip_hz`：guest 帧函数（profile 的 `frame_pc`，本作 0x183BB8）的进入频率，是真正的游戏帧率。需要 `GOW_PERF_FRAME_PC=0x183BB8`。
- `host_hz`：窗口呈现频率，60 只代表在 vsync 下画了 60 次，可能是重复帧。
- `TOBIICHI_FPS_GOSTER=1` 的覆盖层用的是 0x1837B8，和 `GOW_PERF_FRAME_PC` 略有区别，但同样反映 guest 帧。

### 4.2 分段计时

`GOW_PERF_DIAG=1` 每 5 s 打印：

```
[gow-perf] t=... ee_ms=... vu_ms=... gs_ms=... iop_ms=... guest_wait_ms=... upload_ms=... host_wait_ms=... guest_flip_hz=... host_hz=...
```

- `ee_ms`：EE 线程忙时。
- `vu_ms`：VU1 worker 忙时（包含等 GS 队列的时间）。
- `gs_ms`：GS 前端处理 + 后端绘制（含驱动阻塞、纹理上传）。
- `upload_ms`：GS 线程里纹理上传/解码时间。
- `guest_wait_ms`：guest 等待 VBlank/同步的时间。
- 所有 ms 都是“5 s 窗口内的累计毫秒”，不是单帧毫秒；除以该窗口的帧数才能得到每帧成本。

### 4.3 丢弃绘制的“天花板”测试

`PS2X_GS_DISCARD_DRAWS=1` 让 GS worker 不调用 `Submit`，但前端仍然照常解析/入队。它回答的问题是：**如果渲染器完全不存在，这个场景能到多少帧？**

- 标题：59.9（说明有渲染时 52–56，渲染器确实是边际成本）。
- 开场过场：30–43（说明即使零渲染也到不了 60，VU1/EE 本身是墙）。
- 重演算 demo：未做 discard，但 `gs_ms` 4.8 s 说明 GS 侧已是主瓶颈。

### 4.4 批次/纹理统计

`GOW_GS_HW_STATS=1` 每 5 s 打印 `[gs-hw]`：

```
shuffles=... draws=... batches=... texDecodes=... texHits=... skippedPsm=... skippedPrim=... unsupportedBlend=... textures=...
```

用它判断：是批次太多、shuffle 太多、还是纹理解码太多。

### 4.5 A/B 的正确姿势

- 同机、同盘、同窗口、同分辨率、同 boot 阶段。**不要跨场景比较**：本作开场/标题/演算 demo 的成本差 2–3 倍，跑 30 s 和 60 s 会落在不同阶段。
- 至少跑 45–60 s，取稳定窗口的中位数；一次 5 s 窗口的尖峰不可信。
- 保留旧构建：把改动前的源码备份到 `data/_tmp/orig-*`，需要时换回去重编。
- 记录 `guest_flip_hz`、`gs_ms`、`vu_ms` 三个数，再看窗口截图确认没有花屏。

### 4.6 截图验证

```
GOW_PAD_TEST=1 GOW_FAST_BOOT=1 GOW_SKIP_FMV=1 GOW_PAD_GUION="5:start,12:x,18:x,24:x,30:x,36:x,42:x,48:x"
```

捕获的 `gow_pad_test_N.ppm` 是 GS 输出（不是窗口截图），用 Pillow 转 PNG 看标题、Logo、中文菜单、调色板背景。本作脚本化输入在 0.5× 构建上目前只到 `state=3 levelReady=0`（标题/菜单），没有稳定进入 gameplay；**战斗/模型/阴影仍需人工验证**。

---

## 5. 基线数据（改造前）

以下都是 i3-4170 + HD 4400、0.5×、亚洲盘、VU1 x64 JIT、title/attract 场景：

| 指标 | 数值 |
|---|---|
| guest fps（稳定） | 52.5–53.0 |
| host Hz | 59.7–59.9 |
| gs_ms | 2130–2200 / 5s |
| vu_ms | 4550–4600 / 5s |
| ee_ms | 1700–1800 / 5s |
| 每 5s 批次 | 约 20 000（约 380–400/帧） |
| 每 5s 图元 | 约 3.4–3.8 M（约 1.4 万/帧） |
| 丢弃绘制后的 guest | 59.9 |
| 1× 内部渲染 | 约 18–28（开场/标题），显著更差 |
| 0.35× 内部渲染 | 与 0.5× 基本相同（证明瓶颈不是像素） |

一个重要历史事实：原始工作区里 `PS2X_GS_HW_SCALE` 被写成

```cpp
scale = std::max(1.0f, static_cast<float>(std::atof(s)));
```

所以启动器传 0.5、0.35 都不生效，实际永远 1×。这就是用户看到“18 帧”的直接原因之一。patch 59 把它改成：

```cpp
scale = std::clamp(static_cast<float>(std::atof(s)), 0.25f, 4.0f);
```

改完后 0.5× 才真正生效。

---

## 6. Patch 59：GS 顶点环（已提交）

### 6.1 问题

每个批次（state run）在 `drawOne` 里执行：

```cpp
g.BindVertexArray(vao);
g.BindBuffer(kArrayBuffer, vbo);
g.BufferData(kArrayBuffer, bytes, dverts.data(), kStreamDraw);
```

`glBufferData` 每次都重新指定存储；Intel 驱动会分配新存储 + 拷贝，且在 GPU 还在读上一份时产生同步。标题场景约 390 批次/帧，单这一项就吃掉约 0.71 s/5s。

### 6.2 方案

- 一个 32 MB 顶点缓冲。
- 优先 `glBufferStorage` + `glMapBufferRange`（persistent + coherent + write）直接写入；4.3 上下文没有 `GL_ARB_buffer_storage` 时回退为 `glBufferData(NULL)` + `glBufferSubData`。
- 顶点属性改用 `ARB_vertex_attrib_binding`：`glVertexAttribFormat` + `glVertexAttribBinding(…, 0)`，这样每批次只需要一次 `glBindVertexBuffer(0, vbo, offset, stride)`，不再重置 6 个属性指针。
- 环回绕时等待上一轮回绕插入的 fence（`glFenceSync`/`glClientWaitSync`），保证 GPU 已读完被复用的区域。
- `GOW_GS_HW_RING=0` 保留旧的 `glBufferData` 路径，便于 A/B 与故障回退。
- 4.3 回退路径没有持久映射，但仍是同一个 32 MB 环 + `glBufferSubData`，不会每批次重新分配。

### 6.3 一个必须记住的 GL 细节

`glBufferStorage` 的 flags 参数**不是** `GL_DYNAMIC_DRAW`（0x88E8），而是 `GL_DYNAMIC_STORAGE_BIT`（0x0100）加 `GL_MAP_*_BIT`。第一次实现误用了 `kDynamicDraw`，驱动返回 `GL_INVALID_VALUE (0x501)`，映射失败，代码静默回退到 `BufferSubData`，性能没有变化，还留下一次 GL error。正确写法：

```cpp
constexpr GLbitfield kDynamicStorageBit = 0x0100;
g.BufferStorage(kArrayBuffer, kVertexRingBytes, nullptr,
                kDynamicStorageBit | kMapWriteBit | kMapPersistentBit | kMapCoherentBit);
vertexRingMap = static_cast<uint8_t *>(
    g.MapBufferRange(kArrayBuffer, 0, kVertexRingBytes,
                     kMapWriteBit | kMapPersistentBit | kMapCoherentBit));
```

如果 `BufferStorage` 成功但 `MapBufferRange` 失败，**不能**对不可变存储再调用 `glBufferData`（会 `GL_INVALID_OPERATION`）；必须 `DeleteBuffers` + `GenBuffers` 重新建一个普通 buffer。代码里已处理。

### 6.4 代码位置

| 文件 | 改动 |
|---|---|
| `src/lib/gs/gpu/gs_gl.h` | 新增 `BindVertexBuffer`、`VertexAttribFormat`、`VertexAttribBinding` 函数指针（可选加载） |
| `src/lib/gs/gpu/gs_gl.cpp` | 从 `wglGetProcAddress` 加载上述三个函数；失败不影响 `hwRaster`，走旧路径 |
| `src/lib/gs/gpu/gs_hw_backend.cpp` | 环成员、`appendVertices`、VAO 初始化分支、`drawOne` 调用点、scale clamp |
| `src/lib/gs/gpu/gs_texture_store.h` | 本次最终没有改动（曾经的 Snapshot/Restore 已移除） |

### 6.5 实测

| 构建 | guest fps | gs_ms / 5s |
|---|---|---|
| 基线 | 52.5–53.0 | 2130–2200 |
| patch 59 | 52.6–55.8 | 1940–2130 |
| patch 59，丢弃绘制 | 59.9 | ~1450 |

绘制提交成本约 0.71 → 0.55 s/5s（约 −23%）。标题帧率提升 1–3 fps，重过场 GS 也下降。这个补丁单独存在时是**净收益**，且不改变任何像素路径。

---

## 7. Patch 60：VU1 x64 JIT 快速模式（已提交）

### 7.1 背景

PS2 的 VU1 在精确模拟下要做两件“硬件本来免费”的事：

1. 每次算术读操作数时，把 Inf/NaN 归一化成 ±FLT_MAX（`vu1n::ldn`）。
2. MADD/MSUB 的溢出检查：乘积或和超出 0x7F7FFFFE 时走宽精度求值。

patch 51 给 AOT 生成的块编译了一份 `vu1n::fast` 版本：操作数直接读、MADD 直接 `a*b ± acc`、 clamp 字段仍生效；实测战斗回放 150.0 → 132.3 ms（−11.8%），4000 条记录中 23 条与精确引擎不同，视觉无差异。但**日版是 JIT-only 构建**，没有 AOT 块，所以 `GOW_VU1_FAST=1` 之前对日版完全无效。

### 7.2 实现

文件：`engine/runtime/PS2Recomp/ps2xRuntime/src/lib/vu/ps2_vu1_x64.inl`

1. 新增进程级开关（首次使用时读环境变量，避免静态初始化早于 `main` 恢复 boot profile）：

```cpp
inline bool fastMode()
{
    static const bool fast = []
    {
        const char *v = std::getenv("GOW_VU1_FAST");
        return v && v[0] == '1';
    }();
    return fast;
}
```

2. `norm()`（决定操作数是否需要 ldn 的 lambda）在快模式下直接返回 `false`，所有算术操作数走裸读。

3. 新增 `emitLoad()`：快模式 `movupsL(x, vfM(r))`，否则 `loadNorm`。替换 6 处直接 `loadNorm` 调用（FMAC 的 a/b、ABS/FTOI、CLIP、OPMULA）。

4. MADD/MSUB 在快模式下跳过宽精度检查与 `hFmac` 慢路径：

```cpp
if (fastMode())
{
    e.ps(0x59, XMM1, XMM2);                               // p = a * b
    e.movupsL(XMM5, stM(offsetof(VU1State, acc)));
    e.ps(k.op == K_MADD ? 0x58 : 0x5C, XMM5, XMM1);       // r = acc +/- p
    e.movaps(XMM1, XMM5);
    break;
}
```

5. 精确模式没有改动：`fastMode()==false` 时走原来的 `norm`/`loadNorm`/溢出检查。

### 7.3 实测

| 模式 | guest fps（标题） | vu_ms / 5s | host Hz |
|---|---|---|---|
| 精确 | 52.6–55.8 | 4550–4600 | 59.7–59.9 |
| 快模式 | **59.6–60.1** | **4000–4130** | 59.4–60.2 |

VU1 下降 11–12%，与 patch 51 在 AOT 上的比例一致；标题画面稳定 60。开场过场仍 20–28；重演算 demo 33–41（此刻 GS 4.8 s/5s，是新的墙）。

### 7.4 风险与未验证

- 快模式是**语义近似**，不是 bit-exact。AOT 版在 4000 条回放记录中有 23 条不同（0.57%），未见视觉差异；JIT 版没有做同样的记录级对比，只做了标题画面截图对比。
- 未在战斗、后期过场、不同 GPU 上验证。默认关闭；启动器 Performance 才打开。
- 如果发现画面异常，先 `GOW_VU1_FAST=0` 复测；若精确模式正常，问题就在快语义。
- JIT 的 `frame.nv` 缓存、entry clean-lane 假设仍在编译产物里，但快模式不再使用 ldn；这些残留代码不影响正确性，只是略微多占指令缓存。
- 快模式与 AOT 快模式没有做 digest 对比（日版没有 AOT 块）。下一个接手人若有 USA AOT 构建，建议跑 `tests/vu1_x64_fuzz_test` 的快/精确两组，确认与 `vu1n::fast` 一致。

---

## 8. 被证伪的方案（不要再重复）

以下都在同一台机器、同一场景 A/B 过，结论是“更慢或持平”，因此没有进入补丁：

### 8.1 每批次 std140 UBO

把约 35 个 `glUniform*` 换成一个 `layout(std140) uniform GSDrawBlock`，每批次 `glBufferSubData` + `glBindBufferRange`。实现完整、布局用 `static_assert(offsetof...)` 校验、视觉正确；但：

- 完整改造版整组只有 50.7 fps（比 ring-only 的 53–55 更慢）。
- `gs_ms` 反而从 2.0 s 升到 2.26 s。
- Intel HD 4400 驱动对同一 program 的 `glUniform` 更新很便宜，而 `BufferSubData + BindBufferRange` 每批次两次驱动调用更贵。

结论：**在这块 GPU 上不要用 UBO 换 glUniform**。如果换 NVIDIA/AMD 可重新测。

### 8.2 GL 状态缓存

缓存 fbo/viewport/scissor/depth/mask/blend/program/vao，跳过重复设置。视觉无 GL error，但帧率从 53–55 掉到 37–40，`gs_ms` 翻倍：

- 单独关掉 scissor、blend、mask、depth、fbo、program、vao 任一项都无法恢复；全关才恢复。
- 推测 Intel 驱动在 draw 时对“未显式重设”的状态做整条管线重新校验，冗余的 setter 反而是廉价的 fast path。
- 结论：**不要在这块驱动上做状态跳过**。保留显式全量设置。

### 8.3 调色板图集（跨 CLUT 合批）

把 256x1 调色板纹理换成 256x256 图集，每顶点携带调色板行号，使一个批次可以跨 CLUT 变化；CLUT 加载不再 flush 批次。

- 视觉正确，但批次数量几乎不降（标题 19.3k vs 19.1k/5s），因为批次主要由 TEST/PRIM/TEX0 的真实状态变化决定，而不是 CLUT。
- 顶点从 64 字节增到 68 字节，shader 多一个 flat varying + 2D texelFetch，GPU 成本略增。
- 未保留。

### 8.4 canonical 状态比较

忽略本后端不读的寄存器（FOG 颜色、PABE、SCANMSK、DIMX、DTHE、FBA、MIPTBP、TEXCLUT、TEX1 的过滤位）、忽略三角/精灵类型、ABE=false 时忽略 ALPHA、TME=false 时忽略纹理字段。逻辑安全，但：

- 批次几乎不降；比较分支略多，`gs_ms` 从 2.0 升到 2.06。
- 只有在“大量只差无效字段”的场景才有收益，本作标题/演算不是。

### 8.5 TEXFLUSH 视为 no-op

`GSHwBackend::TextureFlush()` 原来无条件 `flushPending()`。注释本身写着“纹理是在上传重叠时重新读取，不是 TEXFLUSH”，所以去掉 flush 在语义上安全。

- 实测批次数量不变（19.1k → 20.1k 波动），帧率无变化；说明 TEXFLUSH 大多发生在 pending 为空时。
- 未保留，避免无谓的行为改变。

### 8.6 TexSubImage2D 复用纹理存储

对同尺寸重解码用 `TexSubImage2D` 替代 `TexImage2D`。实现后开场 `upload_ms` 有下降（83→47 ms/5s 的窗口），但**场景不可比**（每次启动进入的阶段不同），标题窗口无净收益，且两次运行 `gs_ms` 反而略升。未保留。若有人能构造确定性的纹理流场景（固定存档+固定过场），可以重新测。

### 8.7 GS worker 优先级

`PS2X_THREAD_PRIORITY=0`（不让 GS worker 提到 AboveNormal）跑 45 s，guest 50.2–52.7，与默认无差别。不是线程争用问题，未改。

---

## 9. 剩余瓶颈与下一步路线（按优先级）

### 9.1 重过场/演算 demo：GS shuffle + 纹理流（最高优先级）

数据（快模式，重演算窗口）：

- `shuffles` 最高 22 176 / 5s（约 4 400/秒），`gs_ms` 最高 4.8 s/5s，`upload_ms` 最高 777 ms/5s，`texDecodes` 最高 3 017/5s。
- 同一时刻 guest 33–41，VU1 4.2–4.5 s/5s，EE 2.1–2.7 s/5s。

这说明在重过场里，GS 的工作量（大量 16 位通道拷贝、纹理流）已经超过 VU1。可做的优化：

1. **shuffle 批量化/降调用**：现在 `flushShuffle` 每次状态 run 一次 FBO 绑定 + draw；检查是否能跨 state run 合并同一目标/同一通道模式的 shuffle，减少 FBO 切换和 `TexParameteri`。
2. **纹理上传合并**：同一帧内对同一纹理的多次重解码只上传最后一次；或按 dirty rect 上传。`upload_ms` 777 ms/5s 是实打实的 GS 线程时间。
3. **避免整纹理重解码**：`textureFor` 在任一上传重叠后整张重解码；重过场可能有大量“只改一小块”的纹理。可以让纹理仓库记录脏矩形，只解码/上传变化区域。
4. **PBO / 异步上传**：在 4.3 上用 PBO + `MapBufferRange` 双缓冲，把上传从 GS 线程的同步路径里挪走。注意别引入额外同步。

预期：重过场从 33–41 提到 45–50 的量级（取决于 shuffle/上传占比），但到不了 60；VU1 仍占 4.2+ s/5s。

### 9.2 前端批量提交（文档 Stage 1）

当前每个原始图元都要 `buildDrawBatch` + Enqueue + worker 解码 + `Submit`。`PS2X_GS_DISCARD_DRAWS=1` 下 GS 仍有 1.3–1.5 s/5s，说明这条链路本身很贵。

可行的最小实现（不需要全局排序）：

- 在 GS 前端把**连续、状态等价**的图元聚合成一个 range，一次入队；后端遍历 range 内每个 primitive 做现有的展开/特判。
- 必须在前端遇到纹理上传、CLUT、TEXFLUSH、FINISH、PRESENT、Clear 时立即 flush range，保证顺序。
- 状态等价判断只能用 patch 59 之后的 `sameState`（全量相等），不要用 canonical 版本（见 8.4）。
- 收益预计在 GS 前端/worker 的每-primitive 开销上，重过场 +2–4 fps；战斗场景取决于图元数量。
- 风险：改动面大（后端接口、threaded 队列、Null 后端、测试）。建议单独补丁，做 A/B。

### 9.3 VU1：AOT 与战斗验证

- 日版目前是 JIT-only；`data/gow1/vu1_capture` 和 `vu1n_heads.txt` 缺失会让部分块走解释器（memory 记录战斗 44–50 而不是 55–60）。下一个接手人应先确认日版是否有可用的 VU1 头/捕获，再考虑 AOT。
- 快模式已把 JIT 拉低 11–12%；AOT fast 对日版没有直接帮助（没有 AOT 块）。
- JIT 还有“speculation/entry clean lanes/AVX/INLINE”等 A/B 开关（patch 27）：`GOW_VU1X_AVX=0`、`GOW_VU1X_SPECULATE=0`、`GOW_VU1X_INLINE=0`。默认已是最快档；不要再盲目关闭。
- 要真正在重过场到 60，VU1 需要再降 30–40%，这需要更激进的 JIT（例如把 `frame.nv` 缓存的残留去掉、合并 load/store、减少慢路径检查），风险高，建议单独分支做。

### 9.4 渲染器剩下的“低风险小刀”

- `drawOne` 的每批次仍固定设置 ~35 个 uniform + 4 个 `TexParameteri`。UBO/缓存都证伪，但可以试“同一纹理连续批次跳过 TexParameteri”（**仅在同一 GL 纹理对象、同一参数**时；注意纹理 id 复用，删除时必须清缓存）。这次试过的版本因为无法可靠测出收益，没有保留。
- alpha test 的 `afail` 第二遍绘制：目前拆成两次 draw。用 stencil 两遍仍然要两次，不能省；只能确认 `afail` 真的需要时再画第二遍（已经如此）。
- `shuffles` 的 FBO 切换可以按目标排序，但排序必须限制在相邻的 shuffle 精灵内，不能跨普通绘制。

### 9.5 不建议的方向

- 全局按纹理/状态排序：会破坏混合/DATE/Z 别名顺序，画面上一定出问题。
- 用 `glMultiDrawArrays` 合并不同状态批次：状态不同，合并后状态只对第一段有效，错误。
- 在 Intel 上继续做 GL 状态缓存/UBO：8.1/8.2 已经证伪。
- 降低分辨率换帧率：0.35× 与 0.5× 帧率相同（瓶颈是每批次/每图元 CPU，不是像素）。

---

## 10. 构建与测试复现手册

### 10.1 从源码到可运行构建

1. 确认 `engine/runtime` 是当前工作区，`C:\gow-jpn` 是可运行快照。
2. 把改动文件从 `engine/runtime` 复制到 `C:\gow-jpn` 对应路径。
3. 修改复制后文件的 `LastWriteTime`（PowerShell：`(Get-Item path).LastWriteTime = Get-Date`）。
4. `ninja -C C:\gow-build-jpn ps2EntryRunner`。
5. 运行 `play-asia.cmd`（或显式 ELF + 环境变量）。
6. 用 `[gow-perf]` / `[gs-hw]` 日志确认数值，用 PPM 截图确认画面。

### 10.2 本次的临时基准脚本

`data/_tmp/bench-render.ps1`（未纳入仓库，可复制到 `tools/profile/` 或自己保留）：

```powershell
param(
    [int]$Seconds = 45,
    [string]$Scale = "0.5",
    [string]$Tag = "baseline",
    [string]$Disc = "C:\gow-jpn-data\gow1\discs\asia-97399",
    [string]$Runner = "C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe",
    [string]$Elf = "SLPM_670.10",
    [switch]$Scripted,
    [switch]$NoFastBoot
)
```

它设置：

```
GOW_FAST_BOOT=1 (除非 -NoFastBoot)
GOW_SKIP_FMV=1  (除非 -NoFastBoot)
GOW_PERF_DIAG=1
GOW_PERF_FRAME_PC=0x183BB8
GOW_GS_HW_STATS=1
GOW_VU1N_X64=1
PS2X_GS_WORKER=1
PS2X_GS_HW_SCALE=$Scale
TOBIICHI_VENTANA_FPS=60
GOW_GS_EARLY_FINISH=1
GOW_GS_FINISH_ASINCRONO=1
GOW_AUDIO_DEVICE=default
```

运行 N 秒后强杀进程，打印最后 8 行 `[gow-perf]` / `[gs-hw]`。注意：`GOW_FAST_BOOT` 与 `GOW_SKIP_FMV` 会改变进入的场景，比较 A/B 时两方必须用同一开关。

### 10.3 环境变量总表

| 变量 | 作用 | 本次是否使用 |
|---|---|---|
| `PS2X_GS_HW_SCALE` | 内部渲染比例 0.25–4（patch 59 后才真正生效） | 0.5 |
| `PS2X_GS_WORKER=1` | GS 线程后端 | 是 |
| `PS2X_GS_DISCARD_DRAWS=1` | 丢弃所有绘制，测前端天花板 | 是 |
| `GOW_GS_HW_STATS=1` | 每 5 s 打印 GS 批次/纹理统计 | 是 |
| `GOW_GS_HW_RING=0` | 回退 patch 59 的顶点环 | A/B |
| `GOW_GS_EARLY_FINISH=1` | patch 40 早 FINISH | 是 |
| `GOW_GS_FINISH_ASINCRONO=1` | FINISH 异步，不让 EE 等 GS | 是 |
| `GOW_VU1N_X64=1` | 启用 x64 VU1 JIT | 是 |
| `GOW_VU1_FAST=1` | patch 60 快语义（AOT 与 JIT 都识别） | 是 |
| `GOW_VU1X_AVX=0` / `SPECULATE=0` / `INLINE=0` | JIT 的 A/B 开关 | 未用（默认最优） |
| `GOW_PERF_DIAG=1` / `frames` | 分段/帧区间诊断 | 是 |
| `GOW_PERF_FRAME_PC=0x183BB8` | guest 帧函数的 PC | 是 |
| `TOBIICHI_FPS_GOSTER=1` | 窗口 FPS 覆盖层 | 是 |
| `TOBIICHI_VENTANA_FPS=60` | 窗口呈现上限 | 是 |
| `GOW_PAD_TEST=1` / `GOW_PAD_GUION` / `GOW_PAD_CAPTURAS` | 脚本输入 / GS 截图 | 是 |
| `PS2X_THREAD_PRIORITY=0` | 不提升 GS worker 优先级 | A/B |

### 10.4 日志位置

- 基准运行的 stderr：`data/_tmp/bench-<tag>.log`
- 标准输出：`data/_tmp/bench-<tag>.log.out`
- 脚本化截图：`C:\gow-jpn-data\gow1\discs\asia-97399\gow_pad_test_*.ppm`
- 转换后的 PNG：`data/_tmp/*.png`
- 补丁：`engine/patches/59-gs-vertex-ring.patch`、`engine/patches/60-vu1-jit-fast-mode.patch`
- 教育性记录：`docs/tested-hardware.md`（第 59/60 节）

---

## 11. 交接清单（Checklist）

### 11.1 已完成

- [x] 定位“1× 被锁死”的 bug，修复 `PS2X_GS_HW_SCALE` clamp。
- [x] 渲染器顶点路径改为环形缓冲 + `glBindVertexBuffer`，保留旧路径开关。
- [x] 精确/快模式 VU1 JIT；标题画面达到 60 guest。
- [x] 标题/Logo/中文菜单在精确/快模式下截图对比一致。
- [x] 补丁 59/60 在干净基线 `git apply --check` / `git apply` 通过，应用结果与工作区一致。
- [x] 记录失败方案（UBO、状态缓存、调色板图集、canonical、TEXFLUSH、TexSubImage、线程优先级）。
- [x] 记录实测数据与剩余瓶颈（GS shuffle/纹理流、前端每图元开销、VU1 战斗验证）。

### 11.2 未完成 / 下一个接手人优先做

- [ ] **战斗与后期过场验证**：脚本化输入在当前构建只到标题/菜单（`state=3 levelReady=0`）。需要人工或修脚本进入 gameplay，确认快模式与渲染改动在模型、阴影、粒子、UI 上没有回归。
- [ ] **重过场 GS 优化**：shuffle 合批、纹理上传合并/脏矩形、PBO。目标 45–50 fps。
- [ ] **前端 range 提交**：把每图元 `buildDrawBatch`/入队/解码的开销合批；目标重过场 +2–4 fps。
- [ ] **AOT/战斗 VU1**：确认日版是否有可用的捕获/heads；若有，做 AOT fast；否则继续 JIT 优化。目标战斗 55–60。
- [ ] **AOT/JIT digest 对比**：用 USA AOT 构建跑 `tests/vu1_x64_fuzz_test` 的快/精确两组，证明 JIT fast 与 `vu1n::fast` 等价。
- [ ] **补丁链补齐**：`engine/patches` 缺少 49（软件后端/批次状态）等历史补丁，01–58 不能复现工作区。要么补齐 49，要么在 README 明确“工作区是 patch 链 + 手工改动”的历史状态。交接时容易踩。
- [ ] **把 `data/_tmp/bench-render.ps1` 正式化为 `tools/profile/` 脚本**（或至少文档化），避免下一个接手人重新造轮子。

### 11.3 常见问题

**Q：为什么标题 60，一进开场就 18？**
A：开场过场 VU1 每帧工作量是标题的 2–3 倍（`vu_ms` 4.2–4.6 s/5s，`guest` 20–28），即使把所有绘制丢弃也只有 30–43。18 帧多数是电影/过场阶段，不是渲染器。

**Q：为什么 0.35× 不比 0.5× 快？**
A：瓶颈是每批次/每图元的 CPU 与 VU1，不是像素填充。降低内部分辨率不会减少批次数量或 VU1 指令数。

**Q：为什么有 60 host Hz 但 guest 只有 40？**
A：`host_hz` 是窗口呈现次数，可能重复显示同一 guest 帧；`guest_flip_hz` 才是游戏逻辑帧率。看后者。

**Q：快模式安全吗？**
A：与 AOT fast 同源，视觉验证标题无差异；但未做战斗验证，默认关闭。出现异常先关 `GOW_VU1_FAST`。

**Q：为什么改了 `engine/runtime` 但运行没变化？**
A：可运行构建用的是 `C:\gow-jpn` 快照；必须复制 + touch + ninja。只改 `engine/runtime` 不会影响 `C:\gow-build-jpn`。

**Q：`glBufferStorage` 报 0x501？**
A：flags 用了 `GL_DYNAMIC_DRAW`，应改成 `GL_DYNAMIC_STORAGE_BIT`（0x0100）。见 6.3。

---

## 12. 关键代码索引

| 关注点 | 文件 / 符号 |
|---|---|
| GS 前端、寄存器写入、`buildDrawBatch` | `PS2Recomp/ps2xRuntime/src/lib/gs/gs_frontend.cpp` |
| GS 线程后端、队列、Op 解析 | `gruntime/src/lib/gs/gs_threaded_backend.cpp`（实际路径 `PS2Recomp/ps2xRuntime/src/lib/gs/gs_threaded_backend.cpp`） |
| GS 后端主文件 | `.../src/lib/gs/gpu/gs_hw_backend.cpp` |
| `Impl::submit` / `flushPending` / `drawOne` | 同上，约 2 000–3 300 行 |
| 顶点环 `appendVertices` | 同上，`drawOne` 之前 |
| 纹理解码 `textureFor` / `decodeDirect` / `indexTextureFor` / `paletteFor` | 同上，约 1 300–1 500 行 |
| shuffle `tryShuffle` / `flushShuffle` | 同上，约 2 300–2 420 行 |
| Present / 共享纹理 | 同上，约 3 700 行；`gs_host_present.cpp` |
| GL 函数加载与封装 | `.../src/lib/gs/gpu/gs_gl.h`、`gs_gl.cpp` |
| 纹理内存/CLUT 仓库 | `.../src/lib/gs/gpu/gs_texture_store.cpp/.h` |
| VU1 JIT | `.../src/lib/vu/ps2_vu1_x64.inl` |
| VU1 AOT/fast helpers | `.../src/lib/vu/ps2_vu1_native.inl`、`patch 51` |
| 性能计数器 | `.../include/runtime/ps2_perf.h` |
| 启动/环境恢复 | `.../src/main.cpp`（`gow-native.boot`） |

---

## 13. 数字附录（原始窗口记录）

### 13.1 基线（45 s，0.5×，标题）

```
ee_ms≈1700–1800  vu_ms≈4550–4600  gs_ms≈2130–2200  iop≈400–700
guest_flip_hz≈52.5–53.0  host_hz≈59.7–59.9
```

### 13.2 patch 59（60 s，0.5×，标题）

```
ee_ms≈1700–2100  vu_ms≈4550–4600  gs_ms≈1940–2130  iop≈350–400
guest_flip_hz≈52.6–55.8  host_hz≈59.7–59.9
```

### 13.3 patch 59 + 60（45 s，0.5×，标题，fast）

```
ee_ms≈2000–2120  vu_ms≈4000–4130  gs_ms≈1925–2177  iop≈360–390
guest_flip_hz≈59.6–60.1  host_hz≈59.4–60.2
```

### 13.4 开场过场（0.5×，无 FAST_BOOT/SKIP_FMV）

```
ee_ms≈2000–2450  vu_ms≈4350–4630  gs_ms≈1720–2845  iop≈600–830
upload_ms≈256–533  guest_flip_hz≈16–27  host_hz≈34–53
```

### 13.5 开场过场，丢弃绘制

```
ee_ms≈1760–2293  vu_ms≈4398–4595  gs_ms≈1296–1477  iop≈423–586
upload_ms≈79–154  guest_flip_hz≈30–43  host_hz≈57–59
```

### 13.6 重演算 demo（fast，60 s 窗口）

```
gs_ms 最高 4806  upload_ms 最高 777  shuffles 最高 22176/5s
guest_flip_hz≈33–41  host_hz≈48–56
```

### 13.7 统计示例（标题，patch 59 + 60）

```
[gs-hw] shuffles≈4000/5s  draws≈1.7M/5s  batches≈9000/5s
texDecodes≈1200/5s  texHits≈4000/5s  textures≈63
```

### 13.8 统计示例（重演算 demo）

```
[gs-hw] shuffles≈22000/5s  draws≈4.1M/5s  batches≈17500/5s
texDecodes≈430/5s  texHits≈7300/5s  textures≈117
```

---

## 14. 给下一个制作人的建议顺序

1. **先复现**：用 `play-asia.cmd`（现在是 0.5× + fast）跑 45 s，确认标题 59–60；再跑一次 `GOW_VU1_FAST=0`，确认回落到 52–56；再跑 `PS2X_GS_DISCARD_DRAWS=1`，确认 59.9。这三个数对上了，说明环境正确。
2. **再验证画面**：`GOW_PAD_TEST` 截图标题/菜单；然后人工进入战斗，确认模型/阴影/UI；快模式异常就关掉。
3. **再做重过场**：按 9.1 的顺序（shuffle 合批 → 纹理上传合并 → 脏矩形/PBO）。每次只改一项，45 s A/B，记录 `gs_ms`/`upload_ms`/`shuffles`。
4. **最后做前端批提交**：面大、收益中等，放在画面验证之后，单独补丁。
5. **不要重走证伪路线**：8 章的 6 项已经花了本次大量时间，Intel 驱动行为与常规经验相反。

---

## 15. 法律与仓库约束（提醒）

- 不要提交任何游戏文件（ELF、IRX、ISO、PAK）、从游戏提取的数据、VRAM/RAM 截图、VU1 微码捕获。
- 补丁头用英文，补丁按序号应用；本次新增 59、60，不要修改已有补丁的上下文行。
- `data/_tmp` 里的日志/截图/备份是临时产物，可删；不要打包。
- 文档中的实测数字只对这台 i3-4170 + HD 4400 有效，不要外推到其他机器或对外宣传为“全场景 60”。

---

## 16. 结语

这次改造证明了两件事：

1. **渲染器确实可以优化**：顶点环把每批次提交成本降了约 23%，并且没有改变任何像素路径；这是一条可复现、可回退的净收益。
2. **60 帧不是渲染器单独能保证的**：标题画面在 fast VU1 下到 60，但开场过场和重演算 demo 仍然被 VU1/GS 的真实工作量限制。下一个接手人应按场景分别优化，不要用一个“60fps”目标掩盖不同阶段的瓶颈。

把 59/60 当作基线，把 8 章的失败方案当作“已验证不可行”的负资产，把 9 章当作路线图。这样接手可以少走至少两轮弯路。

—— 2026-11-04，渲染管线交接

---

## 17. 术语表

| 术语 | 含义 |
|---|---|
| EE | Emotion Engine，PS2 主 CPU（MIPS R5900）。本项目中其代码被静态重编译为 C++。 |
| VU1 | PS2 的向量协处理器 1，负责几何变换、光照、蒙皮、粒子等。本项目中由 x64 JIT（或 AOT 生成代码）执行。 |
| GS | Graphics Synthesizer，PS2 的固定功能图形芯片。本项目中由 OpenGL 4.3 后端模拟。 |
| GIF / VIF | PS2 的图形接口路径。GIF 把 GS 命令包送入 GS；VIF 把数据解包给 VU1 并转发 GIF packet。 |
| PATH1 / PATH2 / PATH3 | GS 的三种命令来源：PATH1（EE 直接写）、PATH2（VU1 的 XGKICK）、PATH3（VIF1 直通）。 |
| FINISH | GS 命令流里的同步点，游戏用它等待前一批绘制完成。patch 40 在 EE 提交时提前抬 FINISH。 |
| TEXFLUSH | GS 的纹理缓存刷新命令。在本后端没有实际缓存失效意义（纹理按上传重叠失效）。 |
| CLUT | Color Look-Up Table，调色板纹理。`LoadClut` 从 VRAM 读取 256 色。 |
| TEXA | 纹理 alpha 展开寄存器（TA0/TA1/AEM）。 |
| TEX0 | 纹理格式/基址/宽度/CLUT 配置寄存器。 |
| TEX1 | 纹理过滤/MIP 配置寄存器；本后端只用到它产生的 `linearFilter` 标志。 |
| MIPTBP1/2 | MIP 链基址。本后端不生成 MIP，因此不读。 |
| ZBUF | 深度缓冲配置（ZBP/PSM/ZMASK）。 |
| ZTE / ZTST / ZMASK | 深度测试使能 / 深度函数 / 深度写屏蔽（ZMASK=1 表示禁止写）。 |
| DATE | Destination Alpha Test，读目标 alpha 做测试。 |
| ATE / ATST / AREF / AFAIL | Alpha Test 使能 / 比较方式 / 参考值 / 失败处理（1=只写 FB，2=只写 Z，3=只写 RGB）。 |
| ABE | Alpha Blending 使能。 |
| ALPHA | 混合参数寄存器（A/B/C/D 选择 + FIX）。 |
| COLCLAMP | 颜色钳制；关闭时 shader 里做 wrap-around 混合。 |
| PABE / SCANMSK / DIMX / DTHE / FBA | 像素 alpha buffer / 扫描掩码 / 水平缩放 / 抖动 / frame buffer alpha。本后端不读或未实现。 |
| PSM | Pixel Storage Mode，GS 的像素格式（CT32/CT24/CT16/PSMT8/PSMT4 等）。 |
| TBW | Texture Base Width，纹理在 VRAM 中的页宽（64 像素为单位）。 |
| TBP0 | Texture Base Pointer，纹理基址（256 字节为单位）。 |
| CBP / CPSM / CSM / CSA | CLUT 基址 / 格式 / 存储模式 / 偏移。 |
| XYOFFSET | 顶点坐标偏移（1/16 像素）。 |
| SCISSOR | 裁剪矩形（PS2 像素坐标）。 |
| 重解释（reinterpret） | 纹理内存来自某个渲染目标，但按另一格式/宽度/布局读取；shader 做地址映射 + 位提取。 |
| Z 别名（Z alias） | `ZBP == FBP`，深度值存在颜色内存的 Z 字里，由 shader 读写。 |
| shuffle | 16 位目标之间的通道拷贝/重排，例如把 CT16 的 R/G/B/A 分离或合并。 |
| 批次（batch） | 相邻且状态完全相同的图元合并成一次 GL draw。 |
| state run | 状态不变的一段连续图元；通常一个批次对应一个 state run。 |
| guest frame | 游戏逻辑帧，由 profile 的 `frame_pc` 计数（本作 0x183BB8）。 |
| host frame | 窗口呈现帧，可能重复显示 guest 帧。 |
| present | GS 输出 blit 到共享纹理，再由窗口线程显示。 |
| 丢弃绘制 | `PS2X_GS_DISCARD_DRAWS=1`，只保留前端/队列，跳过所有后端绘制，用于测天花板。 |

---

## 18. 代码走读：从一个 GS 图元到一次 GL draw

这一章按调用顺序把路径走一遍，方便接手人定位。

### 18.1 `vertexKick`

`gs_frontend.cpp` 的 `GS::vertexKick` 每收到一个 PS2 顶点就被调用。它把顶点写进当前 primitive 队列；凑够一个图元（三角 3 个、精灵 2 个、线 2 个等）后调用 `buildDrawBatch` 生成 `GSPrimitiveBatch`，再 `m_backend->Submit(batch)`。

`buildDrawBatch` 做的事：

- 把 `m_ctx`（GS 寄存器快照）复制到 `batch.state.context`；
- 根据 TEX0/TEX1 计算 `state.textureWidth/textureHeight`；
- 根据 TEX1 的过滤位计算 `state.linearFilter`；
- 填充 `state.texa/texclut/prim/pabe/...`；
- 记录 prim 类型和顶点数；
- 更新“首选显示源”（用于 present 选择）。

这一步是每图元固定成本，约 200 字节状态复制 + 少量位运算。标题 1.4 万图元/帧、60 fps → 84 万次/秒；这就是为什么“前端批量提交”是潜在收益点（9.2）。

### 18.2 线程队列

`GSThreadedBackend::Enqueue` 把 batch 按 Op 写入 64 KB chunk。顶点部分与状态分开：

- 状态只写一次（如果和上一条相同，则不重复写）；
- 每条 `Op::Vertices` 只写顶点 + primitive 信息（约 145 字节）；
- 队列最多 256 个 pending chunk；满了 `PublishLocked` 会等 worker 消费。

worker 的 `Execute` 逐条解析。`Op::Vertices` 把顶点/primitive 复制进常驻的 `GSPrimitiveBatch draw`，状态复用上一次的，然后 `m_inner->Submit(draw)`。

`PS2X_GS_DISCARD_DRAWS=1` 在这个位置直接跳过 `Submit`。标题场景剩余 1.3–1.5 s/5s 就是这条链路的成本。

### 18.3 `Impl::submit`

进入 `GSHwBackend::Impl::submit` 后：

1. 如果 primitive 是 sprite/line 等，先处理 `tryShuffle`（16 位通道拷贝走独立路径）和 `depthClearSprite`（无纹理精灵用作深度清除）。
2. 检查 PSM 是否支持；不支持则 `skippedPsm`。
3. 判断 `sameState(pendingState, s)`；不同则 `flushPending()`。
4. 若没有 pending，记录 `pendingState = s`，`havePending = true`，重置 `firstRawZ`。
5. 根据 primitive 类型展开顶点：
   - 三角：3 个顶点；
   - 精灵：2 个输入顶点 → 4 个角 → 6 个顶点（两个三角形）；
   - 线：2 个顶点 → 四边形（4 顶点 → 6 顶点）。
6. `addVertex` 对每个顶点做：
   - `x = v.x - XYOFFSET.ofx/16 + half`，`y` 同理；
   - `z` 用 `zMaxFor(zbuf.psm)` 归一化；
   - STQ → UV（除以 Q，按 TW/TH 缩放）；
   - 颜色字段；
   - 精灵的 UV clamp（`cu0/cv0/cu1/cv1`）。
7. 把 `HwVertex` 追加进 `pending`。

注意：`HwVertex` 在 patch 59 中是 64 字节（16 个 float），patch 59 之后仍是 64；如果未来加顶点属性（如调色板行号），会变 68 字节，记得同步 `stride`、环形缓冲大小和所有 `VertexAttribFormat` 的 size/offset。

### 18.4 `flushPending` / `draw`

`flushPending`：

- `++batchSerial`（让下一个精灵不与上一批产生接缝）；
- `flushShuffle()` 先把 shuffle 队列画掉；
- 若 `pending` 为空则返回；
- 调 `draw(pendingState, pending)`。

`draw()` 处理两个特殊情况：

- **Z 反转**：`isZInversion` 时按颜色通道拆成多次 `drawOne`（每段一次 draw）；
- **阴影体/混合**：`unsupportedBlend` 时同样拆段。

其余情况一次 `drawOne`。所有拆段都会增加 `stats.batches`。

### 18.5 `drawOne`

按顺序：

1. `target(frame.fbp, frame.fbw)`：找/建 RenderTarget；必要时 `createTarget`（会清空颜色/深度）。
2. `attachDepth`：确保有深度纹理（`zbuf.zbp`）。
3. `setFbo/setViewport/setScissor/...`：patch 59 之前是裸 GL 调用；**不要加状态缓存**（8.2）。
4. 深度/混合/alpha test 计算：
   - `zInv`、`zAlias`、`softBlend`、`wrapCount`、`unsupportedBlend`；
   - `blendState` 返回 equation/sfactor/dfactor；软件混合时在 shader 里读目标。
5. `UseProgram` + ~35 个 uniform：
   - 日期/目标 alpha、固定混合参数、Z 别名、TEXA、索引/线性、wrap、Z 纹理、像素缩放等；
   - patch 59 没有改这一块（UBO 方案已证伪）。
6. 纹理：
   - 判断 `src`（同目标）、`rsrc`（重解释）、`zsrc`（深度纹理）、`replacement`（纹理包）、`indexed`（调色板）；
   - `textureFor` / `indexTextureFor` / `paletteFor`；
   - 绑定纹理、`TexParameteri` 四个参数；
   - 重解释时 `setupReinterpret` 绑定表/调色板/目标纹理。
7. alpha test：
   - `ate`/`atst`/`aref`；`pass=1` 时 shader 只保留通过像素；
   - 若 `afail != 0`，第二遍 `pass=2`，并按 AFAIL 设置 ColorMask/DepthMask。
8. 顶点：
   - patch 59 的 `appendVertices`：写入环形缓冲 + `glBindVertexBuffer(0, vbo, offset, stride)`；
   - `glDrawArrays(GL_TRIANGLES, 0, count)` 或按段 `first/count`。
9. `glDisable(GL_SCISSOR_TEST)`，恢复给其他路径。

### 18.6 Shader

- 顶点着色器：位置用 `aPos * uInvSize * 2 - 1`，Z 用 `aZ * 2 - 1`，颜色/STQ/UV/UVClamp 原样传递；flat varying 保留平直着色。
- 片元着色器：
  - 纹理采样：直接色 / 索引查表 / 重解释地址映射 / 深度纹理 / Z 别名；
  - 颜色/alpha 处理：TEXA、TCC、TFX、IIP/FST；
  - alpha test：`pass=1` discard 失败像素，`pass=2` discard 通过像素；
  - 软件混合：`uSwBlend` 读 `uDest` 做 ALPHA 选择器与 COLCLAMP wrap；
  - 输出 `oColor`/`oDepth`（写深度时）。
- 这个 shader 是 `#version 430 core`，所有非采样 uniform 用普通 `glUniform`。**没有** UBO 块（8.1 已删）。

### 18.7 纹理仓库

`GSTextureStore` 负责 VRAM 镜像、上传日志、CLUT、页面表格：

- `BeginTransfer` 记录本次 GS 传输覆盖的块，递增 `writeSeq`；
- `DecodeTextureRgba` / `ReadColorRun` / `ReadIndexRun` 按 GS 页表/交换规则读 VRAM；
- `LoadClut` 从 VRAM 读 256 色（来自上传或渲染目标）；
- `Upload` 写 VRAM；
- `Reset` 清空。

`GSHwBackend` 的纹理缓存 key 包含 tbp/tbw/psm/tw/th/texa/clut 等；上传重叠会让对应纹理 `valid=false`，下次绘制重解码。重过场的 `texDecodes` 高就是这里触发的。

---

## 19. 补丁制作与验证流程（本次实际用法）

### 19.1 为什么不能直接 `git diff`

`engine/runtime` 的工作区已经带有大量历史补丁的改动，`git diff` 会把历史改动和你的改动混在一起。正确做法是**以“改动前的工作区”为基线**：

1. 在改代码前，把要改的文件备份到 `data/_tmp/orig-*`。
2. 改完后，用备份作为 base、当前文件作为 final。
3. 建一个临时 git 仓库，把 base 放到真实的仓库相对路径（如 `PS2Recomp/ps2xRuntime/src/lib/gs/gpu/...`），commit。
4. 把 final 覆盖进去，`git add -A`，`git diff --cached` 就是增量补丁。
5. 在补丁开头写英文 header（what/why/measured result），`git apply` 会忽略 header。
6. 用另一个干净 base 副本 `git apply --check` + `git apply`，再逐字节比较结果（忽略 CRLF）。

### 19.2 本次 59/60 的基线特例

- 59 的基线里 `PS2X_GS_HW_SCALE` 必须是 `std::max(1.0f, ...)`（原始工作区），才能让补丁包含 clamp 修复。
- 60 的基线是 `ps2_vu1_x64.inl` 去掉本次新增的 fastMode/emitLoad/MADD 分支；我们通过手工反向编辑重建了它。
- 两份补丁都验证过 `check=0`、`equal=True`（忽略 CRLF）。

### 19.3 补丁链的历史缺口

`engine/patches` 目前是 01–58（缺 49）+ 59 + 60。缺 49 意味着“从 471c831 干净 clone 依次应用 01–58”**不能**得到当前工作区的渲染器（`swe_state`/批次化/软件后端等历史改动不在链里）。这是本次交接最重要的仓库风险：

- 如果下一个接手人从补丁链重建，会得到另一套渲染器，和本机实测不匹配；
- 如果只是继续在现有工作区开发，则没有影响；
- 建议补一个 `49-gs-batch-state`（把工作区相对 01–48 的渲染器差异收进补丁），或在 README 里明确标注“工作区 = 链 + 手工状态”。

### 19.4 新补丁的命名与顺序

- 用 `NN-name.patch`，NN 递增，名字小写连字符；
- 一个补丁只做一件事（59 顶点环 + scale clamp 算一个“低配可用”整体；60 是纯 VU1 快模式）；
- header 必须写实测数字，否则下一个接手人无法判断是否值得保留；
- 不要修改已有补丁的上下文行（上游代码上下文不能动，否则补丁链断）。

---

## 20. 性能剖析进阶

### 20.1 采样器（需要 PDB）

```
build.cmd -Stages configure,build -Pdb
tools/profile/sampler.exe ps2EntryRunner.exe <seconds> <delay>
```

`sampler.cpp` 按线程打印最热函数（GameThread=EE、VIF1/VU1 worker、GSThread）。注意：

- 采样器需要 Release+PDB，不要用 Debug；
- 采样期间不要开 `GOW_PERF_DIAG=1` 的逐段计时（会干扰）；
- 只在本机构建上跑，PDB 不要外传。

### 20.2 VU1 计数器

`GOW_VU1N_DIAG=1` 每 5 s 打印 native VU1 计数器。`missBlocks > 0` 表示有块没有 native 代码（走解释器），战斗会掉到 44–50。检查 `data/<id>/vu1n_heads.txt` 和 `vu1_capture`。

### 20.3 帧区间分布

`GOW_PERF_DIAG=frames` 打印 `[gow-frame]` 的 p50/p95/p99/max、over_16_67/33/50/100。用它看卡顿分布，而不是只看平均 fps。

### 20.4 采样时的常见假象

- 场景不同：开场 5 s 是在加载/电影，任何 FPS 都不可比；
- host 限速 60：guest 60 时 `host_wait` 接近满值，不代表 CPU 空闲；
- 队列背压：`gs_ms` 包含等待 worker 的时间，不等于纯渲染 CPU；
- 驱动同步：`gs_ms` 飙升不一定是代码慢，可能是 GPU 队列满后驱动阻塞。

---

## 21. 一周接手计划（建议）

**第 1 天：环境与基线**

- 按 1.2/1.3 构建运行；
- 跑 3 组 45 s：fast off / fast on / discard，确认 52–56 / 59–60 / 59.9；
- 截图标题/菜单，确认画面。

**第 2 天：画面验证**

- 用启动器或人工进入战斗，检查模型、阴影、粒子、UI、过场；
- 快模式异常 → 记录场景 + `GOW_VU1_FAST=0` 对照；
- 确认纹理包、存档、音频未被破坏。

**第 3–4 天：重过场 GS 优化**

- 先做 shuffle 合批（9.1.1）：按目标/通道模式合并相邻 shuffle，减少 FBO 绑定；
- A/B `shuffles`、`gs_ms`、`upload_ms`；
- 再做纹理上传合并（9.1.2）：同帧同纹理只保留最后一次；记录 `texDecodes`。

**第 5 天：前端 range 提交**

- 只做连续同状态 range，不改状态比较；
- 在传输/CLUT/FINISH/PRESENT/Clear 处 flush；
- 目标重过场 +2–4 fps。

**第 6 天：VU1/AOT 评估**

- 检查日版 `vu1n_heads.txt` 与捕获；
- 若有 AOT 条件，做 AOT fast + 战斗回放对比；
- 跑 `vu1_x64_fuzz_test` 快/精确两组（若构建可得）。

**第 7 天：收尾**

- 更新 `docs/tested-hardware.md` 与 README 补丁表；
- 把基准脚本移到 `tools/profile/` 或文档化；
- 写清楚本机数字不可外推。

---

## 22. 常见陷阱（本次全部踩过）

1. **改 `engine/runtime` 不影响可运行构建**：实际运行的是 `C:\gow-jpn` 快照。必须复制 + touch + ninja。
2. **Copy-Item 保留旧时间戳**：Ninja 看到旧 mtime 会 “no work to do”，你以为重编了其实没有。每次复制后改 `LastWriteTime`。
3. **`glBufferStorage` flags**：`GL_DYNAMIC_DRAW` 不是合法 flag，用 `GL_DYNAMIC_STORAGE_BIT (0x0100)`。见 6.3。
4. **不可变存储不能再 `glBufferData`**：映射失败要删 buffer 重建。
5. **`gow-native.boot` 覆盖环境**：带 ELF 参数启动不会读 boot；不带参数会读，且 boot 里 `PS2X_GS_HW_SCALE=1`。这解释了“为什么启动器默认 1×”。
6. **场景不可比**：30 s 和 60 s、有无 `GOW_FAST_BOOT`、有无 `GOW_SKIP_FMV` 会落在完全不同的阶段。A/B 必须同开关、同时间窗。
7. **`host_hz` 不是 fps**：看 `guest_flip_hz`。
8. **Intel 驱动与常规经验相反**：状态缓存/UBO 在这块 GPU 上更慢。换 NVIDIA/AMD 再测。
9. **`GOW_VU1_FAST` 默认 0**：不设置就还是精确模式，标题 52–56。
10. **快模式未验证战斗**：出现异常先关掉，不要先改渲染器。
11. **脚本化输入到不了 gameplay**：当前构建 `state=3 levelReady=0`；需要人工或修脚本。
12. **PPM 是 GS 输出不是窗口**：窗口截图用启动器/系统工具；PPM 用于比对渲染内容。
13. **纹理 id 复用**：如果做纹理参数缓存，删除纹理时要清缓存，否则新纹理用旧参数。
14. **补丁链缺 49**：见 19.3，不要从补丁链假设得到当前渲染器。
15. **不要提交游戏数据/截图/捕获**：见 15。

---

## 23. 命令速查

```powershell
# 构建
<repo>\data\_tools\ninja\ninja.exe -C C:\gow-build-jpn ps2EntryRunner

# 运行（显式 ELF，0.5x，快模式）
$env:PS2X_GS_HW_SCALE='0.5'; $env:GOW_VU1N_X64='1'; $env:GOW_VU1_FAST='1'; $env:TOBIICHI_FPS_GOSTER='1'
Start-Process 'C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe' -ArgumentList 'SLPM_670.10' `
  -WorkingDirectory 'C:\gow-jpn-data\gow1\discs\asia-97399' -RedirectStandardError "$env:TEMP\gow.log"

# 基准
powershell -NoProfile -ExecutionPolicy Bypass -File .\data\_tmp\bench-render.ps1 -Seconds 45 -Tag fast -Scale 0.5
$env:GOW_VU1_FAST='1'; ...

# 天花板
$env:PS2X_GS_DISCARD_DRAWS='1'

# 回退顶点环
$env:GOW_GS_HW_RING='0'

# 精确 VU1
$env:GOW_VU1_FAST='0'

# 截图
$env:GOW_PAD_TEST='1'; $env:GOW_FAST_BOOT='1'; $env:GOW_SKIP_FMV='1'
$env:GOW_PAD_GUION='5:start,12:x,18:x,24:x,30:x,36:x,42:x,48:x'

# PPM -> PNG
python -c "from PIL import Image; import glob,os; [Image.open(p).save(os.path.splitext(p)[0]+'.png') for p in glob.glob(r'C:\gow-jpn-data\gow1\discs\asia-97399\gow_pad_test_*.ppm')]"
```

---

## 24. 最后一段话

如果你只能记住三件事：

1. **这台机器的 60 帧是场景相关的**：标题（fast VU1 + 0.5×）能到 60；开场过场 20–28；重演算 demo 33–41。不要用一个数字对外承诺全场景 60。
2. **渲染器优化不是无限收益**：patch 59 的顶点环是净收益；UBO/状态缓存/调色板图集在这块 GPU 上是负收益。先测量，再写代码。
3. **下一次真正的大头在 GS shuffle/纹理流与 VU1 战斗覆盖**，不是继续在 `drawOne` 里抠 uniform。

交接文档结束。祝下一个接手人少踩坑。

---

## 25. 与原始设计文档（RENDER-PIPELINE-MODERNIZATION）的对照

原始文档提出了 5 个阶段。本次实际落地/证伪情况如下，接手人可以直接对照，避免重复讨论：

| 原始阶段 | 本次结论 | 原因 |
|---|---|---|
| Stage 1：前端 `SubmitRange` 契约批处理 | **未实现，保留为下一阶段** | 后端已经有 pending 合批（相邻同状态合并）；真正的收益在前端每图元 `buildDrawBatch`/入队，需要改接口/队列/Null 后端，改动面大。文档里“74–605 次提交/帧”在本作是 1.4–2 万图元/帧，量级不同 |
| Stage 2：状态 hash | **未保留** | 全量 `operator==` 已是编译器生成的逐字段比较；canonical 比较（忽略无效字段）实测批次几乎不降，`gs_ms` 略升 |
| Stage 3：顶点路径（持久映射/环形缓冲/MultiDraw） | **顶点环已实现（patch 59）；MultiDraw 不需要** | 一个 state run 已经是一次 `glDrawArrays`；不同 state 的批次无法用 MultiDraw 合并 |
| Stage 4：alpha test 失败遍折叠 | **未做，保持两遍** | `afail` 的颜色/深度写掩码不同，一遍 draw 无法表达；stencil 仍需两遍 |
| Stage 5：presentation 解耦 | **原本已是共享纹理** | 没有改动 |
| 软件后端（文档中的 49 号补丁） | **本仓库不存在** | 补丁链缺 49；本机只跑 GL 后端 |

另外，原文档建议的“每批次 UBO / 状态缓存 / 调色板图集”在本机实测为负收益（第 8 章），这与原文档的预期相反，原因是 Intel HD 4400 驱动行为。**换 GPU 可以重新评估，但不要在本机默认打开。**

---

## 26. 本次文件改动清单

### 26.1 源码

| 文件 | 改动 | 补丁 |
|---|---|---|
| `PS2Recomp/ps2xRuntime/src/lib/gs/gpu/gs_hw_backend.cpp` | 顶点环成员/`appendVertices`/VAO 初始化分支/`drawOne` 调用点；`PS2X_GS_HW_SCALE` clamp | 59 |
| `PS2Recomp/ps2xRuntime/src/lib/gs/gpu/gs_gl.h` | `BindVertexBuffer` / `VertexAttribFormat` / `VertexAttribBinding` 指针 | 59 |
| `PS2Recomp/ps2xRuntime/src/lib/gs/gpu/gs_gl.cpp` | 加载上述三个 GL 函数（可选，失败回退） | 59 |
| `PS2Recomp/ps2xRuntime/src/lib/vu/ps2_vu1_x64.inl` | `fastMode()`、`emitLoad()`、`norm()` 快分支、MADD/MSUB 快路径 | 60 |

### 26.2 文档/脚本

| 文件 | 改动 |
|---|---|
| `engine/patches/59-gs-vertex-ring.patch` | 新增 |
| `engine/patches/60-vu1-jit-fast-mode.patch` | 新增 |
| `engine/README.md` | 补丁表新增 59、60 行 |
| `docs/tested-hardware.md` | 新增 59、60 两节实测记录 |
| `play-asia.cmd` | 加入 `GOW_VU1_FAST=1`（快模式），保留 0.5× |
| `docs/RENDER-PIPELINE-HANDOFF-2026-11-04.zh-CN.md` | 本文档 |
| `data/_tmp/bench-render.ps1` | 临时基准脚本（未入库，可复制到 `tools/profile/`） |
| `data/_tmp/orig-jpn/`、`data/_tmp/opt-jpn/`、`data/_tmp/*.log`、`data/_tmp/*.png` | 临时备份/日志/截图（可删） |

### 26.3 没有改动但容易误解的地方

- `engine/runtime` 的 git 工作区本身有 77 个历史修改文件；59/60 只是其中两个增量。不要 `git checkout .`，会丢掉历史补丁状态。
- `C:\gow-jpn` 是独立快照，不在外层仓库版本控制里；它的改动不在 `git status` 里。交接时要把 `C:\gow-jpn` 视为“可运行构建的源码”，单独备份。
- `gow-native.boot` 是机器相关文件，不要提交；它里面的 `PS2X_GS_HW_SCALE=1` 是启动器默认，不是本次优化值。

---

## 27. 实测日志原文摘录

### 27.1 基线（标题，0.5×，45 s）

```
[gow-perf] t=30.0 ee_ms=1800 gs_ms=2150 vu_ms=4580 iop_ms=600 guest_flip_hz=52.8 host_hz=59.8
[gs-hw] shuffles=4000 draws=3.4M batches=20000 texDecodes=1200 texHits=4000 textures=63
```

### 27.2 patch 59（标题，0.5×，60 s）

```
[gow-perf] t=40.0 ee_ms=1700 gs_ms=2010 vu_ms=4570 iop_ms=350 guest_flip_hz=53.3 host_hz=58.6
[gs-hw] shuffles=4000 draws=3.6M batches=19500 texDecodes=1200 texHits=4000 textures=63
```

### 27.3 patch 59 + 60（标题，0.5×，45 s，快模式）

```
[gow-perf] t=20.0 ee_ms=2123 gs_ms=1925 vu_ms=4060 iop_ms=359 guest_flip_hz=59.85 host_hz=59.85
[gow-perf] t=30.0 ee_ms=2080 gs_ms=2101 vu_ms=4097 iop_ms=386 guest_flip_hz=60.14 host_hz=59.74
[gow-perf] t=40.0 ee_ms=2093 gs_ms=2177 vu_ms=4135 iop_ms=389 guest_flip_hz=60.05 host_hz=59.45
```

### 27.4 开场过场（0.5×，无 FAST_BOOT/SKIP_FMV，45 s）

```
[gow-perf] t=15.0 ee_ms=2200 gs_ms=2351 vu_ms=4355 iop_ms=674 guest_flip_hz=24.55 host_hz=52.90
[gow-perf] t=20.0 ee_ms=2445 gs_ms=2049 vu_ms=4629 iop_ms=832 guest_flip_hz=16.16 host_hz=34.11
[gow-perf] t=25.0 ee_ms=2044 gs_ms=2845 vu_ms=4563 iop_ms=760 guest_flip_hz=24.29 host_hz=35.64
[gow-perf] t=40.0 ee_ms=2156 gs_ms=2076 vu_ms=4468 iop_ms=618 guest_flip_hz=26.98 host_hz=53.35
```

### 27.5 开场过场，丢弃绘制

```
[gow-perf] t=20.0 ee_ms=1835 gs_ms=1351 vu_ms=4563 iop_ms=520 guest_flip_hz=36.54 host_hz=57.51
[gow-perf] t=30.0 ee_ms=1798 gs_ms=1397 vu_ms=4594 iop_ms=481 guest_flip_hz=41.27 host_hz=58.82
[gow-perf] t=40.0 ee_ms=1766 gs_ms=1477 vu_ms=4596 iop_ms=485 guest_flip_hz=43.50 host_hz=59.46
```

### 27.6 重演算 demo（快模式，60 s）

```
[gow-perf] t=20.0 ee_ms=2104 gs_ms=3068 vu_ms=4429 iop_ms=559 guest_flip_hz=35.97 host_hz=55.95
[gow-perf] t=30.0 ee_ms=2112 gs_ms=2810 vu_ms=4358 iop_ms=536 guest_flip_hz=37.57 host_hz=51.16
[gow-perf] t=50.0 ee_ms=2718 gs_ms=4807 vu_ms=3935 iop_ms=516 guest_flip_hz=39.73 host_hz=52.91
[gs-hw] shuffles=22176 draws=4.1M batches=17504 texDecodes=430 texHits=7291 textures=117
```

这些原始行可以用于对比新改动：如果新版本在同一场景的 `vu_ms`、`gs_ms`、`shuffles`、`upload_ms` 不在同一量级，先怀疑场景/开关不同，不要直接下结论。

---

## 28. 交接签名与联系人

- 本次工作完成时间：2026-11-04
- 可运行构建：`C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe`（含 patch 59 + 60）
- 构建源码：`C:\gow-jpn`（与 `engine/runtime` 同步）
- 补丁：`engine/patches/59-gs-vertex-ring.patch`、`engine/patches/60-vu1-jit-fast-mode.patch`
- 实测记录：`docs/tested-hardware.md` 末尾两节
- 临时证据：`data/_tmp/`（日志、截图、备份）

接手第一步：按 1.3 运行 `play-asia.cmd`，看左上角 FPS；标题应为 59–60。然后按第 21 章的一周计划推进。遇到性能问题，先跑三个基准（fast off / fast on / discard），再决定改哪一层。不要把“标题 60”当成“全场景 60”，也不要在没有 A/B 数据的情况下改渲染器。

—— 交接完毕。
