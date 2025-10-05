# ComfyUI Portal

面向非技术成员的 ComfyUI 门户，基于 Flask 打造。它提供登录、可视化表单、任务排队轮询、缩略图预览、ZIP 打包下载以及“工作流 → 服务器地址”的映射管理，帮助团队把 ComfyUI 工作流程封装成易于使用的在线服务。

## 功能特性
- **账号体系**：支持 CSV/Excel 批量维护用户，密码使用 SHA-256 存储，含角色（admin/user）和会话过期控制。
- **工作流表单**：`workflows/*.form.json` 描述字段、默认值、文件上传参数及映射规则，可引用已有素材或允许上传新文件。
- **任务编排**：后台线程维护内置队列，按顺序向目标 ComfyUI 服务器提交 `/prompt` 请求并轮询状态。
- **多服务器支持**：每个工作流可绑定独立 ComfyUI 地址，兼容 ngrok、Cloudflare 隧道等外网映射。
- **结果预览与下载**：任务完成后展示缩略图、支持单图下载与 ZIP 打包，全部请求按任务记录的 `comfy_url` 代理。
- **管理后台**：管理员可配置“工作流 → 服务器”映射并做健康检查，配置保存在 `workflows/servers.json`。

## 目录结构
- `app/`：Flask 后端。`__init__.py` 创建应用并注册蓝图；`jobs2.py` 负责任务队列；`auth*.py` 处理认证；`admin.py` 管理接口；`pages.py` 页面路由。
- `static/`：前端静态资源（样式、脚本）。
- `templates/`：Jinja2 模板（主页、登录、历史、后台设置）。
- `workflows/`：ComfyUI 工作流 JSON 及表单定义；`servers.json` 保存服务器映射。
- `uploads/`：用户上传的临时文件目录（需可写）。
- `results/`：任务产物缓存目录（可选，可映射到持久化存储）。
- `assets/`：预置素材（`images/`、`audio/`）。
- `scripts/`：生产运行脚本。
- `tools/`：辅助脚本，如 `user_admin.py`。

## 环境要求
- Python 3.10 及以上。
- pip 可用，建议使用虚拟环境。
- 如果需解析 Excel 用户表，请安装 `openpyxl`（已包含在 `requirements.txt`）。
- Docker / docker-compose（可选，容器化部署需用）。

## 本地快速开始
1. **克隆项目**
   ```bash
   git clone https://github.com/gaoyancm/comfyui-portal.git
   cd comfyui-portal
   ```
2. **创建虚拟环境并安装依赖**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # Windows
   # 或 source .venv/bin/activate    # macOS / Linux
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. **配置环境变量**
   ```bash
   cp .env.example .env
   ```
   关键项：
   - `COMFY_URL`：默认 ComfyUI 服务器地址（未单独映射时使用）。
   - `SECRET_KEY`：Flask 会话密钥，建议使用随机字符串。
   - `UPLOAD_DIR` / `RESULTS_DIR`：可覆盖保存目录，默认 `uploads/`、`results/`。
4. **准备用户账号**
   - 复制 `users.csv.example` 为 `users.csv`，填写 `username/password_hash/expire_at/role`。
   - 或使用工具脚本：
     ```bash
     python tools/user_admin.py add-user admin --password "StrongPwd" --role admin --expire 2099-12-31
     ```
5. **添加工作流**
   - 将 ComfyUI 导出的 JSON 放到 `workflows/`。
   - 若需要自定义表单，创建同名的 `xxx.form.json` 描述字段与映射。
6. **启动开发服务器**
   ```bash
   python -m app
   ```
   访问 `http://127.0.0.1:5000/`，使用 `users.csv` 中的账号登录。也可使用 `run_dev.ps1` / `run_dev.sh` 快捷脚本。

## 工作流与表单
- `workflows/*.json`：原始工作流定义。
- `workflows/*.form.json`：将前端字段映射到工作流 JSON 的规则，可配置类型、默认值、文件上传目录、可选项等。
- 表单字段中的 `mapping` 指定写入路径，如 `3.inputs.seed` 或 `nodes.5.inputs.text`。
- 文件字段支持 `dirs`（可选择已有素材）、`allow_upload`、`extensions`、`accept` 等属性。
- 管理后台保存的服务器映射写入 `workflows/servers.json`，键可为文件名或不含后缀的名称。

## 用户与权限管理
- 会话默认 30 分钟无操作自动失效，可在 `auth*.py` 中调整。
- 管理员（role=admin）可访问 `/admin/settings` 进行服务器映射管理。
- `tools/user_admin.py` 支持添加用户、重置密码、调整过期时间、启用/停用账号。

## 管理后台使用
1. 登录后访问 `/admin/settings`。
2. 列表显示所有工作流，可录入服务器地址或执行“检查”获取健康状态。
3. 点击“保存”立即写入 `workflows/servers.json`，无需重启应用。
4. 不在工作流列表中的旧映射会标记为“未在工作流列表中”，方便清理。

## 运行与部署
### Docker Compose（推荐）
1. 保证主机安装 Docker 与 docker-compose（或 Docker Compose v2）。
2. 在项目目录执行：
   ```bash
   docker compose up -d --build
   ```
3. 可通过环境变量覆盖默认配置：
   ```bash
   COMFY_URL=http://host.docker.internal:8188 SECRET_KEY=your-secret docker compose up -d --build
   ```
4. 重要挂载：
   - `./workflows` → `/app/comfyui-portal/workflows`
   - `./uploads` → `/data/uploads`
   - `./results` → `/data/results`
   - `./users.csv` → `/app/comfyui-portal/users.csv`
5. 更新代码后重新执行 `docker compose up -d --build` 即可热更新。

### Serv00 / Passenger 部署
1. 将仓库上传至 Serv00（例如 `~/apps/comfyui-portal/`）。
2. 创建虚拟环境并安装依赖：
   ```bash
   cd ~/apps/comfyui-portal
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. 配置 `.env`、`users.csv`、`workflows/` 等文件，确保 `uploads/`、`results/` 可写。
4. 在 Serv00 面板选择 Passenger Python，根目录指向 `comfyui-portal/`，Passenger 会加载 `passenger_wsgi.py` 暴露的 `application`。
5. 更新代码后执行：
   ```bash
   mkdir -p tmp
   touch tmp/restart.txt
   ```
   如开启静态缓存，可清理 `tmp/cache` 再访问。

### 裸机 / Systemd 部署示例
1. 克隆仓库：
   ```bash
   git clone https://github.com/gaoyancm/comfyui-portal.git /opt/comfyui-portal
   cd /opt/comfyui-portal
   ```
2. 创建虚拟环境并安装依赖（同上）。
3. 试运行：
   ```bash
   ./scripts/run_prod.sh
   ```
4. 创建 Systemd 服务 `/etc/systemd/system/comfyui-portal.service`：
   ```ini
   [Unit]
   Description=ComfyUI Portal
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/opt/comfyui-portal
   Environment=COMFY_URL=http://127.0.0.1:8188
   Environment=FLASK_ENV=production
   ExecStart=/opt/comfyui-portal/.venv/bin/gunicorn -b 0.0.0.0:5000 app:app --chdir . --workers 2 --timeout 120
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
5. 启动并开机自启：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now comfyui-portal
   ```
6. 如需暴露公网，可使用 Nginx/Caddy 等反向代理到 5000 端口并配置 HTTPS。

## 常见问题
- **预览/下载失败**：检查后台映射的服务器地址及目标 ComfyUI `/view`、`/prompt` 接口是否可达；外网隧道需保持在线。
- **中文乱码**：确保 CSV/JSON 均为 UTF-8 编码，服务端已设置 `JSON_AS_ASCII=False`。
- **上传失败**：确认 `UPLOAD_DIR` 权限与磁盘空间，必要时限制大小并定期清理。
- **后台列表为空**：确保 `workflows/` 内存在 `*.json`，并确认服务进程具备读取权限。

## 常用命令
- 开发启动：`./run_dev.sh` 或 `./run_dev.ps1`
- 生产启动（调试）：`./scripts/run_prod.sh`
- 添加管理员：`python tools/user_admin.py add-user admin --password <pwd> --role admin`
- 重置密码：`python tools/user_admin.py set-password <user> --password <pwd>`
- 查看现有用户：`python tools/user_admin.py list`

## 维护建议
- 部署后至少验证一次：提交任务 → 轮询进度 → 预览缩略图 → 下载 ZIP。
- 修改工作流或表单后同步更新 `servers.json` 映射。
- 建议定期备份 `workflows/`、`users.csv`、`assets/` 和结果目录。

## 发布与回滚流程
1. **在打标签或部署前保持工作区干净**
   - 运行 `git status`，确保没有待提交的修改。
   - 若看到 `workflows/servers.json` 等环境私有配置有改动，可用 `git restore workflows/servers.json` 或 `git checkout -- workflows/servers.json` 恢复到仓库版本；如需长期保留本地改动，可在单独分支或私有仓库维护。
   - 对于 `.tar.gz` 备份包等临时文件，可执行 `git clean -f` 或手动删除；仓库已忽略 `project_backup_*.tar.gz`，避免误加入提交。
   - 如需暂存本地修改以便稍后恢复，可用 `git stash push --include-untracked`。
2. **创建版本标签**
   ```bash
   git tag -a vX.Y.Z -m "Stable portal release"
   git push origin vX.Y.Z
   ```
   版本号可按团队约定调整，建议同时在 Release Notes/CHANGELOG 中记录关键变更。
3. **部署指定标签**
   - 手工部署时执行 `git fetch --tags` 后 `git checkout vX.Y.Z`，再重启服务进程。
   - CI/CD 可将目标标签作为参数传入，保证线上环境始终指向明确版本。
4. **需要回滚时**
   - 直接切换到旧标签或基于标签创建 hotfix 分支：`git checkout vPrevious` 或 `git checkout -b hotfix/<issue> vPrevious`。
   - 修复后重新打标签并部署。
