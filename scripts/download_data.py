import base64
import concurrent.futures
import json
import os
import pathlib
import time

import requests

CTSSB_TRAINING: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_training.jsonl")
CTSSB_VALIDATION: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_validation.jsonl")
CTSSB_TESTING: pathlib.Path = pathlib.Path("datasets/ctssb_prepared_dataset_testing.jsonl")

CTSSB_CACHE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/cache")
CTSSB_TRAINING_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/training")
CTSSB_VALIDATION_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/validation")
CTSSB_TESTING_SAVE_DIR: pathlib.Path = pathlib.Path("downloaded_data/ctssb/testing")

DEFUNCT_PROJECTS_PATH: pathlib.Path = pathlib.Path("datasets/ctssb_data_1M/defunct_projects.jsonl")

# add github token here for increased api rate limit
token: str = "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"

FROM_CACHE_ONLY: bool = True


def load_dataset_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


# https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28
# get /repos/{owner}/{repo}/contents/{path}?ref={commit_sha}
def download_file(project_url: str, file_path: str, commit_sha: str):
    owner, repo = project_url.rstrip("/").split("/")[-2:]
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={commit_sha}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    content = base64.b64decode(response.json()["content"]).decode("utf-8")
    return content


def download_entry_concurrent(entry: dict[str, str], save_dir: pathlib.Path):
    name = f"{entry['project']}_{entry['commit_sha']}"
    before_filename = pathlib.Path(save_dir, f"{name}_before.py")
    after_filename = pathlib.Path(save_dir, f"{name}_after.py")
    cached_before_filename = pathlib.Path(CTSSB_CACHE_DIR, before_filename.name)
    cached_after_filename = pathlib.Path(CTSSB_CACHE_DIR, after_filename.name)

    cached = False
    if cached_before_filename.exists() and cached_after_filename.exists():
        cached_before_filename.rename(before_filename)
        cached_after_filename.rename(after_filename)
        cached = True
        return f"File {name} found in cached directory"

    if FROM_CACHE_ONLY and not cached:
        return f"File {name} not found in cached directory and not downloaded because downloading is disabled"

    try:
        if not before_filename.exists():
            cached = False
            file_content = download_file(
                project_url=entry["project_url"],
                file_path=entry["file_path"],
                commit_sha=entry["parent_sha"],
            )
            with open(before_filename, "w") as f:
                f.write(file_content)

        if not after_filename.exists():
            cached = False
            file_content = download_file(
                project_url=entry["project_url"],
                file_path=entry["file_path"],
                commit_sha=entry["commit_sha"],
            )
            with open(after_filename, "w") as f:
                f.write(file_content)

        msg = f"File {name} already downloaded" if cached else f"File {name} downloaded"
        return msg
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            with open(DEFUNCT_PROJECTS_PATH, "a") as f:
                f.write(json.dumps(entry) + "\n")
            msg = f"File not found {e}"
        elif e.response.status_code == 403 or e.response.status_code == 429:
            reset_ts = int(e.response.headers["X-RateLimit-Reset"])
            reset_in = reset_ts - int(time.time())
            print(
                f"Rate limit hit. X-RateLimit-Limit = {e.response.headers['X-RateLimit-Limit']}, "
                f"X-RateLimit-Remaining = {e.response.headers['X-RateLimit-Remaining']}, "
                f"Rate limit resets in {reset_in/60} minutes. "
            )
            os._exit(1)
        else:
            print(e)
            print(e.response.headers)
            os._exit(1)

    except Exception as e:
        print(e)
        os._exit(1)

    return msg


def download_entry(entry: dict[str, str], save_dir: pathlib.Path):
    name = f"{entry['project']}_{entry['commit_sha']}"
    before_filename = pathlib.Path(save_dir, f"{name}_before.py")
    after_filename = pathlib.Path(save_dir, f"{name}_after.py")
    cached = True
    if not before_filename.exists():
        cached = False
        file_content = download_file(
            project_url=entry["project_url"],
            file_path=entry["file_path"],
            commit_sha=entry["parent_sha"],
        )
        with open(before_filename, "w") as f:
            f.write(file_content)

    if not after_filename.exists():
        cached = False
        file_content = download_file(
            project_url=entry["project_url"],
            file_path=entry["file_path"],
            commit_sha=entry["commit_sha"],
        )
        with open(after_filename, "w") as f:
            f.write(file_content)

    msg = f"File {name} already downloaded" if cached else f"File {name} downloaded"
    print(msg)


def download_dataset(dataset: list[dict[str, str]], save_dir: pathlib.Path):
    save_dir.mkdir(parents=True, exist_ok=True)
    # for entry in dataset:
    #     download_entry(entry, save_dir)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(download_entry_concurrent, entry, save_dir) for entry in dataset]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                print(result)
            except Exception as e:
                print(f"Error: {e}")
                executor.shutdown(cancel_futures=True)
                raise


def move_files_to_cache():
    for file in CTSSB_TESTING_SAVE_DIR.iterdir():
        if file.is_file():
            file.rename(pathlib.Path(CTSSB_CACHE_DIR, file.name))

    for file in CTSSB_VALIDATION_SAVE_DIR.iterdir():
        if file.is_file():
            file.rename(pathlib.Path(CTSSB_CACHE_DIR, file.name))

    for file in CTSSB_TRAINING_SAVE_DIR.iterdir():
        if file.is_file():
            file.rename(pathlib.Path(CTSSB_CACHE_DIR, file.name))


def main():
    move_files_to_cache()

    training_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TRAINING)
    validation_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_VALIDATION)
    testing_dataset: list[dict[str, str]] = load_dataset_file(CTSSB_TESTING)
    download_dataset(testing_dataset, CTSSB_TESTING_SAVE_DIR)
    download_dataset(validation_dataset, CTSSB_VALIDATION_SAVE_DIR)
    download_dataset(training_dataset, CTSSB_TRAINING_SAVE_DIR)


if __name__ == "__main__":
    main()
