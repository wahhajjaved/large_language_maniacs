import json
import os
import pathlib
import signal
import sys
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

STEP_SIZE = 2
BASE_MODEL_PATH = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
TESTING_DATASET = pathlib.Path("datasets/ctssb_testing.jsonl")
OUTPUT_FILE = pathlib.Path("datasets/ctssb_testing_base_output.jsonl")
OUTPUT_FILE_ERROR = pathlib.Path("datasets/ctssb_testing_base_output_error.jsonl")
OUTPUT_FILE_INCREMENTAL = pathlib.Path(f"datasets/ctssb_testing_base_output_incremental_step_{STEP_SIZE}.jsonl")

max_new_tokens = 2048 + 100  # based on model_max_length used during fine tuning
device = "cuda:2"


def load_dataset_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def save_dataset(data: list[dict], save_location):
    lines = []
    for entry in data:
        lines.append(json.dumps(entry))

    with open(save_location, "w") as f:
        for line in lines:
            f.write(line + "\n")


def build_instruction_prompt(instruction: str):
    return """
You are an AI assistant, developed by DeepSeek Company. For politically sensitive questions, security and privacy issues, you will refuse to answer.
### Instruction:
fix the single statement bug in this python method
{}
### Response:
""".format(
        instruction.strip()
    ).lstrip()


def save_dataset_incremently(data: list[dict], save_location):
    lines = []
    for entry in data:
        lines.append(json.dumps(entry))

    with open(save_location, "a") as f:
        for line in lines:
            f.write(line + "\n")


def main_incremental():
    testing_dataset = load_dataset_file(TESTING_DATASET)
    testing_dataset = testing_dataset[::STEP_SIZE]

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
        device_map=device,
        attn_implementation="flash_attention_2",
    )
    model.generation_config.cache_implementation = "static"
    model.config.use_cache = True
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, trust_remote_code=True, padding_side="left")

    batch_size = 5
    decoded_outputs = []

    with torch.inference_mode():
        for i in range(0, len(testing_dataset), batch_size):
            subset = testing_dataset[i : i + batch_size]
            prompts = [build_instruction_prompt(entry["input"]) for entry in subset]
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


def main():
    testing_dataset = load_dataset_file(TESTING_DATASET)
    testing_dataset = testing_dataset[::20]
    prompts = [build_instruction_prompt(entry["input"]) for entry in testing_dataset]

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
        device_map="cuda:1",
        attn_implementation="flash_attention_2",
    )
    model.generation_config.cache_implementation = "static"
    model.config.use_cache = True
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, trust_remote_code=True, padding_side="left")

    batch_size = 5
    decoded_outputs = []

    def save_on_interrupt(signal_received, frame):
        for entry, output in zip(testing_dataset, decoded_outputs):
            entry["generated_output"] = output
        save_dataset(testing_dataset, OUTPUT_FILE_ERROR)
        print("\nInterrupted! Partial results saved.")
        sys.exit(0)

    signal.signal(signal.SIGINT, save_on_interrupt)

    try:
        with torch.inference_mode():
            for i in range(0, len(prompts), batch_size):
                print(f"Running batch {i}")
                batch = prompts[i : i + batch_size]
                try:
                    inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True)
                    inputs = {k: v.to(model.device) for k, v in inputs.items()}
                    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)
                    decoded_outputs.extend(tokenizer.decode(output, skip_special_tokens=True) for output in outputs)
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    print("OOM on batch, inserting empty outputs.")
                    decoded_outputs.extend(["" for _ in batch])

        for entry, output in zip(testing_dataset, decoded_outputs):
            entry["generated_output"] = output
        save_dataset(testing_dataset, OUTPUT_FILE)

    except Exception as e:
        for entry, output in zip(testing_dataset, decoded_outputs):
            entry["generated_output"] = output
        save_dataset(testing_dataset, OUTPUT_FILE_ERROR)
        print(e)


if __name__ == "__main__":
    main()
