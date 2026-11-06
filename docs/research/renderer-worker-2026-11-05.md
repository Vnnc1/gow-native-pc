# GS 工作线程与顶点环加固（2026-11-05）

**结论先行**：`play-asia.cmd` 少设了 `PS2X_GS_WORKER=1`，导致 VIF1→VU1→GIF→GS 全部同步跑在 EE 线程上。补上之后，同一构建、同一场景下**超过 33 ms 的帧从 92% 降到 61%**，帧时间均值 43.5 → 37.8 ms。本文同时记录一个反直觉的测量教训：**在这台机器上，平均帧率的重复性差到不能用来判断优化是否有效**，必须看帧时间分布。

**机台**：i3-4170（2C4T Haswell）/ Intel HD Graphics 4400 / 8 GB DDR3 / Windows 10 / 亚洲盘 SCAJ-97399（中文壳）/ 内部 0.5× / `GOW_VU1N_X64=1` + `GOW_VU1_FAST=1` / 窗口 1920×1080。
**场景**：`GOW_SKIP_FMV=1` + `GOW_FAST_BOOT=1` 进入关卡后的前 90 s（同一路径、同一时长）。

---

## 1. 问题：手动启动比启动器慢一倍

`launcher/src/lanzador.cpp` 的默认环境里写着 `{"PS2X_GS_WORKER", "1"}`，而 `play-asia.cmd` 没有设它。启动日志可以一眼看出来：

```
[gow-sync-config] early_finish=0 worker=0 timing=0 gs_early_finish=0
```

`worker=0` 意味着 `PS2Memory` 不创建 GS worker：VIF1 解析、VU1 执行、GIF 打包、GS 前端全部在 EE 线程上按顺序完成。三者的忙时相加正好等于帧时间，这就是串行的直接证据：

| 配置 | ee_ms | vu_ms | gs_ms | 三者之和 / 5 s | 帧时间 |
|---|---|---|---|---|---|
| worker=0 | 1130 | 2325 | 1390 | 4845 ms（97%） | 42.6 ms（p50） |
| worker=1 | 1776 | 2846 | 1610 | 6232 ms（125%） | 37.4 ms（p50） |

worker=1 之后三者之和超过窗口长度，说明它们真的并行了（`[gow-perf]` 的 `guest_wait_ms` 也从 0 变成 2800：EE 开始等 worker）。

## 2. 证据：帧时间分布

`GOW_FRAME_DIAG=1`（配 `GOW_PERF_FRAME_PC`）每 5 s 打一行 `[gow-frame]`。两次运行，各取稳态窗口：

| 指标 | worker=0 | worker=1 | 变化 |
|---|---|---|---|
| mean_ms | 43.52 | 37.77 | −13% |
| p50_ms | 42.55 | 37.39 | −12% |
| p95_ms | 55.35 | 56.00 | 持平 |
| p99_ms | 71.60 | 68.38 | −4% |
| max_ms | 72.37 | 92.82 | 更差 |
| **over_33_33** | **106 / 115（92%）** | **81 / 133（61%）** | **−31 个百分点** |

读法：worker 把「地板」抬起来了（绝大多数帧从 43 ms 降到 37 ms，超过 33 ms 的比例大幅下降），但**长尾没动**（p95 仍 56 ms，max 反而更差）。所以它不是「消除卡顿」，是「减少卡顿的密度」。

## 3. 一个必须记住的测量教训：平均帧率不可重复

第一次做 A/B 时得到的是「25 → 35 帧，+40%」。换成同一构建、各跑两次之后：

| 配置 | run 1 | run 2 | 中位数 |
|---|---|---|---|
| worker=0 | 22.15 | 29.79 | 25.97 |
| worker=1 | 24.80 | 27.52 | 26.16 |

**中位数几乎相同**，而单次运行的极差（22–30）比配置差异还大。原因是场景在漂移：`GOW_FAST_BOOT` 之后落到哪一片区域、摄像机朝向、流式加载进度，每次都不完全一样。同一配置的 `draws` 在 1.57 M 与 2.24 M 之间波动（±43%），说明测的根本不是同一段画面。

结论：
- 「+40%」是噪声，**已撤回**。
- 判断是否有效必须看**同一窗口内的分布**（p50/p95/over_33_33），或者用与场景无关的归一化指标（`gs_ms / draws`）。
- 本文第 2 节的两行数据是同一时长的稳态窗口，方向一致（地板抬高、长尾不变），可以采信。

## 4. 顺带修掉的真实隐患：顶点环越界

`gs_hw_backend.cpp` 的 `ringAppend` 在 `bytes > 32 MB` 时会先把 `vertexRingOffset` 归零、再 `memcpy`，等于写穿持久映射区。今天不触发（实测最大批次 84 KB），但这是「迟早一次」的堆越界，症状会是随机花屏或崩溃。

修法：`ringAppend` 在放不下时返回 `kRingOverflow`，调用方各自回退到自己的 buffer —— 顶点路径用新建的 `spillVbo`（**不能**对环再 `BufferData`，它是 `glBufferStorage` 的不可变存储，会 `GL_INVALID_OPERATION`），shuffle 路径用它自己的 `shuffleVbo`。

同时把两个压力指标加进 `[gs-hw]` 行：

```
ringWraps=15 oversized=0
```

`ringWraps` 每 5 s 十几到几十次（约 0.1 次/帧），说明 32 MB 环足够，不需要加大；`oversized` 恒为 0，说明回退路径没有被走到。

## 5. 剩下的 40% 在哪

稳态窗口里 `[gow-perf]` 的典型比例（worker=1，90 s 运行）：

- `vu_ms` 2800–3200 / 5 s → 每帧约 19–21 ms
- `gs_ms` 1450–1680 → 约 10–11 ms
- `ee_ms` 1700–2100 → 约 12–14 ms
- `guest_wait_ms` 2700–2900 → EE 每帧等 worker 约 18–19 ms

帧时间 30–32 ms，而 VU1 一项就 19–21 ms。`PS2X_GS_DISCARD_DRAWS=1`（一次 draw 都不发）在同一路径上只把 `gs_ms` 从 ~1400 降到 ~900，帧率几乎不变 —— **渲染器不是当前的墙**。

要到 60 fps（16.7 ms），必须把 VU1 压到 12 ms 以下；这在渲染器侧做不到，属于 VU1 JIT/AOT 的范围。

## 6. 改了什么

| 文件 | 改动 |
|---|---|
| `play-asia.cmd` | 加 `PS2X_GS_WORKER=1`（附实测注释） |
| `engine/runtime/.../gpu/gs_hw_backend.cpp` | `ringAppend` 越界守卫 + `spillVbo` 回退；`stats.ringWraps` / `oversizedBatches` |
| `tools/test/bench-render.sh` | 新增：从 `regional-builds.json` 取 runner/ELF，跑固定时长，输出 `guest_flip_hz` 与 `[gow-frame]` 分布 |
| `data/gow1/regional-builds.json` | 重新注册新 runner 的 sha256（否则启动器拒绝加载） |

## 7. 回退

| 改动 | 回退方式 |
|---|---|
| 工作线程 | 从 `play-asia.cmd` 删掉 `PS2X_GS_WORKER=1`，或启动时 `set PS2X_GS_WORKER=0` |
| 环守卫 | 只影响「单批次 > 32 MB」，正常路径行为不变；如需回退，`ringAppend` 去掉 `need > kVertexRingBytes` 分支即可 |
| 新统计字段 | 仅多两个数，无行为影响 |

## 8. 未验证

- 画面正确性：worker=1 是启动器默认路径，本次没有做逐像素对照。`data/` 里没有录制帧，`PS2X_GS_RECORD` 未跑。
- NVIDIA / AMD 机器上 worker 的收益（本机只有 Intel HD 4400）。
- 长尾（p95 56 ms）的成因：怀疑是 EE↔worker 的 job 粒度，但没有逐帧时间线，未证实。
- 1.0× 与 0.7× 的对比：两次运行落在不同区域（`batches` 8760 vs 6327），数字不可比，作废。

---

## 9. 第二轮：渲染器静态审查（同日）

`[gs-hw]` 统计行新增 `ringWraps / ringStalls / oversized / zbpchg` 之后，用 0.5× + `PS2X_GS_WORKER=1` 跑 30 s：

```
shuffles=4064 batches=9868 unsupportedBlend=1270 ringWraps=12 ringStalls=0 oversized=0 zbpchg=2032
```

### 9.1 修好的：fence 超时后继续写

顶点环回绕时等上一圈的 fence，超时 1 s 后**继续归零并覆盖**——GPU 可能还在读那一圈，结果是几何被撕开，看起来像驱动 bug。现在改成超时后真等（`GL_TIMEOUT_IGNORED`）并计数 `ringStalls`。本机 30 s 内 `ringStalls=0`，说明环的大小是合适的；这个改动只在病态情况下生效。

### 9.2 量到的：一个深度纹理服务所有 ZBP

`RenderTarget` 只有一个 `depth`，`attachDepth()` 对任何 `ZBP` 都复用它，只把 `t.zbp` 改成新值。GS 里 ZBP 选的是 VRAM 区域，两个 ZBP 是两块不同的内存，所以复用等于让两个深度缓冲互相污染。

先加计数不改行为：**`zbpchg=2032` / 5 s，约 17 次/帧**。也就是说游戏确实在活着的目标上切 ZBP，这不是理论问题。

没有在本轮修，因为修法要动三处：
- 深度纹理按 `(fbo, zbp)` 存，切 ZBP 只重挂附件（`FramebufferTexture2D`），不清、不重建；
- `findReinterpretSource()` 用 `o.zbp == t.fbp` 找可采样的目标，必须跟着变成"该地址的那张深度"；
- 反相 Z（shadow volume）用 `invertedZ` 按 zbp 记，切纹理后判定要重新对齐；
- 还要一次逐像素对照（现在 `data/` 里没有录制帧）。

`RenderTarget::depthCleared` 声明了但**从未被读**，看着就是为这件事准备的，没写完。

### 9.3 查过但不是 bug 的（省下后来人的时间）

| 怀疑 | 结论 |
|---|---|
| `palettes` 无界增长 | 有 4096 上限 + 整表清理；每个 CLUT 1 KB，封顶 4 MB。不是泄漏 |
| `buildTables` 的 `32u << (shiftX+shiftY)` | 正确：页表是 `[block][y][x]`，32 块 × 2048 像素 = 65536，与公式一致 |
| `GSDrawState` 用 `memcmp` 比较 | 不是：`operator==` 是 default 的逐字段比较，注释也写明了 padding 不可比 |
| `shuffleQuads[hd]` 越界 | `half = (byte >> 1) & 1`，恒为 0/1 |
| GL 误用 | `GOW_GS_HW_ERRTRACE=1` 跑 15 s：**0 条 GL 错误** |

### 9.4 一个可以优化但没做的方向

`unsupportedBlend=1270 / batches=9868` ≈ 13% 的批次走软件混合（在着色器里读目标色）。其中 `A=Cs, B=0, C=Ad, D=Cd` 这种标准 alpha 组合本可以映射到固定功能（`DST_ALPHA / ONE_MINUS_DST_ALPHA`）。没做，是因为 `GL_DST_ALPHA` 取的是**存储的**目标 alpha，而 GS 的 CT24 目标 alpha 恒为 0x80、渲染器里未必一致——这正是本项目被"等价替身"坑过的类型。要动就得先逐像素对照。

---

## 10. 修复：按 ZBP 分配深度（补丁 69）

9.2 记的那个问题，这一轮修了。

**改法**：`RenderTarget` 增加 `depthByZbp`（zbp → GL 纹理）。切到一个已知的 ZBP 只重挂附件（`FramebufferTexture2D`），不清、不重建；新 ZBP 才分配一张；每目标最多 4 张（`kDepthsPerTarget`），超了复用当前那张并计 `zbpfull`——无界增长比深度错更糟。`destroy()` 遍历 map 释放。

**怎么证明它真的生效**：`zbpchg` 在两个版本里都会计到 2000 左右（一个计"切了"，一个计"重挂了"），分不出来。所以加了一行只在**创建**时打印的日志：

```
[gs-hw] depth fbp=348 zbp=68  -> 32x256 (1 for this target)
[gs-hw] depth fbp=348 zbp=15c -> 32x256 (2 for this target)
```

25 s、0.5×、同一场景，数这行：

| 配置 | 深度纹理数 | 说明 |
|---|---|---|
| 默认（按 ZBP） | **5** | fbp=348 同时持有 zbp 68 和 15c |
| `GOW_GS_DEPTH_PER_ZBP=0` | **4** | 该目标只有一个缓冲，第二个 ZBP 复用它 |

顺带量出了真实范围：**开场关卡里只有一个目标在切 ZBP**（fbp=348，68 ↔ 15c），但每帧都切。所以这是一个"窄而持续"的错误，不是普遍的。

**没有回归**：同一场景各 25 s，guest 帧率均值 26.2（开）vs 23.8（关），在场景漂移的噪声内；多出的成本是一张 32×256 深度纹理和每次切换一次重挂。

**没有验证的**：像素。`findReinterpretSource` 与 shuffle 的 Z 源都读"当前挂着的"那张（`t.zbp`），所以一个"有纹理但没挂上"的 ZBP 现在完全匹配不到——之前是匹配到并读了另一个缓冲的内容。**缺失比读错安全**，但要下"修好了"的结论，还需要一次录制回放的逐像素对照。

**回退**：`GOW_GS_DEPTH_PER_ZBP=0`。

---

## 11. 补上缺失的那一维：GPU 侧计时（补丁 70）

`gs_ms` 是**线程忙时**，它分不清"CPU 在提交"和"GPU 在画"。这个歧义让前面所有关于"GS 要 10–11 ms"的讨论都只能算半句话。

`include/runtime/gs/gs_gpu_profile.h` 里的时间戳队列其实早就写好了（`ps2xTest` 里有 173 行测试），但**渲染器从没接**。这一轮接上：每帧两个 `GL_TIMESTAMP`（Present 后第一个图元开、下一次 Present 关），四帧后才读，只读 `GL_QUERY_RESULT_AVAILABLE`，不阻塞。开关 `GOW_GS_GPU_PROFILE=1`，默认关（每次时间戳是一次驱动往返）。

第一次量到的（0.5×、`PS2X_GS_WORKER=1`、25 s、亚洲盘开场）：

```
[gs-gpu] frames=4 gpu_ms=5.38 max_ms=10.18
[gs-gpu] frames=4 gpu_ms=7.94 max_ms=17.08
[gs-gpu] frames=4 gpu_ms=7.56 max_ms=19.58
[gs-gpu] frames=4 gpu_ms=4.99 max_ms=10.64
[gow-perf] gs_ms=1437 / 5 s, ~125 帧 → 11.5 ms/帧
```

**结论：GS 的 11.5 ms 里，GPU 只占 5–8 ms，集显约 40% 空闲。** 也就是说一半的 GS 时间是 CPU 提交（构建批次、状态比较、顶点展开、入队/出队），不是光栅化。

这条直接改写了优先级：

| 之前以为 | 现在知道 |
|---|---|
| 降分辨率能救 GS | 不能：GPU 本来就闲，0.35× 与 0.5× 同帧（此前实测） |
| GS 10 ms ≈ GPU 10 ms | GPU 只有 5–8 ms，剩下是 CPU |
| 下一步该优化 shader/像素 | 该优化**提交路径**（每图元固定成本），但收益上限是 ~5 ms/帧 ≈ +14% |

而整帧的墙没变：同一窗口 `vu_ms=2986/5 s` ≈ 24 ms/帧，仍是最大项。

**回退**：不设 `GOW_GS_GPU_PROFILE` 就完全不产生查询。

---

## 12. 削提交路径之前，先量它（结论：不该削那里）

原来打算"跳过每图元的 `sameState` 比较"。先量再动手，`GOW_GS_COST=1`：

```
[gs-cost] submits=2226044 submit_ms=508 (228 ns/prim) compares=2212202 compare_ms=87 (40 ns/cmp)
[gs-cost2] pre_fbo=151 pre_state=13 tex_lookup=273 ...
```

- **比较只占 submit 的 17%**（87 / 508）。就算把比较全删掉，上限是 0.5 ms/帧 ≈ +1.5%。**这个优化不值得做，直接否掉。**
- submit 剩下的 83% 是顶点展开与入队，228 ns/图元，与 patch 66 记录的一致。
- 画批次内部（`one_ms`）里最大的一项是 `tex_lookup`：5 s 内 273–773 ms，其中 `tex_resolve`（`textureFor`：查表 + 源哈希 + 重解码）占 90% 以上。按 796 次重解码/5 s、每次约 1 ms 算，**纹理解码大约吃掉整个窗口的 15–20%**，是 GS 侧仅剩的大块。

### 12.1 一个必须承认的限制：短窗口 A/B 分辨不了 10% 以下的差异

同一配置连跑两次，`pre_fbo` 是 **151 ms 和 832 ms**；换成关闭按 ZBP 分配，是 **157 ms 和 1876 ms**。差异完全由"这一跑落在哪个场景/多少状态变化"决定，与配置无关。

所以：
- 我之前怀疑"深度重挂导致 pre_fbo 涨 5 倍"是**错的**，那是场景漂移。
- 想验证纹理解码那 15%，必须先有**按 guest 帧编号切窗**的测量（同一帧号 = 同一画面），而不是按墙钟 5 秒。这是下一件该做的事，且有半天的工作量。

### 12.2 顺手拿到的真实收益：0.7× 是免费的

GPU 计时接上后，分辨率第一次可以被定价（25 s、开场、`PS2X_GS_WORKER=1`）：

| 内部倍率 | guest fps | `gs_ms` /5 s | `[gs-gpu] gpu_ms` |
|---|---|---|---|
| 0.5× | 29.11 | 1387 | 2.7–10.1（均值约 6.3） |
| 0.7× | 28.99 | 1634 | 10.7–15.6（均值约 13.2） |
| 1.0× | （先前实测 GPU 会到约 27 ms，不安全） | — | — |

像素面积正好翻倍（1.96×），GPU 时间也正好翻倍（2.1×），**而帧率没变**——因为整帧仍被 VU1 的约 24 ms 卡住，GS 这 1.4 ms 的增量被吸收了。

于是把 `play-asia.cmd` 的默认内部分辨率从 0.5× 改成 **0.7×**：同样的帧数，两倍的像素。回退就是把它改回 0.5（重场景若开始顿挫）。

这也说明之前"0.7× 只有 16 fps"的测量是场景漂移的假象——那次 `draws` 是 1.14 M，这次是 2.0 M，根本不是同一段画面。
