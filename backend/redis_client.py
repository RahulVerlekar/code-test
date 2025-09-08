import asyncio
from collections import defaultdict

class MockRedis:
    def __init__(self):
        self.store = {}
        self.expiry = defaultdict(lambda: None)

    async def set(self, key, value):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key, None)

    async def expire(self, key, seconds):
        if key in self.store:
            self.expiry[key] = asyncio.get_event_loop().time() + seconds

    async def delete(self, key):
        if key in self.store:
            del self.store[key]
            if key in self.expiry:
                del self.expiry[key]

    async def check_expiry(self):
        """Simulates expiry cleanup. Call periodically in tests if needed."""
        now = asyncio.get_event_loop().time()
        expired_keys = [k for k, exp in self.expiry.items() if exp and exp < now]
        for k in expired_keys:
            await self.delete(k)

# Usage: Swap out the real redis client with MockRedis
redis_client = MockRedis()

async def add_key_value_redis(key, value, expire=None):
    await redis_client.set(key, value)
    if expire:
        await redis_client.expire(key, expire)

async def get_value_redis(key):
    await redis_client.check_expiry()
    return await redis_client.get(key)

async def delete_key_redis(key):
    await redis_client.delete(key)
