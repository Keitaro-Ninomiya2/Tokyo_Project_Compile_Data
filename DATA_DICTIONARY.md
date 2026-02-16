# Data Dictionary: Tokyo Personnel Master CSV

This document describes all columns in the final `Tokyo_Personnel_Master_All_Years_v2.csv` output.

## Columns

| Column | Type | Description |
|--------|------|-------------|
| `year` | int | Directory publication year (1937-1960) |
| `gov_level` | str | Government level: `TokyoShi` (東京市), `TokyoFu` (東京府), or `TokyoTo` (東京都) |
| `office` | str | Office/department name extracted from directory headers (e.g., 総務局, 土木課) |
| `office_id` | int | Deterministic numeric office ID (alphabetically sorted) for fixed-effects regressions |
| `position` | str | Position title matched against `PositionCrosswalk.csv`. `Unknown` if unmatched |
| `grade` | str | Civil service grade in kanji (e.g., 七上). Empty if not present |
| `name` | str | Personal name after metadata stripping (salary, rank, grade removed) |
| `is_name` | bool | `True` if the name field passes plausibility checks (length 2-8, CJK-dominated, no particles). Non-name rows are kept but flagged for researcher filtering |
| `gender_legacy` | str | Gender via R-equivalent heuristic: checks female kanji endings (子,枝,江,代,etc.) against surname blocklist. Only populated when `is_name=True` |
| `gender_modern` | str | Gender via extended heuristic: adds katakana female given names (ヨシ,キヨ,ハナ,etc.) and broader kanji endings (乃,花,世,奈,etc.). Only populated when `is_name=True` |
| `staff_id` | int | Cross-year person identifier. Assigned by exact `(name, office)` grouping, then fuzzy matching (similarity >= 0.85) for names > 2 chars within the same office. `NaN` for non-name rows |
| `salary` | str | Monthly salary in kanji numerals (e.g., 七五). Extracted from raw OCR text |
| `rank` | str | Court rank (e.g., 正八位, 従六位). Extracted from raw OCR text |
| `page` | int | Source page/folder number from the digitized directory |
| `image` | str | Crop image filename from OCR pipeline |
| `x` | int | Text line x-coordinate (right-to-left reading order in traditional vertical text) |
| `y` | int | Text line y-coordinate (top-to-bottom within columns) |

## Gender Classification Details

### Legacy Method (`gender_legacy`)
Replicates the original R-based heuristic:
- **Female** if name matches `[子枝江代紀美恵貴]$` or `婦$` or `^[小]?[佐]?[美]`
- **Male** if name is in surname blocklist (金子, 増子, 尼子, 砂子, 白子, 呼子, 舞子, 神子) or does not match female patterns
- Only applied to rows where `is_name=True`

### Modern Method (`gender_modern`)
Extends legacy with:
- Additional kanji endings: 乃, 花, 世, 奈, 穂, 織, 里, 香
- Katakana female given names common in pre-war/wartime era (ヨシ, キヨ, ハナ, ハル, フミ, トミ, チヨ, シズ, ウメ, マツ, キク, ツル, etc.)
- Expanded surname blocklist (adds 平子, 星子, 鳴子, etc.)
- For 2-character names: requires exact match against katakana list (higher confidence threshold)

## Noise Filtering (`is_name`)

Rows flagged `is_name=False` include:
- Regulatory/legal text from directory preambles
- Table-of-contents entries and page references
- Library stamps (図書館, 蔵書, 東京都立)
- Phone numbers and addresses
- OCR artifacts (Latin-dominated strings, ellipsis patterns)
- Single-character fragments

These rows are **retained** in the dataset for transparency. Filter with `df[df['is_name'] == True]` for analysis.

## Staff ID Notes

- Exact match: rows sharing the same `(name, office)` pair receive the same `staff_id`
- Fuzzy match: within each office, names > 2 characters with similarity >= 0.85 are merged into the same ID
- Names <= 2 characters only match exactly (too ambiguous for fuzzy matching)
- `staff_id` is `NaN` for rows where `is_name=False`
