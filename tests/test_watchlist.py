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


def test_classify_market():
    assert config.classify_market("7203") == "JP"
    assert config.classify_market("130A") == "JP"   # 日本の新形式（3桁数字＋英字）
    assert config.classify_market("AAPL") == "US"
    assert config.classify_market("KO") == "US"
    assert config.classify_market("BRK.B") == "US"
    assert config.classify_market("") == "JP"


def test_build_watchlist_sets_us_market_and_currency():
    cands = run.build_candidates_watchlist(["AAPL", "7203"], exclude=set())
    by = {c.code: c for c in cands}
    assert by["AAPL"].market_country == "US" and by["AAPL"].currency == "USD"
    assert by["7203"].market_country == "JP" and by["7203"].currency == "JPY"


def test_us_summary_to_fundamentals():
    import usdata
    res = {
        "defaultKeyStatistics": {"bookValue": {"raw": 4.2}, "sharesOutstanding": {"raw": 1_000_000}, "trailingEps": {"raw": 6.1}},
        "summaryDetail": {"dividendRate": {"raw": 0.96}},
    }
    f = usdata.summary_to_fundamentals(res)
    assert f.bps == 4.2 and f.shares_out == 1_000_000 and f.eps == 6.1
    assert f.dps_result == 0.96 and f.equity == 4.2 * 1_000_000
