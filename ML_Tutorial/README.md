# ML Tutorial — Fine-Tuning LLMs with LoRA and QLoRA

Course tutorial submission: a written document plus the runnable code it describes.

| File | Type | Purpose |
|---|---|---|
| `Fine_Tuning_LLMs_Tutorial.md` | Written document | Complete tutorial — concepts, memory arithmetic, code, interpretation, exercises, references |
| `finetuning_tutorial.ipynb` | Runnable code | The same code as an executable Colab/Jupyter notebook |

## Running the notebook

1. Open `finetuning_tutorial.ipynb` in Google Colab.
2. *Runtime → Change runtime type → **T4 GPU***.
3. Run the cells in order. Everything fits on the free 16 GB tier — no paid compute, no API keys, no private data.

Expect roughly 20–40 minutes end to end: install (2–5 min), model download and quantization (1–3 min), training on
2,000 examples for 1 epoch (10–25 min), evaluation and generation (3–5 min). To go faster, change the dataset slice in
Cell 4 from `train[:2000]` to `train[:500]`.

It also runs locally on any NVIDIA GPU with ≥8 GB VRAM.

## What it covers

- When to fine-tune versus prompt, retrieve, or use tools
- Continued pretraining vs. supervised fine-tuning (objectives) vs. full FT / LoRA / QLoRA (methods)
- The memory arithmetic that predicts whether a job will fit, before you launch it
- An end-to-end QLoRA fine-tune of Qwen2.5-1.5B-Instruct on Alpaca-cleaned
- Reading loss curves, choosing checkpoints, evaluating against the un-tuned baseline
- Saving, merging, and deploying an adapter; common pitfalls; eight exercises

## Notes

- **Version drift** is the usual reason fine-tuning tutorials stop running. The notebook detects the installed TRL API
  at runtime (Cell 5), and Appendix B lists the renames explicitly.
- **T4s do not support bfloat16.** Cell 2 detects this once and the training config uses it everywhere.
- Model and dataset licensing is covered in §19 of the written document — the Alpaca lineage carries non-commercial
  restrictions inherited from its origin.
