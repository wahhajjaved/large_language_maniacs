# deepseek message format:
# {
#     "buggy_code": f"{self._before_file}",
#     "fixed_code": f"{self._after_file}",
# }


class DeepseekQuery:
    system_message: str = "You are a bot that detects and fixes single statement bugs in python modules."

    def __init__(self, before_file_name: str, before_file: str, after_file: str):
        self.before_file_name = before_file_name
        self.before_file: str = before_file
        self.after_file: str = after_file

    @property
    def query(self):
        return {
            "prompt": f"{self.before_file}",
            "completion": f"{self.after_file}",
        }

    @property
    def inference_query(self):
        return self.before_file
