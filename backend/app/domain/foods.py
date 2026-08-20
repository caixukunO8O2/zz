"""Food-domain enumerations shared by pure business rules."""

from enum import StrEnum


class StorageType(StrEnum):
    """The storage locations recognised by the food domain."""

    ROOM = "room"
    CHILLED = "chilled"
    FROZEN = "frozen"


class DateBasis(StrEnum):
    """The source used to determine a food's consume-by date."""

    DECLARED_EXPIRY = "declared_expiry"
    PRODUCTION_PLUS_SHELF_LIFE = "production_plus_shelf_life"
    KNOWLEDGE_BASE_ESTIMATE = "knowledge_base_estimate"
    MANUAL_USER_SET = "manual_user_set"


class FoodLifecycle(StrEnum):
    """The lifecycle states recognised by the food domain."""

    ACTIVE = "active"
    EXPIRED = "expired"
    DELETED = "deleted"


class FreshnessBucket(StrEnum):
    """The urgency grouping shown on the home screen."""

    EXPIRED = "expired"
    URGENT = "urgent"
    THIS_WEEK = "this_week"
    NORMAL = "normal"
