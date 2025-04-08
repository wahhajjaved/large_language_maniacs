import json
import os
import pathlib
import signal
import sys
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)


import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

import datasets

BASE_MODEL_PATH = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
ADAPTER_PATH = "models/DeepSeek-Coder-V2-Lite-Instruct-finetuned-ctssb/checkpoint-3366/adapter_model"
TESTING_DATASET = "Muennighoff/quixbugs"
OUTPUT_FILE_INCREMENTAL = pathlib.Path(f"datasets/ctssb_testing_finetuned_output_incremental_step_quix.jsonl")
OUTPUT_FILE_ERROR = pathlib.Path("datasets/ctssb_testing_finetuned_output_quix_error.jsonl")

max_new_tokens = 2048 + 100  # based on model_max_length used during fine tuning


def save_dataset_incremently(data: list[dict], save_location):
    lines = []
    for entry in data:
        lines.append(json.dumps(entry))

    with open(save_location, "a") as f:
        for line in lines:
            f.write(line + "\n")


def insert_docstring_into_function(docstring: str, code: str) -> str:
    lines = code.splitlines()
    indent = " " * 4 if len(lines) > 1 and lines[1].startswith("    ") else " " * 2
    docstring_lines = [f"{indent}"] + [f"{indent}{line}" for line in docstring.strip().splitlines()] + [f"{indent}"]
    return "\n".join([lines[0]] + docstring_lines + lines[1:])


def build_instruction_prompt(doc: str, code: str):
    instruction = insert_docstring_into_function(doc, code)
    return """
You are an AI assistant, developed by DeepSeek Company. For politically sensitive questions, security and privacy issues, you will refuse to answer.
### Instruction:
Provide a fix for the buggy code. Use the doc string to figure out what the code should do.
{}
### Response:
""".format(
        instruction.strip()
    ).lstrip()


def main_incremental():
    testing_dataset = datasets.load_dataset(TESTING_DATASET, split="train")

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=False,
        bnb_4bit_quant_type="nf4",
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_PATH,
        quantization_config=quantization_config,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        device_map="auto",
        attn_implementation="flash_attention_2",
    )
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    model.generation_config.cache_implementation = "static"
    model.config.use_cache = True

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, trust_remote_code=True, padding_side="left")

    batch_size = 10
    decoded_outputs = []

    with torch.inference_mode():
        for i in range(0, len(testing_dataset), batch_size):
            subset = testing_dataset.select(range(i, i + batch_size))
            subset = subset.to_dict(batch_size=None)
            subset = [dict(zip(subset.keys(), values)) for values in zip(*subset.values())]
            prompts = [build_instruction_prompt(entry["docstring"], entry["buggy_program"]) for entry in subset]
            print(f"{time.asctime()} Running batch {i} on finetuned model")

            try:
                inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True)
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
                outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)
                decoded_outputs = [tokenizer.decode(output, skip_special_tokens=True) for output in outputs]
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                print("OOM on batch, inserting empty outputs.")
                decoded_outputs = ["" for _ in prompts]

            for entry, output in zip(subset, decoded_outputs):
                entry["generated_output"] = output
            save_dataset_incremently(subset, OUTPUT_FILE_INCREMENTAL)


if __name__ == "__main__":
    main_incremental()
