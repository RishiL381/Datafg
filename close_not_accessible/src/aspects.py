"""The 5 complaint aspects (fixed by Riley) and the keyword matcher used as the BASELINE classifier.

Label definitions (also in labels/LABELING_GUIDE.md). A review can have 0..5 aspects.
  wait_time          long waits in line / lobby / on hold, slow service, slow prescription fills,
                     long delays to get an appointment or results.
  cost               prices, billing, insurance problems, surprise or wrong charges, copays, refunds.
  staff              rude, dismissive, unhelpful, unprofessional, or incompetent staff or providers;
                     poor communication; feeling disrespected or discriminated against.
  language_access    language barriers: no interpreter, staff can't/won't communicate in the
                     customer's language, mistreatment over language or accent.
  hours_availability closed when it should be open, wrong/unreliable posted hours, closes early,
                     limited hours, phone never answered / can't reach anyone.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

ASPECTS = ["wait_time", "cost", "staff", "language_access", "hours_availability"]

# Keyword baseline. Deliberately simple and transparent: the models have to beat this.
KEYWORDS = {
    "wait_time": [
        r"wait(ed|ing)?\b", r"\bline\b", r"\bhours? (later|wait)", r"\bminutes?\b", r"took (forever|so long)",
        r"\bslow\b", r"\blong (time|wait|line)", r"on hold", r"\bdelay", r"still not ready", r"not ready",
        r"\bforever\b", r"\bqueue\b", r"next available", r"weeks? (later|out|for)",
    ],
    "cost": [
        r"\bprice", r"\bexpensive", r"overpric", r"\bcharg", r"\bbill(ed|ing)?\b", r"\binsurance",
        r"\bcopay", r"co-pay", r"\bcost", r"\bfees?\b", r"\brefund", r"\$\d", r"\bpaid\b", r"\bpay\b",
        r"\bcoupon", r"\bdollars?\b",
    ],
    "staff": [
        r"\brude", r"\bstaff", r"unprofessional", r"\battitude", r"\bdisrespect", r"\bmanager",
        r"\bcashier", r"\bpharmacist", r"\breceptionist", r"front desk", r"\bnurse", r"\bdoctor",
        r"\bunhelpful", r"\bignored", r"\bdismissive", r"\byell", r"\bracis", r"\bcustomer service",
        r"\bemployee", r"\bworker",
    ],
    "language_access": [
        r"\binterpret", r"\btranslat", r"\bspanish\b", r"\benglish\b", r"\blanguage", r"\baccent",
        r"\bmandarin", r"\bcantonese", r"\bchinese\b", r"\bvietnamese", r"\btagalog", r"\bkorean\b",
        r"habla", r"\bespañol", r"\bespanol",
    ],
    "hours_availability": [
        r"\bclosed\b", r"\bhours\b", r"\bopen\b", r"\bclos(e|es|ing) (early|at)", r"\blunch break",
        r"never answer", r"no one answer", r"nobody answer", r"doesn'?t answer", r"don'?t answer",
        r"can'?t reach", r"\bweekends?\b", r"\bholiday", r"after hours",
    ],
}
_KW = {a: re.compile("|".join(p), re.IGNORECASE) for a, p in KEYWORDS.items()}


def keyword_labels(texts: pd.Series | list[str]) -> pd.DataFrame:
    """Binary keyword hits per aspect (the baseline)."""
    s = pd.Series(texts).fillna("").astype(str)
    return pd.DataFrame({a: s.str.contains(rx).astype(int).to_numpy() for a, rx in _KW.items()})


def keyword_matrix(texts) -> np.ndarray:
    return keyword_labels(texts)[ASPECTS].to_numpy()
