"""Track live chat tasks so Reset can stop them before clearing state."""

import asyncio
from autogen_core import CancellationToken

active_chat_tasks: dict[asyncio.Task, CancellationToken | None] = {}


async def stop_chat_tasks():
    tasks = list(active_chat_tasks)
    for task in tasks:
        token = active_chat_tasks.get(task)
        if token is not None:
            token.cancel()
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    for task in tasks:
        active_chat_tasks.pop(task, None)
