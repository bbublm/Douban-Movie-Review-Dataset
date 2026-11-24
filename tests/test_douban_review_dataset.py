from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from ingest.sources.douban_review_dataset import ImportStats, iter_reviews
from transform.reviews import build_title_index, process_review


def test_import_matches_movie_and_preserves_review_metadata() -> None:
    movie = {
        "movie_id": "tt1234567",
        "title_zh": "测试电影",
        "title": "测试电影",
        "title_en": None,
        "original_title": None,
        "release_year": 2020,
        "imdb_id": "tt1234567",
        "tmdb_id": 123,
        "douban_id": "12345678",
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        source_dir = Path(temp_dir)
        with (source_dir / "测试电影.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "2020-01-02 03:04:05",
                "do-not-store-this-name",
                "这是一条足够长的观众短评，用来验证数据导入字段。",
                "5",
                "力荐",
                "12",
                "0.91",
            ])

        stats = ImportStats()
        source_review = next(iter_reviews(
            source_dir,
            build_title_index([movie]),
            {movie["movie_id"]: movie},
            stats,
        ))

    processed, result = process_review(
        source_review,
        index=build_title_index([movie]),
        min_chars=20,
        seen=set(),
    )

    assert result == "kept"
    assert processed is not None
    assert processed["movie_id"] == movie["movie_id"]
    assert processed["douban_id"] == movie["douban_id"]
    assert processed["rating"] == 10
    assert processed["source"] == "douban_dataset"
    assert processed["review_time"] == "2020-01-02T03:04:05"
    assert processed["review_id"] == source_review["external_id"]
    assert processed["douban_sort"] is None
    assert "creator" not in processed
    assert stats.files_seen == stats.matched_files == stats.rows_written == 1
