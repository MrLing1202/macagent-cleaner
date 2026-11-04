# macagent-cleaner

为 agent 类工具设计的 macOS 缓存清理器：只读扫描磁盘占用，按风险分级，将可清理项移入废纸篓。

---

## 一次扫描，三类分级，一个动作

| 级别 | 对象 | 默认行为 |
| --- | --- | --- |
| 低风险 | 系统缓存、日志、崩溃报告 | 默认勾选，一键清理 |
| 需确认 | 应用缓存、Xcode 构建产物、模拟器数据 | 默认不勾选，手动确认 |
| 禁删 | 下载、文稿、桌面、系统保护路径 | 只读展示，不可操作 |

所有清理均以「移入废纸篓」完成，绝不永久删除。

## 安全边界

- 禁删用户文档：下载、文稿、桌面、图片、影片、音乐，及其中任何文件
- 禁删系统路径：/System、/Library、/usr、/Applications、/Volumes 等
- 只读扫描：扫描过程不修改、不移动、不删除任何文件
- 可恢复清理：仅移动至废纸篓，是否清空由用户决定
- 白名单校验：可清理项必须位于允许清理的基目录内，校验不过一律拒绝

## 架构

三个模块，各司其职。

| 模块 | 职责 |
| --- | --- |
| scanner.py | 磁盘占用扫描与风险分级（只读） |
| cleaner.py | 路径安全校验与移入废纸篓 |
| webui.py | 本地网页界面：眼动仪友好，大按钮、大字号、清晰路径 |

## 快速开始

要求：macOS 10.15+，Python 3.8+。

```bash
python3 webui.py
```

浏览器打开 <http://127.0.0.1:8765>，点击「扫描磁盘占用（只读）」，按需勾选后点击「将勾选项目移入废纸篓」。

命令行模式：

```bash
python3 scanner.py --output scan.json
python3 cleaner.py --paths '["/Users/me/Library/Caches/com.apple.Safari"]'
```

## 截图

运行 `python3 webui.py` 后，浏览器中即为主界面。建议在此放置两张截图：

- `docs/main.png` —— 扫描结果分级展示
- `docs/clean.png` —— 清理完成提示

## 贡献

欢迎提交 Issue 与 Pull Request。新增扫描目录前，请确认其属于「可安全清理」类型。

## 协议

MIT © 2026 macagent-cleaner contributors
