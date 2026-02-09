# -*- coding: utf-8 -*-
"""
GetNames Local - UIUC Cluster Version
- matches original Colab logic
- fixes Sorting (Right-Top -> Left-Bottom)
- handles both Numeric (NDL) and Text (Azure) filenames
"""

import os
import json
import csv
import re
import argparse
import pandas as pd
from sudachipy import dictionary, tokenizer

# Initialize Sudachi Tokenizer Globaly
try:
    tokenizer_obj = dictionary.Dictionary().create()
except Exception as e:
    print(f"Warning: SudachiPy initialization failed: {e}")
    tokenizer_obj = None

# ===========================
# SORTING HELPER (The Fix)
# ===========================
def get_image_rank(image_name):
    """
    Assigns a priority score to images to force Right-Top -> Left-Bottom order.
    Higher Score = Processed First.
    """
    name = str(image_name).lower()
    
    # 1. Handle Text Names (Azure)
    if 'right' in name and 'top' in name: return 40
    if 'right' in name and 'bottom' in name: return 30
    if 'left' in name and 'top' in name: return 20
    if 'left' in name and 'bottom' in name: return 10
    
    # 2. Handle Numeric Names (NDL)
    match = re.search(r'\d+', name)
    if match:
        num = int(match.group())
        # If strict 1-4 mapping is needed:
        if num == 4: return 40
        if num == 3: return 30
        if num == 2: return 20
        if num == 1: return 10
        return num * 10 
    return 0

# ===========================
# LABELING LOGIC (Matches Original)
# ===========================
def label_office_names(data, circle):
    circle_symbols = ["◎", "〇", "O", "○", "o", "0", "〓"]
    ending_characters = ["課", "係", "所", "房", "合", "院", "室", "場", "局", "屋", "寮", "館", "康", "ム", "班", "部", "衛", "宿", "校"]

    for entry in data:
        text_sequence = entry.get('text', '')
        if circle == "ON":
            is_office = False
            # Check strictly starting with circle
            if any(text_sequence.startswith(c) and any(e in text_sequence for e in ending_characters) for c in circle_symbols):
                is_office = True
            else:
                for item in entry.get('items', []):
                    t = item.get('text', '')
                    if any(t.startswith(c) and any(e in t for e in ending_characters) for c in circle_symbols):
                        item['label'] = 'Office'
            if is_office: entry['label'] = 'Office'
            
        elif circle == "OFF":
            if any(text_sequence.endswith(e) for e in ending_characters):
                entry['label'] = 'Office'
            else:
                for item in entry.get('items', []):
                    t = item.get('text', '')
                    if any(t.endswith(e) for e in ending_characters):
                        item['label'] = 'Office'
    return data

def label_position_titles_by_sequence(data, column, crosswalk_path):
    if not os.path.exists(crosswalk_path):
        print(f"Warning: Position Crosswalk not found at {crosswalk_path}")
        return data

    df = pd.read_csv(crosswalk_path)
    position_titles = df[column].dropna().unique().tolist()

    for entry in data:
        if 'label' in entry and entry['label'] == 'Office': continue
        text_sequence = entry.get('text', '').replace(" ", "").replace("　", "")

        if text_sequence in position_titles:
            entry['label'] = 'Position'
        else:
            for title in position_titles:
                if text_sequence.startswith(title) and len(text_sequence) > len(title):
                    entry['label'] = 'Position_and_Name'
                    break
    return data

def label_names_with_sudachipy(data):
    if tokenizer_obj is None: return data
    mode = tokenizer.Tokenizer.SplitMode.C
    
    for entry in data:
        if 'label' not in entry:
            text_sequence = entry.get('text', '').replace(" ", "").replace("　", "")
            tokens = list(tokenizer_obj.tokenize(text_sequence, mode))
            
            # Check for Surname + Name pattern
            for i, token in enumerate(tokens[:-1]):
                if '姓' in token.part_of_speech() and '名' in tokens[i + 1].part_of_speech():
                    entry['label'] = 'NameSudachi'
                    break
            else:
                # Check for Address (Proper Noun + Kanji Numbers)
                for token in tokens:
                    if "固有名詞" in token.part_of_speech() and any(k in token.surface() for k in '一二三四五六七八九十百千万'):
                        entry['label'] = 'AddressSudachi'
                        break
    return data

def label_drafted_entries(data):
    # Matches original keyword list
    keywords = ["應召", "召中", "應徴", "徴中", "入營", "營中"]
    for entry in data:
        text_sequence = entry.get('text', '')
        if any(k in text_sequence for k in keywords):
            entry['label'] = 'drafted'
        else:
            for item in entry.get('items', []):
                t = item.get('text', '')
                if any(k in t for k in keywords):
                    item['label'] = 'drafted'
    return data

def extract_names(text):
    if tokenizer_obj is None: return []
    tokens = tokenizer_obj.tokenize(text)
    names, temp_name = [], []
    for token in tokens:
        pos = token.part_of_speech()
        if pos[0] == '名詞' and pos[1] == '固有名詞':
            if pos[2] == '人名':
                if pos[3] == '姓': temp_name.append(token.surface())
                elif pos[3] == '名' and temp_name:
                    temp_name.append(token.surface())
                    names.append(''.join(temp_name))
                    temp_name = []
                elif pos[3] != '名' and temp_name:
                    temp_name.append(token.surface())
                    names.append(''.join(temp_name))
                    temp_name = []
    return names

# ===========================
# AZURE INTEGRATION
# ===========================
def extract_position_titles_simple(text, position_titles):
    text_sequence = text.replace(" ", "").replace("　", "")
    if text_sequence in position_titles:
        return 'Position'
    for title in position_titles:
        if text_sequence.startswith(title) and len(text_sequence) > len(title):
            return 'Position_and_Name'
    return None

def integrate_azure_output(labeled_data, azure_data, position_titles):
    azure_list = []
    # Loop matches original logic: scan azure data for matching Page+Image
    for entry in labeled_data:
        page_name = entry.get('page_name')
        image_name = entry.get('image_name')
        
        for azure_item in azure_data:
            if azure_item.get('page_name') == page_name and azure_item.get('image_name') == image_name:
                position_label = extract_position_titles_simple(azure_item.get('text', ''), position_titles)
                if position_label:
                    modified_item = azure_item.copy()
                    modified_item['label'] = 'Position'
                    azure_list.append(modified_item)
    return azure_list

# ===========================
# MAIN PROCESSING
# ===========================
def process_directory(year, folder_name, posi_col, circle, base_dir, ocr_mode=''):
    year_dir = os.path.join(base_dir, str(year), folder_name)
    crosswalk_path = os.path.join(base_dir, 'PositionCrosswalk.csv')
    
    # Load Position Titles
    try:
        df_pos = pd.read_csv(crosswalk_path)
        position_titles = df_pos[posi_col].dropna().unique().tolist()
    except Exception as e:
        print(f"Error loading crosswalk: {e}")
        return

    main_json_path = os.path.join(year_dir, f'Directory{year}.json')
    azure_json_path = os.path.join(year_dir, f'Directory{year}_Azure.json')
    
    labeled_data = []

    try:
        # 1. LOAD MAIN NDL DATA
        if ocr_mode != 'Azure' and os.path.isfile(main_json_path):
            print(f"Processing Main: {main_json_path}")
            with open(main_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data = label_office_names(data, circle)
            data = label_position_titles_by_sequence(data, posi_col, crosswalk_path)
            data = label_names_with_sudachipy(data)
            data = label_drafted_entries(data)
            labeled_data.extend(data)

        # 2. LOAD & MERGE AZURE DATA
        if os.path.isfile(azure_json_path):
            print(f"Merging Azure Data from: {azure_json_path}")
            with open(azure_json_path, 'r', encoding='utf-8') as f:
                azure_data = json.load(f)
            
            if ocr_mode == 'Azure':
                # Azure Only Mode
                print("Running Azure Only Mode")
                azure_data = label_office_names(azure_data, circle)
                azure_data = label_position_titles_by_sequence(azure_data, posi_col, crosswalk_path)
                azure_data = label_names_with_sudachipy(azure_data)
                azure_data = label_drafted_entries(azure_data)
                labeled_data = azure_data
            else:
                # Merge Mode (NDL + Azure)
                print("Integrating Azure Data...")
                azure_items = integrate_azure_output(labeled_data, azure_data, position_titles)
                labeled_data.extend(azure_items)

        # 3. DEDUPLICATE
        unique_data = {json.dumps(item, sort_keys=True) for item in labeled_data}
        labeled_data = [json.loads(item) for item in unique_data]

        # 4. ROBUST SPATIAL SORT (Page -> Score(Desc) -> Y)
        labeled_data.sort(key=lambda x: (
            x.get('page_name', ''), 
            -get_image_rank(x.get('image_name', '0')), 
            x.get('bounding_box', {}).get('y', 0)
        ))

        # 5. EXTRACT NAMES & SAVE
        if ocr_mode == 'Azure':
            output_csv = azure_json_path.replace('.json', '_Modified.csv')
        else:
            output_csv = main_json_path.replace('.json', '_Modified.csv')

        final_rows = []
        for entry in labeled_data:
            row = entry.copy()
            if row.get('label') in ['NameSudachi', 'Position_and_Name']:
                extracted = extract_names(row.get('text', ''))
                for i, name in enumerate(extracted):
                    row[f'Name{i+1}'] = name
            final_rows.append(row)

        pd.DataFrame(final_rows).to_csv(output_csv, index=False, encoding='utf-8-sig')
        print(f"Success: Saved to {output_csv}")

    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--folder", type=str, required=True)
    parser.add_argument("--posi_col", type=str, default="Merged")
    parser.add_argument("--circle", type=str, default="OFF")
    parser.add_argument("--ocr", type=str, default="")
    parser.add_argument("--base_dir", type=str, default=".")
    args = parser.parse_args()

    process_directory(args.year, args.folder, args.posi_col, args.circle, args.base_dir, args.ocr)
