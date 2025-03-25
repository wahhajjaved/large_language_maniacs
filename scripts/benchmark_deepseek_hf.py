import re
import ast
import torch
from tqdm import tqdm
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
import evaluate
from codebleu import calc_codebleu

# -------------------------------
# Configuration
# -------------------------------
MODEL_NAME = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
DATASET_PATH = "iberu/PySStuBs"
BATCH_SIZE = 8
MAX_NEW_TOKENS = 4096
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_DEBUG = 100

# -------------------------------
# Helper to extract clean code
# -------------------------------
def extract_corrected_code(text: str) -> str:
    """
    Extracts only the corrected code block following the instruction marker.
    Keeps inline comments and ensures complete function extraction.
    """
    split_marker = "# Provide only the corrected code below (no explanation, comments, or extra copies):"
    if split_marker in text:
        after = text.split(split_marker, 1)[1]
        # Remove leading/trailing quotes or whitespace
        after = after.strip().strip("`").strip()
        return after

    return text.strip()

# -------------------------------
# AST Matcher
# -------------------------------
def is_ast_match(pred: str, ref: str) -> bool:
    try:
        return ast.dump(ast.parse(pred)) == ast.dump(ast.parse(ref))
    except:
        return False

# -------------------------------
# Load model and tokenizer
# -------------------------------
print("🔍 Loading model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, device_map="auto", trust_remote_code=True)
model.eval()

# -------------------------------
# Load dataset (debug mode)
# -------------------------------
print("📦 Loading dataset...")
dataset = load_dataset(DATASET_PATH, split="train[:10%]")

# -------------------------------
# Metric tools
# -------------------------------
exact_match = evaluate.load("exact_match")
bleu = evaluate.load("bleu")

# -------------------------------
# Batched Inference
# -------------------------------
print("⚙️ Running inference...")
predictions, references, ast_matches = [], [], []
raw_predictions = []

for i in tqdm(range(0, len(dataset), BATCH_SIZE)):
    batch = dataset.select(range(i, min(i + BATCH_SIZE, len(dataset))))

    # Prompt instructions
    instruction_prefix = (
        "# The function below is part of a larger project and contains a subtle bug.\n"
        "# Only one line needs to be changed."
    )
    instruction_suffix = "# Provide only the corrected code below (no explanation, comments, or extra copies):"

    prompts = [
        f"{instruction_prefix}\n{ex}\n\n{instruction_suffix}"
        for ex in batch["input"]
    ]
    refs = batch["output"]

    # Tokenize + infer
    inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True).to(DEVICE)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)

    decoded_batch = tokenizer.batch_decode(outputs, skip_special_tokens=True)

    for pred_raw, ref in zip(decoded_batch, refs):
        raw_predictions.append(pred_raw)
        pred_clean = extract_corrected_code(pred_raw)
        predictions.append(pred_clean.strip())
        references.append(ref.strip())
        ast_matches.append(is_ast_match(pred_clean.strip(), ref.strip()))

# -------------------------------
# Compute Metrics
# -------------------------------
print("📊 Evaluating...")

em_score = exact_match.compute(predictions=predictions, references=references)["exact_match"]
bleu_score = bleu.compute(predictions=predictions, references=references)["bleu"]
ast_match_score = sum(ast_matches) / len(ast_matches)

codebleu_result = calc_codebleu(
    references,
    predictions,
    lang="python",
    weights=(0.25, 0.25, 0.25, 0.25)
)

# -------------------------------
# Output Results
# -------------------------------
print("\n✅ Evaluation Results")
print(f"Exact Match:         {em_score:.4f}")
print(f"BLEU Score:          {bleu_score:.4f}")
print(f"AST Match:           {ast_match_score:.4f}")
print(f"CodeBLEU (overall):  {codebleu_result['codebleu']:.4f}")
for key, value in codebleu_result.items():
    if key != "codebleu":
        print(f"  {key}: {value:.4f}")

# -------------------------------
# Debugging Mismatches
# -------------------------------
print("\n🔍 Debugging Mismatches (showing first few failures)")
debug_count = 0
for idx, (pred, ref, ast_ok) in enumerate(zip(predictions, references, ast_matches)):
    exact_ok = pred.strip() == ref.strip()
    if not exact_ok or not ast_ok:
        print(f"\n=== Sample {idx} ===")
        print(f"[Exact Match]: {'✅' if exact_ok else '❌'}")
        print(f"[AST Match]:   {'✅' if ast_ok else '❌'}")
        print(f"\nPrompt:\n{dataset[idx]['input']}")
        print(f"\nRaw Prediction:\n{raw_predictions[idx]}")
        print(f"\nCleaned Prediction:\n{predictions[idx]}")
        print(f"\nReference:\n{ref}")
        debug_count += 1
        if debug_count >= MAX_DEBUG:
            break

