import { downloadFoodThumbnail, listFoods } from '../../services/api'
import { freshnessPresentation } from '../../domain/freshness'
import { emptyStateFor, filterByFreshness, type HomeFilter } from '../../domain/home-state'
import type { Food } from '../../types/api'

interface FoodView extends Food {
  days: number
  remainingLabel: string
  storageLabel: string
  thumbnailPath: string
  tone: string
}

const FILTERS: Array<{ key: HomeFilter; label: string }> = [
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
    selectedFilter: 'all' as HomeFilter,
    allFoods: [] as FoodView[],
    foods: [] as FoodView[],
    totalFoodCount: 0,
    emptyState: emptyStateFor(0, 'all'),
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
      const response = await listFoods()
      const allFoods = response.items.map(present)
      this.applyFilter(allFoods)
      this.setData({ loading: false })
      await Promise.all(allFoods.map(async (food) => {
        if (!food.thumbnail_url) return
        try {
          food.thumbnailPath = await downloadFoodThumbnail(food.id)
        } catch {
          // The food remains usable when its optional image cannot be downloaded.
        }
      }))
      this.applyFilter(allFoods)
      this.setData({ heroImage: allFoods.find((food) => food.thumbnailPath)?.thumbnailPath ?? '' })
    } catch (error) {
      const message = error instanceof Error ? error.message : '暂时没有拿到食材列表'
      this.setData({ loading: false, errorMessage: message })
    }
  },

  applyFilter(allFoods?: FoodView[]) {
    const completeFoods = allFoods ?? this.data.allFoods
    const selected = this.data.selectedFilter as HomeFilter
    const foods = filterByFreshness(completeFoods, selected)
    this.setData({
      allFoods: completeFoods,
      foods,
      totalFoodCount: completeFoods.length,
      emptyState: emptyStateFor(completeFoods.length, selected),
      reminder: foods.find((item) => item.days >= 0) ?? null,
    })
  },

  selectFilter(event: WechatMiniprogram.TouchEvent) {
    const selectedFilter = event.currentTarget.dataset.key as HomeFilter
    if (selectedFilter === this.data.selectedFilter) return
    this.setData({ selectedFilter }, () => this.applyFilter())
  },

  openFood(event: WechatMiniprogram.CustomEvent<{ id: number }>) {
    wx.navigateTo({ url: `/pages/food-detail/index?id=${event.detail.id}` })
  },

  startScan() {
    wx.navigateTo({ url: '/pages/scan/index' })
  },
})
