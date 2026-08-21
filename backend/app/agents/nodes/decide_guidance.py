"""Convert accumulated evidence into an exact client scanning instruction."""

from app.agents.state import AnalysisState

FRESH_CATEGORIES = {"fruit", "vegetable", "meat"}


def decide_guidance(state: AnalysisState) -> dict[str, object]:
    fields = state["fields"]
    calculation = state.get("date_calculation")
    if state.get("conflicts") or (calculation is not None and calculation.conflict):
        return {
            "status": "needs_input",
            "missing_fields": ["date"],
            "next_guidance": "识别到不一致的日期，请确认包装信息",
        }
    if fields.food_name is None:
        return {
            "status": "needs_input",
            "missing_fields": ["food_name"],
            "next_guidance": "没有认出是什么，请对准商品正面继续扫描",
        }
    category = fields.category.value if fields.category is not None else None
    has_package_date = fields.declared_expiry_date is not None or (
        fields.production_date is not None and fields.shelf_life_days is not None
    )
    if not has_package_date and category not in FRESH_CATEGORIES:
        return {
            "status": "needs_input",
            "missing_fields": ["date"],
            "next_guidance": "请对准生产日期、有效期或保质期区域",
        }
    if fields.storage_type is None:
        return {
            "status": "needs_input",
            "missing_fields": ["storage_type"],
            "next_guidance": "没有识别到保存方式，请扫描储存说明或手动选择",
        }
    if calculation is None:
        return {
            "status": "needs_input",
            "missing_fields": ["date"],
            "next_guidance": "请确认建议食用日期",
        }
    return {"status": "ready", "missing_fields": [], "next_guidance": "识别完成，请确认"}

