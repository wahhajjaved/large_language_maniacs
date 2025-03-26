import os
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

from fine_tune.load_data import prepare_deepseek_ctssb_queries

model_dir = pathlib.Path("models")
os.environ["HF_HOME"] = str(model_dir.absolute())

import torch
from peft import PeftConfig, PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, logging

from datasets import load_dataset

model_name = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
adapter_dir = pathlib.Path(
    model_dir,
    "DeepSeek-Coder-V2-Lite-Instruct-python-finetuned-ctssb",
)

save_dir = pathlib.Path("output_data/ctssb")
TESTING_DATASET = pathlib.Path("datasets/ctssb_testing.jsonl")


def main():
    # Load base model
    base_model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        device_map="auto",
    )
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        cache_dir=model_dir,
    )
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Load LoRA adapter
    model = PeftModel.from_pretrained(base_model, adapter_dir)
    model.merge_and_unload()

    # Inference
    dataset = load_dataset("json", data_files=str(TESTING_DATASET), split="train")

    for query in dataset:
        inputs = tokenizer(
            query["input"],
            return_tensors="pt",
        ).to(model.device)
        outputs = model.generate(**inputs, max_new_tokens=100)
        output = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print(output)


if __name__ == "__main__":
    main()
