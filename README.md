# 鲜知 V1 后端基础

本仓库当前交付“鲜知”V1：原生微信小程序、连续扫描、真实 MySQL/Redis、FastAPI、Mock 微信登录、食品 CRUD、日期规则及 70 种保鲜知识。扫描分析默认使用可重复的 Mock，也可切换到百炼 `qwen3.5-ocr` 与 `qwen3.7-flash`；Real 微信接口和通知发送仍属于后续工作。

## 准备环境

- Windows PowerShell 7。
- Python 3.11 以上；项目默认使用 `D:\DevTools\Python312\python.exe`。
- Docker Desktop 安装在 `D:\DevTools\DockerDesktop`，Docker 数据已迁移到 `D:\DockerData\wsl`。
- 微信开发者工具用于后续原生小程序联调；当前 Plan 01 只提供可供其调用的 Mock 后端 API。

在仓库根目录初始化 D 盘虚拟环境和哈希锁定依赖：

```powershell
.\scripts\bootstrap.ps1
```

脚本会把虚拟环境、pip/npm 缓存和测试临时目录分别放在 `.runtime/venv`、`.cache/pip`、`.cache/npm` 和 `.task-runtime/tmp`。上传、日志与备份目录约定为 `.data/uploads`、`.data/logs` 和 `.data/backups`。MySQL/Redis 数据保存在 Docker 命名卷 `infra_mysql_data_linux`、`infra_redis_data`，随已迁移到 `D:\DockerData\wsl` 的 Docker/WSL 磁盘落在 D 盘。旧版 `.data/mysql`、`.data/redis` 不会再被 Compose 自动挂载；升级时应先停服务，把内容迁移到命名卷并验证迁移版本与数据计数。Windows bind 初始化的 MySQL 数据不能直接在 Linux 命名卷中启动，应进行逻辑导出/导入；确认无误后仍保留旧目录作为回退。Windows 和 Docker Desktop 仍可能在 C 盘留下少量不可避免的系统元数据。

## 启动与检查

```powershell
.\scripts\dev.ps1
```

首次运行只会在 `.env` 不存在时从 `.env.example` 复制，不会覆盖本地配置。脚本构建 API、等待 MySQL/Redis 健康、以 Alembic 升级现有开发库，然后启动 API；不会删除数据库或卷。

- 存活检查：<http://localhost:8000/api/v1/health/live>
- 就绪检查：<http://localhost:8000/api/v1/health/ready>
- OpenAPI 文档：<http://localhost:8000/docs>

常用 Compose 命令（在仓库根目录运行）：

```powershell
$Docker = 'D:\DevTools\DockerDesktop\resources\bin\docker.exe'
& $Docker compose --env-file .env -f infra\compose.yaml ps
& $Docker compose --env-file .env -f infra\compose.yaml logs -f api
& $Docker compose --env-file .env -f infra\compose.yaml restart api
& $Docker compose --env-file .env -f infra\compose.yaml stop
& $Docker compose --env-file .env -f infra\compose.yaml start
```

若确实要移除容器可使用 `down`，但不要添加 `-v`；`-v` 会删除数据库卷或数据，应先备份并明确确认。

## Mock 登录与 API 示例

Mock 模式接受任意非空、最长 123 字符的演示 code。以下 PowerShell 示例登录、保存 Token，并手动添加一份冷藏草莓：

```powershell
$Login = Invoke-RestMethod -Method Post `
  -Uri 'http://localhost:8000/api/v1/auth/wechat/login' `
  -ContentType 'application/json' `
  -Body '{"code":"demo-user"}'

$Headers = @{
  Authorization = "Bearer $($Login.access_token)"
  'Idempotency-Key' = 'readme-strawberry-001'
}

$Food = Invoke-RestMethod -Method Post `
  -Uri 'http://localhost:8000/api/v1/foods/manual' `
  -Headers $Headers `
  -ContentType 'application/json' `
  -Body '{"food_name":"草莓","category":"fruit","storage_type":"chilled","added_on":"2026-08-20"}'

Invoke-RestMethod -Method Get `
  -Uri 'http://localhost:8000/api/v1/foods?bucket=this_week' `
  -Headers @{ Authorization = "Bearer $($Login.access_token)" }
```

创建与删除食品需要 `Idempotency-Key`。日期示例应换成操作当天；如果包装日期、生产日期加保质期和知识库都不能给出结果，请显式提交 `recommended_consume_by`。

## 环境与安全

`.env.example` 只提供本机 Mock 开发默认值，真实 `.env` 已被 Git 忽略。不要提交访问 Token、openid、微信 Secret、百炼 API Key 或生产数据库口令。切换到任何非 Mock 模式前，必须生成真实 JWT 签名密钥并写入本地 `.env`：

```powershell
. .\scripts\env.ps1
& (Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe') -c "import secrets; print(secrets.token_urlsafe(32))"
```

把输出完整写入 `JWT_SECRET=`，不要沿用 `change-me-for-production`。Real 微信和通知发送适配器尚未实现。

真实百炼识别只需保持 `APP_MODE=mock`，并在本地 `.env` 配置以下项目；这样手机仍使用 Mock 微信登录，只有 OCR/视觉分析会产生真实模型调用：

```dotenv
ANALYSIS_PROVIDER=bailian
DASHSCOPE_API_KEY=在百炼控制台创建的密钥
BAILIAN_OCR_MODEL=qwen3.5-ocr
BAILIAN_VISION_MODEL=qwen3.7-flash
```

更新配置后执行 `docker compose --env-file .env -f infra\compose.yaml up -d --build --force-recreate worker`。商品包装字段先由 OCR 提取；商品名称或分类缺失时才调用视觉模型。

API 容器以固定的非 root 用户 `10001:10001` 运行，根文件系统只读，并丢弃 Linux capabilities、禁止获取新权限；只有上传目录和临时 `/tmp` 可写。MySQL、Redis 与 Python 基础镜像均锁定到保留可读标签的不可变镜像摘要。升级摘要应作为明确的依赖维护变更进行评审。

## 测试

统一测试脚本可从任意工作目录调用：

```powershell
& 'D:\path\to\fresh preservation\scripts\test.ps1'
```

完整检查：

```powershell
. .\scripts\env.ps1
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests -q
& .\.runtime\venv\Scripts\ruff.exe check backend
& .\.runtime\venv\Scripts\python.exe -m mypy backend\app
```

## 食品安全说明

知识库保鲜天数和建议食用日期只用于库存整理与提醒，不构成食品安全、医疗或质量保证。请优先遵循包装标注、监管部门指引和实际储存条件；出现异味、霉变、胀包或其他异常时应丢弃，不能仅依赖应用给出的日期。
