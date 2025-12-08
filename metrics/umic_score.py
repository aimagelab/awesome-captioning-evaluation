from detectron2.engine import DefaultPredictor
from detectron2.config import get_cfg
from detectron2.data import transforms as T
from detectron2 import model_zoo
"""
    HOW TO INSTALL Detectron2? if you cannot install with the standard method like this
    [instruction](https://detectron2.readthedocs.io/en/latest/tutorials/install.html)
    please review this
    [discussion](https://github.com/facebookresearch/detectron2/discussions/5200).
    this is how I installed Detectron2
    pip install --extra-index-url https://miropsota.github.io/torch_packages_builder detectron2==0.6+18f6958pt2.8.0cu129
"""
import torch
import numpy as np
from torch import device

from .base_metric import BaseMetric
from transformers import BertTokenizer

from models.uniter.model import UniterModel
from utils.config import load_model_paths

from PIL import Image

import math

class UmicScore(BaseMetric):
    """
    This class reproduce the UMIC score which can be applied for ANY new dataset.
    That is the major difference from this class to the [UMIC](https://github.com/hwanheelee1993/UMIC).
    The original work already pre-embedded images of the common datasets like: COMPOSITE, FLICKR, etc.
    Because this class serve a more generic purpose so it would take longer time to run since
    it requires Detectron2 to detect the bounding boxes and its corresponding feature vectors
    in any images (please view the UNITER model on how to use detectron2)
    """

    def __init__(self, rcnn_file="faster_rcnn_R_101_FPN_3x.yaml"):
        """
        :param rcnn_file: name of yaml file to configure detectron2
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.rcnn_file = rcnn_file
        self.IMAGE_DIM = 1024 if self.rcnn_file == "faster_rcnn_R_101_FPN_3x.yaml" else 2048

        
    def setup(self):
        # this class heavily depend on detectron2, is used to embed the input images
        self.load_model()

    def load_model(self):
        self.imageEmbedder = ImageFeatureEmbedder(self.device, self.rcnn_file)
        self.candidateTextEmbedder = CandidateCaptionEmbedder(self.device)

        # You need to have `umic.pt` file in checkpoints folder
        # `umic.pt` can be download from here https://archive.org/download/umic_data/umic.pt sourced in
        # the author of UMIC metric repository
        # https://github.com/hwanheelee1993/UMIC?tab=readme-ov-file#-2-download-the-pretrained-model-
        umic_state = torch.load(load_model_paths()["umic"])
        self.umicModel = UniterModel.from_pretrained(
            config_file="config/uniter-config/uniter-base.json",
            state_dict=umic_state,
            img_dim=self.IMAGE_DIM
        )
        self.umicModel.to(self.device).eval()

        self.rank_output = torch.nn.Linear(self.umicModel.config.hidden_size, 1).cuda()
        self.pooler = self.umicModel.pooler


    def compute_score(
            self,
            ims_cs,
            gen_cs,
            gts_cs,
            gts,
            gen
        ):
        """
        :param ims_cs: Required List<String>, list of path to the image
        :param gen_cs: Required List<String>, list candidate caption
        :param gts_cs: Nullable
        :param gts: Nullable
        :param gen: Nullable
        :return: Float, the UMIC score
        """

        assert len(ims_cs) == len(gen_cs), "list of ims_cs and gen_cs are expected to be the same"

        rank_scores = list()

        for img_path, cand_cap in zip(ims_cs, gen_cs):
            # TODO: This version is currently calculate UMIC score for 1-by-1 image, next task is to
            #  use dataloader to process data in batch.
            image = self.read_image(img_path)
            img_feat, img_box = self.imageEmbedder.embed_image(image)
            img_mask = torch.ones(1, img_feat.shape[1], dtype=torch.long).to(self.device)

            cand_input_ids, cand_input_masks = self.candidateTextEmbedder.tokenize(cand_cap)

            # size of joint_mask is: N + L + 2
            # plus 2 tokens because the CLS (id=101) and SEP (id=102)
            # L is the number of token of cand_cap, or number of tokens of the longest caption in a batch
            joint_mask = torch.cat([img_mask, cand_input_masks], dim=1).to(self.device)
            position_ids = torch.arange(cand_input_ids.shape[1], dtype=torch.long, device=self.device)
            gather_ids = torch\
                .arange(cand_input_ids.shape[1] + img_feat.shape[1], dtype=torch.long, device=self.device)\
                .unsqueeze(0)

            outputs = self.umicModel(
                input_ids=cand_input_ids,
                attention_mask=joint_mask,
                position_ids=position_ids,
                img_feat=img_feat,
                img_pos_feat=img_box,
                gather_index=gather_ids,
                output_all_encoded_layers=False
            )


            pooled_output = self.pooler(outputs)
            scores = self.rank_output(pooled_output)
            rank_scores += [scores.squeeze().detach().cpu().numpy()]

        # this step is refer to UMIC repository
        umic_score = [1/(1+math.exp(-rank_score)) for rank_score in rank_scores] # sigmoid

        return {"umic-score": sum(umic_score)/ len(umic_score)}

    def read_image(self, image_path):
        image = Image.open(image_path)
        return np.array(image)

class ImageFeatureEmbedder:
    """
    Generate image region features + object boxes in UNITER format.
    Outputs:
        img_feat: (1, N, 2048)
        img_pos:  (1, N, 7)
    """
    def __init__(self, device="cuda", file="faster_rcnn_R_101_FPN_3x.yaml"):
        """
        :param device: suggest to have cuda environment to load detectron model
        :param file: name of the detectron config file, if you use other configurations, make sure to place it in
            config/COCO-Detection folder and its base config in config/ folder. For example, I put
            `faster_rcnn_R_101_FPN_3x.yaml` in config/COCO-Detection/ and `Base-RCNN-FPN.yaml` in config/
            You can download other config from https://github.com/facebookresearch/detectron2/tree/main/configs.
            However, please adjust `UmicScore.IMAGE_DIM` and potentially make change to ImageFeatureEmbedder.embed_image
            corresponding to the dimension output of your configuration selection. The UMIC author seems to use
            `faster_rcnn_R_101_C4_3x.yaml` producing 2048 IMAGE_DIM but in this repository I chose
            `faster_rcnn_R_101_FPN_3x.yaml` producing 1024 IMAGE DIM
        """
        self.device = device

        # Load Faster R-CNN R101 FPN config
        self.cfg = get_cfg()
        self.cfg.merge_from_file(f"config/COCO-Detection/{file}")
        self.cfg.MODEL.WEIGHTS = model_zoo.get_checkpoint_url(
            f"COCO-Detection/{file}"
        )
        self.cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.2
        self.cfg.MODEL.DEVICE = device

        # Preprocessing augmentation
        self.aug = T.ResizeShortestEdge(
            [self.cfg.INPUT.MIN_SIZE_TEST, self.cfg.INPUT.MIN_SIZE_TEST],
            self.cfg.INPUT.MAX_SIZE_TEST
        )

        # Build predictor and raw model
        self.predictor = DefaultPredictor(self.cfg)
        self.model = self.predictor.model.eval()

    def _boxes_to_uniter_7d(self, boxes, img_h, img_w):
        """
        Convert (N,4) → (N,7): [x1, y1, x2, y2, W, H, area]
        reference from UNITER model paper https://arxiv.org/pdf/1909.11740
        """
        x1, y1, x2, y2 = (
            boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        )
        area = (x2 - x1) * (y2 - y1)

        pos = np.stack([
            x1, y1, x2, y2,
            np.full_like(area, img_w),
            np.full_like(area, img_h),
            area
        ], axis=1)

        return pos  # (N, 7)

    def embed_image(self, img):
        """
        :param pil_image: PIL.Image instance, RGB
        :return: a tuple of 2: (1, N, 2048) features, (1, N, 7) positional features. Normally, N is 1000
        """

        img_h, img_w = img.shape[:2]

        # detectron2 expects BGR channel order
        img_bgr = img[:, :, ::-1]

        # apply resizing augmentation
        transform = self.aug.get_transform(img_bgr)
        img_trans = transform.apply_image(img_bgr)

        # convert to CHW tensor
        img_tensor = torch.as_tensor(
            img_trans.astype("float32").transpose(2, 0, 1)
        )

        inputs = [{
            "image": img_tensor.to(self.device),
            "height": img_h,
            "width": img_w
        }]

        # Extract FPN region features
        with torch.no_grad():
            images = self.model.preprocess_image(inputs)
            features = self.model.backbone(images.tensor)

            # Proposals
            proposals, _ = self.model.proposal_generator(images, features, None)

            # RoIAlign pooled features
            box_features = self.model.roi_heads.box_pooler(
                [features[f] for f in self.model.roi_heads.in_features],
                [p.proposal_boxes for p in proposals]
            )

            # Final FC box head (gives 2048-D vectors)
            box_features = self.model.roi_heads.box_head(box_features)
            region_features = box_features.cpu().numpy()  # (N, 2048)

        # --- Step 5: bounding boxes ---
        boxes = proposals[0].proposal_boxes.tensor.cpu().numpy()  # (N, 4)

        # --- Step 6: convert boxes → 7D ---
        pos_7d = self._boxes_to_uniter_7d(boxes, img_h, img_w)  # (N, 7)

        # --- Step 7: add batch dimension ---
        img_feat = region_features[None, :, :]   # (1, N, 1024)
        img_pos  = pos_7d[None, :, :]            # (1, N, 7)

        # assert img_feat.shape[2] == 1024, "dimension of image feature is not 1024"
        assert img_pos.shape[2] == 7, "dimension of image box is not 7"
        assert img_feat.shape[1] == img_pos.shape[1], "N is not equal for img_feat and img_pos"

        return (torch.from_numpy(img_feat).to(self.device),
                torch.from_numpy(img_pos).to(self.device))

class CandidateCaptionEmbedder:
    def __init__(self, device="cuda"):
        """
        This class is a rework from UMIC repository, please check their original work in
        https://github.com/hwanheelee1993/UMIC/blob/master/make_txt_db.py
        :param device:
        """
        self.device = device
        self.tokenizer = BertTokenizer.from_pretrained("google-bert/bert-base-uncased")

    def tokenize(self, cand_caption):
        """
        This function is basically just to "map" each token/word into a single number.
        The original work of UMIC author was to do it manually which does not include the [CLS]-101
        and [SEP]-102 token. Original version is
        https://github.com/hwanheelee1993/UMIC/blob/9d897ee575d754dada84e00da426bbceabffc450/make_txt_db.py#L18
        The only difference is my work has CLS at beginning and SEP at the end of each sequence
        :param cand_caption:
        :return:
        """

        tokens = self.tokenizer(
            cand_caption,
            return_tensors="pt",
            padding=True,
            truncation=True
        )
        # input_ids = []
        # for word in cand_caption.split():
        #     ws = self.tokenizer.tokenize(word)
        #     if not ws:
        #         # some special char
        #         continue
        #     input_ids.extend(self.tokenizer.convert_tokens_to_ids(ws))
        # input_ids = torch.from_numpy(np.array(input_ids)).unsqueeze(0)
        # mask = torch.ones(input_ids.shape, dtype=torch.long)

        return tokens["input_ids"].to(self.device), tokens["attention_mask"].to(self.device)
        # return input_ids.to(self.device), mask.to(self.device)
