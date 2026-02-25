# Personality Matrix Implementation Plan

## Overview

The personality matrix adds dynamic, configurable personalities to ALFR3D with:
- Presets and custom sliders via frontend
- Mood-based context offsets
- Optional LLM enhancement (Anthropic Claude)
- gTTS fallback for voice output

## Architecture

### Integration Point: `services/service_speak/`

The speak service is ideal because:
- Already consumes `speak` Kafka topic
- Handles TTS generation with fallback to gTTS
- Already sends events to frontend
- Simplest path for LLM → TTS flow

---

## Database Schema

### 1. Add to existing `config` table

```sql
-- Add these columns to config table:
ALTER TABLE config ADD COLUMN name='llm_api_key';
ALTER TABLE config ADD COLUMN name='llm_usage_limit', value='10';
```

### 2. Create `personality` table

```sql
CREATE TABLE personality (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64),
    type ENUM('preset', 'current') DEFAULT 'preset',
    environment_id INT NULL,

    -- Explicit trait columns (0.0 to 1.0)
    sarcasm FLOAT DEFAULT 0.0,
    formality FLOAT DEFAULT 0.5,
    warmth FLOAT DEFAULT 0.5,
    patience FLOAT DEFAULT 1.0,

    linguistic_style VARCHAR(256),
    forbidden_words VARCHAR(512),
    verbal_tics VARCHAR(512),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3. Create `context` table

```sql
CREATE TABLE context (
    id INT AUTO_INCREMENT PRIMARY KEY,
    environment_id INT UNIQUE,

    -- Runtime context fields
    repeat_count INT DEFAULT 0,
    hour INT DEFAULT 12,
    weather VARCHAR(64),
    mood VARCHAR(32) DEFAULT 'neutral',
    last_error_count INT DEFAULT 0,
    llm_calls_today INT DEFAULT 0,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 4. Seed presets

```sql
INSERT INTO personality (name, type, sarcasm, formality, warmth, patience, linguistic_style, forbidden_words, verbal_tics) VALUES
('Butler', 'preset', 0.3, 1.0, 0.4, 0.8, 'Archaic Butler', 'stupid,dumb,idiot', 'I presume,Your Grace'),
('Maid', 'preset', 0.1, 0.8, 0.9, 0.9, 'Polite Maid', 'stupid,dumb', 'Of course,Right away'),
('Snarky', 'preset', 1.0, 0.2, 0.1, 0.2, 'Dry wit', '', 'Groundbreaking,Shocking truly'),
('Friendly', 'preset', 0.1, 0.3, 1.0, 0.9, 'Casual pal', '', 'Hey buddy,You rock');
```

---

## Kafka Topics

### Existing: `speak`
- Input: JSON `{"text": "...", "engine": "Coqui"}`

### New: `personality`
- Output: Broadcasts personality state after each speak
- Format:
```json
{
  "type": "personality_state",
  "sarcasm": 0.5,
  "formality": 0.8,
  "warmth": 0.4,
  "patience": 0.6,
  "mood": "neutral",
  "llm_used": true,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

---

## Service Speak Changes

### New Files

#### `services/service_speak/personality.py`
- Load personality from DB by environment
- Load context from DB
- Calculate mood offset from context
- Blend baseline personality + mood offset
- Build LLM system prompt

#### `services/service_speak/llm_client.py`
- Anthropic Claude API client (Haiku model)
- Check API key from config table
- Check usage limit before calling
- Return response text

### Modified: `services/service_speak/app.py`

**New speak flow:**
```
1. Consume speak topic message
2. Load current personality from DB (by environment_id)
3. Load context from DB
4. Calculate mood offset → blended traits
5. Check llm_api_key and llm_usage_limit
6. If LLM available:
   - Build system prompt with blended traits
   - Call Claude API
   - Use LLM response as TTS text
   - Increment llm_calls_today
7. If no LLM: use original text from message
8. Apply TTS modifications (rate based on traits)
9. Generate audio (Coqui → gTTS fallback)
10. Produce personality state to Kafka
11. Send audio event to frontend
```

---

## Frontend Changes

### Location: Matrix tab → Personality panel

#### Personality Settings
- **Preset dropdown**: Butler, Maid, Snarky, Friendly, Custom
- **4 trait sliders** (0.0 - 1.0):
  - Sarcasm: Earnest ↔ Snarky
  - Formality: Slang ↔ Royal
  - Warmth: Cold ↔ Nurturing
  - Patience: Irritable ↔ Saint
- **Current mood display**: (from Kafka `personality` topic)

#### LLM Settings
- **API key input**: Text field for Anthropic key
- **Usage limit slider**: 0-100 calls per hour

---

## Mood Offset Rules

```python
def calculate_mood_offset(context: dict) -> dict:
    offset = {"sarcasm": 0.0, "patience": 0.0, "warmth": 0.0}

    # User repeats themselves
    if context.get("repeat_count", 0) > 2:
        offset["sarcasm"] += 0.4
        offset["patience"] -= 0.5

    # Late at night
    if context.get("hour", 12) > 22:
        offset["warmth"] -= 0.2

    # Recent errors
    if context.get("last_error_count", 0) > 2:
        offset["patience"] -= 0.3
        offset["warmth"] -= 0.2

    return offset

def blend_traits(base: dict, offset: dict) -> dict:
    return {
        k: max(0.0, min(1.0, v + offset.get(k, 0.0)))
        for k, v in base.items()
    }
```

---

## LLM Prompt Template

```
You are ALFR3D, a home assistant.

Current Personality State:
- Style: {linguistic_style}
- Sarcasm: {sarcasm}/1.0
- Formality: {formality}/1.0
- Warmth: {warmth}/1.0
- Patience: {patience}/1.0

Voice Constraints:
- Use these verbal tics: {verbal_tics}
- Never use these words: {forbidden_words}

Instructions:
- Respond to the user's request
- Keep it under 20 words for TTS efficiency
- Stay in character based on the personality traits above

User request: {user_text}
```

---

## Implementation Order

1. **Database**: Create tables, seed presets
2. **Service speak**: Add personality.py, llm_client.py
3. **Kafka**: Add `personality` topic to docker-compose
4. **Service speak**: Modify app.py flow
5. **Frontend**: Add Matrix → Personality panel
6. **Test**: End-to-end personality changes

---

## Example Results

**Normal context (Butler):**
> "I have adjusted the lights for you, sir."

**High repeat_count (Butler):**
> "I have adjusted the lights. *Again*. I presume you'll want me to dim them further when you inevitably change your mind?"
