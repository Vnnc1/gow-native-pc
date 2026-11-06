# 交给开发者的一份东西

这个文件夹就是为了"发给开发者"准备的，别的都不用动。

## 里面是什么

| 文件 | 给谁 | 说明 |
| --- | --- | --- |
| `SCAJ-97399-support.patch` | 开发者 | **唯一需要发出去的文件**。30 KB，改 7 个文件（+243/−13），不含任何游戏数据 |
| `PR-DESCRIPTION.md` | 开发者 | 英文正文，整段粘到 GitHub Issue 里 |
| `README.md` | 你自己 | 这份说明 |

## 怎么发

1. 打开 <https://github.com/Vnnc1/gow-native-pc/issues/new>
2. 标题（建议）：
   `Support the Asia SCAJ-97399 disc: it carries the Japanese executable byte for byte`
3. 正文：把 `PR-DESCRIPTION.md` 的内容整段粘进去（它第一行是补丁的提交标题，小写开头是仓库的提交习惯，粘进正文没问题）
4. 附件：把 `SCAJ-97399-support.patch` 拖进附件框（GitHub 允许 .patch；若被拦，就把文件内容贴进 ```diff 代码块）

补丁自带头部说明，维护者 `git apply` 之后 `git log` 看到的是同样内容，不需要你再补充解释。

## 不要发

- `zs.iso`（游戏镜像）
- `C:\gow-jpn-data\`（8.1 GB，解出来的盘和存档）
- `C:\gow-jpn\`、`C:\gow-build-jpn\`（运行时快照与构建产物）
- `data/gow1/regional-builds.json`（本机注册表，含本机绝对路径；仓库明确说不发布）
- `run*.log`、`gs_hw_disp_*.ppm`（含游戏数据）
- 标题画面截图：可选，仓库惯例是"不把游戏媒体入库"，不发最稳妥

## 补丁做了什么（一句话版）

这张盘的启动 ELF 是 `SCAJ_973.99`，但它的 `.text` 与日版 `SLPM_670.10` **逐字节相同**（CRC `CA052D22`，
SHA-1 `8ed48ca8…`，1,690,724 字节），所以它跑的是日版代码、不需要第二份构建。补丁给 profile 加一个字段
`code = "japan"`，让"盘的身份"和"用哪个构建"解耦，并且让 `identify.py` 在本机已注册该构建时输出
`playable`，启动器才会把它当成可选项而不是"不支持的区域"。

## 验证到哪一步（补丁里也写着）

- 本机完整编了一个日版运行时（隔离快照 + `regions/japan/runtime.patch` + 区域代码生成 6416 函数，0 错误），
  注册后这张盘**进到了自己的标题画面**，日志无 `no exact recompiled function`、无 GL 错误
- `identify.py` 有注册表时输出 `playable: true / reason_code: regional_installed`，没有时退回 `region_alias`
- 帧率（i3-4170 + HD 4400，VU1 JIT，无 AOT/PGO）：1× 内部分辨率 8.4 fps，0.5× 24.5 fps
- `import_test.py` 16 项通过、`prepare_test.py` 4 项通过
- **没验证**：启动器界面没点过、标题画面之后没玩、没做 AOT/PGO、仅 Windows

## 自己再玩的话

- 启动器：重启后 Add ISO 重新选一次，应该显示 ✔ 和可选的版本
- 命令行：仓库根目录的 `play-asia.cmd`（0.5× 内部分辨率，最快）
