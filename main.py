import json

# Load the dataset
def loadDataset(filepath):
    with open(filepath, 'r') as file:
        data = json.load(file)

    print(data[0])

    return

dataset1 = loadDataset("datasets/sstubsLarge.json")

def filterDataset(dataset):
    filteredDataset = []
    for column in dataset:
        filterDataset.append(column[1])
        