import base64
import json
import pathlib

import requests

CTSSB: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset.jsonl")
SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb")


# https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28
# get /repos/{owner}/{repo}/contents/{path}?ref={commit_sha}
def download_file(project_url: str, file_path: str, commit_sha: str):
    owner, repo = project_url.rstrip("/").split("/")[-2:]
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={commit_sha}"

    response = requests.get(url)
    response.raise_for_status()
    content = base64.b64decode(response.json()["content"]).decode("utf-8")
    return content


def load_dataset_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def main():
    dataset: list[dict[str, str]] = load_dataset_file(CTSSB)

    for entry in dataset:
        before_filename = pathlib.Path(SAVE_DIR, f"{entry['parent_sha']}_before.py")
        after_filename = pathlib.Path(SAVE_DIR, f"{entry['commit_sha']}_after.py")

        if not before_filename.exists():
            file_content = download_file(
                project_url=entry["project_url"],
                file_path=entry["file_path"],
                commit_sha=entry["parent_sha"],
            )
            with open(before_filename, "w") as f:
                f.write(file_content)

        if not after_filename.exists():
            file_content = download_file(
                project_url=entry["project_url"],
                file_path=entry["file_path"],
                commit_sha=entry["commit_sha"],
            )
            with open(after_filename, "w") as f:
                f.write(file_content)

        break


if __name__ == "__main__":
    main()
