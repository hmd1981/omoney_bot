from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable, Sequence, TypeVar

LOGS_DIR = Path("/app/logs")
THEMES_HISTORY_FILE = LOGS_DIR / "last_themes.json"
VISUALS_HISTORY_FILE = LOGS_DIR / "last_visuals.json"
CTAS_HISTORY_FILE = LOGS_DIR / "last_ctas.json"
COMPOSITIONS_HISTORY_FILE = LOGS_DIR / "last_compositions.json"
ROTATION_DIMS_FILE = LOGS_DIR / "last_rotation_dims.json"

THEME_CONSECUTIVE_BLOCK = 1
VISUAL_COOLDOWN = 7
CTA_COOLDOWN = 5
COMPOSITION_CONSECUTIVE_BLOCK = 1
AXIS_COOLDOWN = 4

T = TypeVar("T")


def _ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _load_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, list):
        return [str(item) for item in payload]
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [str(item) for item in items]
    return []


def _save_list(path: Path, items: list[str], *, max_items: int = 32) -> None:
    _ensure_logs_dir()
    trimmed = items[-max_items:]
    path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def _append(path: Path, value: str, *, max_items: int = 32) -> list[str]:
    history = _load_list(path)
    history.append(value)
    _save_list(path, history, max_items=max_items)
    return history


def record_theme(theme_id: str) -> None:
    _append(THEMES_HISTORY_FILE, theme_id)


def record_visual(visual_id: str) -> None:
    _append(VISUALS_HISTORY_FILE, visual_id)


def record_cta(cta: str) -> None:
    _append(CTAS_HISTORY_FILE, cta)


def record_composition(profile_id: str) -> None:
    _append(COMPOSITIONS_HISTORY_FILE, profile_id)


def _load_dims() -> dict[str, list[str]]:
    if not ROTATION_DIMS_FILE.exists():
        return {}
    try:
        payload = json.loads(ROTATION_DIMS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            result[str(key)] = [str(item) for item in value]
    return result


def _save_dims(dims: dict[str, list[str]]) -> None:
    _ensure_logs_dir()
    trimmed = {key: values[-AXIS_COOLDOWN * 3 :] for key, values in dims.items()}
    ROTATION_DIMS_FILE.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def record_rotation_axis(axis: str, value: str) -> None:
    dims = _load_dims()
    history = dims.get(axis, [])
    history.append(value)
    dims[axis] = history[-AXIS_COOLDOWN * 3 :]
    _save_dims(dims)


def record_rotation_bundle(bundle: dict[str, str]) -> None:
    for axis, value in bundle.items():
        if value:
            record_rotation_axis(axis, value)


def _blocked_recent(history: list[str], cooldown: int) -> set[str]:
    if cooldown <= 0 or not history:
        return set()
    return set(history[-cooldown:])


def _blocked_consecutive(history: list[str]) -> set[str]:
    if len(history) < 1:
        return set()
    return {history[-1]}


def pick_weighted(
    items: Sequence[T],
    rng: random.Random,
    *,
    weight_key: Callable[[T], float] | None = None,
) -> T:
    if not items:
        raise ValueError("pick_weighted requires a non-empty pool")
    if weight_key is None:
        return rng.choice(list(items))
    weights = [max(0.01, float(weight_key(item))) for item in items]
    return rng.choices(list(items), weights=weights, k=1)[0]


def pick_avoiding(
    pool: Sequence[T],
    history: list[str],
    key: Callable[[T], str],
    rng: random.Random,
    *,
    cooldown: int = 0,
    block_consecutive: bool = False,
    attempts: int = 48,
) -> T:
    if not pool:
        raise ValueError("pick_avoiding requires a non-empty pool")
    blocked = _blocked_recent(history, cooldown)
    if block_consecutive:
        blocked |= _blocked_consecutive(history)
    candidates = [item for item in pool if key(item) not in blocked]
    if not candidates:
        candidates = [item for item in pool if key(item) not in _blocked_consecutive(history)]
    if not candidates:
        candidates = list(pool)
    return rng.choice(candidates)


def pick_theme(pool: Sequence[T], key: Callable[[T], str], rng: random.Random) -> T:
    return pick_avoiding(
        pool,
        _load_list(THEMES_HISTORY_FILE),
        key,
        rng,
        cooldown=THEME_CONSECUTIVE_BLOCK,
        block_consecutive=True,
    )


def pick_visual(pool: Sequence[T], key: Callable[[T], str], rng: random.Random) -> T:
    return pick_avoiding(
        pool,
        _load_list(VISUALS_HISTORY_FILE),
        key,
        rng,
        cooldown=VISUAL_COOLDOWN,
        block_consecutive=False,
    )


def pick_composition(pool: Sequence[T], key: Callable[[T], str], rng: random.Random) -> T:
    return pick_avoiding(
        pool,
        _load_list(COMPOSITIONS_HISTORY_FILE),
        key,
        rng,
        cooldown=COMPOSITION_CONSECUTIVE_BLOCK,
        block_consecutive=True,
    )


def pick_axis(axis: str, pool: Sequence[str], rng: random.Random) -> str:
    history = _load_dims().get(axis, [])
    blocked = _blocked_recent(history, AXIS_COOLDOWN) | _blocked_consecutive(history)
    candidates = [item for item in pool if item not in blocked]
    if not candidates:
        candidates = [item for item in pool if item not in _blocked_consecutive(history)] or list(pool)
    return rng.choice(candidates)
