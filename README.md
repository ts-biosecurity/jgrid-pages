# J-GRID+ Intelligence Dashboard

AMED 新興・再興感染症研究基盤創生事業（海外拠点研究領域）ネットワークコア拠点「モニタリング体制の強化」の一環として、感染症関連のメディア情報を収集・表示するダッシュボードです。

## 公開URL

https://ts-biosecurity.github.io/jgrid-pages/

## 構成

| ページ | パス | 説明 |
|---|---|---|
| Top | `index.html` | トップページ（各ダッシュボードへのリンク） |
| Intelligence Dashboard | `dashboard.html` | 全対象国のメディア情報一覧（自動生成データ埋め込み） |
| Signal Triage (Daily) | `dashboard.daily.html` | 日次ベースのシグナルトリアージ |
| Signal Triage (Clustered) | `dashboard.cluster.html` | クラスタリング表示 |
| About Us | `aboutus.html` | サイト説明・情報の取り扱い |

### Country Dashboards

| 国 | パス |
|---|---|
| Brazil | `brazil/index.html` |
| Ghana | `ghana/index.html` |
| India | `india/index.html` |
| Indonesia | `indonesia/index.html` |
| Thailand | `thailand/index.html` |
| Vietnam | `vietnam/index.html` |
| Zambia | `zambia/index.html` |

各国フォルダの `data/` にJSONデータを格納。データは [jgrid-fetch](https://github.com/ts-biosecurity/jgrid-fetch)（private）の GitHub Actions により自動更新。

## 更新の仕組み

- `dashboard.html` — `generate_dashboard.py` が `jgrid.xlsx` から自動生成（タイムスタンプはJST表記）
- `dashboard.daily.html` / `dashboard.cluster.html` — 同様に自動生成
- 各国ダッシュボード — `jgrid-fetch` リポジトリの GitHub Actions が BlueDot API + Google News RSS からデータを取得し、本リポジトリの `{country}/data/` に push
