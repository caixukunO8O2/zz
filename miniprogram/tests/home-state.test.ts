import { describe, expect, it } from 'vitest'

import { emptyStateFor, filterByFreshness } from '../domain/home-state'

const foods = [
  { id: 1, freshness_bucket: 'this_week' as const },
]

describe('home list state', () => {
  it('keeps the total inventory while an active filter has no matches', () => {
    expect(filterByFreshness(foods, 'urgent')).toEqual([])
    expect(emptyStateFor(foods.length, 'urgent')).toEqual({
      title: '目前没有快到期的食材',
      body: '其他食材还在对应分类里，换个分类看看',
      showFirstScanAction: false,
    })
  })

  it('uses the first-food message only when the whole inventory is empty', () => {
    expect(emptyStateFor(0, 'all')).toEqual({
      title: '家里还没有记录的食材',
      body: '扫一下包装或完整食材，把新鲜日子记下来',
      showFirstScanAction: true,
    })
  })

  it('filters locally without dropping the complete inventory', () => {
    expect(filterByFreshness(foods, 'all')).toEqual(foods)
    expect(foods).toHaveLength(1)
  })
})
