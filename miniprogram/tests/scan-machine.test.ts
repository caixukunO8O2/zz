import { describe, expect, it } from 'vitest'

import {
  InvalidScanTransition,
  canCapture,
  completeRecognitionAttempt,
  createRecognitionSequence,
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

  it('asks for one targeted photo before marking a missing field for manual entry', () => {
    const initial = createRecognitionSequence(session())
    expect(initial).toMatchObject({ activeKey: 'food_name', captureMode: 'automatic', manualFields: [] })

    const targeted = completeRecognitionAttempt(initial, session(), 'automatic')
    expect(targeted).toMatchObject({ activeKey: 'food_name', captureMode: 'targeted', manualFields: [] })

    const continued = completeRecognitionAttempt(targeted, session(), 'targeted')
    expect(continued).toMatchObject({ activeKey: 'date', captureMode: 'automatic', manualFields: ['food_name'] })
    expect(progressItems(scanningState({ session: session() }), continued).map(({ key, status }) => [key, status])).toEqual([
      ['food_name', 'manual'],
      ['date', 'active'],
      ['shelf_life_days', 'pending'],
      ['storage_type', 'pending'],
    ])
  })

  it('keeps already detected later fields green while advancing in field order', () => {
    const detected = session({
      detected_fields: {
        food_name: { value: '鲜牛奶', confidence: 0.96, source_image_id: 1, source_kind: 'vision', evidence_text: '鲜牛奶' },
        storage_type: { value: 'chilled', confidence: 0.9, source_image_id: 1, source_kind: 'ocr', evidence_text: '冷藏' },
      },
    })
    const sequence = createRecognitionSequence(detected)
    expect(sequence).toMatchObject({ activeKey: 'date', captureMode: 'automatic' })
    expect(progressItems(scanningState({ session: detected }), sequence).map(({ key, status }) => [key, status])).toEqual([
      ['food_name', 'found'],
      ['date', 'active'],
      ['shelf_life_days', 'pending'],
      ['storage_type', 'found'],
    ])
  })

  it('does not require a separate shelf-life value when an expiry date was identified', () => {
    const detected = session({
      detected_fields: {
        food_name: { value: '酸奶', confidence: 0.96, source_image_id: 1, source_kind: 'vision', evidence_text: '酸奶' },
        declared_expiry_date: { value: '2026-08-30', confidence: 0.9, source_image_id: 2, source_kind: 'ocr', evidence_text: '有效期至 2026-08-30' },
        storage_type: { value: 'chilled', confidence: 0.9, source_image_id: 3, source_kind: 'ocr', evidence_text: '冷藏' },
      },
    })
    const sequence = createRecognitionSequence(detected)
    expect(sequence.captureMode).toBe('complete')
    expect(progressItems(scanningState({ session: detected }), sequence).find((item) => item.key === 'shelf_life_days')?.status).toBe('not_required')
  })

  it('finishes only after every unresolved field has either been found or marked manual', () => {
    let sequence = createRecognitionSequence(session())
    for (const key of ['food_name', 'date', 'shelf_life_days', 'storage_type']) {
      expect(sequence.activeKey).toBe(key)
      sequence = completeRecognitionAttempt(sequence, session(), 'automatic')
      sequence = completeRecognitionAttempt(sequence, session(), 'targeted')
    }
    expect(sequence).toMatchObject({ activeKey: null, captureMode: 'complete' })
    expect(sequence.manualFields).toEqual(['food_name', 'date', 'shelf_life_days', 'storage_type'])
  })

  it('clears a red manual marker when a later photo identifies that earlier field', () => {
    const marked = {
      activeKey: 'date' as const,
      captureMode: 'automatic' as const,
      manualFields: ['food_name' as const],
    }
    const recovered = session({
      detected_fields: {
        food_name: { value: '牛肉', confidence: 0.9, source_image_id: 2, source_kind: 'vision', evidence_text: '牛肉' },
        production_date: { value: '2026-08-21', confidence: 0.9, source_image_id: 2, source_kind: 'ocr', evidence_text: '2026-08-21' },
      },
    })
    const next = completeRecognitionAttempt(marked, recovered, 'automatic')
    expect(next.manualFields).toEqual([])
    expect(progressItems(scanningState({ session: recovered }), next).find((item) => item.key === 'food_name')?.status).toBe('found')
  })

  it('increments only accepted non-duplicate frames and waits for analysis', () => {
    const uploading = scanReducer(scanningState({ acceptedFrames: 2 }), { type: 'FRAME_CAPTURED', localPath: 'a.jpg' })
    const waiting = scanReducer(uploading, { type: 'UPLOAD_SUCCEEDED', duplicate: false })
    expect(waiting).toMatchObject({ kind: 'waiting_analysis', acceptedFrames: 3 })
  })

  it('allows one automatic and one targeted frame for each of four fields', () => {
    expect(canCapture(scanningState({ acceptedFrames: 7 }))).toBe(true)
    expect(canCapture(scanningState({ acceptedFrames: 8 }))).toBe(false)
  })

  it('navigates only when backend analysis is ready', () => {
    const ready = scanReducer(scanningState(), { type: 'SESSION_UPDATED', session: session({ status: 'ready', missing_fields: [] }) })
    expect(shouldNavigateToConfirm(ready)).toBe(true)
    expect(canCapture(ready)).toBe(false)
    expect(canCapture(ready, true)).toBe(true)
  })

  it('allows cancellation without losing the backend session id', () => {
    const cancelled = scanReducer(scanningState({ session: session() }), { type: 'CANCELLED' })
    expect(cancelled).toMatchObject({ kind: 'cancelled', session: { id: 'scan-1' } })
  })
})
