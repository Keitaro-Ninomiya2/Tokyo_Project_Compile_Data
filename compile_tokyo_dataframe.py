import pandas as pd
import argparse
import os
import re

def load_position_titles(csv_path, column_name='BeforeWar'):
    """
    Loads titles from the crosswalk to help split 'Position_and_Name' lines.
    """
    if not os.path.exists(csv_path):
        return []
    try:
        df = pd.read_csv(csv_path)
        if column_name not in df.columns:
            column_name = df.columns[0]
        # Sort by length descending to match longest titles first (e.g. match 'Senior Clerk' before 'Clerk')
        titles = df[column_name].dropna().unique().tolist()
        titles.sort(key=len, reverse=True)
        return titles
    except Exception as e:
        print(f"Warning: Could not load crosswalk ({e}). Splitting might be less accurate.")
        return []

def split_position_and_name(text, titles):
    """
    Splits a combined string like "Secretary Tanaka" into ("Secretary", "Tanaka").
    Uses the crosswalk titles to find the split point.
    """
    clean_text = str(text).strip()
    
    # 1. Try matching known titles from Crosswalk
    for title in titles:
        if clean_text.startswith(title):
            # Check if there is text remaining after the title
            remainder = clean_text[len(title):].strip(" ,　")
            if remainder:
                return title, remainder
    
    # 2. Fallback: If no title matches, return original text
    return clean_text, "" 

def main():
    parser = argparse.ArgumentParser(description="Compile parsed lines into a structured DataFrame")
    parser.add_argument("--input_csv", required=True, help="The labeled CSV file (e.g., 1937_Full_Labeled.csv)")
    parser.add_argument("--crosswalk", required=True, help="PositionCrosswalk.csv for title separation")
    parser.add_argument("--output", default="Final_Compiled_Directory.csv", help="Output filename")
    
    args = parser.parse_args()

    # 1. Load Data
    print(f"Loading data from {args.input_csv}...")
    df = pd.read_csv(args.input_csv)
    
    # Ensure no NaN in text
    df['text'] = df['text'].fillna("")

    # Load titles for splitting logic
    known_titles = load_position_titles(args.crosswalk)

    # 2. Initialize State Variables (The "Argument")
    # We keep these in memory as we read down the page.
    current_office = None
    current_position = "Employee" # Default if no position is listed
    compiled_rows = []

    # 3. Iterate sequentially (The data MUST be sorted already by the previous script)
    print("Compiling entries...")
    
    for idx, row in df.iterrows():
        label = row['label']
        text = str(row['text']).strip()
        
        # Metadata
        page_num = row.get('page_number', '')
        img_name = row.get('image_name', '')
        
        # --- LOGIC BLOCK ---
        
        if label == 'Office':
            # New Office found: Update state
            current_office = text
            # Reset position when office changes (usually starts with high-ranking, then drops)
            current_position = "Employee" 
            
        elif label == 'Position':
            # New Position found: Update state
            current_position = text
            
        elif label == 'Position_and_Name':
            # Split the line, update position, then record name
            # This handles cases like "Labor Clerk Tanaka" found in your notebook
            pos_part, name_part = split_position_and_name(text, known_titles)
            
            if pos_part:
                current_position = pos_part
            
            # If there is a name part, process it immediately
            if name_part:
                names = [n.strip() for n in name_part.split(',') if n.strip()]
                for n in names:
                    compiled_rows.append({
                        'page': page_num,
                        'image': img_name,
                        'office': current_office,
                        'position': current_position,
                        'name': n,
                        'drafted': False, # Default
                        'original_text': text
                    })

        elif label == 'NameSudachi':
            # Standard Name line. Might contain "Tanaka, Sato, Suzuki"
            names = [n.strip() for n in text.split(',') if n.strip()]
            
            for n in names:
                # Skip tiny noise (names usually > 1 char)
                if len(n) < 2: continue 

                # ASSIGNMENT LOGIC:
                # Assign the current "remembered" Office and Position to this name
                compiled_rows.append({
                    'page': page_num,
                    'image': img_name,
                    'office': current_office,
                    'position': current_position,
                    'name': n,
                    'drafted': False,
                    'original_text': text
                })

        elif label == 'Drafted':
            # "Drafted" usually applies to the person mentioned IMMEDIATELY before.
            # We go back to the last added person and flag them.
            if compiled_rows:
                compiled_rows[-1]['drafted'] = True

    # 4. Export
    if compiled_rows:
        result_df = pd.DataFrame(compiled_rows)
        
        # Select and Reorder columns
        cols = ['office', 'position', 'name', 'drafted', 'page', 'image', 'original_text']
        # Filter to ensure we only ask for columns that actually exist
        cols = [c for c in cols if c in result_df.columns]
        result_df = result_df[cols]
        
        result_df.to_csv(args.output, index=False)
        print(f"\nProcessing Complete!")
        print(f"Total Individuals Found: {len(result_df)}")
        if 'drafted' in result_df.columns:
            print(f"Drafted Individuals: {result_df['drafted'].sum()}")
        print(f"Saved to: {args.output}")
    else:
        print("No compiled rows generated. Check input labels.")

if __name__ == "__main__":
    main()
