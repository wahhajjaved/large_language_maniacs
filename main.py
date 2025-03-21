import json
import torch
from datasets import load_dataset
import pytorch
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorWithPadding

path = "datasets/ctssb/"
raw_data = []
for i in range (0, 64):
    with open(path+i+"_before.py", r) as beforef:
        raw_data[i] = {"before": read(beforef)}

    with open(path+i+"_after.py", r) as afterf:
        raw_data[i] = {"after": read(afterf)}


