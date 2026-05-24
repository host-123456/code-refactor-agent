"""
test_runner.py
Stage 4: Trigger CI, watch for failures, and retry patching up to N times.
Uses Claude to read error logs and generate fix patches.
"""
import logging
import time

import anthropic
from github import Github

log = logging.getLogger(__name__)

FIX_PROMPT = """A CI pipeline failed after an automated code refactoring PR. 
Analyze the error log and suggest a minimal fix patch.

Original patch title: {title}
Error log:
{error_log}

Respond with a JSON object:
{{
  "root_cause": "<one sentence>",
  "fix_description": "<what to change>",
  "fix_code": "<code snippet to apply, or null if human review needed>",
  "confidence": "low|medium|high"
}}
Only respond with the JSON object, no other text."""


class TestRunner:
    def __init__(self, repo: str, cfg):
        self.repo_name = repo
        self.cfg = cfg
        self.gh = Github(cfg.github_token)
        self.repo = self.gh.get_repo(repo)
        self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        self.model = cfg.model
        self.max_retries = cfg.retry_limit

    def run_and_retry(self, patch: dict, max_retries: int = 3) -> bool:
        """
        Wait for CI checks on the PR branch and retry on failure.
        Returns True if CI passes, False if all retries exhausted.
        """
        branch = self._get_branch_name(patch["title"])
        for attempt in range(max_retries + 1):
            log.info(f"CI check attempt {attempt + 1}/{max_retries + 1} for branch: {branch}")
            status, error_log = self._wait_for_ci(branch)

            if status == "success":
                log.info("CI passed.")
                return True

            if attempt == max_retries:
                log.warning(f"All {max_retries} retries exhausted.")
                return False

            log.warning(f"CI failed. Asking Claude for a fix (attempt {attempt + 1})...")
            fix = self._generate_fix(patch["title"], error_log)
            if not fix or fix.get("confidence") == "low" or not fix.get("fix_code"):
                log.warning("Claude could not generate a confident fix. Escalating.")
                return False

            self._apply_fix_to_branch(branch, fix, patch.get("target_file", ""))
            time.sleep(10)  # Give CI time to pick up the new push

        return False

    def _get_branch_name(self, title: str) -> str:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
        return f"agent/refactor-{slug}"

    def _wait_for_ci(self, branch: str, timeout: int = 300, poll: int = 15) -> tuple[str, str]:
        """Poll GitHub commit status until pass/fail or timeout."""
        elapsed = 0
        while elapsed < timeout:
            try:
                commit = self.repo.get_branch(branch).commit
                statuses = list(commit.get_statuses())
                check_runs = list(commit.get_check_runs())

                # Aggregate results
                all_checks = [(s.state, "") for s in statuses] + \
                             [(r.conclusion or "pending", r.output.text or "") for r in check_runs]

                if not all_checks:
                    log.info("No CI checks found yet, waiting...")
                elif all(s in ("success", "neutral") for s, _ in all_checks):
                    return "success", ""
                elif any(s in ("failure", "error") for s, _ in all_checks):
                    failed = next((log_text for s, log_text in all_checks if s in ("failure", "error")), "")
                    return "failure", failed
            except Exception as e:
                log.warning(f"Error polling CI: {e}")

            time.sleep(poll)
            elapsed += poll

        return "timeout", "CI timed out after waiting."

    def _generate_fix(self, title: str, error_log: str) -> dict | None:
        import json
        prompt = FIX_PROMPT.format(title=title, error_log=error_log[:3000])
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            return json.loads(raw)
        except Exception as e:
            log.error(f"Fix generation failed: {e}")
            return None

    def _apply_fix_to_branch(self, branch: str, fix: dict, target_file: str):
        """Push a fix commit directly via GitHub API (contents endpoint)."""
        if not target_file or not fix.get("fix_code"):
            return
        try:
            contents = self.repo.get_contents(target_file, ref=branch)
            current_code = contents.decoded_content.decode()
            # Append fix as a comment block for human review (safe approach)
            updated = current_code + f"\n# AGENT FIX ({fix['root_cause']}):\n# {fix['fix_description']}\n"
            self.repo.update_file(
                path=target_file,
                message=f"fix(agent): attempt auto-fix - {fix['root_cause']}",
                content=updated,
                sha=contents.sha,
                branch=branch,
            )
            log.info(f"Fix commit pushed to branch: {branch}")
        except Exception as e:
            log.error(f"Failed to push fix commit: {e}")
