from .base_metric import BaseMetric
from evaluation import get_all_metrics


class StandardMetric(BaseMetric):
    def __init__(self):
        pass  # No setup or device needed for standard metrics

    def compute_score(self, gts, gen, ims_cs=None, gen_cs=None, gts_cs=None):
        all_scores = {}
        all_scores_metrics = get_all_metrics(gts, gen, return_per_cap=False)

        for k, v in all_scores_metrics.items():
            if k == 'BLEU':
                all_scores['BLEU-4'] = v[-1]  # Only BLEU-4 is kept
            else:
                all_scores[k] = v

        return all_scores
