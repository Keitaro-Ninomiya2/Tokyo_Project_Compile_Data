"""
Generate a comparison report between old and new master CSV files.

Usage:
    python generate_data_report.py --old_csv <old> --new_csv <new> --output report.md
"""
import pandas as pd
import argparse
import sys


def section(title):
    return f"\n## {title}\n"


def main():
    parser = argparse.ArgumentParser(
        description="Compare old vs new Tokyo Personnel Master CSV")
    parser.add_argument("--old_csv", required=True, help="Path to old master CSV")
    parser.add_argument("--new_csv", required=True, help="Path to new master CSV (v2)")
    parser.add_argument("--output", default="data_report.md",
                        help="Output markdown report path")
    args = parser.parse_args()

    print(f"Loading old CSV: {args.old_csv}")
    old = pd.read_csv(args.old_csv)
    print(f"Loading new CSV: {args.new_csv}")
    new = pd.read_csv(args.new_csv)

    lines = []
    lines.append("# Tokyo Personnel Data Report\n")
    lines.append(f"Old file: `{args.old_csv}`  ")
    lines.append(f"New file: `{args.new_csv}`\n")

    # --- 1. Row counts ---
    lines.append(section("1. Row Counts"))
    lines.append(f"| Metric | Old | New |")
    lines.append(f"|--------|-----|-----|")
    lines.append(f"| Total rows | {len(old):,} | {len(new):,} |")

    if 'year' in old.columns and 'year' in new.columns:
        old_years = sorted(old['year'].dropna().unique())
        new_years = sorted(new['year'].dropna().unique())
        lines.append(f"| Unique years | {len(old_years)} | {len(new_years)} |")
        lines.append("")
        lines.append("**Per-year row counts:**\n")
        lines.append("| Year | Old | New | Diff |")
        lines.append("|------|-----|-----|------|")
        all_years = sorted(set(list(old_years) + list(new_years)))
        for yr in all_years:
            o = len(old[old['year'] == yr]) if yr in old_years else 0
            n = len(new[new['year'] == yr]) if yr in new_years else 0
            diff = n - o
            sign = "+" if diff > 0 else ""
            lines.append(f"| {yr} | {o:,} | {n:,} | {sign}{diff:,} |")

    # --- 2. Non-name filtering ---
    lines.append(section("2. Non-Name Filtering"))
    if 'is_name' in new.columns:
        is_name_counts = new['is_name'].value_counts()
        n_true = is_name_counts.get(True, is_name_counts.get('True', 0))
        n_false = is_name_counts.get(False, is_name_counts.get('False', 0))
        lines.append(f"| is_name | Count | % |")
        lines.append(f"|---------|-------|---|")
        total = len(new)
        lines.append(f"| True | {n_true:,} | {100*n_true/total:.1f}% |")
        lines.append(f"| False | {n_false:,} | {100*n_false/total:.1f}% |")
        lines.append("")

        # Sample non-name rows
        non_name = new[new['is_name'].astype(str).str.lower() == 'false']
        if len(non_name) > 0:
            lines.append("**Sample non-name rows (first 10):**\n")
            sample = non_name.head(10)
            sample_cols = ['name', 'office', 'position', 'year']
            sample_cols = [c for c in sample_cols if c in sample.columns]
            lines.append(sample[sample_cols].to_markdown(index=False))
    else:
        lines.append("*`is_name` column not found in new CSV.*")

    # --- 3. Gender stats ---
    lines.append(section("3. Gender Classification"))
    for col in ['gender_legacy', 'gender_modern']:
        if col in new.columns:
            counts = new[col].value_counts()
            lines.append(f"\n**{col}:**\n")
            lines.append("| Gender | Count | % |")
            lines.append("|--------|-------|---|")
            for val in ['female', 'male', '']:
                c = counts.get(val, 0)
                pct = 100 * c / len(new) if len(new) > 0 else 0
                label = val if val else "(empty/non-name)"
                lines.append(f"| {label} | {c:,} | {pct:.1f}% |")

    # Disagreement rate
    if 'gender_legacy' in new.columns and 'gender_modern' in new.columns:
        both_classified = new[
            (new['gender_legacy'].isin(['male', 'female'])) &
            (new['gender_modern'].isin(['male', 'female']))
        ]
        if len(both_classified) > 0:
            disagree = (both_classified['gender_legacy'] !=
                        both_classified['gender_modern']).sum()
            lines.append(f"\nDisagreement rate (legacy vs modern): "
                         f"{disagree:,} / {len(both_classified):,} "
                         f"({100*disagree/len(both_classified):.2f}%)")

    # Per-year female counts
    if 'gender_modern' in new.columns and 'year' in new.columns:
        lines.append("\n**Female counts by year (modern method):**\n")
        lines.append("| Year | Female | Male | % Female |")
        lines.append("|------|--------|------|----------|")
        for yr in sorted(new['year'].dropna().unique()):
            yr_df = new[new['year'] == yr]
            f = (yr_df['gender_modern'] == 'female').sum()
            m = (yr_df['gender_modern'] == 'male').sum()
            pct = 100 * f / (f + m) if (f + m) > 0 else 0
            lines.append(f"| {yr} | {f:,} | {m:,} | {pct:.1f}% |")

    # --- 4. Staff ID stats ---
    lines.append(section("4. Staff ID Statistics"))
    if 'staff_id' in new.columns:
        valid_ids = new['staff_id'].dropna()
        n_unique = valid_ids.nunique()
        n_with_id = len(valid_ids)
        lines.append(f"- Rows with staff_id: {n_with_id:,} / {len(new):,}")
        lines.append(f"- Unique staff IDs: {n_unique:,}")

        # Panel depth
        if n_unique > 0:
            id_year_counts = new.dropna(subset=['staff_id']).groupby(
                'staff_id')['year'].nunique()
            lines.append(f"- Mean years per person: {id_year_counts.mean():.2f}")
            lines.append(f"- Max years per person: {id_year_counts.max()}")
            lines.append("")
            lines.append("**Panel depth distribution:**\n")
            lines.append("| Years Observed | Staff Count |")
            lines.append("|----------------|-------------|")
            for n_yrs in sorted(id_year_counts.unique()):
                c = (id_year_counts == n_yrs).sum()
                lines.append(f"| {int(n_yrs)} | {c:,} |")
    else:
        lines.append("*`staff_id` column not found in new CSV.*")

    # --- 5. Office coverage ---
    lines.append(section("5. Office Coverage"))
    if 'office' in new.columns:
        n_with_office = (new['office'] != 'Unknown Office').sum()
        lines.append(f"- Rows with assigned office: {n_with_office:,} / "
                     f"{len(new):,} ({100*n_with_office/len(new):.1f}%)")
        lines.append(f"- Unique offices: "
                     f"{new['office'].nunique()}")
        if 'office_id' in new.columns:
            lines.append(f"- Rows with office_id: "
                         f"{new['office_id'].notna().sum():,}")

        if 'year' in new.columns:
            lines.append("\n**Unique offices per year:**\n")
            lines.append("| Year | Unique Offices |")
            lines.append("|------|----------------|")
            for yr in sorted(new['year'].dropna().unique()):
                n = new[new['year'] == yr]['office'].nunique()
                lines.append(f"| {yr} | {n} |")

    # --- 6. Sample data ---
    lines.append(section("6. Sample Data (First 10 Clean Rows)"))
    if 'is_name' in new.columns:
        clean = new[new['is_name'].astype(str).str.lower() == 'true'].head(10)
    else:
        clean = new.head(10)

    display_cols = ['year', 'gov_level', 'office', 'position', 'name',
                    'is_name', 'gender_legacy', 'gender_modern',
                    'staff_id', 'office_id']
    display_cols = [c for c in display_cols if c in clean.columns]
    if len(clean) > 0:
        lines.append(clean[display_cols].to_markdown(index=False))
    else:
        lines.append("*No clean rows found.*")

    # --- Write report ---
    report = "\n".join(lines)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nReport saved to: {args.output}")
    print(f"Report length: {len(lines)} lines")


if __name__ == "__main__":
    main()
