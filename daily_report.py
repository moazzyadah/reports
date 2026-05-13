#!/usr/bin/env python3
"""
Daily Ads Report — يشتغل كل يوم الساعة 8 الصبح
يجيب أداء الإعلانات لليوم اللي فات لكل الحسابات المحددة
Output: نص عربي جاهز للـ WhatsApp
"""

import asyncio
import json
import sys
import os
import urllib.parse
from datetime import datetime, timedelta, date
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from brands_config import BRANDS

TOKEN = os.getenv("META_SYSTEM_USER_TOKEN", "")
API_VERSION = os.getenv("META_API_VERSION", "v25.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"

AD_FIELDS = (
    "spend,impressions,reach,frequency,clicks,ctr,cpm,cpc,"
    "actions,cost_per_action_type,quality_ranking,"
    "engagement_rate_ranking,conversion_rate_ranking"
)


async def get(client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
    params["access_token"] = TOKEN
    url = f"{BASE}/{endpoint}" if not endpoint.startswith("http") else endpoint
    try:
        r = await client.get(url, params=params, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


async def get_ad_account_insights(client: httpx.AsyncClient, account_id: str, since: str, until: str) -> dict:
    """Get account-level ad metrics for a date range."""
    return await get(client, f"{account_id}/insights", {
        "fields": AD_FIELDS,
        "level": "account",
        "time_range": json.dumps({"since": since, "until": until}),
    })


async def get_active_campaigns(client: httpx.AsyncClient, account_id: str, since: str, until: str) -> list:
    """Get campaign-level breakdown for active campaigns."""
    result = await get(client, f"{account_id}/insights", {
        "fields": "campaign_name,spend,impressions,actions,cost_per_action_type,ctr,cpm",
        "level": "campaign",
        "time_range": json.dumps({"since": since, "until": until}),
        "sort": "spend_descending",
        "limit": 5,
    })
    return result.get("data", [])


def extract_results(actions: list, cost_per_action: list) -> tuple[int, float]:
    """Extract primary results count and cost from actions array."""
    result_actions = [
        "onsite_conversion.messaging_conversation_started_7d",
        "onsite_conversion.lead_grouped",
        "lead",
        "link_click",
    ]
    total = 0
    cost = 0.0
    for action in (actions or []):
        if action.get("action_type") in result_actions:
            try:
                total += int(float(action.get("value", 0)))
            except (ValueError, TypeError):
                pass
    for cp in (cost_per_action or []):
        if cp.get("action_type") in result_actions:
            try:
                cost = float(cp.get("value", 0))
                break
            except (ValueError, TypeError):
                pass
    return total, cost


def fmt_currency(val: float, currency: str = "TRY") -> str:
    symbol = "₺" if currency == "TRY" else "$"
    return f"{symbol}{val:,.1f}"


def fmt_pct(val: float) -> str:
    return f"{val:.2f}%"


async def build_brand_daily(client: httpx.AsyncClient, brand_key: str, brand: dict, yesterday: str) -> str:
    account_id = brand["ad_account"]
    currency = brand["currency"]
    brand_name = brand["name"]

    data = await get_ad_account_insights(client, account_id, yesterday, yesterday)

    if data.get("error") or not data.get("data"):
        return f"⚠️ *{brand_name}*: لا توجد بيانات إعلانية أمس"

    d = data["data"][0]
    spend = float(d.get("spend", 0))

    if spend < 1:
        return f"💤 *{brand_name}*: لا يوجد إنفاق أمس"

    impressions = int(d.get("impressions", 0))
    reach = int(d.get("reach", 0))
    ctr = float(d.get("ctr", 0))
    cpm = float(d.get("cpm", 0))
    cpc = float(d.get("cpc", 0))
    freq = float(d.get("frequency", 0))

    results, cpr = extract_results(
        d.get("actions", []),
        d.get("cost_per_action_type", [])
    )

    # Quality rankings
    qr = d.get("quality_ranking", "")
    er = d.get("engagement_rate_ranking", "")
    cr = d.get("conversion_rate_ranking", "")
    ranking_map = {
        "ABOVE_AVERAGE": "↑",
        "AVERAGE": "→",
        "BELOW_AVERAGE_10": "↓",
        "BELOW_AVERAGE_20": "↓↓",
        "BELOW_AVERAGE_35": "↓↓↓",
    }
    rankings = f"{ranking_map.get(qr,'?')} جودة | {ranking_map.get(er,'?')} تفاعل | {ranking_map.get(cr,'?')} تحويل"

    # Top campaigns
    campaigns = await get_active_campaigns(client, account_id, yesterday, yesterday)
    camp_lines = []
    for c in campaigns[:3]:
        c_spend = float(c.get("spend", 0))
        c_results, c_cpr = extract_results(
            c.get("actions", []),
            c.get("cost_per_action_type", [])
        )
        c_name = c.get("campaign_name", "")[:30]
        if c_results > 0:
            camp_lines.append(f"  • {c_name}: {fmt_currency(c_spend, currency)} → {c_results} نتيجة ({fmt_currency(c_cpr, currency)}/نتيجة)")
        else:
            camp_lines.append(f"  • {c_name}: {fmt_currency(c_spend, currency)} (بدون نتائج)")

    lines = [
        f"📊 *{brand_name}*",
        f"💰 إنفاق: {fmt_currency(spend, currency)} | وصل: {reach:,} | {impressions:,} ظهور",
        f"🎯 CTR: {fmt_pct(ctr)} | CPM: {fmt_currency(cpm, currency)} | تكرار: {freq:.1f}x",
    ]
    if results > 0:
        lines.append(f"✅ نتائج: {results} | تكلفة/نتيجة: {fmt_currency(cpr, currency)}")
    if camp_lines:
        lines.append("📋 أكبر 3 حملات:")
        lines.extend(camp_lines)

    return "\n".join(lines)


async def main():
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    day_label = (date.today() - timedelta(days=1)).strftime("%d/%m/%Y")

    brands_to_report = sys.argv[1:] if len(sys.argv) > 1 else list(BRANDS.keys())

    sections = [f"📅 *تقرير الإعلانات اليومي — {day_label}*\n{'─'*30}"]

    async with httpx.AsyncClient() as client:
        tasks = [
            build_brand_daily(client, key, BRANDS[key], yesterday)
            for key in brands_to_report
            if key in BRANDS
        ]
        results = await asyncio.gather(*tasks)

    sections.extend(results)
    sections.append(f"{'─'*30}\n🕗 تم التوليد: {datetime.now().strftime('%H:%M')}")

    print("\n\n".join(sections))


if __name__ == "__main__":
    asyncio.run(main())
