import { validateConfirmedFood, type ConfirmedFoodForm } from '../../domain/confirm-form'
import { createManualFood } from '../../services/api'
import type { FoodCategory, StorageType } from '../../types/api'

const STORAGE_OPTIONS: Array<{ label: string; value: StorageType }> = [
  { label: '常温', value: 'room' }, { label: '冷藏', value: 'chilled' }, { label: '冷冻', value: 'frozen' },
]
const CATEGORY_OPTIONS: Array<{ label: string; value: FoodCategory }> = [
  { label: '水果', value: 'fruit' }, { label: '蔬菜', value: 'vegetable' }, { label: '肉类', value: 'meat' }, { label: '乳制品', value: 'dairy' }, { label: '熟食', value: 'cooked' },
]

function today(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function initialForm(): ConfirmedFoodForm {
  return {
    scanSessionId: '', foodName: '', brand: '', category: '', storageType: '',
    productionDate: '', declaredExpiryDate: '', shelfLifeDays: '', recommendedConsumeBy: '',
    hasDateConflict: false, dateConflictChoice: '',
  }
}

Page({
  data: {
    form: initialForm(), storageOptions: STORAGE_OPTIONS, categoryOptions: CATEGORY_OPTIONS,
    storageIndex: 0, categoryIndex: 0, submitting: false,
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
  goBack() { wx.navigateBack() },
  async saveFood() {
    if (this.data.submitting) return
    const validation = validateConfirmedFood(this.data.form)
    if (!validation.ok) {
      wx.showToast({ title: validation.message, icon: 'none' })
      return
    }
    const payload = validation.payload
    if (!payload.food_name || !payload.storage_type) return
    this.setData({ submitting: true })
    try {
      const food = await createManualFood({
        food_name: payload.food_name,
        brand: payload.brand,
        category: payload.category,
        production_date: payload.production_date,
        declared_expiry_date: payload.declared_expiry_date,
        shelf_life_days: payload.shelf_life_days,
        storage_type: payload.storage_type,
        added_on: today(),
        recommended_consume_by: payload.recommended_consume_by,
      }, `manual-${Date.now()}`)
      wx.redirectTo({ url: `/pages/food-detail/index?id=${food.id}&reminders=off` })
    } catch (error) {
      wx.showToast({ title: error instanceof Error ? error.message : '添加失败', icon: 'none' })
      this.setData({ submitting: false })
    }
  },
})
