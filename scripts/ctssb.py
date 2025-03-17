import gzip
import json
import pathlib

ENTRY_PER_PATTERN = 1000

CTSSB_DIR: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M")


def load_file(path: pathlib.Path) -> list:

    dataset = []
    with gzip.open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def categorize_using_pattern(dataset: list, data: dict[str, list[dict]]) -> dict[str, list[dict]]:

    for entry in dataset:
        pattern = entry["sstub_pattern"]
        if not entry["likely_bug"]:
            continue
        if pattern == "SINGLE_STMT":
            continue

        try:
            if len(data[pattern]) < ENTRY_PER_PATTERN:
                data[pattern].append(entry)
        except KeyError:
            data[pattern] = []
            data[pattern].append(entry)

    return data


def main():
    files = sorted(CTSSB_DIR.glob("*.jsonl.gz"))
    data: dict[str, list[dict]] = {}
    for file in files:
        print(f"Loading file {file.name}")
        dataset = load_file(file)
        data = categorize_using_pattern(dataset, data)
        sizes = [len(v) for v in data.values()]
        if all(i >= ENTRY_PER_PATTERN for i in sizes):
            for k, v in data.items():
                print(f"{k}: {len(v)}")
            break


if __name__ == "__main__":
    main()
