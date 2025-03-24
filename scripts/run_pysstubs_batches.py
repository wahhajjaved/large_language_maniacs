import os
import ast
import base64
import requests
import json
import time
import pandas as pd
from typing import Optional

# Settings
BATCH_SIZE = 2000
SLEEP_BETWEEN_REQUESTS = 1.5  # seconds
OUTPUT_DIR = "../downloaded_data/pysstubs/output_batches"
CSV_PATH = "../datasets/pysstubs.csv"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_file_content(repo: str, sha: str, token: Optional[str] = None) -> Optional[str]:
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    url = f"https://api.github.com/repos/{repo}/git/blobs/{sha}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"[ERROR] Failed to fetch: {url} -> {response.status_code}")
        return None
    content_b64 = response.json().get("content", "")
    return base64.b64decode(content_b64).decode("utf-8")

def extract_function_by_line(source_code: str, target_line: int) -> Optional[str]:
    try:
        tree = ast.parse(source_code)
    except Exception:
        return None

    class FunctionLocator(ast.NodeVisitor):
        def __init__(self):
            self.match = None

        def visit_FunctionDef(self, node):
            start_line = node.lineno
            end_line = max(getattr(n, "end_lineno", n.lineno) for n in ast.walk(node) if hasattr(n, "lineno"))
            if start_line <= target_line <= end_line:
                self.match = (start_line, end_line)
            self.generic_visit(node)

    locator = FunctionLocator()
    locator.visit(tree)

    if locator.match:
        lines = source_code.splitlines()
        start, end = locator.match
        return "\n".join(lines[start - 1:end])
    return None

def process_batch(batch_df: pd.DataFrame, batch_index: int, token: Optional[str]):
    output_path = os.path.join(OUTPUT_DIR, f"batch_{batch_index:03}.jsonl")

    # Skip batch if already processed
    if os.path.exists(output_path):
        print(f"[SKIP] Batch {batch_index} already exists.")
        return

    dataset = []
    seen = set()

    for i, row in batch_df.iterrows():
        repo = row["project_name"]
        line_number = int(row["line_changed"])
        sha_before = row["file_before_woc_sha"]
        sha_after = row["file_after_woc_sha"]

        key = (repo, sha_before, sha_after, line_number)
        if key in seen:
            continue
        seen.add(key)

        try:
            code_before = fetch_file_content(repo, sha_before, token)
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            code_after = fetch_file_content(repo, sha_after, token)
            time.sleep(SLEEP_BETWEEN_REQUESTS)

            if not code_before or not code_after:
                continue

            buggy_func = extract_function_by_line(code_before, line_number)
            fixed_func = extract_function_by_line(code_after, line_number)
            if not buggy_func or not fixed_func:
                continue

            sample = {
                "input": f"# Fix the buggy code below:\n{buggy_func}",
                "output": fixed_func,
                "line_before": row["line_before"],
                "line_after": row["line_after"]
            }

            for col in batch_df.columns:
                if col not in sample:
                    sample[col] = row[col]

            dataset.append(sample)

        except Exception as e:
            print(f"[ERROR] Row {i} failed: {e}")
            continue

    # Write the batch
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")

    print(f"[DONE] Batch {batch_index}: {len(dataset)} samples → {output_path}")

def run_all_batches(csv_path: str, token: Optional[str]):
    df = pd.read_csv(csv_path)
    total = len(df)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_index in range(num_batches):
        start = batch_index * BATCH_SIZE
        end = min((batch_index + 1) * BATCH_SIZE, total)
        batch_df = df.iloc[start:end]
        print(f"\n[START] Batch {batch_index} ({start} → {end})")
        process_batch(batch_df, batch_index, token)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=CSV_PATH, help="Path to pysstubs.csv")
    parser.add_argument("--token", help="GitHub token for API access")
    args = parser.parse_args()

    run_all_batches(args.csv, args.token)

