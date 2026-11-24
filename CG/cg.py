"""
2D Car Racing Game - Python + Pygame
CG concepts used:
  * 2D transformations : manual translate / rotate / scale (matrix math) applied to car vertices
  * Bresenham's line algorithm : road edges, lane dashes, speedometer ticks and needle
  * Orthographic mapping (world 0..W x 0..H, y-up -> screen y-down), double buffering,
    fixed-rate frame loop

Controls: LEFT/RIGHT = steer, UP/DOWN = speed, P = pause, R = restart, ESC = quit
Install : pip install pygame
Run     : python car_racing_pygame.py
"""
import math
import random
import sys

import pygame

W, H = 400, 600
ROAD_X, ROAD_W, LANE_W = 50, 300, 100
CAR_W, CAR_H = 40, 70
N_ENEMY = 4
PLAYER_Y = 75

pygame.init()
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("2D Car Racing - Pygame")
clock = pygame.time.Clock()
FONT_L = pygame.font.SysFont("helvetica,arial,liberationsans,dejavusans", 18)
FONT_S = pygame.font.SysFont("helvetica,arial,liberationsans,dejavusans", 12)


def C(r, g, b):
    """Convert 0..1 float colour (as used by OpenGL) to 0..255 ints."""
    return (round(r * 255), round(g * 255), round(b * 255))


# ---------------------------------------------------------------- Bresenham
def bresenham(x0, y0, x1, y1):
    """Integer line rasterisation, works in all octants. Returns list of (x, y) pixels."""
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return pts


def draw_points(pts, color, size=1):
    """Plot pixels as size x size squares centred on the point (like GL_POINTS).
    World coordinates are y-up, so y is flipped for the screen."""
    col = C(*color)
    half = size // 2
    for x, y in pts:
        screen.fill(col, (x - half, H - y - half, size, size))


EDGE_PTS = (bresenham(ROAD_X, 0, ROAD_X, H) +
            bresenham(ROAD_X + ROAD_W, 0, ROAD_X + ROAD_W, H))   # computed once


# ---------------------------------------------------------------- drawing helpers
def rect(x, y, w, h, color):
    """Axis-aligned filled rectangle with its lower-left corner at (x, y), y-up."""
    pygame.draw.rect(screen, C(*color), (x, H - y - h, w, h))


def alpha_rect(x, y, w, h, color, alpha):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((*C(*color), round(alpha * 255)))
    screen.blit(surf, (x, H - y - h))


def draw_car(x, y, angle, scale, color):
    """Car is modelled around the origin, then moved with scale -> rotate -> translate."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)

    def tf(px, py):
        px *= scale                                   # uniform 2D scale
        py *= scale
        rx = px * c - py * s + x                      # rotate about the centre (z axis)
        ry = px * s + py * c + y                      # then translate to world position
        return (rx, H - ry)                           # world (y-up) -> screen (y-down)

    def part(col, rx, ry, w, h):
        pygame.draw.polygon(screen, C(*col),
                            [tf(rx, ry), tf(rx + w, ry), tf(rx + w, ry + h), tf(rx, ry + h)])

    hw, hh = CAR_W / 2, CAR_H / 2
    for wx in (-hw - 4, hw - 2):                                  # wheels
        for wy in (-hh + 8, hh - 24):
            part((0.1, 0.1, 0.1), wx, wy, 6, 16)
    part(color, -hw, -hh, CAR_W, CAR_H)                           # body
    part((0.6, 0.85, 1), -hw + 6, hh - 26, CAR_W - 12, 14)        # windshield
    part((0.6, 0.85, 1), -hw + 8, -hh + 8, CAR_W - 16, 8)         # rear window
    part((1, 1, 0.6), -hw + 3, hh - 6, 8, 5)                      # headlights
    part((1, 1, 0.6), hw - 11, hh - 6, 8, 5)


def text(x, y, s, color, font=FONT_L):
    """Draw text with its baseline-left corner at world (x, y)."""
    img = font.render(s, True, C(*color))
    screen.blit(img, (x, H - y - font.get_ascent()))


def draw_gauge(cx, cy, r, speed):
    size = 2 * r + 2                                           # dial background (alpha)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    fan = [(r + 1 + r * math.cos(math.radians(d)), r + 1 - r * math.sin(math.radians(d)))
           for d in range(0, 360, 10)]
    pygame.draw.polygon(surf, (0, 0, 0, round(0.6 * 255)), fan)
    screen.blit(surf, (cx - r - 1, H - cy - r - 1))

    ticks = []
    for i in range(7):                                         # scale ticks (Bresenham)
        a = math.radians(210 - 240 * i / 6)
        c, s = math.cos(a), math.sin(a)
        ticks += bresenham(int(cx + (r - 9) * c), int(cy + (r - 9) * s),
                           int(cx + (r - 2) * c), int(cy + (r - 2) * s))
    draw_points(ticks, (1, 1, 1), 2)
    t = max(0.0, min(1.0, (speed - 2) / 12))                   # needle (Bresenham)
    a = math.radians(210 - 240 * t)
    needle = bresenham(cx, cy, int(cx + (r - 10) * math.cos(a)), int(cy + (r - 10) * math.sin(a)))
    draw_points(needle, (1, 0.2, 0.2), 3)


# ---------------------------------------------------------------- game state
def lane_center(lane):
    return ROAD_X + LANE_W * lane + LANE_W // 2


def respawn(e):
    top = max([H] + [o["y"] for o in enemies if o is not e])
    e["x"] = lane_center(random.randint(0, 2))
    e["y"] = top + random.randint(170, 270)
    e["c"] = (random.uniform(.3, 1), random.uniform(0, .6), random.uniform(.3, 1))


def reset():
    global px, tilt, crash, base_speed, boost, dash, score, game_over, paused, enemies
    px, tilt, crash = lane_center(1), 0.0, 0
    base_speed, boost, dash, score = 4.0, 0, 0.0, 0
    game_over = paused = False
    enemies = [{"x": 0, "y": H, "c": (0, 0, 0)} for _ in range(N_ENEMY)]
    for e in enemies:
        respawn(e)


best = 0
left = right = False
reset()


def update():
    global px, tilt, crash, base_speed, dash, score, best, game_over
    if paused:
        return
    if not game_over:
        speed = base_speed + boost
        target = 0
        if left:
            px -= 5; target += 12       # steering left tilts the car anticlockwise
        if right:
            px += 5; target -= 12       # steering right tilts it clockwise
        tilt += (target - tilt) * 0.2   # smooth rotation
        px = max(ROAD_X + CAR_W / 2 + 4, min(ROAD_X + ROAD_W - CAR_W / 2 - 4, px))
        dash = (dash + speed) % 60
        for e in enemies:
            e["y"] -= speed * 0.8
            if e["y"] < -60:
                respawn(e)
                score += 1
                base_speed = min(10, base_speed + 0.15)
            if abs(px - e["x"]) < CAR_W - 4 and abs(PLAYER_Y - e["y"]) < CAR_H - 6:
                game_over = True
                best = max(best, score)
    else:
        crash += 1                      # crash animation: spin and shrink


def display():
    screen.fill(C(0.15, 0.6, 0.2))                                # grass
    rect(ROAD_X, 0, ROAD_W, H, (0.25, 0.25, 0.28))                # road
    draw_points(EDGE_PTS, (1, 1, 1), 4)                           # road edges (Bresenham)

    dashes = []                                                   # lane dashes (Bresenham)
    for lane in (1, 2):
        x = ROAD_X + lane * LANE_W
        y = -dash
        while y < H:
            dashes += bresenham(x, int(y), x, int(y) + 30)
            y += 60
    draw_points(dashes, (1, 1, 1), 4)

    for e in enemies:
        draw_car(e["x"], e["y"], 0, 1.0, e["c"])
    if game_over:
        draw_car(px, PLAYER_Y, tilt + crash * 18, max(0.6, 1 - crash * 0.01), (0.9, 0.1, 0.1))
    else:
        draw_car(px, PLAYER_Y, tilt, 1.0, (0.9, 0.1, 0.1))

    white = (1, 1, 1)
    text(8, H - 25, f"Score: {score}", white)
    text(8, H - 50, f"Best: {best}", white)
    draw_gauge(W - 50, H - 50, 40, base_speed + boost)

    if paused:
        text(W // 2 - 30, H // 2, "PAUSED", (1, 0.2, 0.2))       # same tint as the original
    if game_over:
        alpha_rect(60, H // 2 - 50, 280, 110, (0, 0, 0), 0.7)
        text(W // 2 - 50, H // 2 + 30, "GAME OVER", (1, 0.2, 0.2))
        text(W // 2 - 60, H // 2, f"Final score: {score}", white)
        text(W // 2 - 70, H // 2 - 30, "Press R to restart", white, FONT_S)
    pygame.display.flip()                                         # double-buffer swap


def key_down(key):
    global paused, left, right, boost
    if key == pygame.K_ESCAPE:
        pygame.quit()
        sys.exit(0)
    if key == pygame.K_r:
        reset()
    if key == pygame.K_p:
        paused = not paused
    if key == pygame.K_LEFT:
        left = True
    elif key == pygame.K_RIGHT:
        right = True
    elif key == pygame.K_UP and boost < 4:
        boost += 1
    elif key == pygame.K_DOWN and boost > -2:
        boost -= 1


def key_up(key):
    global left, right
    if key == pygame.K_LEFT:
        left = False
    elif key == pygame.K_RIGHT:
        right = False


def main():
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                key_down(event.key)
            elif event.type == pygame.KEYUP:
                key_up(event.key)
        update()
        display()
        clock.tick(60)                  # ~16 ms per frame, same as the original timer


if __name__ == "__main__":
    main()