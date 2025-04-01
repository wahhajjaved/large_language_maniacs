import os
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)


def getModelsPath():
    script_dir = pathlib.Path(__file__).resolve().parent
    if script_dir.name == "fine_tune":
        return pathlib.Path(script_dir.parent, "models")
    else:
        return pathlib.Path(script_dir, "models")


model_dir = getModelsPath()
os.environ["HF_HOME"] = str(model_dir.absolute())

import evaluate
import Levenshtein
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from datasets import load_dataset

TESTING_DATASET = pathlib.Path("datasets/ctssb_testing.jsonl")
dataset = load_dataset("json", data_files=str(TESTING_DATASET), split="train")


def main():
    tokenizer = AutoTokenizer.from_pretrained(
        "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        trust_remote_code=True,
        cache_dir=model_dir,
    )
    model = AutoModelForCausalLM.from_pretrained(
        "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    bleu = evaluate.load("bleu")
    total_exact = 0
    total_edit_distance = 0
    generations = []
    references = []

    for query in dataset:
        inputs = tokenizer(
            query["input"],
            return_tensors="pt",
        ).to(model.device)
        # tokenizer.eos_token_id is the id of <｜end▁of▁sentence｜>  token
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=False,
            top_k=50,
            top_p=0.95,
            num_return_sequences=1,
            eos_token_id=tokenizer.eos_token_id,
        )
        prediction = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True).strip()
        reference = query["output"]

        generations.append(prediction)
        references.append([reference])

        if prediction == reference:
            total += 1

        total_edit_distance += Levenshtein.distance(prediction, reference)

    bleu_score = bleu.compute(predictions=generations, references=references)
    avg_edit_distance = total_edit_distance / len(queries)
    exact_match = total_exact / len(queries)

    print(f"\n Evaluation Results:")
    print(f" Exact Match Accuracy: {exact_match: .2%}")
    print(f" Average Levenshtein Distance: {avg_edit_distance: .2f}")
    print(f"BLEU Score: {bleu_score['bleu']:.4f}")


if __name__ == "__main__":
    main()
