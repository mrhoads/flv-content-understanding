"""Generate synthetic Content Understanding results for Progressive-style commercials.

This script does **not** call Azure AI Content Understanding or analyze any real
video. It fabricates result JSON that matches the exact shape
`flvCommercialVideoAnalyzer` (see `infra/analyzers/commercial-video.json`) returns,
so the Fabric reporting pipeline in `fabric/README.md` can be demoed end to end
without an Azure deployment or real commercial footage.

The commercial "characters", settings, and catchphrases below are grounded in
widely recognized, long-running Progressive Insurance ad campaigns (Flo and the
Progressive Store, Dr. Rick's "Parentamorphosis", The Motaur, Jamie, and the
Baker Mayfield jingle spots) for demo realism. All specific dialogue, segment
summaries, and markdown here are original paraphrases written for this demo, not
transcripts of any copyrighted commercial.

Usage:
    python fabric/sample-data/generate_synthetic_commercials.py

Writes one JSON file per synthetic video to
`fabric/sample-data/cu-results/<campaign_name>/<id>.json`, matching the blob key
shape `examples/analyze_video.py` uploads to the dedicated Fabric storage
account (`cu-results/<campaign_name>/<id>.json`), so the same files can be
copied straight into that container (or the OneLake shortcut) for a Fabric demo.

The script always overwrites `--output-dir` deterministically from --seed, so
reruns with the same seed reproduce identical file names and content.

Pass --extra N to also generate N additional synthetic "flights" (re-airings)
of the existing campaigns -- same characters/content, each with a fresh unique
ID, createdAt date, and confidences, so Power BI has more historic rows to
trend/aggregate over without inventing new campaign concepts:

    python fabric/sample-data/generate_synthetic_commercials.py --extra 50

Pass --upload (with --fabric-storage-account-url, or FABRIC_STORAGE_ACCOUNT_URL
set) to also upload every generated file (base + --extra) to the dedicated
Fabric storage account's `cu-results` container, reusing the same
managed-identity upload helper `examples/analyze_video.py` uses for real
analyzer output, so synthetic and real results land in the exact same blob
layout:

    python fabric/sample-data/generate_synthetic_commercials.py --extra 50 --upload \\
        --fabric-storage-account-url https://stflvfabricdeve9fd.blob.core.windows.net
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "cu-results"
ANALYZER_ID = "flvCommercialVideoAnalyzer"
API_VERSION = "2025-11-01"

# Make `examples/` importable when this script is run directly (python
# fabric/sample-data/generate_synthetic_commercials.py), so --upload can reuse
# the same managed-identity Blob upload helper real analyzer output uses.
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@dataclass
class CommercialTemplate:
    """One recurring Progressive campaign concept, used to stamp out 1-2 synthetic spots."""

    campaign_name: str
    variants: list[dict]


def _field_string(value: str, confidence: float) -> dict:
    return {"type": "string", "valueString": value, "confidence": round(confidence, 2)}


def _field_array(values: list[str], confidence: float) -> dict:
    return {
        "type": "array",
        "valueArray": [
            {"type": "string", "valueString": item, "confidence": round(confidence, 2)}
            for item in values
        ],
        "confidence": round(confidence, 2),
    }


def _confidence(rng: random.Random, low: float = 0.80, high: float = 0.98) -> float:
    return rng.uniform(low, high)


def _build_fields(rng: random.Random, variant: dict) -> dict:
    return {
        "AdvertiserBrand": _field_string("Progressive Insurance", _confidence(rng, 0.9, 0.99)),
        "VisibleProducts": _field_array(variant["visible_products"], _confidence(rng)),
        "CompetitorsMentioned": _field_array(variant.get("competitors", []), _confidence(rng, 0.7, 0.9)),
        "InsuranceProductsMentioned": _field_array(
            variant["insurance_products"], _confidence(rng, 0.88, 0.99)
        ),
        "Characters": _field_array(variant["characters"], _confidence(rng, 0.9, 0.99)),
        "CharacterRoles": _field_string(variant["character_roles"], _confidence(rng)),
        "MusicAndAudio": _field_string(variant["music_and_audio"], _confidence(rng)),
        "Setting": _field_string(variant["setting"], _confidence(rng)),
        "KeyActions": _field_array(variant["key_actions"], _confidence(rng)),
        "OnScreenText": _field_array(variant["on_screen_text"], _confidence(rng, 0.85, 0.99)),
        "CommercialMessage": _field_string(variant["commercial_message"], _confidence(rng)),
        "CallToAction": _field_string(variant["call_to_action"], _confidence(rng, 0.85, 0.98)),
        "HumorMechanism": _field_string(variant["humor_mechanism"], _confidence(rng, 0.75, 0.95)),
        "EmotionSentiment": _field_string(variant["emotion_sentiment"], _confidence(rng)),
        "SportsOrEntertainmentReferences": _field_array(
            variant.get("sports_or_entertainment_references", []), _confidence(rng, 0.7, 0.92)
        ),
        "BrandSafetyNotes": _field_string(
            variant.get(
                "brand_safety_notes",
                "No obvious brand-safety concerns are visible or spoken.",
            ),
            _confidence(rng, 0.9, 0.99),
        ),
    }


CAMPAIGNS: list[CommercialTemplate] = [
    CommercialTemplate(
        campaign_name="flo-name-your-price-tool",
        variants=[
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Flo pitches the Name Your Price Tool\n\n"
                    "Flo greets shoppers at the bright white Progressive Store and walks a "
                    "customer through entering a monthly budget into the Name Your Price Tool "
                    "kiosk, which returns a shelf of coverage options that fit."
                ),
                "visible_products": [
                    "Name Your Price Tool kiosk",
                    "Progressive Store shelf display",
                    "Progressive employee vest",
                ],
                "insurance_products": ["Auto insurance"],
                "characters": ["Flo", "shopper customer"],
                "character_roles": (
                    "Flo is the upbeat Progressive spokesperson and store guide; the shopper "
                    "is a budget-conscious customer she walks through the tool."
                ),
                "music_and_audio": (
                    "Upbeat, bright instrumental store-jingle bed under Flo's dialogue; no "
                    "lyrics, light register-beep sound effect when the tool returns a price."
                ),
                "setting": "The Progressive Store: a brightly lit, all-white superstore aisle.",
                "key_actions": [
                    "Flo welcomes the shopper at the kiosk",
                    "Shopper enters a monthly budget amount",
                    "Kiosk displays a shelf of matching coverage options",
                    "Flo hands over a labeled box with the selected plan",
                ],
                "on_screen_text": ["Name Your Price Tool", "Progressive.com"],
                "commercial_message": (
                    "You can name the price you want to pay and Progressive will show "
                    "coverage options that fit your budget."
                ),
                "call_to_action": "Visit Progressive.com to try the Name Your Price Tool.",
                "humor_mechanism": (
                    "Deadpan store-clerk delivery applied to an absurdly literal "
                    "'shopping for insurance' premise."
                ),
                "emotion_sentiment": "Upbeat and reassuring throughout, with a confident close.",
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Flo's quick Name Your Price Tool recap\n\n"
                    "A 15-second cut-down: Flo reminds returning viewers that the Name Your "
                    "Price Tool is still there whenever they need to adjust their budget."
                ),
                "visible_products": ["Name Your Price Tool kiosk", "Progressive Store shelf display"],
                "insurance_products": ["Auto insurance"],
                "characters": ["Flo"],
                "character_roles": "Flo delivers a quick direct-to-camera reminder.",
                "music_and_audio": "Short upbeat jingle sting, no spoken lyrics.",
                "setting": "The Progressive Store checkout counter.",
                "key_actions": ["Flo waves to camera", "Flo gestures to the kiosk"],
                "on_screen_text": ["Name Your Price Tool", "1-800-PROGRESSIVE"],
                "commercial_message": "The Name Your Price Tool is always available to fit your budget.",
                "call_to_action": "Call or visit Progressive.com for a quote.",
                "humor_mechanism": "Quick callback to the store premise for familiarity.",
                "emotion_sentiment": "Friendly and brisk.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Flo compares coverage tiers side by side\n\n"
                    "A shopper is torn between a 'Basic' and a 'Plus' coverage box, so Flo "
                    "slides the Name Your Price Tool's budget dial back and forth to show "
                    "how the shelf options change in real time."
                ),
                "visible_products": [
                    "Name Your Price Tool kiosk",
                    "Basic coverage box",
                    "Plus coverage box",
                ],
                "insurance_products": ["Auto insurance"],
                "characters": ["Flo", "shopper customer"],
                "character_roles": (
                    "Flo is the upbeat Progressive spokesperson and store guide; the shopper "
                    "is an indecisive customer comparing two coverage tiers."
                ),
                "music_and_audio": (
                    "Light plucky instrumental under the dialogue, with a soft chime each "
                    "time the shopper slides the budget dial."
                ),
                "setting": "The Progressive Store, between two side-by-side coverage kiosks.",
                "key_actions": [
                    "Shopper picks up the Basic box, then the Plus box",
                    "Flo slides the kiosk's budget dial back and forth",
                    "Shelf display updates to show the matching coverage tier",
                    "Shopper settles on a middle option",
                ],
                "on_screen_text": ["Name Your Price Tool", "Progressive.com"],
                "commercial_message": "Adjusting your budget on the tool shows different coverage levels instantly.",
                "call_to_action": "Try the Name Your Price Tool yourself at Progressive.com.",
                "humor_mechanism": "Flo's overly cheerful narration of an ordinary slider movement.",
                "emotion_sentiment": "Patient and reassuring, ending on a confident decision.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Flo trains a nervous new seasonal employee\n\n"
                    "Flo quizzes a new seasonal hire on how to run the Name Your Price Tool "
                    "kiosk; the trainee fumbles the pitch before landing it with a customer."
                ),
                "visible_products": ["Name Your Price Tool kiosk", "Employee training badge"],
                "insurance_products": ["Auto insurance"],
                "characters": ["Flo", "new seasonal employee"],
                "character_roles": (
                    "Flo is the confident store mentor; the new seasonal employee is "
                    "eager but visibly nervous on his first shift."
                ),
                "music_and_audio": (
                    "Bouncy comedic instrumental cue that stumbles briefly when the trainee "
                    "fumbles his line, then resolves cleanly."
                ),
                "setting": "The Progressive Store, near the front training station.",
                "key_actions": [
                    "Flo quizzes the trainee on the kiosk script",
                    "Trainee stumbles over the pitch to a waiting customer",
                    "Flo gives an encouraging nudge",
                    "Trainee lands the pitch and the customer smiles",
                ],
                "on_screen_text": ["Name Your Price Tool", "Progressive.com"],
                "commercial_message": "Anyone at Progressive can help you find a price that fits your budget.",
                "call_to_action": "Visit Progressive.com to find your price.",
                "humor_mechanism": "The trainee's nervous overcorrection played against Flo's calm coaching.",
                "emotion_sentiment": "Light embarrassment resolving into pride.",
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Flo closes up the store for the night\n\n"
                    "A quiet 15-second close: Flo switches off the kiosk lights one by one "
                    "down the aisle, reminding viewers the tool is available online anytime."
                ),
                "visible_products": ["Name Your Price Tool kiosk", "Progressive Store shelf display"],
                "insurance_products": ["Auto insurance"],
                "characters": ["Flo"],
                "character_roles": "Flo delivers a calm, solo closing-time moment.",
                "music_and_audio": "Slow, mellow instrumental wind-down with soft footstep sound effects.",
                "setting": "The Progressive Store at night, aisle lights dimming in sequence.",
                "key_actions": [
                    "Flo walks the aisle switching off kiosk lights",
                    "Flo pauses at the last kiosk and smiles at the camera",
                ],
                "on_screen_text": ["Progressive.com -- anytime", "Name Your Price Tool"],
                "commercial_message": "Progressive's price tool is available online any time, day or night.",
                "call_to_action": "Get a quote anytime at Progressive.com.",
                "humor_mechanism": "Mild deadpan delivered to an empty store as if it were a full crowd.",
                "emotion_sentiment": "Calm and quietly warm.",
            },
        ],
    ),
    CommercialTemplate(
        campaign_name="flo-group-fast-bundle",
        variants=[
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Flo demos Group Fast bundling\n\n"
                    "Flo and a coworker race carts of home and auto policy boxes toward a "
                    "register in a 'Group Fast' bundling-discount bit set in the store's "
                    "bundling aisle."
                ),
                "visible_products": [
                    "Progressive Store shelf display",
                    "Bundle discount price tag signage",
                ],
                "competitors": [],
                "insurance_products": ["Auto insurance", "Home insurance", "Bundled home and auto"],
                "characters": ["Flo", "Jamie"],
                "character_roles": (
                    "Flo hosts the bit; Jamie, her coworker, races carts with her to "
                    "demonstrate bundling speed."
                ),
                "music_and_audio": (
                    "Energetic uptempo instrumental track with a crowd-cheer sound effect "
                    "at the register."
                ),
                "setting": "The Progressive Store's bundling aisle, racing toward checkout.",
                "key_actions": [
                    "Flo and Jamie load carts with home and auto policy boxes",
                    "They race down the aisle",
                    "Register displays a bundled discount total",
                ],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Bundling home and auto insurance together can save you money, fast.",
                "call_to_action": "Bundle your policies at Progressive.com to start saving.",
                "humor_mechanism": "Mock-competitive cart race played completely straight-faced.",
                "emotion_sentiment": "Playful and energetic, ending on a satisfied note.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Flo demos bundling with renters insurance\n\n"
                    "Flo shows a young renter how adding renters insurance to an auto policy "
                    "stacks a second discount, using a small-scale 'apartment' shelf display."
                ),
                "visible_products": [
                    "Apartment-display shelf unit",
                    "Bundle discount price tag signage",
                ],
                "insurance_products": ["Auto insurance", "Renters insurance", "Bundled auto and renters"],
                "characters": ["Flo", "renter customer"],
                "character_roles": (
                    "Flo hosts the bit; the renter is a young customer skeptical that "
                    "renters insurance is worth bundling in."
                ),
                "music_and_audio": "Bright, friendly instrumental bed with a soft 'ka-ching' sound effect.",
                "setting": "A miniature apartment-themed display aisle inside the Progressive Store.",
                "key_actions": [
                    "Renter picks up a lone auto policy box",
                    "Flo adds a renters insurance box to the cart",
                    "Price tag updates to show the stacked discount",
                    "Renter looks pleasantly surprised",
                ],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Renters can stack a discount by bundling renters insurance with auto.",
                "call_to_action": "See how much you could save by bundling at Progressive.com.",
                "humor_mechanism": "Mini apartment set played completely seriously as a real display.",
                "emotion_sentiment": "Pleasantly surprised and upbeat.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Flo and Jamie's forklift bundling race\n\n"
                    "Flo and Jamie each pilot a small store forklift loaded with policy "
                    "pallets, racing to see who can bundle a family's full policy set first."
                ),
                "visible_products": ["Store forklift", "Policy pallets", "Bundle discount price tag signage"],
                "insurance_products": ["Auto insurance", "Home insurance", "Boat insurance", "Bundled policies"],
                "characters": ["Flo", "Jamie"],
                "character_roles": (
                    "Flo and Jamie are rival coworkers competing good-naturedly to assemble "
                    "the bigger bundle fastest."
                ),
                "music_and_audio": (
                    "Fast-paced comedic chase music with a forklift-beeping sound effect and "
                    "a cartoonish horn sting at the finish."
                ),
                "setting": "The Progressive Store's loading aisle, with two parallel forklift lanes.",
                "key_actions": [
                    "Flo and Jamie race forklifts down parallel aisles",
                    "Each stacks a pallet with home, auto, and boat policy boxes",
                    "They arrive at the register in a near-tie",
                    "Register displays the combined bundle discount",
                ],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Bundling multiple policies together adds up to bigger savings.",
                "call_to_action": "Bundle your policies at Progressive.com.",
                "humor_mechanism": "Over-the-top forklift race for an otherwise mundane paperwork task.",
                "emotion_sentiment": "High-energy and comedic, ending in a friendly tie.",
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Quick bundle-and-save recap\n\n"
                    "A 15-second cut-down: Flo holds up a single combined policy box and "
                    "reminds viewers that bundling is still the fastest way to save."
                ),
                "visible_products": ["Bundle discount price tag signage"],
                "insurance_products": ["Bundled home and auto"],
                "characters": ["Flo"],
                "character_roles": "Flo delivers a brisk, solo reminder about bundling.",
                "music_and_audio": "Short upbeat jingle sting, no lyrics.",
                "setting": "The Progressive Store checkout counter.",
                "key_actions": ["Flo holds up a combined policy box", "Flo points to the discount price tag"],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Bundling is still the fastest way to save with Progressive.",
                "call_to_action": "Bundle today at Progressive.com.",
                "humor_mechanism": "Quick callback to the bundling premise for familiarity.",
                "emotion_sentiment": "Brisk and upbeat.",
            },
        ],
    ),
    CommercialTemplate(
        campaign_name="dr-rick-parentamorphosis",
        variants=[
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Dr. Rick tunes in on a new homeowner\n\n"
                    "Dr. Rick observes a young homeowner starting to repeat his parents' "
                    "habits -- over-explaining a thermostat setting to houseguests -- and "
                    "steps in with a supportive, slightly awkward intervention."
                ),
                "visible_products": ["Progressive Home insurance brochure", "Dr. Rick's clipboard"],
                "insurance_products": ["Home insurance"],
                "characters": ["Dr. Rick", "young homeowner"],
                "character_roles": (
                    "Dr. Rick is Progressive's in-house 'parentamorphosis' counselor; the "
                    "young homeowner is a new policyholder slipping into parent-like habits."
                ),
                "music_and_audio": (
                    "Soft, mock-clinical piano underscore; occasional record-scratch sound "
                    "effect when Dr. Rick interrupts a habit."
                ),
                "setting": "A suburban living room during a casual house-party gathering.",
                "key_actions": [
                    "Homeowner over-explains the thermostat to guests",
                    "Dr. Rick steps in to gently interrupt the habit",
                    "Dr. Rick offers a reassuring, deadpan tip",
                ],
                "on_screen_text": ["Parentamorphosis", "Progressive.com/home"],
                "commercial_message": (
                    "New homeowners can get support (and home insurance) from Progressive "
                    "so they don't turn into their parents."
                ),
                "call_to_action": "Get a home insurance quote at Progressive.com.",
                "humor_mechanism": (
                    "Deadpan clinical framing of mundane parent behaviors as a treatable condition."
                ),
                "emotion_sentiment": "Light, comedic embarrassment resolving into warm reassurance.",
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Dr. Rick's quick check-in\n\n"
                    "A short cut-down where Dr. Rick catches a homeowner refolding takeout "
                    "menus 'for the drawer' and offers a one-line intervention."
                ),
                "visible_products": ["Dr. Rick's clipboard"],
                "insurance_products": ["Home insurance"],
                "characters": ["Dr. Rick", "young homeowner"],
                "character_roles": "Dr. Rick delivers a quick deadpan intervention.",
                "music_and_audio": "Single soft piano sting, brief record-scratch effect.",
                "setting": "A suburban kitchen.",
                "key_actions": ["Homeowner refolds takeout menus", "Dr. Rick interrupts"],
                "on_screen_text": ["Parentamorphosis", "Progressive.com/home"],
                "commercial_message": "Don't let homeownership turn you into your parents.",
                "call_to_action": "Visit Progressive.com/home for a quote.",
                "humor_mechanism": "Quick callback gag to a recognizable parent habit.",
                "emotion_sentiment": "Light and comedic.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Dr. Rick catches a garage-sale pricing habit\n\n"
                    "Dr. Rick observes a homeowner meticulously price-tagging every item at "
                    "a garage sale down to the penny and intervenes with a support-group-style "
                    "lesson."
                ),
                "visible_products": ["Price-tag gun", "Dr. Rick's clipboard"],
                "insurance_products": ["Home insurance"],
                "characters": ["Dr. Rick", "young homeowner"],
                "character_roles": (
                    "Dr. Rick counsels the homeowner through a classic 'parent habit' "
                    "relapse during a driveway garage sale."
                ),
                "music_and_audio": (
                    "Light acoustic guitar underscore; a kazoo-like sound effect plays each "
                    "time the price-tag gun clicks."
                ),
                "setting": "A suburban driveway during a weekend garage sale.",
                "key_actions": [
                    "Homeowner price-tags items down to the penny",
                    "Neighbors look on, mildly concerned",
                    "Dr. Rick steps in with a clipboard and a gentle lesson",
                    "Homeowner loosens up and rounds a price to a whole dollar",
                ],
                "on_screen_text": ["Parentamorphosis", "Progressive.com/home"],
                "commercial_message": "Progressive helps new homeowners recognize parent habits before they take hold.",
                "call_to_action": "Get a home insurance quote at Progressive.com.",
                "humor_mechanism": "Treating obsessive garage-sale pricing as a clinical symptom.",
                "emotion_sentiment": "Comedic discomfort resolving into relief.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Dr. Rick intervenes on unsolicited car advice\n\n"
                    "Dr. Rick catches a homeowner giving a neighbor long-winded, unsolicited "
                    "advice about tire pressure and steps in before it escalates further."
                ),
                "visible_products": ["Tire pressure gauge", "Dr. Rick's clipboard"],
                "insurance_products": ["Home insurance", "Auto insurance"],
                "characters": ["Dr. Rick", "young homeowner", "neighbor"],
                "character_roles": (
                    "Dr. Rick counsels the homeowner; the neighbor is a patient but "
                    "increasingly uninterested listener."
                ),
                "music_and_audio": (
                    "Soft mock-clinical piano underscore with a long drawn-out 'mmm' "
                    "reaction sound effect from the neighbor."
                ),
                "setting": "A suburban driveway, homeowner kneeling by a parked car.",
                "key_actions": [
                    "Homeowner over-explains tire pressure to a visibly bored neighbor",
                    "Dr. Rick steps between them",
                    "Dr. Rick offers a shorter, kinder way to say it",
                    "Neighbor thanks Dr. Rick and walks away",
                ],
                "on_screen_text": ["Parentamorphosis", "Progressive.com/home"],
                "commercial_message": "Dr. Rick helps new homeowners catch parent habits before they talk someone's ear off.",
                "call_to_action": "Get a quote at Progressive.com.",
                "humor_mechanism": "Deadpan escalation of an ordinary over-explaining habit.",
                "emotion_sentiment": "Light cringe-comedy resolving into warmth.",
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Dr. Rick's early-bird dinner reservation habit\n\n"
                    "A short cut-down: Dr. Rick catches a homeowner proudly booking a 4:30pm "
                    "dinner reservation and offers a one-line intervention."
                ),
                "visible_products": ["Dr. Rick's clipboard"],
                "insurance_products": ["Home insurance"],
                "characters": ["Dr. Rick", "young homeowner"],
                "character_roles": "Dr. Rick delivers a quick deadpan intervention.",
                "music_and_audio": "Single soft piano sting, brief record-scratch effect.",
                "setting": "A suburban kitchen, homeowner on the phone.",
                "key_actions": ["Homeowner books an early dinner reservation", "Dr. Rick interrupts"],
                "on_screen_text": ["Parentamorphosis", "Progressive.com/home"],
                "commercial_message": "Don't let homeownership turn you into your parents.",
                "call_to_action": "Visit Progressive.com/home for a quote.",
                "humor_mechanism": "Quick callback gag to a recognizable parent habit.",
                "emotion_sentiment": "Light and comedic.",
            },
        ],
    ),
    CommercialTemplate(
        campaign_name="motaur-motorcycle-savings",
        variants=[
            {
                "duration_ms": 30000,
                "markdown": (
                    "## The Motaur explains motorcycle savings\n\n"
                    "The Motaur, Progressive's half-man-half-motorcycle mascot, greets a "
                    "rider in a garage and explains usage-based motorcycle insurance "
                    "discounts with exaggerated enthusiasm."
                ),
                "visible_products": ["Motorcycle in garage", "Progressive motorcycle policy flyer"],
                "insurance_products": ["Motorcycle insurance"],
                "characters": ["The Motaur", "motorcycle rider"],
                "character_roles": (
                    "The Motaur is an exuberant half-man, half-motorcycle mascot; the rider "
                    "is a skeptical-then-convinced customer."
                ),
                "music_and_audio": (
                    "Driving rock guitar riff under the Motaur's booming voiceover; engine-rev "
                    "sound effect for emphasis."
                ),
                "setting": "A home garage with a parked motorcycle.",
                "key_actions": [
                    "The Motaur gallops in to greet the rider",
                    "The Motaur gestures at the motorcycle while explaining discounts",
                    "Rider looks surprised, then convinced",
                ],
                "on_screen_text": ["Motorcycle insurance starting at $75/year*", "Progressive.com"],
                "commercial_message": "Motorcycle riders can save with usage-based Progressive discounts.",
                "call_to_action": "Get a motorcycle insurance quote at Progressive.com.",
                "humor_mechanism": (
                    "Absurd half-man-half-motorcycle mascot delivering sincere insurance advice."
                ),
                "emotion_sentiment": "High-energy and enthusiastic throughout.",
                "brand_safety_notes": (
                    "Motorcycle riding is shown only in a stationary garage setting; no "
                    "on-road riding or stunts depicted."
                ),
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## The Motaur holds court at a roadside cafe\n\n"
                    "The Motaur joins a table of riders at a roadside cafe stop, launching "
                    "into an enthusiastic, half-shouted pitch about usage-based discounts "
                    "over coffee."
                ),
                "visible_products": ["Parked motorcycles", "Progressive motorcycle policy flyer"],
                "insurance_products": ["Motorcycle insurance"],
                "characters": ["The Motaur", "group of riders"],
                "character_roles": (
                    "The Motaur is the exuberant mascot holding court; the riders are a "
                    "mixed group of regulars, amused and a little overwhelmed."
                ),
                "music_and_audio": (
                    "Upbeat acoustic guitar riff under the Motaur's booming voiceover, "
                    "with ambient cafe chatter and a coffee-cup clink sound effect."
                ),
                "setting": "An outdoor roadside cafe patio popular with motorcycle riders.",
                "key_actions": [
                    "The Motaur approaches the riders' table uninvited",
                    "The Motaur launches into a loud, enthusiastic pitch",
                    "Riders exchange amused glances",
                    "One rider pulls out a phone to get a quote on the spot",
                ],
                "on_screen_text": ["Motorcycle insurance starting at $75/year*", "Progressive.com"],
                "commercial_message": "Riders can get real-time usage-based savings wherever they are.",
                "call_to_action": "Get a motorcycle insurance quote at Progressive.com.",
                "humor_mechanism": "The Motaur's booming, oversized presence crashing a quiet coffee break.",
                "emotion_sentiment": "High-energy, slightly chaotic, ending in amused agreement.",
                "brand_safety_notes": (
                    "Motorcycles are shown parked; no riding, stunts, or helmetless "
                    "operation depicted."
                ),
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## The Motaur narrates a trail ride, voiceover only\n\n"
                    "A scenic off-road trail ride plays out while the Motaur's voice narrates "
                    "usage-based motorcycle savings over the footage, never appearing "
                    "on-screen."
                ),
                "visible_products": ["Off-road motorcycle", "Progressive motorcycle policy flyer"],
                "insurance_products": ["Motorcycle insurance"],
                "characters": ["The Motaur (voiceover only)", "off-road rider"],
                "character_roles": (
                    "The Motaur narrates in voiceover; the off-road rider is shown riding "
                    "a scenic trail without speaking."
                ),
                "music_and_audio": (
                    "Driving rock instrumental under the Motaur's voiceover, blended with "
                    "natural engine and trail ambiance."
                ),
                "setting": "A scenic off-road motorcycle trail at sunset.",
                "key_actions": [
                    "Rider navigates a winding trail",
                    "Motaur's voiceover explains usage-based discounts",
                    "Rider arrives at a scenic overlook as the pitch concludes",
                ],
                "on_screen_text": ["Motorcycle insurance starting at $75/year*", "Progressive.com"],
                "commercial_message": "Usage-based motorcycle insurance rewards safe, measured riding.",
                "call_to_action": "Get a motorcycle insurance quote at Progressive.com.",
                "humor_mechanism": "Mild, since the Motaur's over-the-top voice narrates a serene scene.",
                "emotion_sentiment": "Calm and scenic, with an enthusiastic voiceover undertone.",
                "brand_safety_notes": (
                    "Rider wears a full helmet and protective gear; trail riding shown at "
                    "a measured pace."
                ),
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Quick Motaur discount recap\n\n"
                    "A 15-second cut-down: the Motaur gallops past camera and shouts a "
                    "one-line reminder about motorcycle savings."
                ),
                "visible_products": ["Progressive motorcycle policy flyer"],
                "insurance_products": ["Motorcycle insurance"],
                "characters": ["The Motaur"],
                "character_roles": "The Motaur delivers a brief, high-energy direct-to-camera reminder.",
                "music_and_audio": "Short driving guitar riff sting with an engine-rev sound effect.",
                "setting": "An open parking lot.",
                "key_actions": ["The Motaur gallops past camera", "The Motaur shouts the savings reminder"],
                "on_screen_text": ["Motorcycle insurance starting at $75/year*", "Progressive.com"],
                "commercial_message": "Motorcycle riders can save with usage-based Progressive discounts.",
                "call_to_action": "Get a quote at Progressive.com.",
                "humor_mechanism": "Quick callback to the mascot's exaggerated enthusiasm.",
                "emotion_sentiment": "High-energy and brief.",
                "brand_safety_notes": "No riding shown; mascot appears in an empty lot only.",
            },
        ],
    ),
    CommercialTemplate(
        campaign_name="jamie-employee-of-the-month",
        variants=[
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Jamie's employee-of-the-month bit\n\n"
                    "Jamie, Flo's coworker, is thrilled to be named employee of the month "
                    "and over-explains the honor to uninterested shoppers, while Flo looks "
                    "on with affectionate exasperation."
                ),
                "visible_products": ["Progressive Store shelf display", "Employee of the Month plaque"],
                "insurance_products": ["Auto insurance"],
                "characters": ["Jamie", "Flo"],
                "character_roles": (
                    "Jamie is an eager, slightly overconfident Progressive Store employee; "
                    "Flo is his more composed coworker."
                ),
                "music_and_audio": "Light comedic instrumental sting with a small fanfare cue.",
                "setting": "The Progressive Store checkout area.",
                "key_actions": [
                    "Jamie holds up his employee-of-the-month plaque",
                    "Jamie over-explains the honor to shoppers",
                    "Flo redirects the shoppers to checkout",
                ],
                "on_screen_text": ["Progressive.com"],
                "commercial_message": "Progressive employees (even Jamie) are there to help you save.",
                "call_to_action": "Visit Progressive.com for a quote.",
                "humor_mechanism": "Jamie's over-the-top self-congratulation played against Flo's deadpan.",
                "emotion_sentiment": "Comedic and lighthearted.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Jamie organizes a one-man parade\n\n"
                    "Jamie recruits two other employees into an impromptu mini-parade down "
                    "the main aisle to celebrate a sales milestone, while Flo tries to keep "
                    "shoppers moving."
                ),
                "visible_products": ["Progressive Store shelf display", "Handmade parade banner"],
                "insurance_products": ["Auto insurance"],
                "characters": ["Jamie", "Flo", "two coworkers"],
                "character_roles": (
                    "Jamie leads an enthusiastic, self-organized parade; Flo manages the "
                    "shoppers caught in the middle of it."
                ),
                "music_and_audio": (
                    "Mock-triumphant marching-band instrumental with a kazoo lead line and "
                    "a small cowbell sound effect."
                ),
                "setting": "The Progressive Store's main aisle.",
                "key_actions": [
                    "Jamie leads a small parade with a handmade banner",
                    "Two coworkers follow along half-heartedly",
                    "Flo redirects confused shoppers around the parade",
                    "Jamie takes an exaggerated bow at the register",
                ],
                "on_screen_text": ["Progressive.com"],
                "commercial_message": "Progressive's team celebrates the wins, even small ones, while still helping you save.",
                "call_to_action": "Visit Progressive.com for a quote.",
                "humor_mechanism": "A full parade staged for an extremely minor achievement.",
                "emotion_sentiment": "Comedic and high-energy, ending in a shared laugh.",
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Jamie's new name tag mishap\n\n"
                    "Jamie proudly debuts a new name tag that misspells his name, and spends "
                    "the ad insisting to shoppers that it's intentional, while Flo quietly "
                    "corrects customers behind his back."
                ),
                "visible_products": ["Progressive Store shelf display", "Misspelled name tag"],
                "insurance_products": ["Auto insurance"],
                "characters": ["Jamie", "Flo"],
                "character_roles": (
                    "Jamie insists the misspelled name tag is intentional; Flo quietly "
                    "corrects shoppers out of his earshot."
                ),
                "music_and_audio": "Light comedic instrumental with a soft 'record scratch' sting on the reveal.",
                "setting": "The Progressive Store checkout area.",
                "key_actions": [
                    "Jamie shows off his new name tag",
                    "A shopper points out the misspelling",
                    "Jamie insists it's intentional",
                    "Flo quietly corrects the next shopper behind him",
                ],
                "on_screen_text": ["Progressive.com"],
                "commercial_message": "Even on an off day, Progressive's team is there to help you save.",
                "call_to_action": "Visit Progressive.com for a quote.",
                "humor_mechanism": "Jamie's confident denial of an obvious mistake.",
                "emotion_sentiment": "Light, awkward comedy.",
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Jamie's quick elevator-pitch recap\n\n"
                    "A 15-second cut-down: Jamie tries to deliver a rapid-fire elevator "
                    "pitch about savings before Flo gently cuts him off to wrap the ad."
                ),
                "visible_products": ["Progressive Store shelf display"],
                "insurance_products": ["Auto insurance"],
                "characters": ["Jamie", "Flo"],
                "character_roles": "Jamie rushes an over-enthusiastic pitch; Flo closes it out.",
                "music_and_audio": "Fast comedic instrumental sting that cuts off abruptly.",
                "setting": "The Progressive Store checkout counter.",
                "key_actions": ["Jamie rushes through a pitch", "Flo cuts him off with a smile"],
                "on_screen_text": ["Progressive.com"],
                "commercial_message": "Progressive's team is there to help you save, even in a hurry.",
                "call_to_action": "Visit Progressive.com for a quote.",
                "humor_mechanism": "Jamie's rapid-fire overeagerness cut short by Flo.",
                "emotion_sentiment": "Quick and lighthearted.",
            },
        ],
    ),
    CommercialTemplate(
        campaign_name="baker-mayfield-bundle-jingle",
        variants=[
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Baker Mayfield sings the bundle jingle\n\n"
                    "NFL quarterback Baker Mayfield breaks into a living room, singing a "
                    "short original 'bundle and save' jingle to a surprised homeowner family."
                ),
                "visible_products": ["Living room furniture", "Progressive bundle offer card"],
                "insurance_products": ["Auto insurance", "Home insurance", "Bundled home and auto"],
                "characters": ["Baker Mayfield", "homeowner family"],
                "character_roles": (
                    "Baker Mayfield appears as a celebrity spokesperson delivering a musical "
                    "pitch; the homeowner family reacts with surprised amusement."
                ),
                "music_and_audio": (
                    "Baker Mayfield sings an original short jingle about bundling and saving, "
                    "backed by a simple acoustic guitar."
                ),
                "setting": "A suburban family living room.",
                "key_actions": [
                    "Baker Mayfield appears unannounced in the living room",
                    "He sings the bundle-and-save jingle",
                    "Family reacts with surprised laughter",
                ],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Bundling home and auto insurance with Progressive saves money.",
                "call_to_action": "Bundle your policies at Progressive.com.",
                "humor_mechanism": (
                    "Incongruous celebrity-musical intrusion into an ordinary living room."
                ),
                "emotion_sentiment": "Fun and high-energy, ending on a cheerful note.",
                "sports_or_entertainment_references": ["NFL", "Baker Mayfield (celebrity spokesperson)"],
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Baker Mayfield crashes a backyard BBQ\n\n"
                    "Baker Mayfield hops the fence into a neighborhood backyard BBQ, grabs a "
                    "spatula as a microphone, and serenades surprised guests with the bundle "
                    "jingle before flipping a burger."
                ),
                "visible_products": ["Backyard grill", "Progressive bundle offer card"],
                "insurance_products": ["Auto insurance", "Home insurance", "Bundled home and auto"],
                "characters": ["Baker Mayfield", "BBQ host", "backyard guests"],
                "character_roles": (
                    "Baker Mayfield is the uninvited celebrity performer; the host and "
                    "guests react with surprised amusement."
                ),
                "music_and_audio": (
                    "Baker Mayfield sings the bundle jingle a cappella into a spatula, "
                    "backed by ambient backyard chatter and a grill-sizzle sound effect."
                ),
                "setting": "A suburban backyard during a weekend BBQ.",
                "key_actions": [
                    "Baker Mayfield hops the backyard fence",
                    "He grabs a spatula and sings the jingle",
                    "Guests laugh and start recording on their phones",
                    "He flips a burger and hands it to the host",
                ],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Bundling home and auto insurance with Progressive saves money.",
                "call_to_action": "Bundle your policies at Progressive.com.",
                "humor_mechanism": "A celebrity treating an ordinary BBQ like a concert stage.",
                "emotion_sentiment": "Fun and high-energy, ending in a friendly laugh.",
                "sports_or_entertainment_references": ["NFL", "Baker Mayfield (celebrity spokesperson)"],
            },
            {
                "duration_ms": 30000,
                "markdown": (
                    "## Baker Mayfield interrupts a football watch party\n\n"
                    "During a football watch party, Baker Mayfield appears on the TV screen "
                    "itself and sings the bundle jingle directly to the stunned living room "
                    "before the game resumes."
                ),
                "visible_products": ["Living room TV", "Progressive bundle offer card"],
                "insurance_products": ["Auto insurance", "Home insurance", "Bundled home and auto"],
                "characters": ["Baker Mayfield", "watch party friends"],
                "character_roles": (
                    "Baker Mayfield breaks the fourth wall from inside the TV broadcast; "
                    "the friends react with stunned amusement."
                ),
                "music_and_audio": (
                    "Baker Mayfield sings the bundle jingle over a TV-broadcast audio filter, "
                    "with crowd-noise and a stadium PA sound effect underneath."
                ),
                "setting": "A suburban living room during a football watch party.",
                "key_actions": [
                    "Game broadcast cuts to Baker Mayfield mid-play",
                    "He sings the bundle jingle directly to the room",
                    "Friends stare at the TV, stunned",
                    "Broadcast cuts back to the game as if nothing happened",
                ],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Bundling home and auto insurance with Progressive saves money.",
                "call_to_action": "Bundle your policies at Progressive.com.",
                "humor_mechanism": "A celebrity spokesperson breaking the broadcast's fourth wall.",
                "emotion_sentiment": "Surprised and amused, ending on a playful note.",
                "sports_or_entertainment_references": [
                    "NFL",
                    "Football broadcast",
                    "Baker Mayfield (celebrity spokesperson)",
                ],
            },
            {
                "duration_ms": 15000,
                "markdown": (
                    "## Quick Baker Mayfield jingle recap\n\n"
                    "A 15-second cut-down: Baker Mayfield hums the bundle jingle's hook "
                    "while making a sandwich in a kitchen, barely looking up at the camera."
                ),
                "visible_products": ["Kitchen counter", "Progressive bundle offer card"],
                "insurance_products": ["Bundled home and auto"],
                "characters": ["Baker Mayfield"],
                "character_roles": "Baker Mayfield delivers a brief, casual direct-to-camera moment.",
                "music_and_audio": "Short hummed reprise of the bundle jingle hook, no full lyrics.",
                "setting": "A home kitchen.",
                "key_actions": ["Baker Mayfield hums the jingle hook", "He glances at the camera and winks"],
                "on_screen_text": ["Bundle & Save", "Progressive.com"],
                "commercial_message": "Bundling home and auto insurance with Progressive saves money.",
                "call_to_action": "Bundle your policies at Progressive.com.",
                "humor_mechanism": "Deadpan delivery of the jingle as background noise.",
                "emotion_sentiment": "Casual and lightly amusing.",
                "sports_or_entertainment_references": ["Baker Mayfield (celebrity spokesperson)"],
            },
        ],
    ),
]


def _iso_timestamp(rng: random.Random, days_back_max: int = 365) -> str:
    now = datetime.now(timezone.utc)
    delta = timedelta(days=rng.randint(0, days_back_max), hours=rng.randint(0, 23))
    return (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_id(campaign_name: str, variant_index: int) -> str:
    # Deterministic (not random) so reruns with the same inputs produce the
    # same file name, keeping committed sample data stable across regenerations.
    return str(uuid5(NAMESPACE_URL, f"flv-synthetic/{campaign_name}/{variant_index}"))


def build_result(rng: random.Random, variant: dict, result_id: str) -> dict:
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
                    "fields": _build_fields(rng, variant),
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
            result_id = _stable_id(campaign.campaign_name, variant_index)
            result = build_result(rng, variant, result_id)
            file_path = campaign_dir / f"{result_id}.json"
            file_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written.append(file_path)
    return written


def generate_extra_flights(output_dir: Path, seed: int, count: int) -> list[Path]:
    """Generate additional synthetic "re-airings" (flights) of the existing campaigns.

    Each extra sample reuses one of the existing campaign/variant templates
    verbatim (same characters, dialogue, products) but stamps it with a new
    unique ID, a freshly randomized `createdAt` date and per-field
    confidences -- standing in for the same ad being re-analyzed on a
    different air date, which is realistic for historic campaign volume in
    Power BI (mention counts/trend lines over many flights per campaign)
    without inventing new campaign concepts.
    """
    rng = random.Random(seed)
    campaign_variants = [
        (campaign, variant)
        for campaign in CAMPAIGNS
        for variant in campaign.variants
    ]
    written: list[Path] = []
    for extra_index in range(count):
        campaign, variant = rng.choice(campaign_variants)
        result_id = _stable_id(campaign.campaign_name, f"extra-{extra_index}")
        result = build_result(rng, variant, result_id)
        campaign_dir = output_dir / campaign.campaign_name
        campaign_dir.mkdir(parents=True, exist_ok=True)
        file_path = campaign_dir / f"{result_id}.json"
        file_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        written.append(file_path)
    return written


def upload_results(
    written: list[Path],
    *,
    fabric_storage_account_url: str,
    fabric_container: str,
    app_env: str,
) -> list[str]:
    """Upload each generated file to the Fabric storage account's cu-results container.

    Reuses `examples/analyze_video.py`'s `build_credential`/`upload_fabric_result`
    helpers so synthetic and real analyzer output land in the exact same
    managed-identity-authenticated blob layout
    (`cu-results/<campaign_name>/<id>.json`).
    """
    from examples.analyze_video import build_credential, upload_fabric_result

    credential = build_credential(app_env)
    urls: list[str] = []
    try:
        for file_path in written:
            campaign_name = file_path.parent.name
            url = upload_fabric_result(
                json_path=file_path,
                fabric_storage_account_url=fabric_storage_account_url,
                container_name=fabric_container,
                campaign_name=campaign_name,
                credential=credential,
            )
            urls.append(url)
    finally:
        if hasattr(credential, "close"):
            credential.close()
    return urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for confidence scores and timestamps (deterministic by default).",
    )
    parser.add_argument(
        "--extra",
        type=int,
        default=0,
        help=(
            "Generate this many additional synthetic 'flights' (re-airings) of "
            "the existing campaigns -- same characters/content, new ID, "
            "createdAt date, and confidences each time. Added on top of the 8 "
            "base samples, e.g. --extra 50 for 50 more rows across campaigns."
        ),
    )
    parser.add_argument(
        "--extra-seed",
        type=int,
        default=None,
        help="Random seed for --extra samples. Defaults to --seed + 1.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help=(
            "Also upload every generated file to the Fabric storage account's "
            "cu-results container (requires --fabric-storage-account-url or "
            "FABRIC_STORAGE_ACCOUNT_URL)."
        ),
    )
    parser.add_argument(
        "--fabric-storage-account-url",
        default=os.getenv("FABRIC_STORAGE_ACCOUNT_URL"),
        help=(
            "Dedicated, HNS-enabled Blob account URL whose cu-results container "
            "Fabric reads via a OneLake shortcut. Defaults to "
            "FABRIC_STORAGE_ACCOUNT_URL. Required with --upload."
        ),
    )
    parser.add_argument(
        "--fabric-container",
        default=os.getenv("FABRIC_RESULTS_CONTAINER", "cu-results"),
    )
    parser.add_argument(
        "--app-env",
        default=os.getenv("APP_ENV", "development"),
        choices=("development", "production"),
        help="Development uses DefaultAzureCredential; production uses managed identity.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.upload and not args.fabric_storage_account_url:
        raise SystemExit(
            "--upload requires --fabric-storage-account-url or FABRIC_STORAGE_ACCOUNT_URL."
        )

    written = generate(args.output_dir, args.seed)
    if args.extra:
        written.extend(
            generate_extra_flights(
                args.output_dir,
                args.extra_seed if args.extra_seed is not None else args.seed + 1,
                args.extra,
            )
        )
    print(f"Wrote {len(written)} synthetic Content Understanding result file(s) under {args.output_dir}")
    for path in written:
        print(f"  {path.relative_to(args.output_dir.parent)}")

    if args.upload:
        urls = upload_results(
            written,
            fabric_storage_account_url=args.fabric_storage_account_url,
            fabric_container=args.fabric_container,
            app_env=args.app_env,
        )
        print(f"Uploaded {len(urls)} file(s) to {args.fabric_storage_account_url}/{args.fabric_container}")
        for url in urls:
            print(f"  {url}")
    else:
        print(
            "Upload skipped (pass --upload with --fabric-storage-account-url or "
            "FABRIC_STORAGE_ACCOUNT_URL to push these into the Fabric cu-results container)."
        )


if __name__ == "__main__":
    main()
