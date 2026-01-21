import os
from mmengine.config import ConfigDict

path = 'submodules/separate_pages_mmdet/inference_divide.py'
print(f'Applying V6 (Simple Pipeline) patch for {path}...')

with open(path, 'r') as f:
    lines = f.readlines()

new_lines = []
skip_mode = False

for line in lines:
    # 1. Clean out previous patches
    if '# PATCH:' in line:
        skip_mode = True
    if skip_mode and ('def ' in line or 'class ' in line):
        skip_mode = False
    
    if not skip_mode:
        new_lines.append(line)
        
    # 2. Insert V6 Patch (The Simplifier)
    if 'self.model = init_detector' in line and not skip_mode:
        indent = '        ' # 8 spaces
        new_lines.append(f'{indent}# PATCH: Force Simple Pipeline for MMDetection 3.x\n')
        new_lines.append(f'{indent}if hasattr(self.model, "cfg"):\n')
        new_lines.append(f'{indent}    # 1. DELETE the old complex pipeline\n')
        new_lines.append(f'{indent}    self.model.cfg.data.test.pipeline = [\n')
        new_lines.append(f'{indent}        dict(type="Resize", scale=(1024, 1024), keep_ratio=True),\n')
        new_lines.append(f'{indent}        dict(type="PackDetInputs", meta_keys=("img_id", "img_path", "ori_shape", "img_shape", "scale_factor"))\n')
        new_lines.append(f'{indent}    ]\n')
        new_lines.append(f'{indent}    # 2. Add test_dataloader shim\n')
        new_lines.append(f'{indent}    if not hasattr(self.model.cfg, "test_dataloader"):\n')
        new_lines.append(f'{indent}        try:\n')
        new_lines.append(f'{indent}            self.model.cfg.test_dataloader = ConfigDict({{"dataset": self.model.cfg.data.test}})\n')
        new_lines.append(f'{indent}        except Exception as e:\n')
        new_lines.append(f'{indent}            print(f"[Patch Error] {{e}}")\n')

with open(path, 'w') as f:
    f.writelines(new_lines)

print('✅ Success: Pipeline simplified.')
