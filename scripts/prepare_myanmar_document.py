"""Prepare only the Myanmar Markdown page; never alter the source or static site."""
from pathlib import Path
import sys

destination = Path(sys.argv[1])
destination.mkdir(parents=True, exist_ok=True)
source = Path("myanmar/data_pipeline.md").read_text(encoding="utf-8")
if source.startswith("---\n"):
    raise SystemExit("Document now has front matter; review preparation before deployment.")
(destination / "data_pipeline.md").write_text(
    '---\nlayout: document\npermalink: /myanmar/data_pipeline.html\n'
    'title: "ミャンマー 感染症ニュース取得の仕組み"\n---\n\n' + source,
    encoding="utf-8",
)
layouts = destination / "_layouts"
layouts.mkdir(exist_ok=True)
(layouts / "document.html").write_text(
    '<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>{{ page.title | escape }}</title>'
    '<style>body{max-width:1100px;margin:32px auto;padding:0 20px;'
    'font-family:system-ui,sans-serif;line-height:1.7;overflow-wrap:anywhere}'
    'table{display:block;overflow-x:auto;border-collapse:collapse}'
    'th,td{border:1px solid #ccc;padding:8px;text-align:left}'
    'pre{overflow:auto;background:#f5f5f5;padding:16px}'
    'img{max-width:100%}a{color:#075ea8}</style></head>'
    '<body><nav><a href="./">ミャンマーダッシュボードへ</a></nav>'
    '<main>{{ content }}</main></body></html>\n',
    encoding="utf-8",
)
(destination / "_config.yml").write_text(
    "markdown: kramdown\nplugins: []\n", encoding="utf-8"
)

