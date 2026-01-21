import os

path = 'submodules/separate_pages_mmdet/inference_divide.py'
print(f'Patching {path}...')

with open(path, 'r') as f:
    lines = f.readlines()

new_lines = []
patched = False

for line in lines:
    new_lines.append(line)
    # We insert the fix immediately after the model is loaded
    if 'self.model = init_detector' in line and not patched:
        # Hardcode 8 spaces for indentation to match the file structure
        indent = '        '
        
        new_lines.append(f'{indent}# PATCH: Add test_dataloader for MMDetection 3.x\n')
        new_lines.append(f'{indent}if hasattr(self.model, "cfg") and not hasattr(self.model.cfg, "test_dataloader"):\n')
        new_lines.append(f'{indent}    try:\n')
        new_lines.append(f'{indent}        from mmengine.config import ConfigDict\n')
        new_lines.append(f'{indent}        self.model.cfg.test_dataloader = ConfigDict({{"dataset": self.model.cfg.data.test}})\n')
        new_lines.append(f'{indent}    except Exception as e:\n')
        new_lines.append(f'{indent}        print(f"[Patch Error] {{e}}")\n')
        patched = True

with open(path, 'w') as f:
    f.writelines(new_lines)

print('✅ Success: Config shim applied.')
