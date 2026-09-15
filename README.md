# 空闲时间协调器（空闲交集 · 课程表视图）

多人在一张“课程表”上按小时标出自己空闲的时间，系统自动求**全员交集**，也支持**任意两人两两对比**。风格参考 `../UCAS-lessons/` 选课页的浅色简洁风格。

支持三种运行方式：

| 方式 | 数据 | 适用 |
|---|---|---|
| **单机模式**：直接双击打开 `index.html` | 仅存本浏览器 `localStorage` | 一个人管理、同一台电脑上轮流替多人填写 |
| **局域网共享**：运行 `server.py`，同网设备打开同一网址 | 服务器 `server_data.json`，自动汇总共享 | 同一 Wi‑Fi 下的多人 |
| **公网部署**：部署到 Render 等免费云平台 | 服务器数据文件 | 校园网/异地多人（见下方「部署到公网」） |

## 使用（多人协作）

```bash
cd free-time-scheduler
python3 server.py            # 默认端口 8765；也可 python3 server.py 8080
```

启动后会打印两类地址（同一局域网内手机/电脑都能访问）：

- 本机：`http://localhost:8765/?room=default`
- 局域网：`http://<本机IP>:8765/?room=default`

然后：

1. 浏览器打开上述地址（页面状态条会显示「多人协作 · 房间 …」）。
2. 点页面上的 **🔗 复制共享链接**，把**带链接**发给其他人——`room=` 后面的就是“房间”名，同一房间 = 同一份数据，不同房间互不干扰（可改房间名后点「切换房间」）。
3. 每人添加自己姓名 → 点成员设为“正在填写”→ 在课表网格点格子标空闲；页面每 4 秒自动同步，也可点「🔄 立即同步」。
4. 查看 **👥 全员交集** / **🔗 两人交集**。

注意：`server.py` 运行期间 `server_data.json` 保存所有房间数据（重启不丢），请勿提交/上传该文件。

## 部署到公网（Render，免费）

校园网/公司网常有终端隔离，局域网直连不可用；异地/不同网络也用不了局域网地址。最省事的免费方案是把 `server.py` 部署到 Render，得到固定 https 地址，任何网络都能打开。

1. 推送到 GitHub（本目录已内置 `render.yaml`/`Procfile`，可直接用 Render 的 Blueprint）：
   ```bash
   cd free-time-scheduler
   git init -b main
   git add .
   git commit -m "free-time-scheduler"
   git remote add origin https://github.com/<你的用户名>/free-time-scheduler.git
   git push -u origin main
   ```
2. 打开 <https://dashboard.render.com> → **New + → Blueprint**，选刚推送的仓库，自动读取 `render.yaml` 完成部署。
   - 或 **New + → Web Service**：Runtime 选 Python，Start Command 填 `python server.py --port $PORT`。
3. 部署完成得到形如 `https://free-time-scheduler.onrender.com` 的地址，把 `/?room=小组名` 拼在后面发给别人即可。
   - 免费版闲置约 15 分钟会休眠、首次打开稍慢，属正常；数据存实例磁盘，重建会清空（小规模临时用足够）。

> 嫌注册麻烦、只是临时演示？可用 Cloudflare 快速隧道把本机映射成公网地址：
> ```bash
> brew install cloudflared
> cloudflared tunnel --url http://localhost:8765
> ```
> 会打印一个 `https://xxx.trycloudflare.com` 公网链接（本机需保持运行、联网即可访问）。

## 部署到 PythonAnywhere（免信用卡）

Render 的免费 Web 服务要求先绑信用卡；**PythonAnywhere 免费版无需信用卡**，适合本项目（单进程、文件存储、不休眠、长期有效）。它要求 WSGI 格式，仓库里已备好 `wsgi_app.py`。

1. 注册 https://www.pythonanywhere.com （免费）。
2. 进入 **Bash** 控制台，克隆你自己的仓库（先 fork，或直接用你自己的仓库地址）：
   ```bash
   git clone https://github.com/<你的用户名>/free-time-scheduler.git
   ```
3. 顶部 **Web** 标签 → **Add a new web app** → **Manual configuration** → 选 Python 版本（3.10+）。
4. 在 Web 页找到该应用的 **WSGI configuration file**（形如 `.../<你的用户名>_pythonanywhere_com_wsgi.py`），点进去把默认内容整体替换为：
   ```python
   import sys
   sys.path.insert(0, '/home/<你的用户名>/free-time-scheduler')
   from wsgi_app import application
   ```
5. 回 Web 页点 **Reload**。访问地址：`https://<你的用户名>.pythonanywhere.com/?room=小组名`（发给任何人、任何网络都能开）。

数据文件 `server_data.json` 会写在 `/home/<你的用户名>/free-time-scheduler/` 下，免费版文件系统长期保留。

## 部署你自己的副本（供他人 / 异地使用）

任何人都可以 clone 本仓库、部署**自己的一份**（数据各自独立）。两种形态：

**A. 后端直接托管页面（最省事）**：按上面 Render 或 PythonAnywhere 部署后，后端自带页面，同源无需配置。
分享链接：`https://<你的后端域名>/?room=小组名`

**B. 前端放静态托管（如 GitHub Pages）+ 后端另放**：适合“前端用 github.io 域名（微信/Edge 更友好）”。
- 后端需允许跨域（本仓库 `wsgi_app.py` / `server.py` 已内置 CORS，无需额外配置）
- 前端通过 URL 参数指定后端：`https://<前端地址>/?room=小组名&api=https://<你的后端域名>`
  - `api` 会被浏览器记住；也可在页面右侧“连接后端”里填一次
  - 页面上的「🔗 复制共享链接」会自动把 `api` 一并带上，发出去别人打开即连对你的后端

> 自己部署后，把链接里的 `room=` 换成你们小组名即可开始使用。

## 页面功能

- **✏️ 填写我的空闲**：添加/改名/删除填写者（自动配色）；点人设为“正在填写”，网格点格子 = 该小时空闲，再点取消。每格 1 小时，范围 周一~周日 × 08:00–23:00。
- **👥 全员交集**：自动只对“已填写（≥1 小时）”的人求交集（避免空白者把交集清零），绿色格 = 所有人同时有空；下方列出合并后的时段（如 周一 09:00–11:00）。
- **🔗 两人交集**：任选两人，格子三态显示：共同空闲（✓）/ 仅 A / 仅 B，下方列出重叠时段。
- 右上角：🎲 载入示例 / ⬇️ 导出 / ⬆️ 导入（JSON）/ 🗑 清空全部（多人模式下会清空整个房间）。

## 数据格式（导出/导入 / API）

```jsonc
{
  "people": [ { "id": "pxxxxx", "name": "张三", "color": "#4066d5" } ],
  "data":   { "pxxxxx": { "0_9": true } }   // 键 = "天_整点小时"，天 0=周一…6=周日，小时 8…23
}
```

服务端 API（同一房间内）：
- `GET  /api/state?room=NAME` → `{people, data, version, ts}`
- `GET  /api/hostinfo` → `{lan}`（页面据此把 localhost 换成手机可访问的地址）
- `POST /api/state?room=NAME` → 增量合并上报（`pids/people/data/del`），或 `{"reset":true}` 清空、`{"replace":true,...}` 整体替换
- 合并策略：**按 person 并集**——不同人同时给不同人填写不会互相覆盖；删除为显式操作。

## 文件

| 文件 | 说明 |
|---|---|
| `index.html` | 页面（单机 + 共享双模式；后端地址可由 `?api=` 配置） |
| `server.py` | 共享服务器（纯标准库；支持 `--port N` 或环境变量 `PORT`；内置 CORS） |
| `wsgi_app.py` | WSGI 入口，用于 PythonAnywhere 等 WSGI 平台 |
| `Procfile` / `render.yaml` | Render 云部署配置 |
| `LICENSE` | MIT 开源协议 |
| `server_data.json` | 运行期自动生成（已在 `.gitignore` 忽略，勿提交） |

## 后续可扩展方向

- 时间范围/粒度可配置（起止小时、按半小时等）——文件顶部 `HOURS` 常量集中定义
- 给每台设备锁定“只能改自己”的权限（目前为信任模型）
- 标注偏好（如更想上午/下午）、投票排序、导出结果图片/文本等
