from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rows(mapping: dict[str, Any]) -> str:
    return "".join(f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>" for key, value in mapping.items())


def write_html_report(report: dict[str, Any], path: Path) -> None:
    summary = {
        "Records read": report["records_read"],
        "Would keep / kept": report["records_kept"],
        "Would reject / rejected": report["records_rejected"],
        "Transformed": report["records_transformed"],
        "Characters": report["characters_read"],
        "Elapsed seconds": report["elapsed_seconds"],
        "Records/second": report["throughput_records_per_second"],
        "Reconciliation": "PASS" if report["reconciliation_ok"] else "FAIL",
    }
    finding_rows = _rows(report["findings_by_code"] or {"No findings": 0})
    script_rows = _rows(report["script_totals"] or {"No script letters observed": 0})
    ratio_rows = _rows(report["script_ratio_buckets"] or {"Not applicable": 0})
    threshold_preview = {
        threshold: f"{details['records_below']} records ({details['percentage']}%)"
        for threshold, details in report["script_threshold_preview"].items()
    }
    profile_details = {
        "Name": report["profile_details"]["name"],
        "Target scripts": ", ".join(report["profile_details"]["target_scripts"]) or "unrestricted",
        "Allowed secondary": ", ".join(report["profile_details"]["allowed_secondary_scripts"]) or "none",
    }
    length_rows = _rows(report["length_statistics"])
    cards = []
    for code, examples in report["examples_by_code"].items():
        items = "".join(
            "<li><strong>Record " + str(example["record"]) + "</strong><pre>" + html.escape(example["text"]) + "</pre></li>"
            for example in examples
        )
        cards.append(f"<section><h3>{html.escape(code)}</h3><ul>{items}</ul></section>")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CorpusLens report</title><style>
:root{{--ink:#18212f;--muted:#607086;--surface:#fff;--bg:#f4f6f8;--accent:#635bff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1080px;margin:auto;padding:40px 20px}} h1{{margin-bottom:4px}} .lede{{color:var(--muted);margin-top:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}} section{{background:var(--surface);border:1px solid #dfe4ea;border-radius:12px;padding:18px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}} td{{padding:7px;border-bottom:1px solid #edf0f3}} td:last-child{{text-align:right;font-variant-numeric:tabular-nums}}
pre{{white-space:pre-wrap;background:#f7f8fb;border-radius:8px;padding:10px;max-height:180px;overflow:auto}} ul{{padding-left:20px}}
.pass{{color:#087443;font-weight:700}} code{{color:var(--accent)}}
</style></head><body><main>
<h1>CorpusLens report</h1><p class="lede">{html.escape(report['input_path'])} · profile <code>{html.escape(report['policy']['profile'])}</code></p>
<div class="grid"><section><h2>Run summary</h2><table>{_rows(summary)}</table></section>
<section><h2>Profile</h2><table>{_rows(profile_details)}</table></section>
<section><h2>Findings</h2><table>{finding_rows}</table></section>
<section><h2>Scripts observed</h2><table>{script_rows}</table></section>
<section><h2>Target-script ratio</h2><table>{ratio_rows}</table></section>
<section><h2>Threshold preview</h2><p class="lede">Records below each possible minimum; review examples before rejecting.</p><table>{_rows(threshold_preview or {'Not applicable': 0})}</table></section>
<section><h2>Length distribution</h2><table>{length_rows}</table></section></div>
<h2>Representative findings</h2>{''.join(cards) if cards else '<p>No findings were recorded.</p>'}
</main></body></html>"""
    path.write_text(document, encoding="utf-8")
