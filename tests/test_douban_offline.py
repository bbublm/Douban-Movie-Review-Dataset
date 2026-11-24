from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from ingest.sources.douban import DoubanCollector


class _FakePage:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def close(self) -> None:
        pass


def test_collect_reviews_applies_sort_quotas_dedup_and_movie_cap() -> None:
    page = _FakePage()
    collector = object.__new__(DoubanCollector)
    collector._ctx = type("Context", (), {"new_page": lambda _self: page})()
    collector._ensure_browser = lambda: None
    requested_sorts: list[str] = []

    def navigate(_page: _FakePage, url: str) -> None:
        parts = urlsplit(url)
        sort = parse_qs(parts.query)["sort"][0]
        douban_id = parts.path.split("/")[2]
        requested_sorts.append(sort)
        base = f"{sort}-{douban_id}"
        offset = 0 if "start=0" in url else 20
        page.rows = [
            {"cid": f"{base}-{offset + i}", "text": f"valid review text for {base} {offset + i}",
             "ctime": "2024-01-02 12:30:00",
             "stars": 4, "author": "anonymous"}
            for i in range(20)
        ]
        if sort == "new_score" and douban_id == "db1":
            page.rows[0]["cid"] = "new_score-db1-0"
            page.rows[1] = {
                "cid": "time-db1-0",
                "text": "valid review text for time-db1 0",
                "ctime": "2024-01-02 12:30:00",
                "stars": 4,
                "author": "anonymous",
            }

    collector._navigate_public = navigate
    collector._wait_comments = lambda current_page: len(current_page.rows)
    collector._safe_eval = lambda current_page, _expr: current_page.rows
    collector.stats = {"films": 0, "comments": 0, "skipped_empty": 0}

    records = list(collector.collect_reviews(
        {"movie-1": "db1", "movie-2": "db2"},
        movies_by_id={
            "movie-1": {"title": "Movie One", "imdb_id": "tt0000001"},
            "movie-2": {"title": "Movie Two", "imdb_id": "tt0000002"},
        },
        pages=2,
        delay=0,
        recent_limit=5,
        popular_limit=5,
        existing_by_movie={
            "movie-1": {
                "ids": {"new_score-db1-0"},
                "texts": set(),
                "time": set(),
                "new_score": {"new_score-db1-0"},
            },
        },
    ))

    ids = {record["review_id"] for record in records}
    assert len(records) == 19
    assert len(ids) == 19
    assert "douban:new_score-db1-0" not in ids
    assert sum(record["movie_title"] == "Movie One" for record in records) == 9
    assert sum(record["movie_title"] == "Movie Two" for record in records) == 10
    assert collector.stats["comments_time"] == 10
    assert collector.stats["comments_new_score"] == 9
    assert "time" in requested_sorts
    assert "new_score" in requested_sorts
    assert all(record["source"] == "douban" for record in records)
    assert len({record["text"] for record in records}) == len(records)
    assert all(record["review_time"] == "2024-01-02T12:30:00" for record in records)
    assert {record["douban_sort"] for record in records} == {"time", "new_score"}
