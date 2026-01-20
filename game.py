import random
from typing import List, Optional
from pieces import Piece, PIECE_POOL


class Game:
    """Логіка гри Block Blast з покращеними механіками."""
    
    def __init__(self, size: int = 8, seed=None):
        """Створює нову гру, ініціалізує поле та видає першу руку."""
        self.size = size
        self.grid = [[0] * size for _ in range(size)]
        self.score = 0
        self.rng = random.Random(seed)

        self.hand: List[Optional[Piece]] = [None, None, None]

        self.combo: int = 0
        self.combo_streak: bool = False
        self.hand_clears: int = 0        
        self.prev_hand_had_clear: bool = False

        self.last_action_score: int = 0
        self.last_lines_cleared: int = 0

        self.deal_hand_full(ensure_playable=True)

    def can_place(self, piece: Piece, gx: int, gy: int) -> bool:
        """Перевіряє, чи можна поставити фігуру у позицію (gx, gy) на полі."""
        for dx, dy in piece.cells:
            x, y = gx + dx, gy + dy
            if x < 0 or y < 0 or x >= self.size or y >= self.size:
                return False
            if self.grid[y][x] == 1:
                return False
        return True

    def _can_place_on(self, grid: List[List[int]], piece: Piece, gx: int, gy: int) -> bool:
        """Перевіряє чи можна розмістити фігуру на заданій сітці."""
        for dx, dy in piece.cells:
            x, y = gx + dx, gy + dy
            if x < 0 or y < 0 or x >= self.size or y >= self.size:
                return False
            if grid[y][x] == 1:
                return False
        return True

    def _simulate_on(self, grid: List[List[int]], piece: Piece, gx: int, gy: int) -> List[List[int]]:
        """Розміщує фігуру на копії сітки, очищає лінії, повертає нову сітку."""
        new_grid = [row[:] for row in grid]
        
        for dx, dy in piece.cells:
            new_grid[gy + dy][gx + dx] = 1
        
        for r in range(self.size):
            if all(new_grid[r][c] == 1 for c in range(self.size)):
                for c in range(self.size):
                    new_grid[r][c] = 0
        
        for c in range(self.size):
            if all(new_grid[r][c] == 1 for r in range(self.size)):
                for r in range(self.size):
                    new_grid[r][c] = 0
        
        return new_grid

    def _any_move_available_for_pieces(self, pieces: List[Piece]) -> bool:
        """Перевіряє, чи існує хоча б 1 хід для будь-якої фігури зі списку."""
        for p in pieces:
            for y in range(self.size):
                for x in range(self.size):
                    if self.can_place(p, x, y):
                        return True
        return False

    def any_move_available(self) -> bool:
        """Повертає True, якщо для поточної руки існує хоча б 1 можливий хід."""
        pieces = [p for p in self.hand if p is not None]
        if not pieces:
            return True
        return self._any_move_available_for_pieces(pieces)

    def deal_hand_full(self, ensure_playable: bool = True, max_rolls: int = 600) -> None:
        """Видає нову руку з 3 фігур використовуючи жадібний алгоритм."""
        if not ensure_playable:
            self.hand = [self.rng.choice(PIECE_POOL) for _ in range(3)]
            return

        remaining = list(range(len(PIECE_POOL)))
        next_hand = []
        current_grid = [row[:] for row in self.grid]

        for _ in range(3):
            placed = False
            self.rng.shuffle(remaining)
            
            for piece_idx in remaining:
                piece = PIECE_POOL[piece_idx]
                
                for y in range(self.size):
                    for x in range(self.size):
                        if self._can_place_on(current_grid, piece, x, y):
                            next_hand.append(piece)
                            current_grid = self._simulate_on(current_grid, piece, x, y)
                            placed = True
                            break
                    if placed:
                        break
                
                if placed:
                    remaining.remove(piece_idx)
                    break
            
            if not placed:
                smallest = min(PIECE_POOL, key=lambda p: len(p.cells))
                for y in range(self.size):
                    for x in range(self.size):
                        if self._can_place_on(current_grid, smallest, x, y):
                            next_hand.append(smallest)
                            current_grid = self._simulate_on(current_grid, smallest, x, y)
                            placed = True
                            break
                    if placed:
                        break
                
                if not placed:
                    next_hand.append(self.rng.choice(PIECE_POOL))

        self.hand = next_hand

    def clear_lines(self) -> int:
        """Очищає повні рядки та колонки, повертає кількість очищених ліній."""
        s = self.size
        full_rows = [r for r in range(s) if all(self.grid[r][c] == 1 for c in range(s))]
        full_cols = [c for c in range(s) if all(self.grid[r][c] == 1 for r in range(s))]

        for r in full_rows:
            for c in range(s):
                self.grid[r][c] = 0
        for c in full_cols:
            for r in range(s):
                self.grid[r][c] = 0

        return len(full_rows) + len(full_cols)

    def _score_clears(self, cleared: int) -> None:
        """Нараховує очки за очищення ліній з покращеною системою комбо."""
        if cleared <= 0:
            return

        base_points = 10 * cleared
        bonus = base_points * (self.combo + 1)
        
        if cleared > 2:
            bonus *= (cleared - 1)
        
        all_clear = all(self.grid[r][c] == 0 for r in range(self.size) for c in range(self.size))
        if all_clear:
            bonus += 300
        
        self.score += bonus
        self.combo += cleared
        self.combo_streak = True

    def place(self, slot_index: int, gx: int, gy: int) -> bool:
        """Ставить фігуру зі слота у (gx, gy). Повертає True якщо хід успішний."""
        if not (0 <= slot_index < 3):
            return False

        piece = self.hand[slot_index]
        if piece is None:
            return False

        if not self.can_place(piece, gx, gy):
            return False

        score_before = self.score

        for dx, dy in piece.cells:
            self.grid[gy + dy][gx + dx] = 1

        self.score += len(piece.cells)

        cleared = self.clear_lines()
        self.last_lines_cleared = cleared

        self._score_clears(cleared)

        self.last_action_score = self.score - score_before

        self.hand_clears += cleared

        self.hand[slot_index] = None

        if all(p is None for p in self.hand):

            if self.hand_clears == 0:
                self.combo = 0
                self.prev_hand_had_clear = False
            else:
                if self.combo == 0:
                    if self.prev_hand_had_clear or self.hand_clears >= 2:
                        self.combo = 1

                if self.combo > 0:
                    self.combo += self.hand_clears

                self.prev_hand_had_clear = True

            self.hand_clears = 0

            self.deal_hand_full(ensure_playable=True)

        return True