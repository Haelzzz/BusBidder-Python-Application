"""The hard constraints a traveller's request can impose.

Destination, travel window and seats always apply: they define what the
request means. The others apply only when the traveller sets them (a limit of
``None`` or a requirement of ``False`` in ``TravellerRequest`` means "no
requirement").

The order of the classes in this file is the order they are listed to the user.
"""

from busbidder.filtering.base import CONSTRAINTS, Constraint
from busbidder.models import Offer, TravellerRequest


def _duration(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


@CONSTRAINTS.register("destination")
class DestinationConstraint(Constraint):
    plain_reason = "other destination"

    def requirement(self, request: TravellerRequest) -> str:
        return f"goes to {request.destination_id}"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if offer.destination.destination_id != request.destination_id:
            return f"goes to {offer.destination.name}"
        return None


@CONSTRAINTS.register("travel_window")
class TravelWindowConstraint(Constraint):
    """The departure date must be in the window; an overnight arrival may fall after it."""

    plain_reason = "other dates"

    def requirement(self, request: TravellerRequest) -> str:
        return f"departs between {request.earliest_date} and {request.latest_date}"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if not request.covers(offer.travel_date):
            return f"departs on {offer.travel_date}"
        return None


@CONSTRAINTS.register("seats")
class SeatsConstraint(Constraint):
    plain_reason = "too few seats"

    def requirement(self, request: TravellerRequest) -> str:
        return f"at least {request.seats} seat(s) available"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if offer.available_seats < request.seats:
            return f"only {offer.available_seats} seat(s) left"
        return None


@CONSTRAINTS.register("budget")
class BudgetConstraint(Constraint):
    """The budget covers the whole booking: ticket price times seats."""

    plain_reason = "over budget"

    def is_active(self, request: TravellerRequest) -> bool:
        return request.max_budget_eur is not None

    def requirement(self, request: TravellerRequest) -> str:
        return f"total price at most EUR {request.max_budget_eur:.2f}"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        total = offer.price_eur * request.seats
        if request.max_budget_eur is not None and total > request.max_budget_eur:
            return f"costs EUR {total:.2f}"
        return None


@CONSTRAINTS.register("max_transfers")
class MaxTransfersConstraint(Constraint):
    plain_reason = "too many transfers"

    def is_active(self, request: TravellerRequest) -> bool:
        return request.max_transfers is not None

    def requirement(self, request: TravellerRequest) -> str:
        return f"at most {request.max_transfers} transfer(s)"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if request.max_transfers is not None and offer.transfers > request.max_transfers:
            return f"has {offer.transfers} transfer(s)"
        return None


@CONSTRAINTS.register("max_duration")
class MaxDurationConstraint(Constraint):
    plain_reason = "journey too long"

    def is_active(self, request: TravellerRequest) -> bool:
        return request.max_duration_min is not None

    def requirement(self, request: TravellerRequest) -> str:
        return f"journey at most {_duration(request.max_duration_min or 0)}"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if request.max_duration_min is not None and offer.duration_min > request.max_duration_min:
            return f"takes {_duration(offer.duration_min)}"
        return None


@CONSTRAINTS.register("luggage")
class LuggageConstraint(Constraint):
    plain_reason = "too little luggage"

    def is_active(self, request: TravellerRequest) -> bool:
        return request.min_luggage_kg > 0

    def requirement(self, request: TravellerRequest) -> str:
        return f"at least {request.min_luggage_kg} kg luggage included"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if offer.fare.luggage_kg < request.min_luggage_kg:
            return f"includes {offer.fare.luggage_kg} kg luggage"
        return None


@CONSTRAINTS.register("changeable")
class ChangeableConstraint(Constraint):
    plain_reason = "ticket not changeable"

    def is_active(self, request: TravellerRequest) -> bool:
        return request.require_changeable

    def requirement(self, request: TravellerRequest) -> str:
        return "ticket must be changeable"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if not offer.fare.changeable:
            return f"{offer.fare.fare_type} fare is not changeable"
        return None


@CONSTRAINTS.register("refundable")
class RefundableConstraint(Constraint):
    plain_reason = "ticket not refundable"

    def is_active(self, request: TravellerRequest) -> bool:
        return request.require_refundable

    def requirement(self, request: TravellerRequest) -> str:
        return "ticket must be refundable"

    def violation(self, offer: Offer, request: TravellerRequest) -> str | None:
        if not offer.fare.refundable:
            return f"{offer.fare.fare_type} fare is not refundable"
        return None
