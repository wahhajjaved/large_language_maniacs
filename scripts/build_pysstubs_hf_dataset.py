import os
import ast
import base64
import requests
import json
import pandas as pd
from typing import Optional

def fetch_file_content(repo: str, sha: str, token: Optional[str] = None) -> Optional[str]:
    """Fetch a raw file from GitHub using blob SHA."""
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
    """Extract the full function that contains the target line using AST."""
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

def build_hf_dataset_from_csv(csv_path: str, output_path: str, token: Optional[str] = None, limit: Optional[int] = None):
    df = pd.read_csv(csv_path)
    dataset = []
    seen_pairs = set()

    for i, row in df.iterrows():
        if limit and len(dataset) >= limit:
            break

        repo = row["project_name"]
        line_number = int(row["line_changed"])
        sha_before = row["file_before_woc_sha"]
        sha_after = row["file_after_woc_sha"]

        pair_key = (repo, sha_before, sha_after, line_number)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        try:
            code_before = fetch_file_content(repo, sha_before, token)
            code_after = fetch_file_content(repo, sha_after, token)
            if not code_before or not code_after:
                continue

            buggy_func = extract_function_by_line(code_before, line_number)
            fixed_func = extract_function_by_line(code_after, line_number)
            if not buggy_func or not fixed_func:
                continue

            dataset.append({
                "input": f"# Fix the buggy code below:\n{buggy_func}",
                "output": fixed_func
            })
        except Exception as e:
            print(f"[ERROR] Row {i} failed: {e}")
            continue

    # Write output to JSONL
    with open(output_path, "w", encoding="utf-8") as out_file:
        for item in dataset:
            out_file.write(json.dumps(item) + "\n")

    print(f"[DONE] Wrote {len(dataset)} samples to {output_path}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build HuggingFace JSONL from PySStuBs CSV")
    parser.add_argument("--csv", required=True, help="Path to pysstubs.csv")
    parser.add_argument("--out", default="pysstubs_bugfixes.jsonl", help="Output JSONL file path")
    parser.add_argument("--token", help="GitHub token (optional)")
    parser.add_argument("--limit", type=int, help="Max number of samples to extract")
    args = parser.parse_args()

    build_hf_dataset_from_csv(args.csv, args.out, args.token, args.limit)

