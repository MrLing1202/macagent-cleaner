#!/usr/bin/env python3
"""mac-sweep - 清理器（移入废纸篓，绝不永久删除）

接收待清理路径列表，逐项安全校验后移入废纸篓 (~/.Trash)。

安全校验（硬约束）：
  1. 目标必须位于用户主目录内；
  2. 禁止触碰系统保护路径（/System /Library /usr /Applications 等）；
  3. 禁止触碰用户文档目录（下载 / 文稿 / 桌面 / 图片 / 影片 / 音乐）；
  4. 目标必须位于允许清理的基目录（白名单）之下；
  5. 只执行"移动到废纸篓"，绝不执行永久删除（rm / os.remove 等）。

用法：
  python3 cleaner.py --paths '["/Users/me/Library/Caches/com.apple.Safari", ...]'
  python3 cleaner.py --stdin            # 从标准输入读取 {"paths": [...]}
  python3 cleaner.py --trash            # 打印废纸篓路径后退出（自检用）
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

TRASH_DIR = Path.home() / ".Trash"

# 允许清理的基目录白名单（与 scanner.SCAN_ROOTS 对齐）
ALLOWED_BASE_DIRS = [
    Path.home() / "Library" / "Caches",
    Path.home() / "Library" / "Logs",
    Path.home() / "Library" / "Developer",
    Path.home() / "Library" / "Application Support",
]

# 系统保护路径（出现即拒绝）
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

# 用户文档目录名（出现即拒绝）
USER_DOCUMENT_NAMES = {
    "Downloads",   # 下载
    "Documents",   # 文稿
    "Desktop",     # 桌面
    "Pictures",    # 图片
    "Movies",      # 影片
    "Music",       # 音乐
}

# Application Support 下仅允许清理名称含 cache 的子目录
CACHE_NAME_HINT = "cache"


def _check_allowed(path: Path) -> tuple:
    """返回 (allowed: bool, reason: str)。"""
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return False, "路径无法解析"

    home = Path.home().resolve()

    # 1. 必须在主目录内
    if not resolved.is_relative_to(home):
        return False, "路径不在用户主目录内"

    # 2. 禁止系统保护路径
    for sys_path in SYSTEM_PROTECTED_PATHS:
        r = sys_path.resolve()
        if resolved == r or r in resolved.parents:
            return False, "命中系统保护路径"

    # 3. 禁止用户文档目录
    for part in resolved.parts:
        if part in USER_DOCUMENT_NAMES:
            return False, f"命中用户文档目录 {part}（默认禁删）"

    # 4. 必须在白名单基目录之下
    for base in ALLOWED_BASE_DIRS:
        base_r = base.resolve()
        if resolved.is_relative_to(base_r):
            # Application Support 特判：只允许名称含 cache 的子目录
            if base_r.name == "Application Support":
                try:
                    rel = resolved.relative_to(base_r)
                except ValueError:
                    return False, "Application Support 根目录不允许整体清理"
                if not rel.parts:
                    return False, "Application Support 根目录不允许整体清理"
                if not _has_cache_hint(rel.parts):
                    return False, "Application Support 下仅允许清理缓存类子目录"
            return True, ""

    return False, "不在允许清理的基目录内"


def _has_cache_hint(rel_parts: tuple) -> bool:
    for part in rel_parts:
        if CACHE_NAME_HINT in part.lower():
            return True
    return False


def move_to_trash(path_str: str) -> dict:
    """将单个路径移入废纸篓。返回结果字典。"""
    src = Path(path_str)

    if not src.exists():
        return {"path": path_str, "status": "skipped", "reason": "路径不存在"}

    allowed, reason = _check_allowed(src)
    if not allowed:
        return {"path": path_str, "status": "refused", "reason": reason}

    # 目标重名保护
    target = TRASH_DIR / src.name
    if target.exists():
        target = TRASH_DIR / f"{src.name}-{int(time.time() * 1000)}"

    try:
        shutil.move(str(src), str(target))
        return {
            "path": path_str,
            "status": "moved",
            "trashed_to": str(target),
        }
    except (OSError, shutil.Error) as exc:
        return {"path": path_str, "status": "failed", "reason": str(exc)}


def clean(paths) -> dict:
    """批量清理。paths 为路径字符串列表。"""
    results = [move_to_trash(p) for p in paths]
    return {
        "results": results,
        "summary": {
            "moved": sum(1 for r in results if r["status"] == "moved"),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "refused": sum(1 for r in results if r["status"] == "refused"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="mac-sweep 清理器（移入废纸篓）")
    parser.add_argument("--paths", help="JSON 数组字符串，如 '[\"/path\"]'")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取 {\"paths\": [...]}")
    parser.add_argument("--trash", action="store_true", help="打印废纸篓路径并退出（自检）")
    args = parser.parse_args()

    if args.trash:
        print(TRASH_DIR)
        return

    if args.stdin:
        try:
            data = json.load(sys.stdin)
            paths = data.get("paths", [])
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"JSON 解析失败: {exc}"}, ensure_ascii=False))
            sys.exit(1)
    elif args.paths:
        try:
            paths = json.loads(args.paths)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"--paths 解析失败: {exc}"}, ensure_ascii=False))
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    result = clean(paths)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
