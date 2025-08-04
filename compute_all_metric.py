import argparse
import torch
import numpy as np
import os

from utils.utils import prepare_json, get_metric

if __name__ == '__main__':
    # Argument parsing
    parser = argparse.ArgumentParser(description='Evaluation')
    parser.add_argument('--clip_model', type=str, default='ViT-B/32',
                        choices=['ViT-B/32', 'open_clip_ViT-L/14'])
    parser.add_argument('--compute_metric_type', type=str, nargs='+',
                        default=['clip-score', 'pac-score', 'pac-score++'])

    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"

    files = []
    for file_json in os.listdir('test_captions'):
        if not file_json.endswith('.json') or file_json == 'reference_captions.json':
            continue
        files.append(file_json)

    for file_json in files:
        print(f"***************Processing file: {file_json}")
        gts, gen, ims_cs, gen_cs, gts_cs = prepare_json(file_json)
        for metric_name in args.compute_metric_type:
            metric = get_metric(metric_name, device="cuda",
                                clip_model=args.clip_model)
            if metric_name != 'standard':
                metric.setup()
            scores = metric.compute_score(
                ims_cs=ims_cs, gen_cs=gen_cs, gts_cs=gts_cs, gts=gts, gen=gen)

            for k, v in scores.items():
                print('%s: %.4f' % (k, v))
