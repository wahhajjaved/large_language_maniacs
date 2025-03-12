import json
import pathlib

MANYSSTUBS4K_PATH: pathlib.Path = pathlib.Path("datasets/sstubsLarge.json")


def main():
    with open(MANYSSTUBS4K_PATH) as f:
        dataset = json.load(f)
    print(dataset[0])


if __name__ == "__main__":
    main()
