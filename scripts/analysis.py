import ast
import json
import pathlib

import evaluate
import Levenshtein
from codebleu import calc_codebleu

CTSSB_TESTING_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/testing")
TESTING_DATASET_METADATA_PATH = pathlib.Path("datasets/ctssb_prepared_dataset_testing.jsonl")
TESTING_DATASET_PATH = pathlib.Path("datasets/ctssb_testing.jsonl")
BASE_MODEL_OUTPUT_PATH = pathlib.Path("datasets/ctssb_testing_base_output.jsonl")
FINETUNED_MODEL_OUTPUT_PATH = pathlib.Path("datasets/ctssb_testing_finetuned_output.jsonl")

SEARCH_BY_CONTENT = True


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


def find_sstub_type(entries, project, commit_sha):
    for entry in entries:
        if entry["project"] == project and entry["commit_sha"] == commit_sha:
            return entry["sstub_pattern"]
    return None


def clean_generate_output(generated_output: str) -> str:
    return generated_output.split("### Response:")[1]


def build_data(testing_dataset_metadata, model_outputs):
    data: list[dict[str, str]] = []
    if SEARCH_BY_CONTENT:
        for model_output in model_outputs:
            project_name, commit_hash = search_for_commit_hash(model_output["input"])
            entry = {
                "project_name": project_name,
                "commit_hash": commit_hash,
                "input": model_output["input"],
                "output": model_output["output"],
                "generated_output": clean_generate_output(model_output["generated_output"]),
                "sstub_pattern": find_sstub_type(testing_dataset_metadata, project_name, commit_hash),
            }
            data.append(entry)

    return data


def is_ast_match(pred: str, ref: str) -> bool:
    try:
        return ast.dump(ast.parse(pred)) == ast.dump(ast.parse(ref))
    except:
        return False


def compute_metrics(entry: dict):
    exact_match = evaluate.load("exact_match")
    bleu = evaluate.load("bleu")

    predictions = [entry["generated_output"]]
    references = [entry["output"]]

    em_score = exact_match.compute(predictions=predictions, references=references)["exact_match"]
    bleu_score = bleu.compute(predictions=predictions, references=references)["bleu"]
    codebleu_result = calc_codebleu(references, predictions, lang="python")["codebleu"]

    entry["em_score"] = round(float(em_score), 2)
    entry["bleu_score"] = round(bleu_score, 2)
    entry["codebleu_result"] = round(codebleu_result, 2)
    entry["levenshtein_distance"] = Levenshtein.distance(predictions[0], references[0])
    entry["levenshtein_ratio"] = Levenshtein.ratio(predictions[0], references[0])


def get_overall_results(data: list[dict]):
    total_em_score = 0
    total_bleu_score = 0
    total_codebleu_result = 0
    total_levenshtein_distance = 0
    total_levenshtein_ratio = 0

    for d in data:
        total_em_score += d["em_score"]
        total_bleu_score += d["bleu_score"]
        total_codebleu_result += d["codebleu_result"]
        total_levenshtein_distance += d["levenshtein_distance"]
        total_levenshtein_ratio += d["levenshtein_ratio"]

    average_em_score = total_bleu_score / len(data)
    average_bleu_score = total_bleu_score / len(data)
    average_codebleu_result = total_codebleu_result / len(data)
    average_levenshtein_distance = total_levenshtein_distance / len(data)
    average_levenshtein_ratio = total_levenshtein_ratio / len(data)

    print(f"{average_em_score=:.2f}")
    print(f"{average_bleu_score=:.2f}")
    print(f"{average_codebleu_result=:.2f}")
    print(f"{average_levenshtein_distance=:.2f}")
    print(f"{average_levenshtein_ratio=:.2f}")


def analyze_base_model(testing_dataset_metadata):
    base_model_outputs = load_file(BASE_MODEL_OUTPUT_PATH)
    data = build_data(testing_dataset_metadata, base_model_outputs[:10])
    for d in data:
        compute_metrics(d)

    print("\nResults for base model")
    get_overall_results(data)


def analyze_finetuned_model(testing_dataset_metadata):
    finetuned_model_outputs = load_file(FINETUNED_MODEL_OUTPUT_PATH)
    data = build_data(testing_dataset_metadata, finetuned_model_outputs[:10])
    for d in data:
        compute_metrics(d)

    print("\nResults for finetuned model")
    get_overall_results(data)


def main():
    testing_dataset_metadata = load_file(TESTING_DATASET_METADATA_PATH)
    analyze_base_model(testing_dataset_metadata)
    analyze_finetuned_model(testing_dataset_metadata)


if __name__ == "__main__":
    main()
