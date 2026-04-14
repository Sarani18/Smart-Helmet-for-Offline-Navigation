"""
IDD Label Mask Generator
------------------------
Generates level3Id PNG label masks from IDD JSON polygon annotations.
Fixes the multiprocessing global-args bug in AutoNUE's createLabels.py.

Usage:
    python3 generate_labels.py --datadir data/idd/idd20kII
    python3 generate_labels.py --datadir data/idd/idd20kII --workers 8
"""

import os
import sys
import glob
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

from tqdm import tqdm

# Add AutoNUE helpers to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "autonue_tools" / "helpers"))
sys.path.insert(0, str(SCRIPT_DIR / "autonue_tools" / "preperation"))


def process_one(json_path: str) -> str:
    """Convert a single JSON annotation to a level3Id PNG label mask."""
    import sys
    from pathlib import Path

    # Re-add path in worker process
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir / "autonue_tools" / "helpers"))
    sys.path.insert(0, str(script_dir / "autonue_tools" / "preperation"))

    from json2labelImg import json2labelImg

    dst = json_path.replace("_polygons.json", "_labellevel3Ids.png")
    if Path(dst).exists():
        return f"SKIP {Path(json_path).name}"

    try:
        json2labelImg(json_path, dst, "level3Id")
        return f"OK   {Path(json_path).name}"
    except Exception as e:
        return f"FAIL {Path(json_path).name}: {e}"


def main():
    parser = argparse.ArgumentParser(description="Generate IDD level3Id label masks")
    parser.add_argument("--datadir", required=True, help="Path to IDD dataset root (e.g. data/idd/idd20kII)")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    args = parser.parse_args()

    # Find all JSON annotation files
    search_pattern = os.path.join(args.datadir, "gtFine", "*", "*", "*_polygons.json")
    json_files = sorted(glob.glob(search_pattern))

    if not json_files:
        print(f"❌ No JSON annotation files found in: {search_pattern}")
        print("   Make sure the dataset is extracted correctly.")
        sys.exit(1)

    # Count already generated
    already_done = sum(
        1 for f in json_files
        if Path(f.replace("_polygons.json", "_labellevel3Ids.png")).exists()
    )

    print(f"\n📊 Found {len(json_files)} annotation files")
    print(f"   Already generated: {already_done}")
    print(f"   To process:        {len(json_files) - already_done}")
    print(f"   Workers:           {args.workers}\n")

    if already_done == len(json_files):
        print("✅ All label masks already generated!")
        return

    ok = skip = fail = 0
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_one, f): f for f in json_files}
        for future in tqdm(as_completed(futures), total=len(json_files), desc="Generating labels"):
            result = future.result()
            if result.startswith("OK"):
                ok += 1
            elif result.startswith("SKIP"):
                skip += 1
            else:
                fail += 1
                tqdm.write(result)

    print(f"\n✅ Done! Generated: {ok} | Skipped: {skip} | Failed: {fail}")
    print(f"   Label masks saved alongside JSON files in gtFine/")


if __name__ == "__main__":
    main()
