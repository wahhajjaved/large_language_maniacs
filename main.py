import json
import torch
from datasets import load_dataset
import pytorch
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorWithPadding


raw_data = load_dataset("datasets/ctssb")
print(raw_data)
