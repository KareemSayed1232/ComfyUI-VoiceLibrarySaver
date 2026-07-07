"""
ComfyUI-VoiceLibrarySaver
=========================
A tiny helper node for the TTS-Audio-Suite (diodiogod) workflow.

Why this exists
---------------
TTS-Audio-Suite's multi-character switching (the [Name] tags) resolves each
character name to an audio FILE that lives in `ComfyUI/models/voices/` and has a
companion transcript `.txt`. The suite itself ships NO node that can turn a
LoadAudio / LoadVideo clip into such a named voice from inside ComfyUI. This node
does exactly that one job, writing:

    ComfyUI/models/voices/<voice_name>.wav
    ComfyUI/models/voices/<voice_name>.reference.txt   (the spoken transcript)
    ComfyUI/models/voices/<voice_name>.txt             (same text, metadata slot)

so that a [<voice_name>] tag in the TTS Text node resolves to it. Feed it the
audio from a LoadAudio / VHS Load Video node and the transcript from the suite's
ASR Transcribe node and you never touch a file or type a transcript by hand.

Install / update
----------------
Copy this folder into  ComfyUI/custom_nodes/ComfyUI-VoiceLibrarySaver  (or
`git pull` if already cloned) and restart ComfyUI. No extra dependencies: it only
uses torch / torchaudio, which ComfyUI already requires for its own audio nodes.
"""

import os
import folder_paths


class VoiceLibrarySaver:
    """Save an AUDIO clip + its transcript into models/voices as a named voice."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO", {
                    "tooltip": "The reference clip to save. Connect a LoadAudio node, or the 'audio' output of a VHS Load Video node."
                }),
                "transcript": ("STRING", {
                    "forceInput": True,
                    "tooltip": "The spoken text of the clip. Connect the 'text' output of the "
                               "TTS Audio Suite 'ASR Transcribe' node so it is filled automatically."
                }),
                "voice_name": ("STRING", {
                    "default": "MyVoice1",
                    "tooltip": "The character name. This becomes the file name AND the [tag] you type "
                               "in the TTS Text node. Example: 'Boss' -> use [Boss] in your text."
                }),
            },
            "optional": {
                "overwrite": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "True = always rewrite the files (use when you change a recording). "
                               "False = only write if the voice does not already exist."
                }),
                "subfolder": ("STRING", {
                    "default": "",
                    "tooltip": "Optional subfolder inside models/voices (leave empty for the root)."
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("voice_name", "saved_path")
    FUNCTION = "save_voice"
    OUTPUT_NODE = True  # runs on every queue even if its outputs are not wired anywhere
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
        """Accept any of ComfyUI's audio shapes and return (waveform[C,T] float32, sample_rate)."""
        import torch
        import numpy as np

        # Some sources (older VHS) hand back a lazy callable
        if callable(audio):
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
            raise ValueError(f"Unsupported audio format for VoiceLibrarySaver: {type(audio)}")

        if waveform.dim() == 3:        # [B, C, T] -> first item -> [C, T]
            waveform = waveform[0]
        elif waveform.dim() == 1:      # [T] -> [1, T]
            waveform = waveform.unsqueeze(0)
        return waveform.detach().cpu().to(torch.float32), int(sample_rate)

    # ---- main --------------------------------------------------------------
    def save_voice(self, audio, transcript, voice_name, overwrite=True, subfolder=""):
        import torchaudio

        name = self._sanitize(voice_name)
        out_dir = self._voices_dir(subfolder)
        wav_path = os.path.join(out_dir, name + ".wav")
        ref_path = os.path.join(out_dir, name + ".reference.txt")
        txt_path = os.path.join(out_dir, name + ".txt")

        waveform, sample_rate = self._to_waveform_sr(audio)
        text = (transcript or "").strip()

        wrote_wav = wrote_txt = False
        if overwrite or not os.path.exists(wav_path):
            torchaudio.save(wav_path, waveform, sample_rate)
            wrote_wav = True
        if overwrite or not os.path.exists(ref_path):
            with open(ref_path, "w", encoding="utf-8") as f:
                f.write(text)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            wrote_txt = True

        status = "wrote" if (wrote_wav or wrote_txt) else "kept existing"
        print(f"[VoiceLibrarySaver] {status} voice '{name}'  ->  {wav_path}")
        if text:
            print(f"[VoiceLibrarySaver] transcript: {text}")
        else:
            print(f"[VoiceLibrarySaver] WARNING: empty transcript for '{name}'. "
                  f"Voice cloning quality will suffer. Is the ASR node connected?")

        # Show name + transcript right on the node so you can verify the ASR result
        preview = text if len(text) <= 400 else text[:400] + " …"
        ui_lines = [f"[OK] {name}  ({status})",
                    f"[TEXT] {preview}" if preview else "[TEXT] (empty - ASR not connected?)"]
        return {"ui": {"text": ui_lines}, "result": (name, wav_path)}


NODE_CLASS_MAPPINGS = {
    "VoiceLibrarySaver": VoiceLibrarySaver,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VoiceLibrarySaver": "Save Voice to Library",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
