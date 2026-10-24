import { describe, it, expect } from 'vitest'
import { scrambleFrame, KANJI_SCRAMBLE_STEPS } from './kanjiWisdom'

const never = () => 0 // always picks the first pool glyph, 'ア'

describe('scrambleFrame', () => {
  it('is all noise at step 0 and keeps the length', () => {
    expect(scrambleFrame('ナナコロビヤオキ', 0, 16, never)).toBe('アアアアアアアア')
  })

  it('reveals the real text from the start, one character at a time', () => {
    expect(scrambleFrame('ナナコロビヤオキ', 4, 8, never)).toBe('ナナコロアアアア')
    expect(scrambleFrame('ナナコロビヤオキ', 6, 8, never)).toBe('ナナコロビヤアア')
  })

  it('is almost resolved on the last step', () => {
    const frame = scrambleFrame('イチゴイチエ', KANJI_SCRAMBLE_STEPS - 1, KANJI_SCRAMBLE_STEPS, never)
    expect(frame.startsWith('イチゴイチ')).toBe(true)
    expect(Array.from(frame)).toHaveLength(6)
  })

  it('handles a single-character entry', () => {
    expect(Array.from(scrambleFrame('ワ', 3)).length).toBe(1)
  })
})
