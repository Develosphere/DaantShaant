"""Create a controlled PostgreSQL-backed admin account.

Run manually from the repository root. The password is requested without echo
and is never printed or stored outside its Argon2id hash.
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT / "orchestrator" / "src"))

from orchestrator.db.models import User  # noqa: E402
from orchestrator.db.session import async_session_factory  # noqa: E402
from orchestrator.dentist_portal.auth import hash_password  # noqa: E402
from orchestrator.repositories import UserRepository  # noqa: E402


async def create_admin(email: str, first_name: str, last_name: str) -> None:
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Admin password must contain at least 12 characters")

    async with async_session_factory() as session:
        async with session.begin():
            repository = UserRepository(session)
            if await repository.get_by_email(email):
                raise SystemExit("An account with that email already exists")
            user = await repository.add(
                User(
                    email=email.strip().lower(),
                    password_hash=hash_password(password),
                    role="admin",
                    first_name=first_name.strip(),
                    last_name=last_name.strip(),
                )
            )
    print(f"Created admin account {user.id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    args = parser.parse_args()
    asyncio.run(create_admin(args.email, args.first_name, args.last_name))


if __name__ == "__main__":
    main()
