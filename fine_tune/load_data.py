import pathlib
import typing

from fine_tune.deepseek_query import DeepseekQuery

TRAINING_DATASSET_DIR = pathlib.Path("downloaded_data/ctssb")
TESTING_DATASSET_DIR = pathlib.Path("downloaded_data/ctssb/testing")


def prepare_deepseek_ctssb_queries(dataset_type: typing.Literal["training", "testing"]) -> list[DeepseekQuery]:
    queries: list[DeepseekQuery] = []
    if dataset_type == "training":
        before_file_names = TRAINING_DATASSET_DIR.glob("*_before.py")
    elif dataset_type == "testing":
        before_file_names = TESTING_DATASSET_DIR.glob("*_before.py")
    else:
        raise ValueError

    for before_file_name in before_file_names:
        after_file_name = before_file_name.with_stem(before_file_name.stem.replace("_before", "_after"))
        with open(before_file_name) as f:
            before_file = f.read()
        with open(after_file_name) as f:
            after_file = f.read()
        query = DeepseekQuery(
            before_file_name.name,
            before_file=before_file,
            after_file=after_file,
        )

        queries.append(query)

    return queries
