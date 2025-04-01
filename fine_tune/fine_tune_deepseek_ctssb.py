# Run this with DDP with "accelerate launch fine_tune/fine_tune_deepseek_ctssb.py"
# Run accelerate config and choose the following options (set gpu ids according to which is free)
#  In which compute environment are you running? This machine
# Which type of machine are you using? multi-GPU
# How many different machines will you use (use more than 1 for multi-node training)? [1]: 1
# Should distributed operations be checked while running for errors? This can avoid timeout issues but will be slower. [yes/NO]: no
# Do you wish to optimize your script with torch dynamo?[yes/NO]:no
# Do you want to use DeepSpeed? [yes/NO]: no
# Do you want to use FullyShardedDataParallel? [yes/NO]: no
# Do you want to use TensorParallel? [yes/NO]: no
# Do you want to use Megatron-LM ? [yes/NO]: no
# How many GPU(s) should be used for distributed training? [1]:2
# What GPU(s) (by id) should be used for training on this machine as a comma-seperated list? [all]:1,2
# Would you like to enable numa efficiency? (Currently only supported on NVIDIA hardware). [yes/NO]: no
# Do you wish to use mixed precision? no

import os
import pathlib
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


import peft
import torch

# from accelerate import PartialState
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

from datasets import load_dataset

CTSSB_TRAINING_DATASET: pathlib.Path = pathlib.Path("datasets/ctssb_testing.jsonl")
model_name = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
new_model = "DeepSeek-Coder-V2-Lite-Instruct-python-finetuned-ctssb"


# device_string = PartialState().process_index
# device_map = {"": device_string}
device_map = {"": torch.cuda.current_device()}

max_seq_length = 2048


tokenizer = AutoTokenizer.from_pretrained(
    model_name,
    trust_remote_code=True,
    cache_dir=model_dir,
)
tokenizer.padding_side = "right"
tokenizer.pad_token = tokenizer.eos_token


def filter_long_entry(example):
    prompt = f"input: \n{example['input']} \noutput: \n"
    full_text = prompt + example["output"]
    num_tokens = len(tokenizer.backend_tokenizer.encode(full_text).ids)
    return num_tokens <= tokenizer.model_max_length


def format_dataset_batched(examples):
    prompts = [f"input: \n{inp} \noutput: \n" for inp in examples["input"]]
    full_texts = [p + out for p, out in zip(prompts, examples["output"])]

    tokenized = tokenizer(
        full_texts,
        truncation=True,
        max_length=max_seq_length,
        padding="max_length",  # ensures padding
    )

    prompt_lengths = [len(tokenizer(p)["input_ids"]) for p in prompts]
    labels = []

    for ids, p_len in zip(tokenized["input_ids"], prompt_lengths):
        label = ids.copy()
        label[:p_len] = [-100] * p_len
        labels.append(label)

    tokenized["labels"] = labels
    return tokenized


def format_dataset(example):
    # Construct the prompt and full text
    prompt = f"input: \n{example['input']} \noutput: \n"
    full_text = prompt + example["output"]

    # Tokenize the full text
    tokenized = tokenizer(
        full_text,
        truncation=True,
        max_length=max_seq_length,
        padding="max_length",
    )
    # tokenized = tokenizer(full_text)

    # Tokenize only the prompt to determine its length
    prompt_length = len(tokenizer(prompt)["input_ids"])

    # Copy the tokenized input_ids to labels
    labels = tokenized["input_ids"].copy()

    # Set the prompt tokens to -100 to mask them during loss computation
    labels[:prompt_length] = [-100] * prompt_length
    tokenized["labels"] = labels
    return tokenized


def format_dataset2(example):
    # Construct the prompt and full text
    prompt = f"input: \n{example['input']} \noutput: \n"
    full_text = prompt + example["output"]
    return {"text": full_text}


def print_sequence_lengths(tokenized_dataset):
    # to use this this line in format_dataset() needs to be replaced
    # tokenized = tokenizer(full_text, truncation=True, max_length=max_seq_length, padding="max_length")
    # tokenized = tokenizer(full_text)

    seq_lengths = [len(example["input_ids"]) for example in tokenized_dataset]
    print(f"The max sequence length in the dataset is {max(seq_lengths)}")
    print(f"The min sequence length in the dataset is {min(seq_lengths)}")
    print(f"The mean sequence length in the dataset is {sum(seq_lengths)/len(seq_lengths)}")

    for i in range(1, 16):
        v = 2**i
        count = sum(1 for l in seq_lengths if l > v)
        print(f"Items with token length greater than {v}: {count}")


def main():

    dataset = load_dataset("json", data_files=str(CTSSB_TRAINING_DATASET), split="train")
    dataset = dataset.filter(filter_long_entry, load_from_cache_file=True)
    # dataset2 = dataset.map(format_dataset2, batched=False)

    tokenized_dataset = dataset.map(format_dataset, batched=False, load_from_cache_file=True)
    # tokenized_dataset = dataset.map(format_dataset_batched, batched=True, load_from_cache_file=True)
    # tokenized_dataset = tokenized_dataset.select(range(100))

    # print_sequence_lengths(tokenized_dataset)
    # return

    # QLoRA configuration
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float32,
    )

    # Load base model
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        trust_remote_code=True,
        use_cache=True,
        device_map="cuda:0",
    )
    print(f"Model memory usage after applying BitsAndBytesConfig = {model.get_memory_footprint() / 1e6} MB")

    # Load LoRA configuration
    peft_config = LoraConfig(
        r=64,
        lora_alpha=64 * 2,  # multiplier, usually 2*r
        bias="none",
        lora_dropout=0.05,
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "kv_a_proj_with_mqa",
            "kv_b_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )
    model = peft.prepare_model_for_kbit_training(model)
    model = peft.get_peft_model(model, peft_config)
    print(f"Model memory usage after applying LoraConfig = {model.get_memory_footprint() / 1e6} MB")

    # Set training parameters
    training_arguments = SFTConfig(
        ## GROUP 1: Memory usage
        # These arguments will squeeze the most out of your GPU's RAM
        # Checkpointing
        gradient_checkpointing=True,  # this saves a LOT of memory
        # Set this to avoid exceptions in newer versions of PyTorch
        gradient_checkpointing_kwargs={"use_reentrant": False},
        # Gradient Accumulation / Batch size
        # Actual batch (for updating) is same (1x) as micro-batch size
        gradient_accumulation_steps=1,
        # The initial (micro) batch size to start off with
        per_device_train_batch_size=4,
        # If batch size would cause OOM, halves its size until it works
        auto_find_batch_size=False,
        ## GROUP 2: Dataset-related
        max_seq_length=max_seq_length,
        # Dataset
        # packing a dataset means no padding is needed
        packing=False,
        # matches tokenized["labels"] = labels
        label_names=["labels"],
        ## GROUP 3: These are typical training parameters
        num_train_epochs=10,
        learning_rate=3e-4,
        # Optimizer
        # 8-bit Adam optimizer - doesn't help much if you're using LoRA!
        optim="paged_adamw_8bit",
        ## GROUP 4: Logging parameters
        logging_steps=10,
        logging_dir="./logs",
        output_dir=model_dir,
        report_to="tensorboard",
    )

    # Set supervised fine-tuning parameters
    trainer = SFTTrainer(
        model=model,
        train_dataset=tokenized_dataset,
        args=training_arguments,
        tokenizer=tokenizer,
    )

    print(f"Model is using {model.get_memory_footprint() / 1e6} MB of memory")
    print("Final per-device train batch size:", trainer.args.per_device_train_batch_size)

    print("******************************************************")
    print("*************** Starting Fine tuning *****************")
    print("******************************************************")
    trainer.train()
    if int(os.environ.get("LOCAL_RANK", 0)) == 0:
        trainer.model.save_pretrained(pathlib.Path(model_dir, new_model))


if __name__ == "__main__":
    main()
