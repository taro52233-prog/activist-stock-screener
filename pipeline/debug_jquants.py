"""【一時診断】J-Quants V2の正しいエンドポイントとレスポンス構造を実測で確認する。確認後に削除。"""
import os
import requests

KEY = os.environ.get("JQUANTS_API_KEY", "").strip()
H = {"x-api-key": KEY}
BASE = "https://api.jquants.com/v2"

TESTS = [
    ("/listed/info", {}),
    ("/listed/info", {"date": "20260807"}),
    ("/listed/info", {"code": "7203"}),
    ("/fins/statements", {"code": "7203"}),
    ("/fins/summary", {"code": "7203"}),
    ("/fins/details", {"code": "7203"}),
    ("/markets/daily_quotes", {"code": "7203", "date": "20260807"}),
]


def main():
    if not KEY:
        print("NO KEY")
        return
    for path, params in TESTS:
        url = BASE + path
        try:
            r = requests.get(url, headers=H, params=params, timeout=20)
            print(f"\n{r.status_code} GET {path} {params}")
            print("  body:", r.text[:300])
            if r.status_code == 200:
                j = r.json()
                print("  toplevel keys:", list(j.keys()))
                for k, v in j.items():
                    if isinstance(v, list) and v:
                        print(f"  {k}[0] keys:", sorted(v[0].keys()))
                        break
        except Exception as e:  # noqa: BLE001
            print(f"ERR {path}: {e}")


if __name__ == "__main__":
    main()
