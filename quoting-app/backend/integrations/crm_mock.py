"""Mock CRM client.

Real deployment would swap this module for a Salesforce/HubSpot/Dynamics
REST client behind the same three functions. Seeded from seed_data/crm_accounts.json
so the rest of the pipeline can be built and tested without real CRM credentials.
"""
from __future__ import annotations

import json
import os
from typing import Optional

_SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "seed_data", "crm_accounts.json")

with open(_SEED_PATH) as f:
    _ACCOUNTS = json.load(f)

_CONTACT_INDEX = {}
for _acc in _ACCOUNTS:
    for _c in _acc["contacts"]:
        _CONTACT_INDEX[_c["email"].lower()] = {
            "contact_id": _c["contact_id"],
            "contact_name": _c["name"],
            "account_id": _acc["account_id"],
            "account_name": _acc["account_name"],
            "account_owner": _acc["account_owner"],
            "account_owner_email": _acc["account_owner_email"],
            "price_book": _acc["price_book"],
        }

# in-memory opportunity log, keyed by account_id -> list of dicts. Purely for
# demo/audit purposes; a real CRM write would be an API call instead.
_OPPORTUNITIES: dict[str, list[dict]] = {}


def find_contact_by_email(email: str) -> Optional[dict]:
    return _CONTACT_INDEX.get(email.lower())


def account_owner_email(account_id: str) -> Optional[str]:
    for acc in _ACCOUNTS:
        if acc["account_id"] == account_id:
            return acc["account_owner_email"]
    return None


def price_override(account_id: Optional[str], sku: str) -> Optional[float]:
    if not account_id:
        return None
    for acc in _ACCOUNTS:
        if acc["account_id"] == account_id:
            return acc["price_book"].get(sku)
    return None


def log_opportunity_event(account_id: str, event: str, detail: str) -> None:
    _OPPORTUNITIES.setdefault(account_id, []).append({"event": event, "detail": detail})


def opportunity_log(account_id: str) -> list[dict]:
    return _OPPORTUNITIES.get(account_id, [])
