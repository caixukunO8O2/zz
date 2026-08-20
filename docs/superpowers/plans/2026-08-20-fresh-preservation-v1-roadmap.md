# 「鲜知」V1 实施路线图

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement the linked plans task-by-task. Steps in each linked plan use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按依赖顺序交付可演示、可切换真实服务的「鲜知」V1 原生微信小程序。

**Architecture:** 四份实施计划共享同一模块化 FastAPI 后端、MySQL 事实数据、Redis 队列，以及原生微信小程序客户端；每份计划以已验证接口作为下一份计划的输入。

**Tech Stack:** 微信原生 TypeScript/WXML/WXSS、FastAPI、SQLAlchemy、MySQL、Redis、ARQ、LangGraph、PaddleOCR、阿里云百炼、Docker Compose

**Spec:** `docs/superpowers/specs/2026-08-20-fresh-preservation-mini-program-design.md`

V1 拆为四份按顺序执行的实施计划。每份计划都必须完成其测试和提交后，下一份计划才能开始。

1. `2026-08-20-fresh-preservation-01-backend-foundation.md`
   - D 盘运行环境、Docker Compose、领域规则、70 种知识库、数据库、登录与食品 API。
   - 完成标志：真实 MySQL/Redis 下食品 CRUD 集成测试通过。
2. `2026-08-20-fresh-preservation-02-scan-analysis.md`
   - 扫描会话、关键帧、Mock 适配器、LangGraph、ARQ 异步分析与确认入库。
   - 完成标志：三种 Mock 场景通过 API 完整跑通。
3. `2026-08-20-fresh-preservation-03-miniprogram.md`
   - ImageGen 视觉概念、原生小程序、首页、详情、连续扫描、确认与手动兜底。
   - 完成标志：微信开发者工具编译通过，Mock 后端核心交互与真机相机流程通过；提醒授权回传在下一计划接入真实端点。
4. `2026-08-20-fresh-preservation-04-reminders-real-adapters.md`
   - 提醒 Worker、微信真实接口、PaddleOCR、百炼视觉、隐私清理、准确率框架与发布文档。
   - 完成标志：无密钥环境的契约与端到端测试通过；提供密钥时可执行真实服务冒烟测试。

## 全局执行门槛

- 所有 Python、Node、测试临时文件与缓存必须由 `scripts/env.ps1` 固定到 D 盘项目目录。
- 每个业务任务遵循红—绿—重构：先看到目标测试失败，再实现最小代码，再运行完整相关测试。
- 每个任务单独提交；不得把下一任务的功能混入当前提交。
- 每份计划结束时运行该计划规定的全量验证命令，并记录真实输出。
- 外部服务没有密钥时不得伪造真实成功；只能报告契约测试和 Mock 验证结果。
- 小程序相机最终验收必须使用真机，开发者工具的模拟结果不能替代真机证据。
