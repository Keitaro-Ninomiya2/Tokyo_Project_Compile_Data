import mmengine
#!/usr/bin/env python

# Copyright (c) 2023, National Diet Library, Japan
#
# This software is released under the CC BY 4.0.
# https://creativecommons.org/licenses/by/4.0/

import os
import argparse
import glob
import cv2
import numpy as np
import mmcv
from mmdet.apis import (inference_detector, init_detector)

import time

# default parameters
DEFAULT_CONFIG_PATH = 'models/separate_page/cascade_rcnn_r50_fpn_1x_ndl_1024.py'
DEFAULT_MODEL_PATH  = 'models/separate_page/model.pth'
DEFAULT_INPUT_PATH  = 'inference_input'
DEFAULT_OUTPUT_PATH = 'inference_output'
DEFAULT_LEFT_FOOTER   = '_L'
DEFAULT_RIGHT_FOOTER  = '_R'
DEFAULT_SINGLE_FOOTER = '_S'


def generate_class_colors(class_num):
    colors = 255 * np.ones((class_num, 3), dtype=np.uint8)
    colors[:, 0] = np.linspace(0, 179, class_num)
    colors = cv2.cvtColor(colors[None, ...], cv2.COLOR_HSV2BGR)[0]
    return colors


def draw_legand(img, origin, classes, colors, ssz: int = 16):
    c_num = len(classes)
    x, y = origin[0], origin[1]
    for c in range(c_num):
        color = colors[c]
        color = (int(color[0]), int(color[1]), int(color[2]))
        text = classes[c]
        img = cv2.rectangle(img, (x, y), (x + ssz - 1, y + ssz - 1), color, -1)
        img = cv2.putText(img, text, (x + ssz, y + ssz), cv2.FONT_HERSHEY_PLAIN,
                          1, (255, 0, 0), 1, cv2.LINE_AA)
        y += ssz
    return img


class GutterDetector:
    def __init__(self, config: str, checkpoint: str, device: str):
        print(f'load from config={config}, checkpoint={checkpoint}')
        self.load(config, checkpoint, device)
        cfg = mmengine.Config.fromfile(config)
        self.classes = cfg.classes
        self.colors = generate_class_colors(len(self.classes))

    def load(self, config: str, checkpoint: str, device: str):
        self.model = init_detector(config, checkpoint, device)
        # PATCH: Manual GPU Override for MMDetection 3.x (V12)
        if hasattr(self.model, "cfg"):
            clean_pipeline = [
                dict(type="LoadImageFromFile"),
                dict(type="Resize", scale=(1024, 1024), keep_ratio=True),
                dict(type="PackDetInputs", meta_keys=("img_id", "img_path", "ori_shape", "img_shape", "scale_factor"))
            ]
            try:
                import torch
                from mmengine.config import ConfigDict
                from mmdet.models.data_preprocessors import DetDataPreprocessor
                
                self.model.cfg.data.test.pipeline = clean_pipeline
                self.model.cfg.test_pipeline = clean_pipeline
                if not hasattr(self.model.cfg, "test_dataloader"):
                    self.model.cfg.test_dataloader = ConfigDict({"dataset": ConfigDict({"pipeline": clean_pipeline})})
                
                class NuclearPreprocessor(DetDataPreprocessor):
                    def forward(self, data, training=False):
                        inputs = data["inputs"]
                        batch = torch.stack(inputs).float().cuda()
                        mean = torch.tensor([123.675, 116.28, 103.53], device="cuda").view(1, 3, 1, 1)
                        std = torch.tensor([58.395, 57.12, 57.375], device="cuda").view(1, 3, 1, 1)
                        batch = batch[:, [2, 1, 0], ...]
                        batch = (batch - mean) / std
                        data["inputs"] = batch
                        return data
                
                preprocessor = NuclearPreprocessor()
                preprocessor.cuda()
                self.model.data_preprocessor = preprocessor
            except Exception as e:
                print(f"[Patch Error] {e}")
                class NuclearPreprocessor(DetDataPreprocessor):
                    def forward(self, data, training=False):
                        inputs = data["inputs"]
                        batch = torch.stack(inputs).float().cuda()
                        mean = torch.tensor([123.675, 116.28, 103.53], device="cuda").view(1, 3, 1, 1)
                        std = torch.tensor([58.395, 57.12, 57.375], device="cuda").view(1, 3, 1, 1)
                        batch = batch[:, [2, 1, 0], ...]
                        batch = (batch - mean) / std
                        data["inputs"] = batch
                        return data
                
                preprocessor = NuclearPreprocessor()
                preprocessor.cuda()
                self.model.data_preprocessor = preprocessor
                
            except Exception as e:
                print(f"[Patch Error] {e}")
                class NuclearPreprocessor(DetDataPreprocessor):
                    def forward(self, data, training=False):
                        # 1. Extract inputs (List of Tensors)
                        inputs = data["inputs"]
                        # 2. Stack them into a Batch Tensor
                        batch = torch.stack(inputs)
                        # 3. Move to GPU and convert to Float
                        batch = batch.float().cuda()
                        # 4. Manual Normalization (ImageNet stats)
                        mean = torch.tensor([123.675, 116.28, 103.53], device="cuda").view(1, 3, 1, 1)
                        std = torch.tensor([58.395, 57.12, 57.375], device="cuda").view(1, 3, 1, 1)
                        # 5. BGR -> RGB (Flip channels)
                        batch = batch[:, [2, 1, 0], ...]
                        # 6. Normalize
                        batch = (batch - mean) / std
                        
                        data["inputs"] = batch
                        return data
                
                # Inject the new brain (Initialize first, THEN move to cuda)
                preprocessor = NuclearPreprocessor()
                preprocessor.cuda()
                self.model.data_preprocessor = preprocessor
                
            except Exception as e:
                print(f"[Patch Error] {e}")
                class NuclearPreprocessor(DetDataPreprocessor):
                    def forward(self, data, training=False):
                        # 1. Extract inputs (List of Tensors)
                        inputs = data["inputs"]
                        # 2. Stack them into a Batch Tensor
                        batch = torch.stack(inputs)
                        # 3. Move to GPU and convert to Float
                        batch = batch.float().cuda()
                        # 4. Manual Normalization (ImageNet stats)
                        mean = torch.tensor([123.675, 116.28, 103.53], device="cuda").view(1, 3, 1, 1)
                        std = torch.tensor([58.395, 57.12, 57.375], device="cuda").view(1, 3, 1, 1)
                        # 5. BGR -> RGB (Flip channels)
                        batch = batch[:, [2, 1, 0], ...]
                        # 6. Normalize
                        batch = (batch - mean) / std
                        
                        data["inputs"] = batch
                        return data
                
                # Inject the new brain
                self.model.data_preprocessor = NuclearPreprocessor(device="cuda")
                
            except Exception as e:
                print(f"[Patch Error] {e}")
                class GPUForcedPreprocessor(DetDataPreprocessor):
                    def forward(self, data, training=False):
                        # Force inputs to GPU immediately
                        if "inputs" in data:
                            data["inputs"] = [t.cuda() for t in data["inputs"]]
                        return super().forward(data, training)
                
                preprocessor = GPUForcedPreprocessor(
                    mean=[123.675, 116.28, 103.53], 
                    std=[58.395, 57.12, 57.375], 
                    bgr_to_rgb=True, 
                    pad_size_divisor=32
                )
                self.model.data_preprocessor = preprocessor
                self.model.data_preprocessor.to(self.model.device)
                
            except Exception as e:
                print(f"[Patch Error] {e}")
    def predict(self, img):
        # PATCH: Convert MMDetection 3.x Output to 2.x Format (V14)
        result = inference_detector(self.model, img)
        try:
            if not isinstance(result, (tuple, list)):
                import numpy as np
                pred = result.pred_instances.cpu().numpy()
                bboxes = pred.bboxes
                scores = pred.scores
                labels = pred.labels
                
                if len(bboxes) == 0:
                    # Return empty list of arrays if nothing found
                    return [np.zeros((0, 5), dtype=np.float32)]
                    
                dets = np.hstack((bboxes, scores[:, None]))
                
                num_classes = 1
                if hasattr(self.model, "dataset_meta") and "classes" in self.model.dataset_meta:
                    num_classes = len(self.model.dataset_meta["classes"])
                elif len(labels) > 0:
                    num_classes = max(labels) + 1
                
                bbox_results = []
                for i in range(num_classes):
                    bbox_results.append(dets[labels == i])
                
                # V14 FIX: Return the LIST directly, not a tuple
                return bbox_results
        except Exception as e:
            print(f"[Conversion Error] {e}")
        return result
    def show(self, img_path: str, result, score_thr: float = 0.1, border: int = 3,
             show_legand: bool = True):
        img = cv2.imread(img_path)

        for c in range(len(result)):
            max_conf = 0.0
            max_idx  = None
            for idx, pred in enumerate(result[c]):
                if max_conf < pred[4]:
                    max_conf = pred[4]
                    max_idx  = idx
                if float(pred[4]) < score_thr:
                    continue
                x0, y0 = int(pred[0]), int(pred[1])
                x1, y1 = int(pred[2]), int(pred[3])
                img = cv2.rectangle(img, (x0, y0), (x1, y1), (255, 128, 128), border)

            if max_idx is not None:
                pred = result[c][max_idx]
                x0, y0 = int(pred[0]), int(pred[1])
                x1, y1 = int(pred[2]), int(pred[3])
                center = (img.shape[1]//2, img.shape[0]//2)
                img = cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 255), border)
                img = cv2.line(img, ((x0+x1)//2, 0), ((x0+x1)//2, y0+200), (0, 0, 255), border)
                img = cv2.line(img, ((x0+x1)//2, y1-200), ((x0+x1)//2, img.shape[0]),
                               (0, 0, 255), border)
                sz = max(img.shape[0], img.shape[1])
                scale = 1024.0 / sz
                img = cv2.putText(img, f'{pred[4]:0.3f}', center,
                                  cv2.FONT_HERSHEY_PLAIN, 1.5/scale,
                                  (0, 0, 255), int(1.0/scale), cv2.LINE_AA)

        return img

    def divide(self, input_img, result, score_thr: float = 0.2):
        if isinstance(input_img, str):
            img = cv2.imread(input_img)
        else:
            img = input_img

        max_conf = 0.0
        max_idx  = None
        for idx, pred in enumerate(result[0]):
            if max_conf < pred[4] and score_thr < pred[4]:
                max_conf = pred[4]
                max_idx  = idx

        if max_idx is not None:
            pred = result[0][max_idx]
            x_center = (int(pred[0])+int(pred[2]))//2
            img_L = img[:, 0: x_center]
            img_R = img[:, x_center:]
            return [img_L, img_R]
        else:
            return [img, None]

    def pred_and_divide(self, img, score_thr: float = 0.2):
        result = inference_detector(self.model, img)

        max_conf = 0.0
        max_idx  = None
        for idx, pred in enumerate(result[0]):
            if max_conf < pred[4] and score_thr < pred[4]:
                max_conf = pred[4]
                max_idx  = idx

        if max_idx is not None:
            pred = result[0][max_idx]
            x_center = (int(pred[0])+int(pred[2]))//2
            img_L = img[:, 0: x_center]
            img_R = img[:, x_center:]
            return [img_L, img_R]
        else:
            return [img, None]

    def draw_rects_with_data(self, img, result, score_thr: float = 0.3,
                             border: int = 3, show_legand: bool = True):
        for c in range(len(result)):
            color = self.colors[c]
            color = (int(color[0]), int(color[1]), int(color[2]))
            for pred in result[c]:
                if float(pred[4]) < score_thr:
                    continue
                x0, y0 = int(pred[0]), int(pred[1])
                x1, y1 = int(pred[2]), int(pred[3])
                img = cv2.rectangle(img, (x0, y0), (x1, y1), color, border)

        sz = max(img.shape[0], img.shape[1])
        scale = 1024.0 / sz
        img = cv2.resize(img, dsize=None, fx=scale, fy=scale)

        if show_legand:
            ssz = 16
            c_num = len(self.classes)
            org_width = img.shape[1]
            img = cv2.copyMakeBorder(
                img, 0, 0, 0, 8 * c_num, cv2.BORDER_REPLICATE)
            x = org_width
            y = img.shape[0] - ssz * c_num
            img = draw_legand(img, (x, y), self.classes, self.colors, ssz=ssz)

        return img


def divide_facing_page(input, output: str = "NO_DUMP",
                       left: str = '_L', right: str = '_R', single: str = '_S',
                       ext: str = '.jpg', quality: int = 100,
                       log: str = 'trim_pos.tsv',
                       conf_th: float = 0.2,
                       config: str = DEFAULT_CONFIG_PATH,
                       checkpoint: str = DEFAULT_MODEL_PATH,
                       device: str = 'cuda:0', dump_rect: str = None):

    print(f'Loading model: {checkpoint}')
    print(f'       Config: {config}')
    print(f'       device: {device}')
    detector = GutterDetector(config, checkpoint, device)

    if log:
        if not os.path.exists(log):
            with open(log, mode='a') as f:
                line = 'image_name\ttrimming_x\n'
                f.write(line)

    img_path_list = []
    if os.path.isdir(input):
        img_path_list = list(glob.glob(os.path.join(input, "*")))
    else:
        img_path_list = [input]

    if dump_rect is not None:
        os.makedirs(dump_rect, exist_ok=True)
    if output is not None and output != 'NO_DUMP':
        os.makedirs(output, exist_ok=True)

    print('start inference')
    time_sta = time.time()  # for debug

    for img_path in img_path_list:
        print(f'processing ... {img_path}')
        result = detector.predict(img_path)

        if dump_rect is not None:  # for debug
            img = detector.show(img_path, result, score_thr=conf_th, border=5)
            cv2.imwrite(os.path.join(dump_rect, os.path.basename(img_path)), img)

        basename, ext_ori = os.path.splitext(os.path.basename(img_path))
        img_L, img_R = None, None
        if output is not None and output != 'NO_DUMP':
            img_L, img_R = detector.divide(img_path, result, score_thr=conf_th)
            if img_R is not None:
                cv2.imwrite(os.path.join(output, basename + left + ext), img_L, [cv2.IMWRITE_JPEG_QUALITY, quality])
                cv2.imwrite(os.path.join(output, basename + right + ext), img_R, [cv2.IMWRITE_JPEG_QUALITY, quality])
            else:
                cv2.imwrite(os.path.join(output, basename+single+ext), img_L, [cv2.IMWRITE_JPEG_QUALITY, quality])

        if log is not None:
            basename, ext_ori = os.path.splitext(os.path.basename(img_path))
            if img_R is None:
                with open(log, mode='a') as f:
                    line = '{}\t{}\n'.format(basename+single+ext, 0)
                    f.write(line)
            else:
                _, w, _ = img_L.shape
                with open(log, mode='a') as f:
                    f.write('{}\t{}\n'.format(basename+left+ext, w-1))
                    f.write('{}\t{}\n'.format(basename+right+ext, w))

    t = time.time() - time_sta
    print(f'{t:.6} [sec] / {len(img_path_list)} imgs')  # for debug

def divide_facing_page_with_cli(
    input,
    detector,
    output: str = "NO_DUMP",
    log: str = 'trim_pos.tsv',
    conf_th: float = 0.2,
    dump_rect: str = None):

    if log:
        if not os.path.exists(log):
            with open(log, mode='a') as f:
                line = 'image_name\ttrimming_x\n'
                f.write(line)

    img_path_list = [input]

    # print('start inference')
    time_sta = time.time()

    for img_data in img_path_list:
        result = detector.predict(img_data)

        output_img_list = []
        img_L, img_R = None, None

        img_L, img_R = detector.divide(img_data, result, score_thr=conf_th)
        if img_R is not None:
            output_img_list.append(img_L)
            output_img_list.append(img_R)
        else:
            output_img_list.append(img_L)

    t = time.time() - time_sta
    print(f'{t:.6} [sec] / {len(img_path_list)} imgs')  # for debug
    return output_img_list


def parse_args():
    usage = 'python3 {} [-i INPUT] [-o OUTPUT] [-l LEFT] [-r RIGHT] [-s SINGLE] [-e EXT] [-q QUALITY] [-c CONFIG] [-w WEIGHT]'.format(__file__)
    argparser = argparse.ArgumentParser(
        usage=usage,
        description='Divide facing images at the gutter',
        formatter_class=argparse.RawTextHelpFormatter)
    argparser.add_argument(
        '-i',
        '--input',
        default=DEFAULT_INPUT_PATH,
        help='input image file or directory path\n'
             f'(default: {DEFAULT_INPUT_PATH})',
        type=str)
    argparser.add_argument(
        '-o',
        '--out',
        default=DEFAULT_OUTPUT_PATH,
        help=f'directory path (default: {DEFAULT_OUTPUT_PATH})\n'
             'if OUT is "NO_DUMP", dumping no images',
        type=str)
    argparser.add_argument(
        '-l',
        '--left',
        default='_L',
        help='file name footer of left side page image to be output\n'
             f'e.g) input image:  input.jpg, Default: {DEFAULT_LEFT_FOOTER}\n'
             '     output image: input_01.jpg',
        type=str)
    argparser.add_argument(
        '-r',
        '--right',
        default='_R',
        help='file name footer of right side page image to be output\n'
             f'e.g) input image:  input.jpg, Default: {DEFAULT_RIGHT_FOOTER}\n'
             '     output image: input_R.jpg',
        type=str)
    argparser.add_argument(
        '-s',
        '--single',
        default='_S',
        help='File name footer of the image with no detected gutters to be output\n'
             f'e.g) input image:  input.jpg, Default: {DEFAULT_SINGLE_FOOTER}\n'
             '     output image: input_S.jpg',
        type=str)
    argparser.add_argument(
        '-e',
        '--ext',
        default='.jpg',
        help='Output image file extension. Default: .jpg \n'
             'If EXT is \"SAME\", the same extension as the input image will be used.',
        type=str)
    argparser.add_argument(
        '-q', '--quality',
        default=100,
        dest='quality',
        help='Output jpeg image quality.\n'
             '1 is worst quality and smallest file size,\n'
             'and 100 is best quality and largest file size.\n'
             '[1, 100], default: 100',
        type=int)
    argparser.add_argument(
        '--log',
        default=None,
        help='path of the tsv file that records the split x position'
             'output format:'
             'file name <tab> trimming_x',
        type=str)
    argparser.add_argument(
        '-c', '--config',
        default=DEFAULT_CONFIG_PATH,
        help=f'Model config file path. default: {DEFAULT_CONFIG_PATH}',
        type=str
    )
    argparser.add_argument(
        '-w', '--weight',
        default=DEFAULT_MODEL_PATH,
        help=f'Model weight pth file path. Default: {DEFAULT_MODEL_PATH}',
        type=str
    )
    argparser.add_argument(
        '--debug',
        help='Debug mode flag',
        action='store_true')
    return argparser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    if args.out != "NO_DUMP":
        os.makedirs(args.out, exist_ok=True)
    else:
        print('Not dump split images')

    if args.debug:
        print('Run in debug mode: dump images added bounding box and gutter lines')
    if args.log is not None:
        print('Export estimated gutter position to {}'.format(args.log))

    divide_facing_page(input=args.input, output=args.out,
                       left=args.left, right=args.right, single=args.single,
                       ext=args.ext, quality=args.quality,
                       log=args.log,
                       conf_th=0.2,
                       config=args.config, checkpoint=args.weight,
                       device='cuda:0')
