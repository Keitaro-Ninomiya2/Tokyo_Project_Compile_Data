# convert annotation tsv file to coco annotation format
# annotation tsv: filename<tab>roll, roll is [-0.5, 0.5]

import argparse
import os
import pandas as pd
from enum import IntEnum, auto
import cv2
import tqdm


class Category(IntEnum):
    GUTTER = 0
    VOID = auto()


categories = [
    {'id': int(Category.GUTTER),  'name': 'gutter', 'org_name': 'ノド元'},
    {'id': int(Category.VOID),  'name': 'void', 'org_name': 'void'}
]
categories_org_name_index = {elem['org_name']: elem for elem in categories}
categories_name_index = {elem['name']: elem for elem in categories}


def org_name_to_id(s: str):
    return categories_org_name_index[s]['id']


def get_contour_from_bbox(x1, y1, x2, y2):
    w = x2 - x1
    h = y2 - y1
    area = w * h
    contour = [x1, y1, x2, y1, x2, y2, x1, y2]
    return contour, area


def convert_to_coco(df, img_dir):
    output = {'images': [], 'annotations': []}
    image_id = 0
    annotation_id = 0

    num_rows = len(df)

    for i, r in tqdm.tqdm(df.iterrows(), total=num_rows):
        img_path = os.path.join(img_dir, r['filename'])
        if not os.path.exists(img_path):
            print(f'WARN: {img_path} is not found and skip this sample')
            continue
        img = cv2.imread(img_path, cv2.IMREAD_COLOR)
        h, w, _ = img.shape
        x1 = int(w * max(float(r['roll'])+0.5-0.02, 0.01))
        x2 = int(w * min(float(r['roll'])+0.5+0.02, 0.99))
        y1 = int(float(h)*0.02)
        y2 = int(float(h)*0.98)

        image = {'file_name': r['filename'],
                 'width': w,
                 'height': h,
                 'id': image_id}
        output['images'].append(image)
        bbox = [x1, y1, x2-x1, y2-y1]  # x, y, bbox_width, bbox_height
        contour, area = get_contour_from_bbox(x1, y1, x2, y2)
        ann = {'image_id': image_id,
               'id': annotation_id,
               'bbox': bbox,
               'area': area,
               'iscrowd': 0,
               'category_id': org_name_to_id('ノド元')}
        ann['segmentation'] = [contour]
        output['annotations'].append(ann)
        annotation_id += 1
        image_id += 1

    output['categories'] = categories
    output['info'] = {
        'description': 'NDL',
        "url": "",
        "version": "0.1a",
        "year": 2023,
        "contributor": "morpho",
        "date_created": "2022/12/15"
    }

    output['licenses'] = []

    return output


def json_to_file(data, output_path: str):
    import json
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=4)


def train_test_split(df, ratio: float = 0.9):
    from copy import deepcopy
    print("start train-test split")
    df_copy = deepcopy(df)
    shuffled = df_copy.sample(frac=1)
    data_num = len(shuffled)
    train_num = int(data_num * ratio)
    df_train = shuffled[:train_num]
    df_test = shuffled[train_num:]

    return df_train, df_test


def parse_args():
    usage = 'python3 {} [INPUT] [img_dir] [-o OUT]'.format(__file__)
    argparser = argparse.ArgumentParser(
        usage=usage,
        description='Convert tsv annotation file to MS COCO format',
        formatter_class=argparse.RawTextHelpFormatter)
    argparser.add_argument(
        'input',
        default=None,
        help='input tsv file path',
        type=str)
    argparser.add_argument(
        'image_dir',
        default=None,
        help='image directory path',
        type=str)
    argparser.add_argument(
        '-o',
        '--out',
        default='output',
        help='output dir path',
        type=str)
    return argparser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    df = pd.read_table(args.input, names=('filename', 'roll'))

    print(df.head(5))  # check
    df_train, df_test = train_test_split(df)

    print('Converting: Train data')
    train_json = convert_to_coco(df_train, args.image_dir)
    print('Converting: Test data')
    test_json = convert_to_coco(df_test, args.image_dir)

    os.makedirs(args.out)
    train_json_path = os.path.join(args.out, 'train.json')
    test_json_path = os.path.join(args.out, 'test.json')
    json_to_file(train_json, train_json_path)
    json_to_file(test_json,  test_json_path)
