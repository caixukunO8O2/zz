import { describe, expect, it } from 'vitest'

import { freshnessPresentation } from '../domain/freshness'

function addDays(date: string, days: number): string {
  const value = new Date(`${date}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}

describe('freshnessPresentation', () => {
  it.each([
    [-1, 'expired', '已过期', 'expired'],
    [0, 'urgent', '今天', 'urgent'],
    [1, 'urgent', '1天', 'urgent'],
    [2, 'this_week', '2天', 'week'],
    [7, 'this_week', '7天', 'week'],
    [8, 'normal', '8天', 'normal'],
  ] as const)('maps an offset of %s days to the expected home treatment', (offset, bucket, label, tone) => {
    expect(freshnessPresentation(addDays('2026-08-20', offset), '2026-08-20')).toEqual({
      bucket,
      days: offset,
      label,
      tone,
    })
  })

  it('uses calendar days instead of local time-zone milliseconds', () => {
    expect(freshnessPresentation('2026-03-09', '2026-03-08')).toMatchObject({ days: 1, label: '1天' })
  })

  it('rejects malformed API dates rather than displaying a misleading bucket', () => {
    expect(() => freshnessPresentation('not-a-date', '2026-08-20')).toThrow('invalid_calendar_date')
  })
})
