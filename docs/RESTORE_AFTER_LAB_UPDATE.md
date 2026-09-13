# Restore and resume after the lab update

Checkpoint: September 13, 2026. Repository: https://github.com/sreejamuvva2002/Certification_status
Branch: `Tariffs-data`. Research outputs were pushed in commit `38afdf7`.

## Restore the project

```bash
git clone --branch Tariffs-data https://github.com/sreejamuvva2002/Certification_status.git
cd Certification_status
python3 -m venv outputs/tariffs/runtime-venv
outputs/tariffs/runtime-venv/bin/pip install -r requirements-tariffs.txt
```

Keep the original `/home/sm11926/Certification_status` path if practical: evidence records contain absolute source paths. On a different path, preserve originals and adapt path resolution rather than silently rewriting historical evidence.
The `.env` credentials are intentionally excluded from Git. Restore them separately from a private backup; never commit them. The installed local model was `qwen3.5:35b-a3b` on Ollama. The model weights, Ollama executable, and virtual environment are not backed up by Git. Preserve the lab home directory/model storage if reinstalling would be costly.

## Recover the conversation

The local Codex installation has session history under `/home/sm11926/.codex/sessions` (42 session JSONL files at checkpoint), plus configuration and SQLite state under `/home/sm11926/.codex`. Preserve this directory privately on another machine before a disk reset. It includes sensitive chat content and authentication information and must not be pushed to GitHub. A Git clone alone does not restore this chat.

After restoring the private Codex state with Codex/its extension closed, reopen the same project. The installed CLI supports:

```bash
codex resume --all
# Or: codex resume SESSION_ID
```

Use the picker to select the tariff-research conversation. Restoring the same Codex version and paths may help; IDE history recovery across versions is not guaranteed. Sign in again if necessary. Official guidance: https://learn.chatgpt.com/docs/codex/cli

No private chat/credential archive was created by the assistant: automatic approval review rejected that action pending explicit authorization of a private destination. Copying the project to GitHub does not remove this outstanding backup requirement.

## Research state and next task

- Original 510-query run complete: `outputs/tariffs/pilot-2026-09-09/`.
- Audits v1/v2 preserved: `outputs/tariffs/quality-audit-v1-2026-09-10/` and `quality-audit-v2-2026-09-10/`.
- Company run complete: 193 companies, 205 seed rows, 406 queries, 412 source URLs, 556 chunks, 1,889 new claims.
- Company budget: 500 cumulative Tavily credits approved; 406 conservatively accounted, 396 provider-reported. At most 94 remain, including retries. Baseline credits are a separate historical budget.
- Reviewed company update: `outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12/`. Seven companies have source-reported effects; 12 have responses/opinions. 327 query answers remain insufficient evidence. No current company/facility duty liabilities verified. 57 tariff tests passed before recovery work.
- User authorized additional gap recovery. This is NOT complete. Preserve every earlier output.
- Recovery draft: `scripts/recover_company_tariff_gaps.py`; outputs in `outputs/tariffs/company-research-2026-09-10/recovery-v2-2026-09-12/`.
- Completed recovery discovery: 1,275 documents scanned across all 193 companies; 184 names have text matches; 5,199 discovery windows saved, 754 selected for model review. Matches are NOT validated company tariff findings. The model review and focused new searches have not run. No recovery process was running at this checkpoint.
- Recovery script currently supports prepare, review-local, scan-final and review-final. New web retrieval orchestration and final versioned report exports still need implementation and tests. Do not assume this draft completes the whole workflow. Recheck research dates, which are currently hardcoded to September 12.
- Prioritize full cached texts and verified company identity/product links. Keep parent/group matches provisional. Then use focused primary-source company/customs searches within the cumulative budget. Do not infer tariff rates or exposure from seed products or generic policy.
- No new Tavily calls were made during the interrupted recovery turn. Recheck the actual ledgers before spending. Keep secrets out of logs and Git.

## Prompt for a new chat if history is unavailable

> Read docs/RESTORE_AFTER_LAB_UPDATE.md, docs/company_tariff_research.md, docs/tariff_research_brief.md, and the latest recovery outputs. Resume the authorized company tariff evidence recovery. Preserve original outputs. Review the recovery script before running it; it is incomplete. Use installed local Qwen, start with cached full texts, then focused searches within the previously approved 500-credit cumulative company budget. Do not repeat completed paid searches or claim that name matches are verified tariff findings.
