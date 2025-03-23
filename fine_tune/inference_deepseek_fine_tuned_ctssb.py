import os
import pathlib
import sys
import warnings

from fine_tune.load_data import prepare_deepseek_ctssb_queries

model_dir = pathlib.Path("models")
os.environ["HF_HOME"] = str(model_dir.absolute())

import torch
from peft import PeftConfig, PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, logging

logging.set_verbosity_error()

model_name = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
adapter_dir = pathlib.Path(
    model_dir,
    "DeepSeek-Coder-V2-Lite-Instruct-python-finetuned-ctssb",
)

save_dir = pathlib.Path("output_data/ctssb")


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
    queries = prepare_deepseek_ctssb_queries("testing")

    for q in queries:
        print(f"Running inference on {q.before_file_name}")
        inputs = tokenizer(q.inference_query, return_tensors="pt").to("cuda")
        outputs = model.generate(**inputs, max_new_tokens=100)
        save_file_name = q.before_file_name.replace("_before.py", "_inference.py")
        output_path = pathlib.Path(save_dir, save_file_name)
        output = tokenizer.decode(outputs[0], skip_special_tokens=True)
        with open(output_path, "w") as f:
            f.write(output)


if __name__ == "__main__":
    main()
