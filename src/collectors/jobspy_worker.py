"""Isolated JobSpy process so blocked sources can be stopped on timeout."""

import contextlib
import json
import sys


def main():
    from jobspy import scrape_jobs

    options = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        frame = scrape_jobs(**options)
    # pandas JSON serialization handles NaN, timestamps, and numpy scalars.
    print(frame.to_json(orient="records", date_format="iso"))


if __name__ == "__main__":
    main()
