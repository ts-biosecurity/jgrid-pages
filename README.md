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

| 国 | パス | テーマ |
|---|---|---|
| Brazil | `brazil/index.html` | dark green |
| China | `china/index.html` | dark green |
| DR Congo | `drc/index.html` | dark green |
| Ghana | `ghana/index.html` | dark green |
| India | `india/index.html` | dark green |
| Indonesia | `indonesia/index.html` | dark green |
| Japan | `japan/index.html` | dark green |
| Myanmar | `myanmar/index.html` | light + 国旗カラー（黄/緑/赤） |
| Thailand | `thailand/index.html` | dark green |
| Vietnam | `vietnam/index.html` | dark green |
| Zambia | `zambia/index.html` | dark green |

各国フォルダの `data/` にJSONデータを格納。データは [jgrid-fetch](https://github.com/ts-biosecurity/jgrid-fetch)（private）の GitHub Actions により自動更新。

各国 `index.html` は以下のセクション構成で共通化されている：

- ヘッダー（タイトル＋言語切替 EN/JA/現地語）
- WHO Disease Outbreak News（過去2週間）
- 国別基本情報（CDC Travelers' Health, 外務省 感染症危険情報へのリンク）
- 統計バー（記事数 / アラート発生地域数 / 検出疾患数 / データソース数）
- フィルター（疾患・州/管区・キーワード）
- 地図（Leaflet + TopoJSON）と記事リスト（左右分割）

## 更新の仕組み

- `dashboard.html` — `generate_dashboard.py` が `jgrid.xlsx` から自動生成（タイムスタンプはJST表記）
- `dashboard.daily.html` / `dashboard.cluster.html` — 同様に自動生成（`github-actions[bot]` がpush）
- 各国ダッシュボード — `jgrid-fetch` リポジトリの GitHub Actions が BlueDot API + Google News RSS からデータを取得し、本リポジトリの `{country}/data/` に push
- 各国 `index.html`（HTML本体）は自動再生成の対象外。デザインや構成変更はこのリポジトリで直接編集する

## デザインのカスタマイズ

各国ページの配色は `<style>` 内の `:root` CSS変数で制御している：

```css
:root {
  --bg: ...;          /* 背景 */
  --card: ...;        /* カード/パネル */
  --border: ...;
  --text: ...;
  --text-dim: ...;
  --accent: ...;      /* ボタン背景・フォーカス枠 */
  --danger / --warning / --success: ...;
}
```

加えて：

- ヘッダー背景（`linear-gradient(...)`）
- マップタイル（`L.tileLayer(... dark_nolabels / light_nolabels ...)`）
- ヒートマップ階調 `const HEAT = [...]`（5段階）
- マップ州境界の `color`（GeoJSON style／mouseover）
- 病名タグ `.disease-tag.*` の bg/color
- Leafletポップアップ・info-box の bg/color

を国旗等に合わせて差し替える。Myanmar ページがライトテーマ＋国旗3色のリファレンス実装。
