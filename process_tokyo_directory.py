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

def load_position_titles(csv_path, column_name='BeforeWar'):
    if not os.path.exists(csv_path): return []
    try:
        df = pd.read_csv(csv_path)
        if column_name not in df.columns: column_name = df.columns[0]
        titles = df[column_name].dropna().unique().tolist()
        titles.sort(key=len, reverse=True)
        return titles
    except Exception as e:
        print(f"Error reading position crosswalk: {e}")
        return []

def clean_ranks(text):
    if not text: return text
    return RANK_PATTERN.sub(r', \1, ', text)

def split_names_greedy(text, tokenizer_obj, mode_c):
    """
    Pass 1: Standard splitting using Mode C (Long chunks).
    """
    if not text or not SUDACHI_AVAILABLE: return text
    text = clean_ranks(text) # Pre-clean ranks

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

            # If Surname detected, start new chunk
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
    """
    Pass 2: Aggressive Split.
    Uses Mode A (Short Units).
    Splits if:
    1. A Surname (姓) is found.
    2. A Place Name (地名) is found (often used as surnames like Ebara).
    3. The PREVIOUS token was a Given Name (名) and CURRENT is a Noun (Start of new name).
    """
    if not SUDACHI_AVAILABLE: return ", ".join(name_list)
    
    refined_list = []
    
    for name_segment in name_list:
        # If segment is short and safe, keep it
        if len(name_segment) <= 4:
            refined_list.append(name_segment)
            continue
            
        # Re-tokenize with Mode A
        try:
            tokens = list(tokenizer_obj.tokenize(name_segment, mode_a))
            sub_parts = []
            current_sub = []
            
            prev_was_given_name = False
            
            for i, token in enumerate(tokens):
                surface = token.surface()
                pos = token.part_of_speech()
                
                # POS Checks
                is_noun = (pos[0] == '名詞')
                # pos[1] might be 固有名詞 (Proper), pos[2] might be 地名 (Place) or 人名 (Person)
                is_surname = (len(pos) > 3 and pos[3] == '姓')
                is_place = (len(pos) > 2 and pos[2] == '地名') 
                is_given_name = (len(pos) > 3 and pos[3] == '名')
                
                # DECISION: Should we split here?
                # Trigger split if:
                # A) We are not at start
                # B) AND (It looks like a Surname OR Place OR (Previous was a Given Name))
                should_split = False
                if i > 0:
                    if is_surname:
                        should_split = True
                    elif is_place: # e.g. Ebara
                        should_split = True
                    elif prev_was_given_name and is_noun: # e.g. Hisakichi -> Kon
                        should_split = True
                
                if should_split:
                    if current_sub:
                        sub_parts.append("".join(current_sub))
                        current_sub = []
                    current_sub.append(surface)
                else:
                    current_sub.append(surface)
                
                # Update state for next token
                prev_was_given_name = is_given_name
            
            if current_sub:
                sub_parts.append("".join(current_sub))
            
            refined_list.extend(sub_parts)
            
        except Exception:
            refined_list.append(name_segment)
            
    return ", ".join(refined_list)

def get_sudachi_label(text, tokenizer_obj, mode):
    if not SUDACHI_AVAILABLE: return None
    try:
        tokens = list(tokenizer_obj.tokenize(text, mode))
        for i, token in enumerate(tokens[:-1]):
            pos = token.part_of_speech()
            if len(pos) > 3 and pos[3] == '姓':
                return 'NameSudachi'
    except Exception: pass
    return None

def determine_label(text, position_titles, tokenizer_obj, mode):
    text_norm = text.replace(" ", "").replace("　", "")
    if any(text_norm.endswith(char) for char in OFFICE_ENDINGS): return 'Office'
    if text_norm in position_titles: return 'Position'
    for title in position_titles:
        if text_norm.startswith(title) and len(text_norm) > len(title): return 'Position_and_Name'
    if any(keyword in text_norm for keyword in DRAFTED_KEYWORDS): return 'Drafted'
    sudachi_label = get_sudachi_label(text_norm, tokenizer_obj, mode)
    if sudachi_label: return sudachi_label
    return None

def parse_xml_to_entries(xml_path):
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
                try:
                    entries.append({
                        'page_number': page_number,
                        'text': string_val,
                        'x': int(line.get('X')),
                        'y': int(line.get('Y')),
                        'w': int(line.get('WIDTH')),
                        'h': int(line.get('HEIGHT')),
                        'image_name': image_name,
                        'file_path': xml_path
                    })
                except ValueError: continue
    return entries

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
    parser.add_argument("--year_col", default="BeforeWar")
    args = parser.parse_args()

    # Init Sudachi (Load TWO modes)
    tokenizer_obj = None
    mode_c = None
    mode_a = None
    if SUDACHI_AVAILABLE:
        try:
            tokenizer_obj = dictionary.Dictionary(dict="core").create()
            mode_c = tokenizer.Tokenizer.SplitMode.C # Complex (Standard)
            mode_a = tokenizer.Tokenizer.SplitMode.A # Short (Granular)
        except Exception as e: print(f"Sudachi init failed: {e}")

    position_titles = load_position_titles(args.crosswalk, args.year_col)

    search_pattern = os.path.join(args.input_dir, "**", "*.xml")
    xml_files = glob.glob(search_pattern, recursive=True)
    if not xml_files and os.path.isfile(args.input_dir):
        xml_files = [args.input_dir]

    all_data = []

    for xml_file in xml_files:
        raw_entries = parse_xml_to_entries(xml_file)
        
        pages = {}
        for entry in raw_entries:
            img = entry['image_name']
            if img not in pages: pages[img] = []
            pages[img].append(entry)
        
        def page_sort_key(name):
            n = name.lower()
            if 'right' in n: return 0
            if 'left' in n: return 1
            return 2
            
        sorted_page_names = sorted(pages.keys(), key=page_sort_key)
        
        for page_name in sorted_page_names:
            page_entries = pages[page_name]
            sorted_entries = sort_vertical_columns(page_entries)
            
            for entry in sorted_entries:
                label = determine_label(entry['text'], position_titles, tokenizer_obj, mode_c)
                entry['label'] = label
                
                # Apply Double-Pass Separation
                if label == 'NameSudachi':
                    # Pass 1: Standard Split
                    initial_split = split_names_greedy(entry['text'], tokenizer_obj, mode_c)
                    # Pass 2: Aggressive NER Audit
                    final_text = refine_suspicious_names(initial_split, tokenizer_obj, mode_a)
                    entry['text'] = final_text
                
                all_data.append(entry)

    if all_data:
        df = pd.DataFrame(all_data)
        cols = ['page_number', 'image_name', 'label', 'text', 'x', 'y', 'w', 'h', 'file_path']
        cols = [c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]
        df = df[cols]
        df.to_csv(args.output, index=False)
        print(f"Success! Saved {len(df)} rows to {args.output}")

if __name__ == "__main__":
    main()
