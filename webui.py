#!/usr/bin/env python3
"""macagent-cleaner - 本地网页 UI（眼动仪友好）

启动本地 HTTP 服务（默认 127.0.0.1:8765），浏览器打开即可操作：
  - 大按钮、大字号、清晰路径展示（眼动仪友好）
  - 一键扫描（只读，不修改任何文件）
  - 按风险分级展示：低风险默认勾选、需确认默认不勾选、禁删只读展示
  - 一键"移入废纸篓"（绝不永久删除）

安全说明：
  - 服务只绑定本机回环地址 127.0.0.1，不对外网开放；
  - 清理仅执行"移入废纸篓"，所有删除均为可恢复操作。

用法：
  python3 webui.py                 # 默认 127.0.0.1:8765
  python3 webui.py --port 9000     # 指定端口
"""

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import scanner
import cleaner

HOST = "127.0.0.1"
PORT = 8765

# 最新一次扫描结果缓存（供 /api/scan 复用；页面每次刷新重新扫描）
_scan_cache = {}
_scan_lock = threading.Lock()


def _format_size(n: int) -> str:
    """人类可读大小。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>macagent-cleaner - 磁盘清理</title>
<style>
  :root {
    --bg: #f5f6f8; --card: #ffffff; --ink: #1a1d21;
    --green: #2e8b57; --green-bg: #e6f4ec;
    --orange: #c77d00; --orange-bg: #fff3e0;
    --gray: #8a8f98; --gray-bg: #eef0f2;
    --red: #c0392b;
    --border: #d9dce1;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--ink);
    font-size: 20px; line-height: 1.6;
    padding: 24px; max-width: 1100px; margin: 0 auto;
  }
  h1 { font-size: 34px; margin-bottom: 8px; }
  .sub { color: #5c626b; font-size: 18px; margin-bottom: 24px; }
  .btn {
    display: inline-block; border: none; cursor: pointer;
    font-size: 24px; font-weight: 600; padding: 18px 40px;
    border-radius: 14px; min-height: 60px; line-height: 1.2;
    transition: transform .08s ease, opacity .15s ease;
  }
  .btn:active { transform: scale(.97); }
  .btn:disabled { opacity: .5; cursor: not-allowed; }
  .btn-primary { background: #1a73e8; color: #fff; }
  .btn-danger  { background: var(--green); color: #fff; }
  .bar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin: 24px 0; }
  .status { font-size: 20px; color: #5c626b; }
  .section { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 20px 24px; margin-bottom: 24px; }
  .section h2 { font-size: 26px; margin-bottom: 4px; }
  .section .desc { font-size: 17px; color: #5c626b; margin-bottom: 14px; }
  .item {
    display: flex; align-items: center; gap: 14px;
    padding: 12px 10px; border-top: 1px solid var(--border);
    font-size: 19px;
  }
  .item input[type=checkbox] { width: 26px; height: 26px; flex-shrink: 0; }
  .item .path { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 17px; word-break: break-all; flex: 1; }
  .item .size { font-weight: 600; white-space: nowrap; margin-left: 12px; }
  .tag { display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: 15px; font-weight: 600; white-space: nowrap; }
  .tag-low { background: var(--green-bg); color: var(--green); }
  .tag-confirm { background: var(--orange-bg); color: var(--orange); }
  .tag-forbidden { background: var(--gray-bg); color: var(--gray); }
  .tag-vendor { background: #f0f1f3; color: #6b7280; }
  .tag-agent { background: #1a56b0; color: #ffffff; }
  .hint { font-size: 16px; color: #8a8f98; margin-top: 8px; }
  .empty { color: #8a8f98; padding: 12px 0; font-size: 18px; }
  .summary { font-size: 22px; font-weight: 600; margin: 12px 0; }
  #result { margin-top: 20px; font-size: 20px; }
  #result ul { margin-left: 24px; }
  .danger-note { background: #fdecea; border: 1px solid #f5c6c0; color: #7a1f14; border-radius: 12px; padding: 14px 18px; font-size: 17px; margin-bottom: 20px; }
</style>
</head>
<body>
  <h1>🧹 macagent-cleaner</h1>
  <div class="sub">macOS 磁盘清理 · 只读扫描 · 移入废纸篓（绝不永久删除）</div>

  <div class="danger-note">
    安全边界：默认<b>禁删</b>「下载」「文稿」「桌面」「图片」「影片」「音乐」及任何用户文档；<br>
    系统保护路径（/System、/Library、/usr、/Applications 等）不在扫描范围内。<br>
    所有清理操作均为<b>移入废纸篓</b>，可随时恢复。
  </div>

  <div class="bar">
    <button class="btn btn-primary" id="btnScan" onclick="runScan()">扫描磁盘占用（只读）</button>
    <label for="autoInterval" style="font-size:17px;color:#5c626b;margin-left:12px;">自动检查</label>
    <select id="autoInterval" onchange="toggleAutoCheck()" style="font-size:17px;padding:6px 10px;border-radius:8px;border:1px solid var(--border);">
      <option value="0">关闭</option>
      <option value="5">每 5 分钟</option>
      <option value="15" selected>每 15 分钟</option>
      <option value="30">每 30 分钟</option>
      <option value="60">每 60 分钟</option>
    </select>
    <label for="autoThreshold" style="font-size:17px;color:#5c626b;margin-left:12px;">提醒阈值</label>
    <select id="autoThreshold" onchange="toggleAutoCheck()" style="font-size:17px;padding:6px 10px;border-radius:8px;border:1px solid var(--border);">
      <option value="104857600">100 MB</option>
      <option value="524288000" selected>500 MB</option>
      <option value="1073741824">1 GB</option>
    </select>
    <span class="status" id="status">尚未扫描</span>
  </div>

  <div id="sections"></div>

  <div class="bar" id="actionBar" style="display:none">
    <button class="btn btn-danger" id="btnClean" onclick="runClean()">将勾选项目移入废纸篓</button>
    <span class="status" id="cleanStatus"></span>
  </div>

  <div id="result"></div>

<script>
let lastScan = null;
let autoTimer = null;

function toggleAutoCheck() {
  const mins = parseInt(document.getElementById("autoInterval").value, 10);
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  const status = document.getElementById("status");
  if (mins > 0) {
    autoTimer = setInterval(runScan, mins * 60 * 1000);
    status.textContent = `自动检查已开启：每 ${mins} 分钟，阈值 ${fmtSize(parseInt(document.getElementById("autoThreshold").value, 10))}`;
  } else {
    status.textContent = "自动检查已关闭";
  }
}

function fmtSize(n) {
  const units = ["B","KB","MB","GB","TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return i === 0 ? n + " B" : n.toFixed(1) + " " + units[i];
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function render(data) {
  lastScan = data;
  const s = data.summary || {};
  const items = data.items || [];
  const forbidden = (data.protected && data.protected.user_documents) || [];
  const container = document.getElementById("sections");
  container.innerHTML = "";

  // 低风险
  const low = items.filter(i => i.risk === "low_risk");
  // 需确认
  const confirm = items.filter(i => i.risk === "need_confirm");
  // 禁删（展示保护清单，只读）
  const forbPaths = (data.protected && data.protected.system_paths || []).slice(0, 6);

  container.insertAdjacentHTML("beforeend", `
    <div class="section">
      <h2>🟢 低风险（建议清理）</h2>
      <div class="desc">系统缓存、日志等，可安全清理。共 ${low.length} 项，${fmtSize(s.low_risk || 0)}。</div>
      ${low.length === 0 ? '<div class="empty">没有发现可清理项</div>' : low.map(itemHtml).join("")}
    </div>
  `);

  container.insertAdjacentHTML("beforeend", `
    <div class="section">
      <h2>🟠 需确认（默认不勾选）</h2>
      <div class="desc">应用缓存、构建产物等，清理后可能影响应用下次启动速度或需重新构建。共 ${confirm.length} 项，${fmtSize(s.need_confirm || 0)}。</div>
      ${confirm.length === 0 ? '<div class="empty">没有发现此类项目</div>' : confirm.map(itemHtml).join("")}
    </div>
  `);

  container.insertAdjacentHTML("beforeend", `
    <div class="section">
      <h2>⛔ 禁止触碰（只读展示，不可清理）</h2>
      <div class="desc">以下目录与文件默认禁删，扫描与清理均不会触碰。</div>
      ${forbPaths.map(p => `<div class="item"><span class="tag tag-forbidden">禁删</span><span class="path">${esc(p)}</span></div>`).join("")}
      <div class="hint">用户文档目录：${forbidden.map(esc).join("、")}；系统保护路径：/System、/Library、/usr、/Applications、/Volumes 等。</div>
    </div>
  `);

  const actionBar = document.getElementById("actionBar");
  if (low.length + confirm.length > 0) actionBar.style.display = "flex";
  document.getElementById("actionBar").style.display = "flex";
  const total = (s.low_risk||0) + (s.need_confirm||0);
  let st = `扫描完成：可清理 ${fmtSize(total)}`;
  const th = parseInt(document.getElementById("autoThreshold").value, 10);
  if (autoTimer && total >= th) st += "  ⚠️ 达到自动检查阈值";
  document.getElementById("status").textContent = st;
}

function itemHtml(it) {
  const tag = it.risk === "low_risk"
    ? '<span class="tag tag-low">低风险</span>'
    : '<span class="tag tag-confirm">需确认</span>';
  const vendor = it.vendor
    ? `<span class="tag tag-vendor">${esc(it.vendor)}${it.vendor_category ? " · " + esc(it.vendor_category) : ""}</span>`
    : "";
  const checked = it.risk === "low_risk" ? "checked" : "";
  return `<div class="item">
    <input type="checkbox" data-risk="${it.risk}" ${checked}>
    ${tag}
    ${vendor}
    <span class="path">${esc(it.path)}</span>
    <span class="size">${fmtSize(it.size)}</span>
  </div>`;
}

async function runScan() {
  const btn = document.getElementById("btnScan");
  btn.disabled = true;
  document.getElementById("status").textContent = "正在扫描…（只读，不会修改任何文件）";
  try {
    const resp = await fetch("/api/scan");
    const data = await resp.json();
    render(data);
  } catch (e) {
    document.getElementById("status").textContent = "扫描失败：" + e.message;
  }
  btn.disabled = false;
}

async function runClean() {
  const boxes = document.querySelectorAll(".item input[type=checkbox]:checked");
  const paths = Array.from(boxes).map(b => b.closest(".item").querySelector(".path").textContent);
  if (paths.length === 0) { alert("请先勾选要清理的项目"); return; }

  if (!confirm(`确定将 ${paths.length} 项移入废纸篓吗？\n\n该操作可恢复（进入废纸篓），不会永久删除。`)) return;

  const btn = document.getElementById("btnClean");
  btn.disabled = true;
  document.getElementById("cleanStatus").textContent = "正在移入废纸篓…";
  try {
    const resp = await fetch("/api/clean", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths })
    });
    const data = await resp.json();
    const sm = data.summary || {};
    let html = `<b>清理完成：移入废纸篓 ${sm.moved || 0} 项`;
    if ((sm.skipped||0) > 0) html += `，跳过 ${sm.skipped} 项`;
    if ((sm.refused||0) > 0) html += `，拒绝 ${sm.refused} 项`;
    if ((sm.failed||0) > 0) html += `，失败 ${sm.failed} 项`;
    html += `</b>`;
    const refused = (data.results||[]).filter(r => r.status === "refused" || r.status === "failed" || r.status === "skipped");
    if (refused.length) {
      html += "<ul>" + refused.map(r => `<li>${esc(r.path)} — ${esc(r.reason||r.status)}</li>`).join("") + "</ul>";
    }
    document.getElementById("result").innerHTML = html;
    document.getElementById("cleanStatus").textContent = "完成";
    runScan(); // 重新扫描以刷新占用
  } catch (e) {
    document.getElementById("cleanStatus").textContent = "清理失败：" + e.message;
  }
  btn.disabled = false;
}
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[webui] " + (fmt % args) + "\n")

    def _send(self, code, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/api/scan":
            result = scanner.scan()
            with _scan_lock:
                _scan_cache.update(result)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"Not Found", "text/plain; charset=utf-8")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/clean":
            self._send(404, b"Not Found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
            paths = data.get("paths", [])
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        result = cleaner.clean(paths)
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="macagent-cleaner 本地网页 UI")
    parser.add_argument("--port", type=int, default=PORT, help=f"监听端口（默认 {PORT}）")
    args = parser.parse_args()

    server = ThreadingHTTPServer((HOST, args.port), Handler)
    print(f"macagent-cleaner Web UI 已启动： http://{HOST}:{args.port}")
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
