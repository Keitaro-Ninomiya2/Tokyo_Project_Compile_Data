# separate_pages_mmdet (NDLOCR(ver.2)用ページ分割モジュール)

NDLOCR(ver.2)用の見開きの資料画像をページ単位でノド元で分割するモジュールのリポジトリです。モデルの学習には、MMDetection を利用します。

本プログラムは、全文検索用途のテキスト化のために開発した[ver.1](https://github.com/ndl-lab/ndlocr_cli/tree/ver.1)に対して、視覚障害者等の読み上げ用途にも利用できるよう、国立国会図書館が外部委託して追加開発したプログラムです（委託業者：株式会社モルフォAIソリューションズ）。


事業の詳細については、[令和4年度NDLOCR追加開発事業及び同事業成果に対する改善作業](https://lab.ndl.go.jp/data_set/r4ocr/r4_software/)をご覧ください。

本プログラムは、国立国会図書館がCC BY 4.0ライセンスで公開するものです。詳細については LICENSEをご覧ください。


# Training
MMDetectionのTrain方法に準ずる。configファイルは `configs/ndl/` に格納。

# Data convert
`tools/convert_anno_to_coco.py` を使用しTSVファイルの形式のアノテーションをMS COCO形式に変換することができる。

使用方法
```
$ python3 tools/convert_anno_to_coco.py [INPUT] [img_dir] [-o OUT]
```

```
positional arguments:
  input              input tsv file path
  image_dir          image directory path

optional arguments:
  -h, --help         show this help message and exit
  -o OUT, --out OUT  output dir path
```

TSVファイルのアノテーション形式:
```
image_file_name<tab>float_position
```
float_position は -0.5 以上0.5以下の小数で、ノド元の画像中心からの相対位置を示す。
-0.5 は左端を 0.5 は右端を 0.0 は中央を指す。

# inference
inference_inputディレクトリ(-i オプションで変更可能)にノド元を分割したい画像を入れ、inference_divide.pyを実行する。inference_outputディレクトリ(-o オプションで変更可能)に分割後の画像が出力される。
ノド元はmmdetection formatのモデルによって矩形として検出され、矩形中心部のx座標をノド元位置とする。複数の矩形が検出された場合、最も信頼度の高いものを採用する。
分割後の画像ファイル名は元画像ファイル名+LEFT or RIGHTとなる。入力画像にノド元が検出されなかった場合、画像は分割されずに、元画像ファイル名+SINGLEで出力する。

```
$ python3 inference_divide.py [-i INPUT] [-o OUTPUT] [-l LEFT] [-r RIGHT] [-s SINGLE] [-e EXT] [-q QUALITY] [-c CONFIG] [-w WEIGHT]
```

optional arguments:
```
  -h, --help    ヘルプメッセージを表示して終了
  -i INPUT, --input INPUT
                入力画像または入力画像を格納したディレクトリのパス
                (default: inference_input)
  -o OUT, --out OUT
                出力画像を保存するディレクトリのパス (default: inference_output)
                また、"NO_DUMP"を指定した場合、ノド元で分割した画像を出力しない。
                後述のlogオプションと組み合わせることで画像出力を省略し、ノド元位置のみを取得できる。
  -l LEFT, --left LEFT
                左ページの出力画像のファイル名の末尾につけるフッター
                例）input image:  input.jpg, LEFT: _L(default)
                    output image: input_L.jpg
  -r RIGHT, --right RIGHT
                右ページの出力画像のファイル名の末尾につけるフッター
                例）input image:  input.jpg, RIGHT: _R(default)
                    output image: input_R.jpg
  -s SINGLE, --single SINGLE
                入力画像でノド元が検出されなかった場合に出力する画像ファイル名の末尾に着けるフッター
                例）input image:  input.jpg, SINGLE: _S(default)
                    output image: input_S.jpg
  -e EXT, --ext EXT     
                出力画像の拡張子。 (default: .jpg)
                ただし、"SAME"とした場合は入力画像と同じ拡張子を使用する。
  -q QUALITY, --quality QUALITY
                Jpeg画像出力時の画質。1~100の整数値で指定する。
                1が最低画質で最小ファイルサイズ、100が最高画質で最大ファイルサイズ。
                default: 100
  --lg LOG, --log LOG
                検出したノド元位置を記録するtsvファイルのパス。未指定の場合、出力しない。
                1行目に列名 image_name<tab>trimming_x
                2行目以降に入力画像のファイル名と検出したノド元位置を記録する。
                指定したtsvファイルが既に存在しているときは、入力ファイル名とノド元位置を追記する。
  -c CONFIG, --config CONFIG
                mmdetectionフォーマットのconfigファイルパス
                Default: models/separate_page/cascade_rcnn_r50_fpn_1x_ndl_1024.py
  -w WEIGHT, --weight WEIGHT
                モデルweight pthファイルパス
                Default: models/separate_page/model.pth
```

