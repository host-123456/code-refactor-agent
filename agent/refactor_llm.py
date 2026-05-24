"""
refactor_llm.py
Stage 2: Feed debt manifest to Claude and generate refactor patches.
Uses multi-turn context to keep cross-file edits consistent.
"""
import json
import logging
from pathlib import Path
from typing import Any

import anthropic
import yaml

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert software engineer specializing in code refactoring and quality improvement.

Given a list of technical debt items, you will:
1. Decide if each item can be auto-fixed (set "auto_fixable": true/false)
2. For auto-fixable items, produce the refactored code
3. Provide a clear change rationale, impact scope, and rollback notes

Respond ONLY with a valid JSON array. Each element must have:
{
  "debt_index": <int>,
  "auto_fixable": <bool>,
  "title": "<short PR title>",
  "rationale": "<why this change>",
  "impact_scope": "<affected modules>",
  "rollback": "<how to revert>",
  "original_code": "<snippet>",
  "refactored_code": "<snippet or null if not auto_fixable>",
  "risk": "low|medium|high"
}

If not auto_fixable, set refactored_code to null and explain in rationale why human review is needed.
Do not include any text outside the JSON array."""


class RefactorLLM:
    def __init__(self, cfg):
        self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        self.model = cfg.model
        self.arch_spec = self._load_arch_spec(cfg.arch_spec_path)

    def _load_arch_spec(self, path: str) -> str:
        p = Path(path)
        if p.exists():
            return p.read_text()
        return "No architecture spec provided. Use general Python best practices."

    def generate_patches(self, debt_manifest: list[dict]) -> list[dict]:
        """Send debt manifest to Claude and return structured patches."""
        # Group into batches of 20 to stay within context limits
        patches = []
        batch_size = 20
        for i in range(0, len(debt_manifest), batch_size):
            batch = debt_manifest[i:i + batch_size]
            patches.extend(self._process_batch(batch, i))
        return [p for p in patches if p.get("auto_fixable")]

    def _process_batch(self, batch: list[dict], offset: int) -> list[dict]:
        user_message = f"""Architecture spec:
{self.arch_spec}

Technical debt items to refactor (items {offset} to {offset + len(batch) - 1}):
{json.dumps(batch, indent=2)}

Generate refactoring patches for all items above."""

        messages = [{"role": "user", "content": user_message}]

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            raw = response.content[0].text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            patches = json.loads(raw)
            log.info(f"Batch {offset}: Claude returned {len(patches)} patch proposals")
            return patches
        except (json.JSONDecodeError, anthropic.APIError) as e:
            log.error(f"LLM batch {offset} failed: {e}")
            return []
