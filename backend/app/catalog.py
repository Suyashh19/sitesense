"""Loads the versioned YAML configuration: city profile and category 'Retail DNA'. No application code knows a category by name."""
from dataclasses import dataclass
from functools import lru_cache

import yaml

from .config import CITY, CONFIG_DIR


@dataclass
class CityConfig:
    key: str
    name: str
    bbox: dict
    h3_resolution: int
    worldpop_url: str
    overpass_endpoints: list
    estimates: dict
    localities: list
    metro_stations: list


@lru_cache
def city(key: str = CITY) -> CityConfig:
    d = yaml.safe_load((CONFIG_DIR / f"city_{key}.yaml").read_text(encoding="utf-8"))
    return CityConfig(**{k: d[k] for k in CityConfig.__dataclass_fields__})


@lru_cache
def categories() -> dict:
    d = yaml.safe_load((CONFIG_DIR / "categories.yaml").read_text(encoding="utf-8"))
    for key, c in d["categories"].items():  # BR-01 / AC-07.1: every profile must sum to 100 and cover FG1..FG10
        assert set(c["dna"]) == set(d["factor_groups"]), f"{key}: DNA must cover FG1..FG10"
        assert sum(c["dna"].values()) == 100, f"{key}: DNA weights must sum to 100"
    return d


def _add(sel: dict, selectors: list[dict]):
    for s in selectors:
        for k, vals in s.items():
            sel.setdefault(k, set()).update(vals)


def collect_selectors(cats: dict) -> dict[str, set]:
    """Union of every OSM key/value used by any category or shared layer -> one Overpass query per key."""
    sel: dict[str, set] = {}
    for c in cats["categories"].values():
        _add(sel, c["competitors"])
        _add(sel, c["complementors"])
    _add(sel, cats["anchors"])
    _add(sel, cats["education"])
    _add(sel, cats["hospitals"])
    _add(sel, cats["transit"]["station"])
    return sel


def matches(tags: dict, selectors: list[dict]) -> bool:
    """True if an OSM tag set matches any selector ({key: [values]}; '*' = any value)."""
    for s in selectors:
        for k, vals in s.items():
            v = tags.get(k)
            if v is not None and ("*" in vals or v in vals):
                return True
    return False
