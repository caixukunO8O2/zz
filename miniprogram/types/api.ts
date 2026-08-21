export type StorageType = 'room' | 'chilled' | 'frozen'
export type FoodCategory = 'fruit' | 'vegetable' | 'meat' | 'dairy' | 'cooked'
export type FreshnessBucket = 'expired' | 'urgent' | 'this_week' | 'normal'
export type DateBasis =
  | 'declared_expiry'
  | 'production_plus_shelf_life'
  | 'knowledge_base_estimate'
  | 'manual_user_set'

export interface Session {
  accessToken: string
  expiresAt: number
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
}

export interface Food {
  id: number
  food_name: string
  brand: string | null
  category: string | null
  thumbnail_url: string | null
  production_date: string | null
  declared_expiry_date: string | null
  shelf_life_days: number | null
  storage_type: StorageType
  added_on: string
  recommended_consume_by: string
  date_basis: DateBasis
  freshness_bucket: FreshnessBucket
}

export interface FoodList {
  items: Food[]
}

export interface FoodManualCreate {
  food_name: string
  brand?: string | null
  category?: FoodCategory | null
  production_date?: string | null
  declared_expiry_date?: string | null
  shelf_life_days?: number | null
  storage_type: StorageType
  added_on: string
  recommended_consume_by?: string | null
}

export interface FoodPatch {
  food_name?: string
  brand?: string | null
  category?: FoodCategory | null
  production_date?: string | null
  declared_expiry_date?: string | null
  shelf_life_days?: number | null
  storage_type?: StorageType
  added_on?: string
  recommended_consume_by?: string | null
}

export type ScanStatus =
  | 'scanning'
  | 'analyzing'
  | 'needs_input'
  | 'ready'
  | 'finalized'
  | 'cancelled'
  | 'failed'

export type ImagePurpose = 'general' | 'identity' | 'date' | 'storage'
export type MockScenario = 'packaged_success' | 'needs_identity' | 'fresh_produce'

export interface DetectedField<T = string | number> {
  value: T
  confidence: number
  source_image_id: number | null
  source_kind: 'ocr' | 'vision' | 'user'
  evidence_text: string
}

export interface ScanImage {
  id: number
  purpose: ImagePurpose
  analysis_status: string
}

export interface ScanFrame extends ScanImage {
  duplicate: boolean
}

export interface ScanSession {
  id: string
  status: ScanStatus
  detected_fields: Record<string, DetectedField>
  conflicts: Array<Record<string, unknown>>
  missing_fields: string[]
  next_guidance: string
  expires_at: string
  images: ScanImage[]
}

export interface ScanSessionCreate {
  mock_scenario?: MockScenario
}

export interface ScanFinalizeInput {
  food_name?: string
  brand?: string | null
  category?: FoodCategory | null
  production_date?: string | null
  declared_expiry_date?: string | null
  shelf_life_days?: number | null
  storage_type?: StorageType | null
  recommended_consume_by?: string | null
  date_conflict_choice?: 'existing' | 'candidate' | null
}

export interface ScanFinalizeResponse {
  food: Food
}

export type SubscriptionOutcome = 'accept' | 'reject' | 'ban' | 'filter'
export type SubscriptionOutcomes = Record<string, SubscriptionOutcome>

export interface BackendErrorEnvelope {
  error?: {
    code?: string
    message?: string
    retryable?: boolean
  }
}
