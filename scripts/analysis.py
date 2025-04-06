import ast
import concurrent.futures
import copy
import json
import pathlib
import re

import evaluate
import Levenshtein
from codebleu import calc_codebleu

CTSSB_TESTING_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/testing")
TESTING_DATASET_METADATA_PATH = pathlib.Path("datasets/ctssb_prepared_dataset_testing.jsonl")
TESTING_DATASET_PATH = pathlib.Path("datasets/ctssb_testing.jsonl")
BASE_MODEL_OUTPUT_PATH = pathlib.Path("datasets/ctssb_testing_base_output_incremental_step_2.jsonl")
FINETUNED_MODEL_OUTPUT_PATH = pathlib.Path("datasets/ctssb_testing_finetuned_output_incremental_step_2.jsonl")
MANUAL_VERIFICATION_DIR = pathlib.Path("scripts/manual_verification")

SEARCH_BY_CONTENT = True
MANUAL_VERIFICATION_MODE = False
MANUAL_VERIFICATION_ITEM = 10
PARALLEL = True

exact_match = evaluate.load("exact_match")
bleu = evaluate.load("bleu")


def load_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def search_for_commit_hash(file_content: str):
    for file in CTSSB_TESTING_SAVE_DIR.iterdir():
        if file.is_file():
            with file.open("r", errors="ignore") as f:
                if file_content in f.read():
                    return file.name.split("_")[0:2]
    return ("", "")


def find_sstub_type(entries, project, commit_sha) -> str:
    for entry in entries:
        if entry["project"] == project and entry["commit_sha"] == commit_sha:
            return entry["sstub_pattern"]
    return ""


def clean_generate_output(generated_output: str) -> str:
    cleaned_output = generated_output.split("### Response:")[1].strip()
    base_model_pattern = r"```python\n(.*?)```"
    cleaned_output2 = re.findall(base_model_pattern, cleaned_output, re.DOTALL)

    if cleaned_output2:
        return max(cleaned_output2, key=len).strip()

    return cleaned_output


def normalize_entry(entry: dict[str, str]):
    """Removes superficial differences in strings to reduce false negatives in exact match"""

    # replace_consecutive_newlines
    entry["input"] = re.sub(r"\n+", "\n", entry["input"]).strip()
    entry["output"] = re.sub(r"\n+", "\n", entry["output"]).strip()
    entry["generated_output"] = re.sub(r"\n+", "\n", entry["generated_output"]).strip()


def build_entry(testing_dataset_metadata, model_output) -> dict[str, str]:
    project_name, commit_hash = search_for_commit_hash(model_output["input"])
    entry = {
        "project_name": project_name,
        "commit_hash": commit_hash,
        "input": model_output["input"],
        "output": model_output["output"],
        "generated_output": clean_generate_output(model_output["generated_output"]),
        "sstub_pattern": find_sstub_type(testing_dataset_metadata, project_name, commit_hash),
    }
    normalize_entry(entry)
    return entry


def build_data(
    testing_dataset_metadata,
    model_outputs,
):
    data: list[dict[str, str]] = []
    model_outputs = [model_output for model_output in model_outputs if model_output["generated_output"]]

    for i, model_output in enumerate(model_outputs):
        entry = build_entry(testing_dataset_metadata, model_output)
        data.append(entry)
        print(f"\rProcessed {i}/{len(model_outputs)} entries", end="", flush=True)

    print()
    return data


def compute_metrics(entry: dict):

    predictions = [entry["generated_output"]]
    references = [entry["output"]]

    em_score = exact_match.compute(predictions=predictions, references=references)["exact_match"]
    bleu_score = bleu.compute(predictions=predictions, references=references)["bleu"]
    codebleu_result = calc_codebleu(references, predictions, lang="python")

    entry["levenshtein_distance"] = Levenshtein.distance(predictions[0], references[0])
    entry["levenshtein_ratio"] = Levenshtein.ratio(predictions[0], references[0])

    entry["levenshtein_distance"] = round(entry["levenshtein_distance"], 2)
    entry["levenshtein_ratio"] = round(entry["levenshtein_ratio"], 2)
    entry["em_score"] = round(float(em_score), 2)
    entry["bleu_score"] = round(bleu_score, 2)

    try:
        entry["ast_match"] = int(ast.dump(ast.parse(predictions[0])) == ast.dump(ast.parse(references[0])))
    except SyntaxError:
        entry["ast_match"] = 0

    entry["codebleu_score"] = round(codebleu_result["codebleu"], 2)
    entry["codebleu_ngram_match_score"] = round(codebleu_result["ngram_match_score"], 2)
    entry["codebleu_weighted_ngram_match_score"] = round(codebleu_result["weighted_ngram_match_score"], 2)
    entry["codebleu_syntax_match_score"] = round(codebleu_result["syntax_match_score"], 2)
    entry["codebleu_dataflow_match_score"] = round(codebleu_result["dataflow_match_score"], 2)

    return entry


def get_overall_results(data: list[dict]) -> dict[str, float]:
    total_levenshtein_distance = 0
    total_levenshtein_ratio = 0
    total_em_score = 0
    total_bleu_score = 0
    total_ast_match = 0
    total_codebleu_score = 0
    total_codebleu_ngram_match_score = 0
    total_codebleu_weighted_ngram_match_score = 0
    total_codebleu_syntax_match_score = 0
    total_codebleu_dataflow_match_score = 0

    for d in data:
        total_levenshtein_distance += d["levenshtein_distance"]
        total_levenshtein_ratio += d["levenshtein_ratio"]
        total_em_score += d["em_score"]
        total_bleu_score += d["bleu_score"]
        total_ast_match += d["ast_match"]
        total_codebleu_score += d["codebleu_score"]
        total_codebleu_ngram_match_score += d["codebleu_ngram_match_score"]
        total_codebleu_weighted_ngram_match_score += d["codebleu_weighted_ngram_match_score"]
        total_codebleu_syntax_match_score += d["codebleu_syntax_match_score"]
        total_codebleu_dataflow_match_score += d["codebleu_dataflow_match_score"]

    average_levenshtein_ratio = total_levenshtein_ratio / len(data)
    average_levenshtein_distance = total_levenshtein_distance / len(data)
    average_em_score = total_em_score / len(data)
    average_bleu_score = total_bleu_score / len(data)
    average_ast_match = total_ast_match / len(data)
    average_codebleu_score = total_codebleu_score / len(data)
    average_codebleu_ngram_match_score = total_codebleu_ngram_match_score / len(data)
    average_codebleu_weighted_ngram_match_score = total_codebleu_weighted_ngram_match_score / len(data)
    average_codebleu_syntax_match_score = total_codebleu_syntax_match_score / len(data)
    average_codebleu_dataflow_match_score = total_codebleu_dataflow_match_score / len(data)

    return {
        "average_levenshtein_distance": average_levenshtein_distance,
        "average_levenshtein_ratio": average_levenshtein_ratio,
        "average_em_score": average_em_score,
        "average_bleu_score": average_bleu_score,
        "average_ast_match": average_ast_match,
        "average_codebleu_score": average_codebleu_score,
        "average_codebleu_ngram_match_score": average_codebleu_ngram_match_score,
        "average_codebleu_weighted_ngram_match_score": average_codebleu_weighted_ngram_match_score,
        "average_codebleu_syntax_match_score": average_codebleu_syntax_match_score,
        "average_codebleu_dataflow_match_score": average_codebleu_dataflow_match_score,
    }


def print_results(results: dict[str, float]):
    print(f"average_levenshtein_distance = {results['average_levenshtein_distance']:.2f}")
    print(f"average_levenshtein_ratio = {results['average_levenshtein_ratio']:.2f}")
    print(f"average_em_score = {results['average_em_score']:.2f}")
    print(f"average_bleu_score = {results['average_bleu_score']:.2f}")
    print(f"average_ast_match = {results['average_ast_match']:.2f}")
    print(f"average_codebleu_score = {results['average_codebleu_score']:.2f}")
    print(f"average_codebleu_ngram_match_score = {results['average_codebleu_ngram_match_score']:.2f}")
    print(f"average_codebleu_weighted_ngram_match_score = {results['average_codebleu_weighted_ngram_match_score']:.2f}")
    print(f"average_codebleu_syntax_match_score = {results['average_codebleu_syntax_match_score']:.2f}")
    print(f"average_codebleu_dataflow_match_score = {results['average_codebleu_dataflow_match_score']:.2f}")


def analyze_base_model(testing_dataset_metadata):
    base_model_outputs = load_file(BASE_MODEL_OUTPUT_PATH)
    data = build_data(testing_dataset_metadata, base_model_outputs)
    results = []

    if PARALLEL:
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = [executor.submit(compute_metrics, d) for d in data]
            for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                results.append(future.result())
                print(f"\rcompute_metrics {i}/{len(data)} entries", end="", flush=True)
    else:
        for i, d in enumerate(data):
            results.append(compute_metrics(d))
            print(f"\rBase model compute_metrics {i}/{len(data)} entries", end="", flush=True)

    print()
    return get_overall_results(results)


def analyze_finetuned_model(testing_dataset_metadata):
    finetuned_model_outputs = load_file(FINETUNED_MODEL_OUTPUT_PATH)
    data = build_data(testing_dataset_metadata, finetuned_model_outputs)
    results = []
    if PARALLEL:
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = [executor.submit(compute_metrics, d) for d in data]
            for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                results.append(future.result())
                print(f"\rcompute_metrics {i}/{len(data)} entries", end="", flush=True)
    else:
        for i, d in enumerate(data):
            results.append(compute_metrics(d))
            print(f"\rFinetuned model compute_metrics {i}/{len(data)} entries", end="", flush=True)

    print()
    return get_overall_results(results)


def printsave_manual_verification_results(entry, f):
    f.write(f"levenshtein_distance = {entry['levenshtein_distance']:.2f}\n")
    f.write(f"levenshtein_ratio = {entry['levenshtein_ratio']:.2f}\n")
    f.write(f"em_score = {entry['em_score']:.2f}\n")
    f.write(f"bleu_score = {entry['bleu_score']:.2f}\n")
    f.write(f"ast_match = {entry['ast_match']:.2f}\n")
    f.write(f"codebleu_score = {entry['codebleu_score']:.2f}\n")
    f.write(f"codebleu_ngram_match_score = {entry['codebleu_ngram_match_score']:.2f}\n")
    f.write(f"codebleu_weighted_ngram_match_score = {entry['codebleu_weighted_ngram_match_score']:.2f}\n")
    f.write(f"codebleu_syntax_match_score = {entry['codebleu_syntax_match_score']:.2f}\n")
    f.write(f"codebleu_dataflow_match_score = {entry['codebleu_dataflow_match_score']:.2f}\n")


def manual_verification(testing_dataset_metadata):
    base_model_outputs = load_file(BASE_MODEL_OUTPUT_PATH)
    finetuned_model_outputs = load_file(FINETUNED_MODEL_OUTPUT_PATH)
    base_model_item = base_model_outputs[MANUAL_VERIFICATION_ITEM]
    finetuned_model_item = finetuned_model_outputs[MANUAL_VERIFICATION_ITEM]

    base_entry = build_entry(testing_dataset_metadata, base_model_item)
    finetuned_entry = build_entry(testing_dataset_metadata, finetuned_model_item)
    if base_entry["input"] != finetuned_entry["input"]:
        print(base_entry["input"])
        print(finetuned_entry["input"])
        print(f"Base entry input does not match fine tuned entry input for entry {MANUAL_VERIFICATION_ITEM}")
        return

    base_entry_results = compute_metrics(base_entry)
    finetuned_entry_results = compute_metrics(finetuned_entry)

    filename = pathlib.Path(MANUAL_VERIFICATION_DIR, f"{base_entry['project_name']}-{base_entry['commit_hash']}.txt")
    with open(filename, "w") as f:
        f.write(base_entry["sstub_pattern"] + "\n\n")
        f.write("Base entry results\n")
        printsave_manual_verification_results(base_entry_results, f)

        f.write("\nFine tuned entry results\n")
        printsave_manual_verification_results(finetuned_entry_results, f)
        f.write("\n\n")

        f.write("#" * 40 + "\n" + "\tBase Input\n" + "#" * 40 + "\n")
        f.write(base_entry["input"] + "\n\n\n")

        f.write("#" * 40 + "\n" + "\tBase Output\n" + "#" * 40 + "\n")
        f.write(base_entry["output"] + "\n\n\n")

        f.write("#" * 40 + "\n" + "\tBase Generated Output\n" + "#" * 40 + "\n")
        f.write(base_entry["generated_output"] + "\n\n\n")

        f.write("#" * 40 + "\n" + "\tFinetuned Generated Output\n" + "#" * 40 + "\n")
        f.write(finetuned_entry["generated_output"] + "\n\n\n")

    print(f"Manual verification output saved to {filename.name}")


def main():
    testing_dataset_metadata = load_file(TESTING_DATASET_METADATA_PATH)
    if MANUAL_VERIFICATION_MODE:
        manual_verification(testing_dataset_metadata)
    else:
        base_results = analyze_base_model(testing_dataset_metadata)
        finetunes_results = analyze_finetuned_model(testing_dataset_metadata)
        print("\nResults for base model")
        print_results(base_results)
        print("\nResults for finetuned model")
        print_results(finetunes_results)


if __name__ == "__main__":
    main()
