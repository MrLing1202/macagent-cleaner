#!/usr/bin/env python3
"""macagent-cleaner - 磁盘占用扫描与缓存分级（只读）

扫描 macOS 用户目录下常见可清理位置，按风险分级输出 JSON：
  - low_risk       低风险，可安全清理（系统缓存、日志等）
  - need_confirm   需确认（应用缓存类子目录、Xcode 构建产物等）
  - forbidden      禁止触碰（下载、文稿、桌面、用户文档、系统保护路径）

安全承诺：
  - 本模块只做只读扫描，绝不修改、移动或删除任何文件；
  - 默认不扫描"下载 / 文稿 / 桌面 / 图片 / 影片 / 音乐"等用户文档目录；
  - 系统保护路径（/System /Library /usr /Applications 等）天然不在扫描范围内。

用法：
  python3 scanner.py                 # 打印 JSON 到标准输出
  python3 scanner.py --output out.json   # 写入指定文件
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 安全边界定义（硬约束）
# ---------------------------------------------------------------------------

# 系统保护路径（禁止触碰，出现即视为 forbidden）
SYSTEM_PROTECTED_PATHS = [
    Path("/System"),
    Path("/Library"),
    Path("/bin"),
    Path("/sbin"),
    Path("/usr"),
    Path("/private"),
    Path("/Applications"),
    Path("/Volumes"),
]

# 用户文档目录名（默认禁删）
USER_DOCUMENT_NAMES = {
    "Downloads",   # 下载
    "Documents",   # 文稿
    "Desktop",     # 桌面
    "Pictures",    # 图片
    "Movies",      # 影片
    "Music",       # 音乐
}

# 扫描根目录（相对用户主目录） -> (风险级别, 展示分类)
# 只扫描这些明确安全范围内的目录，绝不越界扫描整个主目录。
SCAN_ROOTS = {
    ("Library", "Caches"):            ("low_risk", "系统缓存"),
    ("Library", "Logs"):              ("low_risk", "系统日志"),
    ("Library", "Application Support", "CrashReporter"): ("low_risk", "崩溃报告"),
    ("Library", "Application Support"): ("need_confirm", "应用缓存"),
    ("Library", "Developer", "Xcode", "DerivedData"):    ("need_confirm", "Xcode 构建产物"),
    ("Library", "Developer", "CoreSimulator"):           ("need_confirm", "模拟器数据"),
}

# 应用支持目录下，仅收集名称含 cache 的子目录（避免误伤应用真实数据）
CACHE_NAME_HINT = "cache"

# ---------------------------------------------------------------------------
# 软件归属识别（agent 软件自动归类）
# ---------------------------------------------------------------------------

# 路径关键词 -> (软件名, 归类)。按顺序匹配，命中即归属。
# 关键词用小写，匹配路径的目录名片段。
VENDOR_RULES = [
    (("opencodedesktop",),         "OpenCode",        "终端 CLI"),
    (("trae",),                    "Trae",            "IDE 编辑器"),
    (("qoder",),                   "Qoder",           "IDE 编辑器"),
    (("cursor",),                  "Cursor",          "IDE 编辑器"),
    (("windsurf",),                "Windsurf",        "IDE 编辑器"),
    (("claude",),                  "Claude Code",     "终端 CLI"),
    (("opencode",),                "OpenCode",        "终端 CLI"),
    (("codex",),                   "Codex CLI",       "终端 CLI"),
    (("gemini",),                  "Gemini CLI",      "终端 CLI"),
    (("zcode",),                   "ZCode",           "桌面客户端"),
    (("raccoon",),                 "Raccoon",         "桌面客户端"),
    (("workbuddy",),               "WorkBuddy",       "桌面客户端"),
    (("marvis",),                  "Marvis",          "桌面客户端"),
    (("mmx-agent",),               "MMX Agent",       "桌面客户端"),
    (("agnescode",),               "AgnesCode",       "桌面客户端"),
    (("puppeteer",),               "Puppeteer",       "开发工具"),
    (("playwright",),              "Playwright",      "开发工具"),
    (("homebrew",),                "Homebrew",        "开发工具"),
    (("cacache",),                 "npm",             "开发工具"),
    (("node-gyp",),                "node-gyp",        "开发工具"),
    (("electron-builder",),        "electron-builder","开发工具"),
    (("_npx",),                    "npm",             "开发工具"),
    (("tabbit",),                  "Tabbit",          "浏览器"),
    (("bambu",),                   "Bambu Studio",    "应用"),
]

# 段级精确匹配（避免短词子串误判）
VENDOR_SEGMENT_RULES = [
    (("uv",),                      "uv",              "开发工具"),
    (("node",),                    "Node.js",         "开发工具"),
    (("edge",),                    "Microsoft Edge",  "浏览器"),
]

def _identify_vendor(path_str: str):
    """根据路径识别归属软件与归类；未命中返回 (None, None)。"""
    low = path_str.lower()
    for keywords, name, cat in VENDOR_RULES:
        if any(k in low for k in keywords):
            return name, cat
    low_parts = {p.lower() for p in Path(path_str).parts}
    for keywords, name, cat in VENDOR_SEGMENT_RULES:
        if any(k in low_parts for k in keywords):
            return name, cat
    return None, None


# ---------------------------------------------------------------------------
# 扫描实现（只读）
# ---------------------------------------------------------------------------

def _dir_size(path: Path) -> int:
    """递归统计目录占用字节数。只读；跳过符号链接避免循环。"""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += _dir_size(Path(entry.path))
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        return 0
    return total


def _entry_is_allowed(entry_path: Path) -> bool:
    """路径安全校验：禁止触碰系统保护路径与用户文档目录。"""
    resolved = entry_path.resolve()
    for sys_path in SYSTEM_PROTECTED_PATHS:
        if resolved == sys_path or sys_path in resolved.parents:
            return False
    for part in resolved.parts:
        if part in USER_DOCUMENT_NAMES:
            return False
    return True


def _is_cache_subdir(rel_parts: tuple) -> bool:
    """Application Support 下仅收名字含 cache 的子目录。"""
    for part in rel_parts:
        if CACHE_NAME_HINT in part.lower():
            return True
    return False


def scan() -> dict:
    """执行只读扫描，返回分级结果。"""
    home = Path.home()
    items = []

    for rel_tuple, (risk, category) in SCAN_ROOTS.items():
        base = home.joinpath(*rel_tuple)
        if not base.exists():
            continue

        if risk == "need_confirm" and rel_tuple[-1] == "Application Support":
            # 应用支持目录：逐个子目录过滤，只保留缓存类
            try:
                for child in sorted(base.iterdir()):
                    if not child.is_dir():
                        continue
                    rel = child.relative_to(home).parts
                    if not _is_cache_subdir(rel):
                        continue
                    size = _dir_size(child)
                    if size > 0:
                        vendor, vendor_category = _identify_vendor(str(child))
                        items.append({
                            "path": str(child),
                            "size": size,
                            "risk": risk,
                            "category": category,
                            "vendor": vendor,
                            "vendor_category": vendor_category,
                        })
            except (OSError, PermissionError):
                continue
        else:
            size = _dir_size(base)
            if size > 0:
                items.append({
                    "path": str(base),
                    "size": size,
                    "risk": risk,
                    "category": category,
                })

    # 按风险级别 + 大小排序（低风险在前，大的在前）
    risk_order = {"low_risk": 0, "need_confirm": 1, "forbidden": 2}
    items.sort(key=lambda x: (risk_order.get(x["risk"], 9), -x["size"]))

    summary = {
        "low_risk": sum(i["size"] for i in items if i["risk"] == "low_risk"),
        "need_confirm": sum(i["size"] for i in items if i["risk"] == "need_confirm"),
    }
    return {
        "items": items,
        "summary": summary,
        "protected": {
            "system_paths": [str(p) for p in SYSTEM_PROTECTED_PATHS],
            "user_documents": sorted(USER_DOCUMENT_NAMES),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="macagent-cleaner 只读扫描器")
    parser.add_argument("--output", "-o", help="将 JSON 结果写入指定文件")
    args = parser.parse_args()

    result = scan()
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"扫描完成，结果已写入 {args.output}")
    else:
        print(payload)


if __name__ == "__main__":
    sys.exit(main())
