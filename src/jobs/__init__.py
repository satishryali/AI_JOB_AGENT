# Job processing module initialization

__all__ = ["JobSearcher"]


def __getattr__(name: str):
    if name == "JobSearcher":
        from src.jobs.searcher import JobSearcher

        return JobSearcher
    raise AttributeError(name)
