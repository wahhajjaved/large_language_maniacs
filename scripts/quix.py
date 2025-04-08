import ast
import json
import pathlib
import re
import signal
import types

import Levenshtein
from codebleu import calc_codebleu
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu

DATASET_PATH = pathlib.Path("datasets/ctssb_testing_finetuned_output_incremental_step_quix.jsonl")


def load_file(path: pathlib.Path) -> list:
    dataset = []
    with open(path) as f:
        for line in f:
            dataset.append(json.loads(line))
    return dataset


def extract_corrected_code(text: str) -> str:
    # Extract code block after correction instruction
    pattern = r"\s*\"{3,}?\s*(.*?)\s*\"{3,}"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback if no triple quotes
    parts = text.split("# Provide only the corrected code below:")
    if len(parts) > 1:
        return parts[1].strip().strip('"').strip()
    return ""


def remove_docstring_from_code(code: str) -> str:
    # Match triple-quoted strings (""" or ''') after function def
    pattern = r'(?s)(def\s+[a-zA-Z_]\w*\s*\(.*?\)\s*:\s*)([\'"]{3}.*?[\'"]{3})'
    return re.sub(pattern, r"\1", code, count=1)


def clean_generate_output(generated_output: str) -> str:
    cleaned_output = generated_output.split("### Response:")[1].strip()
    base_model_pattern = r"```python\n(.*?)```"
    cleaned_output2 = re.findall(base_model_pattern, cleaned_output, re.DOTALL)

    if cleaned_output2:
        return max(cleaned_output2, key=len).strip()

    return cleaned_output


def replace_consecutive_newlines(entry: str):
    """Removes superficial differences in strings to reduce false negatives in exact match"""
    # replace_consecutive_newlines
    return "\n".join(line for line in entry.splitlines() if line.strip())


# AST comparison
def is_ast_equal(code1: str, code2: str) -> bool:
    try:
        tree1 = ast.parse(code1)
        tree2 = ast.parse(code2)
        return ast.dump(tree1) == ast.dump(tree2)
    except:
        return False


# Timeout context manager
def timeout(seconds: int):
    def decorator(func):
        def _handle_timeout(signum, frame):
            raise TimeoutError("Execution timed out")

        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)

        return wrapper

    return decorator


# Unit test checker
@timeout(30)
def passes_unit_tests(code: str, tests: str) -> bool:
    try:
        # Create a fresh "fake" module to sandbox the execution
        sandbox = types.ModuleType("sandbox_module")
        exec(code, sandbox.__dict__)
        exec(tests, sandbox.__dict__)
        return True
    except Exception as e:
        print(f"❌ Test failure: {e}")
        return False


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


dataset = load_file(DATASET_PATH)
# Evaluation loop
exact_matches = 0
ast_matches = 0
unit_test_matches = 0
codebleu_scores = []
bleu_scores = []
levenshtein_distances = []
levenshtein_ratios = []
total = len(dataset)


for i, sample in enumerate(dataset):
    name = sample["name"]
    buggy = sample["buggy_program"]
    doc = sample["docstring"]
    ref = sample["solution"].strip()
    tests = sample["tests"]
    decoded = sample["generated_output"]

    ref = replace_consecutive_newlines(ref)
    # Clean generated output
    predicted_code = clean_generate_output(decoded)
    predicted_code = remove_docstring_from_code(predicted_code)
    predicted_code = replace_consecutive_newlines(predicted_code)

    print("=" * 60)
    print(f"[Example {i+1}/{total}] {name}")
    print("---- Prompt ----")
    print(buggy)
    print("---- Prediction ----")
    print(decoded.strip())
    print("---- Cleaned ----")
    print(predicted_code)
    print("---- Reference ----")
    print(ref)

    # Exact match
    if predicted_code.strip() == ref.strip():
        print("[EXACT MATCH] ✅")
        exact_matches += 1
    else:
        print("[NO EXACT MATCH] ❌")

    # AST match
    if is_ast_equal(predicted_code, ref):
        print("[AST MATCH ✅]")
        ast_matches += 1
    else:
        print("[NO AST MATCH ❌]")

    # Unit test match
    try:
        if passes_unit_tests(predicted_code, tests):
            print("[UNIT TEST MATCH ✅]")
            unit_test_matches += 1
        else:
            print("[UNIT TEST FAIL ❌]")
    except TimeoutError:
        print("[⏱️  TIMEOUT]")

    # CodeBLEU score
    codebleu = calc_codebleu([ref], [predicted_code], lang="python")
    print(f"[CodeBLEU] {codebleu['codebleu']:.4f}")
    codebleu_scores.append(codebleu["codebleu"])

    # BLEU score
    smoothie = SmoothingFunction().method4
    ref_tokens = [ref.strip().split()]
    pred_tokens = predicted_code.strip().split()
    bleu = sentence_bleu(ref_tokens, pred_tokens, smoothing_function=smoothie)
    print(f"[BLEU] {bleu:.4f}")
    bleu_scores.append(bleu)

    # Levenshtein distance
    lev_distance = Levenshtein.distance(predicted_code.strip(), ref.strip())
    lev_ratio = Levenshtein.ratio(predicted_code.strip(), ref.strip())
    print(f"[Levenshtein Distance] {lev_distance}, Similarity: {lev_ratio:.4f}")
    levenshtein_distances.append(lev_distance)
    levenshtein_ratios.append(lev_ratio)

# Summary
print("\n--- Evaluation Results ---")
print(f"Exact match: {exact_matches}/{total} ({exact_matches/total:.2%})")
print(f"AST match:   {ast_matches}/{total} ({ast_matches/total:.2%})")
print(f"Unit test match: {unit_test_matches}/{total} ({unit_test_matches/total:.2%})")
if codebleu_scores:
    avg_codebleu = sum(codebleu_scores) / len(codebleu_scores)
    print(f"Avg CodeBLEU score: {avg_codebleu:.4f}")

if bleu_scores:
    avg_bleu = sum(bleu_scores) / len(bleu_scores)
    print(f"Avg BLEU score: {avg_bleu:.4f}")

if levenshtein_distances:
    avg_lev = sum(levenshtein_distances) / len(levenshtein_distances)
    avg_lev_ratio = sum(levenshtein_ratios) / len(levenshtein_ratios)
    print(f"Avg Levenshtein distance: {avg_lev:.2f}")
    print(f"Avg Levenshtein similarity ratio: {avg_lev_ratio:.4f}")
