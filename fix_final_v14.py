import os

path = 'submodules/separate_pages_mmdet/inference_divide.py'
print(f'Applying V14 (Corrected Translator) patch for {path}...')

with open(path, 'r') as f:
    lines = f.readlines()

new_lines = []
skip_mode = False

for line in lines:
    # 1. Clean out ANY previous patches
    if '# PATCH:' in line:
        skip_mode = True
    if skip_mode and ('def ' in line or 'class ' in line):
        skip_mode = False
    
    if not skip_mode:
        # Rewrite the predict method
        if 'def predict(self, img):' in line:
            new_lines.append(line)
            skip_mode = True 
            
            indent = '        ' # 8 spaces
            new_lines.append(f'{indent}# PATCH: Convert MMDetection 3.x Output to 2.x Format (V14)\n')
            new_lines.append(f'{indent}result = inference_detector(self.model, img)\n')
            new_lines.append(f'{indent}try:\n')
            new_lines.append(f'{indent}    if not isinstance(result, (tuple, list)):\n')
            new_lines.append(f'{indent}        import numpy as np\n')
            new_lines.append(f'{indent}        pred = result.pred_instances.cpu().numpy()\n')
            new_lines.append(f'{indent}        bboxes = pred.bboxes\n')
            new_lines.append(f'{indent}        scores = pred.scores\n')
            new_lines.append(f'{indent}        labels = pred.labels\n')
            new_lines.append(f'{indent}        \n')
            new_lines.append(f'{indent}        if len(bboxes) == 0:\n')
            new_lines.append(f'{indent}            # Return empty list of arrays if nothing found\n')
            new_lines.append(f'{indent}            return [np.zeros((0, 5), dtype=np.float32)]\n')
            new_lines.append(f'{indent}            \n')
            new_lines.append(f'{indent}        dets = np.hstack((bboxes, scores[:, None]))\n')
            new_lines.append(f'{indent}        \n')
            new_lines.append(f'{indent}        num_classes = 1\n')
            new_lines.append(f'{indent}        if hasattr(self.model, "dataset_meta") and "classes" in self.model.dataset_meta:\n')
            new_lines.append(f'{indent}            num_classes = len(self.model.dataset_meta["classes"])\n')
            new_lines.append(f'{indent}        elif len(labels) > 0:\n')
            new_lines.append(f'{indent}            num_classes = max(labels) + 1\n')
            new_lines.append(f'{indent}        \n')
            new_lines.append(f'{indent}        bbox_results = []\n')
            new_lines.append(f'{indent}        for i in range(num_classes):\n')
            new_lines.append(f'{indent}            bbox_results.append(dets[labels == i])\n')
            new_lines.append(f'{indent}        \n')
            new_lines.append(f'{indent}        # V14 FIX: Return the LIST directly, not a tuple\n')
            new_lines.append(f'{indent}        return bbox_results\n')
            new_lines.append(f'{indent}except Exception as e:\n')
            new_lines.append(f'{indent}    print(f"[Conversion Error] {{e}}")\n')
            new_lines.append(f'{indent}return result\n')
            continue
            
        new_lines.append(line)
        
    # 2. Insert V12 Patch (The GPU Fix for init) - KEEPING THIS
    if 'self.model = init_detector' in line and not skip_mode:
        indent = '        ' # 8 spaces
        new_lines.append(f'{indent}# PATCH: Manual GPU Override for MMDetection 3.x (V12)\n')
        new_lines.append(f'{indent}if hasattr(self.model, "cfg"):\n')
        new_lines.append(f'{indent}    clean_pipeline = [\n')
        new_lines.append(f'{indent}        dict(type="LoadImageFromFile"),\n')
        new_lines.append(f'{indent}        dict(type="Resize", scale=(1024, 1024), keep_ratio=True),\n')
        new_lines.append(f'{indent}        dict(type="PackDetInputs", meta_keys=("img_id", "img_path", "ori_shape", "img_shape", "scale_factor"))\n')
        new_lines.append(f'{indent}    ]\n')
        new_lines.append(f'{indent}    try:\n')
        new_lines.append(f'{indent}        import torch\n')
        new_lines.append(f'{indent}        from mmengine.config import ConfigDict\n')
        new_lines.append(f'{indent}        from mmdet.models.data_preprocessors import DetDataPreprocessor\n')
        new_lines.append(f'{indent}        \n')
        new_lines.append(f'{indent}        self.model.cfg.data.test.pipeline = clean_pipeline\n')
        new_lines.append(f'{indent}        self.model.cfg.test_pipeline = clean_pipeline\n')
        new_lines.append(f'{indent}        if not hasattr(self.model.cfg, "test_dataloader"):\n')
        new_lines.append(f'{indent}            self.model.cfg.test_dataloader = ConfigDict({{"dataset": ConfigDict({{"pipeline": clean_pipeline}})}})\n')
        new_lines.append(f'{indent}        \n')
        new_lines.append(f'{indent}        class NuclearPreprocessor(DetDataPreprocessor):\n')
        new_lines.append(f'{indent}            def forward(self, data, training=False):\n')
        new_lines.append(f'{indent}                inputs = data["inputs"]\n')
        new_lines.append(f'{indent}                batch = torch.stack(inputs).float().cuda()\n')
        new_lines.append(f'{indent}                mean = torch.tensor([123.675, 116.28, 103.53], device="cuda").view(1, 3, 1, 1)\n')
        new_lines.append(f'{indent}                std = torch.tensor([58.395, 57.12, 57.375], device="cuda").view(1, 3, 1, 1)\n')
        new_lines.append(f'{indent}                batch = batch[:, [2, 1, 0], ...]\n')
        new_lines.append(f'{indent}                batch = (batch - mean) / std\n')
        new_lines.append(f'{indent}                data["inputs"] = batch\n')
        new_lines.append(f'{indent}                return data\n')
        new_lines.append(f'{indent}        \n')
        new_lines.append(f'{indent}        preprocessor = NuclearPreprocessor()\n')
        new_lines.append(f'{indent}        preprocessor.cuda()\n')
        new_lines.append(f'{indent}        self.model.data_preprocessor = preprocessor\n')
        new_lines.append(f'{indent}    except Exception as e:\n')
        new_lines.append(f'{indent}        print(f"[Patch Error] {{e}}")\n')

with open(path, 'w') as f:
    f.writelines(new_lines)

print('✅ Success: Patch V14 applied.')
