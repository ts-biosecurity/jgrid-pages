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
- 国別基本情報（CDC Travelers' Health, 外務省 感染症危険情報、外務省 世界の医療事情へのリンク）
- 統計バー（記事数 / アラート発生地域数 / 検出疾患数 / データソース数）
- フィルター（疾患・州/管区・データソース・キーワード）
- 地図（Leaflet + TopoJSON）と記事リスト（左右分割）

## データソース

各国の `*_infectious_diseases.json` は **Google News RSS** の疾患キーワード × 国コードクエリで取得した記事を集約したもの（共通仕様）。`who_don.json` は WHO 公式 Disease Outbreak News（過去2週間分、全国共通）。

加えて、**一部の国では国別の追加ソース**を実装している：

| 国 | 共通 | 国別追加ソース | データファイル |
|---|---|---|---|
| Myanmar | Google News, WHO DON | **GNLM**（国営紙 Global New Light Of Myanmar の RSS）<br>**Eleven Myanmar**（民間紙 Eleven Media Group の Drupal サイト検索 `/search/node/<keyword>`）<br>**RFA / BBC Burmese**（国際放送局のビルマ語サービス RSS、過去 168 時間ウィンドウ）<br>**WHO Myanmar / SEARO ニュース**（who.int/myanmar 系を HTML スクレイプ）<br>**WHO SEARO Epidemiological Bulletin**（隔週 PDF 速報、最新1号は PDF からミャンマー個別記述をセクション/ページ単位で抽出し EN→JA 翻訳） | `myanmar_infectious_diseases.json`<br>`myanmar_gnlm.json`<br>`myanmar_eleven.json`<br>`myanmar_intl_burmese.json`<br>`myanmar_who.json`<br>`who_searo_epi.json`<br>`who_don.json` |
| Brazil | Google News, WHO DON | **InfoDengue**（FIOCRUZ のデング熱可視化サービスから地図画像と Pernambuco 州詳細を取得） | `brazil_infectious_diseases.json`<br>`pernambuco_news.json`<br>`infodengue_brazil_map.png`<br>`infodengue_pe_detail.png`<br>`who_don.json` |
| Japan | — | **IDWR 感染症発生動向調査週報（疫学情報）**<br>**ARI（急性呼吸器感染症）サマリ** | `japan_infectious_diseases.json`<br>`japan_idwr_souran.json`<br>`japan_ari_summary.json` |
| Vietnam | Google News, WHO DON | 省境界 GeoJSON（地図描画用） | `vietnam_infectious_diseases.json`<br>`vietnam_provinces.geojson`<br>`who_don.json` |
| その他 | Google News, WHO DON | — | `<country>_infectious_diseases.json`<br>`who_don.json` |

各記事には `dataSource` フィールド（例: `"Google News"`, `"GNLM"`, `"Eleven Myanmar"`, `"RFA Burmese"`, `"BBC Burmese"`, `"WHO Myanmar"`）が付与されており、フロントエンド側ではこの値でソースバッジを色分けしフィルタを提供する。

## 更新の仕組み

- `dashboard.html` — `generate_dashboard.py` が `jgrid.xlsx` から自動生成（タイムスタンプはJST表記）
- `dashboard.daily.html` / `dashboard.cluster.html` — 同様に自動生成（`github-actions[bot]` がpush）
- 各国ダッシュボード — `jgrid-fetch` リポジトリの GitHub Actions（cron 約 JST 06:22 daily）が各種ソースからデータを取得し、本リポジトリの `{country}/data/` に push
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
- データソースバッジ `.source-badge.*`（`gnews` / `gnlm` / `who` / `eleven` / `rfa` / `bbc` / `default`）の bg/color
- Leafletポップアップ・info-box の bg/color

を国旗等に合わせて差し替える。Myanmar ページがライトテーマ＋国旗3色のリファレンス実装。

## 国別補足ドキュメント

- [`myanmar/data_pipeline.md`](myanmar/data_pipeline.md) — Myanmar のデータパイプライン詳細（収集経路・Cloudflare 回避・WHO Myanmar / SEARO Epi 統合の経緯・jgrid-fetch 投入手順）
