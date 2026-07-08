"""
ComfyUI-VoiceLibrarySaver
=========================
ONE simple node for the TTS-Audio-Suite (diodiogod) workflow:

    🎙️  Create Voice Character

Give it an audio clip, an ASR engine you already have loaded, and a name. It
transcribes the clip using **TTS-Audio-Suite's own ASR** (so NO new model is
downloaded — it reuses whatever ASR model your engine already provides) and
writes the files the suite needs to turn that clip into a usable [CharacterName]:

    ComfyUI/models/voices/<name>.wav              (the reference clip)
    ComfyUI/models/voices/<name>.reference.txt    (spoken transcript, used for cloning)
    ComfyUI/models/voices/<name>.txt              (same text, metadata slot)

After it runs, type [<name>] in the 🎤 TTS Text node and press R to refresh the
voice cache. No separate ASR Transcribe node, no hand-typed transcripts.

Wiring
------
    LoadAudio ─────────────► audio
    <your ASR-capable        │
     TTS engine> ──────────► tts_engine   🎙️ Create Voice Character
                                            (any engine the suite's ASR accepts,
                                             e.g. the Qwen3-TTS Engine or a
                                             Granite ASR Engine — the model you
                                             already downloaded)

Install / update
----------------
Put this folder in  ComfyUI/custom_nodes/ComfyUI-VoiceLibrarySaver  (or `git pull`)
and restart ComfyUI. No extra dependencies — it uses torch/torchaudio (already
required by ComfyUI) and calls TTS-Audio-Suite's ASR that you already have.
"""

import os
import folder_paths


def _find_suite_asr_class():
    """Locate TTS-Audio-Suite's UnifiedASRTranscribeNode via ComfyUI's registry.

    Looked up at runtime (not import time) because the suite may load after us.
    """
    import nodes  # ComfyUI's global node registry
    for cls in nodes.NODE_CLASS_MAPPINGS.values():
        if getattr(cls, "__name__", "") == "UnifiedASRTranscribeNode":
            return cls
    return None


# ---------------------------------------------------------------------------
# Shared helpers for the voice-library management nodes
# ---------------------------------------------------------------------------
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".aac")
PURGE_ALL = "⚠️ ALL (empty trash)"


def _voices_root():
    return os.path.join(folder_paths.models_dir, "voices")


def _trash_root():
    # A sibling of models/voices, NOT inside it, so the suite never lists
    # deleted voices as usable characters.
    return os.path.join(folder_paths.models_dir, "voice_trash")


def _sanitize_name(name):
    cleaned = "".join(c for c in (name or "").strip() if c not in '\\/:*?"<>|')
    return cleaned.strip() or "Voice"


def _list_voice_names(directory):
    """Base names of every voice (audio file) in a directory, sorted."""
    names = set()
    if os.path.isdir(directory):
        for f in os.listdir(directory):
            stem, ext = os.path.splitext(f)
            if ext.lower() in AUDIO_EXTS:
                names.add(stem)
    return sorted(names, key=str.lower)


def _companion_files(directory, base):
    """Every file that belongs to a voice: <base>.wav, <base>.reference.txt, etc."""
    out = []
    if os.path.isdir(directory):
        prefix = base + "."
        for f in os.listdir(directory):
            if f.startswith(prefix):
                out.append(f)
    return out


def _move_voice(src_dir, dst_dir, base, overwrite=True):
    """Move all files of a voice from one dir to another. Returns moved filenames."""
    import shutil
    os.makedirs(dst_dir, exist_ok=True)
    moved = []
    for f in _companion_files(src_dir, base):
        src = os.path.join(src_dir, f)
        dst = os.path.join(dst_dir, f)
        if os.path.exists(dst):
            if overwrite:
                os.remove(dst)
            else:
                continue
        shutil.move(src, dst)
        moved.append(f)
    return moved


def _dropdown(names):
    """ComfyUI combos must be non-empty; give a clear placeholder when empty."""
    return names or ["(none found)"]


# Languages the suite's Qwen3 ASR accepts, plus "Auto" for auto-detect.
LANGUAGES = ["Auto", "English", "Arabic", "Chinese", "Cantonese", "German", "French",
             "Spanish", "Portuguese", "Indonesian", "Italian", "Korean", "Russian",
             "Thai", "Vietnamese", "Japanese", "Turkish", "Hindi", "Malay", "Dutch",
             "Swedish", "Danish", "Finnish", "Polish", "Czech", "Filipino", "Persian",
             "Greek", "Romanian", "Hungarian", "Macedonian"]

ROOT_LABEL = "(root)"


def _list_subfolders(directory):
    """'(root)' plus every real subfolder of models/voices — for a save-location dropdown."""
    subs = [ROOT_LABEL]
    if os.path.isdir(directory):
        for f in sorted(os.listdir(directory), key=str.lower):
            if os.path.isdir(os.path.join(directory, f)) and not f.startswith("."):
                subs.append(f)
    return subs


class VoiceLibrarySaver:
    """Transcribe an AUDIO clip with the suite's ASR and save it as a named voice."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO", {
                    "tooltip": "The reference clip. Connect a LoadAudio node (or the "
                               "'audio' output of a VHS Load Video node). 5-20s of clean "
                               "speech works best."
                }),
                "tts_engine": ("TTS_ENGINE", {
                    "tooltip": "An ASR-capable TTS-Audio-Suite engine you ALREADY have loaded "
                               "(e.g. the Qwen3-TTS Engine, or a Granite ASR Engine). Its model "
                               "does the transcription, so nothing new is downloaded."
                }),
                "voice_name": ("STRING", {
                    "default": "MyVoice1",
                    "tooltip": "The character name. Becomes the file name AND the [tag] you "
                               "type in the TTS Text node. Example: 'Boss' -> use [Boss]."
                }),
            },
            "optional": {
                "language": (LANGUAGES, {
                    "default": "Auto",
                    "tooltip": "Spoken language for the ASR ('Auto' to detect). Pick from the list."
                }),
                "overwrite": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "True = always re-transcribe and rewrite the files. "
                               "False = skip if the voice already exists (fast)."
                }),
                "subfolder": (_list_subfolders(_voices_root()), {
                    "default": ROOT_LABEL,
                    "tooltip": "Where to save inside models/voices. '(root)' = the top folder."
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("voice_name", "transcript", "saved_path")
    FUNCTION = "create_voice"
    OUTPUT_NODE = True  # runs on every queue even if outputs are not wired anywhere
    CATEGORY = "audio/TTS Voice Library"

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def _sanitize(name):
        cleaned = "".join(c for c in (name or "").strip() if c not in '\\/:*?"<>|')
        return cleaned.strip() or "Voice"

    @staticmethod
    def _voices_dir(subfolder):
        base = os.path.join(folder_paths.models_dir, "voices")
        if subfolder:
            base = os.path.join(base, subfolder.strip().strip("/\\"))
        os.makedirs(base, exist_ok=True)
        return base

    @staticmethod
    def _to_waveform_sr(audio):
        """Accept any of ComfyUI's audio shapes -> (waveform[C,T] float32, sample_rate)."""
        import torch
        import numpy as np

        waveform, sample_rate = None, 24000
        if isinstance(audio, dict) and "waveform" in audio:
            waveform = audio["waveform"]
            sample_rate = int(audio.get("sample_rate", 24000))
        elif isinstance(audio, (tuple, list)) and len(audio) == 2:
            waveform, sample_rate = audio[0], int(audio[1])
        else:
            waveform = audio

        if isinstance(waveform, np.ndarray):
            waveform = torch.from_numpy(waveform)
        if not isinstance(waveform, torch.Tensor):
            raise ValueError(f"Unsupported audio format for Create Voice Character: {type(audio)}")

        if waveform.dim() == 3:        # [B, C, T] -> first item -> [C, T]
            waveform = waveform[0]
        elif waveform.dim() == 1:      # [T] -> [1, T]
            waveform = waveform.unsqueeze(0)
        return waveform.detach().cpu().to(torch.float32), int(sample_rate)

    def _transcribe_with_suite(self, tts_engine, audio, language):
        """Call TTS-Audio-Suite's ASR node in-process and return the text."""
        asr_cls = _find_suite_asr_class()
        if asr_cls is None:
            raise RuntimeError(
                "Create Voice Character could not find TTS-Audio-Suite's ASR node "
                "(UnifiedASRTranscribeNode). Make sure TTS-Audio-Suite is installed and "
                "loaded, then restart ComfyUI."
            )
        inst = asr_cls()
        func = getattr(inst, getattr(asr_cls, "FUNCTION", "transcribe"))

        # Guard against a misaligned/garbage language widget (e.g. a stray bool
        # from an old node layout). Only accept a real, non-empty string.
        if not isinstance(language, str) or not language.strip():
            language = "Auto"

        # Only pass arguments the installed suite version actually accepts, so we
        # don't break across versions (e.g. some versions have no 'diarization').
        import inspect
        desired = {
            "engine": tts_engine,
            "audio": audio,
            "language": language,
            "task": "transcribe",
            "timestamps": "none",
            "diarization": False,
            "chunk_size": 30,
            "overlap": 2,
            "enable_asr_cache": True,
        }
        try:
            params = inspect.signature(func).parameters
            has_var_kw = any(p.kind == p.VAR_KEYWORD for p in params.values())
            if not has_var_kw:
                desired = {k: v for k, v in desired.items() if k in params}
        except (TypeError, ValueError):
            # Signature unavailable; fall back to the two guaranteed required args.
            desired = {"engine": tts_engine, "audio": audio}

        result = func(**desired)
        # transcribe() returns (text, asr_timing_data, info)
        if isinstance(result, (tuple, list)) and result:
            return (result[0] or "").strip()
        return (result or "").strip()

    # ---- main --------------------------------------------------------------
    def create_voice(self, audio, tts_engine, voice_name,
                     language="Auto", overwrite=True, subfolder=""):
        import torchaudio

        # Resolve a lazy audio callable (some older VHS nodes) once, up front.
        if callable(audio):
            audio = audio()

        if subfolder in (ROOT_LABEL, None):
            subfolder = ""

        name = self._sanitize(voice_name)
        out_dir = self._voices_dir(subfolder)
        wav_path = os.path.join(out_dir, name + ".wav")
        ref_path = os.path.join(out_dir, name + ".reference.txt")
        txt_path = os.path.join(out_dir, name + ".txt")

        already_exists = all(os.path.exists(p) for p in (wav_path, ref_path, txt_path))
        if already_exists and not overwrite:
            existing = ""
            try:
                with open(ref_path, "r", encoding="utf-8") as f:
                    existing = f.read().strip()
            except Exception:
                pass
            print(f"[Create Voice Character] kept existing voice '{name}' -> {wav_path}")
            ui_lines = [f"[OK] {name}  (kept existing)",
                        f"[TEXT] {existing[:400]}" if existing else "[TEXT] (existing transcript)"]
            return {"ui": {"text": ui_lines}, "result": (name, existing, wav_path)}

        # 1) save the reference clip at its native sample rate
        waveform, sample_rate = self._to_waveform_sr(audio)
        torchaudio.save(wav_path, waveform, sample_rate)

        # 2) transcribe with the suite's own ASR (no new model download)
        text = self._transcribe_with_suite(tts_engine, audio, language)

        # 3) write the transcript files that mark this .wav as a usable character
        with open(ref_path, "w", encoding="utf-8") as f:
            f.write(text)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"[Create Voice Character] saved voice '{name}' -> {wav_path}")
        print(f"[Create Voice Character] transcript: {text or '(empty!)'}")
        if not text:
            print("[Create Voice Character] WARNING: ASR returned empty text. "
                  "Is the clip silent, or is the engine ASR-capable?")

        preview = text if len(text) <= 400 else text[:400] + " …"
        ui_lines = [f"[OK] {name}  (saved)",
                    f"[TEXT] {preview}" if preview else "[TEXT] (empty - check clip/engine)"]
        return {"ui": {"text": ui_lines}, "result": (name, text, wav_path)}


class VoiceLibraryDelete:
    """Soft-delete a voice: move it to the trash folder (restorable later)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "voice": (_dropdown(_list_voice_names(_voices_root())), {
                    "tooltip": "The voice to delete. Its files are MOVED to models/voice_trash "
                               "so you can restore them; they no longer resolve as [tags]."
                }),
                "confirm": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Safety switch. Must be ON to actually delete."
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("signal",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "audio/TTS Voice Library"

    def run(self, voice, confirm):
        if voice in ("(none found)", "") or voice is None:
            return {"ui": {"text": ["[SKIP] no voice selected"]}, "result": (voice or "",)}
        if not confirm:
            print(f"[Voice Delete] '{voice}' NOT deleted (confirm is OFF).")
            return {"ui": {"text": [f"[SKIP] {voice}", "Turn 'confirm' ON to delete."]},
                    "result": (voice,)}
        moved = _move_voice(_voices_root(), _trash_root(), voice, overwrite=True)
        print(f"[Voice Delete] moved '{voice}' to trash: {moved}")
        return {"ui": {"text": [f"[DELETED] {voice} -> trash", f"{len(moved)} file(s)"]},
                "result": (voice,)}


class VoiceLibraryRestore:
    """Restore a previously deleted voice from the trash back into models/voices."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "voice": (_dropdown(_list_voice_names(_trash_root())), {
                    "tooltip": "A voice sitting in the trash. It is MOVED back to models/voices "
                               "and becomes a usable [tag] again."
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("signal",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "audio/TTS Voice Library"

    def run(self, voice):
        if voice in ("(none found)", "") or voice is None:
            return {"ui": {"text": ["[SKIP] nothing in trash"]}, "result": (voice or "",)}
        moved = _move_voice(_trash_root(), _voices_root(), voice, overwrite=True)
        print(f"[Voice Restore] restored '{voice}' from trash: {moved}")
        return {"ui": {"text": [f"[RESTORED] {voice}", f"{len(moved)} file(s)"]},
                "result": (voice,)}


class VoiceLibraryPurge:
    """Permanently delete voices from the trash. This cannot be undone."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "voice": (_dropdown([PURGE_ALL] + _list_voice_names(_trash_root())), {
                    "tooltip": "A voice in the trash to erase forever, or ALL to empty the trash."
                }),
                "confirm": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Safety switch. Must be ON. Permanent — there is no undo."
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("signal",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "audio/TTS Voice Library"

    def run(self, voice, confirm):
        if not confirm:
            print(f"[Voice Purge] '{voice}' NOT purged (confirm is OFF).")
            return {"ui": {"text": [f"[SKIP] {voice}", "Turn 'confirm' ON to purge."]},
                    "result": (voice,)}
        trash = _trash_root()
        targets = _list_voice_names(trash) if voice == PURGE_ALL else [voice]
        removed = 0
        for base in targets:
            for f in _companion_files(trash, base):
                try:
                    os.remove(os.path.join(trash, f))
                    removed += 1
                except OSError:
                    pass
        print(f"[Voice Purge] permanently removed {removed} file(s) for {targets}")
        return {"ui": {"text": [f"[PURGED] {voice}", f"{removed} file(s) erased"]},
                "result": (voice,)}


class VoiceLibraryRename:
    """Rename a voice (and its transcript files) in models/voices."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "voice": (_dropdown(_list_voice_names(_voices_root())), {
                    "tooltip": "The voice to rename."
                }),
                "new_name": ("STRING", {
                    "default": "",
                    "tooltip": "New name = new [tag]. Renames the .wav and its transcript files."
                }),
            },
            "optional": {
                "overwrite": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Overwrite if a voice with the new name already exists."
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("signal",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "audio/TTS Voice Library"

    def run(self, voice, new_name, overwrite=False):
        if voice in ("(none found)", "") or voice is None:
            return {"ui": {"text": ["[SKIP] no voice selected"]}, "result": (voice or "",)}
        new_base = _sanitize_name(new_name)
        if not new_name.strip():
            return {"ui": {"text": ["[SKIP] enter a new name"]}, "result": (voice,)}
        if new_base == voice:
            return {"ui": {"text": [f"[SKIP] name unchanged: {voice}"]}, "result": (voice,)}

        voices = _voices_root()
        renamed = 0
        for f in _companion_files(voices, voice):
            suffix = f[len(voice):]                 # ".wav", ".reference.txt", ".txt", ...
            dst = os.path.join(voices, new_base + suffix)
            if os.path.exists(dst):
                if overwrite:
                    os.remove(dst)
                else:
                    print(f"[Voice Rename] '{new_base}' already exists; skipped (overwrite OFF).")
                    return {"ui": {"text": [f"[SKIP] {new_base} exists", "Turn overwrite ON."]},
                            "result": (voice,)}
            os.rename(os.path.join(voices, f), dst)
            renamed += 1
        print(f"[Voice Rename] '{voice}' -> '{new_base}' ({renamed} file(s))")
        return {"ui": {"text": [f"[RENAMED] {voice} -> {new_base}", f"{renamed} file(s)"]},
                "result": (new_base,)}


NODE_CLASS_MAPPINGS = {
    "VoiceLibrarySaver": VoiceLibrarySaver,
    "VoiceLibraryDelete": VoiceLibraryDelete,
    "VoiceLibraryRestore": VoiceLibraryRestore,
    "VoiceLibraryPurge": VoiceLibraryPurge,
    "VoiceLibraryRename": VoiceLibraryRename,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VoiceLibrarySaver": "🎙️ Create Voice Character",
    "VoiceLibraryDelete": "🗑️ Delete Voice (to trash)",
    "VoiceLibraryRestore": "♻️ Restore Deleted Voice",
    "VoiceLibraryPurge": "❌ Purge Trash (permanent)",
    "VoiceLibraryRename": "✏️ Rename Voice",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
