import { describe, it, expect } from 'vitest'
import { scrambleFrame, KANJI_SCRAMBLE_STEPS } from './kanjiWisdom'

const never = () => 0 // always picks the first pool glyph, '一'

describe('scrambleFrame', () => {
  it('is all noise at step 0 and keeps the length', () => {
    expect(scrambleFrame('七転八起', 0, 16, never)).toBe('一一一一')
  })

  it('reveals the real text from the start, one character at a time', () => {
    expect(scrambleFrame('七転八起', 4, 8, never)).toBe('七転一一')
    expect(scrambleFrame('七転八起', 6, 8, never)).toBe('七転八一')
  })

  it('is almost resolved on the last step', () => {
    const frame = scrambleFrame('一期一会', KANJI_SCRAMBLE_STEPS - 1, KANJI_SCRAMBLE_STEPS, never)
    expect(frame.startsWith('一期一')).toBe(true)
    expect(Array.from(frame)).toHaveLength(4)
  })

  it('handles a single-character entry', () => {
    expect(Array.from(scrambleFrame('侘', 3)).length).toBe(1)
  })
})
