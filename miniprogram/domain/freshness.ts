import type { FreshnessBucket } from '../types/api'

export type FreshnessTone = 'expired' | 'urgent' | 'week' | 'normal'

export interface FreshnessPresentation {
  bucket: FreshnessBucket
  days: number
  label: string
  tone: FreshnessTone
}

function calendarDay(date: string): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error('invalid_calendar_date')
  const [year, month, day] = date.split('-').map(Number)
  const timestamp = Date.UTC(year, month - 1, day)
  const parsed = new Date(timestamp)
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    throw new Error('invalid_calendar_date')
  }
  return timestamp
}

export function freshnessPresentation(consumeBy: string, today: string): FreshnessPresentation {
  const days = Math.round((calendarDay(consumeBy) - calendarDay(today)) / 86_400_000)
  if (days < 0) return { bucket: 'expired', days, label: '已过期', tone: 'expired' }
  if (days <= 1) {
    return { bucket: 'urgent', days, label: days === 0 ? '今天' : '1天', tone: 'urgent' }
  }
  if (days <= 7) return { bucket: 'this_week', days, label: `${days}天`, tone: 'week' }
  return { bucket: 'normal', days, label: `${days}天`, tone: 'normal' }
}
