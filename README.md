# ComfyUI Portal

一个面向非技术用户的 ComfyUI 门户（Flask）。支持登录、表单提交工作流、任务轮询、缩略图预览、打包下载，以及“工作流 → 服务器地址”的可视化映射。

## 功能
- 登录与权限（简单用户/管理员）
- 通过表单提交工作流任务（可上传素材文件）
- 简洁展示：排队数量、任务状态、进度条、缩略图、下载与 ZIP 打包
- “显示详情”开关：仅在需要排查时显示原始 JSON 日志
- 多服务器映射：每个工作流可绑定不同的 ComfyUI 地址（支持 ngrok/Cloudflare 隧道）

## 快速开始
1) 创建虚拟环境并安装依赖（Windows PowerShell）
- `python -m venv .venv`
- `.\.venv\Scripts\Activate.ps1`
- `pip install -r requirements.txt`

2) 准备环境变量
- 复制 `.env.example` 为 `.env`，按需修改：
  - `COMFY_URL`: 默认 ComfyUI 地址（当工作流未单独映射时使用）
  - `SECRET_KEY`: Flask 会话密钥

3) 运行
- `python -m app`
- 浏览器访问 `http://127.0.0.1:5000/`
- 账号信息见 `users.csv`（或使用 `users.csv.example` 模板）

## 使用说明
- 首页：
  - 选择工作流 → 填写表单 → 提交任务
  - 点击“开始轮询”：
    - 顶部显示 排队数量、状态（queued/submitting/running/finished）
    - 进度条实时变化
    - 生成完毕后显示缩略图，提供“下载/打包下载”链接
    - 需要排查时，点击“显示详情”查看原始 JSON
- 管理员 → 后台“服务器映射”：
  - 为每个工作流配置一个独立的 ComfyUI 地址
  - 保存后立即生效（写入 `workflows/servers.json`）

## 目录结构
- `app/`：后端代码（`auth.py`, `jobs2.py`, `pages.py`, `admin.py`）
- `templates/`：Jinja2 模板（主页、登录、历史、后台设置）
- `static/`：前端静态资源（`app.css`, `app_main.js`）
- `workflows/`：工作流 JSON 与可选表单 `*.form.json`、服务器映射 `servers.json`
- `uploads/`：用户上传的临时文件
- `results/`：结果存储目录（如需）

## 关键接口（后端）
- 任务
  - `POST /api/jobs` 提交任务（表单模式）
  - `GET  /api/jobs/<job_id>/status` 任务状态与产物
  - `GET  /api/jobs/<job_id>/download?filename=...` 单图下载（按任务的服务器转发）
  - `GET  /api/jobs/<job_id>/download.zip` 打包下载 ZIP（按任务的服务器转发）
  - `GET  /api/jobs/<job_id>/comfy/view?filename=...` 缩略图预览（按任务的服务器转发）
  - `GET  /api/jobs` 简要历史列表
  - `GET  /api/queue` 当前排队数量
- 工作流
  - `GET  /api/workflows` 列表
  - `GET  /api/workflows/<wf>/form` 获取表单定义
- 后台（管理员）
  - `GET  /api/admin/servers` 获取映射
  - `POST /api/admin/servers` 保存映射
  - `GET  /api/health?server=...` 远端 ComfyUI 健康检查

## 备注
- 远端 ComfyUI（隧道/动态域名）场景下，下载与预览均使用“任务记录的服务器地址”，避免拿不到文件。
- 返回 JSON 设置 `JSON_AS_ASCII=False`，确保中文不乱码。
- 如需定制表单，将 `xxx.form.json` 放在 `workflows/` 中，通过 `fields/mapping/server` 描述表单、参数映射与默认服务器。