import pandas as pd
import argparse
import os
import re

def load_position_titles(csv_path, column_name='DuringWar'):
    """
    Loads titles from the crosswalk to help split 'Position_and_Name' lines.
    """
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
    """
    Dissects strings like '月八五結束進一七上, 時田愼雄' 
    into Salary, Rank, and Clean Name.
    """
    if not raw_text:
        return "", None, None

    # 1. Extract Salary (e.g., 月八五, 月七五)
    salary_match = re.search(r'月([一二三四五六七八九十百]+)', raw_text)
    salary = f"月{salary_match.group(1)}" if salary_match else None
    
    # 2. Extract Rank (e.g., 七上, 六下, 八正, 從七)
    rank_match = re.search(r'([一二三四五六七八九十])([上下正從])', raw_text)
    rank = rank_match.group(0) if rank_match else None
    
    # 3. Clean Name
    # Remove the salary, rank, and leading/trailing junk/commas
    clean_name = re.sub(r'月[一二三四五六七八九十百]+|([一二三四五六七八九十])([上下正從])|[\s,、]+', '', raw_text)
    clean_name = clean_name.strip(' ,.()=+-〓*')
    
    return clean_name, salary, rank

def split_position_and_name(text, titles):
    clean_text = str(text).strip()
    clean_text = re.sub(r'[【ヿ〓○●◎]', '', clean_text)
    
    for title in titles:
        if clean_text.startswith(title):
            remainder = clean_text[len(title):].strip(" ,　")
            if remainder:
                return title, remainder
    return clean_text, "" 

def main():
    parser = argparse.ArgumentParser(description="Compile parsed lines into a structured DataFrame")
    parser.add_argument("--input_csv", required=True)
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--output", default="Final_Compiled_Directory.csv")
    parser.add_argument("--year_col", default="DuringWar")
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv)
    df['text'] = df['text'].fillna("")
    known_titles = load_position_titles(args.crosswalk, args.year_col)

    # Singular high-ranking titles that should not "stick" to subordinates
    SINGULAR_TITLES = ["區長", "局長", "課長", "署長", "館長", "所長", "会長", "院長", "校長"]

    current_office = "Unknown Office"
    current_position = "Employee" 
    compiled_rows = []

    for idx, row in df.iterrows():
        label = str(row['label'])
        text = str(row['text']).strip()
        
        page_num = row.get('page_number', '')
        img_name = row.get('image_name', '')
        folder_num = row.get('sort_folder_num', '')

        if label == 'Office':
            current_office = text
            current_position = "Employee"
            
        elif label == 'Position':
            current_position = text
            
        elif label in ['Position_and_Name', 'NameSudachi']:
            # Handle possible combined position if necessary
            raw_content = text
            if label == 'Position_and_Name':
                pos_part, name_part = split_position_and_name(text, known_titles)
                if pos_part: current_position = pos_part
                raw_content = name_part if name_part else text

            # Split entries (in case of multiple names in one block)
            entries = [e.strip() for e in raw_content.split(',') if e.strip()]
            
            for entry in entries:
                clean_n, sal, rnk = parse_imperial_metadata(entry)
                if len(clean_n) < 2: continue

                compiled_rows.append({
                    'folder': folder_num,
                    'page': page_num,
                    'image': img_name,
                    'office': current_office,
                    'position': current_position,
                    'name': clean_n,
                    'salary_kanji': sal,
                    'rank_kanji': rnk,
                    'drafted': False
                })

                # Selective Reset: If the position is a 'Chief' role, reset it immediately
                if any(singular in current_position for singular in SINGULAR_TITLES):
                    current_position = "Employee"

        elif label == 'Drafted':
            if compiled_rows:
                compiled_rows[-1]['drafted'] = True

    if compiled_rows:
        result_df = pd.DataFrame(compiled_rows)
        # Added the two new research columns
        cols = ['office', 'position', 'name', 'salary_kanji', 'rank_kanji', 'drafted', 'folder', 'page', 'image']
        result_df = result_df[cols]
        result_df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f"Success! {len(result_df)} records found. Rank/Salary extracted.")
    else:
        print("Error: No entries found.")

if __name__ == "__main__":
    main()
