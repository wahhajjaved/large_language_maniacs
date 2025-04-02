import json
import os
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)


# import evaluate
# import Levenshtein
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

BASE_MODEL_PATH = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
ADAPTER_PATH = "models/DeepSeek-Coder-V2-Lite-Instruct-finetuned-ctssb/checkpoint-3366/adapter_model"
TESTING_DATASET = pathlib.Path("datasets/ctssb_testing.jsonl")
OUTPUT_FILE = pathlib.Path("datasets/ctssb_testing_base_output.jsonl")

max_new_tokens = 2048 + 100  # based on model_max_length used during fine tuning


def load_dataset_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def build_instruction_prompt(instruction: str):
    return """
You are an AI assistant, developed by DeepSeek Company. For politically sensitive questions, security and privacy issues, you will refuse to answer.
### Instruction:
{}
### Response:
""".format(
        instruction.strip()
    ).lstrip()


def main():
    testing_dataset = load_dataset_file(TESTING_DATASET)
    prompts = [build_instruction_prompt(entry["input"]) for entry in testing_dataset[:10]]

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_PATH,
        quantization_config=quantization_config,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, trust_remote_code=True, padding_side="left")

    inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True)
    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)
    decoded_outputs = [tokenizer.decode(output, skip_special_tokens=True) for output in outputs]

    with open(OUTPUT_FILE, "w") as f:
        for output in decoded_outputs:
            f.write(output + "\n")


if __name__ == "__main__":
    main()
