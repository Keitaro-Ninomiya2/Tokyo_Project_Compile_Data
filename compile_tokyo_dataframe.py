import pandas as pd
import argparse
import re
import os
import sys

def is_header_candidate(text, headers_set):
    """
    Returns True if text is likely a Department name.
    """
    if pd.isna(text): return False
    text = str(text).strip()

    # 1. Check Explicit Crosswalk Headers
    if text in headers_set: return True

    # 2. Heuristics (Ends in Section/Bureau)
    # Exclude 'Section Chief' (ends in 長) unless it's a known office
    if len(text) < 15 and re.search(r'(課|係|局|部|署|區|室|寮)$', text):
        if not text.endswith('長'):
            return True
    return False

def parse_metadata(text):
    """
    Optional: Extracts Salary/Rank if present in the Name field.
    """
    salary = ""
    rank = ""
    if not isinstance(text, str): return "", "", ""
    
    # Regex for Salary (e.g. 月八五)
    sal_match = re.search(r'月([一二三四五六七八九十百]+)', text)
    if sal_match:
        salary = sal_match.group(1)
        text = text.replace(sal_match.group(0), "")

    # Regex for Rank (e.g. 正七位)
    rank_match = re.search(r'([正従][一二三四五六七八][位]?)', text)
    if rank_match:
        rank = rank_match.group(1)
        text = text.replace(rank_match.group(1), "")

    return text.strip(" ,　"), salary, rank

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_csv", required=True)
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--year_col", default="DuringWar")
    args = parser.parse_args()

    # print(f"Loading data from {args.input_csv}...")
    try:
        df = pd.read_csv(args.input_csv)
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return

    # --- CRITICAL CHANGE ---
    # WE DO NOT SORT HERE. 
    # The input CSV is already sorted by Crop Order (Right->Left, Top->Bot) 
    # and Column Order (Right->Left) by the extraction script.
    # -----------------------

    # Load Headers
    headers_set = set()
    if os.path.exists(args.crosswalk):
        try:
            cw = pd.read_csv(args.crosswalk)
            if 'Is_Header' in cw.columns:
                headers_set = set(cw[cw['Is_Header'] == 1]['Japanese'].unique())
        except:
            pass

    compiled_rows = []
    current_office = "Unknown Office"

    for idx, row in df.iterrows():
        raw_name = str(row.get('name', '')).strip()
        raw_pos  = str(row.get('position', '')).strip()
        
        # Skip empty rows
        if raw_name == "nan": raw_name = ""
        if raw_pos == "nan": raw_pos = ""

        # 1. Header Detection
        # Sometimes a "Name" is actually a Header (e.g. "Civil Engineering Section")
        # We check raw_name because typically headers appear in the text body
        if is_header_candidate(raw_name, headers_set):
            current_office = raw_name
            # If it's a header line, we generally don't add it as a person record,
            # we just update the state.
            continue
        
        # 2. Process Person
        # We only add a row if there is actual content
        if raw_name or raw_pos:
            # Extract metadata (Salary/Rank) if mixed in text
            clean_name, salary, rank = parse_metadata(raw_name)

            entry = {
                'year': row.get('year', args.year_col),
                'office': current_office,
                'position': raw_pos,
                'name': clean_name,
                'salary': salary,
                'rank': rank,
                'page': row.get('folder', ''),
                'image': row.get('image', ''),
                'x': row.get('x', 0),
                'y': row.get('y', 0)
            }
            compiled_rows.append(entry)

    if compiled_rows:
        result_df = pd.DataFrame(compiled_rows)
        
        # Reorder columns for readability
        cols = ['year', 'office', 'position', 'name', 'salary', 'rank', 'page', 'image', 'x', 'y']
        # specific column order if they exist
        final_cols = [c for c in cols if c in result_df.columns]
        result_df = result_df[final_cols]

        result_df.to_csv(args.output, index=False, encoding='utf-8-sig')
        # print(f"Success! Compiled {len(result_df)} records.")
    else:
        print("Error: No entries compiled.")

if __name__ == "__main__":
    main()
