from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
import torch

torch.cuda.empty_cache()

"""
Loading pretrained DeepSeek-V2 model from hugging face.
Using AutoModelForCausalLM to generate output purely based on input

torch_dtype and device_map is set to auto for optimal resource usage,
modify these values as per system and model needs
"""

model_id = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True)

# print(model.config)

# text generation pipeline

generation_pipeline = pipeline(task="text-generation",
                               model=model,
                               tokenizer=tokenizer,
                               batch_size=1,
                               trust_remote_code=True)
generation_pipeline("Hello, What are you?", max_new_tokens=25)
