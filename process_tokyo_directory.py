import os
import glob
import pandas as pd
import xml.etree.ElementTree as ET
import argparse
import re
import sys

# Try importing Sudachi
try:
    from sudachipy import tokenizer, dictionary
    SUDACHI_AVAILABLE = True
except ImportError:
    SUDACHI_AVAILABLE = False
    print("Warning: sudachipy not found. Name labeling will be limited.")

# --- Configuration ---
OFFICE_ENDINGS = ["課", "係", "所", "房", "合", "院", "室", "場", "局", "屋", "寮", "館", "康", "ム", "班", "部", "衛", "宿", "校"]
DRAFTED_KEYWORDS = ["應召中", "應召", "召中", "應徴中", "應徴", "徴中", "入營中", "入營", "營中"]
KANJI_NUMBERS = '一二三四五六七八九十百千万'
RANK_PATTERN = re.compile(r'([正従][一二三四五六七八][位]?)')

def load_position_titles(csv_path, column_name='DuringWar'):
    if not os.path.exists(csv_path):
        print(f"CRITICAL ERROR: Crosswalk file not found at {csv_path}")
        sys.exit(1)
    try:
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding='shift-jis')
        
        print(f"--- Crosswalk Debug Info ---")
        print(f"Requested Column: {column_name}")
        print(f"Available Columns: {df.columns.tolist()}")
        
        if column_name not in df.columns:
            print(f"ERROR: Column '{column_name}' not found. Using first column.")
            column_name = df.columns[0]
            
        titles = df[column_name].dropna().astype(str).str.strip().unique().tolist()
        titles = [t for t in titles if len(t) > 1]
        titles.sort(key=len, reverse=True)
        print(f"Successfully loaded {len(titles)} unique position titles.")
        return titles
    except Exception as e:
        print(f"Error loading CSV: {e}")
        sys.exit(1)

def clean_ranks(text):
    if not text: return text
    return RANK_PATTERN.sub(r', \1, ', text)

def split_names_greedy(text, tokenizer_obj, mode_c):
    if not text or not SUDACHI_AVAILABLE: return text
    text = clean_ranks(text)
    try:
        tokens = list(tokenizer_obj.tokenize(text, mode_c))
        formatted_names = []
        current_name_parts = []
        for token in tokens:
            surface = token.surface()
            pos = token.part_of_speech()
            if surface in [',', '、', ' ', '　']:
                if current_name_parts:
                    formatted_names.append("".join(current_name_parts))
                    current_name_parts = []
                continue
            is_surname = (len(pos) > 3 and pos[3] == '姓')
            if is_surname:
                if current_name_parts:
                    formatted_names.append("".join(current_name_parts))
                    current_name_parts = []
                current_name_parts.append(surface)
            else:
                current_name_parts.append(surface)
        if current_name_parts:
            formatted_names.append("".join(current_name_parts))
        return formatted_names
    except Exception:
        return [text]

def refine_suspicious_names(name_list, tokenizer_obj, mode_a):
    if not SUDACHI_AVAILABLE: return ", ".join(name_list)
    refined_list = []
    for name_segment in name_list:
        if len(name_segment) <= 4:
            refined_list.append(name_segment)
            continue
        try:
            tokens = list(tokenizer_obj.tokenize(name_segment, mode_a))
            sub_parts = []
            current_sub = []
            prev_was_given_name = False
            for i, token in enumerate(tokens):
                surface = token.surface()
                pos = token.part_of_speech()
                is_noun = (pos[0] == '名詞')
                is_surname = (len(pos) > 3 and pos[3] == '姓')
                is_place = (len(pos) > 2 and pos[2] == '地名') 
                is_given_name = (len(pos) > 3 and pos[3] == '名')
                should_split = False
                if i > 0:
                    if is_surname or is_place or (prev_was_given_name and is_noun):
                        should_split = True
                if should_split:
                    if current_sub:
                        sub_parts.append("".join(current_sub))
                        current_sub = []
                    current_sub.append(surface)
                else:
                    current_sub.append(surface)
                prev_was_given_name = is_given_name
            if current_sub: sub_parts.append("".join(current_sub))
            refined_list.extend(sub_parts)
        except Exception:
            refined_list.append(name_segment)
    return ", ".join(refined_list)

def determine_label(text, position_titles, tokenizer_obj, mode):
    # Strip symbols for cleaner matching
    text_norm = re.sub(r'[【ヿ〓○●◎]', '', text).replace(" ", "").replace("　", "").strip()
    if any(text_norm.endswith(char) for char in OFFICE_ENDINGS): return 'Office'
    if text_norm in position_titles: return 'Position'
    for title in position_titles:
        if text_norm.startswith(title) and len(text_norm) > len(title): return 'Position_and_Name'
    if any(keyword in text_norm for keyword in DRAFTED_KEYWORDS): return 'Drafted'
    if SUDACHI_AVAILABLE:
        try:
            tokens = list(tokenizer_obj.tokenize(text_norm, mode))
            for token in tokens:
                pos = token.part_of_speech()
                if len(pos) > 3 and pos[3] == '姓': return 'NameSudachi'
        except Exception: pass
    return None

def parse_xml_to_entries(xml_path):
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        entries = []
        for page in root.findall('.//PAGE'):
            image_name = page.get('IMAGENAME')
            page_number = ""
            for block in page.findall('.//BLOCK'):
                if block.get('TYPE') == 'ノンブル':
                    page_number = block.get('STRING', "")
                    break
            for textblock in page.findall('.//TEXTBLOCK'):
                for line in textblock.findall('.//LINE'):
                    string_val = line.get('STRING')
                    if not string_val: continue
                    entries.append({
                        'page_number': page_number, 'text': string_val,
                        'x': int(line.get('X')), 'y': int(line.get('Y')),
                        'w': int(line.get('WIDTH')), 'h': int(line.get('HEIGHT')),
                        'image_name': image_name, 'file_path': xml_path
                    })
        return entries
    except Exception: return []

def sort_vertical_columns(entries, tolerance=30):
    if not entries: return []
    entries_sorted_x = sorted(entries, key=lambda e: e['x'], reverse=True)
    columns = []
    for entry in entries_sorted_x:
        center_x = entry['x'] + (entry['w'] / 2)
        placed = False
        for col in columns:
            col_x_values = [e['x'] + (e['w'] / 2) for e in col]
            avg_col_x = sum(col_x_values) / len(col_x_values)
            if abs(center_x - avg_col_x) < tolerance:
                col.append(entry)
                placed = True
                break
        if not placed: columns.append([entry])
    columns.sort(key=lambda col: sum(e['x'] + e['w']/2 for e in col)/len(col), reverse=True)
    final_sorted = []
    for col in columns:
        col.sort(key=lambda e: e['y'])
        final_sorted.extend(col)
    return final_sorted

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--output", default="labeled_output.csv")
    parser.add_argument("--year_col", default="DuringWar")
    args = parser.parse_args()

    # Init Sudachi
    tokenizer_obj = None
    mode_c = None
    mode_a = None
    if SUDACHI_AVAILABLE:
        try:
            tokenizer_obj = dictionary.Dictionary(dict="core").create()
            mode_c = tokenizer.Tokenizer.SplitMode.C
            mode_a = tokenizer.Tokenizer.SplitMode.A
        except Exception: pass

    position_titles = load_position_titles(args.crosswalk, args.year_col)
    xml_files = glob.glob(os.path.join(args.input_dir, "**", "input_data.sorted.xml"), recursive=True)
    all_data = []

    for xml_file in xml_files:
        match = re.search(r'Page(\d+)', xml_file)
        folder_num = int(match.group(1)) if match else 999999
        raw_entries = parse_xml_to_entries(xml_file)
        
        pages = {}
        for entry in raw_entries:
            img = entry['image_name']
            if img not in pages: pages[img] = []
            pages[img].append(entry)
            
        for page_name in sorted(pages.keys(), key=lambda x: 0 if 'right' in x.lower() else 1):
            sorted_entries = sort_vertical_columns(pages[page_name])
            for entry in sorted_entries:
                label = determine_label(entry['text'], position_titles, tokenizer_obj, mode_c)
                entry['label'] = label
                entry['sort_folder_num'] = folder_num
                
                # Handling Position Split while preserving original metadata
                if label == 'Position_and_Name':
                    clean_text = re.sub(r'[【ヿ〓○●◎]', '', entry['text']).replace(" ", "").replace("　", "")
                    matched_title = ""
                    for title in position_titles:
                        if clean_text.startswith(title):
                            matched_title = title
                            break
                    if matched_title:
                        # Row 1: Position
                        pos_row = entry.copy()
                        pos_row['label'] = 'Position'
                        pos_row['text'] = matched_title
                        all_data.append(pos_row)
                        # Prep original entry to become the Name entry
                        entry['text'] = entry['text'].replace(matched_title, "", 1).strip(" ,、")
                        entry['label'] = 'NameSudachi'
                        label = 'NameSudachi'

                if entry['label'] == 'NameSudachi':
                    # Apply your Pass 1 and Pass 2 Name refinement
                    p1 = split_names_greedy(entry['text'], tokenizer_obj, mode_c)
                    entry['text'] = refine_suspicious_names(p1, tokenizer_obj, mode_a)
                
                all_data.append(entry)

    if all_data:
        df = pd.DataFrame(all_data)
        df.sort_values(by=['sort_folder_num', 'image_name', 'y'], inplace=True)
        final_cols = ['sort_folder_num', 'page_number', 'image_name', 'label', 'text', 'x', 'y', 'w', 'h', 'file_path']
        df = df[[c for c in final_cols if c in df.columns]]
        df.to_csv(args.output, index=False)
        print(f"Success: Processed {len(df)} rows.")

if __name__ == "__main__":
    main()
