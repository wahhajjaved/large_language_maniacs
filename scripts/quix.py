from datasets import load_dataset                                                  
from transformers import AutoTokenizer, AutoModelForCausalLM                       
import torch                                                                       
import re                                                                          
import ast                                                                         
import types                                                                       
import signal                                                                      
from codebleu import calc_codebleu                                                 
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import Levenshtein
import argparse
from peft import PeftModel

parser = argparse.ArgumentParser()
parser.add_argument("--model", type=str, default="deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct", help="Model path or ID")
args = parser.parse_args()

# Load model and tokenizer                                                         
model_id = args.model                           
tokenizer = AutoTokenizer.from_pretrained(model_id)                                
base_model = AutoModelForCausalLM.from_pretrained(
    "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True
)
model = PeftModel.from_pretrained(base_model, model_id)                                                                                  
                                                                                   
# Load QuixBugs dataset                                                            
dataset = load_dataset("Muennighoff/quixbugs", split="train")                      

def extract_corrected_code(text: str) -> str:                                      
    # Extract code block after correction instruction                              
    pattern = r"# Provide only the corrected code below:\s*\"{3,}?\s*(.*?)\s*\"{3,}"
    match = re.search(pattern, text, re.DOTALL)                                    
    if match:                                                                      
        return match.group(1).strip()                                              
                                                                                   
    # Fallback if no triple quotes                                                 
    parts = text.split("# Provide only the corrected code below:")                 
    if len(parts) > 1:                                                             
        return parts[1].strip().strip("\"").strip()                                
    return ""                                                                      
                                                                                   
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
    name = sample['name']                                                       
    buggy = sample['buggy_program']                                             
    doc = sample['docstring']                                                   
    ref = sample['solution'].strip()                                            
    tests = sample['tests']                                                     
                                                                                
    # Build prompt                                                              
    prompt = f"""# Provide a fix for the buggy code                             
    # code docstring                                                            
    {doc}\n                                                                     
    # Buggy code                                                                
    {buggy}\n                                                                   
    # Provide only the corrected code below:"""                                 
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)            
    outputs = model.generate(**inputs, max_new_tokens=4096, do_sample=False)    
    decoded = tokenizer.decode(outputs[0], skip_special_tokens=True)            
                                                                                
    # Clean generated output                                                    
    predicted_code = extract_corrected_code(decoded)                            
                                                                                
    print("=" * 60)                                                             
    print(f"[Example {i+1}/{total}] {name}")                                    
    print("---- Prompt ----")                                                   
    print(prompt)                                                               
    print("---- Prediction ----")                                               
    print(decoded)                                                              
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
    codebleu_scores.append(codebleu['codebleu'])                                

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
