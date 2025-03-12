import gzip
import json
import pathlib

CTSSB_DIR: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M")


def load_file(path: pathlib.Path) -> list:

    dataset = []
    with gzip.open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def filter_dataset(dataset: list):
    filtered_dataset = []
    for entry in dataset:
        if entry["likely_bug"] and entry["sstub_pattern"] != "SINGLE_STMT":
            filtered_dataset.append(entry)

    print(f"dataset size = {len(dataset):_}, filtered dataset size = {len(filtered_dataset):_}")


def main():
    file_path = pathlib.Path(CTSSB_DIR, "file-0.jsonl.gz")
    dataset = load_file(file_path)
    filtered_dataset = filter_dataset(dataset)


if __name__ == "__main__":
    main()
