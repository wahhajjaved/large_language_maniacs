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

BASE_MODEL_PATH = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
TESTING_DATASET = pathlib.Path("datasets/ctssb_testing.jsonl")
OUTPUT_FILE = pathlib.Path("datasets/ctssb_testing_base_output.jsonl")
OUTPUT_FILE_ERROR = pathlib.Path("datasets/ctssb_testing_base_output_error.jsonl")

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


def main():
    testing_dataset = load_dataset_file(TESTING_DATASET)
    testing_dataset = testing_dataset[::10]
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
                inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True).to(model.device)
                outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)
                decoded_outputs.extend(tokenizer.decode(output, skip_special_tokens=True) for output in outputs)

        for entry, output in zip(testing_dataset, decoded_outputs):
            entry["generated_output"] = output
        save_dataset(testing_dataset, OUTPUT_FILE)

    except Exception as e:
        save_dataset(testing_dataset, OUTPUT_FILE_ERROR)
        print(e)


# def main2():
#     tokenizer = AutoTokenizer.from_pretrained(
#         "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
#         trust_remote_code=True,
#         cache_dir=model_dir,
#     )
#     model = AutoModelForCausalLM.from_pretrained(
#         "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
#         trust_remote_code=True,
#         torch_dtype=torch.bfloat16,
#         device_map="auto",
#     )

#     bleu = evaluate.load("bleu")
#     total_exact = 0
#     total_edit_distance = 0
#     generations = []
#     references = []

#     for query in dataset:
#         inputs = tokenizer(
#             query["input"],
#             return_tensors="pt",
#         ).to(model.device)
#         # tokenizer.eos_token_id is the id of <｜end▁of▁sentence｜>  token
#         outputs = model.generate(
#             **inputs,
#             max_new_tokens=512,
#             do_sample=False,
#             top_k=50,
#             top_p=0.95,
#             num_return_sequences=1,
#             eos_token_id=tokenizer.eos_token_id,
#         )
#         prediction = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True).strip()
#         reference = query["output"]

#         generations.append(prediction)
#         references.append([reference])

#         if prediction == reference:
#             total += 1

#         total_edit_distance += Levenshtein.distance(prediction, reference)

#     bleu_score = bleu.compute(predictions=generations, references=references)
#     avg_edit_distance = total_edit_distance / len(queries)
#     exact_match = total_exact / len(queries)

#     print(f"\n Evaluation Results:")
#     print(f" Exact Match Accuracy: {exact_match: .2%}")
#     print(f" Average Levenshtein Distance: {avg_edit_distance: .2f}")
#     print(f"BLEU Score: {bleu_score['bleu']:.4f}")


if __name__ == "__main__":
    main()
