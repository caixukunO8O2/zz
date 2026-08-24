from collections import Counter
from pathlib import Path

import pytest

from app.domain.foods import StorageType
from app.domain.preservation import find_rule, load_seed_rules

SEED_PATH = Path(__file__).parents[2] / "app" / "seed" / "preservation_rules.csv"
SOURCE_NOTE = "V1 产品估算；实际状态受开封、温度和食品状态影响"


@pytest.fixture
def seed_rules():
    return load_seed_rules(SEED_PATH)


EXPECTED = {
    "fruit": {
        "草莓": (1, 5, 30), "香蕉": (5, 7, None), "苹果": (15, 30, 180),
        "葡萄": (2, 7, 90), "橙子": (10, 21, 180), "梨": (7, 30, 180),
        "桃": (2, 7, 180), "李子": (3, 7, 180), "樱桃": (1, 5, 180),
        "蓝莓": (2, 7, 180), "芒果": (5, 7, 180), "菠萝": (2, 5, 180),
        "西瓜": (3, 7, 180), "哈密瓜": (5, 7, 180), "猕猴桃": (7, 30, 180),
        "柠檬": (14, 30, 180), "柚子": (14, 30, 180), "石榴": (14, 60, 180),
        "火龙果": (5, 14, 180), "荔枝": (2, 5, 180),
    },
    "vegetable": {
        "西兰花": (1, 5, 180), "菠菜": (1, 3, 180), "生菜": (1, 5, None),
        "白菜": (3, 7, 180), "卷心菜": (7, 21, 180), "胡萝卜": (7, 30, 365),
        "土豆": (30, 90, None), "番茄": (7, 10, 180), "黄瓜": (3, 7, None),
        "茄子": (3, 7, 180), "青椒": (5, 10, 180), "芹菜": (3, 14, 180),
        "菜花": (2, 7, 180), "蘑菇": (1, 5, 180), "洋葱": (30, 60, 180),
        "南瓜": (30, 90, 365), "玉米": (2, 5, 180), "豆角": (2, 5, 180),
        "韭菜": (1, 5, 180), "油菜": (1, 5, 180),
    },
    "meat": {
        "猪肉": (None, 3, 180), "牛肉": (None, 3, 240), "羊肉": (None, 3, 240),
        "鸡肉": (None, 2, 270), "鸭肉": (None, 2, 180), "鸡胸肉": (None, 2, 270),
        "肉馅": (None, 1, 120), "香肠": (7, 14, 60), "培根": (7, 14, 30),
        "火腿": (7, 7, 60),
    },
    "dairy": {
        "鲜牛奶": (None, 7, 30), "酸奶": (None, 14, 60), "奶酪": (None, 21, 180),
        "黄油": (1, 90, 270), "淡奶油": (None, 7, 90), "炼乳": (30, 90, 180),
        "奶粉": (180, 365, None), "奶油奶酪": (None, 14, 60), "鸡蛋": (7, 30, 90),
        "冰淇淋": (None, None, 60),
    },
    "cooked": {
        "米饭": (None, 2, 30), "面条": (None, 2, 30), "粥": (None, 2, 30),
        "炒菜": (None, 3, 30), "炖肉": (None, 3, 60), "卤味": (None, 3, 30),
        "熟鸡蛋": (None, 7, 30), "熟海鲜": (None, 2, 30), "馒头": (2, 5, 30),
        "披萨": (1, 3, 30),
    },
}


def test_seed_has_required_category_counts(seed_rules):
    counts = Counter(rule.category for rule in seed_rules)
    assert counts == {"fruit": 20, "vegetable": 20, "meat": 10, "dairy": 10, "cooked": 10}


def test_seed_has_exact_names_days_and_metadata(seed_rules):
    assert len(seed_rules) == 70
    assert {(rule.category, rule.name) for rule in seed_rules} == {
        (category, name) for category, values in EXPECTED.items() for name in values
    }
    for rule in seed_rules:
        room, chilled, frozen = EXPECTED[rule.category][rule.name]
        assert (rule.room_days, rule.chilled_days, rule.frozen_days) == (room, chilled, frozen)
        assert rule.version == "v1"
        assert rule.source_note == SOURCE_NOTE


def test_requirement_examples_are_exact(seed_rules):
    assert find_rule(seed_rules, "草莓").days_for(StorageType.CHILLED) == 5
    assert find_rule(seed_rules, "香蕉").days_for(StorageType.FROZEN) is None
    assert find_rule(seed_rules, "苹果").days_for(StorageType.FROZEN) == 180
    assert find_rule(seed_rules, "鸡蛋").days_for(StorageType.CHILLED) == 30


def test_alias_match_is_normalized_and_exact(seed_rules):
    assert find_rule(seed_rules, " 牛 奶 ").name == "鲜牛奶"
    assert find_rule(seed_rules, "西红柿").name == "番茄"
    assert find_rule(seed_rules, "花 椰 菜").name == "菜花"
    assert find_rule(seed_rules, "青花菜").name == "西兰花"
    assert find_rule(seed_rules, "鲜 鸡 蛋").name == "鸡蛋"
    assert find_rule(seed_rules, "牛奶制品") is None


def test_aliases_are_exactly_the_seed_aliases(seed_rules):
    aliases = {rule.name: rule.aliases for rule in seed_rules if rule.aliases}
    assert aliases == {
        "鲜牛奶": ("牛奶", "纯牛奶"),
        "番茄": ("西红柿",),
        "菜花": ("花椰菜",),
        "西兰花": ("青花菜",),
        "鸡蛋": ("生鸡蛋", "鲜鸡蛋"),
    }


def write_csv(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "rules.csv"
    path.write_text(content, encoding="utf-8", newline="")
    return path


CSV_HEADER = "name,aliases,category,room_days,chilled_days,frozen_days,source_note,version\n"


def test_loader_rejects_duplicate_normalized_names(tmp_path):
    content = CSV_HEADER + (
        "苹果,,fruit,1,2,3,note,v1\n"
        "苹 果,,fruit,1,2,3,note,v1\n"
        + "香蕉,,fruit,1,2,3,note,v1\n" * 18
        + "菠菜,,vegetable,1,2,3,note,v1\n" * 20
        + "猪肉,,meat,,2,3,note,v1\n" * 10
        + "鲜牛奶,苹果,dairy,,2,3,note,v1\n"
        + "酸奶,,dairy,,2,3,note,v1\n" * 9
        + "米饭,,cooked,,2,3,note,v1\n" * 10
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_seed_rules(write_csv(tmp_path, content))


def test_loader_rejects_duplicate_normalized_aliases(tmp_path):
    content = CSV_HEADER + (
        "苹果,红苹果,fruit,1,2,3,note,v1\n"
        "香蕉,红 苹 果,fruit,1,2,3,note,v1\n"
        + "桃,,fruit,1,2,3,note,v1\n" * 18
        + "菠菜,,vegetable,1,2,3,note,v1\n" * 20
        + "猪肉,,meat,,2,3,note,v1\n" * 10
        + "鲜牛奶,,dairy,,2,3,note,v1\n"
        + "酸奶,,dairy,,2,3,note,v1\n" * 9
        + "米饭,,cooked,,2,3,note,v1\n" * 10
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_seed_rules(write_csv(tmp_path, content))


def test_loader_rejects_negative_days(tmp_path):
    content = CSV_HEADER + "苹果,,-1,1,2,3,note,v1\n"
    with pytest.raises(ValueError, match="category"):
        load_seed_rules(write_csv(tmp_path, content))
    content = CSV_HEADER + "苹果,,fruit,-1,2,3,note,v1\n"
    with pytest.raises(ValueError, match="negative"):
        load_seed_rules(write_csv(tmp_path, content))


def test_loader_rejects_missing_or_wrong_category_counts(tmp_path):
    content = CSV_HEADER + "苹果,,fruit,1,2,3,note,v1\n"
    with pytest.raises(ValueError, match="category"):
        load_seed_rules(write_csv(tmp_path, content))
    content = CSV_HEADER + "苹果,,,1,2,3,note,v1\n"
    with pytest.raises(ValueError, match="missing category"):
        load_seed_rules(write_csv(tmp_path, content))


def test_empty_storage_cells_map_to_none_not_zero(seed_rules):
    rule = find_rule(seed_rules, "香蕉")
    assert rule.frozen_days is None
    assert rule.frozen_days != 0
