# ComfyUI-VoiceLibrarySaver

A voice-library toolkit for [TTS-Audio-Suite](https://github.com/diodiogod/TTS-Audio-Suite):
**create, manage, back up, and restore** the voice characters the suite uses for
`[CharacterName]` switching — entirely inside ComfyUI, with dropdowns instead of
typing and plain-English status on every node.

The suite resolves each `[Name]` tag to an audio **file** in `models/voices/`
that has a companion transcript. This pack is the set of nodes that create and
manage those files.

## Install

**ComfyUI-Manager:** *Install via Git URL* →
`https://github.com/KareemSayed1232/ComfyUI-VoiceLibrarySaver`

**Manual:**
```
cd ComfyUI/custom_nodes
git clone https://github.com/KareemSayed1232/ComfyUI-VoiceLibrarySaver
```
Restart ComfyUI. **No extra dependencies** — it uses torch/torchaudio (already
required by ComfyUI) and, for transcription, calls the ASR you already have via
TTS-Audio-Suite. No new models are ever downloaded.

Two ready-made workflows ship in the repo root:
`Voice-Character-Creator.json` (make a voice) and `Voice-Manager.json` (manage
them).

## Create a voice — 🎙️ Create Voice Character

Give it an audio clip, an ASR engine you already have loaded, and a name. It
transcribes the clip with **the suite's own ASR** and writes the three files that
make a usable character:

```
models/voices/<name>.wav              # the reference clip (saved at native sample rate)
models/voices/<name>.reference.txt    # the spoken transcript (used for cloning)
models/voices/<name>.txt              # same text (metadata slot)
```

| Input | Type | Notes |
|-------|------|-------|
| `audio` | AUDIO | The reference clip (from **LoadAudio**). 5–20s of clean speech is ideal. |
| `tts_engine` | TTS_ENGINE | An ASR-capable engine you **already have loaded** (e.g. the Qwen3-TTS Engine, or a Granite ASR Engine). Its model does the transcription. |
| `voice_name` | text | Becomes the file name **and** the `[tag]` you type (e.g. `Boss` → `[Boss]`). |
| `language` | dropdown | Spoken language for the ASR — `Auto` to detect. |
| `overwrite` | toggle | On = re-transcribe & rewrite. Off = skip if the voice already exists. |
| `subfolder` | dropdown | Where to save inside `models/voices` — `(root)` for the top folder. |

Outputs `voice_name`, `transcript`, `saved_path`. Wiring:

```
LoadAudio ───────────────► audio
                                   🎙️ Create Voice Character
<your ASR-capable engine> ─► tts_engine
```

After it runs, type `[<voice_name>]` in the 🎤 **TTS Text** node.

## Manage voices

All management nodes live in category `audio/TTS Voice Library`. They:

- pick voices from a **dropdown** (same style as the suite's Character Voices node);
- show a plain-English **status line right on the node** after they run;
- **auto-refresh every dropdown** in the graph and the suite's own character cache,
  so you never press R or wire a Refresh node.

| Node | What it does |
|------|--------------|
| 🗑️ **Delete Voice (to trash)** | Moves a voice's files to `models/voice_trash/` — gone from your library but restorable. `confirm` must be ON. |
| ♻️ **Restore Deleted Voice** | Moves a voice back from the trash into `models/voices/`. |
| ❌ **Purge Trash (permanent)** | Erases a voice from the trash forever (or `ALL` to empty it). `confirm` must be ON — no undo. |
| ✏️ **Rename Voice** | Renames a voice's `.wav` + transcript files (its `[tag]` changes too). |
| ⧉ **Duplicate Voice** | Copies a voice to a new name, keeping the original. |
| 🔎 **Preview Voice** | Outputs a saved voice's `audio` + `transcript` — wire `audio` into a Preview Audio node to hear it. |
| 📋 **List Voices** | Lists every saved voice, flags any missing a transcript, and shows what's in the trash. |
| 📦 **Backup / Export Voices** | Zips the whole `models/voices/` folder (optionally the trash too) into `ComfyUI/output/` with a timestamp. |
| 📥 **Import / Restore Backup** | Restores voices from a backup zip — pick it from a dropdown of the `.zip` files in `output/` and `input/`. |

### Deleting vs. purging

Delete is a **soft-delete**: files move to `models/voice_trash/`, a *sibling* of
`models/voices/` (so deleted voices never resolve as `[tags]`). That's what makes
**Restore** possible. **Purge** is the real permanent delete, and it only ever
touches the trash.

### Backup & restore

- 📦 **Backup** writes `ComfyUI/output/<prefix>_<timestamp>.zip`, keeping the
  `voices/…` folder structure inside (and `voice_trash/…` if you include it).
- 📥 **Import** reads any `.zip` from `output/` or `input/` and unpacks it back
  into `models/voices/` (and the trash). It skips voices that already exist unless
  `overwrite` is ON, and ignores unsafe paths inside the zip.
- To move voices to another machine: copy the zip over, drop it in that ComfyUI's
  `input/` (or `output/`) folder, and run 📥 Import.

### Safety

Destructive nodes (Delete, Purge) default to `confirm = OFF`, and Rename /
Duplicate / Import won't clobber existing voices unless `overwrite` is ON — so
queuing the whole management workflow does nothing until you flip a switch. Every
node runs on Queue, so to perform one operation, **bypass** (Ctrl+B) the groups
you're not using.

Note: the dropdown lists are read when the graph loads and refreshed after each
operation. If you add files to `models/voices/` outside ComfyUI, reload the
workflow (or press R) to see them.

## License

MIT
