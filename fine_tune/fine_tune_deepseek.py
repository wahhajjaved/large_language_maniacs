import pathlib

TRAINING_DATASSET_DIR = pathlib.Path("downloaded_data/ctssb")

# deepseek message format:
# messages = [
#     {"role": "system", "content": "You are a code fixer."},
#     {"role": "user", "content": buggy_code},
#     {"role": "assistant", "content": fixed_code},
# ]


class DeepseekQuery:
    system_message: str = "You are a bot that detects and fixes single statement bugs in python modules."

    def __init__(self, before_file: str, after_file: str):
        self._before_file: str = before_file
        self._after_file: str = after_file

        self._query: list[dict[str, str]] = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": self._before_file},
            {"role": "assistant", "content": self._after_file},
        ]

    @property
    def query(self):
        return self._query


def prepare_queries() -> list[DeepseekQuery]:
    queries: list[DeepseekQuery] = []

    before_file_names = TRAINING_DATASSET_DIR.glob("*_before.py")
    for before_file_name in before_file_names:
        after_file_name = before_file_name.with_stem(before_file_name.stem.replace("_before", "_after"))
        with open(before_file_name) as f:
            before_file = f.read()
        with open(after_file_name) as f:
            after_file = f.read()
        query = DeepseekQuery(
            before_file=before_file,
            after_file=after_file,
        )

        queries.append(query)

    return queries


def main():
    prepare_queries()


if __name__ == "__main__":
    main()
