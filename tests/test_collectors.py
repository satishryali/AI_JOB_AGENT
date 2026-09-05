from src.collectors.base import BaseCollector
from src.collectors.runner import run_collectors
from src.models.job import NormalizedJob


class OkCollector(BaseCollector):
    name = "ok"

    async def collect(self, keywords, locations, max_results):
        return [
            NormalizedJob(source="ok", external_job_id="1", title="Python", company="A"),
        ]


class BoomCollector(BaseCollector):
    name = "boom"

    async def collect(self, keywords, locations, max_results):
        raise RuntimeError("source exploded")


async def test_collector_failure_isolation():
    jobs, results, _dupes = await run_collectors(
        ["python"],
        ["remote"],
        10,
        collectors=[BoomCollector(), OkCollector()],
    )
    assert len(jobs) == 1
    assert jobs[0].source == "ok"
    boom = next(r for r in results if r.source == "boom")
    assert boom.error
    assert not boom.jobs
