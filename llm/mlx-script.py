#!/usr/bin/env python3

from mlx_lm import generate, load

model_name = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
prompt = "Write a hello world function in Haskell"

model, tokenizer = load(model_name)  # type: ignore

response = generate(model, tokenizer, prompt=prompt, verbose=True)
print(response)
