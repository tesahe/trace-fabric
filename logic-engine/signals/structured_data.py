"""Schema.org JSON-LD parser as a Tier 0 signal source.

LocalBusiness JSON-LD is one of the highest-signal artifacts a small
business site can carry: when present, it tells us in machine-readable
form that the page represents a real business AND surfaces the address /
phone / hours / aggregate rating without any heuristic guessing.

This module is intentionally conservative:

  * We never raise. Every JSON parse / type access goes through try/except
    so a single malformed block can't break a lead.
  * We emit detections at confidence 90 (high but not 100) — schema markup
    can be wrong, copy-pasted, or stale.
  * We recognize LocalBusiness and the common subclasses used by the
    industries we target (Restaurant, ProfessionalService, Dentist,
    Plumber, etc.). Anything else under the LocalBusiness umbrella is
    surfaced as the generic ``LocalBusiness`` type.

Public API:
  - ``parse_jsonld_blocks(raw_html) -> list[dict]``
  - ``extract_local_business_signals(raw_html) -> list[Detection]``
"""

from __future__ import annotations

import json
import logging
import re
from typing import Iterable

from bs4 import BeautifulSoup

from .detection import Detection, MatchSource, truncate_value

logger = logging.getLogger(__name__)


# Schema.org LocalBusiness subtype hierarchy (only the leaves we care about
# for SMB lead-gen). Anything not listed here that contains "Business" or
# matches a known synonym still gets surfaced as generic LocalBusiness.
_LOCAL_BUSINESS_TYPES = frozenset({
    "LocalBusiness",
    # AnimalShelter, ArchiveOrganization, etc. — limited; skipped.
    "AutomotiveBusiness",
    "AutoBodyShop",
    "AutoDealer",
    "AutoRepair",
    "ChildCare",
    "Dentist",
    "DryCleaningOrLaundry",
    "EmergencyService",
    "EmploymentAgency",
    "EntertainmentBusiness",
    "FinancialService",
    "FoodEstablishment",
    "Bakery",
    "BarOrPub",
    "Brewery",
    "CafeOrCoffeeShop",
    "FastFoodRestaurant",
    "IceCreamShop",
    "Restaurant",
    "Winery",
    "GovernmentOffice",
    "HealthAndBeautyBusiness",
    "BeautySalon",
    "DaySpa",
    "HairSalon",
    "HealthClub",
    "NailSalon",
    "TattooParlor",
    "HomeAndConstructionBusiness",
    "Electrician",
    "GeneralContractor",
    "HVACBusiness",
    "HousePainter",
    "Locksmith",
    "MovingCompany",
    "Plumber",
    "RoofingContractor",
    "InternetCafe",
    "LegalService",
    "Attorney",
    "Notary",
    "LodgingBusiness",
    "BedAndBreakfast",
    "Hotel",
    "Motel",
    "MedicalBusiness",
    "MedicalClinic",
    "Optician",
    "Pharmacy",
    "Physician",
    "VeterinaryCare",
    "ProfessionalService",
    "RadioStation",
    "RealEstateAgent",
    "RecyclingCenter",
    "SelfStorage",
    "ShoppingCenter",
    "SportsActivityLocation",
    "Store",
    "AutoPartsStore",
    "BikeStore",
    "BookStore",
    "ClothingStore",
    "ComputerStore",
    "ConvenienceStore",
    "DepartmentStore",
    "ElectronicsStore",
    "Florist",
    "FurnitureStore",
    "GardenStore",
    "GroceryStore",
    "HardwareStore",
    "HobbyShop",
    "HomeGoodsStore",
    "JewelryStore",
    "LiquorStore",
    "MensClothingStore",
    "MobilePhoneStore",
    "MovieRentalStore",
    "MusicStore",
    "OfficeEquipmentStore",
    "OutletStore",
    "PawnShop",
    "PetStore",
    "ShoeStore",
    "SportingGoodsStore",
    "TireShop",
    "ToyStore",
    "WholesaleStore",
    "TelevisionStation",
    "TouristInformationCenter",
    "TravelAgency",
})

_PROPERTY_KEYS = (
    ("aggregateRating", "has_aggregateRating"),
    ("openingHours", "has_openingHours"),
    ("openingHoursSpecification", "has_openingHours"),
    ("telephone", "has_telephone"),
    ("address", "has_address"),
    ("geo", "has_geo"),
    ("priceRange", "has_priceRange"),
    ("review", "has_review"),
    ("hasMenu", "has_menu"),
    ("acceptsReservations", "has_acceptsReservations"),
    ("paymentAccepted", "has_paymentAccepted"),
)

# Conservative regex used as a *fallback* when BeautifulSoup misreads a
# malformed document. We still prefer soup; this is just defense-in-depth.
_JSONLD_FALLBACK = re.compile(
    r"<script[^>]+type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


# Public API ------------------------------------------------------------------


def parse_jsonld_blocks(raw_html: str) -> list[dict]:
    """Parse every JSON-LD ``<script>`` block in ``raw_html``.

    Returns the list of parsed top-level objects. ``@graph`` arrays are
    flattened: each child object is yielded as its own block. Malformed
    blocks are silently dropped — JSON-LD in the wild is often broken and
    must not break lead processing.
    """
    if not raw_html or not isinstance(raw_html, str):
        return []

    raw_blocks: list[str] = []
    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(raw_html, "html.parser")
        except Exception:
            soup = None

    if soup is not None:
        try:
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                # ``script.string`` is None when the block contains nested
                # tags or HTML comments; fall back to the raw text() in
                # that case so we still try to parse it.
                body = script.string
                if body is None:
                    try:
                        body = script.get_text()
                    except Exception:
                        body = ""
                if body and isinstance(body, str):
                    raw_blocks.append(body)
        except Exception:
            logger.debug("structured_data: soup-based block extraction failed", exc_info=True)

    # Defense-in-depth: if soup found nothing, try the regex fallback.
    if not raw_blocks:
        try:
            raw_blocks = [m.group(1) for m in _JSONLD_FALLBACK.finditer(raw_html)]
        except Exception:
            raw_blocks = []

    parsed: list[dict] = []
    for block in raw_blocks:
        try:
            doc = json.loads(block)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        # Flatten @graph containers so each business gets its own dict.
        for item in _flatten(doc):
            if isinstance(item, dict):
                parsed.append(item)
    return parsed


def extract_local_business_signals(raw_html: str) -> list[Detection]:
    """Emit Detections for every LocalBusiness JSON-LD block found.

    For each business block:
      * One ``Schema.org: <type>`` Detection (confidence 90).
      * Additional Detections for present sub-properties
        (``has_aggregateRating``, ``has_openingHours``, ``has_telephone``,
        ``has_address``, etc.) — each at confidence 90.

    All Detections use ``MatchSource.STRUCTURED_DATA`` and
    ``pack="structured_data"``. They flow through the resolver / blocklist
    like any other Detection.
    """
    out: list[Detection] = []
    seen_types: set[str] = set()
    seen_props: set[str] = set()

    try:
        blocks = parse_jsonld_blocks(raw_html)
    except Exception:
        logger.exception("structured_data: parse_jsonld_blocks raised — returning []")
        return []

    for idx, block in enumerate(blocks):
        try:
            types = _extract_types(block)
            biz_type = _pick_business_type(types)
            if biz_type is None:
                continue

            display = f"Schema.org: {biz_type}"
            if display not in seen_types:
                seen_types.add(display)
                summary = _summarize(block)
                out.append(
                    Detection(
                        name=display,
                        pack="structured_data",
                        categories=(),  # no Wappalyzer-style category id
                        confidence=90,
                        version=None,
                        source=MatchSource.STRUCTURED_DATA,
                        matched_field=f"jsonld_blocks[{idx}].@type",
                        matched_value=truncate_value(summary),
                        pattern_id=f"structured_data:LocalBusiness:{biz_type}#{idx}",
                        cpe=None,
                        pricing=(),
                        saas=False,
                        oss=False,
                        website=None,
                    )
                )

            # Sub-properties — emit one synthetic Detection per recognised key.
            for key, signal_name in _PROPERTY_KEYS:
                if signal_name in seen_props:
                    continue
                if not _has_property(block, key):
                    continue
                seen_props.add(signal_name)
                out.append(
                    Detection(
                        name=f"Schema.org: {signal_name}",
                        pack="structured_data",
                        categories=(),
                        confidence=90,
                        version=None,
                        source=MatchSource.STRUCTURED_DATA,
                        matched_field=f"jsonld_blocks[{idx}].{key}",
                        matched_value=truncate_value(_summarize_value(block.get(key))),
                        pattern_id=f"structured_data:property:{signal_name}#{idx}",
                    )
                )
        except Exception:
            logger.debug("structured_data: skipping malformed block %d", idx, exc_info=True)
            continue

    return out


# Internals -------------------------------------------------------------------


def _flatten(doc) -> Iterable:
    """Yield every dict reachable from a top-level JSON-LD doc.

    JSON-LD may be a bare object, a list of objects, or an object with a
    top-level ``@graph`` array. We flatten all three into a flat iterable.
    """
    if isinstance(doc, dict):
        graph = doc.get("@graph")
        if isinstance(graph, list):
            yield from _flatten(graph)
        yield doc
    elif isinstance(doc, list):
        for item in doc:
            yield from _flatten(item)


def _extract_types(block: dict) -> list[str]:
    """Read ``@type`` (string or list of strings)."""
    raw = block.get("@type")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [t for t in raw if isinstance(t, str)]
    return []


def _pick_business_type(types: list[str]) -> str | None:
    """Pick the most specific recognised LocalBusiness subtype.

    Strategy: prefer the most specific known subtype (anything other than
    ``LocalBusiness`` itself), fall back to ``LocalBusiness`` if present,
    else ``None``.
    """
    specific = [t for t in types if t in _LOCAL_BUSINESS_TYPES and t != "LocalBusiness"]
    if specific:
        return specific[0]
    if "LocalBusiness" in types:
        return "LocalBusiness"
    return None


def _has_property(block: dict, key: str) -> bool:
    """True if ``key`` is present on ``block`` with a non-empty value."""
    if key not in block:
        return False
    val = block[key]
    if val is None:
        return False
    if isinstance(val, (str, list, dict)) and not val:
        return False
    return True


def _summarize(block: dict) -> str:
    """One-line summary for the matched_value audit field."""
    name = block.get("name") if isinstance(block.get("name"), str) else ""
    types = _extract_types(block)
    type_str = ",".join(types[:3])
    return f"@type={type_str} name={name}"


def _summarize_value(val) -> str:
    """Summary of a sub-property value for audit-trail readability."""
    if val is None:
        return ""
    if isinstance(val, (str, int, float, bool)):
        return str(val)
    try:
        return json.dumps(val, ensure_ascii=False)[:200]
    except Exception:
        return repr(val)[:200]
