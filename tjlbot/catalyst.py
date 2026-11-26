"""Mechanical stand-in for the catalyst read (box 6). The manual routine had Claude judge it; unattended, the
bot classifies Alpaca/Benzinga headlines since the prior close. Claude's daily report re-reads the headlines
of every traded name and notes any disagreement (see docs/tjl-bot.md). Tagged "catalyst: auto" in Notes."""
import re

# her ranking: earnings/guidance > M&A > FDA > index inclusion > sympathy > analyst upgrade > none
CLASSES = [
    ("Earnings/guidance", r"\bearnings\b|\bresults\b|\brevenue\b|\bguidance\b|\bquarter|\bq[1-4]\b|\beps\b|\boutlook\b|raises (its )?forecast"),
    ("M&A", r"acqui(re|res|sition)|\bmerger\b|\bto buy\b|takeover|buyout|deal to (buy|acquire)"),
    ("FDA", r"\bfda\b|approval|phase (1|2|3|i|ii|iii)\b"),
    ("Index inclusion", r"s&p 500|join(s|ing)? the .*index|added to the .*index"),
    ("Analyst upgrade", r"upgrade|price target|initiat(es|ed) .*(buy|overweight|outperform)"),
]
# "up on bad news" and denied rumors are traps: skip the name (doc: "denied rumor = skip")
TRAP = r"\boffering\b|dilut|\bprobe\b|investigat|subpoena|\bdenie[sd]\b|\bmiss(es|ed)?\b|(cuts?|lowers?) (its )?(guidance|outlook|forecast)|downgrade|lawsuit|\brecall\b|\bdelist"


def classify(items):
    """items: Alpaca news dicts (headline, summary). Returns catalyst (bool), type, trap, headline."""
    best = None
    trap = None
    for it in items:
        text = f"{it.get('headline', '')} {it.get('summary', '')}".lower()
        if re.search(TRAP, text):
            trap = trap or it.get("headline", "")
        for rank, (name, pat) in enumerate(CLASSES):
            if re.search(pat, text) and (best is None or rank < best[0]):
                best = (rank, name, it.get("headline", ""))
    if trap:
        return {"catalyst": False, "type": "None", "trap": True, "headline": trap}
    if best:
        return {"catalyst": True, "type": best[1], "trap": False, "headline": best[2]}
    if items:
        return {"catalyst": False, "type": "Other news", "trap": False, "headline": items[0].get("headline", "")}
    return {"catalyst": False, "type": "None", "trap": False, "headline": ""}
