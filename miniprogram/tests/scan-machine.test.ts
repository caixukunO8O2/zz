import { describe, expect, it } from 'vitest'

import {
  InvalidScanTransition,
  canCapture,
  nextFlashMode,
  primaryGuidance,
  progressItems,
  scanReducer,
  scanningState,
  shouldNavigateToConfirm,
} from '../domain/scan-machine'
import type { ScanSession } from '../types/api'

function session(overrides: Partial<ScanSession> = {}): ScanSession {
  return {
    id: 'scan-1',
    status: 'scanning',
    detected_fields: {},
    conflicts: [],
    missing_fields: ['food_name', 'date', 'storage_type'],
    next_guidance: '请先对准商品正面或完整食材',
    expires_at: '2026-08-21T12:00:00Z',
    images: [],
    ...overrides,
  }
}

describe('scanReducer', () => {
  it('toggles the camera torch for continuous scan lighting', () => {
    expect(nextFlashMode('off')).toBe('torch')
    expect(nextFlashMode('torch')).toBe('off')
  })

  it('serializes frame capture and upload', () => {
    const uploading = scanReducer(scanningState(), { type: 'FRAME_CAPTURED', localPath: 'a.jpg' })
    expect(canCapture(uploading)).toBe(false)
    expect(() => scanReducer(uploading, { type: 'FRAME_CAPTURED', localPath: 'b.jpg' })).toThrow(InvalidScanTransition)
  })

  it('preserves a local frame for retryable upload failures', () => {
    const uploading = scanReducer(scanningState(), { type: 'FRAME_CAPTURED', localPath: 'a.jpg' })
    const failed = scanReducer(uploading, { type: 'UPLOAD_FAILED', retryable: true, message: '网络不稳定' })
    expect(failed).toMatchObject({ kind: 'failed', localPath: 'a.jpg', retryable: true })
    expect(scanReducer(failed, { type: 'RETRY' })).toMatchObject({ kind: 'uploading', localPath: 'a.jpg' })
  })

  it('returns to scanning after a permanent image-quality rejection', () => {
    const uploading = scanReducer(scanningState(), { type: 'FRAME_CAPTURED', localPath: 'dark.jpg' })
    const next = scanReducer(uploading, { type: 'UPLOAD_FAILED', retryable: false, message: '画面太暗，请换个角度' })
    expect(next).toMatchObject({ kind: 'scanning', guidance: '画面太暗，请换个角度', acceptedFrames: 0 })
  })

  it('routes missing identity to targeted guidance and progress', () => {
    const next = scanReducer(scanningState(), {
      type: 'SESSION_UPDATED',
      session: session({ status: 'needs_input', missing_fields: ['food_name'], next_guidance: '没有认出是什么，请对准商品正面继续扫描' }),
    })
    expect(primaryGuidance(next)).toBe('没有认出是什么，请对准商品正面继续扫描')
    expect(progressItems(next).find((item) => item.key === 'food_name')?.status).toBe('active')
  })

  it('marks detected fields and date conflicts independently', () => {
    const next = scanReducer(scanningState(), {
      type: 'SESSION_UPDATED',
      session: session({
        status: 'needs_input',
        detected_fields: {
          food_name: { value: '鲜牛奶', confidence: 0.96, source_image_id: 1, source_kind: 'vision', evidence_text: '鲜牛奶' },
          declared_expiry_date: { value: '2026-08-25', confidence: 0.9, source_image_id: 2, source_kind: 'ocr', evidence_text: '有效期至 2026-08-25' },
        },
        conflicts: [{ field_name: 'declared_expiry_date' }],
        missing_fields: ['storage_type'],
        next_guidance: '请补充储存条件',
      }),
    })
    expect(progressItems(next).map(({ key, status }) => [key, status])).toEqual([
      ['food_name', 'found'],
      ['date', 'conflict'],
      ['shelf_life_days', 'missing'],
      ['storage_type', 'active'],
    ])
  })

  it('increments only accepted non-duplicate frames and waits for analysis', () => {
    const uploading = scanReducer(scanningState({ acceptedFrames: 2 }), { type: 'FRAME_CAPTURED', localPath: 'a.jpg' })
    const waiting = scanReducer(uploading, { type: 'UPLOAD_SUCCEEDED', duplicate: false })
    expect(waiting).toMatchObject({ kind: 'waiting_analysis', acceptedFrames: 3 })
  })

  it('stops capture after four accepted frames', () => {
    expect(canCapture(scanningState({ acceptedFrames: 4 }))).toBe(false)
  })

  it('navigates only when backend analysis is ready', () => {
    const ready = scanReducer(scanningState(), { type: 'SESSION_UPDATED', session: session({ status: 'ready', missing_fields: [] }) })
    expect(shouldNavigateToConfirm(ready)).toBe(true)
    expect(canCapture(ready)).toBe(false)
  })

  it('allows cancellation without losing the backend session id', () => {
    const cancelled = scanReducer(scanningState({ session: session() }), { type: 'CANCELLED' })
    expect(cancelled).toMatchObject({ kind: 'cancelled', session: { id: 'scan-1' } })
  })
})
