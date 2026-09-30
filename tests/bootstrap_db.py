"""Создает тестовую БД, если ее нет:  python -m tests.bootstrap_db"""

import asyncio
import os

import asyncpg


async def main() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    head, _, name = url.rpartition("/")
    connection = await asyncpg.connect(f"{head}/postgres")
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{name}"')
            print(f"Создана тестовая БД {name}")
    finally:
        await connection.close()


if __name__ == "__main__":
    import tests.conftest  # noqa: F401  — выставляет DATABASE_URL тестовой БД

    asyncio.run(main())
