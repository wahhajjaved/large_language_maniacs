import pathlib
import sys
import os

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
from fine_tune.deepseek_query import DeepseekQuery

TRAINING_DATASSET_DIR = pathlib.Path("downloaded_data/ctssb")


def prepare_queries() -> list[DeepseekQuery]:
    queries: list[DeepseekQuery] = []

    before_file_names = TRAINING_DATASSET_DIR.glob("*_before.py")
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
    queries = prepare_queries()
    print(f"{len(queries): } queries created. Queries using {sys.getsizeof(queries) / 1024: } MB")
	
    print(f"Downloading model into {model_dir.absolute()}")
	
    tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
    trust_remote_code=True, cache_dir=model_dir)
    model = AutoModelForCausalLM.from_pretrained(
        "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    ).cuda()

    inputs = tokenizer(
        #(q.inference_query for q in queries),
        "# write a hello world program in python",
        #add_generation_prompt=True,
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
    print(tokenizer.decode(outputs[0][len(inputs[0]) :], skip_special_tokens=True))


if __name__ == "__main__":
    main()
