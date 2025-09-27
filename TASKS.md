# 待办清单（comfyui-portal）

## 今日完成
- 修复下载与预览：所有下载/打包/预览均使用 job 记录的 `comfy_url`，支持 Cloudflare/隧道。
- 新增预览接口：`GET /api/jobs/<job_id>/comfy/view`（缩略图直接可见）。
- 简洁首页：仅显示排队数量、状态、进度条、缩略图、下载与 ZIP；“显示详情”折叠原始 JSON。
- 进度条：轮询时实时更新；新增队列数量刷新。
- 中文编码修复：页面与 JSON 均为 UTF‑8；`JSON_AS_ASCII=False`。
- 重构前端脚本：`static/app_main.js` 承载轮询与渲染逻辑。
- 文档与部署：更新 `README.md`；新增 `Dockerfile`、`docker-compose.yml`、`scripts/run_prod.*`、`DEPLOY.md`；
  FreeBSD/Serv00 环境新增 `passenger_wsgi.py`。

## 明日计划（按优先级）
1) 完成 Serv00 首次上线验证
   - venv 安装依赖 → 配置 `.env` → Passenger 指向目录 → `touch tmp/restart.txt` → 访问自测。
2) 错误信息友好化
   - 提交/轮询失败时返回 ComfyUI 响应摘要，前端提示可读的解决建议。
3) 后台“服务器映射”体验
   - 保存后显示改动清单；健康检查增加版本与颜色标识；失败可重试。
4) 历史与体验
   - 历史页状态筛选、缩略图列；首页“重新开始轮询”按钮与加载失败提示。

## 可选后续
- 任务持久化（SQLite）：保存概要与产物索引，重启不丢历史。
- GitHub Actions/rsync 自动部署（push 即更新服务器并重启 Passenger）。
- 上传限制与清理：限制大小与类型，定期清理 `uploads/`。

## 快捷命令
- Windows 开发启动：`./run_dev.ps1`
- 创建用户：`python tools/user_admin.py add-user alice --password "pwd" --expire 2099-12-31`
- 创建管理员：`python tools/user_admin.py add-user admin --password "pwd" --role admin --expire 2099-12-31`
