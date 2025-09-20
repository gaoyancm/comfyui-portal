# 待办清单（comfyui-portal）

近期目标
- 工作流表单机制：每个工作流一个 `form.json`，前端按定义自动渲染；后端将表单值映射/注入到 ComfyUI 工作流 JSON。
- 队列与进度优化：页面进度条、状态轮询节流、错误提示；`/api/queue` 显示排队数量。
- 结果下载：支持“下载全部为 ZIP”、单文件下载；考虑把输出索引存到 `results/`（或仅代理 ComfyUI）。
- 登录与页面：添加登录页与未登录拦截；保留 Excel `users.xlsx` 用户表（放在仓库根目录）。
- 部署脚本：服务器 venv + gunicorn/systemd；可选 Docker Compose。

表单机制详细事项
- 设计 `workflows/<name>/form.json` Schema（字段类型：text/number/select/file/textarea 等，含校验与默认值）。
- API：`GET /api/workflows` 列表；`GET /api/workflows/<name>/form` 返回定义；`POST /api/jobs` 接收表单并生成 overrides。
- 映射规则：表单字段 → Comfy 节点参数（支持路径表达式）；文件字段写入 `_uploads` 并按规则注入。

结果与下载
- `GET /api/jobs/<id>/artifacts` 列出输出；`GET /download/<job_id>.zip` 打包下载（可选）。
- 图片/视频代理：沿用 `/api/comfy/view`；视频 MIME 类型与大文件流式传输。

稳健性与安全
- 上传大小/类型限制与清理策略；异常统一返回格式；日志与请求 ID。
- 可选切换 Redis 队列（预留 `QUEUE_BACKEND` 和 `REDIS_URL`）。

文档
- README 增补：表单 Schema、部署步骤、环境变量说明。

备注
- 当前已实现：登录/单点、内存队列、任务创建与进度轮询、图片代理、基础页面。
- 使用说明：本地 `./run_dev.ps1` 或 `bash run_dev.sh`；设置 `.env` 中的 `COMFY_URL` 指向你的 ComfyUI。
