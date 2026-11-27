"""Two async pools: quarantine_proxy (writes) and memory_reader (recall). Not opened at import."""

from psycopg_pool import AsyncConnectionPool

from app.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        proxy_url = settings.DATABASE_URL_PROXY.get_secret_value()
        reader_url = settings.DATABASE_URL_READER.get_secret_value()
        self.proxy: AsyncConnectionPool | None = (
            AsyncConnectionPool(proxy_url, min_size=1, max_size=8, open=False, name="proxy")
            if proxy_url
            else None
        )
        self.reader: AsyncConnectionPool | None = (
            AsyncConnectionPool(reader_url, min_size=1, max_size=4, open=False, name="reader")
            if reader_url
            else None
        )

    @property
    def configured(self) -> bool:
        return self.proxy is not None and self.reader is not None

    async def open(self) -> None:
        for pool in (self.proxy, self.reader):
            if pool is not None:
                # wait=False: start even when the DB is down; /health reports it as degraded.
                await pool.open(wait=False)

    async def close(self) -> None:
        for pool in (self.proxy, self.reader):
            if pool is not None:
                await pool.close()

    async def ping(self) -> bool:
        if self.proxy is None:
            return False
        try:
            async with self.proxy.connection() as conn:
                await conn.execute("SELECT 1")
        except Exception:
            return False
        return True
