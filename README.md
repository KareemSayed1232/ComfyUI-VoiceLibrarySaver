# ComfyUI-VoiceLibrarySaver

A single tiny node for [TTS-Audio-Suite](https://github.com/diodiogod/TTS-Audio-Suite):
**💾 Save Voice to Library**.

It saves an `AUDIO` clip + its transcript into `ComfyUI/models/voices/` as a named
voice, so the suite's `[CharacterName]` tags resolve to it — letting you build a
multi-voice library entirely inside ComfyUI, with **no manual file copying and no
hand-typed transcripts**.

## Why

TTS-Audio-Suite's multi-character switching resolves each `[Name]` tag to an audio
**file** in `models/voices/` that has a companion transcript `.txt`. The suite ships
no node to create those files from inside ComfyUI. This node does exactly that one
job, writing:

```
models/voices/<voice_name>.wav
models/voices/<voice_name>.reference.txt   # the spoken transcript (used for cloning)
models/voices/<voice_name>.txt             # same text (metadata slot)
```

Feed it audio from a **LoadAudio** node and the transcript from the suite's
**✏️ ASR Transcribe** node and everything is automatic.

## Install

**ComfyUI-Manager:** *Install via Git URL* →
`https://github.com/KareemSayed1232/ComfyUI-VoiceLibrarySaver`

**Manual:**
```
cd ComfyUI/custom_nodes
git clone https://github.com/KareemSayed1232/ComfyUI-VoiceLibrarySaver
```
Restart ComfyUI. No extra dependencies (uses torch/torchaudio, already required by
ComfyUI).

## The node

**💾 Save Voice to Library** — category `audio/TTS Voice Library`

| Input | Type | Notes |
|-------|------|-------|
| `audio` | AUDIO | The reference clip (from LoadAudio). |
| `transcript` | STRING | Spoken text — wire the `text` output of ✏️ ASR Transcribe. |
| `voice_name` | STRING | Becomes the file name **and** the `[tag]` you type (e.g. `Voice2` → `[Voice2]`). |
| `overwrite` | BOOLEAN | True = always rewrite (use when you change a recording). |
| `subfolder` | STRING | Optional subfolder inside `models/voices`. |

Outputs `voice_name` and `saved_path`. It is an `OUTPUT_NODE`, so it runs on every
queue even with its outputs unwired.

## Typical wiring

```
LoadAudio ──► ✏️ ASR Transcribe (any TTS-Audio-Suite engine) ──► 💾 Save Voice to Library
```

Then type `[<voice_name>]` tags in the 🎤 TTS Text node. After the first build,
press **R** in ComfyUI so the voice-folder cache refreshes.

## License

MIT
