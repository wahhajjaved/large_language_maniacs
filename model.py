from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
import torch

"""
Loading pretrained DeepSeek-V2 model from hugging face.
Using AutoModelForCausalLM to generate output purely based on input

torch_dtype and device_map is set to auto for optimal resource usage,
modify these values as per system and model needs
"""

model_id = "deepseek-ai/DeepSeek-V2"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True)

# text generation pipeline

generation_pipeline = pipeline(task="text-generation",
                                model=model,
                                tokenizer=tokenizer,
                                trust_remote_code=True)
generation_pipeline("Hello, What are you?", max_new_tokens=25)