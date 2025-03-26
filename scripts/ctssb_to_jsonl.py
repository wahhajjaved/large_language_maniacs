import ast
import concurrent.futures
import json
import pathlib
import typing

START_AT_TRAINING = 0
START_AT_VALIDATION = 0
START_AT_TESTING = 0

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
                raise SyntaxError(f"before_functions and after_functions list different.")
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


def save_dataset_as_jsonl_2(data: list[tuple[str, str]], save_location):
    lines = []
    for entry in data:
        line = {"input": entry[0], "output": entry[1]}
        lines.append(json.dumps(line))

    with open(save_location, "w") as f:
        for line in lines:
            f.write(line + "\n")


def create_entry(
    entry_metadata: dict[str, str], entry_type: typing.Literal["training", "validation", "testing"]
) -> tuple[str | None, str | None]:
    entry = DatasetEntry(entry_metadata, entry_type)
    return entry.before_function_text, entry.after_function_text


def pool_wrapper(
    dataset: list[dict[str, str]],
    entries: list[tuple[str, str]],
    entry_type: typing.Literal["training", "validation", "testing"],
) -> int:
    errors_detected = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=20) as executor:
        futures = {}
        for entry_metadata in dataset:
            future = executor.submit(create_entry, entry_metadata, entry_type)
            futures[future] = entry_metadata

        for future in concurrent.futures.as_completed(futures):
            try:
                before_function_text, after_function_text = future.result()
                if not before_function_text or not after_function_text:
                    entry_metadata = futures[future]
                    print(f"Error: DatasetEntry creation failed for {entry_metadata}")
                    break

                entries.append((before_function_text, after_function_text))

            except SyntaxError as e:
                errors_detected += 1
                entry_metadata = futures[future]
                print(f"Could not parse {entry_metadata['project']}_{entry_metadata['commit_sha']}")
                print(e)
                with open(DEFUNCT_PROJECTS_PATH, "a") as f:
                    f.write(json.dumps(entry_metadata) + "\n")
            except FileNotFoundError as e:
                errors_detected += 1
                print(e)
            except Exception as e:
                errors_detected += 1
                print(e)

    return errors_detected


def process_data_concurrently():
    testing_errors = 0
    validation_errors = 0
    training_errors = 0

    # testing_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TESTING)
    # testing_dataset_entries: list[tuple[str, str]] = []
    # testing_errors = pool_wrapper(testing_dataset[START_AT_TESTING:], testing_dataset_entries, "testing")
    # save_dataset_as_jsonl_2(testing_dataset_entries, CTSSB_TESTING_DATASET)

    # validation_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_VALIDATION)
    # validation_dataset_entries: list[tuple[str, str]] = []
    # validation_errors = pool_wrapper(validation_dataset[START_AT_VALIDATION:], validation_dataset_entries, "validation")
    # save_dataset_as_jsonl_2(validation_dataset_entries, CTSSB_VALIDATION_DATASET)

    training_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TRAINING)
    training_dataset_entries: list[tuple[str, str]] = []
    training_errors = pool_wrapper(training_dataset[START_AT_TRAINING:], training_dataset_entries, "training")
    save_dataset_as_jsonl_2(training_dataset_entries, CTSSB_TRAINING_DATASET)

    print(f"\n\nDatasets converted to jsonl.")
    print(f"{testing_errors=}")
    print(f"{validation_errors=}")
    print(f"{training_errors=}")


def save_dataset_as_jsonl(data: list[DatasetEntry], save_location):
    lines = []
    for entry in data:
        line = {"input": entry.before_function_text, "output": entry.after_function_text}
        lines.append(json.dumps(line))

    with open(save_location, "w") as f:
        for line in lines:
            f.write(line + "\n")


def process_data_sequentially():
    training_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TRAINING)
    validation_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_VALIDATION)
    testing_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TESTING)

    training_dataset_entries: list[DatasetEntry] = []
    validation_dataset_entries: list[DatasetEntry] = []
    testing_dataset_entries: list[DatasetEntry] = []

    # for line in testing_dataset:
    #     try:
    #         testing_dataset_entries.append(DatasetEntry(entry_metadata=line, entry_type="testing"))
    #     except SyntaxError:
    #         print(f"Could not parse {line['project']}_{line['commit_sha']}")
    #         with open(DEFUNCT_PROJECTS_PATH, "a") as f:
    #             f.write(json.dumps(line) + "\n")
    #     except FileNotFoundError as e:
    #         print(e)
    #         break

    for line in validation_dataset:
        try:
            validation_dataset_entries.append(DatasetEntry(entry_metadata=line, entry_type="validation"))
        except SyntaxError as e:
            print(f"Could not parse {line['project']}_{line['commit_sha']}. {e}")
            with open(DEFUNCT_PROJECTS_PATH, "a") as f:
                f.write(json.dumps(line) + "\n")
        except FileNotFoundError as e:
            print(e)
            break

    # for line in training_dataset:
    #     try:
    #         training_dataset_entries.append(DatasetEntry(entry_metadata=line, entry_type="training"))
    #     except SyntaxError:
    #         print(f"Could not parse {line['project']}_{line['commit_sha']}")
    #         with open(DEFUNCT_PROJECTS_PATH, "a") as f:
    #             f.write(json.dumps(line) + "\n")
    #     except FileNotFoundError as e:
    #         print(e)
    #         break

    # save_dataset_as_jsonl(testing_dataset_entries, CTSSB_TESTING_DATASET)
    save_dataset_as_jsonl(validation_dataset_entries, CTSSB_VALIDATION_DATASET)
    # save_dataset_as_jsonl(training_dataset_entries, CTSSB_TRAINING_DATASET)


def main():
    process_data_concurrently()
    # process_data_sequentially()
    print()


if __name__ == "__main__":
    main()
