# XTTS v2 Usage Guide for ALFR3D Speak Service

## Overview
XTTS v2 is a high-quality multilingual voice cloning model that can generate speech in 17 languages. Unlike traditional TTS models with fixed voices, XTTS v2 can clone any voice from a short audio sample.

## Speaker/voice_idx Information
XTTS v2 has built-in speakers including "Claribel Dervla" (UK female voice) as the default. You can also use voice cloning or specify other built-in speakers.

### Default Speaker: Claribel Dervla
The system defaults to using "Claribel Dervla" (UK female voice) for XTTS v2 when no speaker is specified.

### Option 1: Built-in Speakers (Default)
Uses Claribel Dervla or other available speakers:
```json
{"text": "Hello world"}  // Uses Claribel Dervla by default
{"text": "Hello world", "speaker": "Ana Florence"}  // Uses specific speaker
```

### Option 2: Voice Cloning
Provide a `speaker_wav` parameter with a path to a voice sample (3-6 seconds of audio):
```json
{"text": "Hello world", "speaker_wav": "/path/to/voice_sample.wav"}
```

## Usage Examples

### Voice Cloning
```json
{
  "text": "Hello, this is my cloned voice speaking.",
  "speaker_wav": "/path/to/my_voice_sample.wav"
}
```

### Using Speaker Name (if available)
```json
{
  "text": "Hello world",
  "speaker": "Ana Florence"
}
```

### Specifying Model and Language
```json
{
  "text": "Bonjour le monde",
  "model": "tts_models/multilingual/multi-dataset/xtts_v2",
  "speaker_wav": "/path/to/french_voice.wav",
  "language": "fr"
}
```

### Fallback to gTTS
```json
{
  "text": "Hello world",
  "engine": "gTTS"
}
```

## Supported Languages
- English (en) - default
- Spanish (es)
- French (fr)
- German (de)
- Italian (it)
- Portuguese (pt)
- Polish (pl)
- Turkish (tr)
- Russian (ru)
- Dutch (nl)
- Czech (cs)
- Arabic (ar)
- Chinese (zh-cn)
- Hungarian (hu)
- Korean (ko)
- Japanese (ja)
- Hindi (hi)

## Voice Sample Requirements
- **Length**: 3-6 seconds (longer samples work but only first part is used)
- **Format**: WAV, MP3, or other common audio formats
- **Quality**: Clear speech, minimal background noise
- **Content**: Any speech content works

## Testing Speakers
To see available speakers for XTTS v2, you can check the service logs when it initializes, or the model will indicate if voice cloning is required.</content>
<parameter name="filePath">services/service_speak/XTTS_README.md
