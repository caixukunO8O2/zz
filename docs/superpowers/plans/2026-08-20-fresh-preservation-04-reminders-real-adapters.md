# 「鲜知」V1 提醒与真实适配器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付提醒调度、微信真实登录/通知、PaddleOCR、阿里云百炼、隐私清理、准确率评估和最终端到端验收。

**Architecture:** Reminder Worker 与扫描 Worker 共用后端镜像和 ARQ；MySQL 保存任务事实，Redis 负责领取协调。Real 适配器实现既有 Port，并通过 HTTP/模型桩做无密钥契约测试；真实密钥存在时才运行 live smoke 标记测试。

**Tech Stack:** ARQ、MySQL、Redis、httpx、PaddleOCR、阿里云百炼兼容 API、微信小程序 API、pytest、Docker Compose

**Spec:** `docs/superpowers/specs/2026-08-20-fresh-preservation-mini-program-design.md`

## Global Constraints

- 必须先完成后端、扫描和小程序三份计划。
- 食品生命周期与提醒任务状态严格分离。
- 每个被接受的模板授权只创建一条对应类型任务；拒绝授权不创建可发送任务。
- 数据库存 UTC，用户时区固定为 `Asia/Shanghai`，页面按该时区显示自然日。
- Worker 使用事务领取和幂等发送，最大重试 3 次。
- 外部调用不得记录 openid、Token、Secret、API Key 或原始图片。
- 无真实凭据时 live 测试必须明确 `SKIPPED`，不得改写为成功。
- PaddleOCR 模型和缓存位于 D 盘 Docker 卷；默认 Mock 启动不得下载模型。
- 真实服务产生费用的测试只在用户提供凭据并明确启用 `RUN_LIVE_TESTS=1` 时执行。

## File Structure

```text
backend/app/domain/reminders.py                  提醒时间与状态规则
backend/app/models/reminder_entities.py          提醒与授权模型
backend/app/repositories/reminders.py             事务领取和状态更新
backend/app/ports/wechat_notify.py                微信通知 Port
backend/app/adapters/mock_wechat_notify.py        日志型 Mock 通知
backend/app/adapters/wechat_auth.py               code2Session Real 登录
backend/app/adapters/wechat_notify.py             订阅消息 Real 通知
backend/app/adapters/paddle_ocr.py                 PaddleOCR Real 适配器
backend/app/adapters/bailian_vision.py             百炼 Real 视觉适配器
backend/app/workers/reminder_tasks.py              发送、过期、清理定时任务
backend/app/services/reminder_service.py           授权结果与任务创建
backend/app/api/reminders.py                       授权 API
backend/app/evaluation/                             准确率清单与评估器
infra/compose.yaml                                  real-ocr Profile
docs/runbooks/                                      真实服务和运维说明
backend/tests/                                      提醒、契约、live、e2e 测试
```

---

### Task 1: 提醒时间、授权、模型、仓储与 API

**Files:**
- Create: `backend/app/domain/reminders.py`
- Create: `backend/app/models/reminder_entities.py`
- Create: `backend/app/repositories/reminders.py`
- Create: `backend/app/services/reminder_service.py`
- Create: `backend/app/schemas/reminders.py`
- Create: `backend/app/api/reminders.py`
- Modify: `backend/app/main.py`
- Create: `backend/migrations/versions/0003_reminders.py`
- Test: `backend/tests/unit/test_reminder_rules.py`
- Test: `backend/tests/api/test_reminder_subscription.py`

**Interfaces:**
- Produces: `build_reminder_specs(consume_by: date, timezone: str, accepted_types: set[ReminderType]) -> tuple[ReminderSpec, ...]`.
- Produces: `ReminderRepository.claim_due(now_utc, limit)`, `mark_sent`, `mark_failed`, `cancel_for_food`.
- Produces: `POST /api/v1/foods/{id}/reminders/subscription`.
- Consumes: food ownership, user timezone, and template IDs.

- [ ] **Step 1: Write failing reminder boundary and authorization tests**

```python
def test_two_accepted_templates_create_two_shanghai_9am_tasks():
    specs = build_reminder_specs(date(2026, 8, 25), "Asia/Shanghai", {ReminderType.DAY_BEFORE, ReminderType.DUE_DAY})
    assert [(spec.type.value, spec.scheduled_at_utc.isoformat()) for spec in specs] == [
        ("day_before", "2026-08-24T01:00:00+00:00"),
        ("due_day", "2026-08-25T01:00:00+00:00"),
    ]


def test_rejected_template_does_not_create_pending_task(auth_client, active_food):
    response = auth_client.post(f"/api/v1/foods/{active_food}/reminders/subscription", json={"day_before": "accept", "due_day": "reject"})
    assert response.status_code == 200
    assert [item["reminder_type"] for item in response.json()["tasks"]] == ["day_before"]


def test_1000_synthetic_reminders_match_expected_instants():
    cases = synthetic_reminder_cases(count=1000, timezone="Asia/Shanghai", seed=20260820)
    assert sum(build_reminder_specs(case.consume_by, case.timezone, case.accepted_types) == case.expected for case in cases) == 1000
```

- [ ] **Step 2: Run tests and verify missing reminder modules**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_reminder_rules.py backend\tests\api\test_reminder_subscription.py -q`

Expected: import or route failures.

- [ ] **Step 3: Implement exact reminder rules and persistence**

Send time is 09:00 in the user's timezone. If the calculated send time is already in the past when authorization is recorded, create the task for the next whole minute and mark `late_schedule=true` in metadata. Unique constraint `(food_id, reminder_type)` prevents duplicates. Updating a food's consume-by date cancels pending tasks and recreates only types with valid unconsumed authorization.

`claim_due` uses `SELECT ... FOR UPDATE SKIP LOCKED`, moves selected rows from `pending` to `processing`, and increments `attempt_count` in the same transaction.

- [ ] **Step 4: Apply migration and run tests**

Run:

```powershell
Push-Location backend
& ..\.runtime\venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_reminder_rules.py backend\tests\api\test_reminder_subscription.py -q
```

Expected: tests pass; all 1000 deterministic boundary cases match, and duplicate authorization calls do not create duplicate tasks.

- [ ] **Step 5: Commit**

```powershell
git add backend
git commit -m "feat: add reminder subscriptions and scheduling"
```

---

### Task 2: Mock/Real 微信通知与提醒 Worker

**Files:**
- Create: `backend/app/ports/wechat_notify.py`
- Create: `backend/app/adapters/mock_wechat_notify.py`
- Create: `backend/app/adapters/wechat_notify.py`
- Create: `backend/app/workers/reminder_tasks.py`
- Modify: `backend/app/workers/settings.py`
- Test: `backend/tests/unit/test_wechat_notify_contract.py`
- Test: `backend/tests/integration/test_reminder_worker.py`

**Interfaces:**
- Produces: `WechatNotifierPort.send(message: ReminderMessage) -> SendResult`.
- Produces: `dispatch_due_reminders(ctx) -> int`, `expire_foods(ctx) -> int`.
- Consumes: reminder repository and configured notifier.

- [ ] **Step 1: Write failing send, retry, idempotency, and expiry tests**

```python
@pytest.mark.asyncio
async def test_successful_dispatch_marks_sent(worker_ctx, due_task):
    sent = await dispatch_due_reminders(worker_ctx)
    assert sent == 1
    refreshed = await worker_ctx["reminder_repository"].get(due_task.id)
    assert refreshed.status == "sent"
    assert refreshed.provider_message_id == "mock-message-1"


@pytest.mark.asyncio
async def test_retryable_failure_returns_task_to_pending(worker_ctx, due_task, retryable_notifier):
    await dispatch_due_reminders({**worker_ctx, "notifier": retryable_notifier})
    refreshed = await worker_ctx["reminder_repository"].get(due_task.id)
    assert refreshed.status == "pending"
    assert refreshed.attempt_count == 1


@pytest.mark.asyncio
async def test_expiry_cancels_future_tasks(worker_ctx, food_due_yesterday):
    assert await expire_foods(worker_ctx) == 1
    assert (await worker_ctx["food_repository"].get(food_due_yesterday.id)).lifecycle_status == "expired"
    assert await worker_ctx["reminder_repository"].pending_for_food(food_due_yesterday.id) == []
```

- [ ] **Step 2: Run tests and verify missing notifier/worker failure**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_wechat_notify_contract.py backend\tests\integration\test_reminder_worker.py -q`

Expected: import failures.

- [ ] **Step 3: Implement notifier contract, access-token cache, error classification, and cron jobs**

Real adapter retrieves a stable access token through the configured WeChat endpoint, caches it in Redis for `expires_in - 300` seconds, and posts subscribe messages. WeChat credential/recipient/template errors are permanent; timeout, connection, HTTP 429, and server errors are retryable. Logs contain only task ID, template type, status, latency, and provider error code.

ARQ cron schedules `dispatch_due_reminders` every minute, `expire_foods` daily at 00:10 Asia/Shanghai, and stale processing recovery every five minutes. A `processing` task older than ten minutes returns to pending only when `attempt_count < 3`.

- [ ] **Step 4: Run contract and frozen-clock worker tests**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_wechat_notify_contract.py backend\tests\integration\test_reminder_worker.py -q
& .\.runtime\venv\Scripts\python.exe -m mypy backend\app\ports\wechat_notify.py backend\app\adapters\wechat_notify.py
```

Expected: all tests pass; mypy confirms Mock and Real implementations satisfy the Port.

- [ ] **Step 5: Commit**

```powershell
git add backend/app backend/tests
git commit -m "feat: dispatch wechat reminders safely"
```

---

### Task 3: Real 微信登录适配器与契约测试

**Files:**
- Create: `backend/app/adapters/wechat_auth.py`
- Modify: `backend/app/adapters/factory.py`
- Test: `backend/tests/unit/test_wechat_auth_contract.py`
- Test: `backend/tests/live/test_wechat_live.py`
- Create: `docs/runbooks/wechat.md`

**Interfaces:**
- Produces: Real `WechatAuthPort.exchange_code(code) -> WechatIdentity`.
- Consumes: `WECHAT_APP_ID`, `WECHAT_APP_SECRET`, and shared httpx client.

- [ ] **Step 1: Write failing HTTP contract tests**

```python
@pytest.mark.asyncio
async def test_real_auth_maps_code2session_response(httpx_mock, settings):
    httpx_mock.add_response(json={"openid": "openid-1", "session_key": "secret-session"})
    identity = await WechatAuthAdapter(settings, httpx.AsyncClient()).exchange_code("wx-code")
    assert identity.openid == "openid-1"
    assert "secret-session" not in repr(identity)


@pytest.mark.asyncio
async def test_real_auth_maps_wechat_error_without_leaking_secret(httpx_mock, settings):
    httpx_mock.add_response(json={"errcode": 40029, "errmsg": "invalid code"})
    with pytest.raises(ExternalAuthError, match="invalid_wechat_code"):
        await WechatAuthAdapter(settings, httpx.AsyncClient()).exchange_code("bad")
```

- [ ] **Step 2: Run contract tests and verify missing adapter failure**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_wechat_auth_contract.py -q`

Expected: import failure for Real adapter.

- [ ] **Step 3: Implement safe code2Session mapping and mode factory**

Use a 5-second connect and 10-second total timeout. Never persist `session_key`. Factory returns Mock adapter only for `APP_MODE=mock`; Real mode validates both app credentials on startup. `wechat.md` documents AppID, Secret, request domain, two subscription template IDs, local HTTPS proxy requirements, and how to rotate credentials without committing them.

- [ ] **Step 4: Run contract tests and conditional live smoke**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_wechat_auth_contract.py -q
$env:RUN_LIVE_TESTS='0'
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\live\test_wechat_live.py -q
```

Expected: contract tests pass; live test reports one skipped test when `RUN_LIVE_TESTS` is `0`. With credentials and a fresh one-time code, set `RUN_LIVE_TESTS=1` and expect pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/adapters backend/tests docs/runbooks/wechat.md
git commit -m "feat: add real wechat authentication adapter"
```

---

### Task 4: PaddleOCR Real 适配器与独立 Compose Profile

**Files:**
- Create: `backend/app/adapters/paddle_ocr.py`
- Create: `backend/requirements-ocr.in`
- Create: `backend/requirements-ocr.txt`
- Create: `backend/Dockerfile.ocr`
- Modify: `backend/app/adapters/factory.py`
- Modify: `infra/compose.yaml`
- Create: `backend/tests/contract/test_paddle_ocr_adapter.py`
- Create: `backend/tests/live/test_paddle_ocr_live.py`
- Create: `docs/runbooks/paddleocr.md`

**Interfaces:**
- Produces: Real `OcrPort.extract(image, purpose) -> OcrResult`.
- Produces: Compose profile `real-ocr` with model/cache volumes under D-drive Docker storage.
- Consumes: stored images and OCR Port from scan plan.

- [ ] **Step 1: Write failing normalized-output contract tests**

```python
def test_normalize_paddle_lines_to_ocr_result():
    raw = [[[[10, 10], [110, 10], [110, 30], [10, 30]], ("生产日期 2026.08.18", 0.98)]]
    result = normalize_paddle_result(raw)
    assert result.text == "生产日期 2026.08.18"
    assert result.lines[0].confidence == pytest.approx(0.98)
    assert result.lines[0].box == ((10, 10), (110, 10), (110, 30), (10, 30))
```

- [ ] **Step 2: Run contract test and verify missing normalizer**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\contract\test_paddle_ocr_adapter.py -q`

Expected: import failure for `normalize_paddle_result`.

- [ ] **Step 3: Implement lazy model loading and real-ocr image**

Model initialization occurs once per worker process on first OCR call, never at module import. `PADDLEOCR_MODEL_DIR` is mandatory in Real mode and maps to `/models/paddleocr`; download/cache variables point to that same volume. Normalize all provider shapes into `OcrLine(text, confidence, box)` and discard blank text but retain low-confidence evidence for the confirmation UI.

Generate `backend/requirements-ocr.txt` with `& .\.runtime\venv\Scripts\pip-compile.exe --generate-hashes --output-file backend\requirements-ocr.txt backend\requirements-ocr.in`. The `real-ocr` profile builds `Dockerfile.ocr`, installs that OCR lock after the base application lock, mounts the model volume, and never starts during default Mock Compose.

- [ ] **Step 4: Run contract and optional live OCR tests**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\contract\test_paddle_ocr_adapter.py -q
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml --profile real-ocr config --quiet
$env:RUN_LIVE_TESTS='0'
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\live\test_paddle_ocr_live.py -q
```

Expected: contract test and Compose config pass; live test skips without downloaded model. When enabled, the clear label fixture returns non-empty text containing a date token.

- [ ] **Step 5: Commit**

```powershell
git add backend infra docs/runbooks/paddleocr.md
git commit -m "feat: add paddleocr real adapter profile"
```

---

### Task 5: 阿里云百炼视觉 Real 适配器

**Files:**
- Create: `backend/app/adapters/bailian_vision.py`
- Modify: `backend/app/adapters/factory.py`
- Test: `backend/tests/contract/test_bailian_vision_adapter.py`
- Test: `backend/tests/live/test_bailian_live.py`
- Create: `docs/runbooks/bailian.md`

**Interfaces:**
- Produces: Real `VisionPort.identify(images, ocr_text) -> VisionResult`.
- Consumes: `DASHSCOPE_API_KEY`, `BAILIAN_VISION_MODEL`, versioned prompt, and at most four scan images.

- [ ] **Step 1: Write failing schema, malformed JSON, and timeout tests**

```python
@pytest.mark.asyncio
async def test_bailian_maps_structured_food_result(httpx_mock, settings):
    httpx_mock.add_response(json=provider_response('{"food_name":"伊利鲜牛奶","category":"dairy","brand":"伊利","confidence":0.93}'))
    result = await BailianVisionAdapter(settings, httpx.AsyncClient()).identify([stored_image()], "生产日期 2026-08-18")
    assert result.fields["food_name"].value == "伊利鲜牛奶"
    assert result.fields["food_name"].confidence == pytest.approx(0.93)


@pytest.mark.asyncio
async def test_malformed_provider_json_is_retryable(httpx_mock, settings):
    httpx_mock.add_response(json=provider_response("not-json"))
    with pytest.raises(VisionProviderError) as error:
        await BailianVisionAdapter(settings, httpx.AsyncClient()).identify([stored_image()], "")
    assert error.value.retryable is True
```

- [ ] **Step 2: Run contract tests and verify missing adapter failure**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\contract\test_bailian_vision_adapter.py -q`

Expected: import failure.

- [ ] **Step 3: Implement image encoding, structured response validation, and redacted logs**

Resize each image so the long side is at most 1600 px, encode JPEG quality 85, and send at most four images. Require JSON fields `food_name`, `category`, optional `brand`, optional `storage_type`, and `confidence` in `[0,1]`. Pydantic rejects unknown top-level fields. Timeout is 30 seconds; one retry is allowed for timeout, 429, 5xx, or malformed model JSON. Logs include image count and byte total, never base64, OCR text, or API key.

- [ ] **Step 4: Run contract and conditional live tests**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\contract\test_bailian_vision_adapter.py -q
$env:RUN_LIVE_TESTS='0'
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\live\test_bailian_live.py -q
```

Expected: contract tests pass; live test skips without opt-in. With a valid key and opt-in, the strawberry fixture returns `food_name=草莓` and `category=fruit`.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/adapters backend/tests docs/runbooks/bailian.md
git commit -m "feat: add bailian vision adapter"
```

---

### Task 6: 图片清理、准确率框架、全栈验收与发布文档

**Files:**
- Create: `backend/app/workers/cleanup_tasks.py`
- Modify: `backend/app/workers/settings.py`
- Create: `backend/app/evaluation/__init__.py`
- Create: `backend/app/evaluation/run.py`
- Create: `backend/app/evaluation/schema.py`
- Create: `backend/evaluation/sample-manifest.csv`
- Create: `backend/tests/integration/test_cleanup.py`
- Create: `backend/tests/unit/test_evaluation.py`
- Create: `backend/tests/e2e/test_v1_stack.py`
- Create: `docs/qa/v1-backend-results.md`
- Create: `docs/runbooks/deployment.md`
- Modify: `README.md`

**Interfaces:**
- Produces: `cleanup_expired_scan_images(ctx, now_utc) -> CleanupResult`.
- Produces: `python -m app.evaluation.run --manifest <csv> --output <json>`.
- Produces: final Dockerized Mock stack and opt-in Real smoke workflow.
- Consumes: every previous plan output.

- [ ] **Step 1: Write failing cleanup and evaluation-metric tests**

```python
@pytest.mark.asyncio
async def test_cleanup_deletes_finalized_raw_images_after_seven_days(cleanup_ctx, finalized_scan_from_eight_days_ago):
    result = await cleanup_expired_scan_images(cleanup_ctx, now_utc=datetime(2026, 8, 20, tzinfo=UTC))
    assert result.deleted_images == finalized_scan_from_eight_days_ago.image_count
    assert finalized_scan_from_eight_days_ago.thumbnail_path.exists()


def test_evaluation_metrics_are_exact():
    report = evaluate([expected("草莓", "2026-08-25"), expected("苹果", "2026-09-01")], [predicted("草莓", "2026-08-25"), predicted("梨", "2026-09-01")])
    assert report.food_top1_accuracy == 0.5
    assert report.date_exact_accuracy == 1.0
```

- [ ] **Step 2: Run focused tests and verify missing cleanup/evaluator**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\integration\test_cleanup.py backend\tests\unit\test_evaluation.py -q`

Expected: import failures.

- [ ] **Step 3: Implement retention, evaluation, deployment, and runbook details**

Cleanup removes raw images for finalized/cancelled/failed sessions older than 7 days, expired unfinished sessions older than 24 hours, and all images for deleted foods after the thumbnail delete transaction succeeds. It validates path containment before deletion and reports counts without paths.

Evaluation manifest columns are `case_id,image_paths,expected_food_name,expected_category,expected_production_date,expected_expiry_date,expected_shelf_life_days,expected_storage_type`. Report includes sample counts, food top-1, category accuracy, per-date-field exact accuracy, aggregate date accuracy, failure cases, adapter mode, model names, Prompt versions, and Git commit. The evaluator labels a run `target_evaluable=false` unless it contains at least 200 identity examples and 300 package-date examples; the committed small sample manifest is only a smoke fixture and cannot substantiate the 90%/95% Real accuracy targets.

`deployment.md` documents D-drive paths, Compose profiles, migrations, backup/restore, health checks, logs, secret rotation, live-test opt-in, rollback, and Docker Desktop licensing note.

- [ ] **Step 4: Run final full-stack verification**

Run:

```powershell
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml down
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml up -d --build
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests -q
& .\.runtime\venv\Scripts\ruff.exe check backend
& .\.runtime\venv\Scripts\python.exe -m mypy backend\app
Push-Location miniprogram
npm test -- --run
npm run typecheck
npm run lint
& 'D:\微信web开发者工具\cli.bat' preview --project $PWD.Path --qr-format terminal
Pop-Location
Invoke-RestMethod http://localhost:8000/api/v1/health/ready | ConvertTo-Json -Compress
```

Expected: backend and client test suites pass; static checks exit 0; preview QR is produced; readiness reports MySQL and Redis `ok`. Record exact command output, skipped live tests, Docker service versions, and remaining credential-dependent checks in `docs/qa/v1-backend-results.md`.

- [ ] **Step 5: Commit**

```powershell
git add backend miniprogram infra docs README.md
git commit -m "test: complete v1 full-stack verification"
```
