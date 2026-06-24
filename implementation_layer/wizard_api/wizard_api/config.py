import os

from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    return os.getenv(
        "WIZARD_DATABASE_URL",
        "postgresql+psycopg://wizard:wizard@localhost:5432/wizard",
    )
