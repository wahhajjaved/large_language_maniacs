import pathlib
import sys
import os
import evaluate
import Levenshtein

def getModelsPath():
    script_dir = pathlib.Path(__file__).resolve().parent
    if script_dir.name == "fine_tune":
	    return pathlib.Path(script_dir.parent, "models")
    else:
	    return pathlib.Path(script_dir, "models")
model_dir = getModelsPath()   
os.environ["HF_HOME"] = str(model_dir.absolute())

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from deepseek_query import DeepseekQuery

TESTING_DATASET_DIR = pathlib.Path("datasets/ctssb_prepared_dataset_testing.jsonl")
dataset = load_dataset("json", data_files=TESTING_DATASET_DIR)

def prepare_queries() -> list[DeepseekQuery]:
    queries: list[DeepseekQuery] = []

    before_file_names = TESTING_DATASET_DIR.glob("*_before.py")
    for before_file_name in before_file_names:
        after_file_name = before_file_name.with_stem(before_file_name.stem.replace("_before", "_after"))
        with open(before_file_name) as f:
            before_file = f.read()
        with open(after_file_name) as f:
            after_file = f.read()
        query = DeepseekQuery(
            before_file=before_file,
            after_file=after_file,
        )

        queries.append(query)

    return queries


def main():
    #queries = prepare_queries()
    #print(f"{len(queries): } queries created. Queries using {sys.getsizeof(queries) / 1024: } MB")
	
    #print(f"Downloading model into {model_dir.absolute()}")
	
    tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
    trust_remote_code=True, cache_dir=model_dir)
    model = AutoModelForCausalLM.from_pretrained(
        "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    ).cuda()

    bleu = evaluate.load("bleu")
    total_exact = 0
    total_edit_distance = 0
    generations = []
    references = []

    for query in dataset:
        inputs = tokenizer(
            (q.inference_query for q in queries),
            # write a hello world program in python",
            # add_generation_prompt = True,
            query.before_file,
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
        prediction = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        reference = query.after_file.strip()

        generations.append(prediction)
        references.append([reference])

        if prediction == reference:
            total += 1

        total_edit_distance += Levenshtein.distance(prediction, reference)

    bleu_score = bleu.compute(predictions=generations, references= references)
    avg_edit_distance = total_edit_distance / len(queries)
    exact_match = total_exact / len(queries)

    print(f"\n Evaluation Results:")
    print(f" Exact Match Accuracy: {exact_match: .2%}")
    print(f" Average Levenshtein Distance: {avg_edit_distance: .2f}")
    print(f"BLEU Score: {bleu_score['bleu']:.4f}")
    

if __name__ == "__main__":
    main()
