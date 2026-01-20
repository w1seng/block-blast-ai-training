import json
import os
import time
import threading
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
import ai_trainer 


STATE_PATH = "state.json"
ACTION_PATH = "action.json"
RESTART_PATH = "restart.json"
WEIGHTS_PATH = "weights.json"
GENERIC_PATH = "stats.json"

POLL_DELAY_SEC = 0.05
MOVE_COOLDOWN_SEC = 0.02

FALLBACK_WEIGHTS = {
    'holes': -8.0,
    'max_height': -3.0,
    'avg_height': -1.0,
    'filled': -0.3,
    'edge_penalty': -2.0,
    'cluster_score': 4.0,
    'row_almost_full': 15.0,
    'col_almost_full': 15.0,
    'empty_rows': 5.0,
    'combo_preservation': 50.0,
    'piece_fit': 8.0,
    'diversity': 3.0,
    'cleared_lines': 100.0,
    'immediate_gain': 1.0,
}


def load_weights(path: str, fallback: dict) -> dict:
    """Завантажує ваги з файлу або використовує fallback."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for key in fallback:
            if key not in data:
                raise ValueError(f"Missing weight: {key}")

        return {k: float(v) for k, v in data.items()}

    except Exception as e:
        print(f"⚠️ Не вдалося завантажити ваги ({e}), використовую fallback")
        return fallback.copy()


@dataclass
class Piece:
    """Фігура з клітинками."""
    cells: List[Tuple[int, int]]
    slot: int


@dataclass
class GameState:
    """Стан гри."""
    grid: List[List[int]]
    hand: List[Optional[Piece]]
    combo: int
    combo_active: bool
    score: int
    size: int


@dataclass
class SimulatedState:
    """Симульований стан після ходу."""
    grid: List[List[int]]
    cleared_lines: int
    score_gain: int
    piece: Piece
    gx: int
    gy: int


def load_state(path: str) -> Optional[GameState]:
    """Завантажує та парсить state.json."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    
    status = data.get("status", {})
    if status.get("game_over") or not status.get("any_move_available", True):
        return None
    
    board = data.get("board", {})
    grid = board.get("grid", [])
    size = board.get("size", 8)
    
    hand_data = data.get("hand", [])
    hand: List[Optional[Piece]] = [None, None, None]
    
    for entry in hand_data:
        slot_idx = int(entry.get("slot", 0))
        if entry.get("empty", True):
            hand[slot_idx] = None
        else:
            piece_data = entry.get("piece")
            if piece_data:
                cells = [(int(x), int(y)) for x, y in piece_data.get("cells", [])]
                hand[slot_idx] = Piece(cells=cells, slot=slot_idx)
    
    combo_data = data.get("combo", {})
    combo = int(combo_data.get("combo", 0))
    combo_active = bool(combo_data.get("combo_active", False))
    
    score = int(data.get("score", 0))
    
    return GameState(
        grid=grid,
        hand=hand,
        combo=combo,
        combo_active=combo_active,
        score=score,
        size=size
    )


def can_place(grid: List[List[int]], piece: Piece, gx: int, gy: int) -> bool:
    """Перевіряє чи можна поставити фігуру."""
    size = len(grid)
    for dx, dy in piece.cells:
        x, y = gx + dx, gy + dy
        if x < 0 or y < 0 or x >= size or y >= size:
            return False
        if grid[y][x] == 1:
            return False
    return True


def place_piece(grid: List[List[int]], piece: Piece, gx: int, gy: int) -> None:
    """Розміщує фігуру на сітці (мутує grid!)."""
    for dx, dy in piece.cells:
        grid[gy + dy][gx + dx] = 1


def clear_lines(grid: List[List[int]]) -> int:
    """Очищає повні лінії, повертає кількість очищених."""
    size = len(grid)
    
    full_rows = [r for r in range(size) if all(grid[r][c] == 1 for c in range(size))]
    full_cols = [c for c in range(size) if all(grid[r][c] == 1 for r in range(size))]
    
    for r in full_rows:
        for c in range(size):
            grid[r][c] = 0
    
    for c in full_cols:
        for r in range(size):
            grid[r][c] = 0
    
    return len(full_rows) + len(full_cols)


def calculate_score_gain(cleared: int, combo: int) -> int:
    """Рахує нарахування очків за твоєю формулою."""
    if cleared <= 0:
        return 0
    
    base = 10 * cleared
    bonus = base * (combo + 1)
    
    if cleared > 2:
        bonus *= (cleared - 1)
    
    return bonus


def simulate_move(state: GameState, piece: Piece, gx: int, gy: int) -> Optional[SimulatedState]:
    """Симулює хід, повертає новий стан."""
    if not can_place(state.grid, piece, gx, gy):
        return None
    
    new_grid = [row[:] for row in state.grid]
    
    place_piece(new_grid, piece, gx, gy)
    
    base_gain = len(piece.cells)
    
    cleared = clear_lines(new_grid)
    
    clear_gain = calculate_score_gain(cleared, state.combo)
    total_gain = base_gain + clear_gain
    
    return SimulatedState(
        grid=new_grid,
        cleared_lines=cleared,
        score_gain=total_gain,
        piece=piece,
        gx=gx,
        gy=gy
    )


def calc_holes(grid: List[List[int]]) -> float:
    """Кількість дірок (порожніх клітинок під заповненими)."""
    size = len(grid)
    holes = 0
    
    for x in range(size):
        seen_block = False
        for y in range(size):
            if grid[y][x] == 1:
                seen_block = True
            elif seen_block and grid[y][x] == 0:
                holes += 1
    
    return float(holes)


def calc_max_height(grid: List[List[int]]) -> float:
    """Максимальна висота стовпців."""
    size = len(grid)
    max_h = 0
    
    for x in range(size):
        for y in range(size):
            if grid[y][x] == 1:
                h = size - y
                max_h = max(max_h, h)
                break
    
    return float(max_h)


def calc_avg_height(grid: List[List[int]]) -> float:
    """Середня висота стовпців."""
    size = len(grid)
    heights = []
    
    for x in range(size):
        for y in range(size):
            if grid[y][x] == 1:
                heights.append(size - y)
                break
        else:
            heights.append(0)
    
    return sum(heights) / len(heights) if heights else 0.0


def calc_filled(grid: List[List[int]]) -> float:
    """Загальна заповненість поля."""
    total = sum(sum(row) for row in grid)
    return float(total)


def calc_edge_penalty(grid: List[List[int]], piece: Piece, gx: int, gy: int) -> float:
    """Штраф за розміщення біля країв (ризиковано)."""
    size = len(grid)
    edge_cells = 0
    
    for dx, dy in piece.cells:
        x, y = gx + dx, gy + dy
        if x == 0 or x == size - 1 or y == 0 or y == size - 1:
            edge_cells += 1
    
    return float(edge_cells)


def calc_cluster_score(grid: List[List[int]]) -> float:
    """Скупченість блоків (добре для майбутніх очищень)."""
    size = len(grid)
    cluster = 0
    
    for y in range(size):
        for x in range(size):
            if grid[y][x] == 1:
                neighbors = 0
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < size and 0 <= ny < size and grid[ny][nx] == 1:
                        neighbors += 1
                cluster += neighbors
    
    return float(cluster)


def calc_row_almost_full(grid: List[List[int]]) -> float:
    """Кількість майже повних рядків (6-7 з 8 клітинок)."""
    size = len(grid)
    almost_full = 0
    
    for y in range(size):
        filled = sum(grid[y])
        if size - 2 <= filled < size:
            almost_full += 1
    
    return float(almost_full)


def calc_col_almost_full(grid: List[List[int]]) -> float:
    """Кількість майже повних колонок."""
    size = len(grid)
    almost_full = 0
    
    for x in range(size):
        filled = sum(grid[y][x] for y in range(size))
        if size - 2 <= filled < size:
            almost_full += 1
    
    return float(almost_full)


def calc_empty_rows(grid: List[List[int]]) -> float:
    """Кількість повністю порожніх рядків (простір для маневру)."""
    size = len(grid)
    empty = 0
    
    for y in range(size):
        if sum(grid[y]) == 0:
            empty += 1
    
    return float(empty)


def calc_combo_preservation(combo: int, combo_active: bool, cleared: int) -> float:
    """Цінність збереження комбо."""
    if combo_active and cleared > 0:
        return 30.0 * cleared

    if not combo_active and cleared > 0:
        return 10.0 * cleared

    return 0.0


def calc_piece_fit(grid: List[List[int]], piece: Piece, gx: int, gy: int) -> float:
    """Наскільки добре фігура заповнює простір."""
    size = len(grid)
    fit_score = 0
    
    for dx, dy in piece.cells:
        x, y = gx + dx, gy + dy
        
        neighbors = 0
        for ndx, ndy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
            nx, ny = x + ndx, y + ndy
            if nx < 0 or ny < 0 or nx >= size or ny >= size:
                neighbors += 1
            elif grid[ny][nx] == 1:
                neighbors += 1
        
        fit_score += neighbors
    
    return float(fit_score)


def calc_diversity(grid: List[List[int]]) -> float:
    """Різноманітність висот (плоске поле краще ніж нерівне)."""
    size = len(grid)
    heights = []
    
    for x in range(size):
        for y in range(size):
            if grid[y][x] == 1:
                heights.append(size - y)
                break
        else:
            heights.append(0)
    
    if not heights:
        return 0.0
    
    avg = sum(heights) / len(heights)
    variance = sum((h - avg) ** 2 for h in heights) / len(heights)
    std_dev = variance ** 0.5
    
    return -std_dev


def evaluate_move(sim: SimulatedState, state: GameState, weights: Dict[str, float]) -> float:
    """Головна формула оцінки ходу: S = k1*b1 + k2*b2 + ... + kn*bn."""
    
    b1 = calc_holes(sim.grid)
    b2 = calc_max_height(sim.grid)
    b3 = calc_avg_height(sim.grid)
    b4 = calc_filled(sim.grid)
    b5 = calc_edge_penalty(sim.grid, sim.piece, sim.gx, sim.gy)
    b6 = calc_cluster_score(sim.grid)
    b7 = calc_row_almost_full(sim.grid)
    b8 = calc_col_almost_full(sim.grid)
    b9 = calc_empty_rows(sim.grid)
    b10 = calc_combo_preservation(state.combo, state.combo_active, sim.cleared_lines)
    b11 = calc_piece_fit(sim.grid, sim.piece, sim.gx, sim.gy)
    b12 = calc_diversity(sim.grid)
    b13 = float(sim.cleared_lines)
    b14 = float(sim.score_gain)
    
    value = (
        weights['holes'] * b1 +
        weights['max_height'] * b2 +
        weights['avg_height'] * b3 +
        weights['filled'] * b4 +
        weights['edge_penalty'] * b5 +
        weights['cluster_score'] * b6 +
        weights['row_almost_full'] * b7 +
        weights['col_almost_full'] * b8 +
        weights['empty_rows'] * b9 +
        weights['combo_preservation'] * b10 +
        weights['piece_fit'] * b11 +
        weights['diversity'] * b12 +
        weights['cleared_lines'] * b13 +
        weights['immediate_gain'] * b14
    )
    
    return value


def find_all_legal_moves(state: GameState) -> List[Tuple[Piece, int, int]]:
    """Знаходить всі можливі ходи (piece, gx, gy)."""
    moves = []
    
    for piece in state.hand:
        if piece is None:
            continue
        
        for gy in range(state.size):
            for gx in range(state.size):
                if can_place(state.grid, piece, gx, gy):
                    moves.append((piece, gx, gy))
    
    return moves


def choose_best_move(state: GameState, weights: Dict[str, float]) -> Optional[Tuple[int, int, int]]:
    """Знаходить найкращий хід за формулою оцінки. Повертає: (slot, gx, gy) або None."""
    legal_moves = find_all_legal_moves(state)
    
    if not legal_moves:
        return None
    
    best_move = None
    best_value = -1e18
    
    for piece, gx, gy in legal_moves:
        sim = simulate_move(state, piece, gx, gy)
        if sim is None:
            continue
        
        value = evaluate_move(sim, state, weights)
        
        if value > best_value:
            best_value = value
            best_move = (piece.slot, gx, gy)
    
    return best_move


def write_action(slot: int, gx: int, gy: int, move_id: int) -> None:
    """Записує хід в action.json атомарно з retry."""
    action = {
        "move_id": move_id,
        "slot": slot,
        "gx": gx,
        "gy": gy
    }
    
    tmp_path = ACTION_PATH + ".tmp"
    
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(action, f, ensure_ascii=False, indent=2)
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            if os.path.exists(ACTION_PATH):
                os.remove(ACTION_PATH)
            
            os.rename(tmp_path, ACTION_PATH)
            return
            
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.05)
            else:
                print(f"⚠️ Не вдалось записати action.json після {max_retries} спроб")
                try:
                    os.remove(tmp_path)
                except:
                    pass
                raise


class Toggle:
    """Потокобезпечний перемикач для AI."""
    
    def __init__(self):
        self.enabled = False
        self._lock = threading.Lock()
    
    def set(self, v: bool):
        with self._lock:
            self.enabled = v
    
    def get(self) -> bool:
        with self._lock:
            return self.enabled


def console_thread(toggle: Toggle):
    """Консольний інтерфейс для керування AI."""
    print("🤖 AI Control:")
    print("  on   - увімкнути AI")
    print("  off  - вимкнути AI")
    print("  quit - вийти")
    
    while True:
        cmd = input("> ").strip().lower()
        
        if cmd == "on":
            toggle.set(True)
            print("✅ AI увімкнено")
        elif cmd == "off":
            toggle.set(False)
            print("⸱️ AI на паузі")
        elif cmd in ("quit", "exit", "q"):
            toggle.set(False)
            print("👋 Вихід...")
            os._exit(0)
        else:
            print("❌ Команди: on / off / quit")


def main():
    """Головний цикл AI."""
    toggle = Toggle()
    
    try:
        with open(GENERIC_PATH, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except:
        stats = {}
    
    t = threading.Thread(target=console_thread, args=(toggle,), daemon=True)
    t.start()
    
    move_id = 0
    game = 4
    generic = 1
    max_combo = 0
    max_score = 0

    weights = load_weights(WEIGHTS_PATH, FALLBACK_WEIGHTS)
    print("🎮 AI запущено! Очікую на гру...")
    
    while True:
        if not toggle.get():
            time.sleep(0.1)
            continue
        
        if game == 1 and generic == 1 and move_id == 0:
            if ai_trainer.load_json(ai_trainer.STATS_FILE):
                ai_trainer.train()
                weights = load_weights(WEIGHTS_PATH, FALLBACK_WEIGHTS)
        
        time.sleep(POLL_DELAY_SEC)

        state = load_state(STATE_PATH)
        if state is None:
            stats[game] = {
                "Moves": move_id,
                "Score": max_score,
                "Max_Combo": max_combo
            }
            
            with open(GENERIC_PATH, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            
            game += 1
            move_id = 0
            max_combo = 0
            max_score = 0

            if game > 10:
                ai_trainer.train()
                weights = load_weights(WEIGHTS_PATH, FALLBACK_WEIGHTS)
                
                generic += 1
                game = 1
                stats = {}
    
            with open(RESTART_PATH, "w", encoding="utf-8") as f:
                json.dump({"restart": True}, f, ensure_ascii=False, indent=2)

            continue
        
        if state.combo > max_combo:
            max_combo = state.combo
        if state.score > max_score:
            max_score = state.score

        best = choose_best_move(state, weights)
        
        if best is None:
            continue
        
        slot, gx, gy = best
        
        move_id += 1
        write_action(slot, gx, gy, move_id)
        print(f"Покоління {generic} Гра {game} Хід #{move_id}, Рахунок {state.score}, combo={state.combo}")
        
        time.sleep(MOVE_COOLDOWN_SEC)


if __name__ == "__main__":
    main()