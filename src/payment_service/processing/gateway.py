import asyncio
import random
from collections.abc import Awaitable, Callable


async def simulate_gateway(
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    uniform: Callable[[float, float], float] = random.uniform,
    random_value: Callable[[], float] = random.random,
) -> bool:
    await sleep(uniform(2, 5))
    return random_value() < 0.9
