import type { ScanSession } from '../types/api'

interface BaseState {
  acceptedFrames: number
  guidance: string
  session?: ScanSession
}

export type ScanState =
  | (BaseState & { kind: 'idle' })
  | (BaseState & { kind: 'starting' })
  | (BaseState & { kind: 'scanning' })
  | (BaseState & { kind: 'capturing' })
  | (BaseState & { kind: 'uploading'; localPath: string })
  | (BaseState & { kind: 'waiting_analysis' })
  | (BaseState & { kind: 'needs_input' })
  | (BaseState & { kind: 'ready'; session: ScanSession })
  | (BaseState & { kind: 'failed'; message: string; retryable: boolean; localPath?: string })
  | (BaseState & { kind: 'cancelled' })

export type ScanEvent =
  | { type: 'STARTED'; session: ScanSession }
  | { type: 'FRAME_CAPTURED'; localPath: string }
  | { type: 'UPLOAD_SUCCEEDED'; duplicate: boolean }
  | { type: 'UPLOAD_FAILED'; retryable: boolean; message: string }
  | { type: 'SESSION_UPDATED'; session: ScanSession }
  | { type: 'RETRY' }
  | { type: 'CANCELLED' }

export type RecognitionFieldKey = 'food_name' | 'date' | 'shelf_life_days' | 'storage_type'
export type ProgressStatus = 'missing' | 'pending' | 'active' | 'found' | 'manual' | 'not_required' | 'conflict'

export type RecognitionCaptureMode = 'automatic' | 'targeted' | 'complete'

export interface RecognitionSequence {
  activeKey: RecognitionFieldKey | null
  captureMode: RecognitionCaptureMode
  manualFields: RecognitionFieldKey[]
}

export interface ProgressItem {
  key: RecognitionFieldKey
  label: '商品名称' | '日期信息' | '保质期' | '储存条件'
  status: ProgressStatus
}

export class InvalidScanTransition extends Error {
  constructor(state: ScanState['kind'], event: ScanEvent['type']) {
    super(`invalid_scan_transition:${state}:${event}`)
    this.name = 'InvalidScanTransition'
  }
}

export type FlashMode = 'off' | 'torch'

export function nextFlashMode(current: FlashMode): FlashMode {
  return current === 'off' ? 'torch' : 'off'
}

const INITIAL_GUIDANCE = '请先对准商品正面或完整食材'

export function scanningState(overrides: Partial<Extract<ScanState, { kind: 'scanning' }>> = {}): Extract<ScanState, { kind: 'scanning' }> {
  return {
    kind: 'scanning',
    acceptedFrames: 0,
    guidance: INITIAL_GUIDANCE,
    ...overrides,
  }
}

function updateFromSession(state: ScanState, session: ScanSession): ScanState {
  const common = {
    acceptedFrames: state.acceptedFrames,
    guidance: session.next_guidance,
    session,
  }
  switch (session.status) {
    case 'scanning': return { kind: 'scanning', ...common }
    case 'analyzing': return { kind: 'waiting_analysis', ...common }
    case 'needs_input': return { kind: 'needs_input', ...common }
    case 'ready':
    case 'finalized': return { kind: 'ready', ...common }
    case 'cancelled': return { kind: 'cancelled', ...common }
    case 'failed': return { kind: 'failed', ...common, message: session.next_guidance || '识别没有完成，请重试', retryable: true }
  }
}

export function scanReducer(state: ScanState, event: ScanEvent): ScanState {
  if (event.type === 'CANCELLED' && state.kind !== 'cancelled') {
    return { kind: 'cancelled', acceptedFrames: state.acceptedFrames, guidance: state.guidance, session: state.session }
  }
  if (event.type === 'STARTED' && (state.kind === 'idle' || state.kind === 'starting')) {
    return updateFromSession(state, event.session)
  }
  if (event.type === 'FRAME_CAPTURED' && canCapture(state, true)) {
    return { ...state, kind: 'uploading', localPath: event.localPath }
  }
  if (event.type === 'UPLOAD_SUCCEEDED' && state.kind === 'uploading') {
    return {
      kind: 'waiting_analysis',
      acceptedFrames: state.acceptedFrames + (event.duplicate ? 0 : 1),
      guidance: '正在识别这张关键画面',
      session: state.session,
    }
  }
  if (event.type === 'UPLOAD_FAILED' && state.kind === 'uploading') {
    if (!event.retryable) {
      return {
        kind: 'scanning',
        acceptedFrames: state.acceptedFrames,
        guidance: event.message,
        session: state.session,
      }
    }
    return {
      kind: 'failed',
      acceptedFrames: state.acceptedFrames,
      guidance: event.message,
      message: event.message,
      retryable: true,
      localPath: state.localPath,
      session: state.session,
    }
  }
  if (event.type === 'SESSION_UPDATED' && !['idle', 'starting', 'cancelled'].includes(state.kind)) {
    return updateFromSession(state, event.session)
  }
  if (event.type === 'RETRY' && state.kind === 'failed' && state.retryable) {
    if (state.localPath) return { ...state, kind: 'uploading', localPath: state.localPath }
    return { kind: 'scanning', acceptedFrames: state.acceptedFrames, guidance: state.guidance, session: state.session }
  }
  throw new InvalidScanTransition(state.kind, event.type)
}

export function canCapture(state: ScanState, continueAfterReady = false): boolean {
  const captureState = state.kind === 'scanning'
    || state.kind === 'needs_input'
    || (continueAfterReady && state.kind === 'ready')
  return captureState && state.acceptedFrames < 8
}

const FIELD_ORDER: RecognitionFieldKey[] = ['food_name', 'date', 'shelf_life_days', 'storage_type']

function isFieldDetected(key: RecognitionFieldKey, session: ScanSession): boolean {
  const detected = session.detected_fields
  if (key === 'date') return Boolean(detected.production_date || detected.declared_expiry_date)
  return Boolean(detected[key])
}

function isNotRequired(key: RecognitionFieldKey, session: ScanSession): boolean {
  return key === 'shelf_life_days'
    && Boolean(session.detected_fields.declared_expiry_date)
    && !session.detected_fields.shelf_life_days
}

function nextUnresolvedField(
  session: ScanSession,
  manualFields: RecognitionFieldKey[],
): RecognitionFieldKey | null {
  return FIELD_ORDER.find((key) => (
    !manualFields.includes(key)
    && !isFieldDetected(key, session)
    && !isNotRequired(key, session)
  )) ?? null
}

export function createRecognitionSequence(session: ScanSession): RecognitionSequence {
  const activeKey = nextUnresolvedField(session, [])
  return {
    activeKey,
    captureMode: activeKey ? 'automatic' : 'complete',
    manualFields: [],
  }
}

export function completeRecognitionAttempt(
  sequence: RecognitionSequence,
  session: ScanSession,
  attempt: Exclude<RecognitionCaptureMode, 'complete'>,
): RecognitionSequence {
  const current = sequence.activeKey
  if (!current) return sequence
  const reconciledManualFields = sequence.manualFields.filter((key) => (
    !isFieldDetected(key, session) && !isNotRequired(key, session)
  ))
  if (isFieldDetected(current, session) || isNotRequired(current, session)) {
    const activeKey = nextUnresolvedField(session, reconciledManualFields)
    return {
      activeKey,
      captureMode: activeKey ? 'automatic' : 'complete',
      manualFields: reconciledManualFields,
    }
  }
  if (attempt === 'automatic') return { ...sequence, captureMode: 'targeted', manualFields: reconciledManualFields }
  const manualFields = [...reconciledManualFields, current]
  const activeKey = nextUnresolvedField(session, manualFields)
  return {
    activeKey,
    captureMode: activeKey ? 'automatic' : 'complete',
    manualFields,
  }
}

function statusFor(
  key: ProgressItem['key'],
  state: ScanState,
): ProgressStatus {
  const session = state.session
  if (!session) return 'missing'
  const detected = session.detected_fields
  const isDate = key === 'date'
  const conflictNames = isDate
    ? ['production_date', 'declared_expiry_date', 'date']
    : [key]
  if (session.conflicts.some((item) => conflictNames.includes(String(item.field_name)))) return 'conflict'
  const found = isDate
    ? Boolean(detected.production_date || detected.declared_expiry_date)
    : Boolean(detected[key])
  if (found) return 'found'
  const missingNames = isDate ? ['date', 'production_date', 'declared_expiry_date'] : [key]
  if (state.kind === 'needs_input' && session.missing_fields.some((name) => missingNames.includes(name))) return 'active'
  return 'missing'
}

export function progressItems(state: ScanState, sequence?: RecognitionSequence): ProgressItem[] {
  const items: Array<Omit<ProgressItem, 'status'>> = [
    { key: 'food_name', label: '商品名称' },
    { key: 'date', label: '日期信息' },
    { key: 'shelf_life_days', label: '保质期' },
    { key: 'storage_type', label: '储存条件' },
  ]
  return items.map((item) => {
    if (!sequence || !state.session) return { ...item, status: statusFor(item.key, state) }
    const backendStatus = statusFor(item.key, state)
    let status: ProgressStatus = 'pending'
    if (backendStatus === 'conflict') status = 'conflict'
    else if (backendStatus === 'found') status = 'found'
    else if (isNotRequired(item.key, state.session)) status = 'not_required'
    else if (sequence.manualFields.includes(item.key)) status = 'manual'
    else if (sequence.activeKey === item.key) status = 'active'
    return { ...item, status }
  })
}

export function primaryGuidance(state: ScanState): string {
  if (state.kind === 'uploading') return '正在上传关键画面'
  if (state.kind === 'waiting_analysis') return '正在识别这张关键画面'
  if (state.kind === 'failed') return state.message
  return state.guidance
}

export function shouldNavigateToConfirm(state: ScanState): boolean {
  return state.kind === 'ready'
}
