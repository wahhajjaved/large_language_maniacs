import ast
import json
import pathlib
import typing

ENTRY_PER_PATTERN_TRAINING = 900
ENTRY_PER_PATTERN_VALIDATION = 150
ENTRY_PER_PATTERN_TESTING = 100

# input
CTSSB_TRAINING_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/training")
CTSSB_VALIDATION_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/validation")
CTSSB_TESTING_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/testing")
CTSSB_TRAINING: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_training.jsonl")
CTSSB_VALIDATION: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_validation.jsonl")
CTSSB_TESTING: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_testing.jsonl")

# output
CTSSB_TRAINING_DATASET: pathlib.Path = pathlib.Path("datasets/ctssb_training.jsonl")
CTSSB_VALIDATION_DATASET: pathlib.Path = pathlib.Path("datasets/ctssb_validation.jsonl")
CTSSB_TESTING_DATASET: pathlib.Path = pathlib.Path("datasets/ctssb_testing.jsonl")
DEFUNCT_PROJECTS_PATH: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M/defunct_projects.jsonl")


class DatasetEntry:

    def __init__(self, entry_metadata: dict[str, str], entry_type: typing.Literal["training", "validation", "testing"]):
        self._entry_metadata: dict[str, str] = entry_metadata
        self._entry_type = entry_type
        self._before_function: typing.Optional[ast.FunctionDef] = None
        self._after_function: typing.Optional[ast.FunctionDef] = None
        self.get_files()
        self.extract_function()
        if not self._before_function or not self._after_function:
            raise SyntaxError(f"Could not extract method for {self._entry_metadata}")

    def get_files(self):
        name = f"{self._entry_metadata['project']}_{self._entry_metadata['commit_sha']}"
        if self._entry_type == "training":
            save_dir = CTSSB_TRAINING_SAVE_DIR
        elif self._entry_type == "validation":
            save_dir = CTSSB_VALIDATION_SAVE_DIR
        elif self._entry_type == "testing":
            save_dir = CTSSB_TESTING_SAVE_DIR
        self._before_filename = pathlib.Path(save_dir, f"{name}_before.py")
        self._after_filename = pathlib.Path(save_dir, f"{name}_after.py")
        with open(self._before_filename) as f:
            self._before_file = f.read()
        with open(self._after_filename) as f:
            self._after_file = f.read()

    def extract_function(self):
        before_tree = ast.parse(self._before_file)
        after_tree = ast.parse(self._after_file)
        before_functions: list[ast.FunctionDef] = [n for n in ast.walk(before_tree) if isinstance(n, ast.FunctionDef)]
        after_functions: list[ast.FunctionDef] = [n for n in ast.walk(after_tree) if isinstance(n, ast.FunctionDef)]

        if len(before_functions) != len(after_functions):
            raise ValueError("The number of functions differs between before and after files.")

        for b, a in zip(before_functions, after_functions):
            if b.name != a.name:
                raise ValueError(f"before_functions and after_functions list different.")
            before_text = ast.get_source_segment(self._before_file, b)
            after_text = ast.get_source_segment(self._after_file, a)
            if before_text != after_text:
                self._before_function = b
                self._after_function = a

    @property
    def before_function_text(self):
        if not self._before_function:
            raise ValueError()
        return ast.get_source_segment(self._before_file, self._before_function)

    @property
    def after_function_text(self):
        if not self._after_function:
            raise ValueError()
        return ast.get_source_segment(self._after_file, self._after_function)


def load_dataset_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def save_dataset_as_jsonl(data: list[DatasetEntry], save_location):
    lines = []
    for entry in data:
        line = {"input": entry.before_function_text, "output": entry.after_function_text}
        lines.append(json.dumps(line))

    with open(save_location, "w") as f:
        for line in lines:
            f.write(line + "\n")


def main():
    training_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TRAINING)
    validation_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_VALIDATION)
    testing_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TESTING)

    training_dataset_entries: list[DatasetEntry] = []
    validation_dataset_entries: list[DatasetEntry] = []
    testing_dataset_entries: list[DatasetEntry] = []

    for line in testing_dataset:
        try:
            testing_dataset_entries.append(DatasetEntry(entry_metadata=line, entry_type="testing"))
        except SyntaxError:
            print(f"Could not parse {line['project']}_{line['commit_sha']}")
            with open(DEFUNCT_PROJECTS_PATH, "a") as f:
                f.write(json.dumps(line) + "\n")
        except FileNotFoundError as e:
            print(e)
            break

    save_dataset_as_jsonl(testing_dataset_entries, CTSSB_TESTING_DATASET)


if __name__ == "__main__":
    main()
