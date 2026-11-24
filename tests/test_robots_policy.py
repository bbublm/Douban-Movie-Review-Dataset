from __future__ import annotations

from ingest.robots import RobotsPolicy


def test_robots_failure_can_fail_closed() -> None:
    policy = RobotsPolicy(fail_closed=True)
    policy._fetch = lambda _netloc: None  # type: ignore[method-assign]

    assert not policy.can_fetch("https://movie.douban.com/subject/1292052/")


def test_robots_denied_path_is_not_fetchable() -> None:
    from urllib.robotparser import RobotFileParser

    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /subject/"])
    policy = RobotsPolicy(fail_closed=True)
    policy._fetch = lambda _netloc: parser  # type: ignore[method-assign]

    assert not policy.can_fetch("https://movie.douban.com/subject/1292052/")
