#!/usr/bin/env python3
"""
Fetch ALL Meta Ads actions/costs for all brands → data/latest.json
Analysis is Claude's job — we just collect everything faithfully.
"""

import asyncio
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from brands_config import BRANDS

TOKEN = os.environ["META_SYSTEM_USER_TOKEN"]
BASE = "https://graph.facebook.com/v25.0"

# Every action type we care about — Claude picks what's relevant per campaign
FIELDS = (
    "campaign_id,campaign_name,objective,"
    "spend,reach,impressions,frequency,"
    "actions,cost_per_action_type,action_values"
)


async def api_get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    params["access_token"] = TOKEN
    try:
        r = await client.get(f"{BASE}/{path}", params=params, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def parse_actions(actions: list, costs: list, values: list) -> dict:
    """Return flat dict of all action counts, costs, and values."""
    result = {}
    for a in (actions or []):
        at = a["action_type"]
        result[f"count_{at}"] = int(float(a.get("value", 0)))
    for c in (costs or []):
        at = c["action_type"]
        result[f"cpr_{at}"] = float(c.get("value", 0))
    for v in (values or []):
        at = v["action_type"]
        result[f"value_{at}"] = float(v.get("value", 0))
    return result


async def fetch_account_yesterday(client, account_id: str, yesterday: str) -> dict:
    r = await api_get(client, f"{account_id}/insights", {
        "fields": "spend,reach,impressions,actions,cost_per_action_type,action_values",
        "level": "account",
        "time_range": json.dumps({"since": yesterday, "until": yesterday}),
    })
    data = r.get("data", [])
    if not data:
        return {"spend": 0}
    d = data[0]
    return {
        "spend": float(d.get("spend", 0)),
        "reach": int(d.get("reach", 0)),
        "impressions": int(d.get("impressions", 0)),
        **parse_actions(d.get("actions", []), d.get("cost_per_action_type", []), d.get("action_values", [])),
    }


async def fetch_campaigns_lifetime(client, account_id: str) -> list:
    r = await api_get(client, f"{account_id}/insights", {
        "fields": FIELDS,
        "level": "campaign",
        "date_preset": "maximum",
        "filtering": json.dumps([{
            "field": "campaign.effective_status",
            "operator": "IN",
            "value": ["ACTIVE"],
        }]),
        "sort": "spend_descending",
        "limit": 15,
    })
    campaigns = []
    for c in r.get("data", []):
        campaigns.append({
            "id": c.get("campaign_id"),
            "name": c.get("campaign_name"),
            "objective": c.get("objective"),
            "spend": float(c.get("spend", 0)),
            "reach": int(c.get("reach", 0)),
            "impressions": int(c.get("impressions", 0)),
            "frequency": float(c.get("frequency", 0)),
            **parse_actions(c.get("actions", []), c.get("cost_per_action_type", []), c.get("action_values", [])),
        })
    return campaigns


async def fetch_brand(client, key: str, brand: dict, yesterday: str) -> dict:
    yesterday_data, campaigns = await asyncio.gather(
        fetch_account_yesterday(client, brand["ad_account"], yesterday),
        fetch_campaigns_lifetime(client, brand["ad_account"]),
    )
    return {
        "key": key,
        "name": brand["name"],
        "currency": brand["currency"],
        "yesterday": yesterday_data,
        "active_campaigns_lifetime": campaigns,
    }


async def main():
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[
            fetch_brand(client, k, v, yesterday) for k, v in BRANDS.items()
        ])

    output = {
        "date": yesterday,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "brands": list(results),
    }

    Path("data").mkdir(exist_ok=True)
    payload = json.dumps(output, ensure_ascii=False, indent=2)
    Path("data/latest.json").write_text(payload)
    Path(f"data/{yesterday}.json").write_text(payload)
    print(f"✓ data/latest.json + data/{yesterday}.json")


if __name__ == "__main__":
    asyncio.run(main())
