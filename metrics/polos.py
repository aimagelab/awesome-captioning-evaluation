import numpy as np
from .base_metric import BaseMetric
from polos.models import download_model, load_checkpoint
from PIL import Image


class PolosMetric(BaseMetric):
    def __init__(self, device="cuda"):
        self.device = device
        self.model = None

    def setup(self):
        model_path = download_model("polos")
        self.model = load_checkpoint(model_path)

    def prepare_polos_dict(self, ims_cs, gen_cs, gts_cs):
        polos_dict = []
        for i, (im, gen, gts) in enumerate(zip(ims_cs, gen_cs, gts_cs)):
            curr = {
                'img': Image.open(im).convert("RGB"),
                'mt': gen,
                'refs': gts
            }
            polos_dict.append(curr)
        return polos_dict

    def compute_score(self, ims_cs, gen_cs, gts_cs=None, gts=None, gen=None):
        if self.model is None:
            raise RuntimeError(
                "Polos model not initialized. Call setup() first.")

        self.polos_dict = self.prepare_polos_dict(ims_cs, gen_cs, gts_cs)

        _, scores = self.model.predict(
            self.polos_dict, batch_size=10, cuda=(self.device == "cuda"))
        return {f"{self.metric_name.upper()}": np.mean(scores)}
