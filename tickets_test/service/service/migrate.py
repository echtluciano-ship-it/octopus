from __future__ import annotations

from pathlib import Path

from service.db import connection


def main() -> None:
    migrations = Path(__file__).with_name("migrations")
    with connection() as conn:
        for path in sorted(migrations.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
        conn.commit()
    print("Tickets migrations applied")


if __name__ == "__main__":
    main()
