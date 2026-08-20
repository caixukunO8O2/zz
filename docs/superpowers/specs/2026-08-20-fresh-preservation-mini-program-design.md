# 「鲜知」微信小程序 V1.0 设计规格

- 日期：2026-08-20
- 状态：已完成方案讨论，等待书面规格复核
- 产品名称：「鲜知」
- 产品全称：AI 智能保鲜提醒助手
- 客户端：微信原生小程序（TypeScript、WXML、WXSS）
- 后端：Python 3.12、FastAPI、LangChain、LangGraph、SQLAlchemy
- 基础设施：MySQL、Redis、Docker Desktop / Docker Compose

## 1. 目标与成功标准

V1.0 建立“扫描食材 → 自动识别 → 用户确认 → 计算建议日期 → 创建提醒 → 到期处理”的完整闭环。默认运行真实 MySQL 与 Redis，OCR、视觉模型、微信登录和微信订阅消息通过可切换适配器支持 Mock 与 Real 两种模式。

V1 的交付目标是：没有外部密钥时仍可稳定演示全部业务流程；补充微信、PaddleOCR 和阿里云百炼配置后，无须改动页面或业务核心即可切换到真实能力。

成功标准：

1. 原生小程序可在微信开发者工具中打开、编译和预览。
2. Docker Compose 可启动 API、任务 Worker、MySQL 与 Redis。
3. 三条核心演示流程全部通过：包装食品一次扫描成功、名称缺失后定向补扫成功、无包装生鲜通过视觉识别和知识库得到建议日期。
4. 用户可修改识别结果，确认后只生成一条食品记录和对应提醒任务。
5. 首页正确区分当天或剩余 1 天、2–7 天、超过 7 天及已过期食品。
6. 拒绝微信订阅消息不会阻止食品保存。
7. 删除食品会软删除记录并取消所有未发送提醒。

原需求中的真实能力准确率目标保留为上线验收目标：食品识别不低于 90%，日期 OCR 不低于 95%，提醒任务调度准确率不低于 99%。这些比例不能由 Mock 数据证明；Real 模式验收需要启用真实服务，并使用独立标注数据集。建议食品识别集不少于 200 个代表性样本、日期字段集不少于 300 个包装日期样本、提醒调度使用不少于 1000 个合成任务进行时间边界测试。

## 2. V1 范围

### 2.1 包含

- 微信静默登录；Mock 模式使用固定演示用户，Real 模式使用 `wx.login` 与微信 `code2Session`。
- 可选用户资料：用户主动设置昵称和头像；登录本身不依赖资料授权。
- 一次连续扫描会话，自动收集食品名称、品牌、日期、保质期与储存条件。
- 相机不可用或识别失败时，从相册补充对应图片或手动填写。
- PaddleOCR 适配器、阿里云百炼视觉模型适配器及可复现 Mock 适配器。
- LangGraph 分析流程与独立节点文件。
- 70 种基础食品保存知识库：水果 20、蔬菜 20、肉类 10、奶制品 10、熟食 10。
- 常温、冷藏、冷冻三种保存方式与建议日期计算。
- 食品列表、分类筛选、详情、修改、软删除。
- 提前一天与到期当天两类微信订阅消息任务。
- 定时发送、失败记录、自动过期与提醒取消。
- Docker Compose、数据库迁移、初始化数据、环境示例与 README。

### 2.2 不包含

- 天气、温度和湿度修正模型。
- 整个冰箱照片的批量库存识别。
- 菜谱推荐、家庭共享、消费分析和智能家电连接。
- 后台运营管理平台。
- 持续上传摄像头视频流。
- 将知识库估算描述为食品安全保证。

## 3. 产品与视觉设计

视觉方向采用已确认的“温暖生活”方案：暖白背景、陶土色主操作、柔和圆角与生活化文案。页面应让用户感到亲切，但到期信息必须保持明确的风险层级。

状态色：

- 红色：当天或剩余 1 天。
- 黄色：剩余 2–7 天。
- 绿色：剩余超过 7 天。
- 灰色：已过期或已删除。

核心页面：

1. 首页：问候、优先处理摘要、全部/快吃/本周/正常筛选、食品列表、扫描入口。
2. 扫描页：全屏相机、取景引导、当前目标提示、字段识别进度、关键帧数量、相册补充入口。
3. 识别确认页：食品图片、可编辑字段、字段来源、低置信提示、建议日期和提醒授权入口。
4. 食品详情页：图片、类别、储存方式、日期依据、剩余时间、提醒状态、编辑和删除。
5. 手动添加页：相机拒绝授权或 AI 不可用时的完整兜底表单。

知识库计算出的日期统一显示为“建议食用日期”；包装明确标注的日期显示为“包装有效期”。页面附带简短提示：实际状态受开封、温度与食品状态影响，食用前仍需自行检查。

## 4. 连续扫描体验

### 4.1 用户体验

用户只启动一次扫描，不需要预先决定拍摄“正面图”还是“日期图”。界面根据当前缺失字段动态提示：

- 缺少身份信息：提示对准商品正面或完整食材。
- 缺少日期：提示对准日期喷码、有效期或保质期区域。
- 缺少储存条件：提示对准包装储存说明；无法读取时在确认页选择常温、冷藏或冷冻。

当信息足够时，扫描自动停止并进入确认页。识别失败时只要求补充缺少的部分，不让用户重复提交已经识别成功的信息。

### 4.2 客户端关键帧策略

微信小程序使用 `<camera>`、`wx.createCameraContext()` 和 `onCameraFrame()`。低分辨率实时帧只在本地用于亮度、模糊和稳定性判断；画面合格时调用 `takePhoto()` 取得高质量关键帧。每个扫描会话最多上传 4 张关键帧，按感知哈希移除近似重复图片，不上传完整视频。

真机性能保护：

- 低频抽样实时帧，不对每帧执行计算。
- 同一时间只允许一个关键帧上传和分析任务。
- 低端设备或帧监听失败时切换为“保持稳定后自动拍摄”的定时策略。
- 微信开发者工具用于页面和状态验证；实时相机帧必须在真机补充验收。

### 4.3 服务端字段分类

每张关键帧依次执行图像校验、OCR、字段分类与会话合并。系统识别并区分：

- `food_name`
- `brand`
- `production_date`
- `declared_expiry_date`
- `shelf_life_days`
- `storage_instruction`

当 OCR 无法得到可靠名称时：

- 首图已经是商品正面或无包装生鲜：直接复用该图调用视觉模型。
- 首图是包装背面、局部标签或日期区域：提示补扫商品正面。
- 补扫仍失败：保留日期等已识别字段，允许手动填写名称。

## 5. 系统架构

采用单仓库、模块化单体：

```text
微信原生小程序
    ↓ HTTPS / JSON / multipart
FastAPI API
    ↓
领域服务 + LangGraph 分析编排
    ↓
Ports：OCR / Vision / WeChat / Storage / Queue
    ↓
Mock 或 Real Adapters
    ↓
MySQL + Redis + 本地图片卷
```

仓库结构：

```text
miniprogram/                 微信原生小程序
backend/app/api/             API 路由与请求响应模型
backend/app/domain/          实体、枚举和纯业务规则
backend/app/services/        应用服务与用例
backend/app/agents/          LangGraph 状态与图构建
backend/app/agents/nodes/    独立分析节点
backend/app/adapters/        Mock/Real 外部服务适配器
backend/app/prompts/         独立 AI Prompt 文件
backend/app/models/          SQLAlchemy 模型
backend/app/repositories/    数据访问层
backend/app/workers/         ARQ 任务与定时任务
backend/migrations/          Alembic 迁移
backend/tests/               单元与集成测试
infra/                       Docker 和服务配置
scripts/                     Windows 开发、测试和初始化脚本
docs/                        设计、计划与运行文档
```

FastAPI 与 Worker 使用同一代码镜像。Redis 承担 ARQ 队列、短期缓存和去重；MySQL 是所有业务状态的唯一事实来源。图片开发环境保存在项目挂载卷，生产环境可通过 `StoragePort` 替换为对象存储。

关键帧上传采用异步任务：API 先校验所属用户、保存图片和任务记录，再将分析任务写入 ARQ 并返回 `202`；Worker 更新扫描会话，客户端每秒轮询会话状态，直到得到下一条扫描引导或进入确认页。入队失败时事务回滚，不留下永远处于分析中的会话。

## 6. LangGraph 分析流程

一次关键帧分析使用以下节点：

```text
validate_image
  → assess_quality
  → run_ocr
  → classify_ocr_fields
  → decide_visual_analysis
  → run_visual_analysis（条件节点）
  → merge_session_fields
  → calculate_date
  → decide_next_guidance
  → persist_result
```

Graph 状态包含：用户、扫描会话、当前图片、已有关键帧、OCR 文本、候选字段、字段置信度、字段证据、缺失字段、储存方式、日期依据、建议食用日期、下一条扫描提示和错误信息。

每个节点只负责一个明确功能，并依赖 Port 接口而非具体供应商 SDK。Prompt 按任务拆分为名称识别、无包装食品识别、OCR 字段纠错和结果融合四类文件，并带版本号以支持回归测试。

## 7. 数据模型

### 7.1 `users`

- `id`
- `openid`：Mock 用户使用保留前缀，Real 用户保存真实 openid
- `nickname`
- `avatar_url`
- `created_at`
- `updated_at`

### 7.2 `scan_sessions`

- `id`：UUID
- `user_id`
- `status`：`scanning / analyzing / needs_input / ready / finalized / cancelled / failed / expired`
- `mode`：`mock / real`
- `detected_fields`：JSON
- `field_confidence`：JSON
- `field_evidence`：JSON，记录字段来源图片和 OCR 文本片段
- `missing_fields`：JSON
- `next_guidance`
- `error_code`
- `created_at / updated_at / expires_at`

### 7.3 `scan_images`

- `id`
- `scan_session_id`
- `sequence`
- `purpose`：`general / identity / date / storage`
- `storage_path`
- `sha256`
- `perceptual_hash`
- `analysis_status`
- `ocr_text`
- `created_at`

### 7.4 `food_records`

- `id`
- `user_id`
- `scan_session_id`，手动添加时允许为空
- `food_name`
- `brand`
- `category`
- `thumbnail_path`
- `production_date`
- `declared_expiry_date`
- `shelf_life_days`
- `storage_type`：`room / chilled / frozen`
- `recommended_consume_by`
- `date_basis`：`declared_expiry / production_plus_shelf_life / knowledge_base_estimate`
- `confidence_summary`：JSON
- `lifecycle_status`：`active / expired / deleted`
- `created_at / updated_at / deleted_at`

### 7.5 `preservation_rules`

- `id`
- `food_name`
- `aliases`：JSON
- `category`
- `room_days`
- `chilled_days`
- `frozen_days`
- `source_note`
- `rule_version`
- `enabled`

不适用的保存方式使用空值，界面禁止选择，而不是把空值解释为 0 天。

### 7.6 `reminder_tasks`

- `id`
- `food_id`
- `reminder_type`：`day_before / due_day`
- `scheduled_at_utc`
- `timezone`
- `template_id`
- `status`：`pending / processing / sent / failed / cancelled`
- `attempt_count`
- `provider_message_id`
- `last_error_code`
- `sent_at`
- `created_at / updated_at`

食品生命周期与提醒发送状态严格分离，发送过提醒不会改变食品本身状态。

## 8. 日期与状态规则

日期优先级：

1. 有可靠的包装有效日期时，`recommended_consume_by = declared_expiry_date`。
2. 否则有生产日期和保质期天数时，使用 `生产日期 + N 个日历日`；例如 8 月 18 日生产、保质期 7 天，结果为 8 月 25 日。
3. 否则对无包装食品按知识库、储存方式和添加日期估算。
4. 有效日期与“生产日期 + 保质期”相互冲突时，不静默覆盖，确认页同时展示证据并要求用户选择。
5. 无日期且知识库没有匹配项时，用户必须手动设置建议日期后才能保存。

日期解析支持常见中文包装格式、点号/斜杠/连字符分隔和“见包装某处”等非日期文本过滤。两位年份与缺少年份的日期不自动猜测，必须确认。

首页按用户时区的自然日计算剩余天数：

- 小于 0：`expired`
- 0–1：红色“快吃”
- 2–7：黄色“本周”
- 大于 7：绿色“还新鲜”

每日定时任务将到期记录标记为 `expired`，取消其未发送提醒，但不自动物理删除食品历史。

## 9. API 设计

所有业务 API 使用 `/api/v1` 前缀。

### 9.1 登录

- `POST /auth/wechat/login`：输入微信 code；Mock 模式接受演示 code，返回应用会话 Token。
- `PATCH /users/me/profile`：用户主动更新昵称或头像。

### 9.2 扫描

- `POST /scan-sessions`：创建扫描会话。
- `POST /scan-sessions/{id}/frames`：上传单张关键帧，包含用途提示和幂等键，返回 `202`。
- `GET /scan-sessions/{id}`：获取识别字段、置信度、缺失字段、任务状态和下一条引导。
- `POST /scan-sessions/{id}/finalize`：提交用户确认后的字段并创建食品。
- `POST /scan-sessions/{id}/cancel`：取消未完成会话。

### 9.3 食品

- `GET /foods`：按 `urgent / this_week / normal / expired` 筛选。
- `POST /foods/manual`：手动创建。
- `GET /foods/{id}`：查看详情。
- `PATCH /foods/{id}`：修改字段并重新计算日期和提醒。
- `DELETE /foods/{id}`：软删除并取消提醒。

### 9.4 提醒与健康检查

- `POST /foods/{id}/reminders/subscription`：记录两个模板的授权结果并创建相应任务。
- `GET /health/live`：进程存活检查。
- `GET /health/ready`：MySQL、Redis 与队列就绪检查。

创建、确认和删除操作使用幂等键；所有食品和扫描资源均验证所属用户。

## 10. 微信提醒

用户点击“确认添加并设置提醒”后，小程序请求两个订阅消息模板：提前一天模板和到期当天模板。每个被接受的模板对应一条提醒任务；拒绝其中任一模板不影响食品保存，也不伪造已开启状态。

ARQ Worker 处理到期任务：

1. 从 MySQL 领取到期且为 `pending` 的任务。
2. 使用事务和状态更新避免重复领取。
3. 调用 Mock 或 Real `WeChatNotifierPort`。
4. 成功后记录发送时间和供应商消息标识。
5. 可重试错误按退避策略最多重试 3 次；永久错误直接标记 `failed`。
6. 每日过期任务负责更新食品状态并取消未来提醒。

所有时间在数据库中保存为 UTC，同时记录用户时区；V1 默认用户时区为 `Asia/Shanghai`。

## 11. Mock 与 Real 适配器

`APP_MODE=mock`：

- 固定演示用户，无须微信密钥。
- 三组可复现扫描场景：一次成功、名称缺失需补扫、无包装生鲜。
- Mock OCR 和视觉结果保留与 Real 模式相同的字段、置信度和错误结构。
- Mock 微信通知写入数据库和结构化日志，不向外发送。

`APP_MODE=real`：

- 微信 code2Session 与订阅消息。
- PaddleOCR 本地模型，模型目录显式配置到项目数据目录或 Docker 卷。
- 阿里云百炼视觉模型，模型名称通过环境变量配置。
- 网络调用使用超时、重试和脱敏错误日志。

适配器在应用启动时由配置注入。业务服务和 LangGraph 节点禁止直接导入供应商 SDK。

## 12. 错误恢复与隐私

- 相机权限拒绝：提供相册与手动添加，不循环请求权限。
- 关键帧上传失败：扫描会话保留，只重试该帧。
- OCR 或视觉超时：返回已识别字段，允许补扫或手填。
- 重复关键帧：返回可识别的重复状态，不消耗 4 张上限。
- 并发上传：同一会话串行处理，后到请求排队。
- 重复确认：幂等返回同一食品记录。
- 微信授权拒绝：保存食品并明确显示提醒未开启。
- 数据库或 Redis 不可用：就绪检查失败，API 返回统一可重试错误，不创建半成品记录。

日志不记录 openid、图片内容、访问 Token、微信 Secret 或百炼 API Key。上传图片仅用于识别和食品缩略图；扫描原始关键帧在会话完成 7 天后清理，只保留用户食品详情所需的缩略图。用户删除食品后清理关联缩略图与剩余扫描图片。

## 13. 配置、部署与磁盘边界

项目提供 `.env.example`，真实密钥只保存在未提交的 `.env`。主要配置包括：

- `APP_MODE`
- `DATABASE_URL`
- `REDIS_URL`
- `WECHAT_APP_ID / WECHAT_APP_SECRET`
- `WECHAT_PRE_EXPIRY_TEMPLATE_ID / WECHAT_DUE_DAY_TEMPLATE_ID`
- `DASHSCOPE_API_KEY / BAILIAN_VISION_MODEL`
- `PADDLEOCR_MODEL_DIR`
- `UPLOAD_DIR`
- `APP_TIMEZONE`

Docker Compose 默认服务：

- `api`
- `worker`
- `mysql`
- `redis`

Real OCR 使用单独 Compose Profile，避免 Mock 开发时下载 PaddleOCR 模型。MySQL 与 Redis 使用 Compose named volumes，它们实际存放在已迁移到 `D:\DockerData\wsl` 的 Docker 虚拟磁盘中；上传图片、日志和数据库备份使用项目下的 D 盘绑定目录。

项目脚本将 Python 虚拟环境、pip/npm 缓存、测试临时目录、上传图片和日志固定在 D 盘项目目录：

```text
.runtime/venv
.cache/pip
.cache/npm
.task-runtime/tmp
.data/uploads
.data/logs
.data/backups
```

Docker Desktop 的系统配置、安装日志和安装器临时解压仍可能少量写入 Windows 的 C 盘系统目录；应用主体、项目环境和容器虚拟磁盘使用 D 盘。

## 14. 测试与验收

### 14.1 后端

- 领域单元测试：日期解析、日期优先级、日期冲突、状态颜色、知识库查找和提醒生成。
- LangGraph 节点测试：每个节点独立测试；图级测试覆盖条件视觉识别和补扫分支。
- API 集成测试：使用 Docker MySQL 与 Redis，覆盖登录、扫描、确认、列表、详情、修改、删除和幂等。
- Worker 测试：冻结时钟验证提前一天、到期当天、重试、重复领取和自动过期。
- 适配器契约测试：Mock 与 Real 返回相同领域结构；Real HTTP 使用录制外形的本地桩，不在常规测试中消耗云 API。

### 14.2 小程序

- TypeScript 类型检查与静态检查。
- 扫描状态机测试：字段点亮、最大关键帧、重复帧、补扫和手动兜底。
- 请求层测试：Token、重试、幂等键和统一错误提示。
- 组件测试：首页筛选、食品卡片、确认表单和提醒状态。
- 微信开发者工具编译、页面跳转和 Mock API 联调。
- 真机测试：相机权限、实时帧监听、自动关键帧、拍照、相册、弱网和订阅消息弹窗。

### 14.3 完整验收场景

1. 包装鲜牛奶：扫描正面和日期区域，识别名称、生产日期、7 天保质期和冷藏，计算日期并创建两类提醒。
2. 包装背面：OCR 得到日期但名称缺失，页面提示补扫正面，视觉模型补齐名称后确认。
3. 草莓：无包装、无日期，视觉模型识别为草莓，用户选择冷藏，知识库给出建议食用日期。
4. 日期冲突：包装有效期与生产日期计算结果不一致，用户必须确认选择。
5. 权限与网络：拒绝相机、拒绝订阅、上传失败、OCR 超时均可恢复且不丢失已有结果。
6. 生命周期：提醒发送、到期标记、删除食品、取消未来提醒均符合状态规则。

## 15. 主要风险与控制

- 实时帧性能差异：低频采样、串行上传、4 张上限和真机分档测试。
- 包装日期格式复杂：规则解析与语义分类结合，低置信字段必须确认。
- 百炼或微信接口波动：Port 隔离、超时、重试、错误分类和 Mock 回归。
- PaddleOCR 镜像体积大：独立 Profile 和 D 盘模型卷，默认 Mock 开发不下载模型。
- 食品保存规则并非安全诊断：区分包装日期与知识库估算，并展示明确提示。
- 外部准确率无法用演示样例证明：独立标注数据集、固定评估脚本和版本化报告。

## 16. 实施顺序

1. 初始化仓库、D 盘环境脚本、Docker Compose、数据库迁移和健康检查。
2. 以测试驱动实现日期、状态、知识库和提醒等纯领域逻辑。
3. 实现用户、扫描会话、食品和提醒 API。
4. 实现 Mock 适配器、LangGraph 节点和 ARQ Worker，跑通后端闭环。
5. 实现原生小程序视觉系统、首页和详情页。
6. 实现连续扫描、关键帧、识别进度、补扫和确认页。
7. 在微信开发者工具与真机上完成 Mock 联调。
8. 实现并验证 Real 微信、PaddleOCR 和百炼适配器。
9. 完成文档、准确率评估框架、异常测试和最终验收。
