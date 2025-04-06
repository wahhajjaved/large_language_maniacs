import json
import pathlib

REDUCED_ENTRIES_PER_PATTERN = 300

CTSSB_DIR: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M")
INPUT_FULL_FILE: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_training.jsonl")
INPUT_FILE: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_training.jsonl")
OUTPUT_FILE: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_training_reduced.jsonl")


def load_dataset_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def save_dataset(data: list[list[dict]], save_location):
    lines = []
    for l in data:
        for entry in l:
            lines.append(json.dumps(entry))

    with open(save_location, "w") as f:
        for line in lines:
            f.write(line + "\n")


def main():
    data: dict[str, list[dict]] = {}
    reduced_data: dict[str, list[dict]] = {}
    data = load_dataset_file(INPUT_FILE)

    for entry in data:
        pattern = entry["sstub_pattern"]
        if len(reduced_data.get(pattern, [])) < REDUCED_ENTRIES_PER_PATTERN:
            reduced_data.setdefault(pattern, []).append(entry)

    save_dataset(reduced_data.values(), OUTPUT_FILE)


if __name__ == "__main__":
    main()
