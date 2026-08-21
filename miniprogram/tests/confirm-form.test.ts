import { describe, expect, it, vi } from 'vitest'

import { submitConfirmedFood, validateConfirmedFood, type ConfirmedFoodForm } from '../domain/confirm-form'
import type { Food, ScanFinalizeResponse } from '../types/api'

const FOOD: Food = {
  id: 9,
  food_name: '伊利鲜牛奶',
  brand: '伊利',
  category: 'dairy',
  thumbnail_url: null,
  production_date: '2026-08-18',
  declared_expiry_date: null,
  shelf_life_days: 7,
  storage_type: 'chilled',
  added_on: '2026-08-21',
  recommended_consume_by: '2026-08-25',
  date_basis: 'production_plus_shelf_life',
  freshness_bucket: 'urgent',
}

function validForm(overrides: Partial<ConfirmedFoodForm> = {}): ConfirmedFoodForm {
  return {
    scanSessionId: 'scan-1',
    foodName: '伊利鲜牛奶',
    brand: '伊利',
    category: 'dairy',
    storageType: 'chilled',
    productionDate: '2026-08-18',
    declaredExpiryDate: '',
    shelfLifeDays: '7',
    recommendedConsumeBy: '2026-08-25',
    hasDateConflict: false,
    dateConflictChoice: '',
    ...overrides,
  }
}

describe('confirmed food form', () => {
  it('requires an explicit choice when package dates conflict', () => {
    expect(validateConfirmedFood(validForm({ hasDateConflict: true }))).toEqual({
      ok: false,
      field: 'dateConflictChoice',
      message: '请选择正确的包装日期',
    })
  })

  it('requires a name, storage type, and a usable date basis', () => {
    expect(validateConfirmedFood(validForm({ foodName: '  ' }))).toMatchObject({ ok: false, field: 'foodName' })
    expect(validateConfirmedFood(validForm({ storageType: '' }))).toMatchObject({ ok: false, field: 'storageType' })
    expect(validateConfirmedFood(validForm({ productionDate: '', shelfLifeDays: '', recommendedConsumeBy: '' }))).toMatchObject({ ok: false, field: 'recommendedConsumeBy' })
  })

  it('rejects a production date without shelf life', () => {
    expect(validateConfirmedFood(validForm({ shelfLifeDays: '' }))).toEqual({
      ok: false,
      field: 'shelfLifeDays',
      message: '请填写包装上的保质期',
    })
  })

  it('saves the food when both reminder subscriptions are rejected', async () => {
    const calls: string[] = []
    const finalize = vi.fn(async (): Promise<ScanFinalizeResponse> => {
      calls.push('finalize')
      return { food: FOOD }
    })
    const requestSubscription = vi.fn(async () => {
      calls.push('subscribe')
      return { PRE_TEMPLATE: 'reject', DUE_TEMPLATE: 'reject' } as const
    })
    const saveSubscription = vi.fn(async () => {
      calls.push('save-outcomes')
    })

    const result = await submitConfirmedFood(validForm(), 'finalize-1', {
      finalize,
      requestSubscription,
      saveSubscription,
    })

    expect(result).toEqual({ food: FOOD, remindersEnabled: false })
    expect(calls).toEqual(['finalize', 'subscribe', 'save-outcomes'])
    expect(saveSubscription).toHaveBeenCalledWith(9, { PRE_TEMPLATE: 'reject', DUE_TEMPLATE: 'reject' })
  })

  it('returns the saved food if the WeChat subscription prompt itself fails', async () => {
    const result = await submitConfirmedFood(validForm(), 'finalize-2', {
      finalize: async () => ({ food: FOOD }),
      requestSubscription: async () => { throw new Error('requestSubscribeMessage:fail') },
      saveSubscription: async () => { throw new Error('must not be reached') },
    })

    expect(result).toEqual({ food: FOOD, remindersEnabled: false })
  })
})
