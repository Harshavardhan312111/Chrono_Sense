"""
Minimal runtime wrapper for the official MMA-DFER checkpoint.

This loads the authors' DFEW checkpoint directly with a rolling 16-frame face
buffer and a zero-audio input fallback so the model can be used in the current
camera pipeline without waiting for an ONNX export.
"""

from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict, deque
from pathlib import Path
from types import SimpleNamespace

import cv2

LOGGER = logging.getLogger(__name__)

MODULE_ROOT = Path(__file__).resolve().parent
VENDOR_PY = MODULE_ROOT / ("vendor-py313" if sys.version_info[:2] == (3, 13) else "vendor-py")
FALLBACK_VENDOR_PY = MODULE_ROOT / "vendor-py"
VENDOR_REPO = MODULE_ROOT / "vendor" / "mma_dfer_repo"
for candidate in (VENDOR_PY, FALLBACK_VENDOR_PY, VENDOR_REPO):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.append(str(candidate))

import torch
import torch.nn as nn

from models.Generate_Model import GenerateModel, PatchEmbed_new
from models import models_vit
from AudioMAE import audio_models_vit


DFEW_LABELS = [
    "Happy",
    "Sad",
    "Neutral",
    "Angry",
    "Surprise",
    "Disgust",
    "Fear",
]


class MMADFERInferenceModel(GenerateModel):
    """Official architecture without external pretrain checkpoint dependencies."""

    def _build_audio_model(
        self,
        model_name="vit_base_patch16",
        drop_path_rate=0.1,
        global_pool=False,
        mask_2d=True,
        use_custom_patch=False,
        ckpt_path="audiomae_pretrained.pth",
    ):
        del ckpt_path
        self.audio_model = audio_models_vit.__dict__[model_name](
            drop_path_rate=drop_path_rate,
            global_pool=global_pool,
            mask_2d=mask_2d,
            use_custom_patch=use_custom_patch,
            n_seq=self.n_audio,
            n_progr=self.n_progr,
        )
        emb = torch.randn(
            1,
            self.n_audio + self.n_progr * (len(self.audio_model.blocks) // 6) + 1,
            768,
        )
        self.audio_model.patch_embed = PatchEmbed_new(
            img_size=(512, 128),
            patch_size=(16, 16),
            in_chans=1,
            embed_dim=768,
            stride=16,
        )
        self.audio_model.pos_embed = nn.Parameter(emb, requires_grad=False)

    def _build_image_model(
        self,
        model_name="vit_base_patch16",
        ckpt_path="./mae_face_pretrain_vit_base.pth",
        global_pool=False,
        num_heads=12,
        drop_path_rate=0.1,
        img_size=224,
        n_frames=16,
    ):
        del ckpt_path
        self.image_encoder = getattr(models_vit, model_name)(
            global_pool=global_pool,
            num_classes=num_heads,
            drop_path_rate=drop_path_rate,
            img_size=img_size,
            n_seq=self.n_image,
            n_progr=self.n_progr,
            n_frames=n_frames,
        )
        pos_embed = torch.randn(
            1,
            self.image_encoder.pos_embed.size(1) + (len(self.image_encoder.blocks)) * self.n_progr // 6,
            768,
        )
        pos_embed[:, : -(len(self.image_encoder.blocks)) * self.n_progr // 6, :] = self.image_encoder.pos_embed
        self.image_encoder.pos_embed = nn.Parameter(pos_embed)


class MMADFERCheckpointRuntime:
    def __init__(self, checkpoint_path, image_size=112, sequence_length=16):
        self.checkpoint_path = str(checkpoint_path)
        self.image_size = int(image_size)
        self.sequence_length = int(sequence_length)
        self.device = torch.device("cpu")
        self.frame_buffers = defaultdict(lambda: deque(maxlen=self.sequence_length))
        self.model = self._load_model()
        self.model.eval()
        self.model.to(self.device)
        torch.set_grad_enabled(False)
        LOGGER.info(
            "MMA-DFER checkpoint runtime ready "
            f"(checkpoint={self.checkpoint_path}, image_size={self.image_size}, sequence_length={self.sequence_length})"
        )

    def _load_model(self):
        self._prepare_pickle_compat()
        args = SimpleNamespace(
            temporal_layers=1,
            number_class=len(DFEW_LABELS),
            img_size=self.image_size,
        )
        model = MMADFERInferenceModel(args=args)
        checkpoint = torch.load(self.checkpoint_path, map_location="cpu", weights_only=False)
        state_dict = checkpoint.get("state_dict", checkpoint)
        normalized_state = {
            key[7:] if key.startswith("module.") else key: value
            for key, value in state_dict.items()
        }
        load_result = model.load_state_dict(normalized_state, strict=False)
        LOGGER.info(
            "Loaded MMA-DFER checkpoint state "
            f"(missing={len(load_result.missing_keys)}, unexpected={len(load_result.unexpected_keys)})"
        )
        return model

    @staticmethod
    def _prepare_pickle_compat():
        main_module = sys.modules.get("__main__")
        if main_module is None:
            return
        if not hasattr(main_module, "RecorderMeter"):
            class RecorderMeter:  # noqa: D401
                """Compatibility shim for official MMA-DFER checkpoints."""

                def __init__(self, *args, **kwargs):
                    del args, kwargs

            setattr(main_module, "RecorderMeter", RecorderMeter)

    def infer(self, face_roi, track_key):
        tensor = self._face_to_tensor(face_roi)
        buffer = self.frame_buffers[str(track_key or "anonymous")]
        buffer.append(tensor)
        sequence = self._sequence_tensor(list(buffer))
        audio = torch.zeros((1, 1, 512, 128), dtype=torch.float32, device=self.device)
        with torch.no_grad():
            logits = self.model(sequence, audio)
            probabilities = torch.softmax(logits, dim=1)[0].cpu().tolist()
        fill_ratio = min(1.0, len(buffer) / float(self.sequence_length))
        adjusted = [score * fill_ratio for score in probabilities]
        best_index = max(range(len(adjusted)), key=lambda index: adjusted[index])
        return {
            "emotion": DFEW_LABELS[best_index],
            "confidence": float(adjusted[best_index]),
            "all_scores": {
                label: round(float(adjusted[index]), 4)
                for index, label in enumerate(DFEW_LABELS)
            },
            "buffer_size": len(buffer),
            "fill_ratio": round(fill_ratio, 4),
        }

    def _face_to_tensor(self, face_roi):
        resized = cv2.resize(face_roi, (self.image_size, self.image_size), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).to(torch.float32).div(255.0)
        return tensor

    def _sequence_tensor(self, buffered_frames):
        frames = list(buffered_frames)
        if not frames:
            frames = [torch.zeros((3, self.image_size, self.image_size), dtype=torch.float32)]
        while len(frames) < self.sequence_length:
            frames.append(frames[-1].clone())
        frames = frames[-self.sequence_length :]
        stacked = torch.stack(frames, dim=0).unsqueeze(0)
        return stacked.to(self.device)
