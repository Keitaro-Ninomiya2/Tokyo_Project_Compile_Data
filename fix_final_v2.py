import os

path = 'submodules/separate_pages_mmdet/inference_divide.py'
print(f'Applying V2 patch for {path}...')

with open(path, 'r') as f:
    lines = f.readlines()

new_lines = []
skip_mode = False

for line in lines:
    # 1. Clean out previous patches to avoid duplicates
    if '# PATCH:' in line:
        skip_mode = True
    
    # Stop skipping when we hit normal code again
    if skip_mode and ('def ' in line or 'class ' in line):
        skip_mode = False
    
    if not skip_mode:
        new_lines.append(line)
        
    # 2. Insert the NEW, smarter patch
    if 'self.model = init_detector' in line and not skip_mode:
        indent = '        ' # 8 spaces
        new_lines.append(f'{indent}# PATCH: Fix MMDetection 3.x Config Issues (img_scale & flip)\n')
        new_lines.append(f'{indent}if hasattr(self.model, "cfg"):\n')
        new_lines.append(f'{indent}    # Fix A: Remove deprecated args from MultiScaleFlipAug\n')
        new_lines.append(f'{indent}    if hasattr(self.model.cfg.data.test, "pipeline"):\n')
        new_lines.append(f'{indent}        for step in self.model.cfg.data.test.pipeline:\n')
        new_lines.append(f'{indent}            if step["type"] == "MultiScaleFlipAug":\n')
        new_lines.append(f'{indent}                if "img_scale" in step: step.pop("img_scale")\n')
        new_lines.append(f'{indent}                if "flip" in step: step.pop("flip")\n')
        new_lines.append(f'{indent}                if "transforms" not in step:\n')
        new_lines.append(f'{indent}                    step["transforms"] = [\n')
        new_lines.append(f'{indent}                        dict(type="Resize", keep_ratio=True),\n')
        new_lines.append(f'{indent}                        dict(type="RandomFlip"),\n')
        new_lines.append(f'{indent}                        dict(type="Pad", size_divisor=32),\n')
        new_lines.append(f'{indent}                        dict(type="ImageToTensor", keys=["img"]),\n')
        new_lines.append(f'{indent}                        dict(type="Collect", keys=["img"])\n')
        new_lines.append(f'{indent}                    ]\n')
        new_lines.append(f'{indent}    # Fix B: Add test_dataloader shim\n')
        new_lines.append(f'{indent}    if not hasattr(self.model.cfg, "test_dataloader"):\n')
        new_lines.append(f'{indent}        try:\n')
        new_lines.append(f'{indent}            from mmengine.config import ConfigDict\n')
        new_lines.append(f'{indent}            self.model.cfg.test_dataloader = ConfigDict({{"dataset": self.model.cfg.data.test}})\n')
        new_lines.append(f'{indent}        except Exception as e:\n')
        new_lines.append(f'{indent}            print(f"[Patch Error] {{e}}")\n')

with open(path, 'w') as f:
    f.writelines(new_lines)

print('✅ Success: Patch V2 applied.')
