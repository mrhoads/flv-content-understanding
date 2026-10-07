"""Generate synthetic Content Understanding results under the v2 commercial-video schema.

This reuses the exact same synthetic Progressive-style commercial campaigns and
variants defined in `generate_synthetic_commercials.py` (so the two scripts
describe the *same* underlying videos), but renders each one through the v2
field schema in `infra/analyzers/commercial-video-v2.json`
(`cuCommercialVideoAnalyzerV2`) instead of the original v1 schema in
`infra/analyzers/commercial-video.json` (`flvCommercialVideoAnalyzer`).

The point is to let the demo show, side by side, how the *same* video produces
different structured output when the analyzer's field schema changes:

- `CallToAction` (free-text string) becomes `HasCallToAction` (Yes/No,
  `classify`) + `CallToActionType` (`classify` enum), so presence/category can
  be aggregated without string parsing.
- `EmotionSentiment` (free-text string) becomes `SentimentCategory`
  (`classify` enum) + `SentimentNarrative` (renamed free-text string).
- `BrandSafetyNotes` gains a companion `BrandSafetyFlag` (`classify` enum) for
  filtering.
- A new quantitative field is added: `BrandMentionCount` (integer).
- A new `KnownCharacters` field classifies which of a known recurring-character
  roster (Flo, Jamie, Mara, Alan, Dr. Rick) appear, while `Characters` keeps
  capturing the full cast as free text, including any character outside that
  roster.

See `docs/content-understanding-architecture.md` and `fabric/README.md` for
the narrative explanation of this schema comparison.

This script does **not** call Azure AI Content Understanding or analyze any
real video -- see `generate_synthetic_commercials.py` for that disclaimer in
full.

Usage:
    python fabric/sample-data/generate_synthetic_commercials_v2.py

Writes one JSON file per synthetic video to
`fabric/sample-data/cu-results-v2/<campaign_name>/<id>.json`, mirroring the v1
output layout in `fabric/sample-data/cu-results/<campaign_name>/<id>.json` so
the two can be compared file-for-file (same campaign_name, same id).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from generate_synthetic_commercials import (  # noqa: E402  (sibling-script import)
    API_VERSION,
    CAMPAIGNS,
    _confidence,
    _field_array,
    _field_string,
    _iso_timestamp,
    _stable_id,
)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "cu-results-v2"
ANALYZER_ID = "cuCommercialVideoAnalyzerV2"

_CALL_TO_ACTION_TYPES = (
    ("call", "PhoneCall"),
    ("quote", "GetAQuote"),
    ("bundle", "PurchaseNow"),
    ("try", "VisitWebsite"),
    ("find your price", "VisitWebsite"),
)

_MIXED_SENTIMENT_KEYWORDS = ("awkward", "embarrassment", "discomfort", "cringe")

_KNOWN_CHARACTER_ROSTER = ("Flo", "Jamie", "Mara", "Alan", "Dr. Rick")


def _field_bool_enum(value: str, confidence: float) -> dict:
    """A `classify`-style field value: still a string type, but drawn from an enum."""
    return _field_string(value, confidence)


def _field_integer(value: int, confidence: float) -> dict:
    return {"type": "integer", "valueInteger": value, "confidence": round(confidence, 2)}


def _classify_call_to_action_type(call_to_action_text: str) -> str:
    lowered = call_to_action_text.lower()
    for keyword, category in _CALL_TO_ACTION_TYPES:
        if keyword in lowered:
            return category
    return "VisitWebsite"


def _classify_sentiment_category(emotion_sentiment_text: str) -> str:
    lowered = emotion_sentiment_text.lower()
    if any(keyword in lowered for keyword in _MIXED_SENTIMENT_KEYWORDS):
        return "Mixed"
    return "Positive"


def _classify_known_characters(characters: list[str]) -> list[str]:
    """Map the free-text `characters` list to the known recurring-character roster."""
    matched = []
    for roster_name in _KNOWN_CHARACTER_ROSTER:
        if any(roster_name.lower() in character.lower() for character in characters):
            matched.append(roster_name.replace(". ", "").replace(".", ""))
    return matched


def _count_brand_mentions(variant: dict) -> int:
    # Advertiser brand (always Progressive) plus each distinct competitor mentioned.
    return 1 + len(variant.get("competitors", []))


def _build_fields_v2(rng: random.Random, variant: dict) -> dict:
    call_to_action_type = _classify_call_to_action_type(variant["call_to_action"])
    sentiment_category = _classify_sentiment_category(variant["emotion_sentiment"])
    return {
        "AdvertiserBrand": _field_string("Progressive Insurance", _confidence(rng, 0.9, 0.99)),
        "VisibleProducts": _field_array(variant["visible_products"], _confidence(rng)),
        "CompetitorsMentioned": _field_array(variant.get("competitors", []), _confidence(rng, 0.7, 0.9)),
        "InsuranceProductsMentioned": _field_array(
            variant["insurance_products"], _confidence(rng, 0.88, 0.99)
        ),
        "Characters": _field_array(variant["characters"], _confidence(rng, 0.9, 0.99)),
        "KnownCharacters": _field_array(
            _classify_known_characters(variant["characters"]), _confidence(rng, 0.85, 0.98)
        ),
        "CharacterRoles": _field_string(variant["character_roles"], _confidence(rng)),
        "MusicAndAudio": _field_string(variant["music_and_audio"], _confidence(rng)),
        "Setting": _field_string(variant["setting"], _confidence(rng)),
        "KeyActions": _field_array(variant["key_actions"], _confidence(rng)),
        "OnScreenText": _field_array(variant["on_screen_text"], _confidence(rng, 0.85, 0.99)),
        "CommercialMessage": _field_string(variant["commercial_message"], _confidence(rng)),
        "HasCallToAction": _field_bool_enum("Yes", _confidence(rng, 0.9, 0.99)),
        "CallToActionType": _field_bool_enum(call_to_action_type, _confidence(rng, 0.85, 0.98)),
        "HumorMechanism": _field_string(variant["humor_mechanism"], _confidence(rng, 0.75, 0.95)),
        "SentimentCategory": _field_bool_enum(sentiment_category, _confidence(rng, 0.85, 0.98)),
        "SentimentNarrative": _field_string(variant["emotion_sentiment"], _confidence(rng)),
        "SportsOrEntertainmentReferences": _field_array(
            variant.get("sports_or_entertainment_references", []), _confidence(rng, 0.7, 0.92)
        ),
        "BrandSafetyFlag": _field_bool_enum("Clear", _confidence(rng, 0.9, 0.99)),
        "BrandSafetyNotes": _field_string(
            variant.get(
                "brand_safety_notes",
                "No obvious brand-safety concerns are visible or spoken.",
            ),
            _confidence(rng, 0.9, 0.99),
        ),
        "BrandMentionCount": _field_integer(_count_brand_mentions(variant), _confidence(rng, 0.85, 0.98)),
    }


def build_result_v2(rng: random.Random, variant: dict, result_id: str) -> dict:
    duration_ms = variant["duration_ms"]
    return {
        "id": result_id,
        "status": "Succeeded",
        "result": {
            "analyzerId": ANALYZER_ID,
            "apiVersion": API_VERSION,
            "createdAt": _iso_timestamp(rng),
            "contents": [
                {
                    "kind": "audioVisual",
                    "startTimeMs": 0,
                    "endTimeMs": duration_ms,
                    "markdown": variant["markdown"],
                    "fields": _build_fields_v2(rng, variant),
                }
            ],
        },
    }


def generate(output_dir: Path, seed: int) -> list[Path]:
    rng = random.Random(seed)
    written: list[Path] = []
    for campaign in CAMPAIGNS:
        campaign_dir = output_dir / campaign.campaign_name
        campaign_dir.mkdir(parents=True, exist_ok=True)
        for variant_index, variant in enumerate(campaign.variants):
            # Reuses the v1 stable-ID scheme so the same video has the same
            # `id` under both schemas, making v1/v2 rows easy to join for
            # comparison in Power BI.
            result_id = _stable_id(campaign.campaign_name, variant_index)
            result = build_result_v2(rng, variant, result_id)
            file_path = campaign_dir / f"{result_id}.json"
            file_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written.append(file_path)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for confidence scores and timestamps (deterministic by default).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    written = generate(args.output_dir, args.seed)
    print(
        f"Wrote {len(written)} synthetic v2-schema Content Understanding result file(s) "
        f"under {args.output_dir}"
    )
    for path in written:
        print(f"  {path.relative_to(args.output_dir.parent)}")


if __name__ == "__main__":
    main()
