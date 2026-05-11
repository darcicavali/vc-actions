"""Sample Meta Ads data shaped roughly like what vc-dashboard produces.

These are illustrative numbers, not real Vanessa Cavali figures.
"""

META_SUMMARY = [
    {
        "week_start": "2026-05-04",
        "spend": 412.50,
        "impressions": 128_400,
        "clicks": 1_980,
        "ctr": 0.0154,
        "cpm": 3.21,
        "cpc": 0.21,
        "atc_rate": 0.041,
        "ic_rate": 0.36,
        "purchases": 27,
        "revenue": 3_180.00,
        "roas": 7.71,
    }
]

META_BY_CAMPAIGN = [
    {
        "week_start": "2026-05-04",
        "campaign": "Prospect ASC",
        "spend": 218.50,
        "impressions": 71_200,
        "ctr": 0.0162,
        "cpm": 3.07,
        "freq": 1.42,
        "atc_rate": 0.043,
        "ic_rate": 0.38,
        "purchases": 8,
        "revenue": 920.00,
        "roas": 4.21,
    },
    {
        "week_start": "2026-05-04",
        "campaign": "RT - non customer",
        "spend": 148.50,
        "impressions": 41_800,
        "ctr": 0.0141,
        "cpm": 3.55,
        "freq": 3.54,
        "atc_rate": 0.039,
        "ic_rate": 0.32,
        "purchases": 9,
        "revenue": 1_280.00,
        "roas": 8.62,
    },
    {
        "week_start": "2026-05-04",
        "campaign": "RT-customer",
        "spend": 45.50,
        "impressions": 15_400,
        "ctr": 0.0188,
        "cpm": 2.95,
        "freq": 2.10,
        "atc_rate": 0.052,
        "ic_rate": 0.48,
        "purchases": 10,
        "revenue": 980.00,
        "roas": 21.5,
    },
]

META_BY_AD_SET = [
    {"campaign": "Prospect ASC", "ad_set": "Broad", "spend": 218.50, "ctr": 0.0162},
    {"campaign": "RT - non customer", "ad_set": "Web 30d", "spend": 148.50, "ctr": 0.0141},
]

META_BY_AD = [
    {"campaign": "Prospect ASC", "ad": "Catalog v3", "spend": 218.50, "freq": 1.42},
    {"campaign": "RT - non customer", "ad": "Static spring", "spend": 148.50, "freq": 3.54},
]

META_DEMOGRAPHICS = [
    {"age": "25-34", "gender": "female", "share_of_revenue": 0.46},
    {"age": "35-44", "gender": "female", "share_of_revenue": 0.31},
]
