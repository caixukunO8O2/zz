import { deleteFood, downloadFoodThumbnail, getFood, updateFood } from '../../services/api'
import { freshnessPresentation } from '../../domain/freshness'
import type { Food, StorageType } from '../../types/api'

const STORAGE_OPTIONS: Array<{ label: string; value: StorageType }> = [
  { label: '常温', value: 'room' },
  { label: '冷藏', value: 'chilled' },
  { label: '冷冻', value: 'frozen' },
]

function today(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

Page({
  data: {
    foodId: 0,
    food: null as Food | null,
    thumbnailPath: '',
    storageLabel: '',
    remainingLabel: '',
    remainingTone: 'normal',
    editing: false,
    storageOptions: STORAGE_OPTIONS,
    storageIndex: 0,
    draftStorage: 'chilled' as StorageType,
    draftConsumeBy: '',
    loading: true,
    saving: false,
    errorMessage: '',
  },

  onLoad(query: Record<string, string | undefined>) {
    const foodId = Number(query.id)
    if (!Number.isInteger(foodId) || foodId <= 0) {
      this.setData({ loading: false, errorMessage: '没有找到这份食材' })
      return
    }
    this.setData({ foodId })
    void this.loadFood()
  },

  async loadFood() {
    this.setData({ loading: true, errorMessage: '' })
    try {
      const food = await getFood(this.data.foodId)
      const freshness = freshnessPresentation(food.recommended_consume_by, today())
      const storageIndex = Math.max(0, STORAGE_OPTIONS.findIndex((item) => item.value === food.storage_type))
      this.setData({
        food,
        storageLabel: STORAGE_OPTIONS[storageIndex].label,
        storageIndex,
        draftStorage: food.storage_type,
        draftConsumeBy: food.recommended_consume_by,
        remainingLabel: freshness.label,
        remainingTone: freshness.tone,
        loading: false,
      })
      if (food.thumbnail_url) {
        try {
          this.setData({ thumbnailPath: await downloadFoodThumbnail(food.id) })
        } catch {
          // Image absence does not block food management.
        }
      }
    } catch (error) {
      this.setData({ loading: false, errorMessage: error instanceof Error ? error.message : '加载失败' })
    }
  },

  goBack() {
    wx.navigateBack()
  },

  beginEdit() {
    this.setData({ editing: true })
  },

  cancelEdit() {
    const food = this.data.food
    if (!food) return
    const storageIndex = Math.max(0, STORAGE_OPTIONS.findIndex((item) => item.value === food.storage_type))
    this.setData({ editing: false, storageIndex, draftStorage: food.storage_type, draftConsumeBy: food.recommended_consume_by })
  },

  changeStorage(event: WechatMiniprogram.PickerChange) {
    const storageIndex = Number(event.detail.value)
    this.setData({ storageIndex, draftStorage: STORAGE_OPTIONS[storageIndex].value })
  },

  changeConsumeBy(event: WechatMiniprogram.PickerChange) {
    this.setData({ draftConsumeBy: String(event.detail.value) })
  },

  async saveEdit() {
    if (this.data.saving) return
    this.setData({ saving: true })
    try {
      await updateFood(this.data.foodId, {
        storage_type: this.data.draftStorage,
        recommended_consume_by: this.data.draftConsumeBy,
      })
      this.setData({ editing: false, saving: false })
      await this.loadFood()
      wx.showToast({ title: '已保存', icon: 'success' })
    } catch (error) {
      this.setData({ saving: false })
      wx.showToast({ title: error instanceof Error ? error.message : '保存失败', icon: 'none' })
    }
  },

  deleteFood() {
    wx.showModal({
      title: '删除这份食材？',
      content: '删除后不会再显示和提醒。',
      confirmText: '删除',
      confirmColor: '#D84A2B',
      success: (result) => {
        if (!result.confirm) return
        void this.confirmDelete()
      },
    })
  },

  async confirmDelete() {
    try {
      await deleteFood(this.data.foodId, `delete-${this.data.foodId}-${Date.now()}`)
      wx.showToast({ title: '已删除', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 350)
    } catch (error) {
      wx.showToast({ title: error instanceof Error ? error.message : '删除失败', icon: 'none' })
    }
  },
})
