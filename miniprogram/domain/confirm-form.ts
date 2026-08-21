import type {
  Food,
  FoodCategory,
  ScanFinalizeInput,
  ScanFinalizeResponse,
  StorageType,
  SubscriptionOutcomes,
} from '../types/api'

export interface ConfirmedFoodForm {
  scanSessionId: string
  foodName: string
  brand: string
  category: FoodCategory | ''
  storageType: StorageType | ''
  productionDate: string
  declaredExpiryDate: string
  shelfLifeDays: string
  recommendedConsumeBy: string
  hasDateConflict: boolean
  dateConflictChoice: 'existing' | 'candidate' | ''
}

export type ValidationResult =
  | { ok: true; payload: ScanFinalizeInput }
  | { ok: false; field: keyof ConfirmedFoodForm; message: string }

export interface ConfirmationDependencies {
  finalize: (
    scanSessionId: string,
    payload: ScanFinalizeInput,
    idempotencyKey: string,
  ) => Promise<ScanFinalizeResponse>
  requestSubscription: () => Promise<SubscriptionOutcomes>
  saveSubscription: (foodId: number, outcomes: SubscriptionOutcomes) => Promise<void>
}

function optional(value: string): string | undefined {
  const normalized = value.trim()
  return normalized || undefined
}

export function validateConfirmedFood(form: ConfirmedFoodForm): ValidationResult {
  const foodName = form.foodName.trim()
  if (!foodName) return { ok: false, field: 'foodName', message: '请填写食材名称' }
  if (!form.storageType) return { ok: false, field: 'storageType', message: '请选择储存方式' }
  if (form.hasDateConflict && !form.dateConflictChoice) {
    return { ok: false, field: 'dateConflictChoice', message: '请选择正确的包装日期' }
  }
  if (form.productionDate && !form.shelfLifeDays) {
    return { ok: false, field: 'shelfLifeDays', message: '请填写包装上的保质期' }
  }
  const shelfLifeDays = form.shelfLifeDays ? Number(form.shelfLifeDays) : undefined
  if (shelfLifeDays !== undefined && (!Number.isInteger(shelfLifeDays) || shelfLifeDays < 0 || shelfLifeDays > 3650)) {
    return { ok: false, field: 'shelfLifeDays', message: '保质期天数不正确' }
  }
  const hasDateBasis = Boolean(
    form.declaredExpiryDate ||
    (form.productionDate && shelfLifeDays !== undefined) ||
    form.recommendedConsumeBy,
  )
  if (!hasDateBasis) {
    return { ok: false, field: 'recommendedConsumeBy', message: '请填写建议食用日期' }
  }
  return {
    ok: true,
    payload: {
      food_name: foodName,
      brand: optional(form.brand),
      category: form.category || undefined,
      storage_type: form.storageType,
      production_date: optional(form.productionDate),
      declared_expiry_date: optional(form.declaredExpiryDate),
      shelf_life_days: shelfLifeDays,
      recommended_consume_by: optional(form.recommendedConsumeBy),
      date_conflict_choice: form.dateConflictChoice || undefined,
    },
  }
}

export async function submitConfirmedFood(
  form: ConfirmedFoodForm,
  idempotencyKey: string,
  dependencies: ConfirmationDependencies,
): Promise<{ food: Food; remindersEnabled: boolean }> {
  const validation = validateConfirmedFood(form)
  if (!validation.ok) throw new Error(validation.message)
  const { food } = await dependencies.finalize(form.scanSessionId, validation.payload, idempotencyKey)
  try {
    const outcomes = await dependencies.requestSubscription()
    await dependencies.saveSubscription(food.id, outcomes)
    return { food, remindersEnabled: Object.values(outcomes).some((outcome) => outcome === 'accept') }
  } catch {
    return { food, remindersEnabled: false }
  }
}
