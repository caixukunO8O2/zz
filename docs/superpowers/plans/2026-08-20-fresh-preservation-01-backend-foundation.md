# 「鲜知」V1 后端基础实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可在 D 盘运行、由 Docker MySQL/Redis 支撑的 FastAPI 后端基础，并交付日期规则、70 种保鲜知识库、用户登录与食品 CRUD。

**Architecture:** FastAPI 作为模块化单体入口，纯领域规则不依赖数据库；SQLAlchemy 仓储负责持久化，Mock/Real 微信登录通过 Port 注入。Docker Compose 提供真实 MySQL 与 Redis，所有大体积数据落在 D 盘 Docker WSL 虚拟磁盘。

**Tech Stack:** Python 3.12（兼容下限 3.11）、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、MySQL 8.4、Redis 7、pytest、Docker Compose

**Spec:** `docs/superpowers/specs/2026-08-20-fresh-preservation-mini-program-design.md`

## Global Constraints

- 客户端固定为微信原生 TypeScript + WXML + WXSS，不引入 uni-app、Taro 或 React。
- Python 版本下限为 3.11；当前本机解释器为 `D:\DevTools\Python312\python.exe`。
- 所有项目虚拟环境、依赖缓存、数据库导出、上传文件、日志和测试临时文件写入 D 盘项目目录。
- Docker Desktop 应用位于 `D:\DevTools\DockerDesktop`，WSL 数据位于 `D:\DockerData\wsl`。
- 默认 `APP_MODE=mock`，MySQL 与 Redis 始终使用真实 Docker 服务。
- 业务状态唯一事实来源是 MySQL；Redis 仅用于队列、缓存、锁和去重。
- 日期估算必须标记依据；知识库结果不得描述成食品安全保证。
- 任何密钥不得提交到 Git；`.env.example` 只列配置名和安全的开发默认值。

## File Structure

```text
scripts/env.ps1                         当前 PowerShell 会话的 D 盘环境变量
scripts/bootstrap.ps1                   创建虚拟环境并锁定/安装依赖
scripts/dev.ps1                         启动 Compose 与 API
scripts/test.ps1                        统一执行后端测试
.env.example                            非敏感配置示例
backend/requirements.in                 运行依赖输入
backend/requirements-dev.in             开发依赖输入
backend/requirements.txt                pip-compile 生成的运行锁
backend/requirements-dev.txt            pip-compile 生成的开发锁
backend/pyproject.toml                   pytest、ruff、mypy 与包配置
backend/Dockerfile                      API/Worker 共用镜像
backend/app/main.py                     create_app 与健康检查
backend/app/core/config.py              Settings 与加载入口
backend/app/core/security.py            应用 Token 签发与解析
backend/app/domain/foods.py              食品领域类型和状态
backend/app/domain/date_rules.py         日期与列表分桶纯函数
backend/app/domain/preservation.py       保鲜规则类型与查找服务
backend/app/seed/preservation_rules.csv  70 种规则数据
backend/app/models/base.py               SQLAlchemy Base 与时间 mixin
backend/app/models/entities.py           用户、食品、规则模型
backend/app/models/idempotency.py         跨创建/确认/删除操作的幂等记录
backend/app/repositories/users.py        用户仓储
backend/app/repositories/foods.py        食品仓储
backend/app/repositories/rules.py        保鲜规则仓储
backend/app/repositories/idempotency.py  幂等占位、完成与重放
backend/app/api/deps.py                  DB、当前用户与服务依赖
backend/app/api/auth.py                  登录 API
backend/app/api/foods.py                 食品 CRUD API
backend/migrations/                      Alembic 配置和初始迁移
backend/tests/                           单元与集成测试
infra/compose.yaml                       MySQL、Redis、API，并由后续计划加入 Worker
```

---

### Task 1: D 盘运行环境与 FastAPI 健康检查

**Files:**
- Create: `scripts/env.ps1`
- Create: `scripts/bootstrap.ps1`
- Create: `scripts/dev.ps1`
- Create: `scripts/test.ps1`
- Create: `.env.example`
- Create: `backend/requirements.in`
- Create: `backend/requirements-dev.in`
- Create: `backend/pyproject.toml`
- Create: `backend/Dockerfile`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/api/test_health.py`
- Create: `infra/compose.yaml`

**Interfaces:**
- Produces: `app.main.create_app(settings: Settings | None = None) -> FastAPI`
- Produces: `app.core.config.get_settings() -> Settings`
- Produces: `GET /api/v1/health/live` and `GET /api/v1/health/ready`
- Consumes: Docker Engine and Compose already verified on the host.

- [ ] **Step 1: Write the failing health tests**

```python
# backend/tests/api/test_health.py
def test_live_returns_service_identity(client):
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "xianzhi-api"}


def test_ready_reports_injected_dependencies(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "mysql": "ok", "redis": "ok"}
```

`backend/tests/conftest.py` 创建 `Settings(app_mode="mock", database_url="mysql+aiomysql://test:test@mysql/test", redis_url="redis://redis:6379/0")`，并向 `create_app` 注入返回 MySQL/Redis 均为 `ok` 的测试 readiness probe。

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```powershell
. .\scripts\env.ps1
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\api\test_health.py -q
```

Expected: collection fails because `app.main` does not exist.

- [ ] **Step 3: Implement the environment scripts, locked dependencies, settings, app factory, and health routes**

`scripts/env.ps1` resolves the repository root and sets these exact variables:

```powershell
$env:VIRTUAL_ENV = Join-Path $RepoRoot '.runtime\venv'
$env:PIP_CACHE_DIR = Join-Path $RepoRoot '.cache\pip'
$env:npm_config_cache = Join-Path $RepoRoot '.cache\npm'
$env:TEMP = Join-Path $RepoRoot '.task-runtime\tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = Join-Path $RepoRoot 'backend'
```

`bootstrap.ps1` uses `D:\DevTools\Python312\python.exe -m venv`, installs `pip-tools`, compiles both `.in` files with hashes, and installs `requirements-dev.txt`. Runtime dependencies are `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `sqlalchemy`, `aiomysql`, `alembic`, `redis`, `arq`, `langchain`, `langgraph`, `python-multipart`, `PyJWT`, `httpx`, `Pillow`, and `structlog`. Development dependencies are `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-httpx`, `mypy`, `ruff`, `pip-tools`, and `types-PyYAML`.

`Settings` uses `env_file=".env"`, `extra="ignore"`, and the exact fields `app_mode`, `database_url`, `redis_url`, `jwt_secret`, `upload_dir`, `app_timezone`, `wechat_app_id`, `wechat_app_secret`, `wechat_pre_expiry_template_id`, `wechat_due_day_template_id`, `dashscope_api_key`, `bailian_vision_model`, and `paddleocr_model_dir`.

`create_app` mounts routers under `/api/v1`, stores the settings and readiness probe in `app.state`, and returns deterministic health JSON matching the tests. The foundation Compose file defines only `mysql`, `redis`, and `api`; Plan 02 adds the first runnable Worker after its module exists.

- [ ] **Step 4: Run unit checks and Compose configuration validation**

Run:

```powershell
. .\scripts\env.ps1
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\api\test_health.py -q
& .\.runtime\venv\Scripts\ruff.exe check backend
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml config --quiet
```

Expected: 2 tests pass, Ruff exits 0, Compose config exits 0.

- [ ] **Step 5: Commit**

```powershell
git add scripts .env.example backend infra
git commit -m "chore: bootstrap backend runtime and compose stack"
```

---

### Task 2: 食品日期、依据与首页状态纯领域逻辑

**Files:**
- Create: `backend/app/domain/__init__.py`
- Create: `backend/app/domain/foods.py`
- Create: `backend/app/domain/date_rules.py`
- Create: `backend/tests/unit/test_date_rules.py`

**Interfaces:**
- Produces: `StorageType`, `DateBasis`, `FoodLifecycle`, `FreshnessBucket` enums.
- Produces: `calculate_consume_by(...) -> DateCalculation`
- Produces: `freshness_bucket(consume_by: date, today: date) -> FreshnessBucket`
- Consumes: no database or framework dependencies.

- [ ] **Step 1: Write failing date-rule tests**

```python
def test_declared_expiry_has_priority():
    result = calculate_consume_by(
        declared_expiry=date(2026, 8, 24),
        production_date=date(2026, 8, 18),
        shelf_life_days=7,
        added_on=date(2026, 8, 20),
        knowledge_days=5,
    )
    assert result.consume_by == date(2026, 8, 24)
    assert result.basis is DateBasis.DECLARED_EXPIRY
    assert result.conflict is True


def test_production_plus_shelf_life_adds_n_calendar_days():
    result = calculate_consume_by(None, date(2026, 8, 18), 7, date(2026, 8, 20), None)
    assert result.consume_by == date(2026, 8, 25)
    assert result.basis is DateBasis.PRODUCTION_PLUS_SHELF_LIFE


@pytest.mark.parametrize(("remaining", "bucket"), [(-1, "expired"), (0, "urgent"), (1, "urgent"), (2, "this_week"), (7, "this_week"), (8, "normal")])
def test_freshness_boundaries(remaining, bucket):
    assert freshness_bucket(date(2026, 8, 20) + timedelta(days=remaining), date(2026, 8, 20)).value == bucket
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_date_rules.py -q`

Expected: import failure for `app.domain.date_rules`.

- [ ] **Step 3: Implement minimal immutable domain types and functions**

```python
@dataclass(frozen=True, slots=True)
class DateCalculation:
    consume_by: date
    basis: DateBasis
    conflict: bool


def calculate_consume_by(
    declared_expiry: date | None,
    production_date: date | None,
    shelf_life_days: int | None,
    added_on: date,
    knowledge_days: int | None,
) -> DateCalculation:
    calculated = production_date + timedelta(days=shelf_life_days) if production_date and shelf_life_days is not None else None
    if declared_expiry:
        return DateCalculation(declared_expiry, DateBasis.DECLARED_EXPIRY, calculated is not None and calculated != declared_expiry)
    if calculated:
        return DateCalculation(calculated, DateBasis.PRODUCTION_PLUS_SHELF_LIFE, False)
    if knowledge_days is not None:
        return DateCalculation(added_on + timedelta(days=knowledge_days), DateBasis.KNOWLEDGE_BASE_ESTIMATE, False)
    raise MissingDateBasisError("manual consume-by date is required")
```

Reject negative shelf-life days and declared expiry earlier than production date with typed domain errors. `freshness_bucket` implements the exact red/yellow/green boundaries from the spec.

- [ ] **Step 4: Run focused and full unit tests**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_date_rules.py -q
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit -q
```

Expected: all date and boundary tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/domain backend/tests/unit/test_date_rules.py
git commit -m "feat: add food date and freshness rules"
```

---

### Task 3: 70 种版本化保鲜知识库

**Files:**
- Create: `backend/app/domain/preservation.py`
- Create: `backend/app/seed/preservation_rules.csv`
- Create: `backend/tests/unit/test_preservation_rules.py`

**Interfaces:**
- Produces: `PreservationRule(name, aliases, category, room_days, chilled_days, frozen_days, source_note, version)`.
- Produces: `load_seed_rules(path: Path) -> tuple[PreservationRule, ...]`.
- Produces: `find_rule(rules, food_name: str) -> PreservationRule | None` with normalized exact alias matching.
- Consumes: `StorageType` from Task 2.

- [ ] **Step 1: Write failing seed integrity tests**

```python
def test_seed_has_required_category_counts(seed_rules):
    counts = Counter(rule.category for rule in seed_rules)
    assert counts == {"fruit": 20, "vegetable": 20, "meat": 10, "dairy": 10, "cooked": 10}


def test_requirement_examples_are_exact(seed_rules):
    assert find_rule(seed_rules, "草莓").days_for(StorageType.CHILLED) == 5
    assert find_rule(seed_rules, "香蕉").days_for(StorageType.FROZEN) is None
    assert find_rule(seed_rules, "苹果").days_for(StorageType.FROZEN) == 180
    assert find_rule(seed_rules, "鸡蛋").days_for(StorageType.CHILLED) == 30


def test_alias_match_is_normalized(seed_rules):
    assert find_rule(seed_rules, " 牛 奶 ").name == "鲜牛奶"
```

- [ ] **Step 2: Run tests and verify the missing seed failure**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_preservation_rules.py -q`

Expected: import or file-not-found failure.

- [ ] **Step 3: Implement the rule type, loader, and exact V1 seed matrix**

CSV columns are `name,aliases,category,room_days,chilled_days,frozen_days,source_note,version`. Use `|` between aliases and an empty cell for unsupported storage. Every row uses version `v1` and source note `V1 产品估算；实际状态受开封、温度和食品状态影响`.

The exact name set is:

```text
fruit: 草莓,香蕉,苹果,葡萄,橙子,梨,桃,李子,樱桃,蓝莓,芒果,菠萝,西瓜,哈密瓜,猕猴桃,柠檬,柚子,石榴,火龙果,荔枝
vegetable: 西兰花,菠菜,生菜,白菜,卷心菜,胡萝卜,土豆,番茄,黄瓜,茄子,青椒,芹菜,菜花,蘑菇,洋葱,南瓜,玉米,豆角,韭菜,油菜
meat: 猪肉,牛肉,羊肉,鸡肉,鸭肉,鸡胸肉,肉馅,香肠,培根,火腿
dairy: 鲜牛奶,酸奶,奶酪,黄油,淡奶油,炼乳,奶粉,奶油奶酪,鸡蛋,冰淇淋
cooked: 米饭,面条,粥,炒菜,炖肉,卤味,熟鸡蛋,熟海鲜,馒头,披萨
```

The exact `room/chilled/frozen` day matrix is:

```text
fruit: 草莓=1/5/30; 香蕉=5/7/-; 苹果=15/30/180; 葡萄=2/7/90; 橙子=10/21/180; 梨=7/30/180; 桃=2/7/180; 李子=3/7/180; 樱桃=1/5/180; 蓝莓=2/7/180; 芒果=5/7/180; 菠萝=2/5/180; 西瓜=3/7/180; 哈密瓜=5/7/180; 猕猴桃=7/30/180; 柠檬=14/30/180; 柚子=14/30/180; 石榴=14/60/180; 火龙果=5/14/180; 荔枝=2/5/180
vegetable: 西兰花=1/5/180; 菠菜=1/3/180; 生菜=1/5/-; 白菜=3/7/180; 卷心菜=7/21/180; 胡萝卜=7/30/365; 土豆=30/90/-; 番茄=7/10/180; 黄瓜=3/7/-; 茄子=3/7/180; 青椒=5/10/180; 芹菜=3/14/180; 菜花=2/7/180; 蘑菇=1/5/180; 洋葱=30/60/180; 南瓜=30/90/365; 玉米=2/5/180; 豆角=2/5/180; 韭菜=1/5/180; 油菜=1/5/180
meat: 猪肉=-/3/180; 牛肉=-/3/240; 羊肉=-/3/240; 鸡肉=-/2/270; 鸭肉=-/2/180; 鸡胸肉=-/2/270; 肉馅=-/1/120; 香肠=7/14/60; 培根=7/14/30; 火腿=7/7/60
dairy: 鲜牛奶=-/7/30; 酸奶=-/14/60; 奶酪=-/21/180; 黄油=1/90/270; 淡奶油=-/7/90; 炼乳=30/90/180; 奶粉=180/365/-; 奶油奶酪=-/14/60; 鸡蛋=7/30/90; 冰淇淋=-/-/60
cooked: 米饭=-/2/30; 面条=-/2/30; 粥=-/2/30; 炒菜=-/3/30; 炖肉=-/3/60; 卤味=-/3/30; 熟鸡蛋=-/7/30; 熟海鲜=-/2/30; 馒头=2/5/30; 披萨=1/3/30
```

`-` maps to an empty CSV cell, never zero. Add aliases `牛奶|纯牛奶` for `鲜牛奶`, `西红柿` for `番茄`, `花椰菜` for `菜花`, `青花菜` for `西兰花`, and `生鸡蛋|鲜鸡蛋` for `鸡蛋`; all other alias cells may be empty. Loader rejects duplicate normalized names or aliases, negative days, missing categories, or a category count different from 20/20/10/10/10.

- [ ] **Step 4: Run integrity tests and print a deterministic seed summary**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\unit\test_preservation_rules.py -q
& .\.runtime\venv\Scripts\python.exe -c "from pathlib import Path; from app.domain.preservation import load_seed_rules; print(len(load_seed_rules(Path('backend/app/seed/preservation_rules.csv'))))"
```

Expected: tests pass and the command prints `70`.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/domain/preservation.py backend/app/seed backend/tests/unit/test_preservation_rules.py
git commit -m "feat: add versioned preservation knowledge base"
```

---

### Task 4: SQLAlchemy 模型、Alembic 迁移与仓储

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/entities.py`
- Create: `backend/app/models/idempotency.py`
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/users.py`
- Create: `backend/app/repositories/foods.py`
- Create: `backend/app/repositories/rules.py`
- Create: `backend/app/repositories/idempotency.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/migrations/versions/0001_core_tables.py`
- Create: `backend/tests/integration/test_food_repository.py`

**Interfaces:**
- Produces: `session_scope() -> AsyncIterator[AsyncSession]`.
- Produces: `UserRepository.get_or_create_by_openid(openid: str) -> User`.
- Produces: `FoodRepository.create/list_for_user/get_for_user/update/soft_delete`.
- Produces: `RuleRepository.find_by_name(name: str) -> PreservationRuleModel | None`.
- Produces: `IdempotencyRepository.begin/complete/get_replay` scoped by user, route, key, and request hash.
- Consumes: Task 2 domain enums and Task 3 seed data.

- [ ] **Step 1: Write failing repository integration tests**

```python
@pytest.mark.asyncio
async def test_food_repository_is_user_scoped(db_session):
    owner = await UserRepository(db_session).get_or_create_by_openid("mock:owner")
    stranger = await UserRepository(db_session).get_or_create_by_openid("mock:stranger")
    created = await FoodRepository(db_session).create(owner.id, FoodCreateData(food_name="草莓", storage_type="chilled", recommended_consume_by=date(2026, 8, 25), date_basis="knowledge_base_estimate"))
    assert await FoodRepository(db_session).get_for_user(created.id, owner.id) is not None
    assert await FoodRepository(db_session).get_for_user(created.id, stranger.id) is None


@pytest.mark.asyncio
async def test_soft_delete_hides_food_from_active_list(db_session, seeded_user_and_food):
    user, food = seeded_user_and_food
    await FoodRepository(db_session).soft_delete(food.id, user.id)
    assert await FoodRepository(db_session).list_for_user(user.id, include_deleted=False) == []


@pytest.mark.asyncio
async def test_idempotency_rejects_same_key_with_changed_request(db_session, seeded_user):
    repository = IdempotencyRepository(db_session)
    await repository.begin(seeded_user.id, "/foods/manual", "key-1", "hash-a")
    with pytest.raises(IdempotencyConflict):
        await repository.begin(seeded_user.id, "/foods/manual", "key-1", "hash-b")
```

- [ ] **Step 2: Start MySQL/Redis and verify the tests fail before tables exist**

Run:

```powershell
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml up -d mysql redis
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\integration\test_food_repository.py -q
```

Expected: failure for missing model/repository or missing tables.

- [ ] **Step 3: Implement models, migration, seed hook, and scoped repositories**

Use MySQL `BIGINT` primary keys for users/foods/rules and `CHAR(36)` UUIDs for scan-linked nullable IDs. Store enum values as bounded strings, JSON evidence as MySQL JSON, and all timestamps as timezone-aware UTC values at the application boundary. Add indexes on `(user_id, lifecycle_status, recommended_consume_by)` and unique `users.openid`.

The initial migration creates `users`, `food_records`, `preservation_rules`, and `idempotency_records`, then inserts the 70 CSV rows through an idempotent seed function keyed by `(food_name, rule_version)`. The idempotency table has unique `(user_id, route, idempotency_key)`, request hash, status, response status, response resource ID, and bounded response JSON; a reused key with a different request hash is a conflict.

- [ ] **Step 4: Recreate the test database and run repository tests**

Run:

```powershell
Push-Location backend
& ..\.runtime\venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\integration\test_food_repository.py -q
```

Expected: repository tests pass; querying `preservation_rules` returns 70 enabled `v1` rows.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/db.py backend/app/models backend/app/repositories backend/migrations backend/alembic.ini backend/tests/integration
git commit -m "feat: add core persistence and repositories"
```

---

### Task 5: Mock 微信登录、会话 Token 与食品 CRUD API

**Files:**
- Create: `backend/app/ports/__init__.py`
- Create: `backend/app/ports/wechat_auth.py`
- Create: `backend/app/adapters/__init__.py`
- Create: `backend/app/adapters/mock_wechat_auth.py`
- Create: `backend/app/core/security.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/schemas/users.py`
- Create: `backend/app/schemas/foods.py`
- Create: `backend/app/services/auth_service.py`
- Create: `backend/app/services/food_service.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/app/api/users.py`
- Create: `backend/app/api/foods.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_auth_foods.py`

**Interfaces:**
- Produces: `WechatAuthPort.exchange_code(code: str) -> WechatIdentity`.
- Produces: `POST /api/v1/auth/wechat/login`.
- Produces: `GET /api/v1/users/me` and `PATCH /api/v1/users/me/profile`.
- Produces: `GET /api/v1/foods`, `POST /api/v1/foods/manual`, `GET/PATCH/DELETE /api/v1/foods/{id}`.
- Consumes: repositories from Task 4 and date/rule services from Tasks 2–3.

- [ ] **Step 1: Write failing API tests for auth, ownership, date calculation, and deletion**

```python
def test_mock_login_returns_bearer_token(client):
    response = client.post("/api/v1/auth/wechat/login", json={"code": "demo-user"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_manual_strawberry_uses_knowledge_rule(auth_client):
    response = auth_client.post("/api/v1/foods/manual", json={"food_name": "草莓", "category": "fruit", "storage_type": "chilled", "added_on": "2026-08-20"}, headers={"Idempotency-Key": "food-1"})
    assert response.status_code == 201
    assert response.json()["recommended_consume_by"] == "2026-08-25"
    assert response.json()["date_basis"] == "knowledge_base_estimate"


def test_other_user_cannot_read_food(client, owner_token, stranger_token, created_food):
    response = client.get(f"/api/v1/foods/{created_food['id']}", headers={"Authorization": f"Bearer {stranger_token}"})
    assert response.status_code == 404


def test_user_can_update_profile(auth_client):
    response = auth_client.patch("/api/v1/users/me/profile", json={"nickname": "小鲜", "avatar_url": "https://example.test/avatar.png"})
    assert response.status_code == 200
    assert response.json()["nickname"] == "小鲜"


def test_food_list_accepts_expired_filter(auth_client):
    response = auth_client.get("/api/v1/foods?bucket=expired")
    assert response.status_code == 200
    assert all(item["freshness_bucket"] == "expired" for item in response.json()["items"])


def test_delete_replays_with_same_idempotency_key(auth_client, created_food):
    headers = {"Idempotency-Key": "delete-food-1"}
    assert auth_client.delete(f"/api/v1/foods/{created_food['id']}", headers=headers).status_code == 204
    assert auth_client.delete(f"/api/v1/foods/{created_food['id']}", headers=headers).status_code == 204
```

- [ ] **Step 2: Run the focused API tests and verify route failures**

Run: `& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\api\test_auth_foods.py -q`

Expected: 404 or import failures because routes and services are absent.

- [ ] **Step 3: Implement Ports, mock auth, JWT, services, schemas, and routes**

JWT payload uses `sub=<user id>`, `iat`, and `exp` with a 7-day lifetime; algorithms are restricted to `HS256`. `MockWechatAuthAdapter` returns `openid=f"mock:{code}"` only when `APP_MODE=mock`. The user endpoints return the current profile and update only validated nickname/avatar fields. Manual food creation and DELETE require `Idempotency-Key`; duplicate matching requests replay the original status/body, while a changed payload returns `409 idempotency_conflict`. Food lists accept `bucket=urgent|this_week|normal|expired` and return an empty list for a valid bucket with no records. PATCH recalculates dates and DELETE performs soft deletion and later cancellation of reminders through Plan 04.

API errors use this stable envelope:

```json
{"error":{"code":"food_not_found","message":"没有找到这项食材","retryable":false}}
```

- [ ] **Step 4: Run API, type, and lint checks**

Run:

```powershell
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\api\test_auth_foods.py -q
& .\.runtime\venv\Scripts\python.exe -m mypy backend\app
& .\.runtime\venv\Scripts\ruff.exe check backend
```

Expected: focused tests pass, mypy and Ruff exit 0.

- [ ] **Step 5: Commit**

```powershell
git add backend/app backend/tests/api/test_auth_foods.py
git commit -m "feat: add mock login and food management api"
```

---

### Task 6: Docker Compose 集成验收与运行文档

**Files:**
- Modify: `infra/compose.yaml`
- Modify: `backend/app/main.py`
- Modify: `scripts/dev.ps1`
- Modify: `scripts/test.ps1`
- Create: `backend/tests/integration/test_stack_readiness.py`
- Create: `README.md`

**Interfaces:**
- Produces: `docker compose up -d --build` runnable stack.
- Produces: readiness probe that checks `SELECT 1` and Redis `PING`.
- Consumes: all outputs of Tasks 1–5.

- [ ] **Step 1: Write a failing real-readiness test**

```python
@pytest.mark.asyncio
async def test_real_readiness_reports_mysql_and_redis(real_settings):
    result = await probe_readiness(real_settings)
    assert result == {"status": "ready", "mysql": "ok", "redis": "ok"}
```

- [ ] **Step 2: Run the test with Compose dependencies and verify missing probe failure**

Run:

```powershell
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml up -d mysql redis
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests\integration\test_stack_readiness.py -q
```

Expected: import failure for `probe_readiness`.

- [ ] **Step 3: Implement real readiness, container healthchecks, and deterministic scripts**

MySQL healthcheck runs `mysqladmin ping`; Redis healthcheck runs `redis-cli ping`; API depends on both healthy services. `scripts/dev.ps1` sources `env.ps1`, creates `.env` from `.env.example` only when missing, starts the stack, runs Alembic, and prints `http://localhost:8000/docs`. `README.md` documents D-drive setup, Mock login, API examples, Compose stop/start, data locations, and the food-safety disclaimer.

- [ ] **Step 4: Run the full foundation verification**

Run:

```powershell
& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f infra\compose.yaml up -d --build
& .\.runtime\venv\Scripts\python.exe -m pytest backend\tests -q
& .\.runtime\venv\Scripts\ruff.exe check backend
& .\.runtime\venv\Scripts\python.exe -m mypy backend\app
Invoke-RestMethod http://localhost:8000/api/v1/health/ready | ConvertTo-Json -Compress
```

Expected: all backend tests pass; static checks exit 0; readiness prints `{"status":"ready","mysql":"ok","redis":"ok"}`.

- [ ] **Step 5: Commit**

```powershell
git add infra scripts backend README.md
git commit -m "test: verify dockerized backend foundation"
```
