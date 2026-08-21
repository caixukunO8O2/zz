import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.bailian_client import BailianProviderError
from app.agents.state import AnalysisState
from app.core.config import Settings
from app.domain.scans import ScanFields
from app.models.entities import FoodRecord, User
from app.models.idempotency import IdempotencyRecord
from app.models.scan_entities import ScanImage, ScanSession
from app.repositories.scans import ScanRepository
from app.repositories.users import UserRepository
from app.workers.scan_tasks import analyze_scan_frame

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi_test",
)


async def _clean(session: AsyncSession) -> None:
    database_name = await session.scalar(text("SELECT DATABASE()"))
    if database_name != "xianzhi_test":
        raise RuntimeError(f"refusing worker cleanup on {database_name!r}")
    for model in (ScanImage, ScanSession, IdempotencyRecord, FoodRecord, User):
        await session.execute(delete(model))


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _clean(session)
        await session.commit()
    yield factory
    async with factory() as session:
        await _clean(session)
        await session.commit()
    await engine.dispose()


async def _queued_images(
    factory: async_sessionmaker[AsyncSession],
    *,
    count: int,
    scenario: str = "needs_identity",
) -> tuple[int, list[int]]:
    async with factory() as session:
        user = await UserRepository(session).get_or_create_by_openid(
            f"worker-{scenario}-{count}"
        )
        scan = await ScanRepository(session).create(
            user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            mock_scenario=scenario,
        )
        images: list[ScanImage] = []
        for index in range(count):
            image = ScanImage(
                scan_session_id=scan.id,
                purpose="general",
                storage_path=f"D:/mock/{index + 1}.jpg",
                content_type="image/jpeg",
                sha256=f"{index + 1:064x}",
                perceptual_hash=f"{index + 1:016x}",
                width=640,
                height=640,
                brightness=120,
                sharpness=30,
                analysis_status="queued",
            )
            scan.images.append(image)
            images.append(image)
        await session.commit()
        return user.id, [image.id for image in images]


def _settings() -> Settings:
    return Settings(
        app_mode="mock",
        analysis_provider="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
    )


@pytest.mark.asyncio
async def test_worker_updates_session_to_needs_input(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, image_ids = await _queued_images(session_factory, count=1)

    await analyze_scan_frame(
        {"session_factory": session_factory, "settings": _settings()}, image_ids[0]
    )

    async with session_factory() as session:
        image = await session.get(ScanImage, image_ids[0])
        scan = await session.scalar(
            select(ScanSession).where(ScanSession.user_id == user_id)
        )
        assert image is not None and image.analysis_status == "completed"
        assert scan is not None and scan.status == "needs_input"
        assert scan.next_guidance == "没有认出是什么，请对准商品正面继续扫描"


@pytest.mark.asyncio
async def test_final_provider_failure_marks_the_scan_failed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, image_ids = await _queued_images(session_factory, count=1)

    async def failed_analysis(state: AnalysisState) -> AnalysisState:
        del state
        raise BailianProviderError("provider detail must stay internal")

    await analyze_scan_frame(
        {
            "session_factory": session_factory,
            "settings": _settings(),
            "analysis_runner": failed_analysis,
            "job_try": 3,
        },
        image_ids[0],
    )

    async with session_factory() as session:
        image = await session.get(ScanImage, image_ids[0])
        scan = await session.scalar(
            select(ScanSession).where(ScanSession.user_id == user_id)
        )
        assert image is not None and image.analysis_status == "failed"
        assert image.failure_code == "analysis_provider_failed"
        assert scan is not None and scan.status == "failed"


@pytest.mark.asyncio
async def test_same_session_jobs_are_serialized_by_database_lock(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, image_ids = await _queued_images(session_factory, count=2)
    active = 0
    maximum_active = 0

    async def slow_analysis(state: AnalysisState) -> AnalysisState:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {
            **state,
            "fields": ScanFields(),
            "conflicts": (),
            "status": "needs_input",
            "missing_fields": ["food_name"],
            "next_guidance": "没有认出是什么，请对准商品正面继续扫描",
            "date_calculation": None,
        }

    context = {
        "session_factory": session_factory,
        "settings": _settings(),
        "analysis_runner": slow_analysis,
    }
    await asyncio.gather(
        *(analyze_scan_frame(context, image_id) for image_id in image_ids)
    )

    assert maximum_active == 1
