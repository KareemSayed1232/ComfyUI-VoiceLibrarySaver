# ComfyUI-VoiceLibrarySaver

One simple node for [TTS-Audio-Suite](https://github.com/diodiogod/TTS-Audio-Suite):
**🎙️ Create Voice Character**.

Give it an audio clip and a name. It **transcribes the clip itself** (built-in
Whisper ASR) and writes the exact files the suite needs to turn that clip into a
usable `[CharacterName]` — **no external ASR node, no hand-typed transcripts, no
file copying.**

## What it does

TTS-Audio-Suite's multi-character switching resolves each `[Name]` tag to an audio
**file** in `models/voices/` that has a companion transcript. This node creates
those files from one audio input, writing:

```
models/voices/<name>.wav              # the reference clip (saved at native sample rate)
models/voices/<name>.reference.txt    # the spoken transcript (used for cloning)
models/voices/<name>.txt              # same text (metadata slot)
```

## Install

**ComfyUI-Manager:** *Install via Git URL* →
`https://github.com/KareemSayed1232/ComfyUI-VoiceLibrarySaver`

**Manual:**
```
cd ComfyUI/custom_nodes
git clone https://github.com/KareemSayed1232/ComfyUI-VoiceLibrarySaver
pip install faster-whisper        # or: pip install openai-whisper
```
Restart ComfyUI.

The node needs **one** Whisper backend for the ASR and auto-detects whichever is
installed: `faster-whisper` (recommended — fast, low VRAM) or `openai-whisper`.
The chosen model size downloads once on first use, then is cached.

## The node

**🎙️ Create Voice Character** — category `audio/TTS Voice Library`

| Input | Type | Notes |
|-------|------|-------|
| `audio` | AUDIO | The reference clip (from **LoadAudio**). 5–20s of clean speech is ideal. |
| `voice_name` | STRING | Becomes the file name **and** the `[tag]` you type (e.g. `Boss` → `[Boss]`). |
| `whisper_model` | choice | ASR size: `tiny`/`base`/`small`/`medium`/`large-v3`. Default `base`. |
| `language` | choice | Spoken language, or `auto` to detect. |
| `overwrite` | BOOLEAN | True = re-transcribe & rewrite. False = skip if the voice already exists. |
| `subfolder` | STRING | Optional subfolder inside `models/voices`. |

Outputs: `voice_name`, `transcript`, `saved_path`. It is an `OUTPUT_NODE`, so it
runs on every queue even with its outputs unwired, and it shows the detected
transcript right on the node.

## Typical wiring

```
LoadAudio ──► 🎙️ Create Voice Character
```

That's the whole graph. After it runs, type `[<voice_name>]` tags in the
🎤 **TTS Text** node and press **R** in ComfyUI so the voice-folder cache
refreshes.

## License

MIT
