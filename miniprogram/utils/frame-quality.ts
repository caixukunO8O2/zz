export interface AccelerationSample {
  x: number
  y: number
  z: number
}

export interface FrameAssessment {
  brightEnough: boolean
  sharpEnough: boolean
}

function luminance(sample: Uint8ClampedArray, offset: number): number {
  return sample[offset] * 0.299 + sample[offset + 1] * 0.587 + sample[offset + 2] * 0.114
}

export function assessFrame(
  sample: Uint8ClampedArray,
  width: number,
  height: number,
): FrameAssessment {
  if (
    !Number.isInteger(width) ||
    !Number.isInteger(height) ||
    width <= 1 ||
    height <= 1 ||
    sample.length !== width * height * 4
  ) {
    throw new Error('invalid_frame_sample')
  }

  const cropWidth = Math.min(width, 64)
  const cropHeight = Math.min(height, 64)
  const originX = Math.floor((width - cropWidth) / 2)
  const originY = Math.floor((height - cropHeight) / 2)
  const step = 8
  let brightnessTotal = 0
  let edgeTotal = 0
  let count = 0

  for (let y = originY; y < originY + cropHeight - 1; y += step) {
    for (let x = originX; x < originX + cropWidth - 1; x += step) {
      const offset = (y * width + x) * 4
      const rightOffset = offset + 4
      const downOffset = offset + width * 4
      const center = luminance(sample, offset)
      const right = luminance(sample, rightOffset)
      const down = luminance(sample, downOffset)
      brightnessTotal += (center + right + down) / 3
      edgeTotal += (Math.abs(center - right) + Math.abs(center - down)) / 2
      count += 1
    }
  }

  const meanBrightness = brightnessTotal / count
  const meanEdge = edgeTotal / count
  return {
    brightEnough: meanBrightness >= 58,
    sharpEnough: meanEdge >= 18,
  }
}

export function isStable(samples: AccelerationSample[]): boolean {
  if (samples.length < 5) return false
  const recent = samples.slice(-5)
  const ranges = (key: keyof AccelerationSample) => {
    const values = recent.map((sample) => sample[key])
    return Math.max(...values) - Math.min(...values)
  }
  const magnitudes = recent.map(({ x, y, z }) => Math.sqrt(x * x + y * y + z * z))
  const magnitudeRange = Math.max(...magnitudes) - Math.min(...magnitudes)
  return ranges('x') <= 0.08 && ranges('y') <= 0.08 && ranges('z') <= 0.08 && magnitudeRange <= 0.08
}
