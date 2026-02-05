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
        # Try UTF-8, fallback to Shift-JIS
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
        print(f"Warning: Could not load crosswalk ({e}). Splitting might be less accurate.")
        return []

def split_position_and_name(text, titles):
    """
    Splits a combined string like "Secretary Tanaka" into ("Secretary", "Tanaka").
    """
    clean_text = str(text).strip()
    # Remove noise symbols for cleaner splitting
    clean_text = re.sub(r'[【ヿ〓○●◎]', '', clean_text)
    
    for title in titles:
        if clean_text.startswith(title):
            remainder = clean_text[len(title):].strip(" ,　")
            if remainder:
                return title, remainder
    return clean_text, "" 

def main():
    parser = argparse.ArgumentParser(description="Compile parsed lines into a structured DataFrame")
    parser.add_argument("--input_csv", required=True, help="The labeled CSV file")
    parser.add_argument("--crosswalk", required=True, help="PositionCrosswalk.csv")
    parser.add_argument("--output", default="Final_Compiled_Directory.csv", help="Output filename")
    parser.add_argument("--year_col", default="DuringWar")
    
    args = parser.parse_args()

    print(f"Loading data from {args.input_csv}...")
    df = pd.read_csv(args.input_csv)
    df['text'] = df['text'].fillna("")

    known_titles = load_position_titles(args.crosswalk, args.year_col)

    current_office = "Unknown Office"
    current_position = "Employee" 
    compiled_rows = []

    print("Compiling entries into structured format...")
    
    for idx, row in df.iterrows():
        label = str(row['label'])
        text = str(row['text']).strip()
        
        page_num = row.get('page_number', '')
        img_name = row.get('image_name', '')
        folder_num = row.get('sort_folder_num', '')

        # --- Hierarchy Logic ---
        if label == 'Office':
            current_office = text
            current_position = "Employee" # Reset position inside new office
            
        elif label == 'Position':
            current_position = text
            
        elif label == 'Position_and_Name':
            pos_part, name_part = split_position_and_name(text, known_titles)
            if pos_part:
                current_position = pos_part
            
            if name_part:
                # Rule: One name per row (expand commas)
                names = [n.strip() for n in name_part.split(',') if n.strip()]
                for n in names:
                    if len(n) < 2: continue
                    compiled_rows.append({
                        'folder': folder_num,
                        'page': page_num,
                        'image': img_name,
                        'office': current_office,
                        'position': current_position,
                        'name': n,
                        'drafted': False
                    })

        elif label == 'NameSudachi':
            # Rule: One name per row (expand commas)
            names = [n.strip() for n in text.split(',') if n.strip()]
            for n in names:
                if len(n) < 2: continue 
                compiled_rows.append({
                    'folder': folder_num,
                    'page': page_num,
                    'image': img_name,
                    'office': current_office,
                    'position': current_position,
                    'name': n,
                    'drafted': False
                })

        elif label == 'Drafted':
            # Flag the person immediately preceding this row
            if compiled_rows:
                compiled_rows[-1]['drafted'] = True

    # --- Export ---
    if compiled_rows:
        result_df = pd.DataFrame(compiled_rows)
        
        # Only include columns relevant to the final research data
        cols = ['office', 'position', 'name', 'drafted', 'folder', 'page', 'image']
        result_df = result_df[cols]
        
        result_df.to_csv(args.output, index=False)
        print(f"Success! {len(result_df)} individual records found.")
    else:
        print("Error: No name entries were compiled. Verify input labels.")

if __name__ == "__main__":
    main()
