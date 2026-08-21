import { submitConfirmedFood, validateConfirmedFood, type ConfirmedFoodForm } from '../../domain/confirm-form'
import { finalizeScan, getScanSession, recordReminderSubscription } from '../../services/api'
import type { FoodCategory, StorageType, SubscriptionOutcome, SubscriptionOutcomes } from '../../types/api'

const PRE_TEMPLATE = 'PRE_TEMPLATE'
const DUE_TEMPLATE = 'DUE_TEMPLATE'
const STORAGE_OPTIONS: Array<{ label: string; value: StorageType }> = [
  { label: '常温保存', value: 'room' },
  { label: '冷藏保存', value: 'chilled' },
  { label: '冷冻保存', value: 'frozen' },
]
const CATEGORY_OPTIONS: Array<{ label: string; value: FoodCategory }> = [
  { label: '水果', value: 'fruit' },
  { label: '蔬菜', value: 'vegetable' },
  { label: '肉类', value: 'meat' },
  { label: '乳制品', value: 'dairy' },
  { label: '熟食', value: 'cooked' },
]

function emptyForm(scanSessionId: string): ConfirmedFoodForm {
  return {
    scanSessionId,
    foodName: '',
    brand: '',
    category: '',
    storageType: '',
    productionDate: '',
    declaredExpiryDate: '',
    shelfLifeDays: '',
    recommendedConsumeBy: '',
    hasDateConflict: false,
    dateConflictChoice: '',
  }
}

function valueOf(detected: Record<string, { value: string | number }>, key: string): string {
  const value = detected[key]?.value
  return value === undefined || value === null ? '' : String(value)
}

function requestSubscriptions(): Promise<SubscriptionOutcomes> {
  return new Promise((resolve, reject) => {
    wx.requestSubscribeMessage({
      tmplIds: [PRE_TEMPLATE, DUE_TEMPLATE],
      success: (result) => {
        const allowed = new Set<SubscriptionOutcome>(['accept', 'reject', 'ban', 'filter'])
        const outcomes: SubscriptionOutcomes = {}
        for (const templateId of [PRE_TEMPLATE, DUE_TEMPLATE]) {
          const outcome = result[templateId] as SubscriptionOutcome
          if (allowed.has(outcome)) outcomes[templateId] = outcome
        }
        resolve(outcomes)
      },
      fail: reject,
    })
  })
}

Page({
  data: {
    form: emptyForm(''),
    storageOptions: STORAGE_OPTIONS,
    categoryOptions: CATEGORY_OPTIONS,
    storageIndex: 0,
    categoryIndex: 0,
    conflicts: [] as Array<Record<string, unknown>>,
    lowConfidence: [] as string[],
    foodNameNeedsConfirmation: false,
    loading: true,
    submitting: false,
    errorMessage: '',
  },

  onLoad(query: Record<string, string | undefined>) {
    const scanSessionId = query.id ?? ''
    this.setData({ form: emptyForm(scanSessionId) })
    if (!scanSessionId) {
      this.setData({ loading: false, errorMessage: '没有找到本次扫描' })
      return
    }
    void this.loadSession(scanSessionId)
  },

  async loadSession(scanSessionId: string) {
    try {
      const session = await getScanSession(scanSessionId)
      const detected = session.detected_fields
      const storageType = valueOf(detected, 'storage_type') as StorageType | ''
      const category = valueOf(detected, 'category') as FoodCategory | ''
      const form: ConfirmedFoodForm = {
        scanSessionId,
        foodName: valueOf(detected, 'food_name'),
        brand: valueOf(detected, 'brand'),
        category,
        storageType,
        productionDate: valueOf(detected, 'production_date'),
        declaredExpiryDate: valueOf(detected, 'declared_expiry_date'),
        shelfLifeDays: valueOf(detected, 'shelf_life_days'),
        recommendedConsumeBy: '',
        hasDateConflict: session.conflicts.some((item) => item.field_name === 'declared_expiry_date'),
        dateConflictChoice: '',
      }
      const lowConfidence = Object.entries(detected)
        .filter(([, field]) => field.confidence < 0.75)
        .map(([key]) => key)
      this.setData({
        form,
        conflicts: session.conflicts,
        lowConfidence,
        foodNameNeedsConfirmation: lowConfidence.includes('food_name'),
        storageIndex: Math.max(0, STORAGE_OPTIONS.findIndex((item) => item.value === storageType)),
        categoryIndex: Math.max(0, CATEGORY_OPTIONS.findIndex((item) => item.value === category)),
        loading: false,
      })
    } catch (error) {
      this.setData({ loading: false, errorMessage: error instanceof Error ? error.message : '扫描结果加载失败' })
    }
  },

  inputField(event: WechatMiniprogram.Input<Record<string, never>, { field: keyof ConfirmedFoodForm }>) {
    this.setData({ [`form.${event.currentTarget.dataset.field}`]: event.detail.value })
  },

  chooseStorage(event: WechatMiniprogram.PickerChange) {
    const storageIndex = Number(event.detail.value)
    this.setData({ storageIndex, 'form.storageType': STORAGE_OPTIONS[storageIndex].value })
  },

  chooseCategory(event: WechatMiniprogram.PickerChange) {
    const categoryIndex = Number(event.detail.value)
    this.setData({ categoryIndex, 'form.category': CATEGORY_OPTIONS[categoryIndex].value })
  },

  chooseDate(event: WechatMiniprogram.PickerChange<Record<string, never>, { field: keyof ConfirmedFoodForm }>) {
    this.setData({ [`form.${event.currentTarget.dataset.field}`]: String(event.detail.value) })
  },

  chooseConflict(event: WechatMiniprogram.TouchEvent<Record<string, never>, { choice: 'existing' | 'candidate' }>) {
    this.setData({ 'form.dateConflictChoice': event.currentTarget.dataset.choice })
  },

  goBack() {
    wx.navigateBack()
  },

  async confirmFood() {
    if (this.data.submitting) return
    const validation = validateConfirmedFood(this.data.form)
    if (!validation.ok) {
      wx.showToast({ title: validation.message, icon: 'none' })
      return
    }
    this.setData({ submitting: true })
    try {
      const result = await submitConfirmedFood(
        this.data.form,
        `finalize-${this.data.form.scanSessionId}`,
        {
          finalize: finalizeScan,
          requestSubscription: requestSubscriptions,
          saveSubscription: recordReminderSubscription,
        },
      )
      wx.redirectTo({
        url: `/pages/food-detail/index?id=${result.food.id}&reminders=${result.remindersEnabled ? 'on' : 'off'}`,
      })
    } catch (error) {
      wx.showToast({ title: error instanceof Error ? error.message : '确认失败', icon: 'none' })
      this.setData({ submitting: false })
    }
  },
})
