from pathlib import Path

from work_helper.answer.search import top_files


def test_ranks_by_match_count_and_skips_raw(tmp_path):
    (tmp_path / "topics").mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / "topics/a.md").write_text("worker\nqueue\ncron\n")
    (tmp_path / "topics/b.md").write_text("worker\n")
    (tmp_path / "raw/c.json").write_text("worker queue cron\n")

    assert top_files(tmp_path, ["worker", "queue", "cron"]) == [
        Path(tmp_path / "topics/a.md"),
        Path(tmp_path / "topics/b.md"),
    ]


def test_ties_are_stable_despite_threading(tmp_path):
    (tmp_path / "topics").mkdir()
    for name in "abcd":
        (tmp_path / f"topics/{name}.md").write_text("worker\n")
    runs = {tuple(top_files(tmp_path, ["worker", "queue", "cron"])) for _ in range(5)}
    assert len(runs) == 1
