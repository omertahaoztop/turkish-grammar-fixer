"""LoRA eğitimi; yalnız eğitim ortamında (torch + peft) çalışır: python -m tdk.lora <hf-temel> <train.jsonl> <çıktı-dizini>."""

import json
import random
import sys

import torch
from accelerate import init_empty_weights
from peft import LoraConfig, get_peft_model
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

MAX_LEN, BATCH, ACCUM, LR, EPOCHS = 384, 4, 4, 1e-4, 1


def encode(tok, row: dict) -> tuple[list[int], list[int]]:
    prompt = tok.apply_chat_template(row["messages"][:-1], tokenize=False, add_generation_prompt=True)
    answer = row["messages"][-1]["content"] + (tok.eos_token or "")
    p = tok(prompt, add_special_tokens=False)["input_ids"]
    a = tok(answer, add_special_tokens=False)["input_ids"]
    ids = (p + a)[:MAX_LEN]
    # Kayıp yalnız cevap kısmında hesaplanır; model istemi ezberlemez.
    labels = ([-100] * len(p) + a)[:MAX_LEN]
    return ids, labels


def device_map(base: str) -> dict:
    """Katman başı gömme tabloları (Gemma E serisi, ~2.8B parametre) CPU'da kalır; geri kalanı 16 GB GPU'ya sığar."""
    with init_empty_weights():
        meta = AutoModelForCausalLM.from_config(AutoConfig.from_pretrained(base))
    cpu = [n for n, _ in meta.named_modules() if n.endswith("embed_tokens_per_layer")]
    out = {}

    def walk(mod, prefix):
        for name, child in mod.named_children():
            full = prefix + name
            if full in cpu:
                out[full] = "cpu"
            elif any(c.startswith(full + ".") for c in cpu):
                walk(child, full + ".")
            else:
                out[full] = 0
    walk(meta, "")
    return out


def main(base: str, data: str, out: str):
    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16, device_map=device_map(base))
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    # Görüntü/ses kulelerine adaptör eklenmez; GGUF dönüştürücü yalnız dil modeli tensörlerini tanır.
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=r"^(?!.*(vision|audio)).*\.(q|k|v|o)_proj$"))
    model.print_trainable_parameters()
    with open(data, encoding="utf-8") as f:
        rows = [encode(tok, json.loads(line)) for line in f]
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR)
    steps = EPOCHS * len(rows) // (BATCH * ACCUM)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / 10) * max(0.0, 1 - s / max(steps, 1)))
    pad = tok.pad_token_id if tok.pad_token_id is not None else 0
    model.train()
    step = 0
    for _ in range(EPOCHS):
        random.shuffle(rows)
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            n = max(len(ids) for ids, _ in batch)
            ids = torch.tensor([x + [pad] * (n - len(x)) for x, _ in batch], device=0)
            lab = torch.tensor([y + [-100] * (n - len(y)) for _, y in batch], device=0)
            att = torch.tensor([[1] * len(x) + [0] * (n - len(x)) for x, _ in batch], device=0)
            loss = model(input_ids=ids, attention_mask=att, labels=lab).loss / ACCUM
            loss.backward()
            if (i // BATCH + 1) % ACCUM == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
                step += 1
                if step % 10 == 0:
                    print(f"adım {step}/{steps} kayıp {loss.item() * ACCUM:.4f}", flush=True)
    model.save_pretrained(out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
