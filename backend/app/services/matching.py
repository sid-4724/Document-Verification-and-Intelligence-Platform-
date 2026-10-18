"""Conservative row matching: identifiers, exact descriptions, then fuzzy candidates."""

import unicodedata
from difflib import SequenceMatcher

FUZZY_DESCRIPTION_THRESHOLD = 0.82


def normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    characters = []
    for character in text:
        # Combining marks carry meaning in names and scripts such as Devanagari.
        if character.isalnum() or unicodedata.category(character).startswith("M"):
            characters.append(character)
        else:
            characters.append(" ")
    return " ".join("".join(characters).split())


def match_candidates(left: list[dict], right: list[dict]) -> dict[int, dict]:
    """Return candidate indices and review reasons; similarity never guarantees identity."""
    result = {}
    for index, item in enumerate(left):
        sku = normalize(item.get("sku"))
        exact_sku = [
            j for j, other in enumerate(right) if sku and normalize(other.get("sku")) == sku
        ]
        if exact_sku:
            result[index] = {"indices": exact_sku, "method": "exact_identifier", "conflict": False}
            continue
        compatible = [
            j
            for j, other in enumerate(right)
            if not (sku and normalize(other.get("sku")) and sku != normalize(other.get("sku")))
        ]
        description = normalize(item.get("description"))
        exact_description = [
            j
            for j in compatible
            if description and description == normalize(right[j].get("description"))
        ]
        if exact_description:
            result[index] = {
                "indices": exact_description,
                "method": "exact_description",
                "conflict": False,
            }
            continue
        similar = [
            j
            for j in compatible
            if description
            and SequenceMatcher(None, description, normalize(right[j].get("description"))).ratio()
            >= FUZZY_DESCRIPTION_THRESHOLD
        ]
        conflicts = [
            j
            for j, other in enumerate(right)
            if j not in compatible
            and description
            and (
                description == normalize(other.get("description"))
                or SequenceMatcher(None, description, normalize(other.get("description"))).ratio()
                >= FUZZY_DESCRIPTION_THRESHOLD
            )
        ]
        # Conflicting nonempty identifiers are stronger evidence than fuzzy resemblance.
        result[index] = {
            "indices": conflicts or similar,
            "method": "conflicting_identifier" if conflicts else "fuzzy_description",
            "conflict": bool(conflicts),
        }
    return result
