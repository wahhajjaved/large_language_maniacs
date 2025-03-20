import gzip
import json
import pathlib

ENTRY_PER_PATTERN = 5

CTSSB_DIR: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M")
SAVE_FILE: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset.jsonl")
DEFUNCT_PROJECTS_PATH = pathlib.Path = pathlib.Path("datasets/ctssb_data_1M/defunct_projects.txt")


def load_file(path: pathlib.Path) -> list:

    dataset = []
    with gzip.open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def categorize_using_pattern(dataset: list, exclude: list[str], data: dict[str, list[dict]]) -> dict[str, list[dict]]:

    for entry in dataset:
        pattern = entry["sstub_pattern"]
        if not entry["likely_bug"]:
            continue
        if pattern == "SINGLE_STMT":
            continue
        if entry["project"] in exclude:
            continue

        try:
            if len(data[pattern]) < ENTRY_PER_PATTERN:
                data[pattern].append(entry)
        except KeyError:
            data[pattern] = []
            data[pattern].append(entry)

    return data


def save_dataset(data: list[list[dict]]):
    lines = []
    for l in data:
        for entry in l:
            lines.append(json.dumps(entry))

    with open(SAVE_FILE, "w") as f:
        for line in lines:
            f.write(line + "\n")


def main():
    with open(DEFUNCT_PROJECTS_PATH) as f:
        defunct_projects = f.readlines()
    files = sorted(CTSSB_DIR.glob("*.jsonl.gz"))
    data: dict[str, list[dict]] = {}

    for file in files:
        print(f"Loading file {file.name}")
        dataset = load_file(file)
        data = categorize_using_pattern(dataset, defunct_projects, data)
        sizes = [len(v) for v in data.values()]
        if all(i >= ENTRY_PER_PATTERN for i in sizes):
            for k, v in data.items():
                print(f"{k}: {len(v)}")
            break

    save_dataset(data.values())


if __name__ == "__main__":
    main()
