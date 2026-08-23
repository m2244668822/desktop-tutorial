from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.ai_horde_assets import AIHordeAssetError, AIHordeAssetStore
from core.ai_horde_client import AIHordeClient, AIHordeError, validate_horde_request
from core.trevor_identity import TREVOR_AGENT_ID, TREVOR_DISPLAY_NAME


class AIHordeJobManager:
    def __init__(
        self,
        client: AIHordeClient,
        assets: AIHordeAssetStore,
        *,
        executor: Any | None = None,
        sleep: Any = time.sleep,
        clock: Any = time.monotonic,
        max_concurrent: int = 2,
        max_queued: int = 8,
        timeout_seconds: float = 600,
    ):
        self.client = client
        self.assets = assets
        self.executor = executor or ThreadPoolExecutor(
            max_workers=max_concurrent, thread_name_prefix='trevor-ai-horde'
        )
        self.sleep = sleep
        self.clock = clock
        self.max_concurrent = max(1, int(max_concurrent))
        self.max_queued = max(0, int(max_queued))
        self.timeout_seconds = max(1, float(timeout_seconds))
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_horde_request(payload)
        with self._lock:
            self._expire_finished_unlocked()
            inflight = sum(
                job['state'] in {'queued', 'running'} for job in self._jobs.values()
            )
            if inflight >= self.max_concurrent + self.max_queued:
                raise AIHordeError('queue_full', retryable=True)
            job_id = str(uuid.uuid4())
            self._jobs[job_id] = {
                'job_id': job_id,
                'kind': normalized['kind'],
                'prompt': normalized['prompt'],
                'params': normalized['params'],
                'state': 'queued',
                'created_at': time.time(),
                'updated_at': time.time(),
                'queue_position': max(0, inflight - self.max_concurrent + 1),
                'wait_time': 0,
                'result': {},
            }
        self.executor.submit(self._run_job, job_id)
        return {'ok': True, 'job_id': job_id, 'state': 'queued', 'poll_after_ms': 2000}

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job['state'] = 'running'
            job['updated_at'] = time.time()
            kind = job['kind']
            prompt = job['prompt']
            params = dict(job['params'])
        try:
            provider_id = self.client.submit(kind, prompt, params)
            deadline = self.clock() + self.timeout_seconds
            interval = 2.0
            while self.clock() < deadline:
                status = self.client.status(kind, provider_id)
                if bool(status.get('faulted')):
                    raise AIHordeError('provider_rejected')
                if bool(status.get('done')):
                    self._complete_job(job_id, kind, params, status)
                    return
                with self._lock:
                    current = self._jobs.get(job_id)
                    if current:
                        current['queue_position'] = int(status.get('queue_position', 0) or 0)
                        current['wait_time'] = int(status.get('wait_time', 0) or 0)
                        current['updated_at'] = time.time()
                self.sleep(interval)
                interval = min(5.0, interval + 0.5)
            raise AIHordeError('job_timeout', retryable=True)
        except AIHordeAssetError:
            self._fail_job(job_id, AIHordeError('asset_fetch_failed', retryable=True))
        except AIHordeError as exc:
            self._fail_job(job_id, exc)
        except Exception:
            self._fail_job(job_id, AIHordeError('provider_unavailable', retryable=True))

    def _complete_job(
        self,
        job_id: str,
        kind: str,
        params: dict[str, Any],
        status: dict[str, Any],
    ) -> None:
        generations = status.get('generations', [])
        if not isinstance(generations, list) or not generations:
            raise AIHordeError('provider_unavailable', retryable=True)
        if kind == 'image':
            remote_url = str(generations[0].get('img', '') or '')
            asset = self.assets.save_remote(remote_url)
            asset['width'] = int(params.get('width', 512))
            asset['height'] = int(params.get('height', 512))
            result = {
                'reply': '圖片生成完成。',
                'images': [asset],
                'interaction_mode': 'image_generation',
            }
        else:
            reply = str(generations[0].get('text', '') or '').strip()
            if not reply:
                raise AIHordeError('provider_unavailable', retryable=True)
            result = {'reply': reply, 'images': [], 'interaction_mode': 'horde_text'}
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job['state'] = 'complete'
                job['result'] = result
                job['updated_at'] = time.time()
                job.pop('prompt', None)
                job.pop('params', None)

    def _fail_job(self, job_id: str, error: AIHordeError) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job['state'] = 'failed'
                job['result'] = {'error': error.public_dict()}
                job['updated_at'] = time.time()
                job.pop('prompt', None)
                job.pop('params', None)

    def _expire_finished_unlocked(self) -> None:
        now = time.time()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job['state'] in {'complete', 'failed'}
            and now - float(job.get('updated_at', now)) > 60 * 60
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._expire_finished_unlocked()
            job = self._jobs.get(str(job_id or ''))
            if not job:
                raise AIHordeError('job_not_found')
            result = {
                'ok': job['state'] != 'failed',
                'job_id': job['job_id'],
                'state': job['state'],
                'agent': TREVOR_AGENT_ID,
                'role': TREVOR_DISPLAY_NAME,
                'backend': 'ai_horde',
                'poll_after_ms': 2000 if job['state'] == 'queued' else 3000,
            }
            if job['state'] in {'queued', 'running'}:
                result['queue_position'] = int(job.get('queue_position', 0))
                result['wait_time'] = int(job.get('wait_time', 0))
            result.update(dict(job.get('result') or {}))
            return result


__all__ = ['AIHordeJobManager']
