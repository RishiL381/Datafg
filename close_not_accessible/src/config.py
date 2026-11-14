"""Shared paths, seeds, and data-decision constants for the Close ≠ Accessible pipeline.

Every step script imports from here so the decisions live in one place.
"""
from __future__ import annotations

import random
import re
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- paths
IDEA_DIR = Path(__file__).resolve().parents[1]          # Datafg/close_not_accessible
REPO_DIR = IDEA_DIR.parent                               # Datafg
DATA_DIR = REPO_DIR / "data"                             # shared raw data (gitignored)
OUT_DIR = IDEA_DIR / "outputs"                           # zip-level results (committed)
CACHE_DIR = OUT_DIR / "cache"                            # row-level intermediates (gitignored, never shared)

PLACES_CSV = DATA_DIR / "google_maps" / "google_maps.csv"
REVIEWS_CSV = DATA_DIR / "google_maps_reviews" / "google_maps_reviews.csv"
ZILLOW_CSVS = sorted((DATA_DIR / "zillow").glob("zillow_part*.csv"))

for _d in (OUT_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- reproducibility
SEED = 42


def set_seeds(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:  # torch is only installed for Step 3
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass


# ---------------------------------------------------------------- columns we are allowed to read
# Places: only what the pipeline needs. `address` is read ONLY to parse a 5-digit zip (Step 4); it is never written out.
PLACES_COLS = [
    "place_id", "name", "category", "all_categories", "lat", "lon",
    "rating", "reviews_count", "permanently_closed", "temporarily_closed",
]
# Reviews: reviewer_name / reviewer_url / profile_pic_url are NEVER read (privacy rule).
# review_id is a Google review key (not personal) and is used only to drop duplicate rows.
REVIEWS_COLS = [
    "review_id", "place_id", "place_name", "review", "review_rating",
    "review_date", "response_of_owner",
]
ZILLOW_COLS = [
    "zpid", "city", "zipcode", "latitude", "longitude", "homeStatus", "price", "rentZestimate",
]

# ---------------------------------------------------------------- service-type rules
# DATA DECISION: classify on the MAIN `category` field.
#   We checked `all_categories` as a fallback: it mostly adds dentists, pediatricians, therapists
#   (tagged "clinic") and convenience stores (tagged "grocery"), which are NOT the services we
#   mean. The one exception is the exact tag "Pharmacy", which marks in-house pharmacies at
#   clinics/hospitals, so that tag sets the pharmacy flag too.
#
# clinic   = general / primary / urgent / community medical care a resident would walk into.
#            Specialty clinics (dental, PT, acupuncture, fertility, plastic surgery, sleep, ...) excluded.
# pharmacy = retail pharmacy / drug store.
# grocery  = supermarkets and grocery stores (incl. ethnic grocers, produce markets).
#            Convenience stores, liquor stores, food banks and grocery DELIVERY services excluded
#            (convenience stores are the classic "not a real grocery" case in food-access work).
SERVICE_RULES = {
    "clinic": {
        "include": [
            r"^medical clinic$", r"^clinic$", r"^medical cent(er|re)$", r"^public medical cent(er|re)$",
            r"urgent care", r"walk-in clinic", r"community health cent", r"^free clinic$",
            r"^emergency clinic$", r"women's health clinic", r"^pediatric clinic$",
            r"family planning clinic", r"reproductive health clinic", r"children policlinic",
        ],
        "exclude": [r"dental", r"animal", r"veterin", r"cosmetic", r"plastic", r"hair", r"skin",
                    r"laser", r"spa\b", r"school"],
    },
    "pharmacy": {
        "include": [r"pharmacy", r"drug ?store", r"chemist"],
        "exclude": [r"homeopathic", r"wholesale", r"veterin", r"animal"],
    },
    "grocery": {
        "include": [r"grocery store", r"grocery shop", r"supermarket", r"produce market"],
        "exclude": [r"delivery", r"furniture", r"industrial"],
    },
}
SERVICE_TYPES = list(SERVICE_RULES)
_COMPILED = {
    k: (re.compile("|".join(v["include"])), re.compile("|".join(v["exclude"])))
    for k, v in SERVICE_RULES.items()
}


# DATA DECISION (Riley, 2026-11-14): exclude specialty programs that Google files under clinic
# categories. A clinic is dropped if its NAME matches SPECIALTY and does NOT match GENERAL.
CLINIC_SPECIALTY_NAME = re.compile(
    r"\b(transplant|sleep|allerg\w*|immunolog\w*|oncolog\w*|cancer|dermatolog\w*|imaging|radiolog\w*|"
    r"laborator\w*|lab|labs|blood draw|cardio\w*|heart|vascular|surgery|surgical|surgeons?|orthop\w*|"
    r"spine|neuro\w*|dialysis|kidney|fertility|ivf|eye|vision|retina\w*|ophthalm\w*|hearing|audiolog\w*|"
    r"wound|infusion|veins?|weight loss|aesthetics?|botox|med ?spa|ketamine|hormones?|testosterone|"
    r"chiropract\w*|acupunct\w*|rehab\w*|physical therapy|pain|sports medicine|podiatr\w*|gastro\w*|"
    r"endoscop\w*|pulmon\w*|urolog\w*|rheumatolog\w*|endocrin\w*|research|mri|x-ray|mammogra\w*|ultrasound)\b",
    re.IGNORECASE,
)
CLINIC_GENERAL_NAME = re.compile(
    r"\b(urgent|primary|family|community|health cent(er|re)|walk-in|internal medicine|pediatrics?|"
    r"free clinic|cl[ií]nica|planned parenthood|express care|immediate care|convenient care)\b",
    re.IGNORECASE,
)


def is_specialty_clinic_name(name: str) -> bool:
    n = name if isinstance(name, str) else ""
    return bool(CLINIC_SPECIALTY_NAME.search(n)) and not CLINIC_GENERAL_NAME.search(n)


# DATA DECISION (Riley, 2026-11-14): use BOTH review sources, deduped on (place_id, text):
#   1. reviews_file        -> google_maps_reviews.csv joined on place_id (random sample, but only ~1% joins)
#   2. places_top_reviews  -> `top_reviews` JSON inside google_maps.csv (<=8/place, Google "most relevant"
#                             order, so NOT random: 1-star reviews are over-represented). Note in write-up.
REVIEW_SOURCES = ["reviews_file", "places_top_reviews"]


def match_service(category: str) -> str | None:
    """Return the service type for a main category string, or None."""
    c = (category or "").strip().lower()
    for stype, (inc, exc) in _COMPILED.items():
        if inc.search(c) and not exc.search(c):
            return stype
    return None


# ---------------------------------------------------------------- thresholds
LOW_STAR_MAX = 2              # "complaint" reviews = 1-2 stars
MIN_LOW_STAR_REVIEWS = 1500   # Step 1 feasibility gate
