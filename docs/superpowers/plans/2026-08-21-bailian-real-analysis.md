# Bailian Real Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable real Bailian OCR and visual food recognition while making the scan flashlight stay on during scanning.

**Architecture:** Keep `APP_MODE=mock` for local WeChat login and select the scan-analysis provider independently. A Bailian OCR adapter calls `qwen3.5-ocr` for package fields; a Bailian vision adapter calls `qwen3.7-flash` only when identity is missing. Images are sent as Base64 data URLs and the API key remains in the ignored root `.env`.

**Tech Stack:** FastAPI worker, httpx, DashScope multimodal HTTP API, pytest, native WeChat mini-program camera.

**Spec:** User-approved dual-model design in the current Codex task.

## Global Constraints

- Never commit or log `DASHSCOPE_API_KEY`.
- Keep MySQL and Redis loopback-only.
- Preserve mock analysis as the default and as a test path.
- Use `qwen3.5-ocr` for OCR and `qwen3.7-flash` for visual fallback.
- Flash toggle must map to camera `torch`, not photo-only `on`.

---

### Task 1: Continuous flashlight

**Files:**
- Modify: `miniprogram/pages/scan/index.ts`
- Modify: `miniprogram/domain/scan-machine.ts`
- Test: `miniprogram/tests/scan-machine.test.ts`

**Interfaces:**
- Consumes: WeChat camera `flash` values.
- Produces: `nextFlashMode(current): "off" | "torch"`.

- [ ] Add a failing test asserting `off -> torch -> off`.
- [ ] Run the focused Vitest test and confirm the missing function failure.
- [ ] Implement `nextFlashMode` and use it from `toggleFlash`.
- [ ] Run the focused test and TypeScript check.

### Task 2: Bailian OCR and vision adapters

**Files:**
- Create: `backend/app/adapters/bailian_client.py`
- Create: `backend/app/adapters/bailian_ocr.py`
- Create: `backend/app/adapters/bailian_vision.py`
- Create: `backend/tests/unit/test_bailian_analysis_adapters.py`
- Modify: `backend/app/adapters/factory.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/workers/scan_tasks.py`
- Modify: `infra/compose.yaml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: stored image paths, image MIME types, provider settings.
- Produces: existing `OcrResult` and `VisionResult` port values.

- [ ] Write failing adapter tests with an injected HTTP transport and realistic provider JSON.
- [ ] Run the focused pytest file and confirm missing adapter failures.
- [ ] Implement Base64 image encoding, bounded HTTP calls, strict response parsing, typed field conversion, and provider-neutral failures.
- [ ] Add independent `ANALYSIS_PROVIDER`, OCR model, vision model, and base URL settings; wire them into the worker factory.
- [ ] Run focused adapter, factory, worker, Ruff, and mypy checks.

### Task 3: Local real-API smoke test

**Files:**
- Modify locally only: `.env`

**Interfaces:**
- Consumes: the user-provided Bailian API key.
- Produces: running worker using real Bailian analysis while local WeChat login remains mock.

- [ ] Save the key and provider/model configuration in ignored `.env`.
- [ ] Make one minimal `qwen3.7-flash` API request and verify the model/account endpoint.
- [ ] Rebuild and restart only API/worker services as required.
- [ ] Verify readiness, focused tests, and that no secret appears in tracked changes.
