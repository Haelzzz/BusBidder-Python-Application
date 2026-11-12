"""The ranking criteria. A criterion is only used when the traveller gives it a weight.

The order of the classes in this file is the order of the columns in the output.
"""

from busbidder.models import Offer, TravellerRequest
from busbidder.ranking.base import CRITERIA, FixedScaleCriterion, RatioToBestCriterion

MINUTES_PER_DAY = 24 * 60
DEPARTURE_TOLERANCE_MIN = 6 * 60  

FLEXIBILITY_POINTS = {0: 0.0, 1: 60.0, 2: 100.0}
FLEXIBILITY_LABELS = {0: "none", 1: "change", 2: "refund"}


def _hours(minutes: float) -> str:
    minutes = int(minutes)
    return f"{minutes // 60}h{minutes % 60:02d}"


@CRITERIA.register("price")
class PriceCriterion(RatioToBestCriterion):
    label = "Price"

    def raw_value(self, offer: Offer, request: TravellerRequest) -> float | None:
        return offer.price_eur

    def format_raw(self, raw: float) -> str:
        return f"{raw:.2f}"


@CRITERIA.register("duration")
class DurationCriterion(RatioToBestCriterion):
    label = "Duration"

    def raw_value(self, offer: Offer, request: TravellerRequest) -> float | None:
        return offer.duration_min

    def format_raw(self, raw: float) -> str:
        return _hours(raw)


@CRITERIA.register("departure")
class DepartureCriterion(FixedScaleCriterion):
    """Minutes between departure and the preferred time, measured around the clock.

    Without a preferred time the value is missing for every offer, so all
    offers get the same (neutral) score and the criterion has no effect.
    """

    label = "Departure"

    def raw_value(self, offer: Offer, request: TravellerRequest) -> float | None:
        if request.preferred_departure is None:
            return None
        departure = offer.departure.hour * 60 + offer.departure.minute
        preferred = request.preferred_departure.hour * 60 + request.preferred_departure.minute
        difference = abs(departure - preferred)
        return min(difference, MINUTES_PER_DAY - difference)  

    def score(self, raw: float) -> float:
        return 100.0 * max(0.0, 1 - raw / DEPARTURE_TOLERANCE_MIN)

    def format_raw(self, raw: float) -> str:
        return "on time" if raw == 0 else f"{_hours(raw)} off"


@CRITERIA.register("flexibility")
class FlexibilityCriterion(FixedScaleCriterion):
    """Level 0: not changeable, 1: changeable, 2: changeable and refundable."""

    label = "Flexibility"

    def raw_value(self, offer: Offer, request: TravellerRequest) -> float | None:
        if offer.fare.refundable and offer.fare.changeable:
            return 2
        return 1 if offer.fare.changeable else 0

    def score(self, raw: float) -> float:
        return FLEXIBILITY_POINTS[int(raw)]

    def format_raw(self, raw: float) -> str:
        return FLEXIBILITY_LABELS[int(raw)]


@CRITERIA.register("emissions")
class EmissionsCriterion(RatioToBestCriterion):
    """Estimated kg CO2 per passenger. Optional in the data, so it can be missing."""

    label = "CO2"

    def raw_value(self, offer: Offer, request: TravellerRequest) -> float | None:
        return offer.co2_kg

    def format_raw(self, raw: float) -> str:
        return f"{raw:.1f}"
