import csv
import pathlib

# csv headings
# project_name, commit, file_before_woc_sha, file_after_woc_sha, line_changed, line_before,
# line_after, is_java_sstub, sstub_pattern


PYSSTUBS_FILE: pathlib.Path = pathlib.Path("datasets/pysstubs.csv")


def main():
    with open(PYSSTUBS_FILE, "r") as f:
        csv_reader = csv.DictReader(f)
        dataset = [r for r in csv_reader]
    print(dataset[1])


if __name__ == "__main__":
    main()
