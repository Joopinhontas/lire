import sys
from pathlib import Path

from test_auth import ENV


def resume(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    sys.modules.pop("services", None)
    import services  # noqa: PLC0415
    return services.resume_point


def vol(n, chapter_id, read, pages=200, when=""):
    return {"minNumber": n, "chapters": [{"id": chapter_id, "minNumber": 0, "pagesRead": read, "pages": pages,
                                          "lastReadingProgressUtc": when}]}


def test_started_at_volume_two_resumes_there(monkeypatch):
    point = resume(monkeypatch)([vol(1, 10, 0), vol(2, 20, 12, when="2026-10-01T16:27"), vol(3, 30, 0)])
    assert point == {"volume": 2, "page": 12, "pages": 200, "chapter": 20}


def test_most_recent_wins_over_order(monkeypatch):
    point = resume(monkeypatch)([vol(1, 10, 50, when="2026-10-01T10:00"), vol(5, 50, 7, when="2026-10-01T18:00")])
    assert point["chapter"] == 50 and point["page"] == 7


def test_finished_volume_opens_the_next_one(monkeypatch):
    point = resume(monkeypatch)([vol(1, 10, 200, when="2026-10-01T10:00"), vol(2, 20, 0)])
    assert point == {"volume": 2, "page": 0, "pages": 200, "chapter": 20}


def test_nothing_read_falls_back_to_kavita(monkeypatch):
    assert resume(monkeypatch)([vol(1, 10, 0), vol(2, 20, 0)]) is None
