"""Pull committed history; clients own cursors, never backend execution."""
import asyncio
import json
from app.api.service import public


async def event_stream(service, project_id, cursor, disconnected, *, poll=0.1, keepalive=15):
    elapsed = 0.0
    while not await disconnected():
        # No queue or lock is held across yield/client IO. Replay in bounded batches.
        events = await asyncio.to_thread(service.store.event_page, project_id, cursor, 100)
        for event in events:
            if await disconnected():
                return
            cursor = event.sequence
            yield f'id: {cursor}\nevent: domain\ndata: {json.dumps(public(event), separators=(",", ":"))}\n\n'
            elapsed = 0
        if events:
            continue
        await asyncio.sleep(poll)
        elapsed += poll
        if elapsed >= keepalive:
            yield ': keepalive\n\n'
            elapsed = 0
