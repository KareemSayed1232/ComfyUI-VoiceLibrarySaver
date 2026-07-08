"""
ComfyUI-VoiceLibrarySaver
=========================
ONE simple node for the TTS-Audio-Suite (diodiogod) workflow:

    🎙️  Create Voice Character

Give it an audio clip and a name. It transcribes the clip itself (built-in
Whisper ASR) and writes the exact files the suite needs to turn that clip into a
usable [CharacterName]:

    ComfyUI/models/voices/<name>.wav              (the reference clip)
    ComfyUI/models/voices/<name>.reference.txt    (spoken transcript, used for cloning)
    ComfyUI/models/voices/<name>.txt              (same text, metadata slot)

After it runs, type [<name>] in the 🎤 TTS Text node and press R to refresh the
voice cache. No external ASR node, no hand-typed transcripts, no file copying.

Install / update
----------------
Put this folder in  ComfyUI/custom_nodes/ComfyUI-VoiceLibrarySaver  (or `git pull`)
and restart ComfyUI.

Requires ONE Whisper backend (either works, the node auto-detects):
    pip install faster-whisper      (recommended: fast, low VRAM)
    pip install openai-whisper      (alternative)
"""

import os
import folder_paths

# Whisper model sizes offered on the node. Both backends accept these names.
WHISPER_MODELS = ["base", "small", "medium", "large-v3", "tiny"]

# A short language menu; "auto" lets Whisper detect it.
LANGUAGES = ["auto", "en", "ar", "es", "fr", "de", "it", "pt",
             "ru", "zh", "ja", "ko", "hi", "tr", "nl", "pl"]

# Loaded ASR models are cached so repeated runs don't reload from disk.
_ASR_CACHE = {}


def _torch_is_cuda():
    import torch
    return torch.cuda.is_available()


def _asr_faster_whisper(audio_np, model_size, language):
    """Transcribe a 16 kHz mono float32 numpy array with faster-whisper."""
    from faster_whisper import WhisperModel

    device = "cuda" if _torch_is_cuda() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    key = ("faster-whisper", model_size, device, compute_type)

    model = _ASR_CACHE.get(key)
    if model is None:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _ASR_CACHE[key] = model

    lang = None if language == "auto" else language
    segments, info = model.transcribe(audio_np, language=lang, beam_size=5)
    text = "".join(seg.text for seg in segments).strip()
    return text, getattr(info, "language", language)


def _asr_openai_whisper(audio_np, model_size, language):
    """Transcribe a 16 kHz mono float32 numpy array with openai-whisper."""
    import whisper

    device = "cuda" if _torch_is_cuda() else "cpu"
    key = ("openai-whisper", model_size, device)

    model = _ASR_CACHE.get(key)
    if model is None:
        model = whisper.load_model(model_size, device=device)
        _ASR_CACHE[key] = model

    lang = None if language == "auto" else language
    result = model.transcribe(audio_np, language=lang, fp16=(device == "cuda"))
    return result["text"].strip(), result.get("language", language)


class VoiceLibrarySaver:
    """Transcribe an AUDIO clip and save it (+ transcript) as a named voice."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO", {
                    "tooltip": "The reference clip. Connect a LoadAudio node (or the "
                               "'audio' output of a VHS Load Video node). 5-20s of clean "
                               "speech works best."
                }),
                "voice_name": ("STRING", {
                    "default": "MyVoice1",
                    "tooltip": "The character name. Becomes the file name AND the [tag] you "
                               "type in the TTS Text node. Example: 'Boss' -> use [Boss]."
                }),
            },
            "optional": {
                "whisper_model": (WHISPER_MODELS, {
                    "default": "base",
                    "tooltip": "ASR model size. 'base' is a good balance; go bigger for "
                               "more accuracy, smaller for speed. Downloaded once, then cached."
                }),
                "language": (LANGUAGES, {
                    "default": "auto",
                    "tooltip": "Spoken language of the clip. 'auto' lets Whisper detect it."
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

        if callable(audio):          # some older VHS nodes hand back a lazy callable
            audio = audio()

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

    @staticmethod
    def _to_mono_16k_np(waveform, sample_rate):
        """Whisper wants a 16 kHz mono float32 numpy array."""
        import torchaudio
        wf = waveform
        if wf.dim() == 2 and wf.shape[0] > 1:       # downmix to mono
            wf = wf.mean(dim=0, keepdim=True)
        if sample_rate != 16000:
            wf = torchaudio.functional.resample(wf, sample_rate, 16000)
        return wf.squeeze(0).contiguous().cpu().numpy().astype("float32")

    def _transcribe(self, audio_np, model_size, language):
        """Try faster-whisper, then openai-whisper. Raise a clear error if neither is present."""
        import_errors = []
        for backend in (_asr_faster_whisper, _asr_openai_whisper):
            try:
                return backend(audio_np, model_size, language)
            except ImportError as e:
                import_errors.append(str(e))
                continue
        raise RuntimeError(
            "Create Voice Character needs a Whisper backend, but none is installed.\n"
            "Install ONE of these in your ComfyUI python environment:\n"
            "    pip install faster-whisper     (recommended)\n"
            "    pip install openai-whisper\n"
            f"(import errors: {' | '.join(import_errors)})"
        )

    # ---- main --------------------------------------------------------------
    def create_voice(self, audio, voice_name, whisper_model="base",
                     language="auto", overwrite=True, subfolder=""):
        import torchaudio

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

        waveform, sample_rate = self._to_waveform_sr(audio)

        # 1) save the reference clip at its native sample rate
        torchaudio.save(wav_path, waveform, sample_rate)

        # 2) transcribe a 16 kHz mono copy in memory
        audio_np = self._to_mono_16k_np(waveform, sample_rate)
        text, detected_lang = self._transcribe(audio_np, whisper_model, language)

        # 3) write the transcript files that mark this .wav as a usable character
        with open(ref_path, "w", encoding="utf-8") as f:
            f.write(text)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"[Create Voice Character] saved voice '{name}' -> {wav_path}")
        print(f"[Create Voice Character] transcript ({detected_lang}): {text or '(empty!)'}")
        if not text:
            print("[Create Voice Character] WARNING: ASR returned empty text. "
                  "Is the clip silent, or the wrong language selected?")

        preview = text if len(text) <= 400 else text[:400] + " …"
        ui_lines = [f"[OK] {name}  (saved)",
                    f"[LANG] {detected_lang}",
                    f"[TEXT] {preview}" if preview else "[TEXT] (empty - check the clip)"]
        return {"ui": {"text": ui_lines}, "result": (name, text, wav_path)}


NODE_CLASS_MAPPINGS = {
    "VoiceLibrarySaver": VoiceLibrarySaver,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VoiceLibrarySaver": "🎙️ Create Voice Character",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
