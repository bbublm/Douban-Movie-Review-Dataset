"""Import a local Douban review CSV corpus without making network requests."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Protocol


class TitleMatcher(Protocol):
    def lookup(
        self, title, year, imdb_id=None, tmdb_id=None
    ) -> tuple[str | None, str]: ...


@dataclass
class ImportStats:
    files_seen: int = 0
    matched_files: int = 0
    unmatched_titles: list[str] = field(default_factory=list)
    rows_seen: int = 0
    rows_written: int = 0
    skipped_empty: int = 0
    skipped_invalid: int = 0


def _review_time(value: str) -> str | None:
    value = value.strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).isoformat()
        except ValueError:
            continue
    return None


def iter_reviews(
    directory: Path,
    title_index: TitleMatcher,
    movies_by_id: dict[str, dict],
    stats: ImportStats,
) -> Iterator[dict]:
    """Yield only comments from files whose title uniquely matches the movie catalog."""
    files = sorted(directory.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV review files found in {directory}")

    for path in files:
        stats.files_seen += 1
        movie_title = path.stem
        movie_id, _ = title_index.lookup(movie_title, None)
        if not movie_id:
            stats.unmatched_titles.append(movie_title)
            continue
        stats.matched_files += 1
        movie = movies_by_id.get(str(movie_id), {})

        with path.open(encoding="utf-8-sig", newline="") as source:
            for row_index, row in enumerate(csv.reader(source), start=1):
                stats.rows_seen += 1
                if len(row) != 7:
                    stats.skipped_invalid += 1
                    continue

                comment_time = row[0].strip()
                text = row[2].strip()
                review_time = _review_time(comment_time)
                try:
                    stars = float(row[3])
                except ValueError:
                    stars = 0

                if not text:
                    stats.skipped_empty += 1
                    continue
                if review_time is None or not 1 <= stars <= 5:
                    stats.skipped_invalid += 1
                    continue

                sentiment = (
                    "positive" if stars >= 4 else "negative" if stars <= 2 else "neutral"
                )
                identity = "\0".join(
                    (str(movie_id), comment_time, str(stars), text)
                )
                digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
                review_id = f"douban:dataset:{digest}"
                stats.rows_written += 1
                yield {
                    "external_id": review_id,
                    "text": text,
                    "rating": stars * 2,
                    "sentiment": sentiment,
                    "sentiment_score": {
                        "positive": 1.0,
                        "negative": -1.0,
                        "neutral": 0.0,
                    }[sentiment],
                    "movie_title": movie_title,
                    "movie_year": None,
                    "imdb_id": movie.get("imdb_id"),
                    "movie_tmdb_id": movie.get("tmdb_id"),
                    "douban_id": movie.get("douban_id"),
                    "douban_comment_time": comment_time,
                    "review_time": review_time,
                    "lang": "zh",
                    "dataset": "Douban-Movie-Review-Dataset-master",
                    "source": "douban_dataset",
                    "source_file": path.name,
                    "row_index": row_index,
                }
