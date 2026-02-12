import pandas as pd
import argparse
import re
import os
import sys


def is_header_candidate(text, headers_set):
    """
    Returns True if text is likely a Department/Office name.
    """
    if pd.isna(text):
        return False
    text = str(text).strip()

    # 1. Check Explicit Crosswalk Headers
    if text in headers_set:
        return True

    # 2. Heuristics (Ends in Section/Bureau)
    if len(text) < 15 and re.search(r'(課|係|局|部|署|區|室|寮)$', text):
        if not text.endswith('長'):
            return True
    return False


def is_position_only_row(row, known_positions):
    """
    Detect rows where the line is ONLY a position title (no person name).
    These are standalone position headers in the directory layout.
    
    Indicators:
      - position is a known title AND name is empty/NaN
      - OR: raw_text exactly matches a known position
      - OR: name field itself is a known position (misclassified by stage 1)
    """
    pos = str(row.get('position', '')).strip()
    name = str(row.get('name', '')).strip()
    raw = str(row.get('raw_text', '')).strip()

    if pos == 'nan': pos = ''
    if name == 'nan': name = ''

    # Case 1: Stage 1 matched a position and name is empty
    if pos and pos != 'Unknown' and not name:
        return True, pos

    # Case 2: The entire raw_text is itself a known position
    if raw in known_positions:
        return True, raw

    # Case 3: Name field is actually a known position
    if name in known_positions and (not pos or pos == 'Unknown'):
        return True, name

    return False, None


def is_likely_noise(row):
    """
    Filter out OCR noise from cross-column reads.
    """
    raw = str(row.get('raw_text', ''))
    name = str(row.get('name', ''))

    # 1. Latin/symbol dominated lines (like "RT/0・317/88/GA")
    if raw and len(raw) > 3:
        n_latin = sum(1 for c in raw if c.isascii() and c.isalpha())
        if n_latin / len(raw) > 0.4:
            return True

    # 2. Very long raw_text with no position match — likely cross-column read
    if len(raw) > 25 and str(row.get('position', '')) == 'Unknown':
        unique_ratio = len(set(raw)) / len(raw) if raw else 0
        if unique_ratio > 0.7:
            return True

    # 3. Single-char name from long raw_text (fragment from bad split)
    if len(name) == 1 and len(raw) > 15:
        return True

    return False


def parse_metadata_fallback(text):
    """
    Fallback metadata extraction for v1 format CSVs.
    """
    salary = ""
    rank = ""
    if not isinstance(text, str):
        return "", "", ""

    sal_match = re.search(r'月([一二三四五六七八九十百〇]+)', text)
    if sal_match:
        salary = sal_match.group(1)
        text = text[:sal_match.start()] + text[sal_match.end():]

    rank_match = re.search(r'([正従][一二三四五六七八九十][位]?)', text)
    if rank_match:
        rank = rank_match.group(1)
        text = text[:rank_match.start()] + text[rank_match.end():]

    return text.strip(" ,　"), salary, rank


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_csv", required=True)
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--year_col", default="DuringWar")
    args = parser.parse_args()

    try:
        df = pd.read_csv(args.input_csv)
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return

    has_v2_columns = all(c in df.columns for c in ['grade', 'salary', 'rank'])

    # --- Load ALL known positions from crosswalk (all columns) ---
    known_positions = set()
    headers_set = set()
    if os.path.exists(args.crosswalk):
        try:
            cw = pd.read_csv(args.crosswalk)
            title_cols = ['Japanese', 'DuringWar', 'TokyoFu', 'Merged',
                          'BeforeWar', 'AfterWar']
            for col in title_cols:
                if col in cw.columns:
                    vals = cw[col].dropna().astype(str).str.strip().unique()
                    known_positions.update(v for v in vals if v)
            known_positions.discard('')

            if 'Is_Header' in cw.columns:
                headers_set = set(cw[cw['Is_Header'] == 1]['Japanese'].unique())
        except:
            pass

    print(f"Loaded {len(known_positions)} position titles, "
          f"{len(headers_set)} office headers from crosswalk.")

    # --- Single-person positions: only the first name gets the title ---
    single_person_positions = {'課長', '主事', '技師'}

    # --- Main compilation loop ---
    compiled_rows = []
    current_office = "Unknown Office"
    current_position = "Unknown"  # Stateful position tracking
    position_person_count = 0  # Track how many people assigned current position

    n_noise_filtered = 0
    n_position_headers = 0
    n_position_propagated = 0

    for idx, row in df.iterrows():
        raw_name = str(row.get('name', '')).strip()
        raw_pos = str(row.get('position', '')).strip()

        if raw_name == "nan": raw_name = ""
        if raw_pos == "nan": raw_pos = ""

        # --- Step 0: Filter OCR noise ---
        if is_likely_noise(row):
            n_noise_filtered += 1
            continue

        # --- Step 1: Office header detection ---
        if is_header_candidate(raw_name, headers_set):
            current_office = raw_name
            continue
        if raw_pos and is_header_candidate(raw_pos, headers_set):
            current_office = raw_pos
            continue

        # --- Step 2: Standalone position header detection ---
        is_pos_header, detected_pos = is_position_only_row(
            row, known_positions)
        if is_pos_header:
            current_position = detected_pos
            position_person_count = 0  # Reset counter for new position
            n_position_headers += 1
            continue

        # --- Step 3: Process person row ---
        if raw_name or raw_pos:
            # Use explicit match if available, otherwise propagate
            if raw_pos and raw_pos != 'Unknown':
                effective_pos = raw_pos
                current_position = raw_pos
                position_person_count = 1  # This person is the first
            elif current_position != "Unknown":
                # Check single-person rule before propagating
                if current_position in single_person_positions and position_person_count >= 1:
                    # Already assigned this single-person position to someone
                    effective_pos = "Unknown"
                else:
                    effective_pos = current_position
                    position_person_count += 1
                    n_position_propagated += 1
            else:
                effective_pos = "Unknown"

            if has_v2_columns:
                clean_name = raw_name
                salary = str(row.get('salary', '')).strip()
                rank = str(row.get('rank', '')).strip()
                grade = str(row.get('grade', '')).strip()
                if salary == "nan": salary = ""
                if rank == "nan": rank = ""
                if grade == "nan": grade = ""
            else:
                clean_name, salary, rank = parse_metadata_fallback(raw_name)
                grade = ""

            entry = {
                'year': row.get('year', args.year_col),
                'office': current_office,
                'position': effective_pos,
                'grade': grade,
                'name': clean_name,
                'salary': salary,
                'rank': rank,
                'page': row.get('folder', ''),
                'image': row.get('image', ''),
                'x': row.get('x', 0),
                'y': row.get('y', 0),
            }
            compiled_rows.append(entry)

    # --- Output ---
    if compiled_rows:
        result_df = pd.DataFrame(compiled_rows)

        cols = ['year', 'office', 'position', 'grade', 'name',
                'salary', 'rank', 'page', 'image', 'x', 'y']
        final_cols = [c for c in cols if c in result_df.columns]
        result_df = result_df[final_cols]

        result_df.to_csv(args.output, index=False, encoding='utf-8-sig')

        n_total = len(result_df)
        n_with_office = (result_df['office'] != 'Unknown Office').sum()
        n_with_pos = (result_df['position'] != 'Unknown').sum()

        print(f"Success! Compiled {n_total} records to {args.output}")
        print(f"  Office assigned:    {n_with_office} / {n_total} "
              f"({100*n_with_office/n_total:.1f}%)")
        print(f"  Position assigned:  {n_with_pos} / {n_total} "
              f"({100*n_with_pos/n_total:.1f}%)")
        print(f"  Position headers found:  {n_position_headers}")
        print(f"  Positions propagated:    {n_position_propagated}")
        print(f"  Noise rows filtered:     {n_noise_filtered}")
    else:
        print("Error: No entries compiled.")


if __name__ == "__main__":
    main()
