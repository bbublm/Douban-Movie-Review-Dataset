"""Restore the processed catalog from the bundled snapshot without touching reviews or ES."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.seed import normalize_legacy
from ingest.jsonl_io import iter_jsonl, write_jsonl
from transform.movies import MovieMerger

SNAPSHOT = ROOT / "frontend" / "public" / "data" / "movies.json"
LEGACY = ROOT / "data" / "web_movies.json"
DOUBAN = ROOT / "data_lake" / "interim" / "douban_movies.jsonl"
OUTPUT = ROOT / "data_lake" / "processed" / "movies.jsonl"


def _snapshot_record(row: dict) -> dict:
    title = row.get("title_zh") or row.get("title") or ""
    imdb_id = str(row.get("imdb_id") or row.get("id") or "").strip()
    return {
        "imdb_id": imdb_id if imdb_id.startswith("tt") else None,
        "tmdb_id": row.get("tmdb_id"),
        "title": title,
        "title_zh": title or None,
        "title_en": row.get("title_en"),
        "original_title": row.get("original_title"),
        "release_year": row.get("year") or row.get("release_year"),
        "runtime": row.get("runtime"),
        "overview": row.get("summary") or row.get("overview") or "",
        "genres_zh": row.get("genres_zh") or [],
        "genres_en": row.get("genres_en") or [],
        "director": row.get("director"),
        "cast": row.get("cast") or [],
        "vote_average": row.get("vote_average") or row.get("rating"),
        "vote_count": row.get("vote_count") or row.get("votes"),
        "poster_url": row.get("poster_url"),
        "source": "legacy",
    }


def build_catalog() -> tuple[list[dict], int, int]:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    legacy = json.loads(LEGACY.read_text(encoding="utf-8")).get("movies") or []
    douban = list(iter_jsonl(DOUBAN))
    if not isinstance(snapshot, list) or len(snapshot) < 400:
        raise ValueError(f"Bundled movie snapshot is unexpectedly small: {len(snapshot)}")

    merger = MovieMerger()
    for row in snapshot:
        merger.add(_snapshot_record(row))
    for row in legacy:
        merger.add(normalize_legacy(row))

    snapshot_ids = {
        str(row.get("id") or row.get("imdb_id") or "").strip().lower()
        for row in snapshot
    }
    douban_matches = 0
    for row in douban:
        imdb_id = str(row.get("imdb_id") or "").strip().lower()
        if imdb_id and imdb_id in snapshot_ids:
            douban_matches += 1
        merger.add(row)

    catalog = list(merger.results())
    if len(catalog) < len(snapshot):
        raise ValueError(
            f"Restored catalog ({len(catalog)}) is smaller than its source "
            f"snapshot ({len(snapshot)})"
        )
    if not all(movie.get("title") and movie.get("movie_id") for movie in catalog):
        raise ValueError("Restored catalog contains a record without title or movie_id")
    return catalog, len(snapshot), douban_matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="back up and replace processed/movies.jsonl (default is a dry run)",
    )
    args = parser.parse_args()

    catalog, snapshot_count, douban_matches = build_catalog()
    print(f"Snapshot movies: {snapshot_count}")
    print(f"Douban records matched by IMDb id: {douban_matches}")
    print(f"Restored catalog: {len(catalog)}")
    for field in ("release_year", "vote_average", "director", "overview", "poster_url"):
        count = sum(bool(movie.get(field)) for movie in catalog)
        print(f"  {field}: {count}/{len(catalog)}")

    if not args.apply:
        print(f"Dry run only. Re-run with --apply to replace {OUTPUT}")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = OUTPUT.with_name(f"movies.before-restore-{stamp}.jsonl")
        shutil.copy2(OUTPUT, backup)
        print(f"Backup: {backup}")

    temporary = OUTPUT.with_name("movies.restore.tmp")
    write_jsonl(catalog, temporary)
    temporary.replace(OUTPUT)
    print(f"Restored: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
