import pandas as pd
import argparse
import os
import re

def load_position_titles(csv_path, column_name='DuringWar'):
    if not os.path.exists(csv_path):
        print(f"Warning: Crosswalk file not found at {csv_path}")
        return []
    try:
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding='shift-jis')
        if column_name not in df.columns:
            column_name = df.columns[0]
        titles = df[column_name].dropna().unique().tolist()
        titles.sort(key=len, reverse=True)
        return titles
    except Exception as e:
        print(f"Warning: Could not load crosswalk ({e}).")
        return []

def parse_imperial_metadata(raw_text):
    """Dissects strings like '月八五一七上, 時田愼雄' into (CleanName, Salary, Rank)."""
    if not raw_text: return "", None, None
    salary_match = re.search(r'月([一二三四五六七八九十百]+)', raw_text)
    salary = f"月{salary_match.group(1)}" if salary_match else None
    rank_match = re.search(r'([一二三四五六七八九十])([上下正從])', raw_text)
    rank = rank_match.group(0) if rank_match else None
    # Clean name by removing metadata and noise
    name = re.sub(r'月[一二三四五六七八九十百]+|([一二三四五六七八九十])([上下正從])|[\s,、]+', '', raw_text)
    name = name.strip(' ,.()=+-〓*')
    return name, salary, rank

def split_position_and_name(text, titles):
    clean_text = re.sub(r'[【ヿ〓○●◎]', '', str(text).strip())
    for title in titles:
        if clean_text.startswith(title):
            remainder = clean_text[len(title):].strip(" ,　")
            if remainder: return title, remainder
    return clean_text, "" 

def main():
    parser = argparse.ArgumentParser(description="Layout-Aware Hierarchy Compiler")
    parser.add_argument("--input_csv", required=True)
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--output", default="Final_Compiled_Directory.csv")
    parser.add_argument("--year_col", default="DuringWar")
    args = parser.parse_args()

    print(f"Loading data from {args.input_csv}...")
    df = pd.read_csv(args.input_csv).fillna("")
    known_titles = load_position_titles(args.crosswalk, args.year_col)

    # Configuration for structural logic
    SINGULAR_TITLES = ["區長", "局長", "課長", "署長", "館長", "所長", "会長", "院長", "校長"]
    Y_EPSILON = 10  # Pixels within which fragments are considered on the same 'line'

    current_office = "Unknown Office"
    current_position = "Employee"
    compiled_rows = []

    # Step 1: Group by Page to process systematically
    pages = df.sort_values(by=['page_number', 'y', 'x'])
    
    for page_id, page_df in pages.groupby('page_number', sort=False):
        # Round Y coordinates to group names into physical 'rows'
        # This allows us to see how many people share a horizontal line
        page_df = page_df.copy()
        page_df['y_row'] = (page_df['y'].astype(float) / Y_EPSILON).round() * Y_EPSILON
        
        for y_val, row_group in page_df.groupby('y_row', sort=False):
            
            # --- PHASE A: Update Anchors ---
            # Check if this physical row contains an Office or Position label
            for _, row in row_group.iterrows():
                lbl, txt = row['label'], str(row['text']).strip()
                if lbl == 'Office':
                    current_office = txt
                    current_position = "Employee" # Reset position on new office
                elif lbl == 'Position':
                    current_position = txt
                elif lbl == 'Position_and_Name':
                    pos_part, name_part = split_position_and_name(txt, known_titles)
                    if pos_part: current_position = pos_part

            # --- PHASE B: Count Row Density ---
            # Identify all name-containing fragments in this row
            name_fragments = row_group[row_group['label'].isin(['Name', 'NameSudachi', 'Position_and_Name'])]
            
            # Extract individual names from fragments (handling comma separation)
            names_in_row_raw = []
            for _, n_frag in name_fragments.iterrows():
                txt = n_frag['text']
                if n_frag['label'] == 'Position_and_Name':
                    _, txt = split_position_and_name(txt, known_titles)
                
                parts = [p.strip() for p in re.split(r'[,，、]', txt) if len(p.strip()) > 1]
                names_in_row_raw.extend(parts)

            names_count = len(names_in_row_raw)

            # --- PHASE C: Structural Inference ---
            # RULE: If 2 or 3 names share a line, they are by definition not 'Singular Elite'
            # We downgrade the position if it's not a known 'Mass Elite' title like 主事
            if names_count >= 2:
                if not any(t in current_position for t in ["主事", "技師"]):
                    current_position = "雇 (Employee/Stacked)"

            # --- PHASE D: Compile Records ---
            for entry_text in names_in_row_raw:
                clean_n, sal, rnk = parse_imperial_metadata(entry_text)
                if len(clean_n) < 2: continue

                compiled_rows.append({
                    'folder': row_group.iloc[0].get('sort_folder_num', ''),
                    'page': page_id,
                    'image': row_group.iloc[0].get('image_name', ''),
                    'office': current_office,
                    'position': current_position,
                    'name': clean_n,
                    'salary_kanji': sal,
                    'rank_kanji': rnk,
                    'names_per_row': names_count,
                    'is_elite_structure': names_count == 1,
                    'drafted': False
                })

                # One-Shot Title Reset (Ward Mayor etc only apply to the FIRST name found)
                if names_count == 1 and any(s in current_position for s in SINGULAR_TITLES):
                    current_position = "Employee"

            # --- PHASE E: Draft Marker ---
            if any(row_group['label'] == 'Drafted') and compiled_rows:
                compiled_rows[-1]['drafted'] = True

    # Final Export
    if compiled_rows:
        result_df = pd.DataFrame(compiled_rows)
        cols = ['office', 'position', 'name', 'salary_kanji', 'rank_kanji', 
                'names_per_row', 'is_elite_structure', 'drafted', 'folder', 'page', 'image']
        result_df[cols].to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f"Success! {len(result_df)} records compiled with layout-aware logic.")
    else:
        print("Error: No entries compiled.")

if __name__ == "__main__":
    main()
