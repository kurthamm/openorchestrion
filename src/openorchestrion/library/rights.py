"""What makes a redistribution claim checkable rather than merely asserted.

``rights_status`` drives real consequences: ``verified-open`` material is what
the project is willing to ship and stream, while ``personal`` stays on the
appliance that imported it. Until now the strongest claim the system could make
required no evidence at all — ``--rights-status verified-open`` wrote that value
with a null source, null license and null attribution — so nothing distinguished
a researched claim from a hopeful one.

This module holds the evidence model and the audit that decides whether a claim
is supported. It is deliberately pure: no filesystem, no catalog, no network. The
importer applies it when the claim is first made and the metadata writer applies
it when a claim is revised, so there is one definition of "verified" rather than
one per entry point.

Two rights questions are independent and are recorded separately, because
conflating them is exactly how a library ends up redistributing something it may
not. A Joplin rag is a public-domain *composition*; a particular MIDI sequencing
of it made in 2003 is a separate copyrightable work whose author may reserve
every right. Both must clear before the file is redistributable:

* ``composition_rights`` — the underlying musical work.
* ``license`` — the specific MIDI file/arrangement in hand.

The audit refuses anything it cannot establish. An unrecognized license is not
treated as permissive, and missing evidence is never read as consent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

RIGHTS_STATUSES: tuple[str, ...] = ("personal", "verified-open", "unknown")

COMPOSITION_RIGHTS: tuple[str, ...] = (
    "public-domain",
    "licensed",
    "in-copyright",
    "unknown",
)

REDISTRIBUTION: tuple[str, ...] = (
    "permitted",
    "permitted-with-attribution",
    "prohibited",
    "unknown",
)

# Licenses whose terms are established well enough to redistribute under, keyed
# to whether they oblige us to credit someone. The list is intentionally short:
# it holds the licenses this project has actually reasoned about, and grows by
# a deliberate edit rather than by pattern-matching an unfamiliar string. An id
# that is absent is not thereby restrictive — it is merely unestablished, which
# is the state the audit refuses to act on.
_LICENSE_TERMS: dict[str, str] = {
    "public-domain": "permitted",
    "CC0-1.0": "permitted",
    "CC-PDM-1.0": "permitted",
    "CC-BY-3.0": "permitted-with-attribution",
    "CC-BY-4.0": "permitted-with-attribution",
    "CC-BY-SA-3.0": "permitted-with-attribution",
    "CC-BY-SA-4.0": "permitted-with-attribution",
    # This project's own license, which covers the generated conformance
    # fixtures: they are output of an MIT-licensed generator in this repository,
    # not a third-party composition, and MIT permits redistribution provided the
    # copyright notice travels with them.
    "MIT": "permitted-with-attribution",
}

# Recognized so the audit can give the specific reason rather than the generic
# "unestablished" one. Failing closed is not the same as explaining why: a
# curator who is told a license is merely unfamiliar will go and look it up,
# while one told it is non-commercial knows the answer is settled. The
# non-commercial entries are here because this project's starter catalog is
# redistributable material; they remain perfectly usable as personal imports.
_KNOWN_RESTRICTIVE: frozenset[str] = frozenset(
    {
        "all-rights-reserved",
        "CC-BY-NC-4.0",
        "CC-BY-NC-SA-4.0",
        "CC-BY-NC-ND-4.0",
        "CC-BY-ND-4.0",
    }
)

#: License ids a curator may claim, for help text and validation messages.
ESTABLISHED_LICENSES: tuple[str, ...] = tuple(sorted(_LICENSE_TERMS))

EVIDENCE_FIELDS: tuple[str, ...] = (
    "rights_status",
    "source_reference",
    "source_label",
    "license",
    "license_url",
    "attribution",
    "composition_rights",
    "composition_rights_basis",
    "redistribution",
    "verified_at",
    "verified_by",
)


class RightsError(ValueError):
    """Raised when a rights claim is malformed or unsupported by its evidence."""


@dataclass(frozen=True, slots=True)
class RightsEvidence:
    """One asset's rights record: the claim, and what backs it.

    Every field is optional so that ``personal`` and ``unknown`` material — the
    overwhelming majority of a real user's library — carries no research burden.
    The obligations attach only to the ``verified-open`` claim.
    """

    rights_status: str = "unknown"
    source_reference: str | None = None
    source_label: str | None = None
    license: str | None = None
    license_url: str | None = None
    attribution: str | None = None
    composition_rights: str = "unknown"
    composition_rights_basis: str | None = None
    redistribution: str = "unknown"
    verified_at: str | None = None
    verified_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: dict[str, Any] | None) -> RightsEvidence:
        """Read evidence out of a stored provenance block.

        Sidecars written before this model existed carry only the original five
        fields; the defaults fill the rest, which correctly renders them as
        unestablished rather than as cleared.
        """
        source = values or {}
        unknown = set(source) - set(EVIDENCE_FIELDS) - {"imported_at"}
        if unknown:
            raise RightsError(f"unknown provenance field(s): {', '.join(sorted(unknown))}")
        return cls(**{name: source[name] for name in EVIDENCE_FIELDS if name in source})


def _text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RightsError(f"{name} must be a string")
    stripped = value.strip()
    return stripped or None


def implied_redistribution(license_id: str | None) -> str:
    """What a license id alone says about redistribution.

    Used to catch a stated ``redistribution`` that contradicts the license, so a
    transcription error cannot quietly widen what we claim to be allowed.
    """
    if license_id is None:
        return "unknown"
    if license_id in _KNOWN_RESTRICTIVE:
        return "prohibited"
    return _LICENSE_TERMS.get(license_id, "unknown")


def normalize(values: dict[str, Any]) -> dict[str, Any]:
    """Validate and clean an evidence mapping without judging its sufficiency."""
    unknown = set(values) - set(EVIDENCE_FIELDS)
    if unknown:
        raise RightsError(f"unknown rights field(s): {', '.join(sorted(unknown))}")

    cleaned: dict[str, Any] = {}
    for name, value in values.items():
        if name in {"rights_status", "composition_rights", "redistribution"}:
            allowed = {
                "rights_status": RIGHTS_STATUSES,
                "composition_rights": COMPOSITION_RIGHTS,
                "redistribution": REDISTRIBUTION,
            }[name]
            if value not in allowed:
                raise RightsError(f"{name} must be one of {', '.join(allowed)}")
            cleaned[name] = value
            continue
        cleaned[name] = _text(name, value)
    return cleaned


def audit(evidence: RightsEvidence) -> tuple[str, ...]:
    """Every reason this evidence fails to support its own claim.

    Returns the reasons rather than a bare boolean so a curator is told what to
    go and find, and so a bulk run can report precisely which entry is short of
    what. An empty tuple means the claim stands on its evidence.

    Only ``verified-open`` is audited. ``personal`` and ``unknown`` make no
    assertion about redistribution, so there is nothing to substantiate.
    """
    if evidence.rights_status not in RIGHTS_STATUSES:
        return (f"rights_status must be one of {', '.join(RIGHTS_STATUSES)}",)
    if evidence.rights_status != "verified-open":
        return ()

    reasons: list[str] = []

    if not (evidence.source_reference or "").strip():
        reasons.append(
            "source_reference is required: a verified claim must be re-checkable "
            "against where the file came from"
        )

    if evidence.composition_rights not in {"public-domain", "licensed"}:
        reasons.append(
            "composition_rights must be established as public-domain or licensed "
            f"(found {evidence.composition_rights!r})"
        )
    elif not (evidence.composition_rights_basis or "").strip():
        # A bare "public domain" is an opinion, and a bare "licensed" is worse:
        # it names no licensor and no terms. The basis is the reasoning that
        # makes either reviewable by someone who was not there. ``license``
        # cannot stand in for it, because that field is the terms of the MIDI
        # file, and the entire point of the model is that the two are separate.
        example = (
            "composer died 1917, published 1899"
            if evidence.composition_rights == "public-domain"
            else "licensed by the arranger under CC-BY-4.0, see <url>"
        )
        reasons.append(
            "composition_rights_basis is required for a "
            f"{evidence.composition_rights} composition (for example: {example})"
        )

    license_id = (evidence.license or "").strip()
    if not license_id:
        reasons.append(
            "license is required: the MIDI file or arrangement is a separate work "
            "from the composition and needs its own terms"
        )
    else:
        implied = implied_redistribution(license_id)
        if implied == "prohibited":
            reasons.append(f"license {license_id} does not permit redistribution")
        elif implied == "unknown":
            reasons.append(
                f"license {license_id!r} is not one this project has established terms for; "
                "add it to the license table after reviewing it, or leave the file "
                "out of the redistributable set"
            )
        elif evidence.redistribution != implied:
            # Not merely a mismatch to normalize away: one of the two is wrong,
            # and guessing which would defeat the point of recording both.
            reasons.append(
                f"redistribution is {evidence.redistribution!r} but license "
                f"{license_id} implies {implied!r}"
            )
        elif implied == "permitted-with-attribution" and not (evidence.attribution or "").strip():
            reasons.append(
                f"attribution text is required by {license_id} and must be recorded "
                "so it can actually be displayed"
            )

    if evidence.redistribution not in {"permitted", "permitted-with-attribution"}:
        reasons.append(
            "redistribution must be established as permitted or "
            f"permitted-with-attribution (found {evidence.redistribution!r})"
        )

    return tuple(reasons)


def verify(evidence: RightsEvidence) -> None:
    """Raise unless the evidence supports the claim it carries."""
    reasons = audit(evidence)
    if reasons:
        raise RightsError(
            "rights_status 'verified-open' is not supported by the recorded evidence:\n  - "
            + "\n  - ".join(reasons)
        )


def attribution_required(evidence: RightsEvidence) -> bool:
    """Whether this asset obliges the player to credit someone.

    Deliberately coarse, and not a distribution-compliance check. A license can
    oblige far more than a credit line — ShareAlike terms on a derived work, for
    one — and this returns nothing about that. The stored ``license`` and
    ``license_url`` remain the source of license-specific obligations; this only
    answers whether a credit must be shown alongside playback.
    """
    return evidence.redistribution == "permitted-with-attribution"
