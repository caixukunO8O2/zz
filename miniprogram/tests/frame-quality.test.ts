import { describe, expect, it } from 'vitest'

import { assessFrame, isStable } from '../utils/frame-quality'

function solidRgba(value: number, width: number, height: number): Uint8ClampedArray {
  const sample = new Uint8ClampedArray(width * height * 4)
  for (let index = 0; index < sample.length; index += 4) {
    sample[index] = value
    sample[index + 1] = value
    sample[index + 2] = value
    sample[index + 3] = 255
  }
  return sample
}

function checkerboardRgba(width: number, height: number): Uint8ClampedArray {
  const sample = new Uint8ClampedArray(width * height * 4)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4
      const value = (x + y) % 2 === 0 ? 20 : 235
      sample[offset] = value
      sample[offset + 1] = value
      sample[offset + 2] = value
      sample[offset + 3] = 255
    }
  }
  return sample
}

describe('frame quality', () => {
  it('rejects a dark rgba sample', () => {
    expect(assessFrame(solidRgba(32, 64, 64), 64, 64).brightEnough).toBe(false)
  })

  it('does not call a uniformly bright but blurry frame sharp', () => {
    expect(assessFrame(solidRgba(190, 64, 64), 64, 64)).toEqual({ brightEnough: true, sharpEnough: false })
  })

  it('accepts a high-contrast label sample', () => {
    expect(assessFrame(checkerboardRgba(64, 64), 64, 64)).toEqual({ brightEnough: true, sharpEnough: true })
  })

  it('rejects dimensions that do not match the rgba buffer', () => {
    expect(() => assessFrame(new Uint8ClampedArray(4), 64, 64)).toThrow('invalid_frame_sample')
  })

  it('requires five stable accelerometer samples', () => {
    expect(isStable([
      { x: 0.01, y: 0.02, z: 0.99 },
      { x: 0.01, y: 0.02, z: 1 },
      { x: 0.02, y: 0.02, z: 0.99 },
      { x: 0.01, y: 0.01, z: 1 },
      { x: 0.01, y: 0.02, z: 1 },
    ])).toBe(true)
    expect(isStable([{ x: 0, y: 0, z: 1 }])).toBe(false)
  })

  it('rejects a five-sample sequence containing visible movement', () => {
    expect(isStable([
      { x: 0, y: 0, z: 1 },
      { x: 0.01, y: 0, z: 1 },
      { x: 0.42, y: 0.2, z: 0.7 },
      { x: 0, y: 0.01, z: 1 },
      { x: 0, y: 0, z: 1 },
    ])).toBe(false)
  })
})
