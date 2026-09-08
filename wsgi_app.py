#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PythonAnywhere（免信用卡免费平台）专用 WSGI 入口。

与 server.py 共用同一套“房间/合并”逻辑，仅把 HTTP 出入换成 WSGI 形态，
供 PythonAnywhere 的 Web 应用直接调用：

    application = wsgi_app.application

部署（详见 README「部署到 PythonAnywhere」）：
    1. 注册 https://www.pythonanywhere.com （免费、无需信用卡）
    2. Bash 控制台:  git clone https://github.com/ConradLee49/free-time-scheduler.git
    3. Web 标签页 → Add a new web app → Manual configuration → 选 Python 版本
    4. 点该应用的 “WSGI configuration file” 链接，把内容改为：
         import sys
         sys.path.insert(0, '/home/<你的用户名>/free-time-scheduler')
         from wsgi_app import application
    5. 点 Reload，即可访问 https://<你的用户名>.pythonanywhere.com/?room=小组名

说明：本文件与 server.py 位于同一目录；server.py 仅在被直接运行时才启动
自带 HTTP 服务器（有 if __name__ == '__main__' 保护），import 它安全。
"""
import json
import mimetypes
import os
from urllib.parse import urlparse, parse_qs

from server import clean_room, ensure_room, merge, save_db, _lock

BASE = os.path.dirname(os.path.abspath(__file__))


def _ok(environ, start_response, status, payload, ctype="application/json; charset=utf-8"):
    """发送 200 响应。status 形如 '200 OK'；payload 为 dict/list 或 bytes。"""
    head_only = environ.get("REQUEST_METHOD", "GET").upper() == "HEAD"
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    elif isinstance(payload, str):
        body = payload.encode("utf-8")
    else:
        body = payload
    start_response(status, [
        ("Content-Type", ctype),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
    ])
    return [] if head_only else [body]


def _room_of(environ):
    qs = parse_qs(environ.get("QUERY_STRING", ""))
    return clean_room((qs.get("room") or [""])[0])


def _read_body(environ):
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ["wsgi.input"].read(n) if n > 0 else b""
        obj = json.loads(raw.decode("utf-8") or "{}")
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        return None


def application(environ, start_response):
    path = urlparse(environ.get("PATH_INFO", "/")).path
    method = environ.get("REQUEST_METHOD", "GET").upper()

    if method == "OPTIONS":  # CORS 预检（github.io 前端跨域访问时浏览器会先发 OPTIONS）
        start_response("200 OK", [
            ("Content-Type", "text/plain"),
            ("Content-Length", "0"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ])
        return [b""]

    if path == "/api/state":
        if method == "GET":
            with _lock:
                room_obj = ensure_room(_room_of(environ))
                return _ok(environ, start_response, "200 OK", {
                    "ok": True, "room": _room_of(environ),
                    "version": room_obj["version"],
                    "people": room_obj["people"],
                    "data": room_obj["data"],
                    "ts": room_obj["ts"],
                })
        if method == "POST":
            payload = _read_body(environ)
            if payload is None:
                return _ok(environ, start_response, "400 Bad Request",
                           {"ok": False, "error": "bad_json"})
            with _lock:
                room_obj = ensure_room(_room_of(environ))
                version = merge(room_obj, payload)
                save_db()
            return _ok(environ, start_response, "200 OK",
                       {"ok": True, "room": _room_of(environ), "version": version})

    if path == "/api/hostinfo":
        return _ok(environ, start_response, "200 OK", {"ok": True, "lan": ""})

    # ------- 静态文件托管 -------
    if path == "/":
        path = "/index.html"
    rel = os.path.normpath(path.lstrip("/"))
    fp = os.path.join(BASE, rel)
    if not fp.startswith(BASE) or not os.path.isfile(fp):
        return _ok(environ, start_response, "404 Not Found",
                   {"ok": False, "error": "not_found"})
    ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
        ctype += "; charset=utf-8"
    with open(fp, "rb") as f:
        data = f.read()
    return _ok(environ, start_response, "200 OK", data, ctype)
