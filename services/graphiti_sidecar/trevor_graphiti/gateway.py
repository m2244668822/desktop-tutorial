from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any


def _serialize(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    public = {
        key: _serialize(item)
        for key, item in vars(value).items()
        if not str(key).startswith('_')
    } if hasattr(value, '__dict__') else {}
    return public or str(value)


def _reference_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class GraphitiGateway:
    def __init__(self, graphiti: Any, *, query_concurrency: int = 1):
        self.graphiti = graphiti
        self._query_semaphore = asyncio.Semaphore(max(1, min(2, int(query_concurrency))))
        self._write_lock = asyncio.Lock()

    async def _episode_exists(self, name: str, group_id: str) -> bool:
        driver = getattr(self.graphiti, 'driver', None)
        if driver is None:
            return False
        records, _, _ = await driver.execute_query(
            """
            MATCH (episode:Episodic {name: $name, group_id: $group_id})
            RETURN episode.uuid AS uuid
            LIMIT 1
            """,
            name=str(name or '')[:200],
            group_id=str(group_id or 'trevor'),
            routing_='r',
        )
        return bool(records)

    async def health(self) -> dict[str, Any]:
        async with self._query_semaphore:
            await self.graphiti.driver.health_check()
        return {'ok': True, 'database': 'falkordb', 'private': True}

    async def search(
        self,
        query: str,
        *,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[Any]:
        async with self._query_semaphore:
            result = await self.graphiti.search(
                str(query or '').strip(),
                group_ids=group_ids,
                num_results=max(1, min(50, int(limit))),
            )
        return _serialize(result)

    async def add_episode(
        self,
        *,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: str | datetime,
        episode_uuid: str,
        group_id: str = 'trevor',
    ) -> Any:
        async with self._write_lock:
            if await self._episode_exists(name, group_id):
                return {
                    'ok': True,
                    'duplicate': True,
                    'idempotency_key': str(episode_uuid),
                }
            result = await self.graphiti.add_episode(
                name=str(name or '')[:200],
                episode_body=str(episode_body or ''),
                source_description=str(source_description or '')[:300],
                reference_time=_reference_time(reference_time),
                group_id=str(group_id or 'trevor'),
                update_communities=False,
            )
        return _serialize(result)


__all__ = ['GraphitiGateway']
