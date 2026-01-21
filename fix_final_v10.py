import os

path = 'submodules/separate_pages_mmdet/inference_divide.py'
print(f'Applying V10 (GPU Enforcer) patch for {path}...')

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
        new_lines.append(line)
        
    # 2. Insert V10 Patch
    if 'self.model = init_detector' in line and not skip_mode:
        indent = '        ' # 8 spaces
        new_lines.append(f'{indent}# PATCH: GPU Enforcer for MMDetection 3.x (V10)\n')
        new_lines.append(f'{indent}if hasattr(self.model, "cfg"):\n')
        new_lines.append(f'{indent}    # 1. Clean Pipeline\n')
        new_lines.append(f'{indent}    clean_pipeline = [\n')
        new_lines.append(f'{indent}        dict(type="LoadImageFromFile"),\n')
        new_lines.append(f'{indent}        dict(type="Resize", scale=(1024, 1024), keep_ratio=True),\n')
        new_lines.append(f'{indent}        dict(type="PackDetInputs", meta_keys=("img_id", "img_path", "ori_shape", "img_shape", "scale_factor"))\n')
        new_lines.append(f'{indent}    ]\n')
        new_lines.append(f'{indent}    try:\n')
        new_lines.append(f'{indent}        from mmengine.config import ConfigDict\n')
        new_lines.append(f'{indent}        self.model.cfg.data.test.pipeline = clean_pipeline\n')
        new_lines.append(f'{indent}        self.model.cfg.test_pipeline = clean_pipeline\n')
        new_lines.append(f'{indent}        if not hasattr(self.model.cfg, "test_dataloader"):\n')
        new_lines.append(f'{indent}            self.model.cfg.test_dataloader = ConfigDict({{"dataset": ConfigDict({{"pipeline": clean_pipeline}})}})\n')
        new_lines.append(f'{indent}            \n')
        new_lines.append(f'{indent}        # 2. CUSTOM PREPROCESSOR (The Fix)\n')
        new_lines.append(f'{indent}        from mmdet.models.data_preprocessors import DetDataPreprocessor\n')
        new_lines.append(f'{indent}        class GPUForcedPreprocessor(DetDataPreprocessor):\n')
        new_lines.append(f'{indent}            def forward(self, data, training=False):\n')
        new_lines.append(f'{indent}                # Force inputs to GPU immediately\n')
        new_lines.append(f'{indent}                if "inputs" in data:\n')
        new_lines.append(f'{indent}                    data["inputs"] = [t.cuda() for t in data["inputs"]]\n')
        new_lines.append(f'{indent}                return super().forward(data, training)\n')
        new_lines.append(f'{indent}        \n')
        new_lines.append(f'{indent}        preprocessor = GPUForcedPreprocessor(\n')
        new_lines.append(f'{indent}            mean=[123.675, 116.28, 103.53], \n')
        new_lines.append(f'{indent}            std=[58.395, 57.12, 57.375], \n')
        new_lines.append(f'{indent}            bgr_to_rgb=True, \n')
        new_lines.append(f'{indent}            pad_size_divisor=32\n')
        new_lines.append(f'{indent}        )\n')
        new_lines.append(f'{indent}        self.model.data_preprocessor = preprocessor\n')
        new_lines.append(f'{indent}        self.model.data_preprocessor.to(self.model.device)\n')
        new_lines.append(f'{indent}        \n')
        new_lines.append(f'{indent}    except Exception as e:\n')
        new_lines.append(f'{indent}        print(f"[Patch Error] {{e}}")\n')

with open(path, 'w') as f:
    f.writelines(new_lines)

print('✅ Success: Patch V10 applied.')
