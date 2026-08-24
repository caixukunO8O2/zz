import {
  InvalidScanTransition,
  canCapture,
  captureControlsLocked,
  completeRecognitionAttempt,
  createRecognitionSequence,
  nextFlashMode,
  primaryGuidance,
  progressItems,
  scanReducer,
  scanningState,
  type RecognitionCaptureMode,
  type RecognitionFieldKey,
  type RecognitionSequence,
  type ScanState,
} from '../../domain/scan-machine'
import { cancelScanSession, createScanSession, getScanSession, uploadFrame } from '../../services/api'
import type { ImagePurpose } from '../../types/api'
import { assessFrame, isStable, type AccelerationSample } from '../../utils/frame-quality'

let machine: ScanState = scanningState()
let cameraContext: WechatMiniprogram.CameraContext | undefined
let frameListener: WechatMiniprogram.CameraFrameListener | undefined
let accelerationSamples: AccelerationSample[] = []
let accelerometerListener: WechatMiniprogram.OnAccelerometerChangeCallback | undefined
let pollTimer: ReturnType<typeof setTimeout> | undefined
let fallbackTimer: ReturnType<typeof setTimeout> | undefined
let lastFrameAt = 0
let takingPhoto = false
let pollStartedAt = 0
let sequence: RecognitionSequence | undefined
let currentAttempt: Exclude<RecognitionCaptureMode, 'complete'> = 'automatic'
let freshProduceMode = false
let lastCapturedPath = ''

const FIELD_COPY: Record<RecognitionFieldKey, { capture: string; automatic: string; targeted: string; purpose: ImagePurpose }> = {
  food_name: { capture: '拍商品正面', automatic: '请对准商品正面，系统正在识别名称', targeted: '名称未识别，请拍一张商品正面', purpose: 'identity' },
  date: { capture: '拍日期区域', automatic: '请对准生产日期或过期日期区域', targeted: '日期未识别，请拍一张日期区域', purpose: 'date' },
  shelf_life_days: { capture: '拍保质期', automatic: '请对准包装上的保质期说明', targeted: '保质期未识别，请拍一张保质期区域', purpose: 'date' },
  storage_type: { capture: '拍储存说明', automatic: '请对准冷藏、冷冻等储存说明', targeted: '储存条件未识别，请拍一张储存说明', purpose: 'storage' },
}

function sequenceGuidance(): string {
  if (freshProduceMode) return '请拍摄食材本体，系统会自动填写名称和分类'
  const activeKey = sequence?.activeKey
  if (!activeKey) return '关键信息已检查，请确认识别结果'
  return sequence?.captureMode === 'targeted' ? FIELD_COPY[activeKey].targeted : FIELD_COPY[activeKey].automatic
}

function activePurpose(): ImagePurpose {
  if (freshProduceMode) return 'identity'
  const activeKey = sequence?.activeKey
  return activeKey ? FIELD_COPY[activeKey].purpose : 'general'
}

Page({
  data: {
    guidance: '请先对准商品正面或完整食材',
    progress: progressItems(machine),
    acceptedFrames: 0,
    flash: 'off' as 'off' | 'torch',
    cameraDenied: false,
    timedOut: false,
    busy: false,
    canRetry: false,
    captureLabel: '拍商品正面',
    recognitionStep: 1,
    targetedCapture: false,
    freshProduceMode: false,
    analysisFailed: false,
    captureLocked: true,
  },

  onLoad() {
    machine = scanningState()
    sequence = undefined
    freshProduceMode = false
    currentAttempt = 'automatic'
    lastCapturedPath = ''
    void this.startSession()
  },

  onUnload() {
    this.stopSensors()
    if (pollTimer) clearTimeout(pollTimer)
  },

  async startSession() {
    this.setData({ busy: true })
    try {
      const session = await createScanSession()
      machine = scanReducer({ ...machine, kind: 'starting' }, { type: 'STARTED', session })
      sequence = createRecognitionSequence(session)
      this.renderMachine()
      this.startSensors()
    } catch (error) {
      wx.showModal({
        title: '暂时无法开始扫描',
        content: error instanceof Error ? error.message : '请检查网络后重试',
        confirmText: '重试',
        cancelText: '返回',
        success: (result) => result.confirm ? void this.startSession() : wx.navigateBack(),
      })
    } finally {
      this.setData({ busy: false })
    }
  },

  renderMachine() {
    const activeKey = sequence?.activeKey
    const machineBusy = ['starting', 'uploading', 'waiting_analysis'].includes(machine.kind)
    const captureLocked = captureControlsLocked(machine, takingPhoto)
    this.setData({
      guidance: machineBusy || ['failed', 'analysis_failed'].includes(machine.kind) ? primaryGuidance(machine) : sequenceGuidance(),
      progress: progressItems(machine, sequence),
      acceptedFrames: machine.acceptedFrames,
      busy: machineBusy || (!canCapture(machine, true) && !['failed', 'cancelled'].includes(machine.kind)),
      canRetry: machine.kind === 'failed' && machine.retryable,
      captureLabel: machine.kind === 'uploading'
        ? '上传中…'
        : machine.kind === 'waiting_analysis'
          ? '识别中…'
          : freshProduceMode
            ? '拍摄食材本体'
            : (activeKey ? FIELD_COPY[activeKey].capture : '识别完成'),
      recognitionStep: activeKey ? ['food_name', 'date', 'shelf_life_days', 'storage_type'].indexOf(activeKey) + 1 : 4,
      targetedCapture: sequence?.captureMode === 'targeted',
      freshProduceMode,
      analysisFailed: machine.kind === 'analysis_failed',
      captureLocked,
    })
  },

  startSensors() {
    cameraContext = wx.createCameraContext()
    accelerometerListener = (sample) => {
      accelerationSamples.push({ x: sample.x, y: sample.y, z: sample.z })
      accelerationSamples = accelerationSamples.slice(-5)
      if (!wx.canIUse('CameraContext.onCameraFrame') && isStable(accelerationSamples) && this.canTakeAutomaticFrame() && !fallbackTimer) {
        this.setData({ guidance: '保持稳定，正在自动取景' })
        fallbackTimer = setTimeout(() => {
          fallbackTimer = undefined
          this.takeAutomaticPhoto()
        }, 1200)
      }
    }
    wx.startAccelerometer({ interval: 'game' })
    wx.onAccelerometerChange(accelerometerListener)

    if (wx.canIUse('CameraContext.onCameraFrame')) {
      frameListener = cameraContext.onCameraFrame((frame) => {
        const now = Date.now()
        if (now - lastFrameAt < 500 || !this.canTakeAutomaticFrame() || takingPhoto) return
        lastFrameAt = now
        const assessment = assessFrame(new Uint8ClampedArray(frame.data), frame.width, frame.height)
        if (!assessment.brightEnough) {
          this.setData({ guidance: '画面有点暗，请移到光线更好的地方' })
          return
        }
        if (!assessment.sharpEnough) {
          this.setData({ guidance: '请靠近一点，并保持包装文字清晰' })
          return
        }
        if (isStable(accelerationSamples)) this.takeAutomaticPhoto()
      })
      frameListener.start()
    }
  },

  stopSensors() {
    frameListener?.stop()
    frameListener = undefined
    if (accelerometerListener) wx.offAccelerometerChange()
    accelerometerListener = undefined
    wx.stopAccelerometer()
    if (fallbackTimer) clearTimeout(fallbackTimer)
    fallbackTimer = undefined
  },

  canTakeAutomaticFrame() {
    return !freshProduceMode && sequence?.captureMode === 'automatic' && canCapture(machine, true)
  },

  takeAutomaticPhoto() {
    this.capturePhoto('automatic')
  },

  takePhoto() {
    const attempt = sequence?.captureMode === 'targeted' || freshProduceMode ? 'targeted' : 'automatic'
    this.capturePhoto(attempt)
  },

  capturePhoto(attempt: Exclude<RecognitionCaptureMode, 'complete'>) {
    if (!cameraContext || captureControlsLocked(machine, takingPhoto)) return
    takingPhoto = true
    this.renderMachine()
    currentAttempt = attempt
    cameraContext.takePhoto({
      quality: 'high',
      success: (result) => {
        takingPhoto = false
        this.acceptLocalFrame(result.tempImagePath, attempt)
      },
      fail: () => {
        takingPhoto = false
        this.renderMachine()
        wx.showToast({ title: '没有拍到清晰画面，请再试一次', icon: 'none' })
      },
    })
  },

  acceptLocalFrame(localPath: string, attempt: Exclude<RecognitionCaptureMode, 'complete'> = 'targeted') {
    try {
      currentAttempt = attempt
      lastCapturedPath = localPath
      machine = scanReducer(machine, { type: 'FRAME_CAPTURED', localPath })
      this.renderMachine()
      void this.uploadLocalFrame(localPath)
    } catch (error) {
      if (!(error instanceof InvalidScanTransition)) throw error
    }
  },

  async uploadLocalFrame(localPath: string) {
    const sessionId = machine.session?.id
    if (!sessionId) return
    try {
      const frame = await uploadFrame(
        sessionId,
        localPath,
        activePurpose(),
        `frame-${sessionId}-${machine.acceptedFrames + 1}`,
      )
      machine = scanReducer(machine, { type: 'UPLOAD_SUCCEEDED', duplicate: frame.duplicate })
      this.renderMachine()
      this.beginPolling()
    } catch (error) {
      const clientError = error as { retryable?: boolean; message?: string }
      machine = scanReducer(machine, {
        type: 'UPLOAD_FAILED',
        retryable: clientError.retryable ?? true,
        message: clientError.message ?? '关键画面上传失败',
      })
      this.renderMachine()
    }
  },

  beginPolling() {
    pollStartedAt = Date.now()
    this.setData({ timedOut: false })
    void this.pollSession()
  },

  async pollSession() {
    const sessionId = machine.session?.id
    if (!sessionId) return
    if (Date.now() - pollStartedAt >= 30_000) {
      this.setData({ timedOut: true, busy: false })
      return
    }
    try {
      const session = await getScanSession(sessionId)
      machine = scanReducer(machine, { type: 'SESSION_UPDATED', session })
      this.renderMachine()
      if (['waiting_analysis', 'scanning'].includes(machine.kind)) {
        pollTimer = setTimeout(() => void this.pollSession(), 1000)
        return
      }
      if (machine.kind === 'analysis_failed') return
      this.finishCurrentRecognition(session)
    } catch {
      pollTimer = setTimeout(() => void this.pollSession(), 1000)
    }
  },

  finishCurrentRecognition(session: import('../../types/api').ScanSession) {
    if (freshProduceMode) {
      const manualFields: RecognitionFieldKey[] = []
      if (!session.detected_fields.food_name) manualFields.push('food_name')
      if (!session.detected_fields.storage_type) manualFields.push('storage_type')
      this.openConfirmation(manualFields, true)
      return
    }
    if (!sequence) return
    sequence = completeRecognitionAttempt(sequence, session, currentAttempt)
    this.renderMachine()
    if (sequence.captureMode === 'complete') this.openConfirmation(sequence.manualFields, false)
  },

  openConfirmation(manualFields: RecognitionFieldKey[], fresh: boolean) {
    const sessionId = machine.session?.id
    if (!sessionId) return
    this.stopSensors()
    if (pollTimer) clearTimeout(pollTimer)
    if (lastCapturedPath) wx.setStorageSync(`scan-preview:${sessionId}`, lastCapturedPath)
    const manual = encodeURIComponent(manualFields.join(','))
    wx.redirectTo({ url: `/pages/scan-confirm/index?id=${sessionId}&manual=${manual}&fresh=${fresh ? '1' : '0'}` })
  },

  continueWaiting() {
    this.beginPolling()
  },

  retryUpload() {
    if (machine.kind !== 'failed') return
    machine = scanReducer(machine, { type: 'RETRY' })
    this.renderMachine()
    if (machine.kind === 'uploading') void this.uploadLocalFrame(machine.localPath)
  },

  chooseFromAlbum() {
    if (captureControlsLocked(machine, takingPhoto)) return
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      sizeType: ['compressed'],
      success: (result) => this.acceptLocalFrame(result.tempFiles[0].tempFilePath, 'targeted'),
    })
  },

  startFreshProduce() {
    if (takingPhoto || ['uploading', 'waiting_analysis'].includes(machine.kind)) return
    freshProduceMode = true
    sequence = undefined
    this.renderMachine()
    wx.showToast({ title: '请拍摄食材本体', icon: 'none' })
  },

  returnToPackagedScan() {
    if (takingPhoto || ['uploading', 'waiting_analysis'].includes(machine.kind)) return
    const session = machine.session
    if (!session) return
    freshProduceMode = false
    sequence = createRecognitionSequence(session)
    this.renderMachine()
  },

  toggleFlash() {
    this.setData({ flash: nextFlashMode(this.data.flash) })
  },

  cameraError(event: WechatMiniprogram.CameraError) {
    const denied = String(event.detail.errMsg).includes('auth') || String(event.detail.errMsg).includes('permission')
    this.setData({ cameraDenied: denied })
    if (denied) this.stopSensors()
  },

  openManual() {
    const sessionId = machine.session?.id ?? ''
    wx.redirectTo({ url: `/pages/manual-add/index?scanSessionId=${sessionId}` })
  },

  async stopScan() {
    const sessionId = machine.session?.id
    try {
      if (sessionId) await cancelScanSession(sessionId)
    } finally {
      machine = scanReducer(machine, { type: 'CANCELLED' })
      wx.navigateBack()
    }
  },
})
