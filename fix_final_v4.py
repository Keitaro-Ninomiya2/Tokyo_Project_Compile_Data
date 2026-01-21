import os

path = 'submodules/separate_pages_mmdet/inference_divide.py'
print(f'Applying V4 patch for {path}...')

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
        
    # 2. Insert V4 Patch
    if 'self.model = init_detector' in line and not skip_mode:
        indent = '        ' # 8 spaces
        new_lines.append(f'{indent}# PATCH: Fix MMDetection 3.x Config Issues (V4)\n')
        new_lines.append(f'{indent}if hasattr(self.model, "cfg"):\n')
        new_lines.append(f'{indent}    if hasattr(self.model.cfg.data.test, "pipeline"):\n')
        new_lines.append(f'{indent}        for step in self.model.cfg.data.test.pipeline:\n')
        new_lines.append(f'{indent}            if step["type"] == "MultiScaleFlipAug":\n')
        new_lines.append(f'{indent}                # Remove deprecated args\n')
        new_lines.append(f'{indent}                if "img_scale" in step: step.pop("img_scale")\n')
        new_lines.append(f'{indent}                if "flip" in step: step.pop("flip")\n')
        new_lines.append(f'{indent}                # FIX THE TRANSFORMS LIST\n')
        new_lines.append(f'{indent}                if "transforms" in step:\n')
        new_lines.append(f'{indent}                    for t in step["transforms"]:\n')
        new_lines.append(f'{indent}                        # Find Resize and force the scale\n')
        new_lines.append(f'{indent}                        if t["type"] == "Resize":\n')
        new_lines.append(f'{indent}                            t["scale"] = (1024, 1024)\n')
        new_lines.append(f'{indent}                            t["keep_ratio"] = True\n')
        new_lines.append(f'{indent}    # Add test_dataloader shim\n')
        new_lines.append(f'{indent}    if not hasattr(self.model.cfg, "test_dataloader"):\n')
        new_lines.append(f'{indent}        try:\n')
        new_lines.append(f'{indent}            from mmengine.config import ConfigDict\n')
        new_lines.append(f'{indent}            self.model.cfg.test_dataloader = ConfigDict({{"dataset": self.model.cfg.data.test}})\n')
        new_lines.append(f'{indent}        except Exception as e:\n')
        new_lines.append(f'{indent}            print(f"[Patch Error] {{e}}")\n')

with open(path, 'w') as f:
    f.writelines(new_lines)

print('✅ Success: Patch V4 applied.')
