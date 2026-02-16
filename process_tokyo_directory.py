import os
import glob
import pandas as pd
import xml.etree.ElementTree as ET
import argparse
import re
from tqdm import tqdm

# --- Sudachi Imports for Name Splitting ---
try:
    from sudachipy import dictionary, tokenizer
    tokenizer_obj = dictionary.Dictionary().create()
    mode = tokenizer.Tokenizer.SplitMode.C
    print("SudachiPy initialized successfully.")
except ImportError:
    print("Warning: SudachiPy not found. Name splitting will be skipped.")
    tokenizer_obj = None
except Exception as e:
    print(f"Warning: SudachiPy initialization failed: {e}")
    tokenizer_obj = None


# ==========================================
# 0. PRE-PROCESSING: Strip Metadata BEFORE Sudachi
# ==========================================

# --- Regex patterns for metadata embedded in name strings ---
# Salary: 月 followed by kanji numerals (e.g. 月七五, 月八五〇)
SALARY_RE = re.compile(r'月([一二三四五六七八九十百〇]+)')
# Rank:  正/従 + numeral + optional 位 (e.g. 正八, 従七位, 正八位)
RANK_RE   = re.compile(r'([正従][一二三四五六七八九十][位]?)')
# Grade prefix: e.g. 七上, 六下, 五等 — often prepended before position title
GRADE_RE  = re.compile(r'^([一二三四五六七八九十]+[上中下等級])')
# Additional common non-name tokens that appear inline
MISC_METADATA_RE = re.compile(
    r'(勅任|奏任|判任'           # Appointment types
    r'|[一二三四五六七八九十]+等'  # Grade (e.g. 七等)
    r'|技手|嘱託|兼務'           # Common suffixes
    r'|休職|待命|出向)')          # Status markers


def strip_metadata(text):
    """
    Extracts salary, rank, and grade prefixes from raw text BEFORE
    name splitting. Returns (cleaned_text, salary, rank, grade).
    """
    if not isinstance(text, str):
        return "", "", "", ""

    salary = ""
    rank = ""
    grade = ""

    # 1. Extract Salary
    sal_match = SALARY_RE.search(text)
    if sal_match:
        salary = sal_match.group(1)
        text = text[:sal_match.start()] + text[sal_match.end():]

    # 2. Extract Rank
    rank_match = RANK_RE.search(text)
    if rank_match:
        rank = rank_match.group(1)
        text = text[:rank_match.start()] + text[rank_match.end():]

    # 3. Extract Grade prefix (only at start of string)
    grade_match = GRADE_RE.match(text)
    if grade_match:
        grade = grade_match.group(1)
        text = text[grade_match.end():]

    # 4. Strip misc metadata tokens (勅任, 奏任, etc.)
    text = MISC_METADATA_RE.sub('', text)

    # Clean up any leftover whitespace / punctuation
    text = re.sub(r'[\s　,、]+', '', text)  # collapse whitespace
    return text.strip(), salary, rank, grade


# ==========================================
# 1. NAME EXTRACTION LOGIC (Improved)
# ==========================================
def extract_names(text):
    """
    Uses Sudachi to split a string of concatenated names into a list.
    IMPORTANT: Call strip_metadata() BEFORE this function.

    Only emits names that have a surname+given name pair (姓+名),
    or are 3+ characters. Lone 1-2 char surname-only tokens are
    discarded — they are usually place names or OCR fragments that
    Sudachi's dictionary happens to tag as 人名/姓.

    Returns list of name strings.
    """
    if tokenizer_obj is None or not text:
        return []

    tokens = tokenizer_obj.tokenize(text, mode)
    names = []
    temp_name = []
    has_given_name = False  # Track if we saw a 名 token in current name

    for token in tokens:
        pos = token.part_of_speech()

        if pos[0] == '名詞' and pos[1] == '固有名詞' and pos[2] == '人名':
            if pos[3] == '姓':
                # New surname encountered — flush any pending name
                if temp_name:
                    candidate = ''.join(temp_name)
                    # Only keep if it had a given name or is 3+ chars
                    if has_given_name or len(candidate) >= 3:
                        names.append(candidate)
                    temp_name = []
                    has_given_name = False
                temp_name.append(token.surface())
            elif pos[3] == '名' and temp_name:
                # Given name following a surname
                temp_name.append(token.surface())
                has_given_name = True
                names.append(''.join(temp_name))
                temp_name = []
                has_given_name = False
            elif pos[3] == '名' and not temp_name:
                # Orphaned given name (rare) — keep if 2+ chars
                surface = token.surface()
                if len(surface) >= 2:
                    names.append(surface)
            else:
                # Other person-name subtype
                if temp_name:
                    temp_name.append(token.surface())
                else:
                    temp_name.append(token.surface())
        else:
            # Non-name token encountered — flush pending name
            if temp_name:
                candidate = ''.join(temp_name)
                if has_given_name or len(candidate) >= 3:
                    names.append(candidate)
                temp_name = []
                has_given_name = False

    # Flush final pending name
    if temp_name:
        candidate = ''.join(temp_name)
        if has_given_name or len(candidate) >= 3:
            names.append(candidate)

    return names


# ==========================================
# 2. XML PARSING LOGIC (unchanged)
# ==========================================
def parse_xml_by_page(xml_path):
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
                except:
                    continue

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
                    except:
                        continue

        if lines:
            pages_data[image_name] = lines

    return pages_data


def sort_lines_by_columns(lines, tolerance=30):
    if not lines:
        return []

    lines_sorted_x = sorted(lines, key=lambda e: e['x'], reverse=True)

    columns = []
    for line in lines_sorted_x:
        center_x = line['x'] + (line['w'] / 2)
        placed = False

        for col in columns:
            col_x_values = [l['x'] + (l['w'] / 2) for l in col]
            avg_col_x = sum(col_x_values) / len(col_x_values)

            if abs(center_x - avg_col_x) < tolerance:
                col.append(line)
                placed = True
                break

        if not placed:
            columns.append([line])

    columns.sort(key=lambda col: sum(l['x'] for l in col) / len(col), reverse=True)

    final_sorted = []
    for col in columns:
        col.sort(key=lambda l: l['y'])
        final_sorted.extend(col)

    return final_sorted


# ==========================================
# 3. POSITION MATCHING (Improved)
# ==========================================
def match_position(text, known_titles):
    """
    Match position title from text, handling grade prefixes.
    
    Example: "七上技師" -> grade="七上", position="技師"
             "技師"     -> grade="",    position="技師"
    
    Returns (position, grade, remaining_text)
    """
    if not text:
        return "Unknown", "", text

    # 1. Try direct startswith match first (longest match wins)
    best_match = None
    for title in known_titles:
        if text.startswith(title):
            if best_match is None or len(title) > len(best_match):
                best_match = title

    if best_match:
        remaining = text[len(best_match):].strip()
        return best_match, "", remaining

    # 2. If no direct match, try stripping grade prefix first
    grade_match = GRADE_RE.match(text)
    if grade_match:
        grade_prefix = grade_match.group(1)
        text_after_grade = text[grade_match.end():]

        best_match = None
        for title in known_titles:
            if text_after_grade.startswith(title):
                if best_match is None or len(title) > len(best_match):
                    best_match = title

        if best_match:
            remaining = text_after_grade[len(best_match):].strip()
            return best_match, grade_prefix, remaining

    # 3. No match at all
    return "Unknown", "", text


# ==========================================
# 4. MAIN EXECUTION
# ==========================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--crosswalk", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--year_col", default="DuringWar")
    args = parser.parse_args()

    # Load Crosswalk — pull titles from ALL Japanese-text columns
    known_titles = set()
    if args.crosswalk and os.path.exists(args.crosswalk):
        try:
            cw = pd.read_csv(args.crosswalk)
            title_cols = ['Japanese', 'DuringWar', 'TokyoFu', 'Merged',
                          'BeforeWar', 'AfterWar']
            for col in title_cols:
                if col in cw.columns:
                    vals = cw[col].dropna().astype(str).str.strip().unique()
                    known_titles.update(v for v in vals if v)
            known_titles.discard('')
        except Exception:
            pass

    print(f"Loaded {len(known_titles)} titles from crosswalk.")

    # Find XML Files
    xml_files = glob.glob(os.path.join(args.input_dir, "**", "*.xml"), recursive=True)
    xml_files = [x for x in xml_files if 'mets' not in x.lower()]

    # Sort XML files by page number to ensure correct reading order
    def xml_sort_key(path):
        fname = os.path.basename(path)
        m = re.search(r'Page(\d+)', path) or re.search(r'(\d+)', fname)
        return int(m.group(1)) if m else 999999

    xml_files.sort(key=xml_sort_key)

    print(f"Found {len(xml_files)} XML files in {args.input_dir}")
    if not xml_files:
        return

    all_data = []

    for xml_file in tqdm(xml_files):
        # A. Parse Crops
        pages_dict = parse_xml_by_page(xml_file)
        if not pages_dict:
            continue

        # B. Sort Pages
        def page_sort_key(fname):
            fname = fname.lower()
            side_rank = 1 if 'left' in fname else 0
            if 'top' in fname:
                vert_rank = 0
            elif 'middle' in fname or 'mid' in fname:
                vert_rank = 1
            elif 'bottom' in fname or 'bot' in fname:
                vert_rank = 2
            else:
                vert_rank = 0
            return (side_rank, vert_rank, fname)

        sorted_pagenames = sorted(pages_dict.keys(), key=page_sort_key)

        filename = os.path.basename(xml_file)
        page_match = re.search(r'Page(\d+)', xml_file) or re.search(r'(\d+)', filename)
        page_num = int(page_match.group(1)) if page_match else 999999

        # C. Process Sorted Crops
        for img_name in sorted_pagenames:
            raw_lines = pages_dict[img_name]
            sorted_lines = sort_lines_by_columns(raw_lines, tolerance=30)

            for line_obj in sorted_lines:
                text = line_obj['text']

                # === KEY CHANGE: Position matching with grade-prefix awareness ===
                position, grade, raw_name_text = match_position(text, known_titles)

                # === KEY CHANGE: Strip metadata BEFORE name splitting ===
                cleaned_text, salary, rank, grade_from_name = strip_metadata(raw_name_text)

                # Merge grade sources (position prefix takes priority)
                if not grade and grade_from_name:
                    grade = grade_from_name

                # === Name Splitting on CLEAN text ===
                extracted_names = extract_names(cleaned_text)

                if extracted_names:
                    # One row per extracted name
                    for name_chunk in extracted_names:
                        all_data.append({
                            'office': 'Unknown Office',
                            'position': position,
                            'grade': grade,
                            'name': name_chunk,
                            'salary': salary,
                            'rank': rank,
                            'raw_text': text,
                            'x': line_obj['x'],
                            'y': line_obj['y'],
                            'folder': page_num,
                            'image': img_name,
                            'year': args.year_col,
                            'split_method': 'sudachi'
                        })
                else:
                    # Fallback: keep cleaned text as name
                    all_data.append({
                        'office': 'Unknown Office',
                        'position': position,
                        'grade': grade,
                        'name': cleaned_text if cleaned_text else raw_name_text,
                        'salary': salary,
                        'rank': rank,
                        'raw_text': text,
                        'x': line_obj['x'],
                        'y': line_obj['y'],
                        'folder': page_num,
                        'image': img_name,
                        'year': args.year_col,
                        'split_method': 'none'
                    })

    if all_data:
        df = pd.DataFrame(all_data)
        df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f"Success: Extracted {len(df)} rows to {args.output}")
        # Summary stats
        n_sudachi = (df['split_method'] == 'sudachi').sum()
        n_none = (df['split_method'] == 'none').sum()
        n_known = (df['position'] != 'Unknown').sum()
        print(f"  Sudachi splits: {n_sudachi} | Unsplit: {n_none}")
        print(f"  Position matched: {n_known} / {len(df)} "
              f"({100*n_known/len(df):.1f}%)")
    else:
        print("Error: No data extracted.")


if __name__ == "__main__":
    main()
