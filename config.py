import os
from dataclasses import dataclass


@dataclass
class Config:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    max_tokens_per_day: int = int(os.getenv("MAX_TOKENS_PER_DAY", "5000000"))
    retry_limit: int = int(os.getenv("RETRY_LIMIT", "3"))
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    arch_spec_path: str = os.getenv("ARCH_SPEC_PATH", "rules/arch_spec.yaml")
    debt_rules_path: str = os.getenv("DEBT_RULES_PATH", "rules/debt_rules.yaml")
    model: str = "claude-opus-4-5"

    def validate(self):
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is not set")
