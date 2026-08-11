"""【一時的な診断スクリプト】EDINETの大量保有報告書メタデータとCSV構造を実データで確認する。

本番pipelineには影響しない。ログに生データを吐き出して正しいパース方法を確定するためのもの。
確認後に削除する。
"""
from __future__ import annotations

import json
import os
from datetime import date

import edinet
from config import EDINET_DOCTYPE_HOLDING

KEY = os.environ.get("EDINET_API_KEY", "").strip()


def main():
    if not KEY:
        print("NO EDINET KEY")
        return
    # 直近3営業日の大量保有報告メタを集める
    metas = []
    for day in edinet.business_days_back(date.today(), 3):
        try:
            results = edinet.list_documents(KEY, day)
            metas.extend(edinet.filter_holding_reports(results))
        except Exception as e:  # noqa: BLE001
            print("LIST ERR", day, e)
    print(f"=== 大量保有メタ件数: {len(metas)} ===")

    # 先頭3件の全メタデータ（全キー）を出力
    for i, m in enumerate(metas[:3]):
        print(f"\n=== META[{i}] 全フィールド ===")
        for k, v in m.items():
            print(f"  {k} = {v}")

    # 先頭2件のCSV中身を出力（要素ID・項目名・値）
    for i, m in enumerate(metas[:2]):
        doc_id = m.get("docID")
        print(f"\n=== CSV rows for docID={doc_id} (filerName={m.get('filerName')}) ===")
        try:
            rows = edinet.download_csv_rows(KEY, doc_id)
        except Exception as e:  # noqa: BLE001
            print("  CSV ERR", e)
            continue
        printed = 0
        for r in rows:
            el = r.get("要素ID", "")
            label = r.get("項目名", "")
            val = r.get("値", "")
            # 会社名/コード/保有割合/取得資金 に関係しそうな行を優先表示
            key_terms = ("保有割合", "発行", "会社", "証券", "コード", "提出者", "氏名", "名称",
                         "取得", "資金", "株券等", "対象", "银行", "銘柄")
            if any(t in str(label) for t in key_terms) or any(t in str(el) for t in key_terms):
                print(f"  [{el}] {label} = {val}")
                printed += 1
            if printed >= 60:
                break
        print(f"  (printed {printed} relevant rows of {len(rows)} total)")


if __name__ == "__main__":
    main()
