import pandas as pd
import argparse
import re
import os
import sys

# --- Sudachi for name validation ---
try:
    from sudachipy import dictionary, tokenizer
    _sudachi_tokenizer = dictionary.Dictionary().create()
    _sudachi_mode = tokenizer.Tokenizer.SplitMode.C
    print("SudachiPy initialized for name validation.")
except ImportError:
    print("Warning: SudachiPy not found. Falling back to heuristic name validation.")
    _sudachi_tokenizer = None
except Exception as e:
    print(f"Warning: SudachiPy init failed: {e}. Falling back to heuristic.")
    _sudachi_tokenizer = None


def is_header_candidate(text, headers_set):
    """
    Returns True if text is likely a Department/Office name.
    Detects offices by ending characters (課, 係, 局, etc.) and crosswalk.
    Leading circle symbols (◎, 〇, ○, etc.) are stripped before checking,
    as offices may or may not be prefixed with them.
    """
    if pd.isna(text):
        return False
    text = str(text).strip()
    if not text:
        return False

    # Reject OCR-malformed headers (leading parentheses/brackets from TOC)
    if text[0] in '({[（「【':
        return False

    # Strip leading circle symbols — offices may start with them
    circle_symbols = "◎〇O○o0〓●"
    cleaned = text.lstrip(circle_symbols).strip()
    if not cleaned:
        return False

    # 1. Check Explicit Crosswalk Headers (both original and circle-stripped)
    if text in headers_set or cleaned in headers_set:
        return True

    # 2. Pattern-based detection: office names end with these characters
    office_endings = set("課係所房合院室場局屋寮館康ム班部衛宿校署區")
    if len(cleaned) < 15 and cleaned[-1] in office_endings:
        # Reject position titles like 課長, 部長 (office ending + 長)
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


# Katakana given names that Sudachi classifies as common nouns rather than person names.
# These are unambiguously names in a personnel directory context.
_KATAKANA_GIVEN_NAMES = {
    'ヨシ', 'キヨ', 'ハナ', 'ハル', 'フミ', 'トミ', 'チヨ', 'シズ',
    'ウメ', 'マツ', 'キク', 'ツル', 'ミツ', 'タケ', 'サダ', 'トク',
    'マサ', 'カネ', 'ヤス', 'ナカ', 'タカ', 'シゲ', 'アキ', 'テル',
    'ミヨ', 'スミ', 'ノブ', 'ヒデ', 'トシ', 'クニ', 'イネ', 'トメ',
    'スエ', 'タミ', 'ヒサ', 'ムメ', 'リン', 'セツ', 'ミネ', 'フク',
}


def _sudachi_has_person_name(name):
    """
    Uses SudachiPy to check if the string contains person-name tokens.
    Returns True if at least one token is tagged 名詞/固有名詞/人名
    AND at least one person-name token is 2+ characters long.

    Single-kanji surname+given name pairs (e.g. 衞+務, 表+玄) are
    almost always OCR fragments, not real names. Real Japanese names
    have multi-character surnames (田中, 鈴木) or given names (太郎, 啓子).
    """
    if name in _KATAKANA_GIVEN_NAMES:
        return True
    tokens = _sudachi_tokenizer.tokenize(name, _sudachi_mode)
    name_chars = 0
    has_multi_char_token = False
    has_surname = False
    for token in tokens:
        pos = token.part_of_speech()
        if pos[0] == '名詞' and pos[1] == '固有名詞' and pos[2] == '人名':
            surface = token.surface()
            name_chars += len(surface)
            if len(surface) >= 2:
                has_multi_char_token = True
            if pos[3] == '姓':
                has_surname = True
    if name_chars < len(name) * 0.5:
        return False
    if not has_multi_char_token:
        return False
    # A standalone given name (no surname) must be 3+ chars to be credible
    if not has_surname and len(name) <= 2:
        return False
    return True


def is_plausible_name(name):
    """
    Returns True if name looks like a Japanese personal name.
    Primary: SudachiPy morphological analysis (人名 token check).
    Fallback: basic length/CJK heuristic if Sudachi unavailable.
    """
    if not name or not isinstance(name, str):
        return False
    name = name.strip()

    # Length check: Japanese names are 2-8 characters
    if len(name) < 2 or len(name) > 8:
        return False

    # Must be >=80% CJK or katakana
    n_cjk = sum(1 for c in name if '\u4e00' <= c <= '\u9fff'
                or '\u30a0' <= c <= '\u30ff'
                or '\u3400' <= c <= '\u4dbf')
    if n_cjk / len(name) < 0.8:
        return False

    # Use Sudachi if available
    if _sudachi_tokenizer is not None:
        return _sudachi_has_person_name(name)

    # --- Heuristic fallback (only if Sudachi unavailable) ---
    if re.search(r'[年月日]', name):
        return False
    if re.search(r'昭和|大正|明治|平成|現在|以上|以下', name):
        return False
    if re.search(r'[號條項則級俸給勳位階官]', name):
        return False
    if re.search(r'[課係局部署區室寮所院庁]$', name) and len(name) > 2:
        return False
    if len(name) > 3 and re.search(r'[のをはがでノヲハガデ]', name):
        return False
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


# ============================================================
# Office hierarchy inference
# ============================================================

# 旧字体 → 新字体 character normalization map
KYUJI_MAP = str.maketrans({
    '總': '総', '經': '経', '濟': '済', '勞': '労', '藥': '薬', '會': '会',
    '區': '区', '學': '学', '營': '営', '國': '国', '實': '実', '產': '産',
    '醫': '医', '檢': '検', '衞': '衛', '稅': '税', '關': '関', '灣': '湾',
    '觀': '観', '權': '権', '獸': '獣', '險': '険', '驗': '験', '雜': '雑',
    '對': '対', '畫': '画', '處': '処', '兒': '児', '賣': '売', '靈': '霊',
    '澁': '渋', '淺': '浅', '收': '収', '纖': '繊', '廳': '庁', '廣': '広',
    '鐵': '鉄', '證': '証', '條': '条', '單': '単',
})

_OFFICE_LEADING_SYMBOLS = '〓◇△○□〔◎〇Oo0●'

# Level-3 compound endings — sorted longest-first so maximal match wins
_L3_COMPOUNDS = sorted([
    '地方事務所', '出納員室',
    '営業所', '出張所', '試験所', '研究所', '事務所', '事業所', '保健所',
    '清掃所', '取締所', '指導所', '訓練所', '検定所', '相談所', '処分場',
    '作業所', '診療所', '保養所', '授産場', '種畜場', '消毒所',
    '試験場', '区役所',
    '工場', '分場', '支所',
], key=len, reverse=True)

# Level-1 exact matches (checked before any suffix rule)
_L1_EXACT = frozenset({'知事室', '出納長室', '中央卸売市場'})

# 院-ending names that are NOT level-1
_L1_BLOCKED_IN = ('分院', '病院', '乳児院', '看護学院')

# Level-3 simple suffixes (checked after compounds)
_L3_SIMPLE = ('課', '室', '署', '場', '所')


def normalize_office(text):
    """Strip leading symbols and apply 旧字体→新字体 normalization."""
    if not isinstance(text, str) or not text:
        return ''
    text = text.strip().lstrip(_OFFICE_LEADING_SYMBOLS).strip()
    return text.translate(KYUJI_MAP)


def classify_office_level(normed):
    """
    Classify a normalized office name to its hierarchy level.
    Returns 1 (局), 2 (部), 3 (課-equivalent), 4 (係), or None if unmatched.

    Check order (longest/most-specific first):
      1. Level-1 exact matches
      2. Level-3 compound endings (longest first)
      3. Level-4 (ends with 係)
      4. Level-1 (ends with 局 or qualifying 院)
      5. Level-2 (ends with 部)
      6. Level-3 simple endings (課 室 署 場 所)
    """
    if not normed:
        return None
    # 1. Level-1 exact matches
    if normed in _L1_EXACT:
        return 1
    # 2. Level-3 compound endings
    for comp in _L3_COMPOUNDS:
        if normed.endswith(comp):
            return 3
    # 3. Level-4
    if normed.endswith('係'):
        return 4
    # 4. Level-1: 局, or 院 not in blocked list
    if normed.endswith('局'):
        return 1
    if normed.endswith('院') and not any(normed.endswith(b) for b in _L1_BLOCKED_IN):
        return 1
    # 5. Level-2
    if normed.endswith('部'):
        return 2
    # 6. Level-3 simple
    for suf in _L3_SIMPLE:
        if normed.endswith(suf):
            return 3
    return None


def infer_office_hierarchy(df):
    """
    Add office hierarchy columns to the compiled DataFrame.

    New columns added:
      office_norm  — normalized office name (旧字体→新字体, leading symbols stripped)
      off_level    — hierarchy level: 1=局, 2=部, 3=課-equivalent, 4=係 (NaN if unmatched)
      kyoku        — 局 this row belongs to (forward-filled within year)
      bu           — 部 this row belongs to (resets on new 局 or 部)
      ka           — 課 this row belongs to (resets on new 局, 部, or 課)
      kakari       — 係 this row belongs to (resets on any new level)

    Uses the cumulative-group technique: a new group starts whenever a
    header of the relevant level (or higher) transitions in, then all rows
    in that group are filled with the header value via groupby-first.
    """
    df = df.copy()
    df['office_norm'] = df['office'].apply(normalize_office)
    df['off_level'] = df['office_norm'].apply(classify_office_level)

    parts = []
    for _year, ydf in df.groupby('year', sort=False):
        ydf = ydf.copy()

        # Detect rows where the office section transitions
        changed = ydf['office'] != ydf['office'].shift()
        lvl = ydf['off_level']

        is_l1 = (lvl == 1) & changed
        is_l2 = (lvl == 2) & changed
        is_l3 = (lvl == 3) & changed
        is_l4 = (lvl == 4) & changed

        # Cumulative group IDs — increment at each relevant transition
        kyoku_grp  = is_l1.cumsum()
        bu_grp     = (is_l1 | is_l2).cumsum()
        ka_grp     = (is_l1 | is_l2 | is_l3).cumsum()
        kakari_grp = (is_l1 | is_l2 | is_l3 | is_l4).cumsum()

        # Place the office name only at the header row that opens each group
        norm = ydf['office_norm']
        ydf['_k']  = norm.where(is_l1)
        ydf['_b']  = norm.where(is_l2)
        ydf['_ka'] = norm.where(is_l3)
        ydf['_kk'] = norm.where(is_l4)

        # Forward-fill: all rows in a group receive the header value
        # groupby().first() skips NaN, so only the non-NaN header value propagates
        ydf['kyoku']  = ydf.groupby(kyoku_grp )['_k' ].transform('first')
        ydf['bu']     = ydf.groupby(bu_grp    )['_b' ].transform('first')
        ydf['ka']     = ydf.groupby(ka_grp    )['_ka'].transform('first')
        ydf['kakari'] = ydf.groupby(kakari_grp)['_kk'].transform('first')

        ydf.drop(columns=['_k', '_b', '_ka', '_kk'], inplace=True)
        parts.append(ydf)

    return pd.concat(parts) if parts else df


def _print_hierarchy_diagnostics(df):
    """Print hierarchy inference summary and unmatched office names."""
    n = len(df)
    level_labels = {1: '局', 2: '部', 3: '課-eq', 4: '係'}

    print("\n--- Office hierarchy level distribution ---")
    for lvl, label in sorted(level_labels.items()):
        mask = df['off_level'] == lvl
        n_rows = int(mask.sum())
        n_unique = int(df.loc[mask, 'office_norm'].nunique())
        print(f"  Level {lvl} ({label:5s}): {n_rows:6d} rows, {n_unique:4d} unique offices")
    n_none = int(df['off_level'].isna().sum())
    print(f"  Unmatched:         {n_none:6d} rows")

    print("\n--- Hierarchy fill rates ---")
    for col in ('kyoku', 'bu', 'ka', 'kakari'):
        n_filled = int(df[col].notna().sum())
        pct = 100 * n_filled / n if n else 0.0
        print(f"  {col:8s}: {n_filled:6d} / {n} ({pct:.1f}%)")

    # Unmatched Japanese office names — useful for rule refinement
    has_cjk = df['office_norm'].str.contains(
        r'[\u4e00-\u9fff\u3400-\u4dbf]', regex=True, na=False)
    unmatched = (
        df[df['off_level'].isna() & has_cjk]
        .groupby('office_norm', dropna=False)
        .size()
        .sort_values(ascending=False)
    )
    if len(unmatched):
        print(f"\n--- Unmatched Japanese office names "
              f"({len(unmatched)} unique, {int(unmatched.sum())} rows) ---")
        for name, cnt in unmatched.head(30).items():
            print(f"  {cnt:4d}  {name!r}")
        if len(unmatched) > 30:
            print(f"  ... and {len(unmatched) - 30} more")
    else:
        print("\nAll Japanese office names matched a hierarchy level.")


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
    parser.add_argument("--start_page", type=int, default=None,
                        help="First page of personnel data (skip preamble before this)")
    parser.add_argument("--end_page", type=int, default=None,
                        help="Last page of personnel data (skip appendix after this)")
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

    # --- Page range filtering ---
    use_page_range = args.start_page is not None or args.end_page is not None
    if use_page_range:
        start_pg = args.start_page if args.start_page is not None else 0
        end_pg = args.end_page if args.end_page is not None else 999999
        print(f"Page range filter: pages {start_pg} to {end_pg}")

    # --- Main compilation loop ---
    compiled_rows = []
    current_office = "Unknown Office"
    current_position = "Unknown"  # Stateful position tracking
    position_person_count = 0  # Track how many people assigned current position

    n_noise_filtered = 0
    n_page_filtered = 0
    n_position_headers = 0
    n_position_propagated = 0

    for idx, row in df.iterrows():
        raw_name = str(row.get('name', '')).strip()
        raw_pos = str(row.get('position', '')).strip()

        if raw_name == "nan": raw_name = ""
        if raw_pos == "nan": raw_pos = ""

        # --- Step 0a: Page range filter (human-specified) ---
        if use_page_range:
            page_num = int(row.get('folder', 0))
            if page_num < start_pg or page_num > end_pg:
                n_page_filtered += 1
                continue

        # --- Step 0b: Filter OCR noise ---
        if is_likely_noise(row):
            n_noise_filtered += 1
            continue

        # --- Step 1: Office header detection (pattern-based) ---
        raw_text = str(row.get('raw_text', '')).strip()
        if raw_text == "nan": raw_text = ""

        if is_header_candidate(raw_name, headers_set):
            current_office = raw_name
            continue
        if raw_pos and is_header_candidate(raw_pos, headers_set):
            current_office = raw_pos
            continue
        # Also check raw_text for office names that stage 1 didn't classify
        if raw_text and not raw_name and not raw_pos:
            if is_header_candidate(raw_text, headers_set):
                current_office = raw_text
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

            # Detect drafted (military conscription) keywords in raw text
            draft_keywords = ["應召", "召中", "應徴", "徴中", "入營", "營中"]
            is_drafted = any(k in raw_text for k in draft_keywords)

            entry = {
                'year': row.get('year', args.year_col),
                'office': current_office,
                'position': effective_pos,
                'grade': grade,
                'name': clean_name,
                'is_name': name_flag,
                'drafted': is_drafted,
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

        # --- Infer office hierarchy ---
        result_df = infer_office_hierarchy(result_df)
        _print_hierarchy_diagnostics(result_df)

        cols = ['year', 'office', 'office_norm', 'off_level',
                'kyoku', 'bu', 'ka', 'kakari',
                'position', 'grade', 'name',
                'is_name', 'drafted', 'gender_legacy', 'gender_modern',
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
        if use_page_range:
            print(f"  Page-range filtered:     {n_page_filtered}")
        print(f"  Noise rows filtered:     {n_noise_filtered}")

        n_is_name = result_df['is_name'].sum()
        n_female_legacy = (result_df['gender_legacy'] == 'female').sum()
        n_female_modern = (result_df['gender_modern'] == 'female').sum()
        print(f"  Plausible names:         {n_is_name} / {n_total} "
              f"({100*n_is_name/n_total:.1f}%)")
        print(f"  Female (legacy):         {n_female_legacy}")
        print(f"  Female (modern):         {n_female_modern}")
        n_drafted = result_df['drafted'].sum()
        print(f"  Drafted:                 {n_drafted}")
    else:
        print("Error: No entries compiled.")


if __name__ == "__main__":
    main()
