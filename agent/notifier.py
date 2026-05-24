"""
notifier.py
Send Slack alerts when the Agent needs human intervention.
Includes Claude's root-cause analysis in the message.
"""
import json
import logging
import urllib.request

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, cfg):
        self.webhook_url = cfg.slack_webhook_url

    def alert_human(self, patch: dict, pr_url: str):
        """Send a Slack message with patch details and PR link."""
        if not self.webhook_url:
            log.warning("SLACK_WEBHOOK_URL not set, skipping notification.")
            return

        message = {
            "text": ":robot_face: *Code Refactor Agent — Human Review Required*",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🤖 Agent needs your help"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*PR Title:*\n{patch.get('title', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*Risk Level:*\n{patch.get('risk', 'unknown')}"},
                        {"type": "mrkdwn", "text": f"*Rationale:*\n{patch.get('rationale', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*Impact Scope:*\n{patch.get('impact_scope', 'N/A')}"},
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"CI failed after {3} auto-retry attempts. Manual review needed.\n<{pr_url}|View PR on GitHub>"
                    }
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Sent by code-refactor-agent · auto-generated"}]
                }
            ]
        }

        try:
            data = json.dumps(message).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                log.info(f"Slack notification sent. Status: {resp.status}")
        except Exception as e:
            log.error(f"Slack notification failed: {e}")
