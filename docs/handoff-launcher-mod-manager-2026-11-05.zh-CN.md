# 《战神》原生 PC 移植：Mod 管理器与启动器集成交接手册

> 文档版本：2026-11-05（v1）
> 面向：接手「给启动器做 Mod 管理器」的下一位工程师
> 工作副本：`<repo>`
> 构建源：`C:\gow-jpn`；构建目录：`C:\gow-build-jpn`
> 设计依据：`docs/mod-manager-design.zh-CN.md`（2451 行，下称「设计文档」）
> 运行时补丁：`engine/patches/71-mod-vfs-hooks.patch`
> 管理器 CLI：`tools/mods/gow_mods_cli.py`

---

## 0. 先读这一页

### 0.1 一句话结论

Mod 管理器的**后端已经做完并且实机跑通**：它能发现与校验 Mod、解析元数据、按优先级排序、做纹理包与 VFS 资源覆盖、检测冲突与缺失、事务化启用/禁用、失败回滚、把启用状态落盘，并能把计划注入运行时；在日版《战神》上从标题进到 3D 场景，无 Mod 与启用示例 Mod 两种状态都到达了玩法状态（`state=11`）。

**没做完的是「启动器界面」这一层**：本工作副本的 `launcher/` 目录只有编译好的 `bin`，没有 QML/C++ 源码；完整源码在 `C:\gow-jpn\launcher`。所以下一位的第一件事不是写新功能，而是把启动器源码取回工作副本、确认能重新编译，再把已经稳定的 CLI 用一个薄薄的 `ModsModel` 接进 `gow-launcher.exe`。这份手册的绝大部分篇幅，就是把这个「薄层」拆到文件级、函数级，并把所有坑先标出来。

### 0.2 当前完成度（诚实版）

| 能力 | 状态 | 证据/位置 |
|---|---|---|
| Mod 发现、`mod.toml` 解析、校验 | 完成 | `gow_mods_cli.py` 的 `scan_packages` / `validate_package` |
| 启用顺序、优先级、依赖、冲突仲裁 | 完成 | `build_plan` / `resolve_order`，plan 里记录 excluded/conflicts/warnings |
| 纹理覆盖（PCSX2 纹理包口径） | 完成 | 复用 patch 52 的 `GOW_TEXTURE_PACK`；CLI 只做 staging |
| VFS 文件覆盖 | 完成 | patch 71；`GOW_MOD_VFS_TABLE` TSV |
| 环境变量型 Mod | 完成 | 白名单 + 保留键；`plan.env` |
| 启用状态持久化 | 完成 | `data/mods/state.json` + profile TOML + journal |
| 事务、回滚、崩溃恢复 | 完成 | `activate` / `restore` / `rollback`，WAL journal |
| 实机三态验证 | 基本完成 | 见第 8 章；「禁用后恢复」用的是改号前的同一份代码，建议补一次 71 版复跑 |
| 启动器 UI | **未做** | 本手册第 5～6 章给方案 |
| `.PAK` / 函数 / 脚本 / 存档 Mod | 明确不做（降级） | CLI `UNSUPPORTED_SECTIONS`，原因见 3.6 |
| C++ 原生核心（`gow_mods` 静态库） | 未做 | 设计文档 §7.2 要求的发布形态；见 5.7 |
| 启动器会话报告 | 未做 | 设计文档 §20.5；见 5.6 |

### 0.3 下一位的「第一天三件事」

1. **取回启动器源码**：把 `C:\gow-jpn\launcher\{src,qml,recursos,CMakeLists.txt}` 复制进工作副本 `launcher/`（保留现有 `bin/`），然后 `build.cmd -Stages launcher` 或按 `launcher/CMakeLists.txt` 顶部注释手工 CMake+Ninja。先保证**原样能编、能开、能截图**，不要一上来就加页面。
2. **跑通 CLI 基线**：`python -I tools/mods/gow_mods_cli.py selftest`、`list`、`plan -p verify`、`apply -p verify`、`status`。确认 `data/mods/` 已存在且 profile `verify` 里有示例 Mod。
3. **照第 5.1 节的「最小闭环」接线**：`Main.qml` 加第 7 个页签 → `ModsModel` 读写 profile → 「开始游戏」前 `apply` 并把 `GOW_MOD_VFS_TABLE`/`GOW_TEXTURE_PACK` 注入 `Lanzador::iniciar()` 的环境 → 失败时弹错误且**不启动游戏**。做完这三步，玩家就能在启动器里勾 Mod 并进游戏；其余 UI 都是增强项。

### 0.4 本手册怎么读

- 只想快速开工：读第 0、2、5、6 章。
- 要改运行时/资源层：读第 3、4 章，尤其 3.5 的安全边界和 4.4 的纹理尺寸规则。
- 要复现实机验证：读第 8 章，命令可以照抄。
- 要评估风险或排期：读第 9、10 章。

---

## 1. 交接范围与验收口径

### 1.1 用户当初的交付要求（原文要点）

在 `<repo>` 中按设计文档实现 Mod 管理器，交付标准是「完整可以玩」——能真正加载/启用/禁用 Mod 并进游戏验证，不是只做界面壳。具体要求包括：

1. 先核对仓库现状（`git status`、已有 launcher/GUI/配置与资源加载路径），把设计文档功能点拆成「必须做/可选/暂不做」，说明接入点；文档与代码冲突时以代码为准并指出冲突。
2. 实现发现/元数据、启用顺序与优先级、资源覆盖（`.PAK`/纹理/音频/脚本等按文档口径）、冲突与缺失检测、启用状态持久化、失败回滚。安全默认：未启用时不改变原版行为；损坏或不兼容的 Mod 不能把游戏搞崩，要有隔离与错误提示。
3. 与现有补丁栈一致：独立补丁、编号接续、更新 `engine/README.md`；不破坏 patch 59–66（`PS2X_GS_RUN`、`PS2X_GS_PIPELINE`、`GOW_GS_*`、`GOW_VU1_FAST` 等）。
4. 渲染/画质或游戏数据改动只能基于项目内逆向证据与文档结论，禁止编造参数或伪造资源格式。
5. 验证必须真跑：干净全量编译；实际启动并进到 3D 场景，在「无 Mod / 启用一个示例 Mod / 禁用后恢复」三种状态下确认画面与行为正确，无花屏、崩溃、资源缺失；给出日志证据与关键截图或描述。
6. 不 git commit、不 push、不生成额外交付文件夹；构建沿用 `C:\gow-jpn` + `C:\gow-build-jpn`。

### 1.2 本次交接新增的目标

在上一段的基础上，本次的目标是**给启动器做 Mod 管理器**：让玩家在 `gow-launcher.exe` 的界面里看到 Mod 列表、勾选/取消、看到冲突和指纹状态，并在点「开始游戏」时自动应用计划。后端不再重写，启动器只做「薄壳 + 编排」。

### 1.3 验收口径（建议直接写进任务单）

- **安全默认**：启动器未启用任何 Mod 时，注入的环境变量集合必须与改造前完全一致（除管理器自己的诊断变量外），游戏行为不变。
- **失败不启动**：`plan`/`apply` 失败、指纹过期未处理、Mod 校验失败时，启动器必须显示可读错误并且**不启动 runner**。
- **可逆**：在界面点「禁用全部」后，下一次启动的注入集合为空，`data/mods/hooks/` 不再被 runner 读取。
- **可解释**：冲突、被排除的 Mod、缺失依赖、纹理尺寸不符，都能在界面上看到原因，而不是只有一个「失败」。
- **UI 可测**：新增页面有稳定的 `objectName`；文案走 `Textos.js` 的 tr/en/es 三语表；`tools/test/launcher-languages.py` 能通过。
- **实机**：无 Mod、启用示例 Mod、禁用后恢复三种状态都能进到 `state=11`，日志无 `cannot read`、无资源缺失，画面正常。

---

## 2. 事实基线：这个仓库现在到底长什么样

### 2.1 两棵树：工作副本与完整源码

这是本次交接**最重要的一条事实**，先记住：

- `<repo>` 是**工作副本**。它包含 `docs/`、`data/`、`engine/`、`games/`、`tools/`、`build.cmd` 等，但 `launcher/` 下只有 `bin/` 与 `bin-backup-20261104/`，**没有** `src/`、`qml/`、`recursos/`、`CMakeLists.txt`。工作副本根目录也**不是 git 仓库**（`git status` 会失败）；只有 `engine/runtime` 是 git 仓库（PS2Recomp 克隆）。
- `C:\gow-jpn` 是**完整源码树**，是一个 git 仓库，含 `launcher/src`、`launcher/qml`、`launcher/recursos`、`launcher/CMakeLists.txt`，也含 `PS2Recomp/ps2xRuntime` 的完整生成代码。构建产物在 `C:\gow-build-jpn`。

因此：

- 改运行时 → 改 `engine/runtime/...`，同步到 `C:\gow-jpn\...`，用 `C:\gow-build-jpn` 编译。
- 改启动器 → **先**把 `C:\gow-jpn\launcher` 的源码复制进工作副本（或直接在 `C:\gow-jpn` 里改并构建）。工作副本的 `launcher/bin/gow-launcher.exe` 是 2026-11-04 的构建，源码版本以其为准但可能落后；复制后先用 `TOBIICHI_CAPTURA` 截图确认 UI 与现二进制一致，再改。
- 设计文档 §2.7 与 §20.3 早就记录了这个「本工作副本缺 launcher 源码」的特殊性，并明确说**不要反编译 exe 里的 QML 来凑合**。这条仍然有效。

### 2.2 启动器现状（Qt 6 Quick）

工作副本 `launcher/bin/` 里是可运行的发行版：

- 主程序 `gow-launcher.exe`（约 5.1 MB，2026-11-04），Qt 6 运行库齐全（`Qt6Core/Gui/Qml/Quick/QuickControls2` 等），还有 `gow-session.exe`（会话诊断收集器）。
- 源码工程名 `TobiichiLauncher`，版本 `1.0.0`，使用 `Qt6::Core Gui Qml Quick QuickControls2`，C++20，`qt_add_qml_module(URI Tobiichi)`，QML 资源别名去掉 `qml/` 前缀，`Tema.qml` 注册为 singleton（见 `C:\gow-jpn\launcher\CMakeLists.txt`）。
- 入口 `main.cpp`：`QGuiApplication` + `QQmlApplicationEngine`，把 `Lanzador` 以 `lanzador` 之名注册到根上下文（`engine.rootContext()->setContextProperty("lanzador", &lanzador)`），把标题字体名注册为 `fuenteTitulo`，把 `TOBIICHI_CAPTURA_PESTANA` 注册为 `pestanaInicial`。现成的截图钩子：`TOBIICHI_CAPTURA=<png>` 启动 3 秒后抓窗退出，`TOBIICHI_CAPTURA_PESTANA` 选页签，`TOBIICHI_CAPTURA_ALTO` 调窗口高度。**这是 UI 验收的现成工具，务必沿用。**
- 设置：`Main.qml` 顶部的 `Settings { category: "ajustes" }`，应用组织/名称是 `Tobiichi` / `LauncherUltimate`（`main.cpp` 里显式设置，并从旧的 `Launcher` 迁移键值，排除 elf/ejecutable 两个路径）。Windows 下落在 `%APPDATA%\Tobiichi\LauncherUltimate`。
- 数据目录：`Lanzador::carpetaDatos()` = `QStandardPaths::AppDataLocation`；日志 `registros/ultimo.log`（上一局为 `anterior.log`）；runner 的工作目录就是这个数据目录（`m_proceso->setWorkingDirectory(carpetaDatos())`），不是仓库根目录。**这一点会直接影响 Mod 管理器找仓库根与相对路径，见 5.3。**
- 运行方式：`Lanzador::iniciar(QVariantMap)` 从 QML 收到一个 `ajustes` 映射，合成 `QProcessEnvironment`，`setProgram(ejecutable)`、`setArguments({elf})`、`setProcessEnvironment(entorno)`、`setStandardOutputFile(registro)`，然后 `start()`。退出后 `terminado()` 解析日志尾部，发 `juegoTerminado(codigo, fallo, segundos, resumen)` 信号，QML 弹提示。
- 现有环境变量注入点：`lanzador.cpp` 的 `iniciar()`，从第 343 行开始，依次写 `kEntornoBase`（`PS2X_GS_WORKER=1`、`GOW_GS_FINISH_ASINCRONO=1`、`GOW_AUDIO_DEVICE=default`）、`GOW_SKIP_FMV`、`GOW_FAST_BOOT`、`TOBIICHI_DMC5_CONTROLS`、`TOBIICHI_ESC_SALIR`、`GOW_CANCELAR`、`TOBIICHI_TECLAS`、`TOBIICHI_TRUCOS`、`TOBIICHI_IDIOMA`、窗口/比例/滤镜/锐化、`PS2X_GS_ESCALA`、`PS2X_GS_HW_SCALE`、`PS2X_GS_NITIDO`、`PS2X_GS_ESCALA_DINAMICA`、`PS2X_GS_HW`、帧率/垂直同步/帧计数、`GOW_ISO`、`PS2X_GS_SHADER_CACHE_DIR`、GPU 选择。**Mod 的环境变量应该加在这个函数里，而不是在 QML 里拼。**
- 页面结构：`Main.qml` 里是 `TabBar` + `StackLayout`，共 6 个页签：Gráfico、Rendimiento、Archivos、Controles、Trucos、Otros（`Pestana { text: Tema.t("pestGrafico") }` 等，`StackLayout` 里对应 `PaginaGrafico`…`PaginaOtros`）。**不是设计文档 §20.3 写的 sidebar `NavItem` + `pagina = 9`**；这里没有 `AccessibilityPage.qml`，也没有 `launcher/qml/idiomas/` 目录。以代码为准。
- 本地化：`qml/Textos.js`（`.pragma library`，`var tabla = { key: { tr, en, es }, ... }`），当前只有土耳其语/英语/西班牙语三种；`Tema.t(key)` 取当前语言。`tools/test/launcher-languages.py` 会解析 `Textos.js` 与 `idiomas/*.js`，检查键存在、`%1/%2` 占位符一致；没有 `idiomas/` 时它不会报错，但新增键仍应加进 `Textos.js` 的三种语言。
- 构建：仓库 `build.ps1` 有 `launcher` stage（`tools/pipeline/modules/distribution.ps1`），从**仓库根**的 `launcher/` 目录做 CMake+Ninja；`build.cmd -Stages launcher` 是入口。工作副本缺源码时这个 stage 必然失败，这就是第 0.3 节第一步要补源码的原因。

### 2.3 运行时现状（与 Mod 相关的部分）

- `engine/runtime` 是 PS2Recomp 的克隆，补丁栈 `engine/patches/01..71` 按文件名顺序应用。当前尾部：
  - `67-gs-ring-overflow-guard`：顶点环溢出保护（另一位并行会话的工作）。
  - `68-gs-ring-stall-and-depth-zbp`：环等待与 ZBP 深度测量（并行会话）。
  - `69-gs-depth-per-zbp`：按 ZBP 分深度纹理（并行会话）。
  - `70-gs-gpu-frame-timing`：GPU 时间戳（并行会话）。
  - `71-mod-vfs-hooks`：**本次交付**，运行时半部。
- 纹理包：patch 52 的 `GOW_TEXTURE_PACK` 指向一个目录，运行时按 PCSX2 命名 `<hash>-<pal>-<bits>.png` 查找替换纹理；alpha 128 表示 GS 单位的不透明值；`GOW_TEXTURE_PACK_STATS=1` 打印 `[gs-texpack] hits=... loads=...`；`GOW_TEX_PCSX2_NAMES` 可输出会话里实际使用的纹理名。管理器**不实现**纹理解码，只把合法 PNG 放进 staging 目录并把环境变量指过去。
- VFS：`PS2Vfs::resolveHostPath` 是入口。patch 71 在「原生 host 根」之后、「设备根」之前插入一次 `ModVfsTable::lookup`。表为空时就是一次失败的哈希探测，原路径解析不变；`GOW_MOD_VFS_TABLE` 未设置时表为空。诊断：`GOW_MOD_VFS_STATS`（JSON 计数，运行中与退出时刷新）、`GOW_MOD_VFS_TRACE`（逐条路径追加，被杀也有证据）、`GOW_MOD_VFS_LOG=1`（stderr 打印前若干命中）。
- 既有开关仍然可用：`PS2X_GS_RUN`、`PS2X_GS_PIPELINE`、`GOW_GS_*`、`GOW_VU1_FAST`、`GOW_VU1N_X64` 等；本次没有改它们的语义。

### 2.4 管理器 CLI 现状

`tools/mods/gow_mods_cli.py`（约 1480 行，Python 3.11+，仅标准库），是设计文档 §7.2「Python 可执行规范」的落地。命令：

```
fingerprint | list | validate | import | enable | disable | plan | apply |
deactivate | rollback | status | run | report | selftest
```

数据目录（默认 `data/mods/`，可用 `--mods-dir` 改）：

```
data/mods/
├── packages/<id>@<version>/       已安装的 Mod 包
├── profiles/<name>.toml           启用列表（唯一事实来源）
├── plans/<planId>.json            计划缓存
├── staging/<planId>/              物化后的纹理/ VFS 文件
├── hooks/{env.json,vfs-overrides.tsv,plan.json,profile.txt}
├── journal/<planId>.json          WAL
├── reports/<run>.json             run/report 摘要
├── runs/<stamp>-<label>/          实机运行日志、vfs-stats/trace、截图
├── state.json                     当前激活状态
└── fingerprint.json               上次指纹
```

CLI 的退出码约定（`ManagerError(code)`）：2 = 参数/校验/计划错误，3 = 已存在冲突，4 = 事务/运行记录缺失，5 = runner/ELF 找不到，6 = 没有激活计划。启动器只需根据非零退出码 + stderr 文本提示，不必细分。

### 2.5 文档与代码的冲突登记（必须写进交接）

| 设计文档说法 | 代码现实 | 处理 |
|---|---|---|
| §20.3：`Main.qml` 侧边栏 `NavItem`，`pagina = 9`，不动 0..8 | 实际是 `TabBar` + `StackLayout`，6 个页签；页签由 `TOBIICHI_CAPTURA_PESTANA` 0..5 选 | 以代码为准：新增第 7 个页签（index 6），不重排现有 6 个 |
| §20.3：新增 `ModsPage.qml`，`launcher/qml/idiomas/{fr,de,it,ru,zh}.js` | 实际命名风格是西班牙语 `Pagina*.qml`；没有 `idiomas/`，只有 `Textos.js` 的 tr/en/es | 新页面命名 `PaginaMods.qml`；文案加进 `Textos.js` 三语 |
| §20.4：`AccessibilityPage.qml` 的 `pacoteTexturas`/`usarPacoteTexturas` 要迁移 | 当前启动器没有 Accessibility 页，也没有这两个设置；`GOW_TEXTURE_PACK` 不由启动器写 | 不需要迁移；Mods 页独占 `GOW_TEXTURE_PACK` 即可 |
| §20.2：`engine/runtime/launcher/src/main.cpp:94-95` 注册 `ModsModel` | 实际是 `C:\gow-jpn\launcher\src\main.cpp` 第 94 行注册 `lanzador`；路径是仓库根的 `launcher/`，不是 runtime 里的 launcher | 以实际路径为准 |
| §7.2：C++ 核心 + Python 镜像 | 目前只有 Python CLI；C++ 核心未做 | 分阶段：先薄封装，发布前补 C++（见 5.7） |
| §18.2：补丁名 `67-mod-hooks.patch` | 本次补丁最终是 `71-mod-vfs-hooks.patch`（67/68/69/70 已被并行会话占用） | 以实际文件名和 README 为准 |
| §20.3/§2.7：本副本缺 launcher 源码 | 工作副本确实缺；`C:\gow-jpn\launcher` 有完整源码 | 先取回源码（0.3 第 1 步） |
| 设计文档默认 PCSX2 纹理包「照搬即可」 | 实测：包内 PNG 尺寸小于名字里的 TW/TH（如 64x64 替换 512x512）会让 runner 在过场退出 | CLI 在 `validate` 阶段就拒绝尺寸不符；见 4.4 |

另外两个「并发工作」造成的现实冲突：

1. 补丁编号被并行会话连续占用（67→68→69→70），本次补丁从 67 一路改号到 71 才稳定。**交接后如果再看到新的 71/72，以 `engine/README.md` 表和目录实际文件为准，并在动手前重新确认最大编号。**
2. `data/gow1/regional-builds.json` 的 `runner_sha256` 会被任何一次重编译更新；指纹里的 `patchChainHash` 也会随补丁目录变化。**启动器在每次启动前必须重算指纹**，否则会出现「计划明明应用了、启动却说 stale」的假故障。

---

## 3. Mod 管理器的设计契约（落地版）

这一章把设计文档里与启动器相关的部分压缩成「实现口径」。设计文档更细的论证（为什么不用 xdelta、为什么不做通用管理器）不重复，只保留下一位需要遵守的约束。

### 3.1 三层注入模型（为什么 Mod 不是「改光盘」）

本工程不是模拟器：ISO 里的 ELF 被重编译成 `ps2EntryRunner.exe`，游戏代码是宿主 C++。因此 Mod 不能像 PCSX2 那样改镜像或打 xdelta 补丁，只能在**启动时**注入。实际采用三层：

| 层 | 内容 | 本次是否实现 | 注入点 |
|---|---|---|---|
| L1 | 源码级补丁（`source_patch`），需要重新应用补丁链并重编译 | 否（明确不做） | `engine/patches` + `build.cmd` |
| L2 | 环境变量（画质、音频、玩法开关） | 是 | 启动器/Runner 进程环境 |
| L3 | 资源覆盖（PCSX2 纹理包、guest 文件路径覆盖） | 是 | `GOW_TEXTURE_PACK`、`GOW_MOD_VFS_TABLE` |

L2 是最安全的一层：变量本来就被运行时读取。L3 是「只读覆盖」：VFS 表只把某个 guest 路径改指向 staging 文件，不改设备挂载、不写游戏数据；纹理包只替换纹理名对应的图片，解码仍走 patch 52。**安全默认**靠的是「表为空 / 变量未设置」时行为与改造前完全一致，而不是靠运行时判断「有没有装 Mod」。

### 3.2 `mod.toml` 的实际字段（以实现为准）

```toml
spec = 1
id = "verify.gow.subset"           # 必填，小写 [a-z0-9._-]，2..64 字符
name = "Verification subset"       # 必填，非空
version = "1.0.0"                  # 必填，数字点分，可带 -suffix
type = "content"                   # content / code / mixed；code/mixed 直接报错（不支持）
priority = 0                       # -100..100，数值越大越先应用

[target]
game_id = "gow1"                   # 必填，必须等于 games/gow1/game.toml 的 id
regions = ["asia"]                 # 可选，必须是 game.toml 里存在的 region id
edition = "..."                    # 可选，字符串，必须等于指纹的 edition

[requires]
mods = ["base.mod@1.0.0"]          # 可选，字符串数组；缺失依赖 → 计划错误

[conflicts]
mods = ["other.mod"]               # 可选，声明冲突；先按 rank 淘汰一方

[env]
GOW_SCALER = "sharp"               # 只允许 ENV_ALLOWED 里的键；值 ≤64 字符、不能含换行

[textures]
dir = "textures"                   # 目录内 *.png，文件名必须是 PCSX2 名

[vfs]
"cdrom0:\\LIBSD.IRX" = "payload/vfs/LIBSD.IRX"
```

关键限制（全部在 `validate_package` 中实现）：

- `id` 必须匹配 `^[a-z0-9][a-z0-9._-]{1,63}$`；版本必须匹配数字点分；安装目录名必须是 `<id>@<version>`（否则 warn，便于发现重复安装）。
- `type` 为 `code`/`mixed` → error：函数覆盖需要把宿主符号编进 runner，本次不交付。
- manifest 里出现 `pak`、`function`、`script` 段 → error（原因写在 `UNSUPPORTED_SECTIONS`：PAK 重映射需要光盘 TOC，IOP 按 LBA 读而不是按路径；函数覆盖需要编译进去；guest 脚本是游戏自己解析的数据，没有按路径替换的钩子）。
- `env`：键必须在 `ENV_ALLOWED`，不能是 `ENV_RESERVED`（管理器自己的 staging/诊断变量、测试钩子、`GOW_TEXTURE_PACK`、`GOW_MC0`、`GOW_SAVES_DIR` 等），否则 error。`ENV_ALLOWED` 的值分 `visual`/`behaviour`/`engine`/`diagnostic`；`engine` 与 `diagnostic` 只给 warn，因为「改引擎开关的 Mod」本质上不是内容 Mod，但仍允许玩家自己承担。
- `textures`：文件名必须匹配 `^[0-9a-f]+-[0-9a-f]+(?:-[0-9a-f]+)?$`；每张图必须通过内联 PNG 结构校验（签名、IHDR、IDAT、crc、zlib 解压）；目录/文件不能是符号链接，不能越出包目录。
- `vfs`：guest 路径必须匹配 `^(?:(?:cdrom0|cdrom|host|mc0|mc1|rom0):|(?:[A-Za-z0-9_.-]+[\\/])+)`；payload 必须是包内普通文件，不能是符号链接、不能是 `.exe/.dll/.bat/.cmd/.ps1/.com/.scr/.msi`。
- 包内文件数量 ≤4096，单文件 ≤256 MB，总计 ≤2 GB；最多 256 个已安装包（扫描上限）。

`settings` 段（设计文档 §10.4 的用户覆盖）在本次实现中没有做。Mod 的环境变量是「包作者定值」，玩家想覆盖只能改 profile/后续在 UI 里做覆盖层。这一点在界面上要避免误导：不要显示「可在界面调整」的开关，除非真的实现了。

### 3.3 指纹与兼容性

`fingerprint` 由 7 个字段 + 1 个 runner 哈希组成：

```json
{
  "gameId": "gow1",
  "edition": "<regional-builds.json builds[0].region>",
  "region": "<builds[0].code>",
  "elfCrc": "<builds[0].elf_crc 大写>",
  "textSha1": "<builds[0].text_sha1>",
  "runtimeCommit": "<git -C engine/runtime rev-parse HEAD>",
  "patchChainHash": "<所有 engine/patches/*.patch 按名排序后的 sha256>",
  "fingerprintId": "<上述 7 字段稳定 JSON 的 sha256>",
  "runnerSha256": "<builds[0].runner_sha256>"
}
```

注意：

- `fingerprintId` **不包含** `runnerSha256`。这样重编译 runner 不会让计划失效，但 `patchChainHash` 变化会让计划失效（因为补丁可能改变资源行为）。
- `patchChainHash` 包含**所有**补丁文件的内容，包括并行会话刚加的补丁。因此并行开发期间计划会频繁变 stale，这是设计行为，不是 bug。
- `ensure_fingerprint` 每次运行都会把当前指纹写入 `data/mods/fingerprint.json` 并返回 `changed`；`apply` 不会自动因为 stale 而重算（`build_plan` 会重新算指纹并写进 plan），但 `run` 会检测 `state.fingerprintId != 当前` → 自动 `deactivate` 并报「no active plan」。启动器必须显式处理这个分支：**要么在启动前重算并重新 apply，要么提示玩家「游戏文件/补丁变了，请重新应用」**。

### 3.4 顺序、优先级与冲突

排序算法（`resolve_order`）：

1. 依赖图做拓扑排序（`requires.mods` 是「被依赖者先应用」）。
2. 同一层可用的 Mod 按 `rank_of` 排序：`(-priority, id, -version)`，即 priority 大的先，同 priority 按 id，再按版本降序。
3. 检测环：剩余未排序的节点标记 `requires.cycle` error。

冲突/覆盖规则（`build_plan` 遍历排序结果，先到先得）：

- 同一 `env` 键被两个 Mod 设成不同值：后到的被跳过，记录 `env.shadowed` warning 和 `conflicts` 条目；值相同则合并。
- 同一 guest 路径：后到的跳过，`vfs.shadowed` warning。
- 同一纹理名：后到的跳过，`texture.shadowed` warning。
- 声明式冲突（`conflicts.mods`）：按 `rank_of` 淘汰 rank 较低的一方（注意 `rank_of` 越小越优先），记 `declared conflict` 与 `excluded`。
- 区域/版本不匹配：`excluded`，原因写清楚。
- 校验失败的包：直接 `excluded`（reason `validation failed`），不会进入 plan 的 `mods`。

这套规则是「确定性」的：同样的包集合、同样的 profile、同样的指纹，`planId` 一定相同（因为 plan payload 里含每个资源的内容 sha256，见 `build_plan`）。`planId` = 稳定 JSON（键排序、无空格）的 sha256。启动器可以用它判断「当前激活的是不是这份计划」。

### 3.5 安全边界（实现里已经做的）

- 路径穿越：`resolve_dir`/`resolve_payload` 都用 `resolve()` 后 `relative_to(base)` 检查，拒绝绝对路径、`..` 逃逸、符号链接。
- 可执行 payload：按扩展名拒绝。
- PNG：结构解码校验，避免「raylib 在运行时才发现坏图」。
- 数量/体积上限：见 3.2。
- 环境变量：白名单 + 保留键 + 长度限制，未知键直接 error（不静默无效）。
- 空计划：`apply` 在「profile 里启用了 Mod 但全被排除」时拒绝，除非 `--allow-empty`。这是为了防止玩家以为启用了、实际什么都没加载。
- 原子写：所有 JSON/TOML 都是「写临时文件 → fsync → `os.replace`」，Windows 被杀毒/索引短暂占用时重试 6 次（`atomic_write`、`_replace_dir`）。
- 事务：`activate` 先写 journal（记录 hooks 目录与 state 的旧内容），再物化 staging、写 hooks、写 state；任何一步异常都 `restore` 回旧 hooks/state 并删除 staging。

### 3.6 明确降级/不做的部分

| 设计文档要求 | 本次 | 原因 |
|---|---|---|
| `.PAK` 重映射 | 不做 | IOP 按 LBA 读，运行时没有按路径拦截 PAK 的钩子；伪造 PAK 格式会违反「禁止编造资源格式」 |
| `function_override` | 不做 | 需要把替换函数编进 runner，属于 L1/重编译，不是运行时可插拔 |
| 脚本/文本替换 | 不做 | 游戏自己解析；没有按路径替换的钩子 |
| 存档 Mod | 不做 | 存档是二进制卡镜像，格式未逆向到可安全重写 |
| 音频替换 | 部分（仅 VFS 路径级，如 `.IRX`/bank 文件） | 音频流由 SPU2 解码，没有单独格式替换钩子；VFS 能覆盖文件本身 |
| 用户设置覆盖（`settings`） | 不做 | 需要额外 UI 与覆盖层，本次优先级低于启动器接线 |
| L1 源码补丁 Mod | 不做 | 会触发重编译，设计文档也把它列为独立阶段 |
| 通用多游戏 | 不做 | 指纹、地址表、变量前缀都绑定 `gow1`；通用化收益接近零 |

---

## 4. 已实现代码地图（改之前先读这一章）

### 4.1 `tools/mods/gow_mods_cli.py`

这是唯一的「核心实现」。按职责分块：

| 区块 | 关键函数 | 说明 |
|---|---|---|
| 常量 | `SCHEMA`、`MAX_*`、`ENV_ALLOWED`、`ENV_RESERVED`、`UNSUPPORTED_SECTIONS` | 所有限制集中在这里；加白名单键要同时确认 runtime 真的 `getenv` 读取 |
| 工具 | `atomic_write`、`atomic_write_json`、`load_toml`、`digest`、`sha256_file`、`canonical_guest_path` | `canonical_guest_path` 必须与 C++ 的 `gow::mods::canonicalGuestPath` 保持一致 |
| 模型 | `Issue`、`Package`、`Context` | `Context` 在构造时创建 `data/mods/*` 全部子目录 |
| 指纹 | `gather_fingerprint`、`ensure_fingerprint` | 读 `data/gow1/regional-builds.json` 的 `builds[0]` 与 `games/gow1/game.toml` |
| 发现/校验 | `resolve_dir`、`resolve_payload`、`validate_png`、`texture_expected_size`、`validate_package`、`scan_packages` | `texture_expected_size` 解析 PCSX2 名的 bits 字段 |
| Profile/Plan | `read_profile`、`write_profile`、`select_enabled`、`expand_dependencies`、`resolve_order`、`build_plan`、`describe_plan` | `build_plan` 输出 `plan.json` 并写 plans 目录 |
| 激活 | `hooks_snapshot`、`write_hooks`、`materialize`、`activate`、`restore`、`deactivate` | journal 是 `journal/<planId>.json`；`restore` 用 journal 的 `previous` 快照 |
| 命令 | `cmd_*` 共 13 个 | 见 2.4 |
| 自检 | `cmd_selftest` | 在临时目录造好坏包、验校验、plan、staging；不需要游戏数据 |

几个容易踩的实现细节：

- `materialize` 每次先 `rmtree(staging)` 再重建，避免上一次的残留在新计划里「复活」。
- 纹理 staging 用 `os.link`（硬链接），失败才 `copy2`；因此 staging 与包内文件共享 inode，**不要**在激活后修改包内 PNG。
- VFS staging 目录名是 `digest(guest)[:16]`，文件名保留原文件名；`vfs-overrides.tsv` 里写的是 staging 的绝对路径（`resolve()`），所以 `data/mods` 不能整体搬到别的盘后继续用旧 plan（重新 apply 即可）。
- `write_hooks` 里 `env.json` 只存 Mod 的 env；`plan.json` 存整份计划；`profile.txt` 存 profile 名（给外部工具看）。
- `run` 会设置 `GOW_MOD_VFS_STATS/TRACE` 指向本次 run 目录，并在结束时把 `vfs-stats.json` 合并进 `run.json`；启动器不走 `run` 时，需要自己设置同类诊断路径，否则没有命中统计。

### 4.2 `engine/runtime/.../mod_vfs_table.h/.cpp`

接口：

```cpp
class ModVfsTable final {
public:
    static const ModVfsTable &instance();
    bool active() const { return !m_table.empty(); }
    bool lookup(std::string_view guestPath, std::filesystem::path &result) const;
private:
    std::unordered_map<std::string, std::string> m_table;
    mutable std::atomic<uint64_t> m_lookups{0};
    mutable std::atomic<uint64_t> m_hits{0};
    ...
};
std::string canonicalGuestPath(std::string_view path);
```

行为：

- 首次 `lookup` 时读取 `GOW_MOD_VFS_TABLE` 指向的文件：`#` 注释、`\t` 分隔、最多 4096 行；开头打印 `[mod-vfs] N overrides from <path>`。
- 键用 `canonicalGuestPath`：ASCII 小写、`\`→`/`、去前导/重复分隔符、去末尾 `;N`。两侧都做，所以游戏用 `cdrom0:\LIBSD.IRX;1` 也能命中表里的 `cdrom0:/libsd.irx`。
- 命中返回 host 绝对路径；未命中返回 false，调用方继续用设备根解析。
- 可选诊断：`GOW_MOD_VFS_STATS`（JSON：overrides/lookups/hits/misses，运行中与退出时刷新）、`GOW_MOD_VFS_TRACE`（逐条 `H\t`/`M\t` 即时 flush，上限 4096）、`GOW_MOD_VFS_LOG=1`（前若干条打印到 stderr）。
- 表只读，不校验 host 文件是否存在（由 CLI 在激活前保证）；如果文件在运行中被删，游戏会得到打开失败，行为与「缺资源」一致，不会崩。

### 4.3 `ps2_vfs.cpp` 的钩子位置

`PS2Vfs::resolveHostPath` 的顺序：

1. 原生 host 根（`host0:` 等）解析成功 → 返回。
2. **patch 71 插入点**：`ModVfsTable::instance().lookup(path, modPath)`，命中 → 返回。
3. 设备根（cdrom/mc/rom）按原逻辑解析。

这个顺序保证：

- 未设置表时只多一次失败哈希探测，行为不变。
- 原生 host 路径不会被 Mod 覆盖（玩家自己给的绝对路径优先）。
- 设备路径可以被 Mod 覆盖，但只在表里显式列出的路径。

### 4.4 纹理名与尺寸规则（实测得出的硬约束）

PCSX2 纹理包文件名 `<hash>-<pal>-<bits>.png`。`bits` 是十六进制，位段：

```
bits = PSM | (TW << 6) | (TH << 10)
期望宽 = 1 << ((bits >> 6) & 0xF)
期望高 = 1 << ((bits >> 10) & 0xF)
```

例：`...-00002253.png` → `bits=0x2253`，TW=(0x2253>>6)&0xF=9 → 512，TH=(0x2253>>10)&0xF=8 → 256，所以期望 512×256。

**2026-11-05 实测**：把 512×512 的 GS 纹理替换成 64×64 的 PNG，runner 会在 intro cutscene 处退出（两次复现，42–56 秒；严格子集 7 张大纹理也复现）。改成与名字 TW/TH 一致的尺寸后，200 秒运行通过。因此 CLI 在 validate 阶段就报 `textures.size` error。这不是编造的规则，是实测证据；如果未来要支持缩放，必须先改运行时绑定逻辑并重新验证，不能在管理器里放宽。

### 4.5 示例 Mod（验证夹具，不是内容）

`data/mods/packages/verify.gow.subset@1.0.0/`：

- `mod.toml`：`id=verify.gow.subset`、`version=1.0.0`、`type=content`、`priority=0`、`[target] game_id=gow1`。
- `payload/textures/`：7 张纯品红 RGBA PNG（alpha=128），文件名来自基线会话实际用到的 PCSX2 纹理名，尺寸与名字 TW/TH 一致（512×512 与 512×256）。
- `payload/vfs/LIBSD.IRX`：从日版光盘提取的 `LIBSD.IRX` 字节副本，映射到 guest `iop_mod\libsd.irx`，用来验证 patch 71 的 VFS 命中。
- 生成器 `tools/mods/make_verify_mod.py` 可重建；**IRX 是游戏数据，不能随发行包分发**。

这个夹具的目的只有一个：让「纹理替换 + VFS 覆盖」两条 L3 路径都在真实游戏里被走到。它不是给玩家的示例内容。

### 4.6 补丁 71 与 README

`engine/patches/71-mod-vfs-hooks.patch`（320 行，LF）包含：

- 新增 `PS2Recomp/ps2xRuntime/include/runtime/mod_vfs_table.h`（75 行）。
- 新增 `PS2Recomp/ps2xRuntime/src/lib/mod_vfs_table.cpp`（187 行）。
- `ps2_vfs.cpp` 一行 include + 一个 lookup 块。
- `CMakeLists.txt` 一行源文件。
- 头部注释说明为什么是「只读查找」而不是新格式。

`engine/README.md` 的补丁表已新增 `71-mod-vfs-hooks` 行，记录实测证据与纹理尺寸约束。**补丁链可以从干净源码重建**：`git apply` 按名顺序应用 01..71 即可；71 的生成脚本在 `data/_tmp/make_patch71.py`（临时文件，交接前可删，但生成逻辑值得保留在文档里）。

### 4.7 验证运行记录

`data/mods/runs/` 下每次运行都有：

- `stderr.log` / `stdout.log`：runner 原始输出。
- `run.json`：标签、profile、mods、planId、fingerprintId、秒数、exitCode、timedOut、envApplied、vfsStats。
- `vfs-stats.json` / `vfs-trace.txt`：patch 71 的诊断。
- `shots/`：本次整理时补存的 PPM/PNG 截图（`gow_pad_test_*.ppm` 由 `GOW_PAD_CAPTURAS` 写出，位于光盘目录，运行后复制进来）。

关键 run 目录：

| 目录 | 内容 |
|---|---|
| `20261105-041240-gameplay-ok` | 改号前的 200 秒启用 Mod 成功运行（7 纹理 + VFS，`state=11`，65.25 s 进玩法） |
| `20261105-053134-v69-off` | 71 版二进制、`--no-mods` 200 秒基线（44.44 s 进玩法，4 张截图） |
| `20261105-053535-v69-on` | 71 版二进制、启用示例 Mod（47.36 s 进玩法，`[mod-vfs] 1 overrides`、`hits=1`、`[gs-texpack] 7 images`、`hits=4856 loads=7`，184.65 s 被外部终止） |
| 更早的 `after-disable` / `baseline3` | 禁用后恢复与基线，日志无 Mod 钩子、画面正常 |

（run 目录名里的 `v69` 是当时补丁号 69 的标签；71 只是改号，二进制逻辑相同。）

---

## 5. 启动器集成方案（核心章节）

### 5.1 目标形态与最小闭环

启动器需要提供三件事，按优先级排列：

1. **看见**：列出已安装 Mod、是否启用、是否兼容、冲突与排除原因。
2. **选择**：勾选/取消，写入 profile；支持导入包、打开目录、撤销。
3. **启动**：点「开始游戏」时，保证「当前 profile 的计划已激活」，把计划的环境变量注入 runner；失败就阻止启动并给出原因。

最小闭环（Phase 1）只做第 1、2、3 的直线路径：

```
玩家打开启动器
  → ModsModel 载入 data/mods（list --json）
  → 玩家勾选某个 Mod
      → 写 profiles/<name>.toml（enable/disable）
      → 立即 plan（可选，用于显示冲突）
  → 点「开始游戏」
      → 重新 fingerprint
      → 若 state.activePlan 缺失或 fingerprint 不匹配 → apply（失败则弹窗，不启动）
      → 读取 hooks/plan.json + state.json，合成 env
      → Lanzador::iniciar(settings, envMods)
      → 启动后照旧
```

Phase 1 不需要原生 C++ 核心，也不需要每次启动都跑 Python：**Python 只在「改启用状态」和「apply」时跑**；点 Play 时如果状态已经匹配，只读 JSON 即可。这样启动延迟几乎为零，也避免 runner 已经启动后 Python 还在跑。

Phase 2 再加：导入、冲突详情、指纹差异、回滚、报告、日志查看、批量启用/禁用。

Phase 3 再把 Python 核心移植成 C++ 静态库，解决发行包不能依赖玩家装 Python 的问题。

### 5.2 三条技术路线与选择

| 路线 | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A. 启动器只读 `hooks/` JSON | ModsModel 直接读 `plan.json`、`state.json`、`vfs-overrides.tsv` | 启动零延迟、无 Python 依赖、最简单 | 改启用状态仍需跑 CLI（或自己写 TOML） | **Phase 1 的启动路径用它** |
| B. 每次 Play 调 CLI `apply`/`env` | QProcess 跑 `python gow_mods_cli.py apply`，解析 stdout | 与 CLI 行为完全一致、不易分叉 | 需要 Python；启动多几十毫秒；错误处理要健壮 | **Phase 1 的管理路径用它** |
| C. 原生 C++ `gow_mods` | 把 planner/applier 移植进 `gow-launcher.exe` | 无 Python、类型安全、可发布 | 工程量大、要与 Python 版产出同一 `planId` | **Phase 3** |

推荐组合：**A（启动注入） + B（管理操作） → 逐步替换为 C**。这也是设计文档 §7.2「混合双层」的务实落地：先用 Python 作为可执行规范，再移植。

### 5.3 三个必须先解决的工程问题

#### 5.3.1 启动器怎么找到仓库根

`Lanzador::carpetaDatos()` 是 `QStandardPaths::AppDataLocation`，runner 的工作目录也是那里。而 `data/mods`、`tools/mods/gow_mods_cli.py`、`games/gow1/game.toml` 都在**安装/仓库根**。因此不能在 `iniciar()` 里用 `currentPath()` 找 CLI。

建议在 `ModsModel` 里实现 `repoRoot()`：

```cpp
QString ModsModel::repoRoot()
{
    // 优先显式设置（开发/测试用；也方便 CI 指定临时仓库）
    const QByteArray env = qgetenv("GOW_MODS_REPO");
    if (!env.isEmpty() && QDir(QString::fromLocal8Bit(env)).exists())
        return QDir::cleanPath(QString::fromLocal8Bit(env));

    // 与 Lanzador::rutasDetectadas 相同的「向上找 6 层」策略：
    // 从 exe 所在目录开始，找 tools/mods/gow_mods_cli.py 与 games/gow1/game.toml。
    QDir dir(QCoreApplication::applicationDirPath());
    for (int level = 0; level < 7; ++level)
    {
        if (QFileInfo::exists(dir.absoluteFilePath(QStringLiteral("tools/mods/gow_mods_cli.py"))) &&
            QFileInfo::exists(dir.absoluteFilePath(QStringLiteral("games/gow1/game.toml"))))
            return dir.absolutePath();
        if (!dir.cdUp())
            break;
    }
    return {};
}
```

如果找不到，界面上要显示「安装目录不完整」而不是默默失败。发行包至少要有 `tools/mods/`、`games/gow1/`、`data/`（可写）。

#### 5.3.2 Python 解释器

开发机上 `python` 在 PATH 里；发行机上不一定。建议：

```cpp
QString ModsModel::python()
{
    const QByteArray explicitPath = qgetenv("GOW_PYTHON"); // 玩家/测试可覆盖
    if (!explicitPath.isEmpty())
        return QString::fromLocal8Bit(explicitPath);
    // Windows 下优先 python.exe，再试 py -3（后者需要不同的参数形式，见下）
    return QStringLiteral("python");
}
```

`QProcess` 启动时设置 `setProgram(python())`、`setArguments({"-I", cliPath, ...})`。如果 `QProcess::FailedToStart` 或 stderr 显示 `ModuleNotFoundError`，在 UI 里给出「此版本需要 Python 3.11+，或安装原生版启动器」的明确提示。**不要**在失败时静默降级成「无 Mod 启动」，那会让玩家以为 Mod 生效了。

更稳的做法（Phase 2）：把 CLI 用 PyInstaller / `python -m zipapp` 打成单文件，随 `launcher/bin/tools/` 分发；或用 `QStandardPaths::findExecutable("python")` + 版本探测。注意 Windows Defender 对 PyInstaller 单文件误报较多，若采用要签名/加白说明。

#### 5.3.3 工作目录与相对路径

CLI 的 `--repo` 必须显式传仓库根；`--mods-dir` 用默认 `data/mods` 即可。调用时设置 `process.setWorkingDirectory(repoRoot)`，避免 CLI 内部相对路径行为依赖启动器的工作目录。

`data/mods` 必须可写。如果安装目录在 Program Files 且无写权限，Mod 管理会失败。启动器应在启动时检测 `data/mods` 是否可写，给出「请以管理员运行或把游戏安装到可写目录」的提示（或把 `--mods-dir` 指到 `AppData`，但那样指纹与 hooks 路径也会变，需整体迁移）。

### 5.4 `ModsModel` 设计（建议直接照此实现）

文件：`launcher/src/mods/mods_model.h` / `.cpp`，注册名 `mods`。

```cpp
class ModsModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString profile READ profile WRITE setProfile NOTIFY profileChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool stale READ stale NOTIFY statusChanged)
    Q_PROPERTY(QString statusText READ statusText NOTIFY statusChanged)
    Q_PROPERTY(int enabledCount READ enabledCount NOTIFY modsChanged)
    Q_PROPERTY(QVariantList mods READ mods NOTIFY modsChanged)
    Q_PROPERTY(QVariantList conflicts READ conflicts NOTIFY statusChanged)
    Q_PROPERTY(QVariantList excluded READ excluded NOTIFY statusChanged)

public:
    explicit ModsModel(QObject *parent = nullptr);

    QString profile() const;
    void setProfile(const QString &name);
    bool busy() const;
    bool stale() const;
    QString statusText() const;
    int enabledCount() const;
    QVariantList mods() const;
    QVariantList conflicts() const;
    QVariantList excluded() const;

    Q_INVOKABLE void refresh();                       // list + status + plan（异步）
    Q_INVOKABLE void setEnabled(const QString &label, bool on); // enable/disable + refresh
    Q_INVOKABLE void applyProfile();                  // plan + apply
    Q_INVOKABLE void deactivate();
    Q_INVOKABLE void importPackage(const QString &folder);
    Q_INVOKABLE void openModsFolder();
    Q_INVOKABLE QString lastError() const;

    // 供 Lanzador::iniciar 调用：保证「当前 profile 已激活」，返回要注入的 env。
    // 失败时返回空 map 并设置 lastError；调用方必须阻止启动。
    QMap<QString, QString> prepareSession(QString *error);

signals:
    void profileChanged();
    void modsChanged();
    void statusChanged();
    void busyChanged();
    void error(const QString &message);
};
```

实现要点：

- 所有 CLI 调用走一个私有 `runCli(args, timeoutMs)`，同步等待（`QProcess::waitForFinished`），因为管理操作是用户点击触发的，几秒钟可接受；UI 用 `busy` 属性显示转圈。
- 解析 JSON 用 `QJsonDocument`。`list --json` 返回数组，每项含 `mod/name/type/priority/capabilities/valid/enabled/issues`；`plan --json` 返回完整 plan（含 `mods/env/vfs/textures/excluded/conflicts/warnings/issues`）。
- **不要**在 QML 里拼命令或解析 JSON；QML 只绑属性、调 `Q_INVOKABLE`。
- `prepareSession()` 的逻辑：

```cpp
QMap<QString, QString> ModsModel::prepareSession(QString *error)
{
    error->clear();
    const QString root = repoRoot();
    if (root.isEmpty()) { *error = tr("Install folder is incomplete (tools/mods missing)."); return {}; }

    // 1) 先读现有状态做快速判断（避免每次 Play 都起 Python）
    const QJsonObject state = readJson(root + "/data/mods/state.json");
    const QJsonObject plan = readJson(root + "/data/mods/hooks/plan.json");
    const QString profile = m_profile;

    // 2) 指纹是否匹配：state.fingerprintId == plan.fingerprintId，且 plan.profile == profile
    //    这里不主动重算指纹（重算是 apply 的职责）；如果玩家刚改过补丁/重编译，apply 会更新。
    if (state.value("activePlan").toString() == plan.value("planId").toString()
        && plan.value("profile").toString() == profile
        && state.value("fingerprintId").toString() == plan.value("fingerprintId").toString())
    {
        return envFromPlan(root, plan, state);
    }

    // 3) 否则 apply（plan 由 apply 内部重算）
    QStringList args = {"-I", cliPath(root), "apply", "--repo", root, "-p", profile};
    if (!runCli(args, 30000, error))
        return {};

    // 4) apply 成功后重新读 hooks/state 并合成 env
    const QJsonObject newPlan = readJson(root + "/data/mods/hooks/plan.json");
    const QJsonObject newState = readJson(root + "/data/mods/state.json");
    if (newPlan.isEmpty() || newState.value("activePlan").toString().isEmpty())
    {
        *error = tr("The plan was applied but the hooks are missing.");
        return {};
    }
    return envFromPlan(root, newPlan, newState);
}
```

`envFromPlan` 的规则（与 CLI `plan_hook_env` 等价）：

```cpp
QMap<QString, QString> ModsModel::envFromPlan(const QString &root, const QJsonObject &plan, const QJsonObject &state)
{
    QMap<QString, QString> env;
    for (auto it = plan["env"].toObject().begin(); it != plan["env"].toObject().end(); ++it)
        env.insert(it.key(), it.value().toObject().value("value").toString());

    const QString staging = state.value("staging").toString();
    if (!plan["textures"].toObject().isEmpty() && !staging.isEmpty())
        env.insert("GOW_TEXTURE_PACK", staging + "/textures");
    if (!plan["vfs"].toObject().isEmpty())
        env.insert("GOW_MOD_VFS_TABLE", root + "/data/mods/hooks/vfs-overrides.tsv");
    return env;
}
```

注意：`GOW_MOD_VFS_TABLE` 只在 plan 有 VFS 覆盖时才设置。空表虽然也安全，但「不设置」更能保证原版行为，也便于日志里判断「这次到底有没有 Mod」。

- `setEnabled` 先调 `enable`/`disable` 改 profile，再 `refresh()`。**不要**由 QML 自己维护勾选状态；profile 是唯一事实来源，避免 UI 与磁盘不一致。
- `importPackage` 调 `import --replace`（如果玩家确认覆盖）；导入成功后再刷新列表。
- `deactivate` 调 CLI 并刷新状态；界面上显示「未启用任何 Mod」。
- `refresh()` 的 `plan` 调用只是「预演」，不写 hooks；它能让界面提前显示冲突/排除原因。真正的写入只发生在 `apply`。

### 5.5 `Lanzador::iniciar` 的改动点

现状：`iniciar(const QVariantMap &a)` 里自己构造 `QProcessEnvironment`。最小改动是给它加一个可选的第二个参数：

```cpp
// lanzador.h
Q_INVOKABLE bool iniciar(const QVariantMap &ajustes);
// 新增（不破坏 QML 现有调用）：
bool iniciar(const QVariantMap &ajustes, const QMap<QString, QString> &entornoMods,
             QString *error);
```

或者保持签名不变，在 `Lanzador` 里持有一个 `ModsModel*`，在 `iniciar` 开头调用 `m_mods->prepareSession(&error)`。后者对 QML 改动更小，但把「Mod 逻辑」耦合进 `Lanzador`。推荐前者：`Main.qml` 的 `jugar()` 先调 `mods.prepareSession`，成功后再 `lanzador.iniciar(a, envMods)`。

`iniciar` 里的插入位置：**在所有既有环境变量设置之后、`m_proceso->start()` 之前**，逐个 `entorno.insert(key, value)`。如果 key 已经存在（例如玩家手动设了 `GOW_TEXTURE_PACK`），Mod 的值应覆盖它——因为这是玩家在启动器里明确启用的 Mod；但要在界面/日志里提示「已有环境变量被 Mod 覆盖」。更保守的做法是检测冲突并拒绝启动，让玩家先清理环境。**推荐拒绝并提示**，因为 `GOW_TEXTURE_PACK` 被两个来源同时设置时行为很难解释。

错误处理：

```cpp
if (!modsEnvReady)
{
    emit error(QStringLiteral("errorMods"), errorText);
    return false;
}
```

QML 已有的 `onError` 处理会显示提示；确保 `jugar()` 在 `iniciar` 返回 false 时不最小化窗口、不显示「运行中」。

### 5.6 页签与页面

`Main.qml` 的改动面：

1. `Settings` 里加 `property string modsProfile: "default"`（或 "verify"）；`property bool modsEnabled: true`（全局开关，给「临时无 Mod 启动」用）。
2. `function jugar()` 里先 `mods.prepareSession()`，再构造 `a`，再 `lanzador.iniciar(a, modsEnv)`。
3. `TabBar` 末尾加 `Pestana { text: Tema.t("pestMods") }`；`StackLayout` 末尾加 `PaginaMods { mods: mods; ajustes: ajustes }`。**保持新增页签在最后（index 6）**，现有 0..5 的编号与截图脚本不变。
4. 页签高度/宽度沿用现有布局，不需要改 sidebar（没有 sidebar）。

`PaginaMods.qml` 结构建议（沿用现有控件）：

```
ScrollView
├── 顶部状态条（Rectangle + RowLayout）
│     ├── 状态文字：已启用 N 个 / 未启用 / 指纹过期 / 有冲突
│     ├── BotonSecundario「重新扫描」
│     └── BotonSecundario「禁用全部」
├── 冲突/排除提示区（visible: conflicts.length > 0 || excluded.length > 0）
│     └── Repeater + Fila（只读，显示 mod 与原因）
├── Repeater（mods）
│     └── Fila
│           ├── titulo: name + label
│           ├── descripcion: capabilities + priority + 兼容性
│           ├── Interruptor { checked: modelData.enabled; onToggled: mods.setEnabled(modelData.mod, checked) }
│           └── 错误徽标（modelData.issues 里 severity=error）
└── 底部按钮行
      ├── BotonSecundario「导入 Mod…」 → CampoRuta / FileDialog
      ├── BotonSecundario「打开 Mods 目录」
      └── BotonSecundario「应用计划」
```

视觉规范：`Tema.fondo #0a0605`、`Tema.panel #cc140c0a`、`Tema.oro #d4a857`、`Tema.rojo #b0221a`、`Tema.texto`/`Tema.textoSuave`/`Tema.textoTenue`；行距与 `Fila` 一致；不要硬编码中文（走 `Tema.t`）。

导入：现有 `CampoRuta` 支持目录选择（`soloCarpeta: true`），可以直接用它选一个 Mod 包目录，再调 `mods.importPackage(ruta)`。不要自己写文件对话框。

### 5.7 发布形态与 Python 依赖（必须提前决定）

设计文档 §7.2 要求最终是 C++ 核心 + Python 镜像。当前实现只有 Python，因此：

- **开发期**（现在）：启动器依赖系统 `python`。工作副本的开发机上可用；CI/打包机需要确保 Python 3.11+。
- **发行期**：两条路
  1. 打包 Python 运行时（嵌入式 zip + `python3xx.dll`，约 10–20 MB），启动器调自带解释器；优点是不用重写核心，缺点是要处理路径/杀毒误报/许可。
  2. 移植 C++ 核心（Phase 3）；优点是干净、启动快、与 launcher 同构建系统；缺点是要保证与 Python 版产出**完全相同的 planId**。

建议排期：Phase 1 先用方案 1（或开发期直接依赖系统 Python），把 UI 与流程跑通；Phase 3 再做 C++。不要在 Phase 1 同时写两套核心，否则冲突/回归成本会翻倍。

### 5.8 会话报告（Phase 2）

启动器启动 runner 时不走 CLI `run`，因此默认没有 `data/mods/runs/<stamp>`。建议：

- 在 `ModsModel::prepareSession` 成功后，写一份 `data/mods/reports/session-<timestamp>.json`：`planId`、`fingerprintId`、profile、启用的 id/version、capabilities、纹理数量、VFS 数量、冲突数量。**不要**写绝对路径、ELF/ISO 路径、环境变量全量 dump（设计文档 §20.5 的白名单）。
- 给 runner 设置 `GOW_MOD_VFS_STATS=<AppData>/mods-vfs-stats.json`、`GOW_MOD_VFS_TRACE=<AppData>/mods-vfs-trace.txt`，退出后解析 `overrides/lookups/hits`，追加到会话报告。
- 纹理命中：runner 已有 `GOW_TEXTURE_PACK_STATS`，输出 `[gs-texpack] hits=... loads=...` 到日志；`terminado()` 里从 `registro` 解析最后一行即可。
- 报告导出严格按白名单；`tools/test/session-game-smoke.py` 会断言导出不含 `.ps2/.iso/.ppm`，新增文件不要破坏这条。

---

## 6. 文件级实施步骤（照做即可）

### 6.1 Phase 0：把启动器源码放回工作副本

在 PowerShell 中（工作副本根目录）：

```powershell
Copy-Item -Recurse -Force C:\gow-jpn\launcher\src       .\launcher\src
Copy-Item -Recurse -Force C:\gow-jpn\launcher\qml       .\launcher\qml
Copy-Item -Recurse -Force C:\gow-jpn\launcher\recursos  .\launcher\recursos
Copy-Item -Force        C:\gow-jpn\launcher\CMakeLists.txt .\launcher\CMakeLists.txt
```

保留 `launcher\bin` 与 `launcher\bin-backup-20261104` 不动。然后构建：

```powershell
.\build.cmd -Stages launcher
```

或者按 `launcher/CMakeLists.txt` 顶部注释手工构建（需要 Qt 6.5+ 与 Ninja）：

```powershell
cmake -S launcher -B launcher/build -G Ninja -DCMAKE_BUILD_TYPE=Release
ninja -C launcher/build
```

首次构建可能很慢（Qt 元对象/QML 编译）。构建完成后先跑现成截图钩子确认 UI：

```powershell
$env:TOBIICHI_CAPTURA = "$PWD\data\_tmp\launcher-before.png"
$env:TOBIICHI_CAPTURA_PESTANA = "0"
.\launcher\build\gow-launcher.exe
```

注意：`build.ps1` 的 `launcher` stage 用的是 `data/_tools` 里的 Qt 源码/工具链与 `launcher/build-clang`，与手工 `launcher/build` 不是同一个目录；选一种并保持一致，不要两个目录混用。

### 6.2 Phase 1：C++ 薄封装

新增文件：

- `launcher/src/mods/mods_model.h`
- `launcher/src/mods/mods_model.cpp`
- `launcher/qml/PaginaMods.qml`

修改文件：

- `launcher/CMakeLists.txt`：`qt_add_executable` 加 `src/mods/mods_model.cpp src/mods/mods_model.h`；`ARCHIVOS_QML` 加 `qml/PaginaMods.qml`。
- `launcher/src/main.cpp`：创建 `ModsModel mods;`，`engine.rootContext()->setContextProperty(QStringLiteral("mods"), &mods);`（放在 `lanzador` 注册之后即可）。
- `launcher/src/lanzador.h/.cpp`：`iniciar` 增加 `entornoMods` 参数并逐个 `entorno.insert`；`iniciar` 返回失败时保证 `m_proceso` 不被创建。
- `launcher/qml/Main.qml`：见 5.6。
- `launcher/qml/Textos.js`：新增键（见 6.5）。

`ModsModel` 必须处理「没有 Mod」的情况：`data/mods/packages` 为空时，`list` 返回 `[]`，页面显示空状态，`prepareSession` 返回空 env，启动器行为与改造前一致。**不要**在没有任何 Mod 时仍设置 `GOW_MOD_VFS_TABLE`（空表虽然无害，但会多一次读取和 `[mod-vfs]` 日志，干扰「无 Mod」验证）。

### 6.3 Phase 1：`Lanzador::iniciar` 的精确改法

在 `lanzador.h` 里加：

```cpp
#include <QMap>
...
bool iniciar(const QVariantMap &ajustes, const QMap<QString, QString> &entornoMods, QString *error);
```

保留原有 `Q_INVOKABLE bool iniciar(const QVariantMap &ajustes)` 作为重载（QML 现有调用不变），内部转调新签名、传空 map。这样即使 QML 还没改完，旧路径也不会坏。

在 `lanzador.cpp` 的 `iniciar` 末尾（`aplicarTarjeta` 之后、写日志之前）加：

```cpp
for (auto it = entornoMods.begin(); it != entornoMods.end(); ++it)
{
    if (entorno.contains(it.key()))
    {
        if (error) *error = tr("The environment already defines %1; remove it before launching with mods.").arg(it.key());
        return false;
    }
    entorno.insert(it.key(), it.value());
}
```

注意：`QProcessEnvironment::contains` 会包含系统环境。如果玩家系统里本来就有 `GOW_TEXTURE_PACK`，这里会拒绝——这是有意的「不静默覆盖」。如果产品上不希望这么严格，改成「Mod 覆盖并在日志/界面提示」，但不要两边都静默。

同时把 `GOW_MOD_VFS_STATS` / `GOW_MOD_VFS_TRACE` 指到 `carpetaDatos() + "/registros/"` 下的文件（例如 `mods-vfs-stats.json`、`mods-vfs-trace.txt`），这样即使启动器不跑 CLI `run` 也有诊断证据。注意 `registros/` 已存在；文件名不要与 `ultimo.log` 冲突。

### 6.4 Phase 1：`jugar()` 的改法

```qml
function jugar() {
    var envMods = ({})
    if (ajustes.modsEnabled) {
        var prep = mods.prepareSession()
        if (prep.error.length > 0) {
            ventana.aviso(prep.error)
            return
        }
        envMods = prep.env
    }
    var a = { ... 现有字段 ... }
    if (lanzador.iniciar(a, envMods) && ajustes.minimizarAlJugar)
        minimizarTrasArrancar.start()
}
```

如果 `prepareSession` 是同步的（推荐 Phase 1），QML 里就是上面的直线代码；如果是异步（QProcess 异步 + 信号），需要把「准备完成后启动」拆成 `onSessionReady` 回调，避免 QML 里 `wait`。**Phase 1 建议同步**：apply 通常 <1 秒，UI 用 `busy` 指示即可，逻辑最简单。

### 6.5 文案键（`Textos.js`）

至少新增：

| 键 | en | es | tr |
|---|---|---|---|
| `pestMods` | MODS | MODS | MODLAR |
| `modsTitle` | Mods | Mods | Modlar |
| `modsDesc` | Enable or disable installed mods. Changes apply on the next launch. | Activa o desactiva mods instalados. Los cambios se aplican en el próximo inicio. | Kurulu modları açın veya kapatın. Değişiklikler bir sonraki başlatmada uygulanır. |
| `modsEmpty` | No mods installed. Use "Import mod…" to add one. | No hay mods instalados. Usa "Importar mod…". | Kurulu mod yok. "Mod içe aktar…" ile ekleyin. |
| `modsApply` | Apply plan | Aplicar plan | Planı uygula |
| `modsDeactivate` | Disable all | Desactivar todo | Tümünü kapat |
| `modsRefresh` | Rescan | Volver a escanear | Yeniden tara |
| `modsStale` | Game files changed: re-apply the plan. | Los archivos del juego cambiaron: vuelve a aplicar el plan. | Oyun dosyaları değişti: planı yeniden uygulayın. |
| `modsConflict` | Conflict | Conflicto | Çakışma |
| `modsExcluded` | Not applied | No aplicado | Uygulanmadı |
| `modsImport` | Import mod… | Importar mod… | Mod içe aktar… |
| `modsOpenFolder` | Open mods folder | Abrir carpeta de mods | Mod klasörünü aç |
| `modsBusy` | Working… | Trabajando… | Çalışıyor… |
| `modsError` | Mod error: %1 | Error de mod: %1 | Mod hatası: %1 |
| `modsProfile` | Profile | Perfil | Profil |

规则：`Tema.t(key)` 缺失会回退英文（`Textos.js` 的 `texto` 函数），但 `tools/test/launcher-languages.py` 会检查占位符数量；带 `%1` 的键三种语言都必须有且数量一致。

### 6.6 Phase 1：设置持久化

不要把「哪些 Mod 启用」写进 `QSettings`。它已经在 `profiles/<name>.toml` 里，双写会分叉。`QSettings` 只存：

- `ajustes/modsProfile`：当前使用的 profile 名（默认 `"default"`；验证用 `"verify"`）。
- `ajustes/modsEnabled`：全局开关（临时原版启动用）；默认 `true`。

在 `Main.qml` 的 `Settings` 块加这两个属性即可。若玩家切换 profile，调 `mods.setProfile(nombre)` 并刷新列表。

### 6.7 Phase 2：冲突表与指纹横幅

冲突表数据来自 `plan --json` 的 `conflicts`、`excluded`、`warnings`。建议展示：

- `conflicts`：`mod` vs `with` + `reason`（声明冲突/环境变量不同值/资源被遮蔽）。
- `excluded`：被排除的 Mod 与原因（校验失败/区域不匹配/缺依赖/冲突落败/空计划）。
- `warnings`：`env.shadowed`、`vfs.shadowed`、`texture.shadowed` 等，给出「谁覆盖了谁」。

指纹横幅：`status --json` 返回 `fingerprintId`、`activePlan`、`profile`；与 `plan` 的 `fingerprintId` 比较。若 `state.activePlan` 为空或指纹不一致，横幅显示 `modsStale`，并把「应用计划」按钮高亮；点 Play 时 `prepareSession` 会自动 apply（或按 5.3.1 的选择提示玩家）。

### 6.8 Phase 2：回滚与报告

- 「回滚」调用 `rollback`（默认回滚当前计划）或 `deactivate`；回滚后刷新。
- 「查看报告」读取 `data/mods/reports/<run>.json` 或启动器自己写的 `session-*.json`；只显示白名单字段。
- 「打开日志」用 `lanzador.abrirRegistro()` 已有实现，或单独打开 `registros/ultimo.log`。

### 6.9 Phase 3：C++ 核心

如果决定移植，建议把 Python 版当 oracle：

1. 在 `launcher/src/mods/core/` 建 `Registry` / `Fingerprint` / `Planner` / `Applier` / `Journal`，与 Python 的函数一一对应。
2. 同一输入（同一 `data/mods`、同一指纹）必须产出**字节级相同**的 `plan.json`（键排序、紧凑 JSON、同样的 sha256）；写一个测试对比 Python 与 C++ 的 `planId`。
3. 先只移植「读路径」（list/plan/apply），保留 Python 作为 fallback；用环境变量 `GOW_MODS_CORE=python|cpp` 切换，验证一致后再删 Python。
4. 注意：C++ 侧 TOML 解析用 runtime 已有的 `toml` 能力或自带最小解析器；时间/路径规范化（Windows 大小写、`\` vs `/`）必须与 Python 一致，否则 `planId` 会分叉。

### 6.10 启动器的验证钩子

现成可用：

```powershell
# 打开 Mods 页签并截图（页签 6 是新增的，若从 0 数）
$env:TOBIICHI_CAPTURA = "<repo>\data\_tmp\launcher-mods.png"
$env:TOBIICHI_CAPTURA_PESTANA = "6"
.\launcher\build\gow-launcher.exe
```

如果新增页签导致 `TOBIICHI_CAPTURA_PESTANA` 的旧截图脚本失效，保持旧页签 0..5 不变；只在测试脚本里用 6。`tools/pipeline` 的截图测试（若存在）也应只加不改。

---

## 7. 协议与数据字典

### 7.1 `state.json`

```json
{
  "schema": 1,
  "fingerprintId": "…",
  "activePlan": "<planId>",
  "profile": "verify",
  "enabled": [{"id": "verify.gow.subset", "version": "1.0.0"}],
  "activatedAt": "2026-11-05T05:37:00Z",
  "staging": "…/data/mods/staging/<planId>"
}
```

`activePlan` 为空/文件不存在 = 未启用任何 Mod。启动器只读这个字段做「是否启用」判断，不要自己维护第二份状态。

### 7.2 `plan.json`（关键字段）

```json
{
  "schema": 1,
  "planId": "…",
  "profile": "verify",
  "fingerprintId": "…",
  "fingerprint": {"gameId": "gow1", "edition": "…", "region": "asia", "elfCrc": "…", "textSha1": "…", "runtimeCommit": "…", "patchChainHash": "…"},
  "mods": [{"id": "…", "version": "…", "priority": 0, "capabilities": ["texture_pack","vfs"], "path": "…"}],
  "env": {"KEY": {"value": "…", "mod": "label"}},
  "vfs": {"cdrom0:/libsd.irx": {"host": "…", "mod": "label", "sha256": "…"}},
  "textures": {"<pcsx2-stem>": {"host": "…", "mod": "label", "sha256": "…"}},
  "excluded": [{"mod": "…", "reason": "…"}],
  "conflicts": [{"mod": "…", "with": "…", "reason": "…"}],
  "warnings": [{"code": "env.shadowed", "mod": "…", "message": "…"}],
  "issues": [{"code": "…", "severity": "error|warn", "message": "…", "mod": "…"}]
}
```

启动器的 UI 只依赖这些字段；不要把 CLI 的内部结构（`Package`/`Issue` 类）泄漏进 QML。

### 7.3 `vfs-overrides.tsv`

```
# guest path<TAB>staged host path (patch 71)
# generated by tools/mods/gow_mods_cli.py; do not edit while the game runs
cdrom0:/libsd.irx	<absolute staging path>/LIBSD.IRX
```

规则：`#` 注释、`\t` 分隔、最多 4096 行；guest 已经是 canonical 形式（小写、`/`）；host 是绝对路径。**不要让玩家手改这个文件**；所有变更走 CLI。

### 7.4 环境变量字典（Mod 可用的）

`ENV_ALLOWED`（当前实现）：

- visual：`GOW_SCALER`、`GOW_SHARPEN`、`TOBIICHI_FXAA`、`GOW_PROGRESIVO`、`GOW_TEXTURE_PACK_MB`、`PS2X_GS_HW_SCALE`。
- behaviour：`GOW_CANCELAR`、`GOW_FIJAR`、`GOW_ESPERA_EE`、`GOW_QTE_HOLD`、`GOW_QTE_STICK`、`GOW_EE_FPU_NEAREST`、`GOW_AUDIO`、`GOW_AUDIO_DEVICE`、`GOW_PAD_BT_RUMBLE`、`GOW_WINDOW`。
- engine（只 warn）：`GOW_VU1_FAST`、`GOW_VU1N_X64`、`PS2X_GS_RUN`、`PS2X_GS_PIPELINE`、`GOW_GS_FINISH_ASINCRONO`、`PS2X_GS_HW`、`PS2X_GS_WORKER`。
- diagnostic（只 warn）：`GOW_TEXTURE_PACK_STATS`、`GOW_GS_TEXREUSE`。

`ENV_RESERVED`（Mod 绝对不能设）：`GOW_MOD_VFS_TABLE`、`GOW_MOD_VFS_STATS`、`GOW_MOD_VFS_TRACE`、`GOW_MOD_VFS_LOG`、`GOW_TEXTURE_PACK`、`GOW_MC0`、`GOW_SAVES_DIR`、`GOW_PAD_TEST`、`GOW_PAD_GUION`、`GOW_PAD_CAPTURAS`、`GOW_HOST_SHOT`、`GOW_WINDOW_HIDDEN`、`GOW_PERF_DIAG`、`GOW_PERF_FRAME_PC`、`GOW_DEBUG`。

新增白名单键的流程：先在 runtime 里 `grep getenv` 确认真的被读取 → 加进 `ENV_ALLOWED` → 在 `engine/README.md` 或补丁注释里写清楚来源 → 加一条 selftest/手工验证。**不要**把「看起来应该存在」的变量加进去。

### 7.5 退出码（启动器需要的部分）

| 码 | 含义 | 启动器行为 |
|---|---|---|
| 0 | 成功 | 继续 |
| 2 | 参数/校验/计划错误 | 显示 stderr 摘要，不启动 |
| 3 | 包已存在 | 提示用「覆盖导入」 |
| 4 | 事务/运行记录缺失 | 提示重试或回滚 |
| 5 | runner/ELF 找不到 | 提示检查 Archivos 页 |
| 6 | 没有激活计划 | 调 `apply` 或提示 |

---

## 8. 测试与实机验证手册

### 8.1 编译

运行时（当前已验证）：

```powershell
# 干净全量（约 964 个目标，本次实测通过）
<repo>\data\_tools\ninja\ninja.exe -C C:\gow-build-jpn -t clean
<repo>\data\_tools\ninja\ninja.exe -C C:\gow-build-jpn ps2EntryRunner
```

增量（只改注释/局部）：

```powershell
<repo>\data\_tools\ninja\ninja.exe -C C:\gow-build-jpn ps2EntryRunner
```

启动器：

```powershell
.\build.cmd -Stages launcher
```

注意：并行会话可能同时占用 `ps2EntryRunner.exe`（重链接会 `Permission denied`）。等对方跑完或改名运行；不要 `taskkill` 别人的进程。

### 8.2 CLI 自检

```powershell
python -I tools\mods\gow_mods_cli.py selftest
python -I tools\mods\gow_mods_cli.py list -p verify
python -I tools\mods\gow_mods_cli.py validate verify.gow.subset@1.0.0
python -I tools\mods\gow_mods_cli.py plan -p verify
python -I tools\mods\gow_mods_cli.py apply -p verify
python -I tools\mods\gow_mods_cli.py status
```

`selftest` 覆盖：好包通过、坏包被拒、缺失 payload、路径穿越、坏 PNG、尺寸不符、plan 包含纹理、staging 存在、空计划拒绝。它不依赖游戏数据，CI 可跑。

### 8.3 三态实机验证（可照抄）

前提：日版光盘 `C:\gow-jpn-data\gow1\discs\asia-97399`，runner `C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe`，`data/gow1/regional-builds.json` 指向它。

**状态 A：无 Mod**

```powershell
python -I tools\mods\gow_mods_cli.py run --label off --seconds 200 --no-mods `
  --set GOW_PAD_TEST=1 `
  --set "GOW_PAD_GUION=5:start,8:circulo,12:circulo,16:circulo,20:circulo,25:circulo,30:circulo,40:circulo,50:circulo,60:circulo,70:circulo,80:circulo,90:circulo,100:circulo,110:circulo,120:circulo,130:circulo,140:circulo,150:circulo,160:circulo,170:circulo,180:circulo,190:circulo" `
  --set "GOW_PAD_CAPTURAS=60,100,140,180" `
  --set GOW_VU1N_X64=1 --set PS2X_GS_HW_SCALE=0.5 --set GOW_SKIP_FMV=1
```

判据：`gameplay start at ~44 s`、`state=11 pending=0 levelReady=1`、无 `[mod-vfs]`、无 `[gs-texpack]`、无 `cannot read`、4 张截图正常。

**状态 B：启用示例 Mod**

```powershell
python -I tools\mods\gow_mods_cli.py apply -p verify
python -I tools\mods\gow_mods_cli.py run --label on --seconds 200 `
  --set GOW_PAD_TEST=1 ...（同上）... --set GOW_TEXTURE_PACK_STATS=1
```

判据：`[mod-vfs] 1 overrides from …`、`vfs stats hits=1`、`[gs-texpack] 7 images`、`hits` 递增、`state=11`、无 `cannot read`、画面里出现品红替换区域且 Kratos/HUD 正常（如果截图时刻没有替换纹理入镜，用 `hits>0` 证明替换被使用）。

**状态 C：禁用后恢复**

```powershell
python -I tools\mods\gow_mods_cli.py deactivate
python -I tools\mods\gow_mods_cli.py status   # activePlan 为空
python -I tools\mods\gow_mods_cli.py run --label after-disable --seconds 200 --no-mods ...（同 A）
```

判据：日志不再出现 `[mod-vfs]`/`[gs-texpack]`，画面与 A 一致。

**重要提示**：`run` 会设置 `GOW_MOD_VFS_STATS/TRACE`，即使 `--no-mods` 也会；因此「无 Mod」日志里不应出现 `[mod-vfs] N overrides`（表未设置/为空），但可以有 stats 文件（lookups>0, hits=0）。这是正常的。

### 8.4 本次已获得的证据

- 干净全量编译：964 个目标，`EXIT=0`，无 `error:`/`FAILED`；二进制 `ps2EntryRunner.exe` 链接成功。日志 `data/_tmp/build71.log`（clean 版为 `build68.log`）。
- 无 Mod：`20261105-053134-v69-off`，200.24 s，`gameplay start at 44.44 s`，`state=11`，4 张截图；无 `[mod-vfs]`、无 `[gs-texpack]`、无 `cannot read`。
- 启用 Mod：`20261105-053535-v69-on`，184.65 s，`gameplay start at 47.36 s`，`state=11`；`[mod-vfs] 1 overrides`，VFS `hits=1`；`[gs-texpack] 7 images`，`hits=4856 loads=7 evictions=0`；无 `cannot read`。
- 更早同代码（改号前）：`20261105-041240-gameplay-ok`，200 s，`gameplay start at 65.25 s`，`state=11`，品红地形截图。
- 禁用后：早期 `after-disable` 200 s，`state=11`，日志无 Mod 钩子，画面正常。
- 间歇性退出：多次运行在 44/82/134/184 秒无异常日志地 `exit=1`，`--no-mods` 也出现过；同一机器上另一位并行会话在跑 benchmark（会 `taskkill`/重链接 runner）。判断为环境/并发干扰，而非 Mod 逻辑崩溃；接手后请在一台安静机器上补一次干净的三态复跑。

### 8.5 失败排查顺序

1. `status` 显示 `activePlan` 为空 → 没 apply，或指纹变化后自动 deactivate。
2. 日志有 `[mod-vfs] 0 overrides` → TSV 为空或路径不对；检查 `state.json` 的 staging 是否存在。
3. 日志有 `[gs-texpack] cannot read …png` → PNG 损坏或尺寸不符；`validate` 应该已经拦住，检查是否绕过了 CLI。
4. 启动器界面显示 Mod、但游戏没变化 → 检查 `prepareSession` 是否真的把 env 注入；在 runner 日志里搜 `[mod-vfs]` 与 `[gs-texpack]`。
5. 启动器报 Python 找不到 → `GOW_PYTHON` 或 PATH；Phase 3 之前这是已知限制。
6. `Permission denied` 重链接 → 有 runner 还在跑；等或改名，不要强杀。

---

## 9. 已知风险与未完成事项

这一章按「会不会让玩家炸机 / 会不会让下一位白干」排序。每条都给出当前状态、触发条件、缓解办法和验证方式。

### 9.1 高优先级风险

**R1. 工作副本缺启动器源码**

- 现状：`launcher/` 只有 `bin`，没有 `src/qml/recursos/CMakeLists.txt`；完整源码在 `C:\gow-jpn\launcher`。
- 触发：直接改工作副本的 `launcher/`，或直接跑 `build.cmd -Stages launcher`。
- 缓解：按 6.1 复制源码；复制后立即跑一次原始构建与截图，确认基线。
- 验证：`TOBIICHI_CAPTURA` 能生成 PNG；`gow-launcher.exe` 能打开。

**R2. 启动器依赖 Python**

- 现状：`ModsModel` 的 Phase 1 设计依赖 `python -I tools/mods/gow_mods_cli.py`；发行包目前不保证有 Python。
- 触发：玩家机器没有 Python 3.11+，或 PATH 被裁剪。
- 缓解：Phase 2 打包解释器或 Phase 3 移植 C++；Phase 1 在启动时探测版本并在 UI 明确报错；提供 `GOW_PYTHON` 覆盖。
- 验证：在无 Python 的干净 Windows 用户下启动启动器，确认报错可读且不会「假成功」。

**R3. 并发会话/补丁抢号**

- 现状：本次补丁从 67 改到 71，因为同一工作树里有另一个会话持续新增 67/68/69/70。`patchChainHash` 随每次补丁变化 → 计划频繁 stale。
- 触发：在两个窗口同时改 `engine/patches`、同时重链接 runner、同时跑实机验证。
- 缓解：动手前 `Get-ChildItem engine/patches | Sort-Object Name` 确认最大编号；给自己的补丁取「最大编号 + 1」并在 README 同步；不要删除/重命名别人的补丁；实机验证前先确认没有其它 `ps2EntryRunner` 进程（`Get-Process ps2EntryRunner`）。
- 验证：`python -I tools/mods/gow_mods_cli.py fingerprint` 连续两次 `changed=False`；`apply` 后 `status` 的 `activePlan` 非空。

**R4. 纹理尺寸约束**

- 现状：PCSX2 名里的 TW/TH 决定期望尺寸；实测小于期望尺寸会退出 runner。
- 触发：Mod 作者直接缩放纹理，或从旧版 PCSX2 包拿 64×64 的图片配 512×512 的名字。
- 缓解：CLI 在 validate 阶段报 `textures.size`；启动器导入时展示错误；文档/Mod 模板里写死规则。
- 验证：`validate` 一个故意 64×64 的包，必须 exit 2 并输出尺寸错误。

**R5. 间歇性 `exit=1`（原因未完全定位）**

- 现状：44/82/134/184 秒都出现过无 `[main] fatal exception`、无 WER 事件的 `exit=1`；`--no-mods` 也出现过；并发 benchmark 会重链接/结束进程。
- 触发：共享机器上有其他构建/测试；或长时间运行遇到未定位的运行时问题。
- 缓解：安静机器复跑；记录 `stderr` 最后一行与进程开始/结束时间；启动器 `terminado()` 已经会把非零退出当失败并展示日志摘要，不要静默吞掉。
- 验证：同一台机器、同一二进制、连续 3 次 `--no-mods` 200 秒，统计成功率；再跑 3 次启用 Mod，对比。若两者都失败，先修环境/运行时，不要归咎 Mod。

**R6. 指纹 stale 被误判为「Mod 不生效」**

- 现状：`run` 检测到 stale 会自动 deactivate；`status` 显示空计划。
- 触发：改补丁、重编译、换区域构建、改 `regional-builds.json`。
- 缓解：启动器在「开始游戏」前调用 `prepareSession`（内部 apply）；或者在 UI 上明确显示「需要重新应用」，不要只显示「未启用」。
- 验证：故意改一个补丁文件（或 touch），确认 `status` 变 stale，再点 Play 能自动 apply 或给出正确提示。

### 9.2 中优先级风险

**R7. 显存/内存预算**：纹理包不设硬上限，`GOW_TEXTURE_PACK_MB` 默认预算 1024 MB（缓存预算，不是立即分配）。大量 512×512/1024×1024 纹理仍可能让低端 iGPU 吃紧。缓解：CLI 可以统计纹理总字节并在 UI 显示；超过阈值给 warning；文档建议 Mod 作者控制尺寸。

**R8. 文件锁/杀毒**：`os.replace`、重链接 exe 在 Windows 上会被扫描器短暂占用。已加重试；启动器导入/应用失败时要给出「请稍后重试」而不是「Mod 损坏」。

**R9. 路径与大小写**：Windows 路径大小写不敏感，但 VFS 表键是 ASCII 小写；如果第三方 Mod 的 guest 路径用了非 ASCII 或奇怪分隔符，可能不命中。CLI 的 `GUEST_PATH_RE` 只接受有限前缀；遇到不支持路径应报错，不要静默。

**R10. 环境变量冲突**：启动器已注入某个键（例如玩家系统环境有 `GOW_TEXTURE_PACK`）时，按 6.3 会拒绝启动。必须在 UI 里把冲突键名说清楚，否则玩家不知道为什么点 Play 没反应。

**R11. QSettings 组织名/应用名迁移**：`main.cpp` 使用 `Tobiichi`/`LauncherUltimate`，并从旧的 `Launcher` 迁移。新增 `modsProfile`/`modsEnabled` 时不要改变组织名/应用名，否则玩家所有旧设置丢失。

**R12. 页签编号**：`TOBIICHI_CAPTURA_PESTANA` 用整数索引；新增页签必须放在最后（index 6），不要插到中间。若未来要重排，先更新所有截图脚本与测试。

**R13. 会话报告隐私**：不要把绝对路径、ELF/ISO 路径、环境变量全量、纹理图本身写进报告或上传。按设计文档 §20.5 白名单。

**R14. 版权**：示例 Mod 里的 `LIBSD.IRX` 是游戏数据，只用于本地验证，不能分发；纹理替换图若是从游戏导出也不能分发。启动器/Mod 包导入界面应有「仅安装你有权使用的资源」提示（可选但建议）。

### 9.3 未完成事项清单（按优先级）

1. 启动器源码取回与基线构建（P0，阻塞所有 UI 工作）。
2. `ModsModel` + `PaginaMods.qml` + `Lanzador::iniciar` 注入（P0，最小可玩）。
3. 导入/冲突/指纹 UI（P1）。
4. 会话报告与诊断（P1）。
5. Python 打包或 C++ 核心（P2，发布前必须解决）。
6. 三态实机复跑（P0，安静机器）。
7. 空计划/损坏包/缺依赖的负向测试（P1）。
8. 文档回写：`AGENTS.md` 页面表、`docs/architecture.md` 数据流、`engine/README.md`（如补丁再变）。
9. 删除临时文件：`data/_tmp/make_patch71.py`、`check_patch71.py`、`patchtest/`、旧 fixture。保留 `build68.log`/`build71.log` 作为证据直到验收。

### 9.4 不建议做的事

- 不要从 `gow-launcher.exe` 反编译 QML 来「补源码」。设计文档明确禁止，而且版本会漂移。
- 不要让启动器直接写 `hooks/vfs-overrides.tsv` 或 `state.json`。这些是事务产物，必须由 `activate` 一起写；手写会破坏回滚。
- 不要在 QML 里 `XMLHttpRequest`/`Process` 调 CLI；Qt QML 没有安全的进程 API，逻辑放 C++。
- 不要在 Mod 未启用时仍设置 `GOW_MOD_VFS_TABLE`/`GOW_TEXTURE_PACK` 为空字符串；空字符串与未设置在某些 getenv 分支上不等价。
- 不要把 `.PAK`/函数/脚本覆盖「先做个壳」；没有运行时钩子，做了也不会生效，反而误导玩家。
- 不要在验证时只看「进程没崩」；必须看 `state=11`、`gameplay start`、日志钩子行与截图。

---

## 10. 路线图与任务拆解

### 10.1 P0：能玩（必须）

目标：启动器里能勾选示例 Mod，点 Play 能进游戏，禁用后恢复原版；失败有提示。

任务：

1. 复制 `C:\gow-jpn\launcher` 源码到工作副本，构建并截图基线。
2. 实现 `ModsModel` 的 `repoRoot`、`runCli`、`refresh`、`setEnabled`、`prepareSession`、`envFromPlan`。
3. `Lanzador::iniciar` 增加 `entornoMods` 重载与注入；拒绝未处理的键冲突。
4. `Main.qml`：Settings 两个属性、`jugar()` 先 prepare、第 7 页签、`PaginaMods` 最小列表 + 开关 + 状态。
5. `Textos.js` 加 6.5 的键（先加必需子集：`pestMods`、`modsTitle`、`modsDesc`、`modsEmpty`、`modsApply`、`modsDeactivate`、`modsStale`、`modsError`）。
6. 负向：Mod 包损坏、尺寸不符、缺依赖、空计划 → 点 Play 不启动并显示原因。
7. 实机三态（A/B/C）各一次，记录 `state=11` 与钩子行。

验收：

- 无 Mod 启动：runner 日志无 `[mod-vfs]`/`[gs-texpack]`。
- 启用示例 Mod：日志 `[mod-vfs] 1 overrides`、`hits=1`、`[gs-texpack] 7 images`、`hits>0`。
- 禁用后：日志与无 Mod 相同。
- 启动器截图：Mods 页显示 1 个 Mod、开关状态正确。

### 10.2 P1：好用

- 导入按钮（目录选择 + `import --replace` 确认）。
- 冲突/排除/警告列表，可展开看原因。
- 指纹横幅与「应用计划」按钮。
- 打开 Mods 目录、打开日志。
- 会话报告（白名单字段）。
- 多 profile 选择（默认/verify/自定义）。
- 批量启用/禁用、搜索（Mod 多时）。

验收：`launcher-languages.py` 通过；`qte-controls.py` 若仍存在，不被破坏；导入非法包不会留下半装目录。

### 10.3 P2：可发布

- Python 打包（或 C++ 核心），在无 Python 的干净 Windows 上验证。
- 启动器首次运行引导：检测 `data/mods` 可写、Python 可用、仓库完整。
- 崩溃/失败报告导出（白名单）。
- 性能：启动到窗口 ≤ 现状 + 1 秒；点 Play 到 runner 启动 ≤ 现状 + 2 秒（apply 除外）。
- 安装/卸载：Mod 数据在 `data/mods`，卸载器是否保留由产品决定；不要误删玩家 Mod。

### 10.4 P3：原生核心

- `launcher/src/mods/core` 实现 Registry/Fingerprint/Planner/Applier/Journal。
- 与 Python 版 `planId` 字节级一致（交叉测试）。
- 切换开关 `GOW_MODS_CORE`，稳定后删 Python 依赖。
- 复用同一份 `plan.json` schema；不要发明第二套格式。

### 10.5 任务顺序图（依赖关系）

```
P0-1 源码基线 ──> P0-2 ModsModel ──> P0-3 Lanzador 注入 ──> P0-4 QML ──> P0-6 三态
                          │
                          └──> P1 导入/冲突/报告 ──> P2 Python 打包
                                                   └──> P3 C++ 核心
```

P0-1 是硬前置；P0-2 与 P0-3 可以并行（接口先定）；P0-4 依赖 P0-2 的属性名；P0-6 最后做。

---

## 11. 常见问题（FAQ）

**Q1. 为什么启动器里勾了 Mod，游戏却没变化？**

先看 runner 日志（`%APPDATA%\Tobiichi\LauncherUltimate\registros\ultimo.log`）里有没有 `[mod-vfs]`/`[gs-texpack]`。没有 → 环境没注入；有 `[mod-vfs] 0 overrides` → TSV 空/路径错；有 `cannot read` → PNG 坏/尺寸错。再用 `status` 看 `activePlan` 是否为空（stale 会自动清空）。

**Q2. 为什么 `apply` 之后 `status` 又显示没有激活计划？**

`run`/`status` 会重算指纹；如果这期间补丁目录、`regional-builds.json`、`game.toml` 或 runner 哈希变了，计划会 stale。并行开发时尤其常见。重新 `apply` 即可。启动器的 `prepareSession` 就是为此存在。

**Q3. 可以热切换 Mod 吗？**

不可以。环境变量在进程启动时固定；VFS 表在首次 lookup 时读取；纹理包在启动时枚举。改 Mod 必须退出游戏、重新 apply、再启动。UI 上要写清楚「下次启动生效」。

**Q4. 为什么限制纹理尺寸，不能自动缩放？**

patch 52 的替换路径按 GS 纹理尺寸绑定，图片尺寸小于名字 TW/TH 时实测会让 runner 退出（见 4.4）。自动缩放需要改运行时并重新验证；在管理器里放宽只会把崩溃推给玩家。

**Q5. `.PAK` Mod 为什么不能做？**

IOP 通过 LBA 读 PAK，不经过 `PS2Vfs::resolveHostPath`；要支持必须逆向 TOC 并在 IOP 层拦截。设计文档把它列为高风险/后续，本次明确不做。

**Q6. 函数替换为什么不能做？**

`replaceFunction` 需要把替换函数的宿主符号编进 runner（L1 重编译），不是运行时可插拔。动态库注入会破坏「补丁链可重建」和 ABI 稳定性。

**Q7. 为什么 Mod 的环境变量要白名单？**

防止「写了一个运行时根本不读的变量」让玩家以为生效；也防止 Mod 改管理器自己的 staging/诊断变量导致不可回滚。新增键必须先在 runtime 里确认 `getenv`。

**Q8. `planId` 有什么用？**

它是计划内容的哈希（含每个资源文件的 sha256），用于判断「当前激活的是不是这份计划」。启动器显示/记录它，排障时可以据此复现。

**Q9. 指纹包含哪些东西？为什么重编译 runner 不失效？**

`fingerprintId` 包含 gameId/edition/region/elfCrc/textSha1/runtimeCommit/patchChainHash，不含 runnerSha256；重编译只改 runner 二进制时计划仍有效。补丁内容变（patchChainHash）才失效。

**Q10. 为什么补丁号老在变？**

同一工作树有并行会话在加渲染补丁（67–70）。本次 Mod 补丁从 67 改到 71 以避免重号。接手后先确认最大编号，再取下一个；不要复用别人的编号。

**Q11. 启动器应该用哪个 profile？**

默认 `default`；验证/开发用 `verify`（当前 `verify` 启用了示例 Mod）。玩家可以有多个 profile，但 UI 一次只显示一个；切换 profile 时刷新列表并提示「需要重新应用」。

**Q12. 示例 Mod 能发给玩家吗？**

不能。它包含从日版光盘提取的 `LIBSD.IRX` 和游戏纹理替换图，只用于本地验证。发布前删除或替换为自制资源。

**Q13. 为什么 `--no-mods` 运行也会生成 vfs-stats.json？**

`run` 总是设置诊断路径；表为空时 lookups>0、hits=0，这是正常的「无 Mod」证据。关键是没有 `[mod-vfs] N overrides` 行。

**Q14. 启动器点 Play 卡住几秒正常吗？**

Phase 1 的 `prepareSession` 可能同步跑 `apply`（Python 启动 + 哈希），通常 <1 秒；如果 Mod 包很大（纹理多），会更久。用 `busy` 指示并避免重复点击；超过 30 秒超时并报错。

**Q15. 玩家手动设了 `GOW_TEXTURE_PACK` 怎么办？**

按 6.3 拒绝启动并提示键名。让玩家在系统环境里清掉，或在启动器里提供「临时忽略环境变量」的高级选项（默认关闭）。

**Q16. 为什么 Mod 列表里有的包显示 ERR？**

`validate` 发现 error（格式、路径、尺寸、未知 env 键、缺 payload 等）。`list` 的 `issues` 里有原因；修包后重新 `refresh`。ERR 的包不会被 `enable`。

**Q17. 可以给 Mod 加设置开关（比如画质档）吗？**

当前不支持 `settings` 覆盖层。可以让 Mod 用不同 `[env]` 值发布多个版本，或在 profile 层面做（后续 UI 覆盖）。不要在界面上做「假开关」。

**Q18. Mod 会不会改存档？**

不会。VFS 只读覆盖 guest 路径；没有写回逻辑。除非 Mod 显式映射 `mc0:` 到另一个文件（理论上可以），但当前 CLI 不阻止这类 VFS；如果要做强隔离，应在 `validate` 里拒绝 `mc0:`/`mc1:` 前缀（这是待定策略，接手者可决定）。

**Q19. 为什么启动器源码要从 `C:\gow-jpn` 复制，而不是从 bin 反编译？**

bin 里的 QML 是编译进资源的，反编译不可靠且版本漂移；`C:\gow-jpn` 是同一工程的 git 源码，是唯一可靠来源。复制后要确认版本与 bin 行为一致。

**Q20. 验证时如何避免另一个会话干扰？**

`Get-Process ps2EntryRunner` 确认没有别人的进程；用独立 `--label` 目录；记录开始/结束时间；如果进程在非超时时刻消失且无异常日志，优先怀疑外部 `taskkill`，换时间窗口复跑。

---

## 12. 附录

### 12.1 命令速查

```powershell
# 指纹
python -I tools\mods\gow_mods_cli.py fingerprint
# 列表（含兼容性/错误）
python -I tools\mods\gow_mods_cli.py list -p verify --json
# 校验单个包
python -I tools\mods\gow_mods_cli.py validate verify.gow.subset@1.0.0
# 导入/覆盖
python -I tools\mods\gow_mods_cli.py import <folder> --replace
# 启用/禁用
python -I tools\mods\gow_mods_cli.py enable -p verify <spec>
python -I tools\mods\gow_mods_cli.py disable -p verify <spec>
# 计划/应用/状态
python -I tools\mods\gow_mods_cli.py plan -p verify --json
python -I tools\mods\gow_mods_cli.py apply -p verify
python -I tools\mods\gow_mods_cli.py status --json
# 回滚/禁用
python -I tools\mods\gow_mods_cli.py rollback
python -I tools\mods\gow_mods_cli.py deactivate
# 实机
python -I tools\mods\gow_mods_cli.py run --label test --seconds 200 [--no-mods] --set KEY=VALUE ...
# 报告
python -I tools\mods\gow_mods_cli.py report
# 自检
python -I tools\mods\gow_mods_cli.py selftest
```

### 12.2 关键文件清单

| 文件 | 作用 |
|---|---|
| `tools/mods/gow_mods_cli.py` | 管理器核心 + CLI |
| `tools/mods/make_verify_mod.py` | 示例 Mod 生成器 |
| `data/mods/packages/verify.gow.subset@1.0.0/` | 验证夹具 |
| `data/mods/profiles/verify.toml` | 启用列表 |
| `data/mods/state.json` | 当前激活状态 |
| `data/mods/hooks/plan.json` | 激活的计划（启动器读它） |
| `data/mods/hooks/vfs-overrides.tsv` | VFS 覆盖表 |
| `engine/patches/71-mod-vfs-hooks.patch` | 运行时补丁 |
| `engine/runtime/.../mod_vfs_table.h/.cpp` | 运行时实现 |
| `engine/runtime/.../ps2_vfs.cpp` | 钩子位置 |
| `engine/README.md` | 补丁表（67–71） |
| `docs/mod-manager-design.zh-CN.md` | 设计依据 |
| `C:\gow-jpn\launcher\src\lanzador.cpp` | 启动器启动与环境注入 |
| `C:\gow-jpn\launcher\src\main.cpp` | QML 引擎/上下文注册 |
| `C:\gow-jpn\launcher\qml\Main.qml` | 页签/设置/jugar |
| `C:\gow-jpn\launcher\qml\Textos.js` | 三语文案 |
| `C:\gow-jpn\launcher\CMakeLists.txt` | 启动器构建 |

### 12.3 术语

- **Runner / `ps2EntryRunner.exe`**：重编译后的原生游戏程序，启动器最终启动它。
- **Guest 路径**：PS2 侧的路径（`cdrom0:\...`、`mc0:/...`、`host:...`、`iop_mod\...`）。
- **VFS 覆盖**：把某个 guest 路径解析到宿主文件；只读，不改游戏数据。
- **纹理包**：PCSX2 命名规则的 PNG 集合；patch 52 按名替换。
- **指纹**：游戏/区域/ELF/运行时/补丁链的身份哈希。
- **计划 / `planId`**：一份确定的 Mod 应用方案及其内容哈希。
- **staging**：计划物化后的文件目录（纹理/VFS），供 runner 读取。
- **journal**：事务日志，记录激活前的 hooks/state 快照，用于回滚。
- **profile**：启用列表，唯一事实来源。
- **L1/L2/L3**：源码补丁/环境变量/资源覆盖三层注入。

### 12.4 变更记录（截至 2026-11-05）

- 新增运行时补丁 `71-mod-vfs-hooks.patch`：只读 VFS 表 + 诊断。
- 新增 `tools/mods/gow_mods_cli.py` 与 `make_verify_mod.py`。
- 新增 `data/mods/` 数据目录与示例夹具。
- 更新 `engine/README.md` 补丁表（71 行）。
- 修复 CLI：PNG 结构/尺寸校验、plan 内容哈希、staging 清理、Windows 文件锁重试、selftest 夹具尺寸。
- 补丁编号因并行会话从 67 改到 71；代码注释、README、CLI 文档同步。
- 本文档。

### 12.5 接手第一天检查表

- [ ] `C:\gow-jpn\launcher` 源码复制进工作副本，`build.cmd -Stages launcher` 通过。
- [ ] `TOBIICHI_CAPTURA` 能截图，页签 0..5 与旧版一致。
- [ ] `python -I tools\mods\gow_mods_cli.py selftest` 通过。
- [ ] `list -p verify` 显示示例 Mod，`plan -p verify` 无 error。
- [ ] `apply -p verify` 后 `status` 有 `activePlan`，`hooks/plan.json` 存在。
- [ ] 实机跑一次启用 Mod，日志出现 `[mod-vfs] 1 overrides` 与 `[gs-texpack] 7 images`，`state=11`。
- [ ] `deactivate` 后再跑，日志无 Mod 钩子。
- [ ] 记录当天最大补丁号，避免重号。
- [ ] 确认没有其它 `ps2EntryRunner` 进程在跑。
- [ ] 在 `Main.qml`/`Textos.js`/`CMakeLists.txt` 里按第 6 章加最小闭环，截图验收。

### 12.6 给下一位的三句忠告

1. **先让原始启动器能编译、能截图，再动一行 UI**。工作副本缺源码是这次交接最大的坑。
2. **启动路径只读 JSON，管理路径才跑 Python**。不要让「点 Play」变成一次不可控的子进程等待。
3. **任何失败都不要静默降级成无 Mod 启动**。Mod 管理器最容易失去信任的方式，就是玩家以为启用了、实际没有。

---

## 13. 启动器 UI 规格书（可直接交给实现者）

这一章把「Mods 页长什么样、每个控件什么行为、出错时显示什么」写到可以直接照做的程度。所有文案键都指 6.5 节的 `Textos.js`；所有数据字段都指第 7 章的协议。实现时先做「能用的最小版本」，再按本节补齐状态与细节。

### 13.1 信息架构

启动器是单窗口、左侧封面 + 右侧页签的布局。Mods 是第 7 个页签（索引 6），与现有 6 个页签平级，不占据左侧封面区域。页面内部是纵向滚动，分四块：

1. **状态条**：一句话说明当前状态（未启用/已启用 N 个/需要重新应用/有错误），右侧两个按钮（重新扫描、禁用全部）。
2. **提示区**：只在有冲突、排除、警告或错误时出现；每条一行，可展开看完整原因。
3. **Mod 列表**：每个已安装包一行；左侧名称与版本，第二行能力与优先级，右侧开关；不可用的包显示红色 ERR 徽标与原因摘要。
4. **底部操作条**：导入 Mod、打开 Mods 目录、应用计划（主按钮）。

页面不显示「安装进度条」之类的构建概念；Mod 的启用/禁用是即时操作，不需要重启启动器，但需要重启游戏才生效。UI 上必须有一句固定提示：「更改将在下一次启动游戏时生效」。

### 13.2 页面状态机

Mods 页只有五种顶层状态，任何时刻必须处于其中一种，避免「既像加载中又像空列表」：

| 状态 | 触发 | 界面表现 | 允许的操作 |
|---|---|---|---|
| `loading` | 首次进入、点重新扫描、导入后 | 列表区域显示 `modsBusy`，开关禁用 | 无（可取消扫描，可选） |
| `empty` | 扫描完成且 0 个包 | 显示 `modsEmpty` + 导入按钮 | 导入、打开目录、重新扫描 |
| `ready` | 有包，无 error | 列表 + 开关 + 状态条 | 全部 |
| `degraded` | 有包，但有 error/冲突/排除 | 列表 + 提示区 + 状态条（橙色） | 全部；主按钮文案改为「修复后应用」 |
| `failed` | CLI 找不到/仓库不完整/读取失败 | 错误面板 + 重试按钮 | 重试、打开日志、打开目录 |

状态切换必须由 `ModsModel` 的 `statusChanged` 驱动，QML 不要自己推断。例如 `mods.mods.length === 0` 不等于 `empty`——扫描可能还没完成；用显式的 `state` 属性最稳：

```cpp
Q_PROPERTY(QString pageState READ pageState NOTIFY statusChanged) // loading|empty|ready|degraded|failed
```

### 13.3 顶部状态条

布局：左侧一个圆点 + 一行文字，右侧两个 `BotonSecundario`。

圆点颜色：

- 绿色：`ready` 且已启用至少一个 Mod，且指纹匹配。
- 灰色：`empty` 或未启用任何 Mod。
- 橙色：`degraded`（有冲突/排除/警告）。
- 红色：`failed` 或指纹 stale。

文字规则：

- 未启用：`modsNone`（例如「未启用任何 Mod，游戏按原版运行」）。
- 已启用且正常：`modsActive`，带 `%1` 个 Mod（用启用计数，不是安装计数）。
- 指纹 stale：`modsStale`。
- 有错误：`modsHasErrors`，带 `%1` 个错误。

按钮：

- 「重新扫描」→ `mods.refresh()`。扫描期间按钮禁用，文字变 `modsBusy`。
- 「禁用全部」→ 二次确认（`Dialog` 或现有确认控件），确认后 `mods.deactivate()`；成功后状态变灰、列表开关全关。若当前本来就没有启用，按钮禁用。

### 13.4 Mod 列表行

每行复用 `Fila` 的视觉结构（标题 + 描述 + 右侧控件 + 分隔线）。字段：

- **标题**：`name`（玩家可读名）+ `id@version`（小字、弱化）。名称缺失时用 `id@version`。
- **描述第一行**：能力标签。`texture_pack` → 「纹理」；`vfs` → 「文件覆盖」；`env` → 「参数」。多个用「·」连接。没有能力（空包）显示 `content.empty` 的原因。
- **描述第二行**：`priority=N`；若 `target.regions` 非空，显示目标区域；若 `valid=false`，显示第一条 error 的 `message`（截断 120 字符，详情面板看全文）。
- **右侧**：`Interruptor`，`checked = enabled`；`enabled = valid`（ERR 包不能开）。切换时立刻调 `mods.setEnabled(label, checked)`，控件进入「等待」态（禁用 + 降低透明度），成功后再以磁盘状态为准；失败则回弹并弹错。
- **点击行**（非开关区域）：打开详情抽屉/对话框，显示完整 manifest 摘要、issues、覆盖的资源键、来源目录（可复制，不默认展示绝对路径给截图/报告）。

排序：默认按 `id` 字母序；提供「按优先级」切换（可选）。不要按启用状态排序，避免开关一按行就跳。

空包/无能力包：仍然显示，但开关禁用，描述显示「此包没有本运行时能消费的资源」。

### 13.5 冲突与排除面板

数据来自 `plan` 的 `conflicts`、`excluded`、`warnings`。面板默认折叠，标题显示计数，例如「2 个冲突 · 1 个排除」。展开后每条形如：

- 冲突：`A vs B` — 原因（声明冲突 / `KEY` 设置不同 / 纹理 `name` 被遮蔽）。
- 排除：`A` — 原因（校验失败 / 区域不匹配 / 缺少依赖 `X` / 与 `B` 冲突落败 / 全部被排除）。
- 警告：`A` — `GOW_XXX` 已被 `B` 设置，高优先级者生效。

排序：错误优先，其次冲突，再次警告；同组按 mod 名。每条右侧可以有「定位到该行」按钮（滚动并高亮对应 Mod 行）。

**重要**：`excluded` 里的「校验失败」如果同时出现在 `mods[].issues`，不要在列表和面板重复显示两遍不同措辞；统一引用同一条 `message`。

### 13.6 导入对话框

入口：底部「导入 Mod…」按钮。流程：

1. 用现有 `CampoRuta`（`soloCarpeta: true`）或 `FileDialog` 选一个**目录**（不是 zip；当前 CLI 不接收压缩包）。
2. 选择后先调 `validate`（或直接 `import`，CLI 内部会校验）；显示「校验中」。
3. 成功：显示 `id@version` 与能力，确认后调 `import`；若已存在，弹「已安装同版本，是否覆盖？」→ `import --replace`。
4. 失败：显示第一条 error + 「查看全部」；**不要**复制任何文件（CLI 在复制前校验，失败不会留半装目录）。
5. 完成后刷新列表，若新包和现有包冲突，提示区自动展开。

导入对话框不要显示绝对路径历史；最近目录可以存在 QSettings，但不要写进报告。

### 13.7 空状态、错误状态、加载状态

**空状态**：图标（用现有 `Meandro`/`Ascuas` 视觉元素即可）+ 一句 `modsEmpty` + 导入按钮。不要显示空白列表加一行「0 个 Mod」，那看起来像坏了。

**加载状态**：列表区域中央显示 `modsBusy`，不要全屏遮罩；用户仍能看到页签与状态条。

**错误状态**（`failed`）：显示标题「Mod 管理器不可用」、可读原因（例如「安装目录缺少 tools/mods/gow_mods_cli.py」或「未找到 Python 3.11+」）、三个按钮：重试、打开日志、打开 Mods 目录。错误原因要来自 `ModsModel::lastError()`，不要把原始 stderr 整段丢给玩家；日志里保留全文。

### 13.8 键盘、焦点与可访问性

- 页签可键盘切换（现有 `TabBar` 行为即可）；进入 Mods 页后焦点落在第一个开关。
- 所有开关有 `Accessible.name`（用 Mod 名 + 开/关状态），便于屏幕阅读器。
- 颜色不是唯一信息载体：ERR 徽标同时显示文字「错误」，冲突圆点同时显示计数。
- 对比度：`Tema.textoTenue` 只用于次要信息，正文用 `Tema.texto`；橙色/红色文字在深色背景上要足够亮。
- 动画克制：开关状态变化用 150ms 过渡即可，不要做闪烁/粒子，避免低端 GPU 上额外负担。

### 13.9 文案规范

- 一律走 `Tema.t(key)`，不硬编码中文/英文。
- 句子短，动词开头；错误信息包含「发生了什么 + 下一步做什么」。
- 不显示内部术语（`planId`、`fingerprintId`）给普通玩家；放在「详情/高级」里。
- Mod 名用玩家包里的 `name`，不要翻译 id。
- 数字用 `%1` 占位符，方便三语调整语序。

### 13.10 UI 测试点清单

1. 无 Mod：进入 Mods 页 → `empty`，导入按钮可用，Play 不注入任何 Mod 变量。
2. 一个合法 Mod：列表 1 行，开关可切换；切换后重启启动器仍保持（profile 持久化）。
3. ERR 包：显示错误原因，开关禁用，Play 不受影响（其他合法 Mod 仍生效）。
4. 冲突：提示区出现，文案包含双方名称；主按钮仍可用（冲突已在 plan 里裁决）。
5. 指纹 stale：状态条红色，点「应用计划」后变绿；点 Play 自动 apply。
6. 无 Python：`failed` 面板，重试/打开日志可用，不启动游戏。
7. 导入重复包：覆盖确认；取消不改变现有包。
8. 禁用全部：确认后列表全关，`state.json` 的 `activePlan` 为空。
9. 页签索引：`TOBIICHI_CAPTURA_PESTANA=6` 截图正确；0..5 仍是原页面。
10. 三语：切换语言后 Mods 页所有文案都有翻译，无英文残留（除 Mod 名）。

---

## 14. Mod 包作者手册（写给内容作者，也给接手者做夹具）

这一章说明「一个能被本管理器接受的 Mod 包应该怎么造」。内容作者按这里做，接手者按这里造测试包。所有规则都对应 `validate_package` 的实现，不是建议。

### 14.1 最小可用包

目录结构：

```
my-mod/
├── mod.toml
├── textures/                （可选，纹理包）
│   └── <hash>-<pal>-<bits>.png
└── payload/                 （可选，VFS 文件）
    └── file.bin
```

最小 `mod.toml`（环境变量型）：

```toml
spec = 1
id = "author.example"
name = "Example parameter pack"
version = "1.0.0"
type = "content"
priority = 0

[target]
game_id = "gow1"

[env]
GOW_SCALER = "bilinear"
```

这个包只改一个运行时已经支持的变量，风险最低。安装后启用，`plan` 会显示 `env=1`。

### 14.2 纹理包制作

步骤：

1. **拿到纹理名**。用 `GOW_TEX_PCSX2_NAMES=1` 跑一次基线会话（建议 `GOW_SKIP_FMV=1` 快速进场景），日志里会输出实际用到的 PCSX2 名。不要凭猜造名字；名字里的 hash 是运行时算出来的。
2. **确认尺寸**。名字最后一段是 `bits` 十六进制；按 4.4 的公式算 TW/TH。例如 `...-00002253` → 512×256。导出的 PNG 必须正好这个尺寸；多一个像素都会被 `textures.size` 拒绝。
3. **格式**。RGBA8 PNG，非隔行；alpha=128 表示 GS 单位不透明（与 patch 52 的解码口径一致）。不要用 16-bit、调色板或 APNG。
4. **命名**。文件名就是纹理名 + `.png`，放在 `[textures] dir`（默认 `textures/`）。不要改大小写；匹配是精确的。
5. **验证**。`python -I tools/mods/gow_mods_cli.py validate my-mod@1.0.0`，必须无 error；再 `plan -p <profile> --json` 看 `textures` 里是否是你的图。
6. **实机**。启用后跑 200 秒，日志应出现 `[gs-texpack] N images` 与 `hits>0`；画面里目标纹理应变化。若没有变化，先确认该纹理真的在本场景使用（名字来自基线会话），再确认 `GOW_TEXTURE_PACK` 指向 staging。

常见错误：

- 把 1024×1024 的图配给 512×256 的名字 → `textures.size`。
- 用 JPEG 改后缀 → `textures.format`（签名不对）。
- 文件名用 `...-00002253.PNG` → 大小写导致不匹配（Windows 文件系统不区分，但运行时按字符串查表可能区分；统一小写）。
- 包内有两张同名不同内容 → 扫描时后一张覆盖前一张，`plan` 只保留一个；不要依赖覆盖顺序，直接删掉旧图。

### 14.3 VFS 包制作

用途：替换游戏按路径打开的文件（IOP 模块、bank、配置文件等）。

```toml
[vfs]
"cdrom0:\\LIBSD.IRX" = "payload/LIBSD.IRX"
"iop_mod\\libsd.irx" = "payload/LIBSD.IRX"
```

规则：

- guest 路径必须是合法前缀（`cdrom0:`、`cdrom:`、`host:`、`mc0:`、`mc1:`、`rom0:`，或 `dir/file` 形式）。反斜杠可以写，CLI 会 canonical 成 `/`。
- payload 必须存在、是普通文件、不能是符号链接、不能是可执行扩展名。
- 同一个 guest 路径在一个包里只能出现一次（canonical 后比较）。
- 覆盖是只读的：运行时不会把写入落到 payload；如果游戏要写这个文件，行为由游戏决定（可能失败或写不进去）。不要用 VFS 覆盖存档文件。
- 大文件会复制/硬链接到 staging；包体积上限 2 GB。不要塞整个光盘。

验证：启用后日志出现 `[mod-vfs] N overrides`，`vfs-stats.json` 的 `hits` 至少 1。若 `hits=0`，说明游戏没有用这个 guest 路径打开文件（名字写错或该文件在本场景未加载）。

### 14.4 环境变量包制作

只允许 7.4 的 `ENV_ALLOWED` 键。值的语义必须来自项目内逆向证据或既有文档，不能「猜一个数值」。例如：

```toml
[env]
GOW_CANCELAR = "1"       # 取消动画后摇，值 0/1
GOW_QTE_HOLD = "1"       # QTE 按住模式
PS2X_GS_HW_SCALE = "2"   # GS 内部倍率 1..8
```

注意事项：

- `engine` 类键（`GOW_VU1_FAST` 等）会改变引擎行为，`plan` 只给 warning；不要把它们包装成「画质 Mod」。
- `diagnostic` 类键只会写诊断，不要用于内容。
- 同一个键被多个 Mod 设置 → 高优先级生效，低优先级被 shadow；作者应在包里声明 `conflicts` 或让玩家只启用一个。
- 值不能含换行，长度 ≤64；布尔值写 `"1"`/`"0"`，不要写 `"true"`（运行时按字符串/atoi 读取，语义可能不同）。

### 14.5 依赖与冲突声明

```toml
[requires]
mods = ["author.base@1.0.0"]

[conflicts]
mods = ["author.alternative"]
```

- `requires` 是硬依赖：缺失 → 计划 error，包被排除。
- `conflicts` 是声明式互斥：两者都启用时按 `rank_of` 淘汰一方；不是「拒绝启动」。如果作者希望「两个都开就报错」，当前不支持，只能靠文档说明。
- 依赖版本写精确 `<id>@<version>` 最稳；只写 `<id>` 时选已安装的最高版本，可能与作者预期不符。

### 14.6 优先级

`priority` 越大越先应用。适用于「基础包 + 补丁包」：

```toml
# base: priority = 10，提供大部分纹理
# patch: priority = 5，覆盖其中三张
```

因为先到先得，base 先占住键，patch 的同名纹理会被 shadow 掉——**这看起来反直觉**。实际语义是「高优先级 = 先写入 = 赢」，所以想让 patch 覆盖 base，patch 的 priority 要**更高**（更大），并且 base 不应该包含会被 patch 覆盖的键。作者应尽量避免同名键，冲突让玩家显式选择。

### 14.7 包作者的测试流程

1. `validate`：结构/路径/尺寸/env 白名单。
2. `plan`：看 `mods` 里是否有你的包、`env/vfs/textures` 计数是否正确、`excluded/conflicts` 是否为空。
3. `apply`：成功后检查 `data/mods/staging/<planId>/` 里有你的文件、`hooks/vfs-overrides.tsv` 有你的行。
4. `run --seconds 200`：看日志钩子与 `state=11`。
5. `deactivate`：确认恢复原版（无钩子行）。

### 14.8 发布与版权

- 不要分发从游戏提取的资源（纹理、音频、IRX、PAK）；只分发你自制的替换内容。
- 包内不要放 `.exe/.dll/.bat/.cmd/.ps1`（会被拒绝）。
- 在 `name`/描述里写清楚「替换了什么、需要哪个区域、是否与其他包冲突」。
- 不要用「一键安装器」；当前管理器只接受目录，这是有意的安全边界。

---

## 15. CLI 逐命令手册

这一章按命令给出「用途、参数、输出、退出码、注意」。命令都在 `tools/mods/gow_mods_cli.py`；所有命令都支持 `--repo <root>` 与 `--mods-dir <dir>`（默认当前仓库的 `data/mods`）。

### 15.1 `fingerprint`

用途：打印当前游戏身份与指纹，刷新 `data/mods/fingerprint.json`。

参数：无（除全局 `--repo`/`--mods-dir`/`--json`）。

输出：`fingerprint <id> changed=<true|false>`，随后逐行打印 `gameId/edition/region/elfCrc/textSha1/runtimeCommit/patchChainHash/runnerSha256`。

注意：`changed=true` 不一定代表「坏了」，只代表自上次记录后输入变了（补丁、runner、区域构建）。启动器可以用这个值判断是否要提示「重新应用」。

### 15.2 `list`

用途：列出所有已安装包与启用状态。

参数：`-p/--profile <name>`（默认 `default`）、`--json`。

输出（文本）：`on/off/ERR` + `id@version` + capabilities + priority。`ERR` 表示有 error，`on` 表示在 profile 里启用。

注意：`list` 会扫描 `packages/` 并对每个包做完整校验，包很多时会慢；UI 首次加载可以用 `--json` 一次拿全。不要给 ERR 包调用 `enable`。

### 15.3 `validate`

用途：只校验，不改任何状态。

参数：`[mod]`（可选，`id@version` 或 `id`）、`-p/--profile`（当不指定 mod 时用于列出该 profile 的包？实际实现是按包扫描）、`--json`。

输出：每个包一行 `OK/ERR` 与 issues；退出码 1 如果存在 error（注意：`validate` 的返回值在实现里是 `bad` 计数，见 `cmd_validate`）。

注意：校验包括 PNG 结构/尺寸、路径穿越、符号链接、env 白名单、依赖语法；它不会检查 guest 路径在游戏里是否真实存在。后者只能实机验证。

### 15.4 `import`

用途：把一个目录安装到 `packages/<id>@<version>`。

参数：`<source>`、`--replace`。

行为：先 `validate_package(source)`；有 error 就打印并退出 2，**不复制**；目标已存在且没有 `--replace` 则退出 3；复制到临时目录再 `os.replace`，Windows 文件锁会重试。

注意：源目录可以不在仓库内；导入是复制，不是移动。导入后源目录仍保留。大包复制会花时间，UI 要显示进度/忙碌。

### 15.5 `enable` / `15.6 disable`

用途：改 profile 的启用列表。

参数：`-p/--profile`、一个或多个 `<id>` 或 `<id>@<version>`。

行为：`enable` 会拒绝不存在或校验失败的包；`disable` 会按 id 移除（带版本时精确匹配）。写 profile 是原子的。

注意：只改 profile，不动 hooks/state；必须再 `apply` 才生效。UI 可以在切换开关后自动 `plan`（预演）但不要自动 apply，避免玩家连点造成多次事务。

### 15.7 `plan`

用途：计算计划但不激活，写 `plans/<planId>.json`。

参数：`-p/--profile`、`--json`。

输出：`plan <id> profile=... mods=N`、逐条 `+`/`-`/`!`，最后 `env/vfs/textures` 计数；`--json` 输出完整结构。

注意：`plan` 会重算指纹并写 `fingerprint.json`；它不会写 `hooks/`。如果 plan 有 error，退出码 2，但计划文件仍会写（便于排查）。启动器可以用 `plan` 来展示冲突而不改变运行状态。

### 15.8 `apply`

用途：事务化激活当前 profile 的计划。

参数：`-p/--profile`、`--allow-empty`。

行为：重算 plan → 有 error 拒绝 → 空计划（profile 有启用但全被排除）拒绝，除非 `--allow-empty` → `activate`：写 journal、物化 staging、写 hooks、写 state。

输出：`activated <planId 前 12 位> (N mods) in <staging>`，以及 `env/vfs/textures` 计数。

注意：`apply` 是唯一会改 `hooks/` 与 `state.json` 的命令；失败会 `restore` 并删除 staging。不要在游戏运行时 apply（staging 正在被读，删除/替换可能让纹理加载失败）；启动器应在启动前完成。

### 15.9 `deactivate`

用途：恢复「从未装过 Mod」的状态。

参数：`--reason <text>`（写进 journal，便于排障）。

行为：把 hooks/state 恢复成激活前快照，删除 staging，写 journal 状态 `rolling-back`。

注意：它不删除包与 profile；玩家下次仍可重新启用。`deactivate` 后 `status` 的 `activePlan` 为空。

### 15.10 `rollback`

用途：回滚当前计划或指定 journal。

参数：`[journal]`（默认当前 `activePlan`）。

行为：读 journal 的 `previous` 快照，恢复 hooks/state，删除对应 staging。

注意：只有在 journal 存在时有效；如果激活早已完成且 profile 又变了，回滚的是「当时的快照」，不是「当前 profile 的上一版」。UI 上的「回滚」建议只在刚 apply 失败/想撤销时使用。

### 15.11 `status`

用途：显示当前激活状态与指纹。

参数：`--json`。

输出：`profile`、`planId`、`fingerprintId`、启用列表、`activePlan` 是否存在。

注意：`status` 也会重算指纹并写 `fingerprint.json`；如果 `activePlan` 与当前指纹不一致，它会显示 stale（`cmd_status` 里用 `fingerprint_changed` 标记）。

### 15.12 `run`

用途：用当前激活计划启动 runner，收集证据；测试/验证专用。

参数：`--label`、`--seconds`、`--no-mods`、`--set KEY=VALUE`（可重复）、`--json`。

行为：设置 `GOW_MOD_VFS_STATS/TRACE` 到本次 run 目录；`--no-mods` 不设置 `GOW_MOD_VFS_TABLE`/`GOW_TEXTURE_PACK`；其余 `--set` 最后覆盖。超时 `kill` 并记 `timedOut=true`。

注意：`run` 不是给玩家用的启动入口；启动器直接启动 runner。`--seconds=0` 表示不限时（调试用，记得手动关）。`--set` 可以覆盖 Mod 的 env，仅用于测试，不要在产品里暴露。

### 15.13 `report`

用途：汇总最近一次（或指定）run 的证据。

参数：`[run]`、`--json`。

输出：run 元数据 + `stderr` 里的 `[gs-texpack]`/`[mod-vfs]`/`[gow-pad2:test] state=`/`[gs-present]` 关键行 + 最后一行。

注意：只读 `data/mods/runs/`，不读游戏日志的其它部分；报告用于排障，不要包含绝对路径给外部。

### 15.14 `selftest`

用途：无游戏数据的隔离自检。

参数：无。

行为：在临时目录造好包/坏包（坏 PNG、路径穿越、尺寸不符、空包），跑 `validate`/`plan`/`activate`，检查 staging 与拒绝逻辑。

注意：它不会启动游戏，也不依赖 `data/gow1` 区域构建；CI 里应作为第一道门。若它失败，先修 CLI，不要继续实机。

---

## 16. 错误码与 issue code 字典

这一章解释每个 `Issue.code` 的含义与处理方式。严重级别为 `error` 的会阻止激活；`warn` 只提示。UI 应把 `error` 用红色、`warn` 用橙色，并显示 `message`（已包含具体值）。

### 16.1 manifest / 包结构

- `manifest.parse`：`mod.toml` 不是合法 TOML，或读取失败。检查引号、括号、编码（UTF-8）。
- `manifest.id`：id 不匹配 `[a-z0-9._-]` 且 2..64 字符。改成小写、去空格。
- `manifest.version`：版本不是数字点分（可带 `-suffix`）。用 `1.0.0`，不要 `v1.0`。
- `manifest.name`：缺少或为空。补一个玩家可读名。
- `manifest.spec`：`spec != 1`。当前只接受 1。
- `manifest.type`：不是 `content`/`code`/`mixed`。内容包写 `content`。
- `manifest.priority`：不是整数或超出 -100..100。用整数。
- `target.missing`：没有 `[target]` 或 `game_id` 为空。补 `game_id = "gow1"`。
- `target.game`：`game_id` 与 `games/gow1/game.toml` 的 id 不符。改成 `gow1`。
- `target.region`：`regions` 里有未知区域。只写 `game.toml` 里存在的 id。
- `target.edition`：`edition` 不是字符串。改成字符串或删掉。
- `requires.mods` / `requires.spec`：依赖不是字符串数组/引用格式错。用 `<id>` 或 `<id>@<version>`。
- `conflicts.mods` / `conflicts.spec`：同上。
- `package.name`：目录名不是 `<id>@<version>`。warn；建议改成规范名，避免重复安装难排查。
- `package.duplicate`：同一个 `id@version` 装了两份（不同目录）。删掉旧目录。
- `package.files`：文件数 >4096。拆包。
- `package.size`：单文件 >256 MB 或总计 >2 GB。删减。
- `path.empty` / `path.absolute`：payload/目录路径为空或绝对路径。改成包内相对路径。
- `path.traversal`：路径逃出包目录（`..`）。改成包内路径。
- `path.symlink`：payload 是符号链接。换成普通文件。
- `file.missing`：目录或文件不存在。检查拼写。

### 16.2 能力与内容

- `capability.code_unsupported`：`type=code/mixed`，当前不交付函数覆盖。改 `content` 或删掉该包。
- `capability.pak_unsupported`：出现 `[pak]`。当前不支持 PAK 重映射。
- `capability.function_unsupported`：出现 `[function]`。当前不支持函数覆盖。
- `capability.script_unsupported`：出现 `[script]`。当前不支持脚本替换。
- `content.empty`：包没有任何 `env`/`textures`/`vfs`。warn；这个包装了也不会改变游戏，通常应删掉或补内容。
- `env.type`：`[env]` 不是表。改成键值表。
- `env.reserved`：用了管理器保留键（`GOW_TEXTURE_PACK` 等）。删掉；这些由管理器设置。
- `env.unknown`：键不在 `ENV_ALLOWED`。先确认运行时读取，再申请加白名单；否则删掉。
- `env.value`：值超 64 字符或含换行。改成单行短值。
- `env.engine` / `env.diagnostic`：warn；该键改引擎/只写诊断。不是错误，但要在 UI 里提示「这不是内容 Mod」。

### 16.3 纹理

- `textures.type`：`[textures]` 结构不对或 `dir` 不是字符串。改成 `dir = "textures"`。
- `textures.name`：文件名不是 PCSX2 名。用 `<hash>-<pal>-<bits>.png`。
- `textures.duplicate`：同名纹理出现两次。删掉一个。
- `textures.format`：PNG 结构损坏（签名/IHDR/IDAT/crc/zlib）。重新导出。
- `textures.size`：图片尺寸与名字 TW/TH 不符。按 4.4 重导出。
- `textures.empty`：目录里没有 PNG。补图或删掉 `[textures]`。

### 16.4 VFS 与 profile

- `vfs.type`：`[vfs]` 不是「guest → payload」表。改成键值表。
- `vfs.guest`：guest 路径不合法。用 `cdrom0:`/`mc0:`/`dir/file` 形式。
- `vfs.duplicate`：canonical 后重复。删掉一条。
- `vfs.executable`：payload 是可执行扩展名。换成数据文件。
- `vfs.shadowed`（warning）：该 guest 已被更高优先级 Mod 提供。让玩家只启用一个，或调 priority。
- `profile.missing`（warning）：profile 里启用的包没安装。重新安装或从 profile 删除。
- `requires.missing`：依赖未安装。装依赖，或删掉该 Mod。
- `requires.cycle`：依赖环。拆环。
- `env.shadowed` / `texture.shadowed`（warning）：资源被更高优先级者占用。调整优先级或只启用一个。

### 16.5 处理顺序建议

1. 先看 `error`，按列表顺序修（前面的错误可能导致后面的连锁）。
2. 再 `validate` 单包，直到无 error。
3. 再 `plan` 看 `excluded/conflicts/warnings`。
4. 最后 `apply` + 实机。

不要用 `--allow-empty` 掩盖「所有包都被排除」；那是给「故意空计划」的测试用的。

---

## 17. 排障案例库

这一章用「现象 → 证据 → 结论 → 动作」的形式记录真实踩过的坑。案例来自本次实现与验证，不是虚构。

### 17.1 启动器里勾了 Mod，日志却完全没有 `[mod-vfs]`

现象：Mods 页显示启用，runner 日志没有 `[mod-vfs]`，画面无变化。

证据：`status` 的 `activePlan` 为空；`hooks/plan.json` 不存在或 profile 不匹配。

结论：勾选只写了 profile，没有 apply；或指纹变化后 `run` 自动 deactivate。

动作：在启动器里点「应用计划」，或在 Play 前调 `prepareSession`；确认 `apply` 输出 `activated ...`。

### 17.2 `[mod-vfs] 1 overrides` 但 `hits=0`

现象：表加载了，但游戏没有命中。

证据：`vfs-trace.txt` 里只有 miss，没有该 guest 路径；或 trace 里的路径拼写与表不同。

结论：游戏没有用这个路径打开文件（名字写错、文件在本场景未加载），或 canonical 规则不一致（非 ASCII/奇怪分隔符）。

动作：用 `GOW_MOD_VFS_LOG=1` 看前几条查找；确认 guest 路径来自实际 trace，而不是猜的；必要时先用 trace 找真实路径再写表。

### 17.3 `[gs-texpack] cannot read ...png`

现象：日志刷大量读取失败，纹理没有替换。

证据：`can't read` 行指向 staging 里的 PNG；`validate` 当时可能通过（如果包被绕过 CLI 手工放进 staging）。

结论：PNG 损坏、尺寸不符、或 staging 文件被杀毒隔离。

动作：重新 `validate` + `apply`；确认 staging 文件存在且能被 Pillow/raylib 打开；不要手改 staging。

### 17.4 运行 40–60 秒退出，无异常日志

现象：`run` 返回 `exit=1`，stderr 最后一行是普通的 pad 输出，没有 `[main] fatal exception`。

证据：Windows 事件日志没有应用崩溃；同一二进制 `--no-mods` 也可能复现；机器上有另一个会话在跑 benchmark/重链接。

结论：外部终止（`taskkill`/job object）或运行时未定位问题，不是 Mod 逻辑崩溃。

动作：安静窗口复跑；记录开始/结束时间；用 `Get-Process ps2EntryRunner` 确认没有别人的实例；若仍复现，保留 stderr 与二进制哈希，单独排查运行时。

### 17.5 替换大纹理后过场退出

现象：启用纹理包后，intro cutscene 42–56 秒退出；换成 64×64 图更稳定复现。

证据：`validate` 如果没拦住，说明尺寸与名字 TW/TH 不符；日志没有 cannot read（图能读，但绑定尺寸不对）。

结论：patch 52 的替换按 GS 尺寸绑定，图片必须与名字尺寸一致。

动作：按 4.4 重导出同尺寸；把 `textures.size` 作为硬错误；不要用缩放图。

### 17.6 `apply` 报 `Permission denied` / WinError 5

现象：导入或 apply 时 `os.replace` 失败。

证据：Windows 杀毒/索引器短暂占用新文件；重试后成功。

结论：文件锁，不是包损坏。

动作：CLI 已重试 6×0.2s；仍失败时提示「稍后重试」，不要提示「Mod 损坏」；检查是否有进程在扫描 `data/mods`。

### 17.7 `apply` 成功但 `status` 显示 stale

现象：刚 apply，status 说指纹不匹配。

证据：这期间补丁目录/runner 哈希/区域构建变了（并行开发常见）。

结论：指纹输入变化。

动作：重新 apply；开发期尽量在安静窗口验证；启动器 Play 前自动 apply。

### 17.8 `enable` 报「does not validate」

现象：Mod 列表 ERR，点开关失败。

证据：`list --json` 的 `issues` 有 error。

结论：包不合法，不能启用。

动作：按第 16 章修包；修好后 `refresh`；ERR 包不能通过「强制启用」绕过（这是有意的）。

### 17.9 空计划被拒绝

现象：`apply` 报「every enabled mod was excluded」。

证据：profile 有启用，但全部因区域/依赖/校验被排除。

结论：玩家以为启用了，实际没有可应用内容。

动作：看 `plan` 的 `excluded` 原因；修包/装依赖/改区域；只有测试才用 `--allow-empty`。

### 17.10 启动器找不到 Python

现象：Mods 页 `failed`，提示 Python 3.11+。

证据：`QProcess::FailedToStart` 或 stderr `ModuleNotFoundError`。

结论：发行环境没装 Python。

动作：设置 `GOW_PYTHON` 指向解释器；或按 5.7 打包/移植；不要在失败时静默无 Mod 启动。

### 17.11 启动器截图页签错位

现象：`TOBIICHI_CAPTURA_PESTANA=6` 截到别的页。

证据：页签被插到中间，索引变化。

结论：新增页签必须放最后。

动作：恢复 0..5 顺序；新页签 index 6；更新截图脚本前先确认索引。

### 17.12 报告里出现绝对路径

现象：导出的会话报告含 `C:\...`。

证据：报告生成代码直接写了 `plan.path` / `state.staging`。

结论：违反 §20.5 白名单。

动作：只写 id/version/planId/fingerprintId/计数；路径放日志，不进报告。

---

## 18. 设计文档导读（面向启动器实现者）

设计文档 2451 行，不需要全读；这一章按章给出「和启动器有关的部分」，并标注哪些结论已被本次实现验证、哪些是未落地规划。读这一章可以替代通读，但改运行时/资源层时仍建议读原文对应章节。

### 18.1 卷 0（速览）

- §0.2 一页结论：工程是「被编译出来的程序」，Mod 是启动时注入，不是改镜像。
- §0.3 五个铁律：安全默认、内容寻址、事务发布、身份校验、版权边界。启动器实现要遵守前四条；第五条体现在不分发游戏资源。
- §0.4 按角色阅读：启动器开发者看 §7.2、§20、附录 C/D 即可。

### 18.2 卷 I（现状盘点）

- 第 1 章：从 ISO 到 runner 的链路；启动器只需要知道「runner 是最终进程，环境变量是接口」。
- 第 2 章：能力清单。§2.1 纹理包（patch 52）已实现；§2.3 函数注入是 L1；§2.4 VFS/启动配置/存档；§2.6 仅规划项（PAK、save、xdelta）不要当接口。**本次新增的 patch 71 是 §2.4/§18.2 的具体落地。**
- 第 3 章：硬约束。§3.1 `fetch` 管控 runtime 树；§3.2 内容寻址/事务；§3.3 帧循环/GL 上下文；§3.4 身份链；§3.6 陷阱清单。启动器不碰 runtime 树，但「不要在帧循环里做 IO」对任何注入代码都成立。

### 18.3 卷 II（架构）

- 第 4 章：目标/非目标/验收。§4.2 明确不做通用管理器、不做 xdelta 主线；§4.3 验收口径可直接抄进任务单。
- 第 5 章：三层注入。L1 源码、L2 env、L3 资源。启动器只负责 L2/L3 的「合成与注入」，不负责 L1。
- 第 6 章：组件/数据流。§6.2 的组件职责（Registry/Fingerprint/Planner/Applier/Journal/Diagnostics）与本次 CLI 的函数一一对应；§6.3「从勾选到进程启动」的时序就是本手册 5.1 的展开。
- 第 7 章：选型。§7.2 混合双层（C++ 核心 + Python 镜像）；§7.3 不通用化；§7.4 不加 stage、不碰 xdelta、尊重 `data/pipeline.lock`。**本次只实现了 Python 层，C++ 是 Phase 3。**
- 第 8 章：目录/所有权。`data/mods/` 的布局与 2.4 一致；`sync_owned` 精神适用于 staging/hooks（一次性产物，不要手改）。

### 18.4 卷 III（数据模型）

- 第 9 章：六条原则/生命周期。包状态机（安装→校验→启用→激活→回滚）对应 CLI 的 scan/validate/enable/apply/rollback。
- 第 10 章：`mod.toml`。§10.1 顶层字段、§10.2 payload 字段、§10.4 settings 覆盖（**本次未做**）、§10.5 禁止内容。本手册 3.2 是实际实现的子集。
- 第 11 章：指纹。§11.1 九个字段、§11.2 patchChainHash、§11.4 三档兼容、§11.6 指纹变化行为。本手册 3.3 是落地版；`runnerSha256` 不参与 fingerprintId 是本次实现的选择，需要写回设计文档。
- 第 12 章：能力/最小权限。§12.1 能力枚举、§12.3 环境变量白名单、§12.4 能力互斥。本手册 7.4 是最新白名单；设计文档里的示例键可能过期。
- 第 13 章：payload 类型。§13.1 纹理、§13.2 VFS、§13.3 函数、§13.4 env/boot、§13.6 save、§13.7 PAK。本次只做 13.1/13.2/13.4 的子集；其余明确降级。
- 第 14 章：冲突/排序。§14.1 资源键、§14.3 确定性算法、§14.4 人工裁决。本手册 3.4 是实际算法；注意「先到先得」与 priority 的关系（14.6 解释过）。
- 第 15 章：profile/state/lock。§15.2 state.json、§15.3 fingerprint.json、§15.4 锁与并发。**本次没有实现 `data/pipeline.lock` 的互斥**；启动器如果触发 L1 重建才需要，当前不触发。

### 18.5 卷 IV（实现）

- 第 16 章：安装/导入。§16.1 两种入口（UI/CLI）、§16.2 校验分层。本次 CLI 的 `import` 对应「目录入口」；没有实现「本地资源登记」入口 B。
- 第 17 章：Planner。§17.1 依赖、§17.2 指纹匹配、§17.3 冲突求解、§17.4 plan.json。本手册 7.2 的字段与它一致（多了内容 sha256）。
- 第 18 章：Applier。§18.1 L2 env 合成、§18.2 VFS 表（**原计划补丁名 `67-mod-hooks.patch`，实际是 `71-mod-vfs-hooks.patch`**）、§18.3 纹理包合并、§18.4 函数链（未做）、§18.5 L1 重建（未做）、§18.6 音频/FMV/文本/存档映射（仅 VFS 级）。
- 第 19 章：事务/回滚。§19.1 三阶段、§19.2 WAL、§19.3 失败矩阵、§19.4「禁用全部=从未装过」。本次 `activate`/`restore` 对应 19.1/19.2；`deactivate` 的验收就是 19.4。
- 第 20 章：Launch Bridge。§20.1 集成位置（启动器预启动，不加 stage）、§20.2 `ModsModel` 接口、§20.3 QML 最小改动面、§20.4 Accessibility 关系（本副本无此页，忽略）、§20.5 导出白名单。**本手册第 5、6、13 章就是这一章的代码级展开，且修正了与实际启动器不符的 sidebar 假设。**
- 第 21 章：诊断。§21.1 三层日志、§21.2 mod-report 字段、§21.4 命中统计、§21.5「Mod 导致崩溃」排查顺序。本手册第 8、17 章与它对齐。

### 18.6 卷 V（质量/合规/路线）

- 第 22 章：测试策略。§22.2 新增测试清单、§22.3 现有必跑、§22.5 验收矩阵。本手册 8.2/8.3 是它的可执行版。
- 第 23 章：性能预算。§23.1 分层预算、§23.2 帧循环零 IO、§23.3 显存/内存。启动器的 Mod 逻辑在进程启动前完成，不进入帧循环；纹理包的内存仍由运行时管理。
- 第 24 章：安全/供应链/版权。§24.1 威胁模型（本地包、路径穿越、可执行 payload）、§24.3 版权边界。本手册 3.5/14.8 是落地版。
- 第 25 章：路线图 P0–P6。本次完成的是「P0/P1 的后端」；启动器 UI 仍属 P0 的最后一公里。
- 第 26 章：风险登记册。与第 9 章互补；设计文档里的「launcher 源码缺失」风险已在本次交接中确认并给出取回步骤。
- 第 27 章：反模式。尤其「不要用 xdelta 做主路径」「不要把 Mod 塞进 stage」「不要在帧循环做 IO」「不要跨游戏通用化」。

### 18.7 附录

- 附录 A：`mod.toml` 示例（纹理/VFS/函数/参数档）。函数示例不要照抄，当前不支持。
- 附录 B：状态文件 schema。与 7.1/7.2 对照看。
- 附录 C：C++ 代码骨架（ModsModel/Registry/Planner…）。Phase 3 可直接当接口草稿。
- 附录 D：CLI 命令表。与第 15 章对照，注意本次实现新增了 `validate`/`report`/`selftest`，设计文档可能没有。
- 附录 E：错误码表。与第 16 章对照，以代码里的 code 为准。
- 附录 F：环境变量速查。与 7.4 对照；设计文档里的部分键可能未被 runtime 读取，加白名单前必须 grep。
- 附录 G：术语表。与 12.3 对照。
- 附录 H：与现有文档的偏差登记。本手册 2.5/18.5 已经列出本次发现的偏差，接手者应把新发现的偏差回写到这里。

---

## 19. 启动器 C++ 实现细节

这一章补足「知道该做什么，但不知道代码怎么写」的部分。所有代码都是示意，不是最终实现；重点是错误处理、线程模型和 JSON 读取的边界。

### 19.1 QProcess 封装

建议把所有 CLI 调用集中到一个函数，避免每个 Q_INVOKABLE 各写一遍：

```cpp
bool ModsModel::runCli(const QStringList &args, int timeoutMs, QString *error, QJsonDocument *jsonOut)
{
    QProcess process;
    process.setProgram(m_python);
    process.setArguments(QStringList{"-I", m_cliPath} + args + QStringList{"--repo", m_repo});
    process.setWorkingDirectory(m_repo);
    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    env.insert("PYTHONIOENCODING", "utf-8");
    process.setProcessEnvironment(env);
    process.start();
    if (!process.waitForStarted(5000))
    {
        *error = tr("Cannot start Python: %1").arg(process.errorString());
        return false;
    }
    if (!process.waitForFinished(timeoutMs))
    {
        process.kill();
        process.waitForFinished(1000);
        *error = tr("Mod manager timed out after %1 s.").arg(timeoutMs / 1000);
        return false;
    }
    const QString out = QString::fromUtf8(process.readAllStandardOutput());
    const QString err = QString::fromUtf8(process.readAllStandardError());
    if (process.exitCode() != 0)
    {
        *error = err.trimmed().isEmpty() ? out.trimmed() : err.trimmed();
        if (error->isEmpty())
            *error = tr("Mod manager failed with exit code %1.").arg(process.exitCode());
        return false;
    }
    if (jsonOut)
    {
        QJsonParseError parse{};
        *jsonOut = QJsonDocument::fromJson(out.toUtf8(), &parse);
        if (parse.error != QJsonParseError::NoError)
        {
            *error = tr("Mod manager returned invalid JSON: %1").arg(parse.errorString());
            return false;
        }
    }
    return true;
}
```

要点：

- `PYTHONIOENCODING=utf-8`：Windows 控制台代码页可能是 936/1252，不设会导致中文路径/Mod 名乱码。
- `-I`：隔离模式，避免用户 `PYTHONPATH`/`sitecustomize` 干扰；这是 CLI 文档要求的运行方式。
- `--repo` 放在参数尾部也有效；注意 argparse 的全局参数要在子命令前还是后，按 CLI 的实际定义来（当前实现里 `--repo` 是顶层参数，放在子命令前更稳）。
- `waitForFinished` 会阻塞 UI 线程。Phase 1 可以在按钮点击时把整个页面置为 `busy` 并 `QApplication::setOverrideCursor`；如果 apply 可能超过 2 秒，改用异步 `QProcess` + `finished` 信号，避免窗口「未响应」。
- 不要用 `QProcess::readAll()` 在进程结束后才读大输出——如果 CLI 输出很多（`plan --json` 可能几百 KB），管道缓冲区会满导致死锁。同步模式下应使用 `waitForFinished` 前先 `setReadChannelMode(SeparateChannels)`，或者异步读取。更稳的是：CLI 输出量大的命令走临时文件（`--json` 输出到 stdout，重定向到文件），但当前 CLI 不支持 `--output`；可以在 C++ 里用 `QProcess` 的 `setStandardOutputFile` 到临时文件再读，避免管道缓冲问题。

### 19.2 JSON 读取

`plan.json`、`state.json` 可能被上一次异常中断留下半个文件（虽然 CLI 用原子写，但玩家可能手改）。读取时必须容忍：

```cpp
QJsonObject ModsModel::readJson(const QString &path, QString *error)
{
    QFile file(path);
    if (!file.exists())
        return {};
    if (!file.open(QIODevice::ReadOnly))
    {
        if (error) *error = tr("Cannot read %1").arg(QFileInfo(path).fileName());
        return {};
    }
    QJsonParseError parse{};
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parse);
    if (parse.error != QJsonParseError::NoError || !doc.isObject())
    {
        if (error) *error = tr("%1 is not valid JSON").arg(QFileInfo(path).fileName());
        return {};
    }
    return doc.object();
}
```

读取 `state.json` 时不要把「文件不存在」当错误——它就是「没有启用任何 Mod」；只有在文件存在但解析失败时才报错，并建议用户点「禁用全部」重建状态（CLI 的 `deactivate` 会写回快照/删除文件）。

### 19.3 状态与信号

`ModsModel` 内部维护：

```cpp
QString m_profile = "default";
QString m_pageState = "loading";
QString m_statusText;
QVariantList m_mods;
QVariantList m_conflicts;
QVariantList m_excluded;
QString m_lastError;
QProcess *m_running = nullptr; // 异步模式
```

每次 `refresh()`：

1. 设 `pageState=loading`，发 `statusChanged`。
2. 跑 `list --json`，解析数组 → `m_mods`。
3. 跑 `status --json`，读 `activePlan`/`fingerprintId`/`profile`。
4. 跑 `plan --json`（预演），解析 `conflicts/excluded/warnings`。
5. 计算 `pageState`：无包 → `empty`；有 error/冲突 → `degraded`；CLI 失败 → `failed`；否则 `ready`。
6. 发 `modsChanged`/`statusChanged`。

不要在每次属性读取时跑 CLI（`Q_PROPERTY` 的 getter 必须常数时间）；所有数据在 `refresh()` 里缓存。

### 19.4 启用/禁用的乐观更新与回滚

开关点击后：

1. 立即把该行的 `enabled` 置为请求值（乐观更新），让 UI 不卡。
2. 同步跑 `enable`/`disable`。
3. 成功：以 `list --json` 的结果为准刷新整页（防止别的包状态变化）。
4. 失败：把该行恢复为磁盘状态，弹出 `error(message)`，不要只把开关弹回去而不解释。

不要在前一个 `setEnabled` 未完成时接受第二次点击；用 `m_busy` 拒绝并提示「正在处理」。

### 19.5 启动前的准备

`prepareSession` 是唯一允许「在 Play 路径上跑 Python」的地方。为了减少阻塞：

- 先读 `state.json`/`plan.json` 做快速路径（5.4 的代码）。
- 快速路径命中时直接用缓存的 `env`，不再跑 CLI。
- 只有状态缺失/指纹不符/`profile` 不同才跑 `apply`。
- `apply` 成功后重读 `hooks/plan.json` 与 `state.json`，不要复用旧对象。
- 失败时 `error` 必须非空；调用方（`jugar()`）看到空 env + 空 error 也要当作失败（防御性检查），因为「静默无 Mod 启动」是最坏的降级。

### 19.6 注入环境变量

`Lanzador::iniciar` 里的注入要放在 `aplicarTarjeta` 之后、日志文件打开之前。顺序很重要：

1. 先处理所有「启动器自己的设置」（窗口、画质、GPU、ISO、缓存）。
2. 再注入 Mod 的 env；遇到已存在的键按 6.3 拒绝。
3. 最后设置 `GOW_MOD_VFS_STATS/TRACE` 诊断路径。
4. 再打开日志文件、`start()`。

如果 `start()` 失败（`FailedToStart`），要清空本次注入的状态（没有全局副作用，但不应该显示「运行中」）。

### 19.7 日志与错误呈现

- C++ 侧用 `qWarning()` 记录完整 stderr，供开发者排查；QML 只显示 `lastError()` 的简短版本。
- `Lanzador::terminado` already 解析 `registro` 的尾部错误行；会话报告可以复用这段逻辑。
- 启动失败（Python/仓库/Mods）应发 `error("errorMods", detail)`，让 QML 的现有错误弹层显示；不要用 `qFatal`/`abort`。
- 如果 Mod 管理器自身崩溃（C++ 异常），`main.cpp` 的默认 Qt 行为会退出；建议在 `ModsModel` 的入口包 try/catch，把异常转成 `lastError`，避免整个启动器挂掉。

### 19.8 单元/集成测试

启动器目前没有 C++ 测试目标；最小可行：

- 用 `pruebas/tst_teclas.qml` 的 QML 测试机制加一个 `tst_mods.qml`，用 mock 的 `mods` 对象（QML 里 `QtObject` 模拟属性/方法）测试页面逻辑（空状态、开关、错误文案）。
- 用 Python 集成测试直接调 CLI（第 8.2 节），覆盖后端；UI 测试只验证绑定，不重复后端逻辑。
- 如果要做 C++ 测试，给 `ModsModel` 注入一个「命令执行器」接口（`std::function`），在测试里替换成固定 JSON 输出，避免真的起 Python。

### 19.9 打包时的资源

`qt_add_qml_module` 会把 `PaginaMods.qml` 编进资源；新增文件必须加入 `ARCHIVOS_QML`，否则运行时报 `module "Tobiichi" is not installed` 或页面空白。C++ 源文件必须加入 `qt_add_executable` 的列表，否则链接失败。改完 `CMakeLists.txt` 后必须重新配置（删 `build/CMakeCache.txt` 或让 Ninja 自动重新跑 CMake），不要只 `ninja`。

---

## 20. 实机验证的细粒度做法

第 8 章给了命令；这一章解释「怎么判读、怎么留证据、怎么复现」。验证的目标不是「进程活着」，而是「游戏真的进了 3D 场景、资源真的被替换、禁用后真的恢复」。

### 20.1 场景与输入脚本

日版光盘的标题→菜单→新游戏需要按键。本次使用的脚本：

```
5:start,8:circulo,12:circulo,16:circulo,20:circulo,25:circulo,30:circulo,
40:circulo,50:circulo,60:circulo,70:circulo,80:circulo,90:circulo,
100:circulo,110:circulo,120:circulo,130:circulo,140:circulo,150:circulo,
160:circulo,170:circulo,180:circulo,190:circulo
```

语义：第 5 秒按 Start，之后每 5–10 秒按一次「确认」（日版 `circulo`，即 O 键）。多次重复是为了容忍加载慢/菜单焦点变化；即使某次按键落在过场里，也不会改变状态。

为什么不用更短的脚本：

- 启动阶段受 VU1 JIT 编译、着色器缓存、磁盘速度影响，`START` 太早会停在标题。
- 菜单到新游戏需要多次确认；只按一次常常不够。
- 200 秒是为了覆盖「标题 → 过场 → 玩法」并留出稳定观察窗口；60 秒截图只能看到过场。

注意：`GOW_PAD_GUION` 的按钮名是项目自定义的（`start`、`circulo`），不是 PS2 原始键名；换区域/换语言时按钮映射可能不同。美版/欧版请先跑 `GOW_PAD_TEST=1` 看实际按下效果。

### 20.2 截图

`GOW_PAD_CAPTURAS=60,100,140,180` 会在这些秒数写 `gow_pad_test_N.ppm` 到 runner 的工作目录（CLI `run` 的 cwd 是 ELF 所在目录）。本次验证中：

- 60 秒：intro cutscene（船甲板、雨、Kratos）。
- 100/140/180 秒：玩法/场景，能看出 HUD、角色、地形。

判读要点：

- **正常**：角色、HUD、地形颜色自然；没有大片纯色（品红/黑/白）除非场景本来如此；没有三角形撕裂、Z 冲突、纹理缺失导致的灰白格。
- **Mod 生效**：示例 Mod 的 7 张品红纹理应在它们出现的场景里显示为纯品红（远处岩壁/地形），Kratos 与 HUD 不受影响。若截图时刻没有这些纹理入镜，不能凭画面断言「没生效」；用 `[gs-texpack] hits>0` 与 `loads=7` 作为证据。
- **禁用后**：画面应与无 Mod 基线一致；日志无 `[mod-vfs]`/`[gs-texpack]`。

PPM 是二进制 P6，`PIL.Image.open` 可直接读并转 PNG；转换脚本在本次运行目录的 `shots/` 里。不要把 PPM 交给玩家或上传（体积大且含游戏画面）。

### 20.3 日志判读

一次成功运行的关键行（按时间顺序）：

```
[mod-vfs] 1 overrides from ...\data\mods\hooks\vfs-overrides.tsv
[gs-texpack] 7 images in ...\data\mods\staging\<planId>\textures
[gow-fmv] skipped Semo01
[gow-pad2:test] gameplay start at 47.36 s (frame 47)
[gs-texpack] hits=1090 loads=7 evictions=0 resident=7 MB
[gow-pad2:test] state=11 pending=0 stage=0 levelReady=1 ...
[gs-texpack] hits=4856 loads=7 evictions=0 resident=7 MB
```

判据：

- `[mod-vfs]` 行只在有 VFS 覆盖时出现；数字应等于 plan 的 `vfs` 条目数。
- `[gs-texpack] N images` 应等于 plan 的 `textures` 条目数；`loads` 应等于 N（全部被加载），`hits` 随时间增长。
- `gameplay start at X s` 是进入可操作玩法的标志；`state=11` 是 pad 测试的状态（levelReady=1）。
- `cannot read` 任何一行都是失败信号。
- `[main] fatal exception` / `[terminate]` 是崩溃信号；没有这些行但进程 `exit=1`，优先怀疑外部终止（见 17.4）。

### 20.4 失败/超时的记录

CLI `run` 会写 `run.json`：`seconds`、`timedOut`、`exitCode`、`fingerprintChangedDuringRun`、`envApplied`、`vfs`。验证报告至少记录：

- 运行目录名（含时间戳）。
- 二进制 SHA-256（`Get-FileHash`）。
- 指纹 ID 与 `planId`。
- 开始/结束时间、`exitCode`、是否超时。
- 关键日志行（复制 5–10 行）。
- 截图文件名与观察结论。

如果 `fingerprintChangedDuringRun=true`，这次结果不能用于「三态对比」——说明运行期间输入变了（并行会话/重编译），必须重跑。

### 20.5 性能与资源观察

Mod 管理器本身不在帧循环里，但纹理包会影响显存/带宽。验证时可以顺带看：

- `GOW_TEXTURE_PACK_STATS=1` 的 `resident MB`：7 张 512×512/512×256 ≈ 7 MB，远低于默认 1024 MB 预算；如果 Mod 包很大，观察是否触发 `evictions`。
- `GOW_GS_HW_STATS=1` 的 `fps`/`gs_ms`：替换纹理不应改变帧率量级；如果明显下降，检查图片尺寸是否过大或 `GOW_TEXTURE_PACK_MB` 太小导致抖动。
- 进程内存：任务管理器看 `ps2EntryRunner` 的私有工作集；示例 Mod 不应有肉眼可见的增长。

### 20.6 复现与对照

三态验证必须同一二进制、同一光盘、同一脚本、同一机器：

1. 记录二进制哈希；如果中途重编译，三态要全部重跑。
2. 无 Mod 先跑；如果它都无法稳定进玩法，先修环境，不要继续。
3. 启用 Mod 跑；对比关键日志差异（只应多出 `[mod-vfs]`/`[gs-texpack]` 行）。
4. 禁用后跑；应与第 2 步一致（日志、画面）。
5. 每一步保存截图与 `run.json`；不要只凭记忆。

---

## 21. 工程协作与构建纪律

这一章是「怎么在这个仓库里不闯祸」的约定。很多是本次交接踩过的坑。

### 21.1 两棵树的所有权

- `engine/runtime` 是 git 克隆；`engine/patches` 是本项目的补丁。改运行时必须通过补丁，不要直接改 `engine/runtime` 后忘记生成 patch。
- `C:\gow-jpn` 是构建源；`engine/runtime` 的改动要同步过去（本次是复制 4 个文件）。不要在 `C:\gow-jpn` 里做「只此一份」的修改，否则补丁链无法重建。
- `C:\gow-build-jpn` 是构建目录；不要把它当源码仓库，也不要提交。
- 工作副本根目录不是 git 仓库；「不 commit、不 push」的约束来自任务本身，不要因为看到 `C:\gow-jpn` 是 git 仓库就去提交。

### 21.2 补丁纪律

- 编号取当前最大值 + 1；动手前重新列目录，因为并行会话会加补丁。
- 补丁头部写清楚：做什么、为什么、证据、涉及文件；`git apply` 会跳过 `#` 开头的行（本项目的补丁格式）。
- 生成补丁用 LF（`newline="\n"`）；Windows 默认 CRLF 会让 `git apply` 报空白错误。
- 应用测试：在一个干净基线上 `git apply`，再与工作树比较（忽略 CRLF）。本次的 `check_patch71.py` 就是这个思路。
- README 表必须同步；不要只加文件不加表。
- 如果编号冲突无法避免，优先「改自己的号」而不是删别人的补丁；在 README 与文档里登记冲突。

### 21.3 构建纪律

- 干净全量编译用 `ninja -t clean` + `ninja ps2EntryRunner`；增量编译只适合注释/小改。
- 重链接 `ps2EntryRunner.exe` 时如果有进程在跑，会 `Permission denied`；等它退出，或复制一份改名运行（但验证要用正式路径）。
- 启动器构建与 runner 构建是两套目录；不要混用 `launcher/build` 与 `launcher/build-clang`。
- Qt 资源（QML）需要重新配置 CMake 才会进资源；只 `ninja` 可能漏掉新文件。

### 21.4 数据与临时文件

- `data/mods/` 是运行数据，不是源码；可以清理 `runs/`、`staging/` 旧目录，但不要删 `packages/` 里玩家/验证用的包。
- `data/_tmp/` 是临时目录；交接前清理自己的脚本与 fixture，但保留验证日志直到验收。
- 不要提交/打包 `data/mods/staging` 的大文件（硬链接/副本）；发行包只带空目录或示例。
- 示例 Mod 的 `LIBSD.IRX` 是游戏数据，不能进发行包。

### 21.5 测试门

提交/交付前至少跑：

1. `python -I tools/mods/gow_mods_cli.py selftest`。
2. `tools/test/patch-stack-tests.ps1`（如果环境允许）验证补丁链可应用。
3. `tools/test/launcher-languages.py`（启动器改动后）。
4. 第 8.3 的三态（至少无 Mod + 启用）。
5. `git apply` 前向测试（补丁改动后）。

### 21.6 并行会话

本次最大的外部风险是同一工作树有另一个会话在改渲染补丁、重链接、跑 benchmark。约定：

- 动手前看 `engine/patches` 最新编号与 `Get-Process ps2EntryRunner`。
- 不要 `taskkill` 不是自己启动的进程；不要删 `.tmp` 里别人的文件。
- 重链接失败先等 10–20 秒再重试（杀毒/占用）。
- 验证结果如果出现「非超时退出且无异常」，先怀疑外部干扰，再怀疑自己的代码。
- 文档里记录「并发现象」，但不要把别人的补丁写进自己的交付说明。

### 21.7 代码风格

- Python：标准库、类型标注、`pathlib`、原子写；不要引入第三方依赖（Pillow 只用于验证脚本，不是 CLI 运行时依赖）。
- C++：Qt 6/C++20，遵循现有 `lanzador.cpp` 的命名（西班牙语方法名/变量名是本项目风格，新增代码可以沿用或英文，保持一致即可）。
- QML：复用 `Tema`/`Fila`/`Interruptor`/`BotonSecundario`，不要新造一套视觉。
- 注释：解释「为什么」，不要复述代码；测量得出的约束要写日期与证据（如 4.4）。

### 21.8 文档回写

改了以下内容必须同步文档：

- 补丁编号/内容 → `engine/README.md`。
- 数据目录/协议 → 本手册第 7 章 + `docs/architecture.md`。
- 启动器页面/设置 → `AGENTS.md` 页面表（如果存在）+ 本手册 6.5/13。
- 新发现的设计文档偏差 → 本手册 2.5 与设计文档附录 H。

---

## 22. 交接收尾：开放问题与确认清单

### 22.1 需要产品/作者确认的问题

1. **发行版是否允许依赖 Python？** 如果否，Phase 3（C++ 核心）必须提前到发布前，不能拖。
2. **Mod 数据放安装目录还是 AppData？** 当前 CLI 默认 `data/mods`；如果安装目录不可写，需要迁移策略与兼容旧路径。
3. **是否允许 Mod 覆盖 `mc0:`/`mc1:`（存档）？** 当前不禁止；若不允许，应在 `validate` 增加拒绝规则并在文档说明。
4. **是否提供「临时无 Mod 启动」按钮？** 当前设计是 `modsEnabled` 开关；确认是否要放在封面 Play 按钮旁。
5. **是否支持 zip 导入？** 当前只接受目录；zip 需要解压到临时目录再校验，涉及路径穿越风险，建议不做或严格限制。
6. **示例 Mod 是否保留在仓库？** 它含游戏数据（IRX/纹理），只能本地验证；发布前必须删除或替换。
7. **多语言范围**：当前 `Textos.js` 只有 tr/en/es；是否补 fr/de/it/ru/zh？补齐会增加维护量。
8. **Mod 列表的排序**：确认默认按 id 还是按启用/优先级；本手册建议 id，避免开关跳行。

### 22.2 交付前确认清单（逐项打勾）

- [ ] 文档第 2.5 节的「文档/代码冲突」已由当前代码验证，没有新增冲突。
- [ ] `engine/patches/71-mod-vfs-hooks.patch` 能在一个干净基线上 `git apply`，且内容与工作树一致（忽略 CRLF）。
- [ ] `engine/README.md` 的 71 行存在，描述与实测一致。
- [ ] `tools/mods/gow_mods_cli.py` 的 `selftest` 通过。
- [ ] `data/mods/packages/verify.gow.subset@1.0.0` 存在且 `validate` 通过。
- [ ] 无 Mod / 启用 / 禁用三态各有一份 `run.json` 与截图证据。
- [ ] 干净全量编译通过（记录目标数/退出码）。
- [ ] 启动器源码已取回并能构建（Phase 0）。
- [ ] 启动器 Mods 页最小闭环可用（Phase 1）。
- [ ] 没有把 `LIBSD.IRX`、纹理图、存档、ISO 放进任何发行目录。
- [ ] `data/_tmp` 的临时脚本/夹具已清理，验证日志保留。
- [ ] 没有 git commit / push（按任务约束）。

### 22.3 本次交接的「已完成 / 未完成」一页表

| 项目 | 状态 | 证据/位置 |
|---|---|---|
| 运行时 VFS 覆盖 | 完成 | patch 71、`mod_vfs_table.*`、`[mod-vfs]` 日志 |
| 纹理包覆盖 | 完成（复用 patch 52） | `[gs-texpack] 7 images`、`hits=4856` |
| 环境变量 Mod | 完成 | plan.env、白名单、apply |
| 发现/校验/冲突/排序 | 完成 | CLI、selftest、plan JSON |
| 事务/回滚/持久化 | 完成 | journal、state.json、deactivate |
| 无 Mod 安全默认 | 完成 | 200 s 基线、无钩子日志 |
| 实机三态 | 基本完成 | 8.4；禁用后用早期同代码证据 |
| 启动器源码 | 未完成 | 工作副本缺，`C:\gow-jpn` 有 |
| 启动器 UI/注入 | 未完成 | 本手册第 5/6/13/19 章 |
| Python 打包/C++ 核心 | 未完成 | 5.7、10.4 |
| `.PAK`/函数/脚本/存档 | 明确不做 | 3.6、16.2 |
| 设计文档回写 | 部分 | 2.5/18.5 已记录 |

### 22.4 最后的话

这次交付把一个「看起来只是界面」的需求拆成了三层：运行时钩子（patch 71）、可测试的 Python 核心（CLI）、启动器薄壳（未做）。前两层已经在真实游戏里跑通；第三层的工作量与风险主要不在代码，而在「取回启动器源码、决定 Python 依赖、不要静默降级」这三件事上。

接手时请先把本手册 0.3 的三件事做完，再读第 5、6 章；不要从写 UI 开始，也不要先改运行时。遇到文档与代码冲突，以 `C:\gow-jpn` 的代码为准，并把冲突补进 2.5。遇到「进程莫名其妙退出」，先看 17.4，再怀疑自己的改动。

祝顺利。

---

## 23. 验收测试用例全集

这一章给出一套可以逐条执行的验收用例，覆盖包校验、计划、事务、运行时、启动器 UI、构建回归。每条都写「目的、步骤、期望」，可以直接贴进测试管理工具。用例编号稳定，便于回归时引用；新增用例追加编号，不要重排。

### 23.1 A 组：包发现与校验

**A-01 最小合法包通过**

目的：确认校验器接受最小内容包。步骤：造一个只有 `spec/id/name/version/type/target.game_id` 的目录，跑 `validate`。期望：退出码 0，无 error；`list` 显示 `off`（未启用）而不是 `ERR`。

**A-02 缺少 `mod.toml`**

目的：确认不会把普通目录当包。步骤：在 `packages/` 放一个没有 `mod.toml` 的目录，跑 `list`。期望：该目录被忽略，不产生 ERR 行；不崩溃。

**A-03 非法 id**

目的：确认 id 规则。步骤：`id = "Bad ID!"`，跑 `validate`。期望：`manifest.id` error，退出码非 0，`import` 拒绝复制。

**A-04 版本格式**

目的：确认版本规则。步骤：`version = "v1"`。期望：`manifest.version` error。改成 `1.0.0` 后通过。

**A-05 缺 `target.game_id`**

目的：确认目标必填。步骤：删掉 `[target]`。期望：`target.missing` error；不能启用。

**A-06 区域不匹配**

目的：确认区域过滤。步骤：`regions = ["usa"]`，当前日版。期望：`plan` 的 `excluded` 出现「targets region usa, this is asia」，包不进入 `mods`。

**A-07 依赖缺失**

目的：确认硬依赖。步骤：`requires.mods = ["no.such@1.0"]`，启用后 `plan`。期望：`requires.missing` error，包被排除，退出码 2。

**A-08 依赖环**

目的：确认环检测。步骤：A 依赖 B、B 依赖 A，都启用。期望：`requires.cycle` error；不会无限循环。

**A-09 目录穿越**

目的：确认路径安全。步骤：`[textures] dir = "../outside"`。期望：`path.traversal` error；不读取包外文件。

**A-10 符号链接 payload**

目的：确认不跟随链接。步骤：`payload/link.bin` 指向包外文件。期望：`path.symlink` error；不复制链接目标。

### 23.2 B 组：计划与冲突

**B-01 单包 env**

目的：确认 env 合成。步骤：包设 `GOW_SCALER = "sharp"`，`plan --json`。期望：`env.GOW_SCALER.value == "sharp"`，`mods=1`，`planId` 稳定（同输入两次相同）。

**B-02 同键不同值**

目的：确认先到先得。步骤：两个包都设 `GOW_SCALER`，值不同，priority 不同。期望：高优先级生效；低优先级出现在 `warnings` 的 `env.shadowed` 与 `conflicts`。

**B-03 同键相同值**

目的：确认可合并。步骤：两个包都设 `GOW_SCALER="sharp"`。期望：只保留一个 `env` 条目，无冲突（或只有 warning，按实现）。

**B-04 同名纹理**

目的：确认纹理遮蔽。步骤：两个包提供同一 PCSX2 名。期望：高优先级纹理进入 `textures`，低优先级 `texture.shadowed`。

**B-05 同 guest 路径**

目的：确认 VFS 遮蔽。步骤：两个包映射同一个 guest 路径。期望：高优先级进入 `vfs`，低优先级 `vfs.shadowed`。

**B-06 声明冲突**

目的：确认冲突裁决。步骤：A 声明 `conflicts.mods=["B"]`，两者都启用。期望：`conflicts` 有一条；rank 较低者被 `excluded`；不会两个都进 `mods`。

**B-07 空计划**

目的：确认拒绝「假启用」。步骤：profile 启用一个被区域排除的包，`apply`。期望：退出码 2，提示 every enabled mod was excluded；`state.json` 不变。

**B-08 指纹变化**

目的：确认计划失效。步骤：apply 后改一个补丁文件，跑 `status`。期望：显示 stale；`apply` 重新生成新 `planId`。

### 23.3 C 组：事务与回滚

**C-01 apply 成功**

目的：确认 hooks/state 一致。步骤：apply 一个合法包。期望：`state.json` 的 `activePlan` 等于 `hooks/plan.json` 的 `planId`；staging 存在；`env.json`/`vfs-overrides.tsv` 内容正确。

**C-02 staging 残留清理**

目的：确认不会复用旧文件。步骤：apply A，再改包内容 apply B。期望：旧 staging 被删或重建，新 staging 只含 B 的文件。

**C-03 物化失败回滚**

目的：确认失败不破坏旧状态。步骤：apply A 成功后，人为删除 B 的 payload 再 apply（或让磁盘只读）。期望：apply 失败，hooks/state 恢复为 A；journal 状态 `rolled-back`。

**C-04 deactivate**

目的：确认恢复原版。步骤：apply 后 `deactivate`。期望：`activePlan` 为空；hooks 文件被删除或恢复；staging 被删除。

**C-05 rollback**

目的：确认 journal 回滚。步骤：apply 后立即 `rollback`。期望：回到 apply 前的 hooks/state；journal 存在且状态正确。

**C-06 重复 apply 幂等**

目的：确认同计划重复执行不产生垃圾。步骤：同一 profile 连续 apply 两次。期望：第二次成功、`planId` 相同或等价、staging 不重复堆积。

**C-07 原子写**

目的：确认不会读到半个 JSON。步骤：apply 时并发读 `plan.json`/`state.json`（脚本循环解析）。期望：永远能解析，不出现 JSON 错误。

### 23.4 D 组：运行时资源

**D-01 无 Mod 安全默认**

目的：确认不改变原版。步骤：`run --no-mods` 200 秒。期望：无 `[mod-vfs] N overrides`、无 `[gs-texpack]`、无 `cannot read`、`state=11`。

**D-02 VFS 命中**

目的：确认 patch 71。步骤：启用映射 `iop_mod\libsd.irx` 的包，跑。期望：`[mod-vfs] 1 overrides`，`vfs-stats.json` 的 `hits>=1`。

**D-03 纹理命中**

目的：确认 patch 52 路径。步骤：启用 7 张纹理的包，跑。期望：`[gs-texpack] 7 images`，`loads=7`，`hits` 增长，`resident` 合理。

**D-04 纹理尺寸不符**

目的：确认不会崩溃。步骤：造 64×64 PNG 配 512×512 名，`validate`。期望：`textures.size` error；无法 apply；不会进游戏。

**D-05 PNG 损坏**

目的：确认提前拒绝。步骤：把 PNG 截断或改字节，`validate`。期望：`textures.format` error；不复制到 staging。

**D-06 禁用后恢复**

目的：确认可逆。步骤：apply → run → deactivate → run --no-mods。期望：第二次无任何 Mod 钩子行；画面与 D-01 一致。

### 23.5 E 组：启动器 UI

**E-01 空列表**

目的：确认空状态。步骤：清空 `packages/`，打开 Mods 页。期望：`empty` 状态，导入按钮可用，不显示空白列表。

**E-02 列表与开关**

目的：确认绑定。步骤：装一个包，打开 Mods 页，切换开关。期望：开关立即响应，profile 文件变化，重启启动器后状态保持。

**E-03 ERR 包不可启用**

目的：确认错误展示。步骤：装一个坏包，打开 Mods 页。期望：ERR 徽标、原因可见、开关禁用；其他包仍可启用。

**E-04 指纹横幅**

目的：确认 stale 可见。步骤：apply 后改补丁，打开 Mods 页。期望：红色横幅；点「应用计划」后变绿。

**E-05 Play 失败不启动**

目的：确认安全默认。步骤：让 `prepareSession` 失败（改坏 `plan.json` 或移除 Python），点 Play。期望：弹错、不启动 runner、不显示「运行中」。

**E-06 无 Mod 启动**

目的：确认启动器不注入。步骤：清空 profile，点 Play，看 runner 日志。期望：无 `[mod-vfs]`/`[gs-texpack]`；环境变量集合与改造前一致。

### 23.6 F 组：构建与回归

**F-01 补丁可应用**

目的：确认补丁链可重建。步骤：干净基线按名应用 01..71。期望：全部 clean；71 的四个文件与工作树一致（忽略 CRLF）。

**F-02 干净全量编译**

目的：确认没有隐藏依赖。步骤：`ninja -t clean` + 全量构建。期望：成功，无 error；记录目标数。

**F-03 启动器构建**

目的：确认 QML 资源。步骤：复制源码、CMake 重新配置、构建。期望：`gow-launcher.exe` 生成；新页面能打开。

**F-04 CLI 自检**

目的：确认后端纯逻辑。步骤：`selftest`。期望：全部通过；临时目录被清理。

**F-05 旧开关未破坏**

目的：确认 patch 59–66 行为。步骤：分别用 `PS2X_GS_RUN=0/1`、`PS2X_GS_PIPELINE`、`GOW_VU1_FAST` 跑短程。期望：均能启动、无新崩溃；`state=11`（短程至少到玩法）。

### 23.7 用例执行顺序建议

1. A 组（纯校验，最快，先排除包问题）。
2. C 组（事务，不需要游戏）。
3. F-04、F-01（构建/补丁门）。
4. D 组（实机，安静窗口）。
5. E 组（启动器 UI，最后做，避免 UI 问题干扰后端判断）。
6. F-02/F-03/F-05（交付前回归）。

每组失败时先看该组的「目的」——目的不成立时，不要继续后面的组。例如 A-01 失败说明基础校验坏了，此时跑 D 组没有意义。

---

## 24. 联调脚本与命令清单

这一章提供可以直接复制执行的脚本，把「取源码 → 构建 → 截图 → 装 Mod → 启用 → 实机 → 禁用 → 汇总证据」串起来。脚本假设当前目录是工作副本根 `<repo>`，PowerShell 5。执行前先读第 21.6 节，确认没有并行会话在跑。

### 24.1 环境自检

```powershell
# 1) 目录与关键文件
$root = (Get-Location).Path
$need = @(
  "tools/mods/gow_mods_cli.py",
  "games/gow1/game.toml",
  "data/gow1/regional-builds.json",
  "engine/patches/71-mod-vfs-hooks.patch"
)
foreach ($p in $need) {
  if (Test-Path (Join-Path $root $p)) { "OK   $p" } else { "MISS $p" }
}

# 2) Python
python --version
python -I tools\mods\gow_mods_cli.py selftest

# 3) runner 是否被占用
Get-Process ps2EntryRunner -ErrorAction SilentlyContinue | Select-Object Id,StartTime

# 4) 补丁最大编号（避免重号）
Get-ChildItem engine\patches | Sort-Object Name | Select-Object -Last 5 Name
```

期望：四个关键文件都存在；Python 3.11+；`selftest` 通过；没有别的 runner 进程；补丁最大号与你要用的号相邻。

如果 `data/gow1/regional-builds.json` 里的 `runner_sha256` 与 `C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe` 的哈希不一致，说明构建产物与配置不同步。用 `Get-FileHash` 比对，必要时重新构建并更新该字段（该字段由构建/发布流程写，不要手改除非你知道在做什么）。

### 24.2 取回启动器源码并构建

```powershell
$root = (Get-Location).Path
$src  = "C:\gow-jpn\launcher"

# 只在缺失时复制，避免覆盖你正在改的文件
if (!(Test-Path "$root\launcher\src"))       { Copy-Item -Recurse -Force "$src\src"       "$root\launcher\src" }
if (!(Test-Path "$root\launcher\qml"))       { Copy-Item -Recurse -Force "$src\qml"       "$root\launcher\qml" }
if (!(Test-Path "$root\launcher\recursos"))  { Copy-Item -Recurse -Force "$src\recursos"  "$root\launcher\recursos" }
if (!(Test-Path "$root\launcher\CMakeLists.txt")) { Copy-Item -Force "$src\CMakeLists.txt" "$root\launcher\CMakeLists.txt" }

# 用项目流水线构建（Qt 工具链在 data/_tools）
.\build.cmd -Stages launcher
```

如果没有 `build.cmd` 的 Qt 环境，手工构建：

```powershell
cmake -S launcher -B launcher/build -G Ninja -DCMAKE_BUILD_TYPE=Release
ninja -C launcher/build
```

构建后截图基线：

```powershell
$env:TOBIICHI_CAPTURA = "$root\data\_tmp\launcher-before.png"
$env:TOBIICHI_CAPTURA_PESTANA = "0"
& "$root\launcher\build\gow-launcher.exe"
Remove-Item Env:TOBIICHI_CAPTURA
Remove-Item Env:TOBIICHI_CAPTURA_PESTANA
```

期望：3 秒后生成 PNG，启动器自动退出；PNG 能看出封面与页签。若没有生成，检查 `build.ps1` 的 launcher stage 是否真的编译了你复制的源码，而不是旧 `launcher/bin`。

### 24.3 后端三态脚本

把下面的函数放进一个 `.ps1`（不要提交），按顺序跑：

```powershell
$root = (Get-Location).Path
$py   = "python"
$cli  = "tools\mods\gow_mods_cli.py"
$script = "5:start,8:circulo,12:circulo,16:circulo,20:circulo,25:circulo,30:circulo,40:circulo,50:circulo,60:circulo,70:circulo,80:circulo,90:circulo,100:circulo,110:circulo,120:circulo,130:circulo,140:circulo,150:circulo,160:circulo,170:circulo,180:circulo,190:circulo"

function Invoke-ModRun([string]$label, [string]$profile, [switch]$noMods, [switch]$stats) {
  $args = @("-I", $cli, "run", "--label", $label, "--seconds", "200")
  if ($noMods) { $args += "--no-mods" } else { $args += @("-p", $profile) }
  $args += @(
    "--set", "GOW_PAD_TEST=1",
    "--set", "GOW_PAD_GUION=$script",
    "--set", "GOW_PAD_CAPTURAS=60,100,140,180",
    "--set", "GOW_VU1N_X64=1",
    "--set", "PS2X_GS_HW_SCALE=0.5",
    "--set", "GOW_SKIP_FMV=1"
  )
  if ($stats) { $args += @("--set", "GOW_TEXTURE_PACK_STATS=1") }
  & $py @args
}

# A. 无 Mod
Invoke-ModRun "off" "verify" -noMods

# B. 启用（先 apply）
& $py -I $cli apply -p verify
Invoke-ModRun "on" "verify" -stats

# C. 禁用后
& $py -I $cli deactivate
Invoke-ModRun "after-disable" "verify" -noMods
```

期望输出（每个 run 末尾）：

```
run <秒数>s exit=<0|1|...> timeout=<True|False>
  mods: ...
  vfs stats: {'overrides': N, 'lookups': M, 'hits': H, ...}
  [gow-pad2:test] state=11 pending=0 ...
```

判读：A 与 C 的 `overrides=0`、`hits=0`，日志无 `[mod-vfs] N overrides`（N>0）与 `[gs-texpack]`；B 的 `overrides=1`、`hits>=1`，日志有 `[gs-texpack] 7 images`。

超时退出是正常的（`--seconds 200` 到点会 kill）；`timedOut=True` 且 `state=11` 说明跑满了。非超时的 `exit=1` 按 17.4 处理。

### 24.4 证据汇总

```powershell
$run = Get-ChildItem data\mods\runs | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content "$($run.FullName)\run.json"
Select-String -Path "$($run.FullName)\stderr.log" -Pattern "mod-vfs|gs-texpack|gameplay start|state=11|cannot read|fatal exception" |
  Select-Object -First 20 | ForEach-Object { $_.Line }
Get-ChildItem "$($run.FullName)\shots" -ErrorAction SilentlyContinue
```

把输出贴进交付报告，附上二进制哈希：

```powershell
(Get-FileHash C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe -Algorithm SHA256).Hash
```

### 24.5 启动器最小联调的期望

如果你已经按第 6 章接了 `ModsModel`，联调时可以不开游戏，先验证三件事：

1. 打开 Mods 页，列表有 1 个示例 Mod，开关状态与 `profiles/verify.toml` 一致。
2. 点开关，`profiles/verify.toml` 文本变化；重启启动器后状态保持。
3. 点 Play 前，`data/mods/state.json` 的 `activePlan` 与 `hooks/plan.json` 的 `planId` 一致；runner 日志出现 `[mod-vfs]`/`[gs-texpack]`。

如果第 3 步失败，先看启动器日志（`%APPDATA%\Tobiichi\LauncherUltimate\registros\ultimo.log`）里有没有 `GOW_MOD_VFS_TABLE`/`GOW_TEXTURE_PACK` 相关注入；再确认 `Lanzador::iniciar` 是否真的收到了 `entornoMods`（在 C++ 里加一行 `qDebug()` 打印键名即可，发布前删掉）。

### 24.6 脚本使用注意事项

- 脚本里的 `$root` 必须是工作副本根；不要在 `C:\gow-jpn` 里跑，否则 `data/mods` 会写到另一棵树。
- `Invoke-ModRun` 的 `--set` 顺序会影响覆盖：`GOW_TEXTURE_PACK_STATS` 在最后加，不会覆盖 Mod 的值（它不在白名单但也不是保留键；测试专用）。
- 不要把 `GOW_PAD_TEST`/`GOW_PAD_GUION` 写进 Mod 包；它们在 `ENV_RESERVED` 里，会被拒绝。
- 验证结束记得清掉 `$env:TOBIICHI_CAPTURA` 等临时变量，否则下次打开启动器会直接退出。
- 如果脚本报 `Permission denied`（重链接/写 `data/mods`），先等 10–20 秒再重试；不要强杀进程。

---

## 25. 关键设计决策记录（ADR）

这一章记录「为什么是现在这样」，避免下一位在不知道背景的情况下推翻一个已经被验证的决定。每条包含背景、决定、代价、何时可以重新考虑。

### 25.1 ADR-01：后端先用 Python，而不是直接写 C++

背景：设计文档 §7.2 最终形态是 C++ 核心 + Python 镜像，但本次交付的启动器源码不在工作副本，UI 还无法编译；如果先写 C++ 核心，无法用真实启动器验证，只能写一堆没有消费者的代码。

决定：先用 Python 标准库实现完整的管理器（校验/指纹/计划/事务/回滚/运行证据），把它当作「可执行规范」；启动器后续用薄封装消费它。

代价：发行包依赖 Python；启动器多一层进程边界；性能不如同进程 C++。

何时重考：发布前必须解决 Python 依赖（打包或移植）。如果移植，Python 版保留为 oracle，用于对拍 `planId`。

### 25.2 ADR-02：启动路径只读 JSON，管理操作才跑 CLI

背景：点 Play 是最高频、最不能卡的操作；如果每次都起 Python 做 plan/apply，启动延迟不可控，而且 runner 已经启动后 Python 还在跑会增加退出时的竞态。

决定：`prepareSession` 先读 `state.json`/`plan.json` 做快速判断；只有状态缺失或指纹不匹配才跑 `apply`。管理操作（开关、导入、刷新）才跑 CLI。

代价：启动器要理解 `plan.json`/`state.json` 的 schema；两边 schema 变化要同步。

何时重考：如果 CLI 的快速判断逻辑变得复杂（例如需要重新计算内容哈希），可以把「读路径」也做成 CLI 的 `--check` 子命令，启动器只调一次。

### 25.3 ADR-03：VFS 钩子放在原生 host 根之后、设备根之前

背景：`resolveHostPath` 先处理 `host0:` 等原生路径，再处理 cdrom/mc/rom。如果把 Mod 表放在最前，玩家自己给的绝对路径会被 Mod 覆盖，难以解释；如果放在设备根之后，设备路径已经被解析成真实文件，Mod 无法覆盖。

决定：插在两者之间。原生 host 路径优先；设备路径可被 Mod 覆盖；未设置表时只多一次失败探测。

代价：Mod 不能覆盖 `host:` 路径；如果未来需要，必须加显式规则（例如只允许表里以 `host:` 开头的键）。

何时重考：出现「Mod 需要覆盖 host 路径」的真实需求时。

### 25.4 ADR-04：纹理尺寸硬校验，不做自动缩放

背景：实测 64×64 替换 512×512 会让 runner 在过场退出；patch 52 的绑定按 GS 尺寸，自动缩放需要改运行时并重新验证。

决定：`validate` 阶段按 PCSX2 名解析 TW/TH，尺寸不符直接 error。管理器不尝试「聪明地」缩放或裁剪。

代价：Mod 作者必须按原尺寸导出；旧的低分辨率包不能直接用。

何时重考：如果运行时改成「按图片尺寸缩放绑定」并有完整验证（多场景、多纹理、无花屏），可以放宽；在管理器里放宽是最后一步，不是第一步。

### 25.5 ADR-05：`planId` 包含每个资源的内容哈希

背景：早期 `planId` 只哈希计划结构，修改一张 PNG 的内容不会改变 `planId`，导致「计划没变但资源变了」的假象，staging 复用也可能留下旧图。

决定：`vfs`/`textures` 的每个条目都带 `sha256`，`planId` 哈希整份 payload。内容变 → `planId` 变 → staging 重建。

代价：大包 apply 时要多算哈希（一次，可接受）；`planId` 不再是「配置哈希」而是「内容哈希」，比较时要知道。

何时重考：如果包非常大（>GB），可以增量哈希/缓存；但不要退回「只哈希结构」。

### 25.6 ADR-06：`fingerprintId` 不包含 `runnerSha256`

背景：每次重编译 runner 二进制都会变；如果指纹包含它，玩家/开发者每次构建后都要重新 apply，计划频繁失效。

决定：`fingerprintId` 只含 gameId/edition/region/elfCrc/textSha1/runtimeCommit/patchChainHash；`runnerSha256` 单独记录，供发布/校验使用。

代价：如果 runner 二进制被替换但补丁/源码没变，计划不会失效；这在理论上可能掩盖 ABI 变化。实际上 runner 由本工程构建，替换二进制是受控行为。

何时重考：如果发布流程允许「只换 runner 不换补丁」，需要把 runnerSha 加入兼容检查（但不一定加入 fingerprintId）。

### 25.7 ADR-07：拒绝空计划

背景：玩家勾了 Mod 但全部被区域/依赖/校验排除时，如果静默 apply 一个空计划，玩家会以为 Mod 生效，实际原版运行。

决定：`apply` 在「profile 有启用但 plan.mods 为空」时拒绝，除非 `--allow-empty`（测试用）。

代价：某些「故意空」的 profile 需要显式参数；启动器要能显示「全部被排除」的原因。

何时重考：如果产品希望「空 profile 也允许 apply 以清理旧 hooks」，可以在 UI 用 `deactivate` 代替，而不是放宽 apply。

### 25.8 ADR-08：未启用时不设置空表/空路径

背景：空字符串与未设置在某些 `getenv` 分支上不等价；设置 `GOW_MOD_VFS_TABLE=""` 会让运行时尝试打开空路径并打印日志，干扰「无 Mod」验证。

决定：`plan.vfs` 为空时不设置 `GOW_MOD_VFS_TABLE`；`plan.textures` 为空时不设置 `GOW_TEXTURE_PACK`。启动器 `envFromPlan` 也遵守同样规则。

代价：日志里不会出现「空表已加载」的提示；需要靠 `overrides=0` 判断。

何时重考：如果运行时改成「空路径=禁用」的明确语义，可以统一设置；但当前不冒险。

### 25.9 ADR-09：`.PAK`、函数、脚本、存档明确不做

背景：这些都需要运行时钩子或格式逆向：PAK 由 IOP 按 LBA 读、函数覆盖要编进 runner、脚本由游戏自己解析、存档是二进制卡镜像。没有证据就做，会变成「看起来支持、实际不生效」的假功能。

决定：`validate` 直接报 `capability.*_unsupported`；文档与 UI 明确说明不支持。

代价：Mod 生态受限；作者会问「为什么不能像 PCSX2 那样改 PAK」。

何时重考：有运行时钩子 + 实机证据 + 格式文档三者齐备时，逐项开；不要先做 UI 壳。

### 25.10 ADR-10：补丁编号让位并行会话

背景：同一工作树有另一个会话连续新增 67/68/69/70；如果坚持用 67，会出现两个 67 文件、README 两行同号、`patchChainHash` 顺序歧义。

决定：本次补丁取当前最大号 + 1（最终 71），代码注释、README、CLI 文档同步。并行会话的补丁不动。

代价：文档里的「从 67 起」与最终编号不一致；需要在 2.5/21.2 说明。

何时重考：如果团队约定「每人一个号段」或「补丁目录用日期前缀」，可以改；当前以「不冲突」为最高优先。

### 25.11 ADR-11：Mods 作为第 7 个页签，而不是侧边栏

背景：设计文档 §20.3 假设启动器是 sidebar + NavItem 结构；实际代码是 `TabBar` + `StackLayout`，6 个页签。改成 sidebar 会重排现有页面、破坏截图脚本与既有测试。

决定：在 `TabBar`/`StackLayout` 末尾加第 7 个页签（index 6），现有 0..5 不动。

代价：页签数量变多，窗口窄时可能拥挤；需要在 `TabBar` 上做滚动/省略处理（现有样式已有）。

何时重考：如果产品决定重做导航，统一迁移所有页面与截图脚本，不要只改 Mods。

### 25.12 ADR-12：报告只写白名单字段

背景：设计文档 §20.5 与 `session-game-smoke.py` 要求导出不含 ISO/存档/截图/完整环境；路径会泄露玩家目录结构。

决定：报告只写 mod id/version/启用状态/能力/planId/fingerprintId/冲突计数/纹理 hits 等聚合值；路径只进本地日志。

代价：排障时报告本身不够，需要日志；这是有意的隐私/版权边界。

何时重考：除非有明确的用户授权与脱敏流程，否则不放宽。

### 25.13 ADR-13：不做热重载

背景：环境变量在进程启动时固定；VFS 表首次 lookup 读取；纹理包启动时枚举。运行中改 Mod 需要重启 runner。

决定：UI 明确「下次启动生效」；`apply` 在游戏运行时不允许（至少不推荐）。

代价：玩家改一个开关要重启游戏；对频繁调试的作者不友好。

何时重考：如果运行时增加「重新读取表/重新枚举纹理」的钩子，并且验证不影响帧循环，才可以考虑；那是运行时工作，不是管理器工作。

### 25.14 ADR-14：示例 Mod 用真实纹理名 + 真 IRX

背景：验证必须证明「资源真的被替换」，而不是「日志说替换了」。用真实会话里的 PCSX2 名和真实 IOP 文件，才能让两条 L3 路径都被游戏走到。

决定：夹具包含 7 张同尺寸品红纹理 + 一份 `LIBSD.IRX` 副本；只在本地验证，不进发行包。

代价：夹具含游戏数据，不能公开；每次换区域/会话，纹理名可能变，需要重新生成。

何时重考：如果要做公开示例，必须用自制/授权资源，并重新验证命中。

### 25.15 ADR 使用方式

- 改代码前先看相关 ADR；如果你的方案与 ADR 冲突，先写一条新 ADR 说明为什么推翻，再改代码。
- 不要在 PR/交付里悄悄改变 ADR 的决定；这会让下一位无法理解历史。
- ADR 不是永久真理；每条都写了「何时重考」，满足条件就可以重开讨论。

---

## 26. 快速索引与交接速查卡

这一章是整份手册的索引。时间紧时只看这里，按「我要做什么」找到对应章节，再跳过去读细节。

### 26.1 按任务找章节

| 我要做的事 | 先读 | 再读 |
|---|---|---|
| 第一次接手，不知道从哪开始 | 0.3、22.2 | 6.1、24.1 |
| 给启动器加 Mods 页 | 5.1、5.4、5.6 | 6.2～6.6、13 |
| 改 `Lanzador::iniciar` 注入环境变量 | 5.5、6.3 | 19.6 |
| 写 `ModsModel` 的 C++ | 19.1～19.9 | 5.3、7 |
| 做冲突/指纹 UI | 6.7、13.5 | 7.2、23.2 |
| 做导入/回滚/报告 | 6.8、13.6、5.8 | 15.4、15.10、23.3 |
| 造一个 Mod 包 | 14.1～14.8 | 3.2、4.4 |
| 纹理替换不生效/崩溃 | 4.4、17.3、17.5 | 23.4 |
| VFS 不命中 | 4.2、17.2 | 7.3、23.4 |
| 实机三态验证 | 8.3、20 | 24.3、24.4 |
| 补丁链/编号问题 | 21.2、25.10 | 2.5、4.6 |
| 并行会话干扰 | 9.1 R3、21.6 | 17.4 |
| 发布前检查 Python 依赖 | 5.7、10.3、22.1 | 25.1 |
| 移植 C++ 核心 | 5.7、6.9、10.4 | 25.1、设计文档附录 C |
| 找某个具体文件 | 12.2 | 4.1、4.2 |
| 找某条 CLI 命令 | 15 | 2.4、7.5 |
| 找某个错误码 | 16 | 15 |
| 设计文档哪里过时了 | 2.5、18.8 | 25.11、25.10 |

### 26.2 按文件找章节

| 文件 | 相关章节 |
|---|---|
| `tools/mods/gow_mods_cli.py` | 2.4、4.1、7、15、16 |
| `tools/mods/make_verify_mod.py` | 4.5、14.2、14.3 |
| `engine/patches/71-mod-vfs-hooks.patch` | 4.6、21.2、23.6 F-01 |
| `engine/runtime/.../mod_vfs_table.h/.cpp` | 4.2、25.3 |
| `engine/runtime/.../ps2_vfs.cpp` | 4.3、25.3 |
| `engine/README.md` | 4.6、21.2 |
| `data/mods/state.json` | 7.1、19.2 |
| `data/mods/hooks/plan.json` | 7.2、5.4、19.2 |
| `data/mods/hooks/vfs-overrides.tsv` | 7.3、4.2 |
| `data/mods/profiles/*.toml` | 3.4、6.6、15.5 |
| `C:\gow-jpn\launcher\src\lanzador.cpp` | 2.2、5.5、19.6 |
| `C:\gow-jpn\launcher\src\main.cpp` | 2.2、6.2 |
| `C:\gow-jpn\launcher\qml\Main.qml` | 2.2、5.6、6.4 |
| `C:\gow-jpn\launcher\qml\Textos.js` | 6.5、13.9 |
| `C:\gow-jpn\launcher\CMakeLists.txt` | 6.1、19.9 |

### 26.3 按现象找章节

| 现象 | 章节 |
|---|---|
| 启动器里看不到 Mods 页 | 6.1、19.9（QML 没进资源） |
| Mods 页空白/`failed` | 13.7、5.3（Python/仓库根） |
| 勾了 Mod 没效果 | 17.1、8.5 |
| 日志有 `[mod-vfs] 1 overrides` 但 `hits=0` | 17.2 |
| `cannot read` PNG | 17.3、4.4 |
| 运行几十秒无声退出 | 17.4、9.1 R5 |
| 替换大纹理后过场退出 | 17.5、4.4 |
| apply 报 Permission denied | 17.6、9.2 R8 |
| apply 后 status 显示 stale | 17.7、3.3 |
| enable 被拒绝 | 17.8、16 |
| 空计划被拒绝 | 17.9、25.7 |
| 启动器截图页签错 | 17.11、6.10 |
| 报告含路径 | 17.12、25.12 |
| 补丁重号/README 两行同号 | 9.1 R3、21.2、25.10 |

### 26.4 一页纸交付状态（给评审）

- **后端**：完成。Python CLI 覆盖发现/校验/排序/冲突/资源覆盖/事务/回滚/持久化/诊断；`selftest` 通过；示例包可 apply。
- **运行时**：完成。patch 71 提供只读 VFS 覆盖；纹理复用 patch 52；未启用时行为不变。
- **实机**：无 Mod 200 秒到玩法；启用示例 Mod 到玩法并命中纹理/VFS；禁用后恢复（早期同代码证据）；存在间歇性外部终止，已在 8.4/17.4 记录。
- **启动器**：未做。源码在 `C:\gow-jpn\launcher`，工作副本缺；本手册第 5/6/13/19/24 章给到文件级方案与脚本。
- **明确不做**：`.PAK`、函数、脚本、存档、L1 源码 Mod、通用多游戏；原因在 3.6、25.9。
- **发布前必办**：Python 打包或 C++ 核心；启动器 UI 接线；三态在安静机器复跑；示例游戏数据出包。

### 26.5 三条军规（贴在显示器上）

1. **未启用 = 原版**。任何注入都必须能证明「没设置时行为不变」；空表/空值也不要乱设。
2. **失败不启动**。Mod 管理器出错时宁可让玩家看到错误，也不要静默无 Mod 启动。
3. **先证据后参数**。纹理尺寸、VFS 路径、env 值都必须来自实测/逆向；不确定就写「待验证」，不要编。

### 26.6 交接联系点（占位）

- 运行时/补丁：本手册 4.6、21.2；改动前确认 `engine/README.md` 最大编号。
- 启动器：`C:\gow-jpn\launcher` 源码；工作副本只读 `bin`。
- 游戏数据：`C:\gow-jpn-data\gow1\discs\asia-97399`；不要分发。
- 构建：`C:\gow-jpn` + `C:\gow-build-jpn`；启动器另用 `build.cmd -Stages launcher`。
- 验证证据：`data/mods/runs/`；报告：`data/mods/reports/`。

---

## 27. 文档维护与版本约定

### 27.1 这份文档的定位

它不是设计文档的替代品，而是「交接视图」：只保留下一位做启动器 Mod 管理器需要的事实、代码位置、决策与验证方法。设计文档（`docs/mod-manager-design.zh-CN.md`）仍然是有法律效力的设计依据；本手册 2.5/18 记录了两者的偏差。发生冲突时：

1. 运行时行为以 `C:\gow-jpn` 的代码与实测为准。
2. 管理器行为以 `tools/mods/gow_mods_cli.py` 为准。
3. 设计意图以设计文档为准，但过时的路径/页签名不要照抄。

### 27.2 什么时候必须更新

- 新增/删除/改名 CLI 命令、字段、退出码 → 更新第 7、15、16 章。
- 新增补丁或改补丁号 → 更新 2.3、4.6、9.1 R3、12.2、22.2。
- 改启动器页面/设置/注入点 → 更新 2.2、5、6、13、19。
- 新增实测证据（三态、性能、崩溃） → 更新 8.4、20、22.3。
- 推翻某条 ADR → 新增一条 ADR，不要改旧条目的结论；在旧条目末尾加「已被 ADR-XX 取代」。
- 发现新的文档/代码冲突 → 补进 2.5，并在设计文档附录 H 留一条。

### 27.3 版本记录格式

在文末追加（不要覆盖历史）：

```
## 版本记录
- 2026-11-05 v1：初版；后端完成、启动器未做；补丁 71。
- YYYY-MM-DD v2：<一句话变更>；<影响的章节>。
```

本手册当前应视为 v1。后续修改请在文件末尾加记录，并在标题下的「文档版本」同步。

### 27.4 写作风格

- 先结论，后论证；每章开头一句话说明「这一章解决什么问题」。
- 命令、路径、字段名用反引号；不要用「大概」「可能」描述已经验证的事实。
- 实测结论必须带日期与证据位置；未验证的写成「待验证」。
- 不要复制设计文档的大段原文；用「§X.Y + 落地差异」的方式引用。
- 中文为主，代码/标识符保留英文；不要中英混排时加不必要的空格。

### 27.5 评审清单（文档改动）

- [ ] 新增章节编号连续，没有与旧章节冲突。
- [ ] 引用的文件路径在当前工作副本或 `C:\gow-jpn` 真实存在（或在文中明确说明是哪棵树）。
- [ ] 引用的命令能复制执行（PowerShell 语法正确）。
- [ ] 引用的数字（补丁号、目标数、日志值）与最新证据一致。
- [ ] 没有把示例 Mod 的游戏数据、绝对路径、玩家隐私写进「可导出」内容。
- [ ] 没有暗示未实现的功能已经可用（尤其是 `.PAK`/函数/脚本/启动器 UI）。

### 27.6 文档的「不做什么」

- 不写成产品宣传；不承诺未验证的性能/兼容性。
- 不把设计文档全文复制一遍；重复内容会过时。
- 不记录一次性的临时命令输出（放到 `data/mods/runs/` 或日志里）。
- 不把 `C:\gow-jpn` 的完整路径当成发行路径；发行时目录结构会变。

### 27.7 最后的提醒

如果你只记得一件事：**这次的核心不是「做一个 Mod 列表界面」，而是「让启用/禁用成为可解释、可回滚、可验证的状态」**。界面可以慢慢打磨，但状态机、事务、指纹、失败不启动这四件事一旦做错，玩家就会失去信任，后面的功能越多越难修。

补充说明：这份文档里所有「已完成」都以日志和实机为准，不以「代码写了」为准；所有「未完成」都不是「以后再说」，而是有明确的阶段、验收标准和前置条件。接手时请把这份文档当成一份工作清单，而不是一份宣传材料；如果发现哪条已经过时，按第 27.2 节更新，不要口头传播旧结论。

---

## 版本记录

- 2026-11-05 v1：初版。内容：后端（Python CLI + patch 71）已完成并在日版实机走通标题→3D 场景；启动器侧未实现，给出取回源码、ModsModel、QML 页签、环境注入、测试与验收的文件级方案。记录并发补丁编号冲突（最终 71）、纹理尺寸硬约束、间歇性外部终止与已知降级项。对应章节：0–27。文档共 27 章、约四万字，按「任务/文件/现象」三种索引使用。引用时请以本文件当前磁盘版本为准。

（完）



