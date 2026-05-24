"""
code-refactor-agent
Entry point. Run with: python main.py --repo your-org/your-repo [--dry-run]
"""
import argparse
import logging
from agent.scanner import Scanner
from agent.refactor_llm import RefactorLLM
from agent.pr_publisher import PRPublisher
from agent.test_runner import TestRunner
from agent.notifier import Notifier
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def run(repo: str, dry_run: bool = False):
    cfg = Config()
    log.info(f"Starting refactor agent on repo: {repo} (dry_run={dry_run})")

    # Stage 1: Scan
    scanner = Scanner(repo, cfg)
    debt_manifest = scanner.scan()
    log.info(f"Scan complete. Found {len(debt_manifest)} debt items.")

    if not debt_manifest:
        log.info("No debt found. Exiting.")
        return

    # Stage 2: Generate refactor patches via Claude
    llm = RefactorLLM(cfg)
    patches = llm.generate_patches(debt_manifest)
    log.info(f"Generated {len(patches)} patches.")

    for patch in patches:
        if dry_run:
            log.info(f"[DRY RUN] Would submit PR for: {patch['title']}")
            continue

        # Stage 3: Submit PR
        publisher = PRPublisher(repo, cfg)
        pr_url = publisher.submit(patch)
        log.info(f"PR submitted: {pr_url}")

        # Stage 4: Run tests + retry loop
        runner = TestRunner(repo, cfg)
        success = runner.run_and_retry(patch, max_retries=3)

        if not success:
            notifier = Notifier(cfg)
            notifier.alert_human(patch, pr_url)
            log.warning(f"Human intervention needed for PR: {pr_url}")
        else:
            log.info(f"PR passed CI: {pr_url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated code refactor agent")
    parser.add_argument("--repo", required=True, help="GitHub repo in org/name format")
    parser.add_argument("--dry-run", action="store_true", help="Scan and generate patches without submitting PRs")
    args = parser.parse_args()
    run(args.repo, dry_run=args.dry_run)
