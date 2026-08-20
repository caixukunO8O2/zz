# 「鲜知」V1 扫描分析实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一次连续扫描的服务端闭环：关键帧入队、Mock OCR/视觉识别、LangGraph 字段融合、动态补扫引导和用户确认入库。

**Architecture:** FastAPI 接收并持久化关键帧后返回 `202`，ARQ Worker 异步运行 LangGraph。扫描会话在 MySQL 中累计字段和证据，客户端轮询状态；Mock 与 Real 适配器共享 Port 契约，本计划先完整实现并验证 Mock 场景。

**Tech Stack:** FastAPI、SQLAlchemy 2、MySQL、Redis、ARQ、LangGraph、Pydantic v2、Pillow、pytest

**Spec:** `docs/superpowers/specs/2026-08-20-fresh-preservation-mini-program-design.md`

## Global Constraints

- 必须先完成 `2026-08-20-fresh-preservation-01-backend-foundation.md`。
- 默认 `APP_MODE=mock`，但领域结构和 Port 签名必须兼容 Real 适配器。
- 一个扫描会话最多接受 4 张非重复关键帧；同一会话串行分析。
- API 不等待 OCR/视觉执行完成；上传成功后返回 `202` 并由客户端轮询。
- OCR 已识别字段不得因视觉模型低置信结果被静默覆盖。
- 日期冲突必须保留双方证据并进入 `needs_input`。
- 原始图片、临时文件、测试图片和模型缓存全部位于 D 盘项目目录。
- Prompt 独立文件管理；LangGraph 节点一文件一职责。

## File Structure

```text
backend/app/domain/scans.py                    扫描状态、字段、置信度与合并规则
backend/app/models/scan_entities.py            扫描会话、图片和幂等记录
backend/app/repositories/scans.py               扫描持久化与事务锁
backend/app/ports/ocr.py                        OCR Port
backend/app/ports/vision.py                     Vision Port
backend/app/ports/storage.py                    图片 Storage Port
backend/app/adapters/mock_ocr.py                三种固定场景 OCR
backend/app/adapters/mock_vision.py             三种固定场景视觉识别
backend/app/adapters/local_storage.py           D 盘本地图片存储
backend/app/prompts/*.md                        版本化 Prompt
backend/app/agents/state.py                     LangGraph TypedDict 状态
backend/app/agents/graph.py                     图构建和条件边
backend/app/agents/nodes/*.py                   独立分析节点
backend/app/workers/scan_tasks.py               ARQ 关键帧任务
backend/app/services/scan_service.py            创建、查询、确认用例
backend/app/api/scans.py                        扫描 API
backend/tests/fixtures/images/                  小型确定性测试图片
backend/tests/unit|integration|api/             扫描测试
```

---

### Task 1: 扫描领域类型、会话模型与创建/查询 API

**Files:**
- Create: `backend/app/domain/scans.py`
- Create: `backend/app/models/scan_entities.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/repositories/scans.py`
- Create: `backend/app/schemas/scans.py`
- Create: `backend/app/services/scan_service.py`
- Create: `backend/app/api/scans.py`
- Modify: `backend/app/main.py`
- Create: `backend/migrations/versions/0002_scan_tables.py`
- Test: `backend/tests/api/test_scan_sessions.py`

**Interfaces:**
- Produces: `ScanStatus`, `ImagePurpose`, `FieldSource`, `DetectedField[T]`, `ScanFields`.
- Produces: `ScanRepository.create/get_for_user/add_image/update_state/lock_for_analysis`.
- Produces: `POST /api/v1/scan-sessions`, `GET /api/v1/scan-sessions/{id}`, and `POST /api/v1/scan-sessions/{id}/cancel`.
- Consumes: authenticated user dependency and DB session from Plan 01.

- [ ] **Step 1: Write failing session ownership and initial-state tests**

```python
def test_create_scan_session_returns_empty_progress(auth_client):
    response = auth_client.post("/api/v1/scan-sessions", json={"mock_scenario": "packaged_success"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "scanning"
    assert body["detected_fields"] == {}
    assert body["missing_fields"] == ["food_name", "date", "storage_type"]
    assert body["next_guidance"] == "请先对准商品正面或完整食材"


def test_scan_session_is_user_scoped(client, owner_scan_id, stranger_token):
    response = client.get(f"/api/v1/scan-sessions/{owner_scan_id}", headers={"Authorization": f"Bearer {stranger_token}"})
    assert response.status_code == 404


def test_cancel_marks_unfinished_session_cancelled(auth_client):
    session_id = auth_client.post("/api/v1/scan-sessions", json={}).json()["id"]
    response = auth_client.post(f"/api/v1/scan-sessions/{session_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
```

- [ ] **Step 2: Run the focused tests and verify route failures**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\api\test_scan_sessions.py -q`

Expected: 404 or import failures because the scan router is absent.

- [ ] **Step 3: Implement typed fields, models, migration, repository, service, and routes**

`DetectedField` stores `value`, `confidence` in `[0, 1]`, `source_image_id`, `source_kind` (`ocr/vision/user`), and `evidence_text`. `ScanFields` has optional `food_name`, `brand`, `category`, `production_date`, `declared_expiry_date`, `shelf_life_days`, and `storage_type`. Cancel validates ownership and changes only unfinished sessions to `cancelled`; repeating cancel is safe, while finalized sessions return `409 invalid_scan_transition`.

The migration creates `scan_sessions` and `scan_images`; `scan_sessions.id` is `CHAR(36)`, has a user/status index, JSON fields for detections/confidence/evidence/missing fields, an expiry timestamp 24 hours after creation, and a nullable `mock_scenario` accepted only in Mock mode.

- [ ] **Step 4: Apply migration and run tests**

Run:

```powershell
Push-Location backend
& ..\.runtime\venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\api\test_scan_sessions.py -q
```

Expected: tests pass and a newly created session persists the authenticated user ID.

- [ ] **Step 5: Commit**

```powershell
git add backend/app backend/migrations backend/tests/api/test_scan_sessions.py
git commit -m "feat: add scan session lifecycle"
```

---

### Task 2: 关键帧存储、质量校验、去重与上传 API

**Files:**
- Create: `backend/app/ports/storage.py`
- Create: `backend/app/adapters/local_storage.py`
- Create: `backend/app/services/image_quality.py`
- Modify: `backend/app/services/scan_service.py`
- Modify: `backend/app/api/scans.py`
- Create: `backend/tests/fixtures/images/clear-label.jpg`
- Create: `backend/tests/fixtures/images/dark-label.jpg`
- Test: `backend/tests/unit/test_image_quality.py`
- Test: `backend/tests/api/test_scan_frames.py`

**Interfaces:**
- Produces: `StoragePort.save_scan_image(session_id: UUID, content: bytes, suffix: str) -> StoredImage`.
- Produces: `assess_image(content: bytes) -> ImageAssessment` with `width`, `height`, `brightness`, `sharpness`, `sha256`, `perceptual_hash`, and `accepted`.
- Produces: `POST /api/v1/scan-sessions/{id}/frames` returning `202`.
- Consumes: scan repository and settings upload directory.

- [ ] **Step 1: Write failing quality, duplicate, limit, and path-containment tests**

```python
def test_dark_image_is_rejected(dark_image_bytes):
    result = assess_image(dark_image_bytes)
    assert result.accepted is False
    assert result.reason == "image_too_dark"


def test_clear_image_has_hashes(clear_image_bytes):
    result = assess_image(clear_image_bytes)
    assert len(result.sha256) == 64
    assert len(result.perceptual_hash) == 16


def test_fifth_unique_frame_is_rejected(auth_client, scan_with_four_frames, clear_image_path):
    response = auth_client.post(f"/api/v1/scan-sessions/{scan_with_four_frames}/frames", files={"image": ("fifth.jpg", clear_image_path.read_bytes(), "image/jpeg")}, data={"purpose": "date"}, headers={"Idempotency-Key": "frame-5"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "frame_limit_reached"
```

- [ ] **Step 2: Run tests and verify missing implementation failures**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_image_quality.py backend\tests\api\test_scan_frames.py -q
```

Expected: import or route failures.

- [ ] **Step 3: Implement local storage and deterministic image assessment**

Accept JPEG/PNG up to 8 MiB and at least 480×480. Calculate brightness from a 64×64 grayscale thumbnail, sharpness from mean adjacent-pixel gradient, SHA-256 from original bytes, and 64-bit average hash for duplicate detection. Store under `<UPLOAD_DIR>/scans/<user-id>/<session-id>/<image-id>.<ext>` and verify the resolved path remains inside `UPLOAD_DIR`.

Perceptual Hamming distance `<= 4` is duplicate; duplicates return `200` with the existing image ID and do not consume the 4-frame limit. Accepted new frames return `202` with `analysis_status="queued"`.

- [ ] **Step 4: Run focused tests and verify files land under `.data/uploads`**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_image_quality.py backend\tests\api\test_scan_frames.py -q
Get-ChildItem .data\uploads\scans -Recurse -File | Select-Object -First 1 FullName
```

Expected: tests pass; printed path begins with the repository's D-drive `.data\uploads\scans` path.

- [ ] **Step 5: Commit**

```powershell
git add backend/app backend/tests backend/tests/fixtures/images
git commit -m "feat: accept and validate scan keyframes"
```

---

### Task 3: OCR/Vision Port、Mock 场景与字段合并规则

**Files:**
- Create: `backend/app/ports/ocr.py`
- Create: `backend/app/ports/vision.py`
- Create: `backend/app/adapters/mock_ocr.py`
- Create: `backend/app/adapters/mock_vision.py`
- Create: `backend/app/adapters/factory.py`
- Create: `backend/app/domain/date_parser.py`
- Create: `backend/app/prompts/packaged_food_identity-v1.md`
- Create: `backend/app/prompts/fresh_food_identity-v1.md`
- Create: `backend/app/prompts/ocr_field_correction-v1.md`
- Create: `backend/app/prompts/result_merge-v1.md`
- Create: `backend/tests/unit/test_mock_analysis_adapters.py`
- Create: `backend/tests/unit/test_date_parser.py`
- Create: `backend/tests/unit/test_field_merge.py`

**Interfaces:**
- Produces: `OcrPort.extract(image: StoredImage, purpose: ImagePurpose) -> OcrResult`.
- Produces: `VisionPort.identify(images: Sequence[StoredImage], ocr_text: str) -> VisionResult`.
- Produces: `parse_date_candidates(text: str, reference_date: date) -> tuple[ParsedDateCandidate, ...]`.
- Produces: `merge_fields(existing: ScanFields, candidates: Sequence[DetectedField]) -> MergeResult`.
- Consumes: stored image metadata and scan domain types.

- [ ] **Step 1: Write failing contract and precedence tests**

```python
@pytest.mark.asyncio
async def test_packaged_success_mock_returns_required_fields(mock_ocr):
    result = await mock_ocr.extract(mock_image("packaged_success", 1), ImagePurpose.GENERAL)
    assert result.text == "鲜牛奶 生产日期 2026-08-18 保质期7天 冷藏"
    assert result.fields["production_date"].value == date(2026, 8, 18)
    assert result.fields["shelf_life_days"].value == 7


def test_lower_confidence_vision_does_not_replace_ocr_name(existing_ocr_name, lower_vision_name):
    merged = merge_fields(ScanFields(food_name=existing_ocr_name), [lower_vision_name])
    assert merged.fields.food_name.value == "伊利鲜牛奶"
    assert merged.fields.food_name.source_kind == "ocr"


@pytest.mark.parametrize("text, expected", [
    ("生产日期 2026.08.18", date(2026, 8, 18)),
    ("有效期至 2026/08/25", date(2026, 8, 25)),
    ("EXP 2026-08-25", date(2026, 8, 25)),
])
def test_date_parser_accepts_supported_separators(text, expected):
    assert parse_date_candidates(text, date(2026, 8, 20))[0].value == expected


@pytest.mark.parametrize("text", ["有效期 26/08/25", "有效期 08/25", "有效期见包装顶部"])
def test_ambiguous_or_non_date_text_is_not_auto_confirmed(text):
    assert all(candidate.auto_confirm is False for candidate in parse_date_candidates(text, date(2026, 8, 20)))
```

- [ ] **Step 2: Run tests and verify Port/adapter imports fail**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_mock_analysis_adapters.py backend\tests\unit\test_date_parser.py backend\tests\unit\test_field_merge.py -q`

Expected: import failures.

- [ ] **Step 3: Implement exact Mock scenarios and merge precedence**

Mock scenarios:

```text
packaged_success frame 1: name=伊利鲜牛奶, category=dairy, production_date=2026-08-18, shelf_life_days=7, storage_type=chilled
needs_identity frame 1: production_date=2026-08-18, shelf_life_days=7, storage_type=chilled; no name
needs_identity frame 2: vision name=伊利鲜牛奶, category=dairy, brand=伊利
fresh_produce frame 1: vision name=草莓, category=fruit; no package dates
```

`parse_date_candidates` normalizes Chinese `年/月/日` plus `.`, `/`, and `-` separators. Four-digit valid dates may be auto-confirmed when their semantic label is clear. Two-digit years and month/day values remain evidence with `auto_confirm=false`; phrases such as `见包装顶部` produce no concrete date. Invalid calendar values are rejected. The four versioned prompt files remain separate so packaged identity, fresh-food identity, OCR correction, and result fusion can be regression-tested independently.

Merge order is user-confirmed value > higher-confidence OCR value > higher-confidence vision value. Values with equal confidence keep the existing value. Every chosen field retains source image ID and evidence text. A declared expiry conflict is represented as a separate conflict entry, never resolved inside `merge_fields`.

- [ ] **Step 4: Run adapter contracts and merge tests**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_mock_analysis_adapters.py backend\tests\unit\test_date_parser.py backend\tests\unit\test_field_merge.py -q
& .\.runtime\venv\Scripts\python.exe -m mypy backend\app\ports backend\app\adapters
```

Expected: all tests pass and mypy confirms both Mock adapters implement their Protocols.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/ports backend/app/adapters backend/app/domain/date_parser.py backend/app/prompts backend/tests/unit
git commit -m "feat: add mock ocr and vision contracts"
```

---

### Task 4: LangGraph 节点与动态扫描引导

**Files:**
- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/agents/state.py`
- Create: `backend/app/agents/graph.py`
- Create: `backend/app/agents/nodes/validate_image.py`
- Create: `backend/app/agents/nodes/run_ocr.py`
- Create: `backend/app/agents/nodes/decide_visual.py`
- Create: `backend/app/agents/nodes/run_visual.py`
- Create: `backend/app/agents/nodes/merge_fields.py`
- Create: `backend/app/agents/nodes/calculate_date.py`
- Create: `backend/app/agents/nodes/decide_guidance.py`
- Create: `backend/app/agents/nodes/persist_result.py`
- Test: `backend/tests/unit/test_analysis_graph.py`

**Interfaces:**
- Produces: `AnalysisState` TypedDict.
- Produces: `build_analysis_graph(deps: AnalysisDependencies) -> CompiledStateGraph`.
- Produces: final `status`, `fields`, `conflicts`, `missing_fields`, `next_guidance`, and `date_calculation`.
- Consumes: Ports and merge rules from Task 3; date rules from Plan 01.

- [ ] **Step 1: Write failing graph-path tests**

```python
@pytest.mark.asyncio
async def test_name_missing_requests_identity_frame(mock_graph):
    result = await mock_graph.ainvoke(state_for("needs_identity", frame=1))
    assert result["status"] == "needs_input"
    assert result["missing_fields"] == ["food_name"]
    assert result["next_guidance"] == "没有认出是什么，请对准商品正面继续扫描"


@pytest.mark.asyncio
async def test_fresh_produce_uses_knowledge_date(mock_graph):
    result = await mock_graph.ainvoke(state_for("fresh_produce", frame=1, storage_type="chilled"))
    assert result["fields"]["food_name"].value == "草莓"
    assert result["date_calculation"].consume_by == date(2026, 8, 25)
    assert result["status"] == "ready"
```

- [ ] **Step 2: Run graph tests and verify missing graph failure**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_analysis_graph.py -q`

Expected: import failure for `build_analysis_graph`.

- [ ] **Step 3: Implement focused nodes and conditional edges**

`run_ocr` normalizes OCR fields through `parse_date_candidates`, retains ambiguous date evidence, and forwards only auto-confirmable dates as calculated candidates. `decide_visual` returns `run_visual` only when `food_name` is absent or below `0.70`, or when category is absent for knowledge lookup. `decide_guidance` uses this exact order:

```python
if conflict_fields:
    return needs_input("识别到不一致的日期，请确认包装信息")
if not food_name:
    return needs_input("没有认出是什么，请对准商品正面继续扫描")
if not has_any_date and category not in FRESH_CATEGORIES:
    return needs_input("请对准生产日期、有效期或保质期区域")
if not storage_type:
    return needs_input("没有识别到保存方式，请扫描储存说明或手动选择")
return ready()
```

Every node returns only its changed keys. Adapter instances, repositories, clock, and rule lookup enter through `AnalysisDependencies`; nodes do not construct globals.

- [ ] **Step 4: Run graph and domain regression tests**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_analysis_graph.py backend\tests\unit\test_date_rules.py backend\tests\unit\test_field_merge.py -q
& .\.runtime\venv\Scripts\ruff.exe check backend/app/agents
```

Expected: graph branches and domain regressions pass; Ruff exits 0.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/agents backend/tests/unit/test_analysis_graph.py
git commit -m "feat: orchestrate scan analysis with langgraph"
```

---

### Task 5: ARQ 异步任务、串行会话分析与轮询状态

**Files:**
- Create: `backend/app/workers/__init__.py`
- Create: `backend/app/workers/settings.py`
- Create: `backend/app/workers/scan_tasks.py`
- Modify: `backend/app/services/scan_service.py`
- Modify: `backend/app/api/scans.py`
- Modify: `infra/compose.yaml`
- Test: `backend/tests/integration/test_scan_worker.py`

**Interfaces:**
- Produces: `analyze_scan_frame(ctx: dict, scan_image_id: int) -> None`.
- Produces: ARQ `WorkerSettings` with Redis connection and analysis dependencies.
- Produces: upload transaction that persists image, enqueues job, then returns `202`.
- Consumes: graph from Task 4 and scan repository from Task 1.

- [ ] **Step 1: Write failing worker transaction and serialization tests**

```python
@pytest.mark.asyncio
async def test_worker_updates_session_to_needs_input(worker_ctx, queued_needs_identity_image):
    await analyze_scan_frame(worker_ctx, queued_needs_identity_image.id)
    session = await worker_ctx["scan_repository"].get(queued_needs_identity_image.scan_session_id)
    assert session.status == "needs_input"
    assert session.next_guidance == "没有认出是什么，请对准商品正面继续扫描"


@pytest.mark.asyncio
async def test_same_session_jobs_are_serialized(worker_ctx, two_queued_images_same_session):
    await asyncio.gather(*(analyze_scan_frame(worker_ctx, image.id) for image in two_queued_images_same_session))
    assert await worker_ctx["scan_repository"].max_parallel_analyses(two_queued_images_same_session[0].scan_session_id) == 1
```

- [ ] **Step 2: Run tests with Redis and verify missing worker failure**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\integration\test_scan_worker.py -q`

Expected: import failure for `analyze_scan_frame`.

- [ ] **Step 3: Implement ARQ startup/shutdown, MySQL row lock, and failure mapping**

Worker acquires the session with `SELECT ... FOR UPDATE`, moves image `queued → analyzing → completed/failed`, runs the graph, persists state in the same transaction, and releases the lock. Timeout maps to retryable `analysis_timeout`; invalid images map to permanent `invalid_image`. Retryable jobs use ARQ `Retry(defer=2 ** attempt)` with maximum 3 attempts.

If Redis enqueue fails, upload transaction deletes the new DB image row and stored file, then returns `503 queue_unavailable`; it never leaves a queued row without a job.

- [ ] **Step 4: Start worker and run integration tests**

Run:

```powershell
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml up -d --build mysql redis worker
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\integration\test_scan_worker.py -q
```

Expected: worker tests pass and Compose reports the worker container running.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/workers backend/app/services/scan_service.py backend/app/api/scans.py infra/compose.yaml backend/tests/integration/test_scan_worker.py
git commit -m "feat: process scan frames asynchronously"
```

---

### Task 6: 用户确认、日期冲突、幂等食品创建与三场景验收

**Files:**
- Modify: `backend/app/schemas/scans.py`
- Modify: `backend/app/services/scan_service.py`
- Modify: `backend/app/api/scans.py`
- Modify: `backend/app/api/foods.py`
- Create: `backend/tests/api/test_scan_finalize.py`
- Create: `backend/tests/e2e/test_mock_scan_flows.py`

**Interfaces:**
- Produces: `POST /api/v1/scan-sessions/{id}/finalize`.
- Produces: one food record linked to the finalized scan session.
- Produces: `GET /api/v1/foods/{id}/thumbnail`, readable only by the food owner.
- Consumes: food service from Plan 01 and completed scan fields from Tasks 1–5.

- [ ] **Step 1: Write failing finalize and end-to-end tests**

```python
def test_finalize_requires_explicit_conflict_choice(auth_client, conflicted_scan):
    response = auth_client.post(f"/api/v1/scan-sessions/{conflicted_scan}/finalize", json={"fields": confirmed_fields_without_choice()}, headers={"Idempotency-Key": "finalize-conflict"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "date_conflict_requires_choice"


def test_duplicate_finalize_returns_same_food(auth_client, ready_scan):
    first = auth_client.post(f"/api/v1/scan-sessions/{ready_scan}/finalize", json={"fields": confirmed_fields()}, headers={"Idempotency-Key": "finalize-1"})
    second = auth_client.post(f"/api/v1/scan-sessions/{ready_scan}/finalize", json={"fields": confirmed_fields()}, headers={"Idempotency-Key": "finalize-1"})
    assert first.json()["food"]["id"] == second.json()["food"]["id"]
    assert second.status_code == 200


def test_thumbnail_is_owner_scoped(client, owner_token, stranger_token, finalized_food):
    assert client.get(f"/api/v1/foods/{finalized_food}/thumbnail", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get(f"/api/v1/foods/{finalized_food}/thumbnail", headers={"Authorization": f"Bearer {stranger_token}"}).status_code == 404
```

- [ ] **Step 2: Run finalize tests and verify missing endpoint behavior**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\api\test_scan_finalize.py backend\tests\e2e\test_mock_scan_flows.py -q`

Expected: 404 or missing-service failures.

- [ ] **Step 3: Implement transactional finalize**

Finalize accepts all editable fields plus `date_conflict_choice` when conflicts exist. It validates ownership and `ready/needs_input` status, treats submitted fields as `source_kind="user"`, recalculates the date, creates one food, sets session `finalized`, and completes the Plan 01 idempotency record in one transaction. A second identical key returns the same resource; the same key with different payload returns `409 idempotency_conflict`. It derives a JPEG thumbnail with long side at most 480 px and quality 80 from the best identity/general image, strips metadata, stores only its path on the food, and exposes bytes through the owner-scoped thumbnail route; no filesystem path appears in JSON.

- [ ] **Step 4: Run full Mock scan acceptance**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\e2e\test_mock_scan_flows.py -q
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests -q
& .\.runtime\venv\Scripts\ruff.exe check backend
& .\.runtime\venv\Scripts\python.exe -m mypy backend\app
```

Expected: packaged success, identity补扫, fresh produce scenarios pass; all backend tests and static checks pass.

- [ ] **Step 5: Commit**

```powershell
git add backend
git commit -m "feat: finalize mock scan flows into foods"
```
