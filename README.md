---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 23495379e47c99e3552e60753e6b5db6_47bf2498d86c11f1bc41525400638852
    ReservedCode1: PjA5NQOWB7CEB7PB4vY/ZGuY8FweEdMH6mSknDliQFD2Zag/JoNsKp9+IUmaf/IIfpTAyKQ0bu7tG37C3FalDMiHS+qsnntiMK3jt+mYGyD7rUXGFsFGqzOivaI2zsBI9dzg5LQ3qv0O/b/bWmJlHQkVKLSW9KsK4I9P2+rrlP27I6fMRhEqVTalq1c=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 23495379e47c99e3552e60753e6b5db6_47bf2498d86c11f1bc41525400638852
    ReservedCode2: PjA5NQOWB7CEB7PB4vY/ZGuY8FweEdMH6mSknDliQFD2Zag/JoNsKp9+IUmaf/IIfpTAyKQ0bu7tG37C3FalDMiHS+qsnntiMK3jt+mYGyD7rUXGFsFGqzOivaI2zsBI9dzg5LQ3qv0O/b/bWmJlHQkVKLSW9KsK4I9P2+rrlP27I6fMRhEqVTalq1c=
---

# mac-sweep

一个面向 macOS 的本地磁盘清理工具：只读扫描磁盘占用 → 按风险分级 → 将可清理项**移入废纸篓**（绝不永久删除）。内置**眼动仪友好**的本地网页 UI：大按钮、大字号、清晰路径展示。

> 本项目纯 Python 标准库实现，零第三方依赖，可在本地直接运行，也可直接上传 GitHub。

---

## ✨ 功能特性

- **磁盘占用扫描（只读）**：扫描用户目录下常见可清理位置（系统缓存、日志、崩溃报告、应用缓存、Xcode 构建产物、模拟器数据等），统计占用大小。
- **三级风险分级**：
  | 级别 | 含义 | 默认行为 |
  | --- | --- | --- |
  | 🟢 低风险 | 系统缓存、日志等 | 扫描后默认勾选，可一键清理 |
  | 🟠 需确认 | 应用缓存、构建产物等 | 扫描后默认不勾选，需手动确认 |
  | ⛔ 禁删 | 下载、文稿、桌面、系统保护路径 | 只读展示，**不可清理** |
- **移入废纸篓**：所有清理操作均将文件/目录移动到 `~/.Trash`（废纸篓），可随时恢复，**绝不执行永久删除**。
- **本地网页 UI（眼动仪友好）**：超大按钮、超大字号、高对比配色、等宽字体清晰展示完整路径；仅绑定 `127.0.0.1`，不对外网开放。

## 🔒 安全边界（硬约束）

1. **默认禁删用户文档**：「下载」「文稿」「桌面」「图片」「影片」「音乐」目录及其中任何文件，扫描与清理均不触碰。
2. **禁止触碰系统保护路径**：`/System`、`/Library`、`/usr`、`/Applications`、`/Volumes`、`/bin`、`/sbin`、`/private` 等。
3. **白名单校验**：可清理项必须位于允许清理的基目录（`~/Library/Caches`、`~/Library/Logs`、`~/Library/Developer`、`~/Library/Application Support` 下的缓存类子目录）之内，路径校验不过一律拒绝。
4. **只读扫描**：扫描过程不修改、不移动、不删除任何文件。
5. **删除可恢复**：清理仅"移动到废纸篓"，绝不永久删除；废纸篓清空由用户自行决定。

## 📁 项目结构

```
mac-sweep/
├── scanner.py          # 磁盘扫描 + 三级风险分级（只读）
├── cleaner.py          # 安全校验 + 移入废纸篓
├── webui.py            # 本地网页 UI（眼动仪友好）
├── requirements.txt    # 依赖清单（纯标准库，无第三方依赖）
├── README.md           # 本文件
├── LICENSE             # MIT 开源协议
└── .gitignore
```

## 🚀 快速开始

要求：macOS 10.15+，Python 3.8+（macOS 自带 `python3`）。

### 方式一：网页 UI（推荐）

```bash
cd mac-sweep
python3 webui.py
```

浏览器打开 <http://127.0.0.1:8765>：

1. 点击 **「扫描磁盘占用（只读）」** 大按钮开始扫描；
2. 查看分级结果：🟢 低风险默认勾选，🟠 需确认默认不勾选，⛔ 禁删只读展示；
3. 按需勾选后点击 **「将勾选项目移入废纸篓」**；
4. 清理完成后自动重新扫描，实时反映占用变化。

指定端口：

```bash
python3 webui.py --port 9000
```

### 方式二：命令行

```bash
# 1. 扫描（只读），输出 JSON
python3 scanner.py

# 2. 将结果保存到文件
python3 scanner.py --output scan_result.json

# 3. 清理指定路径（移入废纸篓）
python3 cleaner.py --paths '["/Users/<你的用户名>/Library/Caches/com.apple.Safari"]'

# 4. 从标准输入读取待清理路径
echo '{"paths": ["/Users/<你的用户名>/Library/Logs/DiagnosticReports"]}' | python3 cleaner.py --stdin
```

### 安全自检

```bash
# 打印废纸篓路径，确认清理目标位置
python3 cleaner.py --trash
```

## 📸 截图

> 截图占位：运行 `python3 webui.py` 后，浏览器打开 <http://127.0.0.1:8765> 即可看到主界面。
>
> 建议在此处替换为真实截图：
> - `docs/screenshot-main.png`：主界面（扫描结果分级展示）
> - `docs/screenshot-clean.png`：清理完成提示

## 🧪 工作原理

| 阶段 | 模块 | 说明 |
| --- | --- | --- |
| 扫描 | `scanner.scan()` | 遍历白名单基目录，递归统计占用（跳过符号链接），按风险分级排序 |
| 校验 | `cleaner._check_allowed()` | 六重校验：主目录内 / 非系统路径 / 非用户文档 / 白名单内 / Application Support 仅缓存子目录 / 路径可解析 |
| 清理 | `cleaner.move_to_trash()` | 目标重名时自动加时间戳后缀，`shutil.move` 到 `~/.Trash` |
| 展示 | `webui.py` | `ThreadingHTTPServer` 本地服务，大按钮 + 大字号 UI，同源 JSON API |

## 🤝 参与贡献

欢迎提交 Issue 与 Pull Request。请遵守以下原则：

- 不得加入永久删除（`rm` / `os.remove`）逻辑；
- 修改安全边界（白名单、禁删目录）必须同步更新 README 安全边界章节；
- 新增扫描目录前确认其为"可安全清理"类型。

## 📄 开源协议

[MIT](LICENSE) © 2026 mac-sweep contributors

