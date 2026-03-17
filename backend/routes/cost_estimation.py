"""API cost estimation routes for KeyForge."""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict

from backend.config import db
from backend.security import get_current_user

router = APIRouter(prefix="/api", tags=["cost-estimation"])

# ── Pricing data ──────────────────────────────────────────────────────────

API_PRICING: Dict[str, dict] = {
    "openai": {
        "name": "OpenAI",
        "pricing_model": "per_token",
        "tiers": [
            {"name": "GPT-4o", "input_per_1m": 2.50, "output_per_1m": 10.00},
            {"name": "GPT-4o mini", "input_per_1m": 0.15, "output_per_1m": 0.60},
            {"name": "GPT-3.5 Turbo", "input_per_1m": 0.50, "output_per_1m": 1.50},
        ],
        "free_tier": None,
        "docs_url": "https://openai.com/pricing",
    },
    "stripe": {
        "name": "Stripe",
        "pricing_model": "per_transaction",
        "rate": "2.9% + $0.30 per transaction",
        "free_tier": None,
        "docs_url": "https://stripe.com/pricing",
    },
    "twilio": {
        "name": "Twilio",
        "pricing_model": "per_message",
        "sms_rate": 0.0079,
        "voice_per_min": 0.014,
        "free_tier": "Trial account with $15 credit",
        "docs_url": "https://www.twilio.com/pricing",
    },
    "sendgrid": {
        "name": "SendGrid",
        "pricing_model": "per_email",
        "tiers": [
            {"name": "Free", "emails_per_day": 100, "monthly_cost": 0},
            {"name": "Essentials", "emails_per_month": 100000, "monthly_cost": 19.95},
            {"name": "Pro", "emails_per_month": 1500000, "monthly_cost": 89.95},
        ],
        "docs_url": "https://sendgrid.com/pricing",
    },
    "supabase": {
        "name": "Supabase",
        "pricing_model": "per_project",
        "tiers": [
            {"name": "Free", "monthly_cost": 0, "limits": "500MB DB, 1GB storage"},
            {"name": "Pro", "monthly_cost": 25, "limits": "8GB DB, 100GB storage"},
        ],
        "docs_url": "https://supabase.com/pricing",
    },
    "firebase": {
        "name": "Firebase",
        "pricing_model": "per_usage",
        "free_tier": "Spark plan: 1GB storage, 50K reads/day",
        "docs_url": "https://firebase.google.com/pricing",
    },
    "vercel": {
        "name": "Vercel",
        "pricing_model": "per_project",
        "tiers": [
            {"name": "Hobby", "monthly_cost": 0},
            {"name": "Pro", "monthly_cost": 20},
        ],
        "docs_url": "https://vercel.com/pricing",
    },
    "aws": {
        "name": "AWS",
        "pricing_model": "per_usage",
        "free_tier": "12 months free tier for many services",
        "docs_url": "https://aws.amazon.com/pricing",
    },
    "gcp": {
        "name": "GCP",
        "pricing_model": "per_usage",
        "free_tier": "$300 credit for 90 days",
        "docs_url": "https://cloud.google.com/pricing",
    },
    "azure": {
        "name": "Azure",
        "pricing_model": "per_usage",
        "free_tier": "$200 credit for 30 days",
        "docs_url": "https://azure.microsoft.com/pricing",
    },
}


def _estimate_monthly_cost(api_name: str) -> float | None:
    """Return a rough minimum monthly cost for services that have fixed tiers.

    Returns None when the pricing model is usage-based or per-transaction and
    cannot be estimated without actual usage data.
    """
    pricing = API_PRICING.get(api_name)
    if not pricing:
        return None

    tiers = pricing.get("tiers")
    if tiers and isinstance(tiers, list):
        # Find the cheapest non-zero tier (or zero if only free exists)
        costs = [t.get("monthly_cost") for t in tiers if "monthly_cost" in t]
        if costs:
            return min(costs)

    return None


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("/cost-estimation/summary")
async def cost_estimation_summary(
    current_user: dict = Depends(get_current_user),
):
    """Get a summary of estimated monthly costs across all user services."""
    credentials = await (
        db.credentials
        .find({"user_id": current_user["id"]})
        .to_list(1000)
    )

    # Unique api_names the user holds
    user_apis = list({cred.get("api_name") for cred in credentials})

    total_min = 0.0
    service_estimates = []
    for api_name in sorted(user_apis):
        pricing = API_PRICING.get(api_name)
        est = _estimate_monthly_cost(api_name)
        service_estimates.append({
            "api_name": api_name,
            "name": pricing["name"] if pricing else api_name,
            "estimated_monthly_cost": est,
            "pricing_model": pricing["pricing_model"] if pricing else "unknown",
            "note": "Cost depends on usage" if est is None else None,
        })
        if est is not None:
            total_min += est

    return {
        "total_estimated_monthly_minimum": total_min,
        "services_counted": len(user_apis),
        "services": service_estimates,
    }


@router.get("/cost-estimation/{api_name}")
async def cost_estimation_detail(
    api_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Get detailed pricing information for a specific API."""
    pricing = API_PRICING.get(api_name.lower())
    if not pricing:
        raise HTTPException(
            status_code=404,
            detail=f"No pricing data available for '{api_name}'.",
        )

    return {
        "api_name": api_name.lower(),
        **pricing,
        "estimated_monthly_minimum": _estimate_monthly_cost(api_name.lower()),
    }


@router.get("/cost-estimation")
async def cost_estimation_list(
    current_user: dict = Depends(get_current_user),
):
    """Get pricing info for all APIs the user has credentials for."""
    credentials = await (
        db.credentials
        .find({"user_id": current_user["id"]})
        .to_list(1000)
    )

    user_apis = list({cred.get("api_name") for cred in credentials})

    results = []
    for api_name in sorted(user_apis):
        pricing = API_PRICING.get(api_name)
        if pricing:
            results.append({
                "api_name": api_name,
                **pricing,
                "estimated_monthly_minimum": _estimate_monthly_cost(api_name),
            })
        else:
            results.append({
                "api_name": api_name,
                "name": api_name,
                "pricing_model": "unknown",
                "message": "No pricing data available for this service.",
            })

    return {"credentials_count": len(user_apis), "pricing": results}
