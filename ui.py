import os
import json
import pygame
from dataclasses import dataclass
from typing import List, Tuple, Optional

from config import (
    BOARD_SIZE, CELL, CELL_HAND, GAP_BOARD, GAP_HAND,
    PADDING, TOP_BAR, HAND_HEIGHT, EXTRA_W, EXTRA_H,
    BG, GRID_BG, LINE, BLOCK, GHOST_OK, GHOST_BAD, TEXT, SUBTEXT
)
from pieces import Piece
from game import Game
from state_io import write_state_json


BOARD_W = BOARD_SIZE * CELL
BOARD_H = BOARD_SIZE * CELL

WIN_W = PADDING * 2 + BOARD_W + EXTRA_W
WIN_H = TOP_BAR + PADDING + BOARD_H + 20 + HAND_HEIGHT + EXTRA_H

BOARD_X = (WIN_W - BOARD_W) // 2
BOARD_Y = TOP_BAR
HAND_Y = BOARD_Y + BOARD_H + 20

HAND_X = PADDING
HAND_W = WIN_W - 2 * PADDING

STATE_PATH = "state.json"
ACTION_PATH = "action.json"
RESTART_PATH = "restart.json"


def cell_rect(gx: int, gy: int) -> pygame.Rect:
    """Повертає прямокутник клітинки поля (gx, gy) у пікселях."""
    return pygame.Rect(
        BOARD_X + gx * CELL,
        BOARD_Y + gy * CELL,
        CELL - GAP_BOARD,
        CELL - GAP_BOARD
    )


def piece_pixel_size(piece: Piece, cell: int) -> Tuple[int, int]:
    """Обчислює розмір фігури у пікселях для заданого розміру клітинки."""
    return piece.w * cell, piece.h * cell


def draw_piece(surface: pygame.Surface, piece: Piece, px: int, py: int, color, cell: int, gap: int, radius: int):
    """Малює фігуру на поверхні, використовуючи задані параметри відступу та округлення."""
    for dx, dy in piece.cells:
        r = pygame.Rect(px + dx * cell, py + dy * cell, cell - gap, cell - gap)
        pygame.draw.rect(surface, color, r, border_radius=radius)


def draw_ghost(surface: pygame.Surface, piece: Piece, gx: int, gy: int, ok: bool):
    """Малює напівпрозорий 'прев'ю' фігури на полі (зелений/червоний)."""
    col = GHOST_OK if ok else GHOST_BAD
    ghost = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    for dx, dy in piece.cells:
        x, y = gx + dx, gy + dy
        if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
            r = cell_rect(x, y)
            pygame.draw.rect(ghost, (*col, 90), r, border_radius=8)
    surface.blit(ghost, (0, 0))


def snap_top_left_to_grid(px: int, py: int) -> Optional[Tuple[int, int]]:
    """Перетворює верхній-лівий кут фігури в координати клітинки поля (прив'язка до сітки)."""
    relx = px - BOARD_X
    rely = py - BOARD_Y
    gx = int((relx + CELL / 2) // CELL)
    gy = int((rely + CELL / 2) // CELL)
    if 0 <= gx < BOARD_SIZE and 0 <= gy < BOARD_SIZE:
        return gx, gy
    return None


@dataclass
class Draggable:
    """Об'єкт фігури в руці, який можна перетягувати мишкою."""
    piece: Piece
    slot_index: int
    home_pos: Tuple[int, int]
    pos: Tuple[int, int]
    cell: int = CELL_HAND
    dragging: bool = False
    grab_offset: Tuple[int, int] = (0, 0)

    def reset(self):
        """Повертає фігуру назад у позицію руки та скидає стан перетягування."""
        self.pos = self.home_pos
        self.cell = CELL_HAND
        self.dragging = False
        self.grab_offset = (0, 0)


def hand_slot_xs() -> List[int]:
    """Повертає X-координати трьох слотів руки (ліво/центр/право) у пікселях."""
    slot_w = 180
    margin = 24

    hand_left = HAND_X
    hand_right = HAND_X + HAND_W
    hand_center = HAND_X + HAND_W // 2

    return [
        hand_left + margin,
        hand_center - slot_w // 2,
        hand_right - slot_w - margin,
    ]


def build_hand_draggables(hand_slots: List[Optional[Piece]]) -> List[Draggable]:
    """Створює список Draggable для всіх непорожніх слотів руки."""
    drags: List[Draggable] = []

    slot_w, slot_h = 180, 180
    slot_y = HAND_Y + 24
    xs = hand_slot_xs()

    for slot_i in range(3):
        p = hand_slots[slot_i]
        if p is None:
            continue

        w, h = piece_pixel_size(p, CELL_HAND)
        sx = xs[slot_i]
        px = sx + (slot_w - w) // 2
        py = slot_y + (slot_h - h) // 2

        drags.append(
            Draggable(
                piece=p,
                slot_index=slot_i,
                home_pos=(px, py),
                pos=(px, py),
            )
        )

    return drags


def try_read_action(path: str) -> Optional[dict]:
    """Безпечно читає action.json (якщо є), повертає dict або None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    except OSError:
        return None


def try_delete_file(path: str) -> None:
    """Безпечно видаляє файл, якщо він існує."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def run():
    """Запускає UI (pygame) та цикл гри з підтримкою ручного керування і ходу з action.json."""
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Block Blast (pygame)")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Segoe UI", 22)
    font2 = pygame.font.SysFont("Segoe UI", 18)

    game = Game(size=BOARD_SIZE)
    draggables = build_hand_draggables(game.hand)

    active: Optional[Draggable] = None
    ghost_cell: Optional[Tuple[int, int]] = None
    ghost_ok = False
    game_over = False

    last_move_id = -1

    write_state_json(STATE_PATH, game, game_over)

    def sync_hand():
        """Оновлює список Draggable відповідно до поточної руки гри."""
        nonlocal draggables
        draggables = build_hand_draggables(game.hand)

    def apply_ai_action_if_any():
        """Читає action.json і, якщо хід валідний, виконує його та оновлює state.json."""
        nonlocal game_over, ghost_cell, ghost_ok, active, last_move_id

        if active and active.dragging:
            return

        if game_over:
            if os.path.exists(ACTION_PATH):
                try_delete_file(ACTION_PATH)
            return

        action = try_read_action(ACTION_PATH)
        if not action:
            return

        move_id = action.get("move_id", None)
        slot = action.get("slot", None)
        gx = action.get("gx", None)
        gy = action.get("gy", None)

        if move_id is None:
            move_id = last_move_id + 1

        try:
            move_id_int = int(move_id)
        except (TypeError, ValueError):
            try_delete_file(ACTION_PATH)
            return

        if move_id_int <= last_move_id:
            try_delete_file(ACTION_PATH)
            return

        try:
            slot = int(slot)
            gx = int(gx)
            gy = int(gy)
        except (TypeError, ValueError):
            try_delete_file(ACTION_PATH)
            return

        if not (0 <= slot < 3 and 0 <= gx < BOARD_SIZE and 0 <= gy < BOARD_SIZE):
            try_delete_file(ACTION_PATH)
            last_move_id = move_id_int
            return

        piece = game.hand[slot]
        if piece is None:
            try_delete_file(ACTION_PATH)
            last_move_id = move_id_int
            return

        if not game.can_place(piece, gx, gy):
            try_delete_file(ACTION_PATH)
            last_move_id = move_id_int
            return

        ok = game.place(slot, gx, gy)
        try_delete_file(ACTION_PATH)
        last_move_id = move_id_int

        if ok:
            sync_hand()
            active = None
            ghost_cell = None
            ghost_ok = False

            if not game.any_move_available():
                game_over = True

            write_state_json(STATE_PATH, game, game_over)

    def check_restart():
        """Перевіряє чи потрібен автоматичний рестарт від AI."""
        nonlocal game, draggables, active, ghost_cell, ghost_ok, game_over, last_move_id
        
        if not os.path.exists(RESTART_PATH):
            return
        
        try:
            with open(RESTART_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            try_delete_file(RESTART_PATH)
            
            if data.get("restart", False):
                game = Game(size=BOARD_SIZE)
                sync_hand()
                active = None
                ghost_cell = None
                ghost_ok = False
                game_over = False
                last_move_id = -1
                try_delete_file(ACTION_PATH)
                write_state_json(STATE_PATH, game, game_over)
                print("🔄 Гру перезапущено автоматично")
        except Exception as e:
            print(f"⚠️ Помилка читання restart.json: {e}")
            try_delete_file(RESTART_PATH)

    while True:
        clock.tick(60)

        apply_ai_action_if_any()
        check_restart()

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                return

            if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                game = Game(size=BOARD_SIZE)
                sync_hand()
                active = None
                ghost_cell = None
                ghost_ok = False
                game_over = False
                last_move_id = -1
                try_delete_file(ACTION_PATH)
                write_state_json(STATE_PATH, game, game_over)

            if game_over:
                continue

            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                mx, my = e.pos
                for d in reversed(draggables):
                    pw, ph = piece_pixel_size(d.piece, d.cell)
                    rect = pygame.Rect(d.pos[0], d.pos[1], pw, ph)
                    if rect.collidepoint(mx, my):
                        active = d
                        d.dragging = True
                        old_cell = d.cell
                        d.cell = CELL
                        d.grab_offset = (
                            int((mx - d.pos[0]) * (d.cell / old_cell)),
                            int((my - d.pos[1]) * (d.cell / old_cell)),
                        )
                        break

            if e.type == pygame.MOUSEMOTION:
                mx, my = e.pos
                if active and active.dragging:
                    ox, oy = active.grab_offset
                    active.pos = (mx - ox, my - oy)

                ghost_cell = None
                ghost_ok = False
                if active and active.dragging:
                    snapped = snap_top_left_to_grid(active.pos[0], active.pos[1])
                    if snapped:
                        gx, gy = snapped
                        ghost_cell = (gx, gy)
                        ghost_ok = game.can_place(active.piece, gx, gy)

            if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                if active and active.dragging:
                    snapped = snap_top_left_to_grid(active.pos[0], active.pos[1])

                    if snapped:
                        gx, gy = snapped
                        slot = active.slot_index

                        if game.place(slot, gx, gy):
                            sync_hand()
                            active = None
                            ghost_cell = None
                            ghost_ok = False

                            if not game.any_move_available():
                                game_over = True

                            write_state_json(STATE_PATH, game, game_over)
                        else:
                            active.reset()
                            active = None
                            ghost_cell = None
                            ghost_ok = False
                    else:
                        active.reset()
                        active = None
                        ghost_cell = None
                        ghost_ok = False

        screen.fill(BG)

        title = font.render(f"Score: {game.score}", True, TEXT)
        screen.blit(title, (BOARD_X, 14))
        hint = font2.render(f"Combo:{game.combo}", True, TEXT)
        screen.blit(hint, (BOARD_X + 310, 18))

        board_rect = pygame.Rect(BOARD_X, BOARD_Y, BOARD_W, BOARD_H)
        pygame.draw.rect(screen, GRID_BG, board_rect, border_radius=14)

        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                r = cell_rect(x, y)
                pygame.draw.rect(screen, LINE, r, width=1, border_radius=8)
                if game.grid[y][x]:
                    pygame.draw.rect(screen, BLOCK, r, border_radius=8)

        if not game_over and active and active.dragging and ghost_cell:
            draw_ghost(screen, active.piece, ghost_cell[0], ghost_cell[1], ghost_ok)

        for d in draggables:
            if d is active:
                continue
            draw_piece(screen, d.piece, d.pos[0], d.pos[1], BLOCK, d.cell, gap=GAP_HAND, radius=6)

        if active:
            draw_piece(screen, active.piece, active.pos[0], active.pos[1], BLOCK, active.cell, gap=GAP_BOARD, radius=8)

        if game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (0, 0, 0, 160), pygame.Rect(0, 0, WIN_W, WIN_H))
            screen.blit(overlay, (0, 0))
            msg1 = font.render("GAME OVER", True, TEXT)
            msg2 = font2.render("No moves available. Press R to restart.", True, TEXT)
            msg3 = font2.render(f"Final score: {game.score}", True, TEXT)
            screen.blit(msg1, (WIN_W // 2 - msg1.get_width() // 2, WIN_H // 2 - 60))
            screen.blit(msg3, (WIN_W // 2 - msg3.get_width() // 2, WIN_H // 2 - 20))
            screen.blit(msg2, (WIN_W // 2 - msg2.get_width() // 2, WIN_H // 2 + 10))

        pygame.display.flip()