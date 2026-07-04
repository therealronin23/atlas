from pathlib import Path

from atlas.core.self_maintenance.sota_snapshot import SotaSnapshot, SotaSnapshotRecorder


class FakeCrawlerSuccess:
    def __init__(self, markdown: str = "contenido"):
        self._markdown = markdown

    def crawl(self, url: str):
        class Result:
            success = True
            markdown = self._markdown
            error = None

        return Result()


class FakeCrawlerFailure:
    def __init__(self, error: str = "motivo x"):
        self._error = error

    def crawl(self, url: str):
        class Result:
            success = False
            markdown = ""
            error = self._error

        return Result()


class FakeCrawlerException:
    def crawl(self, url: str):
        raise RuntimeError("boom")


def test_capture_success_persists(tmp_path: Path) -> None:
    store = tmp_path / "snapshots.json"
    crawler = FakeCrawlerSuccess(markdown="contenido")
    recorder = SotaSnapshotRecorder(crawler=crawler, store_path=store)

    snapshot = recorder.capture(
        benchmark_name="bench-a",
        atlas_score=0.95,
        reference_url="https://example.com/a",
    )

    assert isinstance(snapshot, SotaSnapshot)
    assert snapshot.benchmark_name == "bench-a"
    assert snapshot.atlas_score == 0.95
    assert snapshot.reference_url == "https://example.com/a"
    assert snapshot.reference_excerpt == "contenido"
    assert store.exists()


def test_two_captures_history_order(tmp_path: Path) -> None:
    store = tmp_path / "snapshots.json"
    recorder = SotaSnapshotRecorder(
        crawler=FakeCrawlerSuccess(markdown="m1"), store_path=store
    )

    recorder.capture(benchmark_name="b1", atlas_score=0.1, reference_url="http://a")
    recorder2 = SotaSnapshotRecorder(
        crawler=FakeCrawlerSuccess(markdown="m2"), store_path=store
    )
    recorder2.capture(benchmark_name="b2", atlas_score=0.2, reference_url="http://b")

    hist = recorder2.history()
    assert len(hist) == 2
    assert hist[0].benchmark_name == "b1"
    assert hist[0].reference_excerpt == "m1"
    assert hist[1].benchmark_name == "b2"
    assert hist[1].reference_excerpt == "m2"


def test_capture_failure_no_exception(tmp_path: Path) -> None:
    store = tmp_path / "snapshots.json"
    recorder = SotaSnapshotRecorder(
        crawler=FakeCrawlerFailure(error="motivo x"), store_path=store
    )

    snapshot = recorder.capture(
        benchmark_name="bench-fail",
        atlas_score=0.0,
        reference_url="https://example.com/fail",
    )

    assert "motivo x" in snapshot.reference_excerpt
    assert "fetch fallido" in snapshot.reference_excerpt


def test_capture_exception_no_propagate(tmp_path: Path) -> None:
    store = tmp_path / "snapshots.json"
    recorder = SotaSnapshotRecorder(
        crawler=FakeCrawlerException(), store_path=store
    )

    snapshot = recorder.capture(
        benchmark_name="bench-exc",
        atlas_score=0.0,
        reference_url="https://example.com/exc",
    )

    assert "fetch fallido" in snapshot.reference_excerpt
    assert "boom" in snapshot.reference_excerpt


def test_history_filters_by_benchmark_name(tmp_path: Path) -> None:
    store = tmp_path / "snapshots.json"
    recorder = SotaSnapshotRecorder(
        crawler=FakeCrawlerSuccess(markdown="m"), store_path=store
    )

    recorder.capture(benchmark_name="x", atlas_score=1.0, reference_url="http://x")
    recorder.capture(benchmark_name="y", atlas_score=2.0, reference_url="http://y")
    recorder.capture(benchmark_name="x", atlas_score=3.0, reference_url="http://x2")

    hist_x = recorder.history(benchmark_name="x")
    assert len(hist_x) == 2
    assert [s.atlas_score for s in hist_x] == [1.0, 3.0]

    hist_y = recorder.history(benchmark_name="y")
    assert len(hist_y) == 1
    assert hist_y[0].atlas_score == 2.0


def test_history_missing_file_returns_empty(tmp_path: Path) -> None:
    store = tmp_path / "nonexistent.json"
    recorder = SotaSnapshotRecorder(
        crawler=FakeCrawlerSuccess(), store_path=store
    )

    assert recorder.history() == []
