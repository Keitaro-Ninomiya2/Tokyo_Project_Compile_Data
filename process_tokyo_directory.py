import os
import glob
import pandas as pd
import xml.etree.ElementTree as ET
import argparse
import re
from tqdm import tqdm

def parse_xml_by_page(xml_path):
    """
    Parses XML but keeps lines grouped by their PAGE (Crop).
    Returns a dictionary: { 'image_name': [list_of_lines], ... }
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception:
        return {}

    pages_data = {}

    for page in root.findall('.//PAGE'):
        image_name = page.get('IMAGENAME', 'unknown')
        lines = []

        # STRATEGY 1: Standard NDL
        for line_node in page.findall('.//LINE'):
            text = line_node.get('STRING') or line_node.text
            if text:
                try:
                    lines.append({
                        'text': str(text).strip(),
                        'x': int(line_node.get('X', 0)),
                        'y': int(line_node.get('Y', 0)),
                        'w': int(line_node.get('WIDTH', 0)),
                        'h': int(line_node.get('HEIGHT', 0))
                    })
                except: continue

        # STRATEGY 2: ALTO/New NDL (fallback)
        if not lines:
            for string_node in page.findall('.//{*}String'):
                text = string_node.get('CONTENT')
                if text:
                    try:
                        lines.append({
                            'text': str(text).strip(),
                            'x': int(string_node.get('HPOS', 0)),
                            'y': int(string_node.get('VPOS', 0)),
                            'w': int(string_node.get('WIDTH', 0)),
                            'h': int(string_node.get('HEIGHT', 0))
                        })
                    except: continue

        if lines:
            pages_data[image_name] = lines

    return pages_data

def sort_lines_by_columns(lines, tolerance=30):
    """
    Groups lines into vertical columns based on X coordinates,
    then sorts columns Right-to-Left, and lines Top-to-Bottom.
    """
    if not lines: return []

    # 1. Sort all lines by X descending (Right to Left)
    lines_sorted_x = sorted(lines, key=lambda e: e['x'], reverse=True)

    columns = []
    for line in lines_sorted_x:
        center_x = line['x'] + (line['w'] / 2)
        placed = False

        # Try to fit line into an existing column
        for col in columns:
            col_x_values = [l['x'] + (l['w'] / 2) for l in col]
            avg_col_x = sum(col_x_values) / len(col_x_values)

            if abs(center_x - avg_col_x) < tolerance:
                col.append(line)
                placed = True
                break

        if not placed:
            columns.append([line])

    # 2. Sort the COLUMNS themselves Right-to-Left
    columns.sort(key=lambda col: sum(l['x'] for l in col)/len(col), reverse=True)

    final_sorted = []
    for col in columns:
        # 3. Sort lines WITHIN each column Top-to-Bottom (Y axis)
        col.sort(key=lambda l: l['y'])
        final_sorted.extend(col)

    return final_sorted

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--crosswalk", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--year_col", default="DuringWar")
    args = parser.parse_args()

    # Load Crosswalk
    known_titles = set()
    if args.crosswalk and os.path.exists(args.crosswalk):
        try:
            cw = pd.read_csv(args.crosswalk)
            col_to_use = 'Japanese' if 'Japanese' in cw.columns else args.year_col
            if col_to_use in cw.columns:
                known_titles = set(cw[col_to_use].dropna().astype(str).unique())
        except Exception:
            pass

    print(f"Loaded {len(known_titles)} titles from crosswalk.")

    # Find XML Files
    xml_files = glob.glob(os.path.join(args.input_dir, "**", "*.xml"), recursive=True)
    xml_files = [x for x in xml_files if 'mets' not in x.lower()]

    print(f"Found {len(xml_files)} XML files in {args.input_dir}")
    if not xml_files: return

    all_data = []

    for xml_file in tqdm(xml_files):
        # A. Parse Crops
        pages_dict = parse_xml_by_page(xml_file)
        if not pages_dict: continue

        # =========================================================
        # B. GENERALIZED SORTING LOGIC (Right->Left, Top->Bottom)
        # =========================================================
        def page_sort_key(fname):
            fname = fname.lower()
            
            # 1. Primary Sort: Page Side (Right comes before Left)
            #    If filename contains 'left', rank=1. Else rank=0 (Right).
            side_rank = 1 if 'left' in fname else 0
            
            # 2. Secondary Sort: Vertical Position (Top -> Middle -> Bottom)
            #    We look for keywords and assign a numeric value.
            if 'top' in fname:
                vert_rank = 0
            elif 'middle' in fname or 'mid' in fname:
                vert_rank = 1
            elif 'bottom' in fname or 'bot' in fname:
                vert_rank = 2
            else:
                vert_rank = 0
                
            # Returns tuple for sorting: 
            # (0,0) Right Top -> (0,1) Right Mid -> (0,2) Right Bot
            # (1,0) Left Top  -> (1,1) Left Mid  -> (1,2) Left Bot
            return (side_rank, vert_rank, fname)

        sorted_pagenames = sorted(pages_dict.keys(), key=page_sort_key)

        filename = os.path.basename(xml_file)
        page_match = re.search(r'Page(\d+)', xml_file) or re.search(r'(\d+)', filename)
        page_num = int(page_match.group(1)) if page_match else 999999

        # C. Process Sorted Crops
        for img_name in sorted_pagenames:
            raw_lines = pages_dict[img_name]

            # D. Sort Lines Within Crop (Right-to-Left Columns)
            sorted_lines = sort_lines_by_columns(raw_lines, tolerance=30)

            for line_obj in sorted_lines:
                text = line_obj['text']

                # Labeling
                best_match = None
                for title in known_titles:
                    if text.startswith(title):
                        if best_match is None or len(title) > len(best_match):
                            best_match = title

                if best_match:
                    pos = best_match
                    name = text[len(best_match):].strip()
                else:
                    pos = "Unknown"
                    name = text

                all_data.append({
                    'office': 'Unknown Office',
                    'position': pos,
                    'name': name,
                    'raw_text': text,
                    'x': line_obj['x'],
                    'y': line_obj['y'],
                    'folder': page_num,
                    'image': img_name, 
                    'year': args.year_col
                })

    if all_data:
        df = pd.DataFrame(all_data)
        df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f"Success: Extracted {len(df)} rows.")
    else:
        print("Error: No data extracted.")

if __name__ == "__main__":
    main()
