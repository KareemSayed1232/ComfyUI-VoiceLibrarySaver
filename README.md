# ComfyUI-VoiceLibrarySaver

One simple node for [TTS-Audio-Suite](https://github.com/diodiogod/TTS-Audio-Suite):
**🎙️ Create Voice Character**.

Give it an audio clip, an ASR engine you already have loaded, and a name. It
transcribes the clip using **TTS-Audio-Suite's own ASR** — so **no new model is
downloaded**, it reuses whatever ASR model your engine already provides — and
writes the files the suite needs to turn that clip into a usable
`[CharacterName]`. No separate ASR Transcribe node, no hand-typed transcripts,
no file copying.

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
```
Restart ComfyUI. **No extra dependencies** — it uses torch/torchaudio (already
required by ComfyUI) and calls the ASR you already have via TTS-Audio-Suite.

## The node

**🎙️ Create Voice Character** — category `audio/TTS Voice Library`

| Input | Type | Notes |
|-------|------|-------|
| `audio` | AUDIO | The reference clip (from **LoadAudio**). 5–20s of clean speech is ideal. |
| `tts_engine` | TTS_ENGINE | An ASR-capable engine you **already have loaded** (e.g. the Qwen3-TTS Engine, or a Granite ASR Engine). Its model does the transcription. |
| `voice_name` | STRING | Becomes the file name **and** the `[tag]` you type (e.g. `Boss` → `[Boss]`). |
| `language` | STRING | Spoken language for the ASR (`Auto` to detect). |
| `overwrite` | BOOLEAN | True = re-transcribe & rewrite. False = skip if the voice already exists. |
| `subfolder` | STRING | Optional subfolder inside `models/voices`. |

Outputs: `voice_name`, `transcript`, `saved_path`. It is an `OUTPUT_NODE`, so it
runs on every queue even with its outputs unwired, and it shows the transcript
right on the node.

## Typical wiring

```
LoadAudio ───────────────► audio
                                   🎙️ Create Voice Character
<your ASR-capable engine> ─► tts_engine
```

The engine is one you already have in your graph — the same one you use for the
suite's own ASR. After the node runs, type `[<voice_name>]` tags in the
🎤 **TTS Text** node and press **R** in ComfyUI so the voice-folder cache
refreshes.

## Managing voices

The pack also includes four management nodes (category `audio/TTS Voice Library`).
Each picks a voice from a **dropdown** (same style as the suite's Character
Voices node) and outputs a `signal` you can wire into ♻️ **Refresh Voice Cache**
so the suite updates immediately.

| Node | What it does |
|------|--------------|
| 🗑️ **Delete Voice (to trash)** | Moves a voice's files to `models/voice_trash/` — gone from your library but restorable. Needs `confirm` ON. |
| ♻️ **Restore Deleted Voice** | Moves a voice back from the trash into `models/voices/`. |
| ❌ **Purge Trash (permanent)** | Erases a voice from the trash forever (or `ALL` to empty it). Needs `confirm` ON — no undo. |
| ✏️ **Rename Voice** | Renames a voice's `.wav` + transcript files (its `[tag]` changes too). |

Trash lives at `models/voice_trash/` — a sibling of `models/voices/`, so deleted
voices never show up as usable characters. The dropdowns are read when the graph
loads; reload the workflow (or press **R**) to see freshly added/removed voices.

Destructive nodes default to `confirm = OFF`, so queuing the management workflow
does nothing until you flip the switch on the operation you want. To run just one
operation, **bypass** (Ctrl+B) the groups you're not using.

## License

MIT
