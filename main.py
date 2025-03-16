import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorWithPadding


# Load the dataset
def loadDataset(filepath):
    with open(filepath, 'r') as file:
        data = json.load(file)

    return

dataset1 = loadDataset("datasets/sstubsLarge.json")

def filterDataset(dataset):
    filteredDataset = []
    for column in dataset:
        filteredDataset.append(
            {"before": column["before"]},
            {"after": column["after"]},
            {"commitNum": column["commitSHA1"]},
        )
    return filteredDataset

model_name = AutoModelForCausalLM.from_pretrained("deepseek-ai/DeepSeek-Coder-V2-Lite-Base", trust_remote_code=True, torch_dtype=torch.bfloat16).cuda()
tokenizedModel = AutoTokenizer.from_pretrained(model_name)
filteredData = filterDataset(dataset1)
print(filterDataset[0])

def tokenize_function(examples):
    return tokenizedModel(examples["before"], examples["after"], truncation = True)

# tokenized_datasets = filteredData.map(tokenize_function, batched = True)
tokenizedData = tokenizedModel.tokenize(filteredData)

print(tokenizedData)
# data_collator = DataCollatorWithPadding(tokenized)
