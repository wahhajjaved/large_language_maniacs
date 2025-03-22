
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

    @property
    def inference_query(self):
        return [{"role": "system", "content": self.system_message}, {"role": "user", "content": self._before_file}]

