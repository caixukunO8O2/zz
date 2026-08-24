import type { FreshnessBucket } from '../types/api'

export type HomeFilter = 'all' | FreshnessBucket

export interface HomeEmptyState {
  title: string
  body: string
  showFirstScanAction: boolean
}

const FILTER_EMPTY_TITLES: Record<Exclude<HomeFilter, 'all'>, string> = {
  urgent: '目前没有快到期的食材',
  this_week: '本周没有需要优先吃的食材',
  normal: '目前没有更安心的食材',
  expired: '目前没有已过期的食材',
}

export function filterByFreshness<T extends { freshness_bucket: FreshnessBucket }>(
  foods: T[],
  filter: HomeFilter,
): T[] {
  return filter === 'all' ? foods : foods.filter((food) => food.freshness_bucket === filter)
}

export function emptyStateFor(totalCount: number, filter: HomeFilter): HomeEmptyState {
  if (totalCount === 0) {
    return {
      title: '家里还没有记录的食材',
      body: '扫一下包装或完整食材，把新鲜日子记下来',
      showFirstScanAction: true,
    }
  }
  return {
    title: filter === 'all' ? '当前没有符合条件的食材' : FILTER_EMPTY_TITLES[filter],
    body: '其他食材还在对应分类里，换个分类看看',
    showFirstScanAction: false,
  }
}
