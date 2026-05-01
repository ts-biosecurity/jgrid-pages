# ミャンマー 感染症ニュース取得の仕組み

**対象ページ**: https://ts-biosecurity.github.io/jgrid-pages/myanmar/
**作成日**: 2026-05-01 JST（GNLM 追加後の現状を反映）
**情報源**:
- 本リポジトリ `jgrid-pages` の `myanmar/index.html`、`myanmar/data/*.json`
- 収集パイプライン `jgrid-fetch` (private) の `myanmar/fetch.py`、`myanmar/fetch_gnlm.py`、`.github/workflows/myanmar.yml`
- 直近の `git log`（GNLM 関連 6 commits、2026-04-30）

---

## 1. 全体像

ミャンマーダッシュボードは **`jgrid-fetch`（private repo）の GitHub Actions が日次でニュースを収集 → `jgrid-pages/myanmar/data/` に JSON を push → ブラウザ側 `index.html` がその JSON を fetch して可視化** する静的サイト構成。

```
  [外部データソース]                    [収集パイプライン]                [公開リポジトリ]                [閲覧]
 ┌──────────────────────────┐         ┌──────────────────────┐        ┌──────────────────────────┐    ┌────────────┐
 │ ① Google News RSS        │ ──┐     │ jgrid-fetch (private) │        │ jgrid-pages (public)     │    │ ブラウザ      │
 │   (multi-language query) │   │     │ GitHub Actions        │        │ myanmar/data/            │    │             │
 │                          │   │     │  cron: 22 21 * * * UTC│        │   ├ myanmar_infectious_  │    │ Leaflet地図  │
 │ ② GNLM (国営紙)          │ ──┼───► │  (= JST 06:22 daily)  │ ─────► │   │   diseases.json     │──► │ 記事一覧      │
 │   gnlm.com.mm RSS        │   │     │                       │        │   ├ myanmar_gnlm.json ★ │    │ WHO DONリスト│
 │                          │   │     │ Python ETL:           │        │   └ who_don.json         │    │             │
 │ ③ WHO DON (公式)         │ ──┘     │  fetch.py / fetch_gnlm│        │ myanmar/index.html       │    │             │
 │   who.int 一覧スクレイプ   │         │  fetch_who_don.py     │        │ (手動メンテ)              │    │             │
 └──────────────────────────┘         └──────────────────────┘        └──────────────────────────┘    └────────────┘
```

★ **`myanmar_gnlm.json` は 2026-04-30 に追加された新規ソース。次回ワークフロー実行（明朝 JST 06:22）で初回反映予定。`index.html` 側の表示対応は未実装。**

ポイント：
- **静的サイト** — サーバー側処理ゼロ。ブラウザが直接 GitHub Pages の JSON を取得。
- **HTML とデータの分離** — `index.html` は手動メンテ、`data/*.json` のみ自動更新。
- **収集ロジックは別 repo（private）** — 本リポジトリには成果物 JSON のみ存在。

---

## 2. データソース一覧

| # | ソース | 種類 | 言語 | 実装状況 | 出力ファイル | `dataSource` 値 |
|---|---|---|---|---|---|---|
| ① | **Google News RSS** | 集約ニュース | EN + MY | **稼働中**（既存） | `myanmar_infectious_diseases.json` | `"Google News"` |
| ② | **GNLM (Global New Light of Myanmar)** | ミャンマー国営紙 | EN | **2026-04-30 追加・バックエンド稼働中、フロント未表示** | `myanmar_gnlm.json` | `"GNLM"` |
| ③ | **WHO Myanmar / SEARO ニュース** | WHO 公式国別＋地域 | EN | **2026-05-01 追加 (frontend 実装済、jgrid-fetch 投入待ち)** | `myanmar_who.json` | `"WHO Myanmar"` |
| ④ | **WHO Disease Outbreak News** | 公式アウトブレイク報告 | EN | 稼働中（全国共通） | `who_don.json` | — |
| ⑤ | **WHO SEARO Epidemiological Bulletin** | 隔週疫学速報 (PDF) | EN | **2026-05-01 追加 (frontend 実装済、jgrid-fetch 投入待ち)** | `who_searo_epi.json` | — |
| ⑥ | **Eleven Myanmar (Eleven Media Group)** | 民間紙（Drupal サイト） | EN | **2026-05-02 追加 (frontend 実装済、jgrid-fetch 投入待ち)** | `myanmar_eleven.json` | `"Eleven Myanmar"` |
| ⑦ | **RFA / BBC Burmese (国際放送)** | 国際放送局のビルマ語サービス RSS | MY | **jgrid-fetch 稼働中・2026-05-02 frontend 統合**（直近 0 件続きで未表示） | `myanmar_intl_burmese.json` | `"RFA Burmese"` / `"BBC Burmese"` |
| ⑧ | CDC Travelers' Health (Myanmar/Burma) | 外部リンクのみ | EN | リンクのみ | — | — |
| ⑨ | 外務省 感染症危険情報 | 外部リンクのみ | JA | リンクのみ | — | — |

> ⚠️ **訂正**: 当初版の資料では BlueDot API も収集源として挙げたが、これは `jgrid-pages/README.md` の記載のみで、`jgrid-fetch` のコードには BlueDot 連携の実装が存在しない（`grep -ri bluedot` で 0 件）。実運用ではミャンマーは **Google News + GNLM + WHO DON** の 3 経路。

---

## 3. ソース別の取得方法

### ① Google News RSS（既存）
- ファイル: `jgrid-fetch/myanmar/fetch.py`
- エンドポイント: `https://news.google.com/rss/search`
- パラメータ: `hl=en, gl=MM, ceid=MM:en` と `hl=my, gl=MM, ceid=MM:my` の 2 系統で英・ビルマ語両方を取得
- 取得期間: 過去 72 時間
- 疾患キーワード × Myanmar の組み合わせクエリ
- 出力: `dataSource: "Google News"`, `sourceName: <発信元媒体>`

### ② GNLM（2026-04-30 追加 / 国営紙）
- ファイル: `jgrid-fetch/myanmar/fetch_gnlm.py`（402 行）
- 公式サイト: https://www.gnlm.com.mm/
- 収集経路: **RSS 3 系統**
  1. メイン RSS: `/feed/`
  2. Health カテゴリ RSS: `/category/health/feed/`
  3. **疾患キーワード検索フィード**: `/?s=<keyword>&feed=rss2`（35 キーワード）
     - dengue, malaria, influenza, avian influenza, bird flu, tuberculosis, measles, cholera, hepatitis, typhoid, leptospirosis, japanese encephalitis, rabies, diphtheria, pertussis, hiv, leprosy, chikungunya, zika, mpox, monkeypox, ebola, meningitis, plague, scrub typhus, snakebite, outbreak, epidemic, infectious, h5n1, h7n9, h1n1, covid
     - **症候群サーベイランス系**（2026-04-30 追加）: acute respiratory infection, respiratory infection, acute diarrhea/diarrhoea, acute watery diarrhoea, diarrhea, diarrhoea
- **Cloudflare bot 判定の回避**:
  - `curl_cffi` で TLS fingerprint を偽装
  - 4 プロファイルを順に試行: `chrome124 → chrome120 → safari17_0 → edge101`
  - 403 が返る間プロファイル切替で再試行（コミット履歴から、4/30 中に 3 回試行錯誤して確立）
  - WP REST API は Solid Security によりロック (401) されているため使用せず、RSS 経路のみ
- 取得期間: 過去 72 時間
- 単語境界マッチ（`\b...\b` 正規表現）で `tb`/`hiv`/`ari`/`awd` 等の短語の誤判定を回避
- 翻訳: `deep_translator` (Google Translate) で headline と summary を EN→JA 変換し `headlineJa`/`summaryJa` に格納
- 出力: `dataSource: "GNLM"`, `sourceName: "Global New Light Of Myanmar"`

### ③ WHO Myanmar / SEARO ニュース（2026-05-01 追加）
- ファイル: `jgrid-fetch/myanmar/fetch_who_myanmar.py`（本リポジトリ `myanmar/scripts/fetch_who_myanmar.py` に staging）
- 取得元（3 ページ HTML スクレイプ）:
  1. https://www.who.int/myanmar — トップに表示される最新 SEARO ＋ Myanmar ニュース・特集
  2. https://www.who.int/myanmar/news — Myanmar ニュース履歴
  3. https://www.who.int/myanmar/news/feature-stories — Feature Stories
- パーサ: BeautifulSoup4。`div.list-view--item` ブロックから:
  - URL: `a.link-container[href]`
  - タイトル: `a[aria-label]`（フォールバックは `.heading`）
  - 日付: `span.timestamp` → `%d %B %Y` パース
  - カテゴリ: `.sf-tags-list-item`（"News release" / "Statement" / "Departmental update" 等）
- フィルタ:
  - 過去 180 日（環境変数 `WHO_MYANMAR_LOOKBACK_DAYS` で調整可）
  - 疾患キーワード（GNLM と同じ語彙）または広域ヘルス語（outbreak / vaccin / surveillance / immuniz 等）にマッチした記事のみ採用
- 詳細ページ（`/news/detail/...`）から先頭段落を取得してサマリ化
- 翻訳: `deep_translator` (Google Translate) で headline と summary を EN→JA 変換し `headlineJa`/`summaryJa` に格納
- 出力: `dataSource: "WHO Myanmar"`, `sourceName: "WHO Myanmar"` または `"WHO South-East Asia"` (URL に `/southeastasia/` を含むものは後者)
- `articleId` プレフィックス: `who_<sha1[:16]>`

### ④ WHO Disease Outbreak News
- ファイル: `jgrid-fetch/fetch_who_don.py`（全国共通）
- 取得元: https://www.who.int/emergencies/disease-outbreak-news
- 過去 2 週間分を抽出して `who_don.json` に書き出し
- ミャンマー特有のフィルタ無し（全国フォルダで同一ファイルが配布される）

### ⑤ WHO SEARO Epidemiological Bulletin（2026-05-01 追加）
- ファイル: `jgrid-fetch/myanmar/fetch_who_searo_epi.py`（本リポジトリ `myanmar/scripts/fetch_who_searo_epi.py` に staging）
- 取得元: https://www.who.int/southeastasia/outbreaks-and-emergencies/surveillance-and-alert/sear-epi-bulletins
- パーサ: BeautifulSoup4。`div.sf-publications-item` ブロックから:
  - タイトル: `.sf-publications-item__title`
  - 日付: `.sf-publications-item__date span` → `%d %B %Y`
  - 詳細ページ URL: `.sf-publications-item__url a` の href
  - PDF URL: `a.download-url`（`iris.who.int/server/api/core/bitstreams/...`）
  - 説明: `.sf-publications-item__description`
- 取得件数: 最新 24 号（`WHO_SEARO_EPI_MAX` で調整可）。隔週刊行のため約 1 年分
- 翻訳: 直近 6 号のみ EN→JA 翻訳（タイトル + 説明）、それ以前は英語表示のまま
- **PDF からの Myanmar 記述抜粋（2026-05-01 追加）**:
  - 最新 `EXCERPT_TOP_N`（既定 3）号の PDF を `iris.who.int` からダウンロード
  - `pdfminer.six` でテキスト抽出 → ページごとに `Influenza` / `COVID-19` / `mpox` / `Dengue` などのトップレベルセクションを検出
  - `•` トップレベル箇条書き / `Notes:` / `Figure N.` 単位で論理ブロックに分割
  - "Myanmar" を含むブロック内の **文単位** で抽出（同言及の重複は先頭 80 文字のキーで除外）
  - 引用文献番号（`Myanmar13` 等）の除去、リファレンスリスト行・URL 単独行の除外
  - `deep_translator` で各 excerpt を EN→JA 翻訳
  - 出力: 各 bulletin の `myanmarExcerpts[]`（`section` / `page` / `text` / `textJa`）
- 出力: `bulletins[]` 配列、`dataSource` フィールドは持たず（記事リストには統合せず別セクション表示）

> **注**: SEARO Epi Bulletin は SEAR 全域 11 か国の疾患状況を集約した PDF で、Myanmar 個別記事ではない。Myanmar ダッシュボードでは WHO DON と並ぶ「公式レポート」枠として上部に独立表示し、**最新 3 号についてはミャンマー関連記述のみを抜き出してカード形式で表示**する設計。

### ⑦ RFA / BBC Burmese（国際放送ビルマ語サービス）

- ファイル: `jgrid-fetch/myanmar/fetch_intl_burmese.py`（既存、2026-05-01 投入）
- 取得元 RSS:
  - RFA Burmese: `https://www.rfa.org/burmese/rss2.xml`
  - BBC Burmese: `https://feeds.bbci.co.uk/burmese/rss.xml`
  - VOA Burmese は USAGM 予算削減（2025-03）影響で実質停止 → 対象外
- 取得期間: 過去 **72 時間**（`fetch_intl_burmese(hours=72)` 固定値）
- フィルタ:
  - 疾患キーワード（英語＋ビルマ語）または汎用健康語（`outbreak` / `vaccination` / `ကူးစက်ရောဂါ` 等）にマッチ
  - 単語境界マッチ（英数）／ビルマ文字は部分一致（`_word_match()`）
- 翻訳: `deep_translator` で MY→EN → MY→JA（ビルマ文字検出時）／ EN→JA
- 出力: `dataSource: "RFA Burmese"` または `"BBC Burmese"`、`originalLanguage: "BURMESE"`
- `articleId` プレフィックス: `rfa_<sha256[:16]>` / `bbc_<sha256[:16]>`
- **観察される挙動**: 政治・軍事報道中心の媒体のため、72時間ウィンドウでは感染症記事が 0 件で終わる週が多い。ローカル実行では RFA 30件 / BBC 34件取得 → 全件「古い記事」or「非健康記事」フィルタで除外、というパターンが続いている。**`fetch_intl_burmese(hours=...)` の引数を 72 → 168 (7日) や 336 (14日) に伸ばすと採用率が上がる可能性あり**。

### ⑥ Eleven Myanmar（2026-05-02 追加）
- ファイル: `jgrid-fetch/myanmar/fetch_eleven_myanmar.py`（本リポジトリ `myanmar/scripts/fetch_eleven_myanmar.py` に staging）
- 公式サイト: https://elevenmyanmar.com/ （Drupal ベース、英語版）
- **取得経路**: サイト全体 RSS (`/rss.xml`) は最新でも 2022 年で実質停止しているため、Drupal 標準の **キーワード検索 `/search/node/<keyword>`** を使う
  - 検索語 31 種（疾患名 + `outbreak` / `epidemic` / `vaccination` / `infectious` / `respiratory infection` / `acute diarrhoea`）
  - 各検索の 1 ページ目（最大 10 件）から `div.search-result > div.search-title a` を抽出 → 詳細ページへ
- 詳細ページから:
  - タイトル: `div.news-detail-title`（og:title はサイト名 "Eleven Media Group Co., Ltd" を返すケースがあるためフォールバック扱い）
  - 発行日時: `<span class="date-display-single" content="ISO8601">` の `content` 属性
  - 先頭段落: `div.field-name-body div.field-item p` ＞ `div.news-detail-content p` ＞ `article p` のフォールバック
- フィルタ:
  - 過去 180 日（環境変数 `ELEVEN_LOOKBACK_DAYS` で調整可）
  - GNLM/WHO Myanmar と同じ疾患語彙で再分類（検索結果は "outbreak" 等の汎用語で関係ない記事も拾うため）
- 翻訳: `deep_translator` (Google Translate) で headline / summary を EN→JA
- 出力: `dataSource: "Eleven Myanmar"`, `sourceName: "Eleven Myanmar"`
- `articleId` プレフィックス: `eleven_<sha1[:16]>`
- 実行時間目安: 約 200 秒（174 候補 URL × 詳細取得 + 翻訳）

---

## 4. 自動更新ワークフロー

`.github/workflows/myanmar.yml`（`jgrid-fetch` 側）:

```yaml
schedule:
  - cron: "22 21 * * *"   # 毎日 UTC 21:22 = JST 06:22
```

実行ステップ:
1. `jgrid-fetch` と `jgrid-pages` を両方 checkout（`JGRID_PAGES_TOKEN` でクロスリポジトリ書き込み）
2. Python 3.12 + `feedparser`, `python-dotenv`, `deep-translator`, `curl_cffi`, `requests`, `beautifulsoup4` をインストール
3. `python myanmar/fetch.py` で **Google News** を取得 → `myanmar_infectious_diseases.json`
4. `python myanmar/fetch_gnlm.py` で **GNLM** を取得 → `myanmar_gnlm.json`
5. **★ `python myanmar/fetch_who_myanmar.py` で WHO Myanmar/SEARO ニュースを取得 → `myanmar_who.json`**
6. **★ `python myanmar/fetch_who_searo_epi.py` で SEARO Epi Bulletin を取得 → `who_searo_epi.json`**
7. 4 つの JSON を `jgrid-pages/myanmar/data/` にコピー
8. `github-actions[bot]` 名義で commit & push（リトライ 3 回）

> 現時点 (2026-05-01 朝段階) では、リポジトリ上の最新 Myanmar データ commit は `2026-04-29T22:16:07Z` のもので **GNLM 追加前**。GNLM 連携の最初の反映は次回 cron 実行 = **2026-05-01 06:22 JST** 以降になる見込み。
>
> WHO Myanmar / SEARO Epi Bulletin の連携は **2026-05-01 にフロント実装＋fetcher を staging** したのみで、`jgrid-fetch` 側への配置と workflow 編集が未完。jgrid-fetch 側の作業手順は本ドキュメントの第 10 章を参照。

---

## 5. 表示の仕組み (`index.html` 側)

| 画面要素 | 取得先 | 状況 |
|---|---|---|
| WHO DON リスト（過去2週間） | `data/who_don.json` | ✅ 表示中 |
| **SEARO Epi Bulletin リスト（最新6号）** | `data/who_searo_epi.json` | ✅ **2026-05-01 実装** (DON の下、左カラム) |
| 統計バー / フィルタ / 州ヒートマップ / 記事リスト | `data/myanmar_infectious_diseases.json` + `data/myanmar_gnlm.json` + `data/myanmar_who.json` + `data/myanmar_eleven.json` + `data/myanmar_intl_burmese.json` を `mergeSources(...sources)` でマージ | ✅ 表示中 |
| GNLM 記事の表示 | `data/myanmar_gnlm.json` | ✅ **2026-05-01 実装** |
| **WHO Myanmar 記事の表示** | `data/myanmar_who.json` | ✅ **2026-05-01 実装** |
| **Eleven Myanmar 記事の表示** | `data/myanmar_eleven.json` | ✅ **2026-05-02 実装** |
| **RFA / BBC Burmese 記事の表示** | `data/myanmar_intl_burmese.json` | ✅ **2026-05-02 実装**（fetcher 自体は 2026-05-01 から稼働） |
| データソースバッジ（記事カード） | 各記事の `dataSource` フィールド | ✅ Google News（青）/ GNLM（黄）/ WHO（シアン）/ Eleven（ピンク）/ RFA（緑）/ BBC（赤） |
| データソースフィルタ | `dataSource` 値で絞り込み | ✅ |
| 記事サマリ表示 | `summary` / `summaryJa`（GNLM・WHO のみ提供） | ✅ 3行 line-clamp |
| CDC / 外務省 ボタン | ハードコード URL | ✅ |

**実装メモ（2026-05-01）**:
- `init()` を 3 並列 fetch（TopoJSON / gnews JSON / gnlm JSON）に拡張
- `fetchJsonOrNull()` で gnlm 404 を graceful fallback（次回 cron 実行までは gnews のみで動作）
- `mergeSources()` で 2 配列を `publishedTimestamp` 降順にマージ。`generated_at` は新しい方、`date_range` は和集合
- 重複検出は省略（`articleId` プレフィックス `gnews_` / `gnlm_` で衝突しない設計のため）
- フィルタバーに「ソース」ドロップダウン追加。3 言語の i18n キーも追加
- 記事カードに色付き `source-badge` と `summary` を追加
- 統計バーの「データソース数」は自動的に 1→2 になる（既存の `renderStats()` で対応済み）

---

## 6. 直近スナップショット観察 (GNLM 反映前)

`myanmar/data/myanmar_infectious_diseases.json`（生成 `2026-04-29T22:16 UTC`、3日間で 4 件）:

| 観察事項 | 詳細 | 含意 |
|---|---|---|
| 全件 `dataSource: "Google News"` | GNLM はまだ反映されていない | 次回 cron 実行で `myanmar_gnlm.json` が生成される予定 |
| 全件 "Malaria" | World Malaria Day（4/25）周辺の集中 | カレンダー連動の集積 |
| 全件 `states: ["Myanmar (region not identified)"]` | 地域抽出失敗 | 州別ヒートマップに反映されない |
| 見出しの地理的妥当性が低い | Nagaland (India), Gujarat (India), Kohima (India), Nepal の話題が中心 | Google News のクエリが「Myanmar」を含むがミャンマー国内事象ではない記事を拾っている。**GNLM 統合により国内記事比率は改善見込み** |

GNLM 連携の **狙い**（と推測）:
- Google News 由来の地理的ノイズ（インド・ネパール記事の混入）を相殺
- 州/管区抽出に有効な国内媒体テキストを供給（GNLM は地名表記が安定）
- `Acute Respiratory Infection` / `Acute Diarrhea` 等の症候群サーベイランス語をキーワード化したことで、未診断段階のシグナルも拾える設計

---

## 7. ファイル早見表

| パス | 役割 | 編集主体 |
|---|---|---|
| `jgrid-pages/myanmar/index.html` | ダッシュボード本体 | 手動 |
| `jgrid-pages/myanmar/data/myanmar_infectious_diseases.json` | Google News 由来記事 | 自動（fetch.py） |
| `jgrid-pages/myanmar/data/myanmar_gnlm.json` ★ | GNLM 由来記事（次回反映） | 自動（fetch_gnlm.py） |
| `jgrid-pages/myanmar/data/myanmar_who.json` ★★ | WHO Myanmar/SEARO 由来記事（2026-05-01 追加） | 自動（fetch_who_myanmar.py） |
| `jgrid-pages/myanmar/data/myanmar_eleven.json` ★★★ | Eleven Myanmar 由来記事（2026-05-02 追加） | 自動（fetch_eleven_myanmar.py） |
| `jgrid-pages/myanmar/data/myanmar_intl_burmese.json` | RFA / BBC ビルマ語放送記事（2026-05-01 fetcher、2026-05-02 frontend 統合） | 自動（fetch_intl_burmese.py） |
| `jgrid-pages/myanmar/data/who_don.json` | WHO DON（全国共通） | 自動（fetch_who_don.py） |
| `jgrid-pages/myanmar/data/who_searo_epi.json` ★★ | SEARO Epi Bulletin（隔週、2026-05-01 追加） | 自動（fetch_who_searo_epi.py） |
| `jgrid-pages/myanmar/scripts/fetch_who_myanmar.py` ★★ | **staging** — `jgrid-fetch/myanmar/` へ移動 | 手動 |
| `jgrid-pages/myanmar/scripts/fetch_who_searo_epi.py` ★★ | **staging** — `jgrid-fetch/myanmar/` へ移動 | 手動 |
| `jgrid-pages/myanmar/scripts/fetch_eleven_myanmar.py` ★★★ | **staging** — `jgrid-fetch/myanmar/` へ移動 | 手動 |
| `jgrid-fetch/myanmar/fetch.py` | Google News 収集 ETL | 手動 |
| `jgrid-fetch/myanmar/fetch_gnlm.py` ★ | GNLM 収集 ETL（2026-04-30 追加） | 手動 |
| `jgrid-fetch/.github/workflows/myanmar.yml` | 日次ワークフロー（cron） | 手動 |
| `jgrid-pages/README.md` | 全体構成 | 手動。**BlueDot 記載は実装と乖離。要更新** |

---

## 8. 関連リンク

- ダッシュボード: https://ts-biosecurity.github.io/jgrid-pages/myanmar/
- GNLM 公式: https://www.gnlm.com.mm/
- WHO Myanmar 国別ページ: https://www.who.int/myanmar
- WHO Myanmar ニュース: https://www.who.int/myanmar/news
- Eleven Myanmar (Eleven Media Group): https://elevenmyanmar.com/
- RFA Burmese RSS: https://www.rfa.org/burmese/rss2.xml
- BBC Burmese RSS: https://feeds.bbci.co.uk/burmese/rss.xml
- WHO SEARO Epi Bulletin 一覧: https://www.who.int/southeastasia/outbreaks-and-emergencies/surveillance-and-alert/sear-epi-bulletins
- WHO DON: https://www.who.int/emergencies/disease-outbreak-news
- CDC Travelers' Health (Myanmar/Burma): https://wwwnc.cdc.gov/travel/destinations/traveler/none/burma
- 外務省 感染症危険情報: https://www.anzen.mofa.go.jp/info/pcinfectionspothazardinfo_018.html
- TopoJSON 境界データ: https://raw.githubusercontent.com/markmarkoh/datamaps/master/src/js/data/mmr.topo.json

---

## 9. 関連コミット履歴 (GNLM 追加経緯、`jgrid-fetch` 2026-04-30)

```
5831ae9  feat: Add GNLM news source for Myanmar
3922e93  feat(myanmar): Add ARI and acute diarrhea keywords
bf5b0a7  fix(myanmar): Use word-boundary matching in classifiers
df0e6f0  fix(myanmar): Switch GNLM fetcher to requests with full browser headers
87bd404  fix(myanmar): Bypass Cloudflare with curl_cffi TLS impersonation
b40ea90  fix(myanmar): Try multiple impersonation profiles for GNLM
```

→ Cloudflare の bot 判定回避が一筋縄ではいかず、TLS fingerprint 偽装の段階的調整で安定化させた経緯が読み取れる。

---

## 10. WHO Myanmar / SEARO Epi Bulletin 投入手順 (2026-05-01)

フロントエンド (`jgrid-pages/myanmar/index.html`) と JSON 消費側はこの commit で実装済み。
`jgrid-fetch` (private) 側で以下を実施することで自動収集が稼働する。

### 10.1 fetcher の配置

```bash
# jgrid-fetch リポジトリで
cp ../jgrid-pages/myanmar/scripts/fetch_who_myanmar.py     myanmar/
cp ../jgrid-pages/myanmar/scripts/fetch_who_searo_epi.py   myanmar/
cp ../jgrid-pages/myanmar/scripts/fetch_eleven_myanmar.py  myanmar/
```

依存追加 (requirements.txt):
- `requests` (既存)
- `beautifulsoup4` ★新規
- `deep-translator` (既存)

### 10.2 workflow 編集

`jgrid-fetch/.github/workflows/myanmar.yml` の Run fetchers ステップに 2 行追加:

```yaml
- name: Fetch WHO Myanmar / SEARO news
  run: python myanmar/fetch_who_myanmar.py jgrid-pages/myanmar/data/

- name: Fetch SEARO Epi Bulletin
  run: python myanmar/fetch_who_searo_epi.py jgrid-pages/myanmar/data/

- name: Fetch Eleven Myanmar
  run: python myanmar/fetch_eleven_myanmar.py jgrid-pages/myanmar/data/
```

`pip install` ステップに `beautifulsoup4` を追加:

```yaml
run: pip install feedparser python-dotenv deep-translator curl_cffi requests beautifulsoup4
```

### 10.3 動作検証 (ローカル)

`jgrid-pages` ローカルで実行し、成果物を確認:

```bash
cd jgrid-pages/myanmar
python3 scripts/fetch_who_searo_epi.py    data/   # ~10秒、24件取得
python3 scripts/fetch_who_myanmar.py      data/   # ~60秒、~10件取得
python3 scripts/fetch_eleven_myanmar.py   data/   # ~200秒（174 候補 → 約8件、180日 lookback デフォルト）
```

`data/who_searo_epi.json` と `data/myanmar_who.json` が生成され、ブラウザで `index.html` を開くと:
- 上部 DON の下に **SEARO Epi Bulletin** カードが 6 件並ぶ
- 記事リストに **WHO Myanmar (シアンバッジ)** の記事が混入する
- フィルタ「ソース」プルダウンに `WHO Myanmar` が追加される

### 10.4 ハマりどころ

- WHO 公式サイトは Cloudflare 経由だが、現状（2026-05-01）は標準 `User-Agent` で 200 が返る。今後 403 化したら GNLM 同様 `curl_cffi` への切替検討
- SEARO Epi Bulletin の `iris.who.int` への PDF 直リンクは長期的に変わる可能性あり。ダッシュボード側は `pageUrl` を主、`pdfUrl` を補助として扱う設計
- 翻訳 API (Google Translate via deep_translator) は時々レート制限で `headlineJa` が空になる — 表示側はフォールバックで原文を表示する設計済み
