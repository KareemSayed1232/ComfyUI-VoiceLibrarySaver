"""
ComfyUI-VoiceLibrarySaver
=========================
A tiny helper node for the TTS-Audio-Suite (diodiogod) workflow.

Why this exists
---------------
TTS-Audio-Suite's multi-character switching (the [Name] tags) resolves each
character name to an audio FILE that lives in `ComfyUI/models/voices/` and has a
companion transcript `.txt`. The suite itself ships NO node that can turn a
LoadAudio clip into such a named voice file from inside ComfyUI. This node does
exactly that one job: it writes

    ComfyUI/models/voices/<voice_name>.wav
    ComfyUI/models/voices/<voice_name>.reference.txt   (the spoken transcript)
    ComfyUI/models/voices/<voice_name>.txt             (same text, metadata slot)

so that a [<voice_name>] tag in the TTS Text node resolves to it. Feed it the
audio from a LoadAudio node and the transcript from the suite's
"ASR Transcribe" node and you never touch a file or type a transcript by hand.

Install
-------
Copy this whole folder into:  ComfyUI/custom_nodes/ComfyUI-VoiceLibrarySaver
then restart ComfyUI.

No extra dependencies: it only uses torch / torchaudio, which ComfyUI already
requires for its own audio nodes.
"""

import os
import folder_paths


class VoiceLibrarySaver:
    """Save an AUDIO tensor + its transcript into models/voices as a named voice."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO", {
                    "tooltip": "The reference clip to save. Connect a LoadAudio node."
                }),
                "transcript": ("STRING", {
                    "forceInput": True,
                    "tooltip": "The spoken text of the clip. Connect the 'text' output of the "
                               "TTS Audio Suite '✏️ ASR Transcribe' node so it is filled automatically."
                }),
                "voice_name": ("STRING", {
                    "default": "Voice1",
                    "tooltip": "The character name. This becomes the file name AND the [tag] you type "
                               "in the TTS Text node. Example: 'Voice2' -> use [Voice2] in your text."
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
    OUTPUT_NODE = True  # so it runs on every queue even if its outputs are not wired anywhere
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

    # ---- main --------------------------------------------------------------
    def save_voice(self, audio, transcript, voice_name, overwrite=True, subfolder=""):
        import torch
        import torchaudio

        name = self._sanitize(voice_name)
        out_dir = self._voices_dir(subfolder)
        wav_path = os.path.join(out_dir, name + ".wav")
        ref_path = os.path.join(out_dir, name + ".reference.txt")
        txt_path = os.path.join(out_dir, name + ".txt")

        # ComfyUI AUDIO = {"waveform": tensor[B, C, T], "sample_rate": int}
        waveform = audio["waveform"]
        sample_rate = int(audio["sample_rate"])
        if hasattr(waveform, "dim"):
            if waveform.dim() == 3:      # [B, C, T] -> take first item -> [C, T]
                waveform = waveform[0]
            elif waveform.dim() == 1:    # [T] -> [1, T]
                waveform = waveform.unsqueeze(0)
        waveform = waveform.detach().cpu().to(torch.float32)

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
        if not text:
            print(f"[VoiceLibrarySaver] WARNING: empty transcript for '{name}'. "
                  f"Voice cloning quality will suffer. Is the ASR node connected?")

        ui_line = f"✅ {name}  ({status})"
        return {"ui": {"text": [ui_line]}, "result": (name, wav_path)}


NODE_CLASS_MAPPINGS = {
    "VoiceLibrarySaver": VoiceLibrarySaver,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VoiceLibrarySaver": "💾 Save Voice to Library",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
