# Parse and compare base vs fine-tuned model results
import re
from collections import defaultdict

from tabulate import tabulate


def parse_results(file_path):
    with open(file_path, "r") as f:
        content = f.read()

    # Split sections
    base_section = re.search(r"Base Model Results(.*?)Finetuned Model Results", content, re.S).group(1)
    fine_section = re.search(r"Finetuned Model Results(.*)", content, re.S).group(1)

    def extract_metrics(section):
        data = defaultdict(dict)
        current_key = None
        for line in section.splitlines():
            line = line.strip()
            if line.startswith("#####"):
                current_key = line.strip("# ").strip()
            elif "=" in line and current_key:
                metric, val = line.split("=")
                data[current_key][metric.strip()] = float(val.strip())
        return data

    return extract_metrics(base_section), extract_metrics(fine_section)


def get_grouped_comparison(base_data, fine_data):
    result = {}
    for category in sorted(base_data.keys()):
        if category in fine_data:
            headers = ["Metric", "Base", "Fine-Tuned", "Diff"]
            rows = []
            for metric in base_data[category]:
                base_val = base_data[category][metric]
                fine_val = fine_data[category].get(metric)
                if fine_val is not None:
                    diff = fine_val - base_val
                    rows.append([metric, round(base_val, 4), round(fine_val, 4), round(diff, 4)])
            result[category] = tabulate(rows, headers=headers, tablefmt="grid")
    return result


def sort_categories_by_metric(data, base_data, fine_data, model_type: str, metric: str):
    if model_type == "base":
        sorted_items = sorted(data.items(), key=lambda item: base_data.get(item[0], {}).get(metric, float("inf")))
    elif model_type == "finetuned":
        sorted_items = sorted(data.items(), key=lambda item: fine_data.get(item[0], {}).get(metric, float("inf")))
    else:
        raise ValueError("model_type must be 'base' or 'finetuned'")

    return sorted_items


def compute_average_metrics(data):
    selected_metrics = [
        "average_levenshtein_ratio",
        "average_em_score",
        # "average_bleu_score",
        # "average_ast_match",
        "average_codebleu_score",
    ]
    result = {}
    for category, metrics in data.items():
        values = [metrics.get(metric, 0.0) for metric in selected_metrics if metric in metrics]
        if values:
            result[category] = round(sum(values) / len(values), 4)
    return result


# Example usage
base, fine = parse_results("analysis_results.txt")  # replace with actual file path

grouped_tables = get_grouped_comparison(base, fine)
sorted_tables = sort_categories_by_metric(
    grouped_tables,
    base,
    fine,
    model_type="finetuned",
    metric="average_em_score",
)
for category, table in sorted_tables:
    print(f"\nCategory: {category}")
    print(table)

# Print average metric scores
base_avg = compute_average_metrics(base)
fine_avg = compute_average_metrics(fine)

avg_table = [
    [category, base_avg.get(category, 0.0), fine_avg.get(category, 0.0)]
    for category in sorted(fine_avg.keys(), key=lambda k: fine_avg[k])
]

# print("\nAverage scores:")
# print(tabulate(avg_table, headers=["Category", "Base Avg", "Fine-Tuned Avg"], tablefmt="grid"))
