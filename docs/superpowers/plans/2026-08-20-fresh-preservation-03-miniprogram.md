# 「鲜知」V1 原生小程序实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付“温暖生活”视觉方向的微信原生小程序，实现登录、首页、食品详情、一次连续扫描、定向补扫、确认修改和手动兜底。

**Architecture:** 页面使用原生 TypeScript、WXML 与 WXSS；纯 TypeScript 模块承载扫描状态机、字段进度和请求逻辑，以 Vitest 测试。相机页低频读取帧判断清晰与稳定，合格后自动拍摄关键帧；后端状态通过轮询更新页面。

**Tech Stack:** 微信原生小程序、TypeScript、WXML、WXSS、微信开发者工具、Vitest、ESLint、Prettier、ImageGen 概念设计

**Spec:** `docs/superpowers/specs/2026-08-20-fresh-preservation-mini-program-design.md`

## Global Constraints

- 必须先完成扫描后端计划并保持 Mock API 可运行。
- 客户端不得引入 uni-app、Taro、React 或将静态截图作为 UI。
- 视觉固定为暖白背景、陶土色主操作、柔和圆角、生活化中文文案。
- 当天或剩余 1 天红色，2–7 天黄色，超过 7 天绿色，已过期灰色。
- 所有可操作文字、按钮、输入、列表和状态必须代码原生；图片只承担食品照片和装饰。
- 关键帧上限为 4；同一时间只上传一张；缺少什么只引导补扫什么。
- 相机拒绝、弱网、OCR 超时、订阅拒绝都必须有不丢数据的兜底路径。
- npm 缓存和测试产物通过 `scripts/env.ps1` 固定到 D 盘。
- 微信开发者工具 CLI 固定为 `D:\微信web开发者工具\cli.bat`。

## File Structure

```text
docs/design/xianzhi-v1-concept.png             最终接受的高保真概念
miniprogram/project.config.json                微信项目配置
miniprogram/package.json                       TypeScript 测试与静态检查
miniprogram/tsconfig.json                      编译配置
miniprogram/app.ts|app.json|app.wxss           应用入口和全局视觉变量
miniprogram/services/api.ts                    登录、食品、扫描和提醒 API
miniprogram/services/http.ts                   Token、重试和错误封装
miniprogram/store/session.ts                   用户会话
miniprogram/domain/scan-machine.ts             可测试扫描状态机
miniprogram/domain/freshness.ts                首页颜色和文案
miniprogram/utils/frame-quality.ts             低频帧质量判断
miniprogram/components/food-card/*             食品卡片
miniprogram/components/field-progress/*        扫描字段进度
miniprogram/pages/home/*                       首页
miniprogram/pages/food-detail/*                详情与删除
miniprogram/pages/scan/*                       连续扫描
miniprogram/pages/scan-confirm/*               识别确认与提醒授权
miniprogram/pages/manual-add/*                 手动添加
miniprogram/tests/*                            Vitest 纯逻辑和服务测试
```

---

### Task 1: ImageGen 高保真概念与视觉规格冻结

**Files:**
- Create: `docs/design/xianzhi-v1-concept.png`
- Create: `docs/design/xianzhi-v1-visual-ledger.md`

**Interfaces:**
- Produces: one accepted 3:4 composite containing Home, Scan, Confirm, and Detail screens.
- Produces: exact visual ledger for colors, typography, radii, spacing, icons, copy, and image treatment.
- Consumes: approved “C · 温暖生活” direction from the design spec.

- [ ] **Step 1: Generate the concept with ImageGen**

Use the image generation skill with this exact intent:

```text
Create a polished 3:4 product-design concept board for a native Chinese WeChat mini program named “鲜知”. Show four complete mobile screens side by side: 家里的新鲜 home inventory, full-screen 扫描食材 camera with detected-field chips, 确认食材信息 editable result, and 伊利鲜牛奶 detail. Warm ivory background, restrained terracotta primary color, soft peach food-photo surfaces, rounded but not childish, calm premium household utility, excellent Chinese typography hierarchy. Use exact visible Chinese copy from the approved spec. Status colors must remain red/yellow/green. No English marketing copy, no glassmorphism, no generic dashboard cards, no floating navigation, no device mockup frame, no extra features.
```

Save the accepted raster without rescaling as `docs/design/xianzhi-v1-concept.png`.

- [ ] **Step 2: Present the concept and obtain explicit visual acceptance**

Show the image at its native dimensions. Approval must cover all four screens; requested changes generate a new concept file and replace the unaccepted image before code work begins.

- [ ] **Step 3: Write the visual ledger from the accepted image**

`xianzhi-v1-visual-ledger.md` records exact values chosen from the concept, including tokens with these stable names:

```text
--color-bg, --color-surface, --color-primary, --color-primary-pressed,
--color-text, --color-muted, --color-urgent, --color-week, --color-normal,
--radius-sm, --radius-md, --radius-lg, --space-1 through --space-8,
--font-title, --font-section, --font-body, --font-caption
```

It also lists the approved above-the-fold copy in order and an icon inventory for camera, album, flash, back, edit, delete, storage, calendar, and notification.

- [ ] **Step 4: Verify the concept asset and ledger are complete**

Run:

```powershell
Get-Item docs\design\xianzhi-v1-concept.png | Select-Object FullName,Length
rg -n -- '--color-bg|above-the-fold|camera|notification' docs\design\xianzhi-v1-visual-ledger.md
```

Expected: PNG exists and is non-empty; ledger includes visual tokens, copy inventory, and all required icons.

- [ ] **Step 5: Commit**

```powershell
git add docs/design
git commit -m "design: approve xianzhi mini program concept"
```

---

### Task 2: 原生小程序脚手架、会话与请求层

**Files:**
- Create: `miniprogram/project.config.json`
- Create: `miniprogram/project.private.config.json.example`
- Create: `miniprogram/package.json`
- Create: `miniprogram/package-lock.json`
- Create: `miniprogram/tsconfig.json`
- Create: `miniprogram/eslint.config.mjs`
- Create: `miniprogram/app.ts`
- Create: `miniprogram/app.json`
- Create: `miniprogram/app.wxss`
- Create: `miniprogram/services/http.ts`
- Create: `miniprogram/services/api.ts`
- Create: `miniprogram/store/session.ts`
- Create: `miniprogram/types/api.ts`
- Create: `miniprogram/tests/http.test.ts`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `request<T>(options: RequestOptions) -> Promise<T>`.
- Produces: `loginWithWechat() -> Promise<Session>` and `getAccessToken() -> string | null`.
- Produces: typed methods `listFoods`, `getFood`, `downloadFoodThumbnail`, `createManualFood`, `createScanSession`, `uploadFrame`, `getScanSession`, `finalizeScan`, `updateFood`, `deleteFood`, and `recordReminderSubscription`.
- Consumes: backend `/api/v1` contracts from Plans 01–02.

- [ ] **Step 1: Write failing HTTP behavior tests**

```typescript
it('adds bearer token and idempotency key', async () => {
  wxRequestMock.mockResolvedValue({ statusCode: 201, data: { id: 7 } })
  await request({ method: 'POST', path: '/foods/manual', data: {}, idempotencyKey: 'food-1' })
  expect(wxRequestMock).toHaveBeenCalledWith(expect.objectContaining({
    header: expect.objectContaining({ Authorization: 'Bearer token-1', 'Idempotency-Key': 'food-1' }),
  }))
})

it('maps backend error envelopes', async () => {
  wxRequestMock.mockResolvedValue({ statusCode: 503, data: { error: { code: 'queue_unavailable', message: '识别服务暂时不可用', retryable: true } } })
  await expect(request({ method: 'GET', path: '/health/ready' })).rejects.toMatchObject({ code: 'queue_unavailable', retryable: true })
})
```

- [ ] **Step 2: Run tests and verify missing module failure**

Run:

```powershell
. .\scripts\env.ps1
Push-Location miniprogram
npm install
npm test -- --run tests/http.test.ts
Pop-Location
```

Expected: import failure for `services/http`.

- [ ] **Step 3: Implement app shell, exact design tokens, session storage, and typed API**

`project.config.json` uses `miniprogramRoot: "./"`, `compileType: "miniprogram"`, and `appid: "touristappid"`; real AppID belongs in ignored `project.private.config.json`. `app.wxss` copies the accepted ledger tokens exactly and explicitly sets typography for buttons, inputs, tabs, and labels.

`package.json` defines exact scripts `"test": "vitest"`, `"typecheck": "tsc --noEmit"`, `"lint": "eslint ."`, and commits the npm-generated lockfile. Development dependencies include TypeScript, Vitest, ESLint, `typescript-eslint`, and `miniprogram-api-typings`; no runtime UI framework is added.

`app.ts` calls `wx.login`, posts the code, stores only the app Token and expiry using `wx.setStorageSync`, and retries login once on backend `401`. Mock development uses code `demo-user` only when the backend base URL is localhost. `downloadFoodThumbnail` calls `wx.downloadFile` with the bearer header and caches only its temporary local path for the current session; food JSON never exposes server storage paths.

- [ ] **Step 4: Run tests, type check, and WeChat CLI compile**

Run:

```powershell
Push-Location miniprogram
npm test -- --run
npm run typecheck
npm run lint
& 'D:\微信web开发者工具\cli.bat' build-npm --project $PWD.Path
Pop-Location
```

Expected: tests, typecheck, lint, and build-npm exit 0.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore miniprogram
git commit -m "feat: scaffold native mini program client"
```

---

### Task 3: 首页、食品卡片、筛选与详情管理

**Files:**
- Create: `miniprogram/domain/freshness.ts`
- Create: `miniprogram/components/food-card/index.ts`
- Create: `miniprogram/components/food-card/index.json`
- Create: `miniprogram/components/food-card/index.wxml`
- Create: `miniprogram/components/food-card/index.wxss`
- Create: `miniprogram/pages/home/index.ts`
- Create: `miniprogram/pages/home/index.json`
- Create: `miniprogram/pages/home/index.wxml`
- Create: `miniprogram/pages/home/index.wxss`
- Create: `miniprogram/pages/food-detail/index.ts`
- Create: `miniprogram/pages/food-detail/index.json`
- Create: `miniprogram/pages/food-detail/index.wxml`
- Create: `miniprogram/pages/food-detail/index.wxss`
- Modify: `miniprogram/app.json`
- Test: `miniprogram/tests/freshness.test.ts`

**Interfaces:**
- Produces: `freshnessPresentation(consumeBy: string, today: string) -> { bucket, days, label, tone }`.
- Produces: Home filters `all/urgent/this_week/normal` and clickable food cards.
- Produces: detail edit and soft-delete actions.
- Consumes: typed food API and accepted visual ledger.

- [ ] **Step 1: Write failing freshness presentation tests**

```typescript
it.each([
  [-1, 'expired', '已过期'], [0, 'urgent', '今天'], [1, 'urgent', '1天'],
  [2, 'this_week', '2天'], [7, 'this_week', '7天'], [8, 'normal', '8天'],
])('maps %s days to %s', (offset, bucket, label) => {
  expect(freshnessPresentation(addDays('2026-08-20', offset), '2026-08-20')).toMatchObject({ bucket, label })
})
```

- [ ] **Step 2: Run the focused test and verify missing function failure**

Run: `Push-Location miniprogram; npm test -- --run tests/freshness.test.ts; Pop-Location`

Expected: import failure for `domain/freshness`.

- [ ] **Step 3: Implement native components and real interactions**

Home above-the-fold copy stays in this order: `别让好食材被忘记`、`家里的新鲜`、`今天的小提醒`、`先吃掉{food}吧，正是好时候`. Empty state says `家里还没有记录的食材` and exposes `扫描第一样食材`.

Food cards show thumbnail, food name, storage label, consume-by date, and remaining label. Detail PATCH updates storage/date and refreshes calculation; delete uses a native confirmation dialog, calls DELETE once, then returns home and refreshes. Use production-quality inline SVG/icon assets or the chosen icon set; do not use emoji glyphs.

- [ ] **Step 4: Run tests and compile the two-page flow**

Run:

```powershell
Push-Location miniprogram
npm test -- --run tests/freshness.test.ts
npm run typecheck
npm run lint
& 'D:\微信web开发者工具\cli.bat' preview --project $PWD.Path --qr-format terminal
Pop-Location
```

Expected: tests and static checks pass; DevTools CLI produces a preview QR code.

- [ ] **Step 5: Commit**

```powershell
git add miniprogram
git commit -m "feat: add food home and detail experience"
```

---

### Task 4: 可测试的连续扫描状态机

**Files:**
- Create: `miniprogram/domain/scan-machine.ts`
- Create: `miniprogram/tests/scan-machine.test.ts`
- Create: `miniprogram/components/field-progress/index.ts`
- Create: `miniprogram/components/field-progress/index.json`
- Create: `miniprogram/components/field-progress/index.wxml`
- Create: `miniprogram/components/field-progress/index.wxss`

**Interfaces:**
- Produces: `ScanState` union and `scanReducer(state, event) -> ScanState`.
- Produces: events `STARTED`, `FRAME_CAPTURED`, `UPLOAD_SUCCEEDED`, `UPLOAD_FAILED`, `SESSION_UPDATED`, `RETRY`, `CANCELLED`.
- Produces: selectors `canCapture`, `progressItems`, `primaryGuidance`, `shouldNavigateToConfirm`.
- Consumes: backend scan session response types.

- [ ] **Step 1: Write failing state-transition tests**

```typescript
it('serializes capture and upload', () => {
  const uploading = scanReducer(scanningState(), { type: 'FRAME_CAPTURED', localPath: 'a.jpg' })
  expect(canCapture(uploading)).toBe(false)
  expect(() => scanReducer(uploading, { type: 'FRAME_CAPTURED', localPath: 'b.jpg' })).toThrow('frame_in_flight')
})

it('routes missing identity to targeted guidance', () => {
  const state = scanReducer(scanningState(), { type: 'SESSION_UPDATED', session: needsIdentitySession() })
  expect(primaryGuidance(state)).toBe('没有认出是什么，请对准商品正面继续扫描')
  expect(progressItems(state).find(item => item.key === 'food_name')?.status).toBe('active')
})

it('stops after four accepted frames', () => {
  expect(canCapture(scanningState({ acceptedFrames: 4 }))).toBe(false)
})
```

- [ ] **Step 2: Run tests and verify missing reducer failure**

Run: `Push-Location miniprogram; npm test -- --run tests/scan-machine.test.ts; Pop-Location`

Expected: import failure for `domain/scan-machine`.

- [ ] **Step 3: Implement the discriminated union and pure reducer**

States are `idle`, `starting`, `scanning`, `capturing`, `uploading`, `waiting_analysis`, `needs_input`, `ready`, `failed`, and `cancelled`. Events invalid for the current state throw `InvalidScanTransition`; retryable upload errors preserve `localPath`, while permanent image-quality errors return to `scanning` with a human message.

The progress component renders code-native chips for `商品名称`, `日期信息`, `保质期`, and `储存条件`, with `missing/active/found/conflict` states and no invented copy.

- [ ] **Step 4: Run reducer tests and coverage**

Run:

```powershell
Push-Location miniprogram
npm test -- --run tests/scan-machine.test.ts --coverage
npm run typecheck
Pop-Location
```

Expected: all transition tests pass and the reducer file has 100% branch coverage.

- [ ] **Step 5: Commit**

```powershell
git add miniprogram/domain miniprogram/components/field-progress miniprogram/tests/scan-machine.test.ts
git commit -m "feat: add continuous scan state machine"
```

---

### Task 5: 相机帧质量、自动关键帧与扫描页面

**Files:**
- Create: `miniprogram/utils/frame-quality.ts`
- Create: `miniprogram/tests/frame-quality.test.ts`
- Create: `miniprogram/pages/scan/index.ts`
- Create: `miniprogram/pages/scan/index.json`
- Create: `miniprogram/pages/scan/index.wxml`
- Create: `miniprogram/pages/scan/index.wxss`
- Modify: `miniprogram/app.json`

**Interfaces:**
- Produces: `assessFrame(sample: Uint8ClampedArray, width: number, height: number) -> { brightEnough, sharpEnough }`.
- Produces: `isStable(accelerationSamples) -> boolean`.
- Produces: full scan page using `CameraContext.onCameraFrame` and `takePhoto`.
- Consumes: scan reducer and scan APIs.

- [ ] **Step 1: Write failing frame sampling tests**

```typescript
it('rejects a dark rgba sample', () => {
  expect(assessFrame(solidRgba(32, 64, 64), 64, 64).brightEnough).toBe(false)
})

it('accepts a high-contrast label sample', () => {
  expect(assessFrame(checkerboardRgba(64, 64), 64, 64)).toEqual({ brightEnough: true, sharpEnough: true })
})

it('requires five stable accelerometer samples', () => {
  expect(isStable([{ x: 0.01, y: 0.02, z: 0.99 }, { x: 0.01, y: 0.02, z: 1.0 }, { x: 0.02, y: 0.02, z: 0.99 }, { x: 0.01, y: 0.01, z: 1.0 }, { x: 0.01, y: 0.02, z: 1.0 }])).toBe(true)
})
```

- [ ] **Step 2: Run tests and verify missing quality functions**

Run: `Push-Location miniprogram; npm test -- --run tests/frame-quality.test.ts; Pop-Location`

Expected: import failure for `utils/frame-quality`.

- [ ] **Step 3: Implement low-frequency sampling and the scan page**

Sample at most twice per second, use every eighth pixel in a maximum 64×64 region, and stop frame listening while capture/upload is active. Require five stable accelerometer samples before `takePhoto({ quality: 'high' })`. If `onCameraFrame` is unavailable, display `保持稳定，正在自动取景` and attempt one timed `takePhoto` after 1.2 seconds of stable acceleration.

The page contains the accepted camera overlay, current guidance, field chips, `n / 4 关键画面`, flash control, stop control, and `相册补充`. Camera denial shows two actions: `从相册选择` and `手动填写`.

After upload, poll `GET /scan-sessions/{id}` once per second with a 30-second ceiling. Timeout preserves the session and offers `继续等待` or `稍后再试`; it does not create a second session.

- [ ] **Step 4: Run tests, compile, and open the scanner in DevTools**

Run:

```powershell
Push-Location miniprogram
npm test -- --run tests/frame-quality.test.ts tests/scan-machine.test.ts
npm run typecheck
npm run lint
& 'D:\微信web开发者工具\cli.bat' open --project $PWD.Path
Pop-Location
```

Expected: tests and checks pass; DevTools opens the native scan page without WXML/WXSS compile errors.

- [ ] **Step 5: Commit**

```powershell
git add miniprogram
git commit -m "feat: add guided continuous scanner"
```

---

### Task 6: 识别确认、手动兜底与订阅授权

**Files:**
- Create: `miniprogram/pages/scan-confirm/index.ts`
- Create: `miniprogram/pages/scan-confirm/index.json`
- Create: `miniprogram/pages/scan-confirm/index.wxml`
- Create: `miniprogram/pages/scan-confirm/index.wxss`
- Create: `miniprogram/pages/manual-add/index.ts`
- Create: `miniprogram/pages/manual-add/index.json`
- Create: `miniprogram/pages/manual-add/index.wxml`
- Create: `miniprogram/pages/manual-add/index.wxss`
- Modify: `miniprogram/services/api.ts`
- Modify: `miniprogram/app.json`
- Create: `miniprogram/tests/confirm-form.test.ts`

**Interfaces:**
- Produces: validation function `validateConfirmedFood(form) -> ValidationResult`.
- Produces: finalize then subscription sequence.
- Produces: manual food creation fallback.
- Consumes: ready/needs_input scan session, two template IDs, food API.

- [ ] **Step 1: Write failing form and authorization-outcome tests**

```typescript
it('requires a date conflict choice', () => {
  expect(validateConfirmedFood(formWithDateConflict())).toEqual({ ok: false, field: 'dateConflictChoice', message: '请选择正确的包装日期' })
})

it('saves food when subscription is rejected', async () => {
  finalizeScanMock.mockResolvedValue({ food: { id: 9 } })
  requestSubscribeMessageMock.mockResolvedValue({ PRE_TEMPLATE: 'reject', DUE_TEMPLATE: 'reject' })
  await submitConfirmedFood(validForm())
  expect(finalizeScanMock).toHaveBeenCalledTimes(1)
  expect(saveSubscriptionMock).toHaveBeenCalledWith(9, { PRE_TEMPLATE: 'reject', DUE_TEMPLATE: 'reject' })
})
```

- [ ] **Step 2: Run focused tests and verify missing form module**

Run: `Push-Location miniprogram; npm test -- --run tests/confirm-form.test.ts; Pop-Location`

Expected: import failure for confirm form functions.

- [ ] **Step 3: Implement editable fields, evidence, conflict UI, finalize, and fallback**

Fields are name, category, brand, storage type, production date, declared expiry, shelf-life days, and consume-by date. Low-confidence fields show `请确认`; date conflicts show both values with their evidence labels. Submit order is: validate → finalize with one idempotency key → call `wx.requestSubscribeMessage` with the two template IDs → post authorization results → navigate to detail. If subscription call fails or is rejected, navigation still succeeds and detail shows `微信提醒未开启`. During this client plan the authorization endpoint is represented by the typed request and test fixture; Plan 04 Task 1 supplies the real backend route before final full-stack acceptance.

Manual add uses the same validation and display components but calls `/foods/manual`; it never manufactures AI confidence.

- [ ] **Step 4: Run all client tests and compile all pages**

Run:

```powershell
Push-Location miniprogram
npm test -- --run
npm run typecheck
npm run lint
& 'D:\微信web开发者工具\cli.bat' preview --project $PWD.Path --qr-format terminal
Pop-Location
```

Expected: all client tests and checks pass; preview QR code is produced.

- [ ] **Step 5: Commit**

```powershell
git add miniprogram
git commit -m "feat: confirm scans and handle manual fallback"
```

---

### Task 7: 视觉保真、交互与真机验收

**Files:**
- Modify: relevant `miniprogram/**/*.wxml`
- Modify: relevant `miniprogram/**/*.wxss`
- Modify: relevant `miniprogram/**/*.ts`
- Create: `docs/qa/miniprogram-v1-fidelity-ledger.md`
- Create: `docs/qa/miniprogram-v1-test-results.md`
- Create: `docs/qa/screenshots/` rendered implementation captures

**Interfaces:**
- Produces: verified implementation matching `docs/design/xianzhi-v1-concept.png`.
- Produces: evidence for desktop DevTools viewport and at least one real phone.
- Consumes: all client tasks and running Mock backend.

- [ ] **Step 1: Capture all required states before making fidelity fixes**

Use the frontend testing/debugging workflow with the available Browser/Windows tools and WeChat developer tools. Capture Home, scanning, targeted补扫, confirmation, detail, empty, loading, and error states. Record device model, viewport, base library version, backend commit, and screenshot path in the QA ledger.

- [ ] **Step 2: Compare against the accepted concept at concrete checkpoints**

The ledger must contain at least these comparisons: above-the-fold copy and order; first viewport balance; title/body/control typography; ivory/terracotta/status palette; card/container model; camera overlay; icon metaphor and stroke; spacing/radii; food image crop; responsive behavior. Each row records concept evidence, render evidence, mismatch, and fix.

- [ ] **Step 3: Fix every material mismatch and run functional interaction checks**

Verify real selected states and data changes for filters, food detail navigation, scanning progress, retry, manual fallback, form editing, subscription rejection, and delete confirmation. Respect reduced motion; fix clipping, overflow, accidental wrapping, browser-default control fonts, icon drift, and stale temporary assets.

- [ ] **Step 4: Run final client and DevTools verification**

Run:

```powershell
Push-Location miniprogram
npm test -- --run
npm run typecheck
npm run lint
& 'D:\微信web开发者工具\cli.bat' preview --project $PWD.Path --qr-format terminal
Pop-Location
```

On a real phone, execute: camera authorization accepted and rejected; packaged success; identity补扫; fresh produce; weak-network retry; album fallback; subscription accepted and rejected. Record pass/fail and screenshots in `miniprogram-v1-test-results.md`.

- [ ] **Step 5: Commit**

```powershell
git add miniprogram docs/qa
git commit -m "test: verify mini program fidelity and core flows"
```
