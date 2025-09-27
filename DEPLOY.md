部署指南（服务器版）

本项目位于目录 comfyui-portal/。以下提供两种部署方式：Docker 与裸机（Gunicorn + Systemd）。

一、Docker（推荐）
- 前提：服务器已安装 Docker 与 docker-compose（或 Compose v2）。
- 步骤：
  1) 进入项目根目录（含 comfyui-portal/）
  2) 按需编辑 comfyui-portal/.env（可选），或在启动时传入环境变量：
     - COMFY_URL：默认的 ComfyUI 地址（可被工作流映射覆盖）
     - SECRET_KEY：会话密钥
  3) 构建并启动：
     - cd comfyui-portal
     - docker compose up -d --build
  4) 打开 http://服务器IP:5000/ 登录使用
- 数据卷映射（见 docker-compose.yml）：
  - workflows/ 映射到容器内项目目录，支持在宿主侧修改工作流
  - uploads/、results/ 分别映射为数据目录
  - users.csv 挂载为用户清单

二、FreeBSD + Passenger（Serv00 场景）
- 说明：Serv00 已内置 HTTPS 与反代，选择 Python + Passenger WSGI 运行时即可，无需自行配置 Nginx。
- 部署步骤：
  1) 将仓库上传到你的用户家目录（建议路径如 `~/apps/comfyui-portal/`）。确保 `comfyui-portal` 目录中包含 `passenger_wsgi.py`。
  2) 进入 `comfyui-portal/` 创建虚拟环境并安装依赖：
     - `python3 -m venv .venv`
     - `source .venv/bin/activate`
     - `pip install --upgrade pip`
     - `pip install -r requirements.txt`
  3) 准备环境变量：复制 `.env.example` 为 `.env` 并修改：
     - `COMFY_URL=https://你的-comfyui-地址`（可用 Cloudflare/内网穿透地址）
     - `SECRET_KEY=随机字符串`
  4) 在 Serv00 面板中将该目录配置为该域名的 Passenger Python 应用根（如 mialuis.serv00.net 指向此目录）。
     - Passenger 会查找当前目录的 `passenger_wsgi.py`，其中已将 `from app import app as application` 暴露给服务器。
  5) 如需重启应用，创建/触碰 `tmp/restart.txt`：`mkdir -p tmp && touch tmp/restart.txt`。
- 静态与模板：项目已在 `app/__init__.py` 中使用项目根目录的 `static/` 与 `templates/`，无需额外配置。

三、裸机部署（Ubuntu/Debian 等）
- 依赖：Python 3.10+。
- 一次性启动（开发/测试）
  - cd comfyui-portal/scripts
  - bash run_prod.sh
  - 浏览器访问 http://服务器IP:5000/
- 生产常驻（示例 Systemd）：
  - 创建 /etc/systemd/system/comfyui-portal.service 内容大致：
    [Unit]
    Description=ComfyUI Portal
    After=network.target

    [Service]
    Type=simple
    WorkingDirectory=/path/to/repo/comfyui-portal
    Environment=COMFY_URL=http://127.0.0.1:8188
    Environment=FLASK_ENV=production
    ExecStart=/path/to/repo/comfyui-portal/.venv/bin/gunicorn -b 0.0.0.0:5000 app:app --chdir . --workers 2 --timeout 120
    Restart=always

    [Install]
    WantedBy=multi-user.target
  - systemctl daemon-reload && systemctl enable --now comfyui-portal

四、反向代理（可选）
- 可使用 Nginx/Caddy 将 80/443 映射到本服务 5000，并配置 HTTPS。

五、工作流服务器映射
- 后台 → 服务器映射：为每个工作流配置独立 ComfyUI 地址（支持隧道/动态域名）。保存后立即生效，写入 workflows/servers.json。

六、常见问题
- 预览/下载失败：检查工作流映射是否为实际可达地址；确认远端开启 /view 和 /prompt API。
- 中文显示异常：确保文件保存为 UTF-8；本服务已设置 JSON_AS_ASCII=False。
- 上传/结果目录权限：确认 uploads/ 与 results/ 可写。
