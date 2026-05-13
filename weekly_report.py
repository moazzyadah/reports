#!/usr/bin/env python3
"""
Weekly Report — يشتغل كل أسبوع (الأحد مثلاً)
يجيب أداء الإعلانات + الأورجانيك (FB Page + IG) للأسبوع اللي فات
لكل البراندات المحددة
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

from brands_config import BRANDS, FB_PAGE_METRICS, IG_METRICS_TOTAL

TOKEN = os.getenv("META_SYSTEM_USER_TOKEN", "")
API_VERSION = os.getenv("META_API_VERSION", "v25.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"

AD_FIELDS = "spend,impressions,reach,clicks,ctr,cpm,actions,cost_per_action_type"


async def get(client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
    params["access_token"] = TOKEN
    url = f"{BASE}/{endpoint}" if not endpoint.startswith("http") else endpoint
    try:
        r = await client.get(url, params=params, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── Page Token Cache ─────────────────────────────────────────────────────────

_page_tokens: dict[str, str] = {}


async def get_page_token(client: httpx.AsyncClient, page_id: str) -> str:
    if page_id not in _page_tokens:
        result = await get(client, "me/accounts", {"fields": "id,access_token", "limit": 50})
        for p in result.get("data", []):
            _page_tokens[p["id"]] = p["access_token"]
    return _page_tokens.get(page_id, TOKEN)


# ── Ad Insights ──────────────────────────────────────────────────────────────

def extract_results(actions: list, cost_per_action: list) -> tuple[int, float]:
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


async def get_weekly_ads(client: httpx.AsyncClient, account_id: str, since: str, until: str) -> dict:
    result = await get(client, f"{account_id}/insights", {
        "fields": AD_FIELDS,
        "level": "account",
        "time_range": json.dumps({"since": since, "until": until}),
    })
    if result.get("error") or not result.get("data"):
        return {}
    return result["data"][0]


async def get_top_campaigns(client: httpx.AsyncClient, account_id: str, since: str, until: str) -> list:
    result = await get(client, f"{account_id}/insights", {
        "fields": "campaign_name,spend,impressions,actions,cost_per_action_type,ctr,cpm",
        "level": "campaign",
        "time_range": json.dumps({"since": since, "until": until}),
        "sort": "spend_descending",
        "limit": 5,
    })
    return result.get("data", [])


# ── FB Page Organic ───────────────────────────────────────────────────────────

async def get_fb_organic(client: httpx.AsyncClient, page_id: str, since: str, until: str) -> dict:
    """Get FB page organic metrics summed over the week."""
    page_token = await get_page_token(client, page_id)

    # Get daily values and sum
    params = {
        "metric": ",".join(FB_PAGE_METRICS),
        "period": "day",
        "since": since,
        "until": until,
        "access_token": page_token,
    }
    url = f"{BASE}/{page_id}/insights"
    try:
        r = await client.get(url, params=params, timeout=30)
        data = r.json()
    except Exception as e:
        return {"error": str(e)}

    if data.get("error"):
        return {}

    totals = {}
    for metric in data.get("data", []):
        name = metric["name"]
        total = 0
        for v in metric.get("values", []):
            val = v.get("value", 0)
            if isinstance(val, dict):
                total += sum(val.values())
            else:
                total += int(val or 0)
        totals[name] = total

    # Get follower count (current snapshot)
    page_data = await get(client, page_id, {"fields": "fan_count", "access_token": page_token})
    totals["fan_count"] = page_data.get("fan_count", 0)

    return totals


# ── IG Organic ────────────────────────────────────────────────────────────────

async def get_ig_organic(client: httpx.AsyncClient, ig_id: str, since: str, until: str) -> dict:
    """Get IG account metrics for the week."""
    totals = {}

    # Batch metrics that use metric_type=total_value
    params = {
        "metric": ",".join(IG_METRICS_TOTAL),
        "period": "day",
        "metric_type": "total_value",
        "since": since,
        "until": until,
        "access_token": TOKEN,
    }
    url = f"{BASE}/{ig_id}/insights"
    try:
        r = await client.get(url, params=params, timeout=30)
        data = r.json()
    except Exception as e:
        return {"error": str(e)}

    if not data.get("error"):
        for metric in data.get("data", []):
            # total_value response structure
            total_val = metric.get("total_value", {})
            if isinstance(total_val, dict):
                totals[metric["name"]] = total_val.get("value", 0)
            else:
                # fallback: sum daily values
                total = sum(
                    v.get("value", 0) for v in metric.get("values", [])
                    if isinstance(v.get("value"), (int, float))
                )
                totals[metric["name"]] = total

    # follower count — current snapshot
    ig_data = await get(client, ig_id, {"fields": "followers_count,media_count"})
    totals["followers_count"] = ig_data.get("followers_count", 0)
    totals["media_count"] = ig_data.get("media_count", 0)

    return totals


# ── Brand Report Builder ──────────────────────────────────────────────────────

def fmt_currency(val: float, currency: str = "TRY") -> str:
    symbol = "₺" if currency == "TRY" else "$"
    return f"{symbol}{val:,.1f}"


async def build_brand_weekly(
    client: httpx.AsyncClient,
    brand_key: str,
    brand: dict,
    since: str,
    until: str,
    prev_since: str,
    prev_until: str,
) -> str:
    brand_name = brand["name"]
    currency = brand["currency"]

    # Parallel fetch
    ads_cur, ads_prev, fb_data, ig_data = await asyncio.gather(
        get_weekly_ads(client, brand["ad_account"], since, until),
        get_weekly_ads(client, brand["ad_account"], prev_since, prev_until),
        get_fb_organic(client, brand["page_id"], since, until),
        get_ig_organic(client, brand["ig_id"], since, until),
    )

    top_camps = await get_top_campaigns(client, brand["ad_account"], since, until)

    lines = [f"━━━━━━━━━━━━━━━━━━━━", f"🏷️ *{brand_name}*"]

    # ── Ads Section ──
    spend = float(ads_cur.get("spend", 0))
    if spend > 0:
        impressions = int(ads_cur.get("impressions", 0))
        reach = int(ads_cur.get("reach", 0))
        ctr = float(ads_cur.get("ctr", 0))
        cpm = float(ads_cur.get("cpm", 0))
        results, cpr = extract_results(
            ads_cur.get("actions", []),
            ads_cur.get("cost_per_action_type", [])
        )

        prev_spend = float(ads_prev.get("spend", 0))
        prev_results, prev_cpr = extract_results(
            ads_prev.get("actions", []),
            ads_prev.get("cost_per_action_type", [])
        )

        # Week-over-week
        spend_chg = ""
        if prev_spend > 0:
            delta = ((spend - prev_spend) / prev_spend) * 100
            spend_chg = f" ({'+' if delta >= 0 else ''}{delta:.0f}% مقارنة بالأسبوع الماضي)"

        cpr_chg = ""
        if prev_cpr > 0 and cpr > 0:
            delta = ((cpr - prev_cpr) / prev_cpr) * 100
            arrow = "🟢" if delta <= 0 else "🔴"
            cpr_chg = f" {arrow} {'+' if delta >= 0 else ''}{delta:.0f}%"

        lines.append(f"\n📢 *الإعلانات*")
        lines.append(f"💰 إنفاق: {fmt_currency(spend, currency)}{spend_chg}")
        lines.append(f"👁️ وصل: {reach:,} | {impressions:,} ظهور | CPM: {fmt_currency(cpm, currency)}")
        lines.append(f"🖱️ CTR: {ctr:.2f}%")
        if results > 0:
            lines.append(f"✅ نتائج: {results:,} | تكلفة/نتيجة: {fmt_currency(cpr, currency)}{cpr_chg}")

        if top_camps:
            lines.append("📋 *أكبر الحملات:*")
            for c in top_camps[:3]:
                c_spend = float(c.get("spend", 0))
                c_results, c_cpr = extract_results(
                    c.get("actions", []),
                    c.get("cost_per_action_type", [])
                )
                c_name = c.get("campaign_name", "")[:35]
                if c_results > 0:
                    lines.append(f"  • {c_name}: {fmt_currency(c_spend, currency)} → {c_results} نتيجة")
                else:
                    lines.append(f"  • {c_name}: {fmt_currency(c_spend, currency)}")
    else:
        lines.append(f"\n📢 *الإعلانات*: لا يوجد إنفاق هذا الأسبوع")

    # ── FB Organic Section ──
    if fb_data and not fb_data.get("error"):
        organic = fb_data.get("page_posts_impressions_organic", 0)
        paid_imp = fb_data.get("page_posts_impressions_paid", 0)
        engagements = fb_data.get("page_post_engagements", 0)
        follows = fb_data.get("page_daily_follows_unique", 0)
        fan_count = fb_data.get("fan_count", 0)
        video_views = fb_data.get("page_video_views", 0)

        lines.append(f"\n📘 *فيسبوك أورجانيك*")
        if fan_count:
            lines.append(f"👥 متابعين: {fan_count:,}")
        lines.append(f"🌱 وصول أورجانيك: {organic:,} | تفاعل: {engagements:,}")
        if video_views:
            lines.append(f"🎬 مشاهدات فيديو: {video_views:,}")
        if follows:
            lines.append(f"➕ متابعين جدد: {follows:,}")

    # ── IG Organic Section ──
    if ig_data and not ig_data.get("error"):
        reach = ig_data.get("reach", 0)
        engaged = ig_data.get("accounts_engaged", 0)
        interactions = ig_data.get("total_interactions", 0)
        profile_views = ig_data.get("profile_views", 0)
        website_clicks = ig_data.get("website_clicks", 0)
        followers = ig_data.get("followers_count", 0)

        lines.append(f"\n📸 *إنستجرام أورجانيك*")
        if followers:
            lines.append(f"👥 متابعين: {followers:,}")
        lines.append(f"🌱 وصل: {reach:,} | تفاعل: {interactions:,} | حسابات متفاعلة: {engaged:,}")
        if profile_views:
            lines.append(f"🔍 زيارات البروفايل: {profile_views:,}")
        if website_clicks:
            lines.append(f"🔗 كليكات الموقع: {website_clicks:,}")

    return "\n".join(lines)


async def main():
    # Last 7 days (Mon-Sun)
    today = date.today()
    # Find last complete week (Sun = last Sunday)
    days_since_sunday = today.weekday() + 1  # Monday=0, so Sunday=6 → +1 to get to prev Sunday
    last_sunday = today - timedelta(days=days_since_sunday % 7 or 7)
    last_monday = last_sunday - timedelta(days=6)

    since = last_monday.strftime("%Y-%m-%d")
    until = last_sunday.strftime("%Y-%m-%d")

    # Previous week for comparison
    prev_since = (last_monday - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_until = (last_sunday - timedelta(days=7)).strftime("%Y-%m-%d")

    week_label = f"{last_monday.strftime('%d/%m')} — {last_sunday.strftime('%d/%m/%Y')}"

    brands_to_report = sys.argv[1:] if len(sys.argv) > 1 else list(BRANDS.keys())

    header = f"📅 *التقرير الأسبوعي — {week_label}*\nإعلانات + أورجانيك لكل البراندات"

    async with httpx.AsyncClient() as client:
        tasks = [
            build_brand_weekly(client, key, BRANDS[key], since, until, prev_since, prev_until)
            for key in brands_to_report
            if key in BRANDS
        ]
        results = await asyncio.gather(*tasks)

    footer = f"━━━━━━━━━━━━━━━━━━━━\n🕗 تم التوليد: {datetime.now().strftime('%H:%M — %d/%m/%Y')}"

    print("\n\n".join([header] + list(results) + [footer]))


if __name__ == "__main__":
    asyncio.run(main())
