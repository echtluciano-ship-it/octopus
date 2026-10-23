from __future__ import annotations

import os

from service.config import settings
from service.gmail import GMAIL_SEND_SCOPE


def main() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials_path = settings.gmail_credentials_path
    if not credentials_path.is_file():
        raise SystemExit(f"Missing OAuth client file: {credentials_path}")
    settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path), scopes=[GMAIL_SEND_SCOPE]
    )
    credentials = flow.run_local_server(
        host="localhost",
        bind_addr="0.0.0.0",
        port=8765,
        open_browser=False,
        authorization_prompt_message="Open this URL in your browser:\n{url}",
        success_message="OCTOPUS Tickets: Gmail authorization completed. You can close this tab.",
    )
    settings.gmail_token_path.write_text(credentials.to_json(), encoding="utf-8")
    try:
        os.chmod(settings.gmail_token_path, 0o600)
    except OSError:
        pass
    print(f"Gmail token saved: {settings.gmail_token_path}")


if __name__ == "__main__":
    main()
