import torch
import json
import evaluation
import os
from metrics.clip_score import ClipScoreMetric
from metrics.polos import PolosMetric
from metrics.standard import StandardMetric


def collate_fn(batch):
    if isinstance(batch, tuple) and isinstance(batch[0], list):
        return batch
    elif isinstance(batch, list):
        transposed = list(zip(*batch))
        return [collate_fn(samples) for samples in transposed]
    return torch.utils.data.default_collate(batch)


def prepare_json(file_json):
    with open('test_captions/reference_captions.json', 'r') as f:
        references = json.load(f)

    # check if file exist
    if os.path.isfile('test_captions/' + file_json):
        with open('test_captions/' + file_json, 'r') as f:
            data = json.load(f)
    else:
        print(
            f"File {file_json} not found in test_captions/.")

    gen = {}
    gts = {}

    ims_cs = list()
    gen_cs = list()
    gts_cs = list()

    for i, d in enumerate(data):  # k = name img, v=cand
        if isinstance(d, dict):
            name = list(d.keys())[0]
            gen_i = d[name]
            d = list(d.keys())[0]
        else:
            gen_i = data[d]
        im_i = 'your-path/COCO_val2014_' + \
            d.zfill(12) + '.jpg'

        gts_i = references[d]
        gen['%d' % (i)] = [gen_i, ]
        gts['%d' % (i)] = gts_i

        ims_cs.append(im_i)
        gen_cs.append(gen_i)
        gts_cs.append(gts_i)

    gts = evaluation.PTBTokenizer.tokenize(gts)
    gen = evaluation.PTBTokenizer.tokenize(gen)

    return gts, gen, ims_cs, gen_cs, gts_cs


def get_metric(name, **kwargs):
    name = name.lower()
    if name == "clip-score" or name == "pac-score" or name == "pac-score++":
        return ClipScoreMetric(metric_name=name, **kwargs)
    elif name == "polos":
        return PolosMetric(device=kwargs.get("device"))
    elif name == "standard":
        return StandardMetric()
    else:
        raise ValueError(f"Unknown metric: {name}")
