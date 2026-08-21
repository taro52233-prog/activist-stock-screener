"""監視リスト（バリュー参考）まわりの決定論ロジックをオフライン検証。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

import config  # noqa: E402
import run     # noqa: E402


def test_load_watchlist_parses(tmp_path, monkeypatch):
    p = tmp_path / "watchlist.txt"
    p.write_text(
        "# コメント\n"
        "7203   # トヨタ\n"
        "\n"
        "８３０６  # 全角コード\n"
        "7203\n"          # 重複
        "6758\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "WATCHLIST_PATH", p)
    codes = config.load_watchlist()
    assert codes == ["7203", "8306", "6758"]   # 順序維持・全角半角化・重複排除


def test_load_watchlist_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WATCHLIST_PATH", tmp_path / "nope.txt")
    assert config.load_watchlist() == []


def test_build_watchlist_candidates_excludes_tracked():
    cands = run.build_candidates_watchlist(["7203", "6758", "9999"], exclude={"6758"})
    codes = [c.code for c in cands]
    assert codes == ["7203", "9999"]        # 追跡中(6758)は除外
    assert all(c.is_watchlist for c in cands)
    assert all(not c.is_known_activist and c.fund == "" for c in cands)
