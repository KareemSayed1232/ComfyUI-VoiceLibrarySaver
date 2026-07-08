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
                "language": ("STRING", {
                    "default": "Auto",
                    "tooltip": "Spoken language for the ASR ('Auto' to detect). Passed straight "
                               "to the suite's ASR node."
                }),
                "overwrite": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "True = always re-transcribe and rewrite the files. "
                               "False = skip if the voice already exists (fast)."
                }),
                "subfolder": ("STRING", {
                    "default": "",
                    "tooltip": "Optional subfolder inside models/voices (leave empty for root)."
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
        # Mirror the suite ASR node's defaults; only language is exposed on our node.
        result = func(
            engine=tts_engine,
            audio=audio,
            language=(language or "Auto"),
            task="transcribe",
            timestamps="none",
            diarization=False,
            chunk_size=30,
            overlap=2,
            enable_asr_cache=True,
        )
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


NODE_CLASS_MAPPINGS = {
    "VoiceLibrarySaver": VoiceLibrarySaver,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VoiceLibrarySaver": "🎙️ Create Voice Character",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
