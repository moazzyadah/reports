#!/usr/bin/env python3
"""
Generate docs/index.html from data/latest.json
Runs in GitHub Actions after fetch_data.py
"""

import json
from pathlib import Path
from datetime import datetime

data = json.loads(Path("data/latest.json").read_text())
report_date = data["date"]
fetched_at = data.get("fetched_at", "")[:16].replace("T", " ") + " UTC"

BRANDS_META = {
    "feluka":       {"emoji": "", "logo_dark": "logos/feluka-white.png",    "logo_light": "logos/feluka-color.png",    "color": "#e8a020"},
    "edvion":       {"emoji": "", "logo_dark": "logos/edvion-light.png",    "logo_light": "logos/edvion-dark.png",     "color": "#2563eb"},
    "mustakbal":    {"emoji": "", "logo_dark": "logos/mustakbal-white.png", "logo_light": "logos/mustakbal-color.png", "color": "#7c3aed"},
    "adventurers":  {"emoji": "🏕️", "logo_dark": None, "logo_light": None,  "color": "#059669"},
    "wsool":        {"emoji": "", "logo_dark": "logos/wsool-light.png",     "logo_light": "logos/wsool-dark.png",      "color": "#0891b2"},
}

RESULT_LABELS = {
    "onsite_conversion.messaging_conversation_started_7d": "رسالة",
    "onsite_conversion.lead_grouped": "ليد",
    "lead": "ليد",
    "omni_purchase": "شراء",
    "link_click": "كليك",
    "post_engagement": "تفاعل",
}

OBJECTIVE_LABELS = {
    "MESSAGES": "رسائل",
    "LEAD_GENERATION": "ليدز",
    "LINK_CLICKS": "كليكات",
    "CONVERSIONS": "تحويلات",
    "BRAND_AWARENESS": "وعي",
    "REACH": "وصول",
    "POST_ENGAGEMENT": "تفاعل",
    "VIDEO_VIEWS": "مشاهدات",
    "PAGE_LIKES": "إعجابات",
    "OUTCOME_TRAFFIC": "زيارات",
    "OUTCOME_LEADS": "ليدز",
    "OUTCOME_ENGAGEMENT": "تفاعل",
    "OUTCOME_AWARENESS": "وعي",
    "OUTCOME_SALES": "مبيعات",
}


def fmt_num(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}"


def fmt_currency(v, currency="TRY"):
    sym = "₺" if currency == "TRY" else "$"
    return f"{sym}{v:,.2f}".rstrip("0").rstrip(".")


def get_primary_result(d: dict) -> tuple:
    """Return (label, count, cpr) for the most important action in data dict."""
    priority = [
        "onsite_conversion.messaging_conversation_started_7d",
        "onsite_conversion.lead_grouped",
        "lead",
        "omni_purchase",
        "link_click",
    ]
    for at in priority:
        count = d.get(f"count_{at}", 0)
        if count and count > 0:
            cpr = d.get(f"cpr_{at}", 0)
            return RESULT_LABELS.get(at, at), int(count), float(cpr)
    return None, 0, 0.0


def delta_class(pct):
    if pct <= -15:
        return "delta-good", f"↓ {abs(pct):.0f}% أقل ✓"
    if pct >= 30:
        return "delta-bad", f"↑ {pct:.0f}% أعلى ⚠️"
    return "delta-ok", f"{'↑' if pct > 0 else '↓'} {abs(pct):.0f}%"


def render_brand(brand: dict) -> str:
    key = brand["key"]
    name = brand["name"]
    currency = brand["currency"]
    meta = BRANDS_META.get(key, {"emoji": "📊", "logo_dark": None, "logo_light": None, "color": "#64748b"})

    yesterday = brand.get("yesterday", {})
    campaigns = brand.get("active_campaigns_lifetime", [])

    spend_y = float(yesterday.get("spend", 0))
    label_y, count_y, cpr_y = get_primary_result(yesterday)

    # Pills
    if spend_y < 1:
        pills_html = '<span class="pill pill-inactive">لا إنفاق أمس</span>'
        yesterday_row = ""
    else:
        pills_html = f"""
            <span class="pill pill-spend">{fmt_currency(spend_y, currency)}</span>
            {"" if not label_y else f'<span class="pill pill-result">{fmt_num(count_y)} {label_y}</span>'}
            {"" if not label_y or cpr_y == 0 else f'<span class="pill pill-cpr">{fmt_currency(cpr_y, currency)}/{label_y}</span>'}
        """
        yesterday_row = ""  # shown in pills

    # Logo
    logo_dark = meta.get("logo_dark")
    logo_light = meta.get("logo_light")
    logo_html = ""
    if logo_dark:
        logo_html = f"""
        <picture>
          <source srcset="{logo_dark}" media="(prefers-color-scheme: dark)">
          <img src="{logo_light or logo_dark}" alt="{name}" class="brand-logo">
        </picture>"""
    else:
        logo_html = f'<span class="brand-emoji">{meta["emoji"]}</span>'

    # Campaigns rows
    camp_rows = ""
    alerts = []
    for c in campaigns:
        c_spend = float(c.get("spend", 0))
        if c_spend < 1:
            continue
        c_label, c_count, c_cpr = get_primary_result(c)
        c_name = c.get("name", "")
        c_obj = OBJECTIVE_LABELS.get(c.get("objective", ""), c.get("objective", ""))
        c_reach = int(c.get("reach", 0))
        c_freq = float(c.get("frequency", 0))
        c_eng = int(c.get("count_post_engagement", 0) or 0)

        # Build metrics cell based on objective
        obj_raw = c.get("objective", "")
        if c_count and c_count > 0:
            metrics_html = f"""
                <div class="metric-row">
                    <span class="metric-label">Lifetime</span>
                    <span class="metric-val">{fmt_num(c_count)} {c_label} | {fmt_currency(c_cpr, currency)}/{c_label}</span>
                </div>"""
            # delta vs yesterday
            if label_y and c_label == label_y and cpr_y > 0 and c_cpr > 0:
                pct = ((cpr_y - c_cpr) / c_cpr) * 100
                dcls, dtxt = delta_class(pct)
                metrics_html += f'<div class="metric-row"><span class="metric-label">CPR أمس</span><span class="{dcls}">{dtxt}</span></div>'
                if pct >= 30:
                    alerts.append(f"CPR أمس أعلى بـ {pct:.0f}% عن الـ Lifetime في «{c_name[:25]}»")
        else:
            # Awareness/engagement
            metrics_html = f"""
                <div class="metric-row">
                    <span class="metric-label">Reach</span>
                    <span class="metric-val">{fmt_num(c_reach)}</span>
                </div>"""
            if c_eng:
                metrics_html += f'<div class="metric-row"><span class="metric-label">تفاعل</span><span class="metric-val">{fmt_num(c_eng)}</span></div>'

        if c_freq > 0:
            freq_cls = ' style="color:#f87171"' if c_freq >= 4 else ""
            metrics_html += f'<div class="metric-row"><span class="metric-label">Frequency</span><span class="metric-val"{freq_cls}>{c_freq:.2f}</span></div>'
            if c_freq >= 4:
                alerts.append(f"Frequency {c_freq:.1f} في «{c_name[:25]}» — تعب جمهور")

        camp_rows += f"""
        <tr>
          <td>
            <div class="camp-name">{c_name}</div>
            <div class="camp-obj">{c_obj} | {fmt_currency(c_spend, currency)}</div>
          </td>
          <td>{metrics_html}</td>
        </tr>"""

    # Alerts HTML
    alerts_html = ""
    for a in alerts:
        alerts_html += f'<div class="camp-alert">⚠️ {a}</div>'

    color = meta["color"]
    return f"""
  <div class="brand-card" style="--brand-color:{color}">
    <div class="brand-header" onclick="this.closest('.brand-card').classList.toggle('open')">
      <div class="brand-identity">
        {logo_html}
        <span class="brand-name">{name}</span>
      </div>
      <div class="brand-pills">
        {pills_html}
        <span class="chevron">▾</span>
      </div>
    </div>
    <div class="brand-body">
      {alerts_html}
      {"<p class='no-data'>لا توجد حملات نشطة</p>" if not camp_rows else f'''
      <table class="camp-table">
        <thead><tr><th>الحملة</th><th>الأداء</th></tr></thead>
        <tbody>{camp_rows}</tbody>
      </table>'''}
    </div>
  </div>"""


# Build all brands
brands_html = "\n".join(render_brand(b) for b in data["brands"])

# Format date nicely
try:
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    months = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
    date_label = f"{dt.day} {months[dt.month-1]} {dt.year}"
except Exception:
    date_label = report_date

html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>تقرير الإعلانات — {date_label} | Wsool للتسويق والأتمتة</title>
<style>
:root {{
  --bg: #090c14;
  --bg2: #111827;
  --bg3: #1a2033;
  --border: #1f2a3d;
  --text: #e2e8f0;
  --text2: #94a3b8;
  --text3: #475569;
  --green: #22c55e;
  --red: #f87171;
  --yellow: #fbbf24;
}}
@media (prefers-color-scheme: light) {{
  :root {{
    --bg: #f1f5f9;
    --bg2: #ffffff;
    --bg3: #f8fafc;
    --border: #e2e8f0;
    --text: #0f172a;
    --text2: #475569;
    --text3: #94a3b8;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, 'Segoe UI', Arial, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}

/* TOP BAR */
.topbar {{
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(8px);
}}
.topbar-title {{ font-size: .9rem; font-weight: 700; color: var(--text); letter-spacing: -.01em; }}
.topbar-date {{ font-size: .8rem; color: var(--text2); }}
.topbar-badge {{
  font-size: .7rem;
  background: #0f2d1a;
  color: var(--green);
  border: 1px solid #166534;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 600;
}}

.container {{ max-width: 900px; margin: 0 auto; padding: 24px 16px; }}

/* SUMMARY ROW */
.summary-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}}
.summary-card {{
  background: var(--bg2);
  border: 1px solid var(--border);
  border-top: 3px solid var(--brand-color, #334155);
  border-radius: 10px;
  padding: 14px 16px;
}}
.summary-brand {{ font-size: .72rem; color: var(--text2); margin-bottom: 6px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }}
.summary-spend {{ font-size: 1.1rem; font-weight: 700; color: var(--text); }}
.summary-result {{ font-size: .78rem; color: var(--green); margin-top: 3px; }}

/* BRAND CARDS */
.brand-card {{
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 14px;
  overflow: hidden;
  transition: box-shadow .2s;
}}
.brand-card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,.25); }}

.brand-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  cursor: pointer;
  border-bottom: 2px solid var(--brand-color, var(--border));
  gap: 12px;
}}
.brand-header:hover {{ background: var(--bg3); }}

.brand-identity {{ display: flex; align-items: center; gap: 12px; }}
.brand-logo {{ height: 32px; width: auto; max-width: 110px; object-fit: contain; }}
.brand-emoji {{ font-size: 1.4rem; }}
.brand-name {{ font-size: 1rem; font-weight: 700; color: var(--text); }}

.brand-pills {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
.pill {{ padding: 4px 12px; border-radius: 20px; font-size: .78rem; font-weight: 600; white-space: nowrap; }}
.pill-spend {{ background: var(--bg3); color: var(--text2); border: 1px solid var(--border); }}
.pill-result {{ background: #0f2d1a; color: #4ade80; border: 1px solid #166534; }}
.pill-cpr {{ background: #1a1a2e; color: #818cf8; border: 1px solid #3730a3; }}
.pill-inactive {{ background: var(--bg3); color: var(--text3); border: 1px solid var(--border); }}

.chevron {{ color: var(--text3); font-size: 1.1rem; transition: transform .2s; flex-shrink: 0; }}
.brand-card.open .chevron {{ transform: rotate(180deg); }}
.brand-body {{ display: none; padding: 16px 20px; }}
.brand-card.open .brand-body {{ display: block; }}

/* CAMP TABLE */
.camp-table {{ width: 100%; border-collapse: collapse; }}
.camp-table th {{
  text-align: right;
  font-size: .7rem;
  font-weight: 600;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: .05em;
  padding: 0 10px 10px;
  border-bottom: 1px solid var(--border);
}}
.camp-table td {{ padding: 12px 10px; border-bottom: 1px solid var(--bg3); vertical-align: top; }}
.camp-table tr:last-child td {{ border-bottom: none; }}
.camp-name {{ font-size: .87rem; font-weight: 600; color: var(--text); margin-bottom: 2px; }}
.camp-obj {{ font-size: .73rem; color: var(--text3); }}

.metric-row {{ display: flex; gap: 8px; align-items: baseline; margin-bottom: 3px; font-size: .82rem; }}
.metric-label {{ color: var(--text3); min-width: 70px; font-size: .73rem; }}
.metric-val {{ color: var(--text2); }}

.delta-good {{ color: var(--green); font-weight: 600; }}
.delta-bad {{ color: var(--red); font-weight: 600; }}
.delta-ok {{ color: var(--text2); }}

.camp-alert {{
  background: #1a0f00;
  border: 1px solid #78350f;
  border-right: 3px solid var(--yellow);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: .82rem;
  color: var(--yellow);
  margin-bottom: 10px;
}}
.no-data {{ color: var(--text3); font-size: .85rem; padding: 8px 0; }}

footer {{ text-align: center; padding: 32px 0 20px; font-size: .72rem; color: var(--text3); }}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-title">📊 تقرير الإعلانات</div>
  <div class="topbar-date">{date_label}</div>
  <div class="topbar-badge">Live Data</div>
</div>

<div class="container">

  <!-- Summary -->
  <div class="summary-grid">
{"".join(
    f'''    <div class="summary-card" style="--brand-color:{BRANDS_META.get(b['key'],{}).get('color','#334155')}">
      <div class="summary-brand">{b['name']}</div>
      <div class="summary-spend">{fmt_currency(float(b['yesterday'].get('spend',0)), b['currency'])}</div>
      <div class="summary-result">{(lambda l,c,p: f'{fmt_num(c)} {l} | {fmt_currency(p, b["currency"])}/{l}' if c > 0 else 'لا إنفاق')(*get_primary_result(b['yesterday']))}</div>
    </div>'''
    for b in data['brands']
)}
  </div>

  <!-- Brand Cards -->
{brands_html}

</div>

<footer>
  <div style="margin-bottom:6px;font-size:.8rem;color:var(--text2)">تقرير آلي يومي</div>
  <div>تصميم وتنفيذ <a href="https://wsool.ai" style="color:#0891b2;text-decoration:none;font-weight:600">Wsool للتسويق والأتمتة</a></div>
  <div style="margin-top:4px">{fetched_at}</div>
</footer>

<script>
// Open first card by default
document.querySelector('.brand-card')?.classList.add('open');
</script>
</body>
</html>"""

Path("docs/index.html").write_text(html, encoding="utf-8")
print("✓ docs/index.html generated")
