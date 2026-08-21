import {
  InvalidScanTransition,
  canCapture,
  primaryGuidance,
  progressItems,
  scanReducer,
  scanningState,
  shouldNavigateToConfirm,
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

function purposeFor(state: ScanState): ImagePurpose {
  const missing = state.session?.missing_fields ?? []
  if (missing.includes('food_name')) return 'identity'
  if (missing.some((field) => ['date', 'production_date', 'declared_expiry_date', 'shelf_life_days'].includes(field))) return 'date'
  if (missing.includes('storage_type')) return 'storage'
  return 'general'
}

Page({
  data: {
    guidance: '请先对准商品正面或完整食材',
    progress: progressItems(machine),
    acceptedFrames: 0,
    flash: 'off' as 'off' | 'on',
    cameraDenied: false,
    timedOut: false,
    busy: false,
    canRetry: false,
  },

  onLoad() {
    machine = scanningState()
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
    this.setData({
      guidance: primaryGuidance(machine),
      progress: progressItems(machine),
      acceptedFrames: machine.acceptedFrames,
      busy: !canCapture(machine) && !['failed', 'ready', 'cancelled'].includes(machine.kind),
      canRetry: machine.kind === 'failed' && machine.retryable,
    })
    if (shouldNavigateToConfirm(machine) && machine.session) {
      this.stopSensors()
      wx.redirectTo({ url: `/pages/scan-confirm/index?id=${machine.session.id}` })
    }
  },

  startSensors() {
    cameraContext = wx.createCameraContext()
    accelerometerListener = (sample) => {
      accelerationSamples.push({ x: sample.x, y: sample.y, z: sample.z })
      accelerationSamples = accelerationSamples.slice(-5)
      if (!wx.canIUse('CameraContext.onCameraFrame') && isStable(accelerationSamples) && canCapture(machine) && !fallbackTimer) {
        this.setData({ guidance: '保持稳定，正在自动取景' })
        fallbackTimer = setTimeout(() => {
          fallbackTimer = undefined
          this.takePhoto()
        }, 1200)
      }
    }
    wx.startAccelerometer({ interval: 'game' })
    wx.onAccelerometerChange(accelerometerListener)

    if (wx.canIUse('CameraContext.onCameraFrame')) {
      frameListener = cameraContext.onCameraFrame((frame) => {
        const now = Date.now()
        if (now - lastFrameAt < 500 || !canCapture(machine) || takingPhoto) return
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
        if (isStable(accelerationSamples)) this.takePhoto()
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

  takePhoto() {
    if (!cameraContext || takingPhoto || !canCapture(machine)) return
    takingPhoto = true
    cameraContext.takePhoto({
      quality: 'high',
      success: (result) => {
        takingPhoto = false
        this.acceptLocalFrame(result.tempImagePath)
      },
      fail: () => {
        takingPhoto = false
        wx.showToast({ title: '没有拍到清晰画面，请再试一次', icon: 'none' })
      },
    })
  },

  acceptLocalFrame(localPath: string) {
    try {
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
        purposeFor(machine),
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
      }
    } catch {
      pollTimer = setTimeout(() => void this.pollSession(), 1000)
    }
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
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      sizeType: ['compressed'],
      success: (result) => this.acceptLocalFrame(result.tempFiles[0].tempFilePath),
    })
  },

  toggleFlash() {
    this.setData({ flash: this.data.flash === 'off' ? 'on' : 'off' })
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
