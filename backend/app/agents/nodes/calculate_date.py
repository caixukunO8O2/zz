"""Calculate the best consume-by date from merged scan evidence."""

from app.agents.state import AnalysisDependencies, AnalysisState
from app.domain.date_rules import DateRuleError, MissingDateBasisError, calculate_consume_by
from app.domain.foods import StorageType


async def calculate_date(
    state: AnalysisState, dependencies: AnalysisDependencies
) -> dict[str, object]:
    fields = state["fields"]
    food_name = fields.food_name.value if fields.food_name is not None else None
    storage = fields.storage_type.value if fields.storage_type is not None else None
    knowledge_days = (
        await dependencies.rule_days(food_name, StorageType(storage))
        if food_name is not None and storage is not None
        else None
    )
    try:
        calculation = calculate_consume_by(
            fields.declared_expiry_date.value
            if fields.declared_expiry_date is not None
            else None,
            fields.production_date.value
            if fields.production_date is not None
            else None,
            fields.shelf_life_days.value
            if fields.shelf_life_days is not None
            else None,
            state["added_on"],
            knowledge_days,
        )
    except MissingDateBasisError:
        calculation = None
    except DateRuleError:
        calculation = None
    return {"date_calculation": calculation}

