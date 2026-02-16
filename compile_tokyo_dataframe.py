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
    Filter out OCR noise from cross-column reads, regulatory text,
    library stamps, page references, and other non-personnel content.
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

    # 4. Ellipsis/dot patterns (page references like "……一五三")
    if re.search(r'[…・．\.]{2,}', raw):
        return True

    # 5. Classical grammar particle density (regulatory text like "ヲ調査蒐録ス")
    if len(raw) > 8:
        classical_particles = set('ハノヲニスル')
        n_particles = sum(1 for c in raw if c in classical_particles)
        if n_particles / len(raw) > 0.15:
            return True

    # 6. Library stamps
    if re.search(r'図書館|蔵書|東京都立', raw):
        return True

    # 7. Numeric-dominated (>50% digits or kanji numerals)
    if raw:
        kanji_nums = set('一二三四五六七八九十百千万〇零')
        n_numeric = sum(1 for c in raw if c.isdigit() or c in kanji_nums)
        if len(raw) > 2 and n_numeric / len(raw) > 0.5:
            return True

    # 8. Phone/address patterns without a valid position
    if re.search(r'番', raw) and str(row.get('position', '')) == 'Unknown':
        if re.search(r'[〇一二三四五六七八九十\d].*番', raw):
            return True

    return False


def is_plausible_name(name):
    """
    Returns True if name looks like a Japanese personal name.
    Used to flag rows for downstream filtering (is_name column).
    """
    if not name or not isinstance(name, str):
        return False
    name = name.strip()

    # Length check: Japanese names are 2-8 characters
    if len(name) < 2 or len(name) > 8:
        return False

    # Must be >=80% CJK or katakana
    n_cjk = sum(1 for c in name if '\u4e00' <= c <= '\u9fff'  # CJK unified
                or '\u30a0' <= c <= '\u30ff'  # Katakana
                or '\u3400' <= c <= '\u4dbf')  # CJK extension A
    if n_cjk / len(name) < 0.8:
        return False

    # Reject hiragana/katakana grammatical particles in names > 3 chars
    if len(name) > 3 and re.search(r'[のをはがでノヲハガデ]', name):
        return False

    # Reject strings with classical verb endings (ス,ル,リ,ム) typical of regulatory text
    if len(name) > 4:
        classical_particles = set('ハノヲニスルリム')
        n_particles = sum(1 for c in name if c in classical_particles)
        if n_particles / len(name) > 0.15:
            return False

    # Reject strings that are purely kanji numerals
    kanji_nums = set('一二三四五六七八九十百千万〇零')
    if all(c in kanji_nums for c in name):
        return False

    return True


def classify_gender_legacy(name):
    """
    Gender classification matching the legacy R heuristic.
    Checks female kanji endings against a surname blocklist.
    """
    if not name or not isinstance(name, str):
        return ""
    name = name.strip()
    if not name:
        return ""

    surname_blocklist = re.compile(
        r'^(金子|増子|尼子|砂子|白子|呼子|舞子|神子)$')
    female_kanji_pat = re.compile(r'[子枝江代紀美恵貴]$|婦$|^[小]?[佐]?[美]')

    if surname_blocklist.match(name):
        return "male"
    if female_kanji_pat.search(name):
        return "female"
    return "male"


def classify_gender_modern(name):
    """
    Extended gender heuristic with katakana given names and broader kanji endings.
    """
    if not name or not isinstance(name, str):
        return ""
    name = name.strip()
    if not name:
        return ""

    surname_blocklist = re.compile(
        r'^(金子|増子|尼子|砂子|白子|呼子|舞子|神子|平子|星子|鳴子|'
        r'銚子|逗子|厨子|対子|硝子|茄子|種子|扇子|格子|障子|帽子)$')

    if surname_blocklist.match(name):
        return "male"

    # Extended kanji endings
    female_kanji_pat = re.compile(
        r'[子枝江代紀美恵貴乃花世奈穂織里香]$|婦$|^[小]?[佐]?[美]')
    if female_kanji_pat.search(name):
        return "female"

    # Katakana female given names (common in pre-war/wartime era)
    katakana_female = {
        'ヨシ', 'キヨ', 'ハナ', 'ハル', 'フミ', 'トミ', 'チヨ', 'シズ',
        'ウメ', 'マツ', 'キク', 'ツル', 'ミツ', 'タケ', 'サダ', 'トク',
        'マサ', 'カネ', 'ヤス', 'ナカ', 'タカ', 'シゲ', 'アキ', 'テル',
        'ミヨ', 'スミ', 'ノブ', 'ヒデ', 'トシ', 'クニ',
    }
    # For 2-char names, check if the whole name matches katakana female
    if len(name) == 2 and name in katakana_female:
        return "female"
    # For longer names, check if the name ends with a katakana female given name
    if len(name) > 2:
        suffix = name[-2:]
        if suffix in katakana_female:
            return "female"

    return "male"


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

            name_flag = is_plausible_name(clean_name)
            entry = {
                'year': row.get('year', args.year_col),
                'office': current_office,
                'position': effective_pos,
                'grade': grade,
                'name': clean_name,
                'is_name': name_flag,
                'gender_legacy': classify_gender_legacy(clean_name) if name_flag else "",
                'gender_modern': classify_gender_modern(clean_name) if name_flag else "",
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
                'is_name', 'gender_legacy', 'gender_modern',
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

        n_is_name = result_df['is_name'].sum()
        n_female_legacy = (result_df['gender_legacy'] == 'female').sum()
        n_female_modern = (result_df['gender_modern'] == 'female').sum()
        print(f"  Plausible names:         {n_is_name} / {n_total} "
              f"({100*n_is_name/n_total:.1f}%)")
        print(f"  Female (legacy):         {n_female_legacy}")
        print(f"  Female (modern):         {n_female_modern}")
    else:
        print("Error: No entries compiled.")


if __name__ == "__main__":
    main()
