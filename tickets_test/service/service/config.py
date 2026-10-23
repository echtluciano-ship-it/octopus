from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ["TICKETS_DATABASE_URL"]
    webhook_token: str = os.environ["TICKETS_WEBHOOK_TOKEN"]
    object_store_path: Path = Path(os.getenv("TICKETS_OBJECT_STORE_PATH", "/objects"))
    accounts_path: Path = Path(os.getenv("TICKETS_ACCOUNTS_PATH", "/run/config/tickets.accounts.json"))
    accept_all_test_groups: bool = _bool("TICKETS_ACCEPT_ALL_TEST_GROUPS")
    allowed_group_ids: tuple[str, ...] = tuple(
        value.strip() for value in os.getenv("TICKETS_ALLOWED_GROUP_IDS", "").split(",") if value.strip()
    )
    export_dir: Path = Path(os.getenv("TICKETS_EXPORT_DIR", "/exports"))
    gmail_credentials_path: Path = Path(
        os.getenv("TICKETS_GMAIL_CREDENTIALS_PATH", "/run/gmail/credentials.json")
    )
    gmail_token_path: Path = Path(
        os.getenv("TICKETS_GMAIL_TOKEN_PATH", "/run/gmail/token.json")
    )
    gmail_attachment_root: Path = Path(
        os.getenv("TICKETS_GMAIL_ATTACHMENT_ROOT", "/mail-packages")
    )
    gmail_allowed_recipients: tuple[str, ...] = tuple(
        value.strip().lower()
        for value in os.getenv(
            "TICKETS_GMAIL_ALLOWED_RECIPIENTS", "oficinaoctopus13@gmail.com"
        ).split(",")
        if value.strip()
    )

    def account_config(self) -> dict:
        return json.loads(self.accounts_path.read_text(encoding="utf-8"))


settings = Settings()
