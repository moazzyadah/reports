"""
Central brand configuration for all report scripts.
Add/remove brands here only — no need to touch report scripts.
"""

BRANDS = {
    "feluka": {
        "name": "فلوكة",
        "ad_account": "act_1735126643976715",
        "page_id": "111479863690722",
        "ig_id": "17841427128493002",
        "currency": "TRY",
    },
    "edvion": {
        "name": "Edvion (Kiief)",
        "ad_account": "act_1139404758027243",
        "page_id": "862193176978036",
        "ig_id": "17841478141821063",
        "currency": "TRY",
    },
    "mustakbal": {
        "name": "مستقبل",
        "ad_account": "act_1232967432358185",
        "page_id": "1017239971475102",
        "ig_id": "17841442183672593",
        "currency": "TRY",
    },
    "adventurers": {
        "name": "المغامرون",
        "ad_account": "act_1337406446930246",
        "page_id": "456510975169084",
        "ig_id": "17841411905870273",
        "currency": "TRY",
    },
    "wsool": {
        "name": "Wsool وصول",
        "ad_account": "act_1863975484434665",
        "page_id": "687629201091006",
        "ig_id": "17841474139006808",
        "currency": "TRY",
    },
}

# FB page metrics that work in v25 (period=day)
FB_PAGE_METRICS = [
    "page_posts_impressions_organic",
    "page_posts_impressions_paid",
    "page_posts_impressions_unique",
    "page_post_engagements",
    "page_video_views",
    "page_daily_follows_unique",
]

# IG metrics that work in v25 (metric_type=total_value, period=day)
IG_METRICS_TOTAL = [
    "reach",
    "profile_views",
    "accounts_engaged",
    "total_interactions",
    "website_clicks",
]
