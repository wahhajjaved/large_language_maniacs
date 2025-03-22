# deepseek message format:
# {
#     "buggy_code": f"{self._before_file}",
#     "fixed_code": f"{self._after_file}",
# }


class DeepseekQuery:
    system_message: str = "You are a bot that detects and fixes single statement bugs in python modules."

    def __init__(self, before_file: str, after_file: str):
        self._before_file: str = before_file
        self._after_file: str = after_file

        # self._query: list[dict[str, str]] = [
        #     {"role": "system", "content": self.system_message},
        #     {"role": "user", "content": self._before_file},
        #     {"role": "assistant", "content": self._after_file},
        # ]

    @property
    def query(self):
        return {
            "prompt": f"{self._before_file}",
            "completion": f"{self._after_file}",
        }

    @property
    def inference_query(self):
        return {
            "prompt": f"{self._before_file}",
        }
