import json
import time
from typing import Dict, Any, List

from pieces import Piece
from game import Game


def _piece_to_dict(p: Piece) -> Dict[str, Any]:
    """Перетворює фігуру в JSON-дружній словник."""
    return {
        "name": p.name,
        "cells": [[int(x), int(y)] for x, y in p.cells],
        "w": int(p.w),
        "h": int(p.h),
    }


def build_state_dict(game: Game, game_over: bool) -> Dict[str, Any]:
    """Збирає повний стан гри у словник для збереження/передачі AI."""
    hand_out: List[Dict[str, Any]] = []
    for slot_i, p in enumerate(game.hand):
        if p is None:
            hand_out.append({"slot": slot_i, "empty": True, "piece": None})
        else:
            hand_out.append({"slot": slot_i, "empty": False, "piece": _piece_to_dict(p)})

    combo_info = {
        "combo": int(game.combo),
        "combo_active": bool(game.combo > 0), 
    }

    return {
        "meta": {
            "version": 2,
            "timestamp_ms": int(time.time() * 1000),
        },
        "board": {
            "size": int(game.size),
            "grid": [list(map(int, row)) for row in game.grid],
        },
        "score": int(game.score),
        "hand": hand_out,
        "combo": combo_info,
        "status": {
            "game_over": bool(game_over),
            "any_move_available": bool(game.any_move_available()),
        },
    }


def write_state_json(path: str, game: Game, game_over: bool) -> None:
    """Записує стан гри у файл JSON."""
    state = build_state_dict(game, game_over)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
