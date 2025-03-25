import gzip
import itertools
import json
import pathlib

ENTRY_PER_PATTERN_TRAINING = 850
ENTRY_PER_PATTERN_VALIDATION = 150
ENTRY_PER_PATTERN_TESTING = 100

CTSSB_DIR: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M")
TRAINING_SAVE_FILE: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_training.jsonl")
VALIDATION_SAVE_FILE: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_validation.jsonl")
TESTING_SAVE_FILE: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_testing.jsonl")
DEFUNCT_PROJECTS_PATH: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M/defunct_projects.jsonl")

seen_keys = set()


def load_file(path: pathlib.Path) -> list:

    dataset = []
    with gzip.open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def categorize_using_pattern(
    dataset: list[dict[str, str]],
    exclude: list[str],
    training_data: dict[str, list[dict]],
    validation_data: dict[str, list[dict]],
    testing_data: dict[str, list[dict]],
):

    for entry in dataset:
        pattern = entry["sstub_pattern"]
        if not entry["likely_bug"]:
            continue
        if pattern == "SINGLE_STMT":
            continue
        if entry in exclude:
            continue
        if not entry["in_function"]:
            continue

        key = (entry["project"], entry["commit_sha"])
        if key in seen_keys:
            continue
        seen_keys.add(key)

        if len(testing_data.get(pattern, [])) < ENTRY_PER_PATTERN_TESTING:
            testing_data.setdefault(pattern, []).append(entry)
        elif len(validation_data.get(pattern, [])) < ENTRY_PER_PATTERN_VALIDATION:
            validation_data.setdefault(pattern, []).append(entry)
        elif len(training_data.get(pattern, [])) < ENTRY_PER_PATTERN_TRAINING:
            training_data.setdefault(pattern, []).append(entry)


def save_dataset(data: list[list[dict]], save_location):
    lines = []
    for l in data:
        for entry in l:
            lines.append(json.dumps(entry))

    with open(save_location, "w") as f:
        for line in lines:
            f.write(line + "\n")


def data_overlaps(training_data: list[list[dict]], testing_data: list[list[dict]]) -> bool:
    train_keys = {(entry["project"], entry["commit_sha"]) for group in training_data for entry in group}
    test_keys = {(entry["project"], entry["commit_sha"]) for group in testing_data for entry in group}
    overlap = train_keys & test_keys
    print(overlap)
    return len(overlap) > 0


def print_stats(
    training_data: dict[str, list[dict]],
    validation_data: dict[str, list[dict]],
    testing_data: dict[str, list[dict]],
):
    print("\n ** Testing Data **")
    print(f"{len(testing_data.keys())} patterns")
    for k, v in testing_data.items():
        print(f"{k}: {len(v)}")

    print("\n ** Validation Data **")
    print(f"{len(validation_data.keys())} patterns")
    for k, v in validation_data.items():
        print(f"{k}: {len(v)}")

    print(" ** Training Data **")
    print(f"{len(training_data.keys())} patterns")
    for k, v in training_data.items():
        print(f"{k}: {len(v)}")


def main():
    defunct_projects: list[dict[str, str]] = []
    with open(DEFUNCT_PROJECTS_PATH) as f:
        for line in f:
            defunct_projects.append(json.loads(line))

    files = sorted(CTSSB_DIR.glob("*.jsonl.gz"))
    training_data: dict[str, list[dict]] = {}
    validation_data: dict[str, list[dict]] = {}
    testing_data: dict[str, list[dict]] = {}

    for file in files:
        print(f"Loading file {file.name}")
        dataset = load_file(file)
        categorize_using_pattern(dataset, defunct_projects, training_data, validation_data, testing_data)

        training_sizes = [len(v) for v in training_data.values()]
        validation_sizes = [len(v) for v in validation_data.values()]
        testing_sizes = [len(v) for v in testing_data.values()]
        if (
            all(i >= ENTRY_PER_PATTERN_TRAINING for i in training_sizes)
            and all(i >= ENTRY_PER_PATTERN_VALIDATION for i in validation_sizes)
            and all(i >= ENTRY_PER_PATTERN_TESTING for i in testing_sizes)
        ):
            break
    else:
        print("\n****** Not enough entries to in the datasets ******\n")

    print_stats(training_data, validation_data, testing_data)

    save_dataset(training_data.values(), TRAINING_SAVE_FILE)
    save_dataset(validation_data.values(), VALIDATION_SAVE_FILE)
    save_dataset(testing_data.values(), TESTING_SAVE_FILE)


if __name__ == "__main__":
    main()
