#!/usr/bin/env python3
"""Daily Ads Report — account + active campaigns lifetime summary."""

import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from brands_config import BRANDS

TOKEN = os.getenv("META_SYSTEM_USER_TOKEN", "")
BASE = f"https://graph.facebook.com/v25.0"

# Ordered priority — first match wins (no summing across types)
RESULT_PRIORITY = [
    "onsite_conversion.messaging_conversation_started_7d",
    "onsite_conversion.lead_grouped",
    "lead",
    "omni_purchase",
    "link_click",
]


async def api_get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    params["access_token"] = TOKEN
    try:
        r = await client.get(f"{BASE}/{path}", params=params, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def extract_primary_result(actions: list, cost_per_action: list) -> tuple[str, int, float]:
    """Return (action_label, count, cost) for the highest-priority action found."""
    action_map = {a["action_type"]: int(float(a.get("value", 0))) for a in (actions or [])}
    cost_map = {c["action_type"]: float(c.get("value", 0)) for c in (cost_per_action or [])}

    labels = {
        "onsite_conversion.messaging_conversation_started_7d": "رسالة",
        "onsite_conversion.lead_grouped": "ليد",
        "lead": "ليد",
        "omni_purchase": "شراء",
        "link_click": "كليك",
    }

    for action_type in RESULT_PRIORITY:
        if action_type in action_map and action_map[action_type] > 0:
            return labels[action_type], action_map[action_type], cost_map.get(action_type, 0.0)

    return "نتيجة", 0, 0.0


async def get_account_yesterday(client: httpx.AsyncClient, account_id: str, yesterday: str) -> dict:
    return await api_get(client, f"{account_id}/insights", {
        "fields": "spend,actions,cost_per_action_type",
        "level": "account",
        "time_range": json.dumps({"since": yesterday, "until": yesterday}),
    })


async def get_active_campaigns_lifetime(client: httpx.AsyncClient, account_id: str) -> list:
    """Active campaigns with their full lifetime stats (date_preset=maximum)."""
    result = await api_get(client, f"{account_id}/insights", {
        "fields": "campaign_name,spend,actions,cost_per_action_type",
        "level": "campaign",
        "date_preset": "maximum",
        "filtering": json.dumps([{
            "field": "campaign.effective_status",
            "operator": "IN",
            "value": ["ACTIVE"],
        }]),
        "sort": "spend_descending",
        "limit": 10,
    })
    return result.get("data", [])


def fmt(val: float, currency: str = "TRY") -> str:
    sym = "₺" if currency == "TRY" else "$"
    return f"{sym}{val:,.1f}"


async def build_brand(client: httpx.AsyncClient, brand: dict, yesterday: str) -> str:
    account_id = brand["ad_account"]
    currency = brand["currency"]
    name = brand["name"]

    yesterday_data, campaigns = await asyncio.gather(
        get_account_yesterday(client, account_id, yesterday),
        get_active_campaigns_lifetime(client, account_id),
    )

    lines = [f"━━━━━━━━━━━\n*{name}*"]

    # ── أمس ──
    d_list = yesterday_data.get("data", [])
    if not d_list or float((d_list[0] if d_list else {}).get("spend", 0)) < 1:
        lines.append("📅 أمس: لا يوجد إنفاق")
    else:
        d = d_list[0]
        spend = float(d.get("spend", 0))
        label, count, cpr = extract_primary_result(
            d.get("actions", []), d.get("cost_per_action_type", [])
        )
        yesterday_line = f"📅 *أمس:* {fmt(spend, currency)} إنفاق"
        if count > 0:
            yesterday_line += f" | {count} {label} | {fmt(cpr, currency)}/{label}"
        else:
            yesterday_line += " | لا نتائج"
        lines.append(yesterday_line)

    # ── الحملات الشغالة (Lifetime) ──
    if campaigns:
        lines.append("📈 *الحملات الشغالة (منذ بدء تشغيلها):*")
        for c in campaigns:
            c_spend = float(c.get("spend", 0))
            label, count, cpr = extract_primary_result(
                c.get("actions", []), c.get("cost_per_action_type", [])
            )
            c_name = c.get("campaign_name", "")[:40]
            if count > 0:
                lines.append(f"  • {c_name}\n    {fmt(c_spend, currency)} | {count:,} {label} | {fmt(cpr, currency)}/{label}")
            else:
                lines.append(f"  • {c_name}\n    {fmt(c_spend, currency)} | لا نتائج")
    else:
        lines.append("📈 لا توجد حملات نشطة حالياً")

    return "\n".join(lines)


async def main():
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    day_label = (date.today() - timedelta(days=1)).strftime("%d/%m/%Y")

    brands_to_report = sys.argv[1:] if len(sys.argv) > 1 else list(BRANDS.keys())

    header = f"📊 *تقرير الإعلانات | {day_label}*"

    async with httpx.AsyncClient() as client:
        tasks = [build_brand(client, BRANDS[k], yesterday) for k in brands_to_report if k in BRANDS]
        results = await asyncio.gather(*tasks)

    footer = f"\n🕗 {datetime.now().strftime('%H:%M')}"
    print("\n\n".join([header] + list(results)) + footer)


if __name__ == "__main__":
    asyncio.run(main())
