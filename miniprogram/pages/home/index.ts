import { downloadFoodThumbnail, listFoods } from '../../services/api'
import { freshnessPresentation } from '../../domain/freshness'
import type { Food, FreshnessBucket } from '../../types/api'

type FilterKey = 'all' | Exclude<FreshnessBucket, 'expired'> | 'expired'

interface FoodView extends Food {
  days: number
  remainingLabel: string
  storageLabel: string
  thumbnailPath: string
  tone: string
}

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'urgent', label: '快到期' },
  { key: 'this_week', label: '本周' },
  { key: 'normal', label: '更安心' },
]

const STORAGE_LABELS = { room: '常温', chilled: '冷藏', frozen: '冷冻' } as const

function today(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function present(food: Food): FoodView {
  const freshness = freshnessPresentation(food.recommended_consume_by, today())
  return {
    ...food,
    days: freshness.days,
    remainingLabel: freshness.label,
    storageLabel: STORAGE_LABELS[food.storage_type],
    thumbnailPath: '',
    tone: freshness.tone,
  }
}

Page({
  data: {
    filters: FILTERS,
    selectedFilter: 'all' as FilterKey,
    foods: [] as FoodView[],
    reminder: null as FoodView | null,
    heroImage: '',
    loading: true,
    errorMessage: '',
  },

  onShow() {
    void this.loadFoods()
  },

  async loadFoods() {
    this.setData({ loading: true, errorMessage: '' })
    try {
      const selected = this.data.selectedFilter as FilterKey
      const response = await listFoods(selected === 'all' ? undefined : selected)
      const foods = response.items.map(present)
      this.setData({ foods, reminder: foods.find((item) => item.days >= 0) ?? null, loading: false })
      await Promise.all(foods.map(async (food, index) => {
        if (!food.thumbnail_url) return
        try {
          const thumbnailPath = await downloadFoodThumbnail(food.id)
          this.setData({ [`foods[${index}].thumbnailPath`]: thumbnailPath })
          if (index === 0) this.setData({ heroImage: thumbnailPath })
        } catch {
          // The food remains usable when its optional image cannot be downloaded.
        }
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : '暂时没有拿到食材列表'
      this.setData({ loading: false, errorMessage: message })
    }
  },

  selectFilter(event: WechatMiniprogram.TouchEvent) {
    const selectedFilter = event.currentTarget.dataset.key as FilterKey
    if (selectedFilter === this.data.selectedFilter) return
    this.setData({ selectedFilter })
    void this.loadFoods()
  },

  openFood(event: WechatMiniprogram.CustomEvent<{ id: number }>) {
    wx.navigateTo({ url: `/pages/food-detail/index?id=${event.detail.id}` })
  },

  startScan() {
    wx.navigateTo({ url: '/pages/scan/index' })
  },
})
