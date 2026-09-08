#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""空闲时间协调器 · 共享服务器（多人协作填写）

用法:  python3 server.py [端口]      # 默认 8765

多人协作原理:
  - 每位填写者用浏览器打开  http://<主机>:<端口>/?room=<房间名>
    （同一“房间” = 同一份数据，不同房间互不干扰）
  - 所有房间数据保存在同目录 server_data.json（首次运行自动创建），
    服务器重启数据不丢。
  - 页面按 person 增量上报，服务端做“并集合并”——不同人同时给不同人
    填表不会互相覆盖；删除 / 整体替换 / 清空为显式操作。

接口:
  GET  /                        静态托管（默认 index.html），?room= 由页面自行读取
  GET  /api/state?room=NAME     返回该房间 {ok, room, version, people, data, ts}
  POST /api/state?room=NAME     上报变更，body JSON：
      { "ver": 客户端已知版本,
        "pids": [personId...],
        "people": [{id,name,color}...],   // 仅含 pids 对应的最新记录
        "data":  {personId:{"d_h":true}},
        "del":   [personId...] }          // 显式删除
    或 { "reset": true }                  // 清空该房间
    或 { "replace": true, "people":[...], "data":{...} }  // 整体替换该房间（导入）
"""
import json
import mimetypes
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "server_data.json")
DEFAULT_PORT = 8765
MAX_ROOM = 24

_lock = threading.Lock()
_db = None          # {"rooms": {room: {"people":[], "data":{}, "version":0, "ts":0}}}


# ---------------- 数据存取 ----------------
def load_db():
    global _db
    if _db is not None:
        return _db
    _db = {"rooms": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("rooms"), dict):
            _db = raw
    except (OSError, ValueError):
        pass
    return _db


def save_db():
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_db, f, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)
    except OSError:
        pass


def clean_room(name):
    name = (name or "").strip()
    name = re.sub(r"[^\w\u4e00-\u9fff\-]", "", name)[:MAX_ROOM]
    return name or "default"


def clean_pid(pid):
    if not pid or not re.fullmatch(r"[A-Za-z0-9_\-]{1,48}", str(pid)):
        return None
    return str(pid)


def clean_data_obj(d):
    """保留形如 '0_9' -> true 的空闲格子，其余字段丢弃。"""
    out = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        if v and re.fullmatch(r"\d{1,2}_\d{1,2}", str(k)):
            out[str(k)] = True
    return out


def ensure_room(room):
    db = load_db()
    if room not in db["rooms"]:
        db["rooms"][room] = {"people": [], "data": {}, "version": 0, "ts": 0}
    return db["rooms"][room]


def merge(room, payload):
    """room: dict; payload: 前端上报。可能含 reset / replace / 增量三种语义。"""
    people = room["people"]
    data = room["data"]

    if payload.get("reset"):
        people.clear()
        data.clear()
    elif payload.get("replace"):
        people[:] = []
        new_pp = []
        for p in payload.get("people") or []:
            pid = clean_pid(p.get("id"))
            if pid is None:
                continue
            name = str(p.get("name", ""))[:20]
            color = str(p.get("color", ""))[:9]
            if not name:
                continue
            new_pp.append({"id": pid, "name": name,
                           "color": color if color.startswith("#") else "#4066d5"})
        people.extend(new_pp)
        data.clear()
        for pid in people:
            dd = clean_data_obj((payload.get("data") or {}).get(pid["id"]))
            if dd:
                data[pid["id"]] = dd
    else:
        # 1) 人员记录 upsert（新增或改名/换色）
        by_idx = {p["id"]: i for i, p in enumerate(people)}
        for rec in payload.get("people") or []:
            pid = clean_pid(rec.get("id"))
            if pid is None:
                continue
            if pid in by_idx:
                p = people[by_idx[pid]]
                nm = str(rec.get("name", "")).strip()
                if nm:
                    p["name"] = nm[:20]
                cl = str(rec.get("color", ""))
                if cl.startswith("#") and len(cl) <= 9:
                    p["color"] = cl
            else:
                people.append({
                    "id": pid,
                    "name": str(rec.get("name", ""))[:20],
                    "color": str(rec.get("color", "")) if str(rec.get("color", "")).startswith("#") else "#4066d5",
                })
        # 2) 各 pids 的空闲数据整段覆盖（以最近上报者为准）
        live_ids = {p["id"] for p in people}
        for pid in payload.get("pids") or []:
            pid = clean_pid(pid)
            if pid is None or pid not in live_ids:
                continue
            dd = clean_data_obj((payload.get("data") or {}).get(pid))
            data[pid] = dd if dd else {}
        # 3) 显式删除（放在最后，删除优先级最高）
        for pid in payload.get("del") or []:
            pid = clean_pid(pid)
            if pid is None:
                continue
            people[:] = [p for p in people if p["id"] != pid]
            data.pop(pid, None)

    room["version"] = int(room.get("version", 0)) + 1
    room["ts"] = int(time.time())
    return room["version"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 精简访问日志（可按需去掉注释恢复）
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body and not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def _room(self):
        qs = parse_qs(urlparse(self.path).query)
        return clean_room((qs.get("room") or [""])[0])

    def do_HEAD(self):  # 供云平台健康检查：只回响应头，不回 body
        self._head_only = True
        self.do_GET()

    # ---------- GET ----------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/hostinfo":
            self._send(200, {"ok": True, "lan": lan_ip()})
            return
        if path == "/api/state":
            with _lock:
                room_obj = ensure_room(self._room())
                body = {"ok": True, "room": self._room(),
                        "version": room_obj["version"],
                        "people": room_obj["people"],
                        "data": room_obj["data"],
                        "ts": room_obj["ts"]}
            self._send(200, body)
            return

        if path == "/":
            path = "/index.html"
        rel = os.path.normpath(path.lstrip("/"))
        fp = os.path.join(ROOT, rel)
        if not fp.startswith(ROOT) or not os.path.isfile(fp):
            self._send(404, {"ok": False, "error": "not_found"}, "application/json; charset=utf-8")
            return
        ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
            ctype += "; charset=utf-8"
        with open(fp, "rb") as f:
            data = f.read()
        self._send(200, data, ctype)

    # ---------- POST ----------
    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/state":
            self._send(404, {"ok": False, "error": "not_found"}, "application/json; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            self._send(400, {"ok": False, "error": "bad_json"}, "application/json; charset=utf-8")
            return
        if not isinstance(payload, dict):
            self._send(400, {"ok": False, "error": "bad_json"}, "application/json; charset=utf-8")
            return
        with _lock:
            room_obj = ensure_room(self._room())
            version = merge(room_obj, payload)
            save_db()
        self._send(200, {"ok": True, "room": self._room(), "version": version})


def lan_ip():
    """尽力探测一个可用于局域网访问的 IP。"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


def main():
    import sys
    # 端口优先级: 命令行 --port N / N > 环境变量 PORT（云平台惯例） > 默认 8765
    args = sys.argv[1:]
    port = 0
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2
        elif args[i].isdigit():
            port = int(args[i]); i += 1
        else:
            i += 1
    if not port:
        port = int(os.environ.get("PORT") or 0) or DEFAULT_PORT
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("空闲时间协调器 · 共享服务器")
    print(f"  本机访问:   http://localhost:{port}/?room=default")
    print(f"  局域网访问: http://{lan_ip()}:{port}/?room=default")
    print("  说明: 同一局域网手机电脑均可打开；把链接里的 room= 改成你们的小组名即可共用一份数据。")
    print("  数据文件: ", DATA_FILE)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
