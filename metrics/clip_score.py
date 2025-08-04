import torch
import numpy as np
from .base_metric import BaseMetric
from models.clip import clip
from models.clip_lora import clip_lora
from models import open_clip
from evaluation import PACScore, RefPACScore
from utils.config import load_model_paths


class ClipScoreMetric(BaseMetric):
    def __init__(self, device, clip_model='ViT-B/32', metric_name='clip-score'):
        self.device = device
        self.clip_model = clip_model
        self.metric_name = metric_name

        if self.metric_name == "pac-score++" or self.metric_name == "clip-score":
            self.weight = 2.5
        elif self.metric_name == 'pac-score':
            self.weight = 2.0
        else:
            raise ValueError(f"Unknown metric name: {self.metric_name}")

        self.model_paths = load_model_paths()
        self.model = None
        self.preprocess = None

    def setup(self):
        if self.clip_model.startswith("open_clip"):
            print(f"Loading OpenCLIP model: {self.clip_model}")
            model, _, preprocess = open_clip.create_model_and_transforms(
                'ViT-L-14', pretrained='laion2b_s32b_b82k'
            )
        elif self.metric_name == 'pac-score++':
            print(f"Loading PAC-S++ model: {self.clip_model}")
            model, preprocess = clip_lora.load(
                self.clip_model, device=self.device, lora=4)
        else:
            print(f"Loading CLIP model: {self.clip_model}")
            model, preprocess = clip.load(self.clip_model, device=self.device)

        model = model.to(self.device).float()

        if self.metric_name.startswith("pac-score"):
            checkpoint_path = self.model_paths[f"{self.metric_name}_{self.clip_model}"]
            print(f"Loading: {checkpoint_path}")
            checkpoint = torch.load(checkpoint_path)
            model.load_state_dict(checkpoint["state_dict"])

        model.eval()
        self.model = model
        self.preprocess = preprocess

    def compute_score(self, ims_cs, gen_cs, gts_cs=None, gts=None, gen=None):
        if self.model is None:
            raise RuntimeError(
                "CLIP model not initialized. Call setup() first.")

        scores = {}
        mean, clip_scores, candidate_feats, _ = PACScore(
            self.model, self.preprocess, ims_cs, gen_cs, self.device, w=self.weight
        )
        scores[f"{self.metric_name.upper()}"] = mean

        if gts_cs:
            _, per_instance_text_text = RefPACScore(
                self.model, gts_cs, candidate_feats, self.device
            )
            refclip_scores = 2 * clip_scores * per_instance_text_text / (
                clip_scores + per_instance_text_text
            )
            scores[f"Ref_{self.metric_name.upper()}"] = np.mean(refclip_scores)

        return scores
