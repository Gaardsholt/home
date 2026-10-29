"""Patch AI - Cheerful animated denim robot companion for GitHub Universe 2026."""

import gc
import math
import os
import random
import sys

APP_DIRS = (
    "/remote/apps/patch_ai",
    "/system/apps/patch_ai",
    "/apps/patch_ai",
    "/patch_ai",
)
APP_DIR = next((path for path in APP_DIRS if is_dir(path)), None)
if APP_DIR:
    try:
        os.chdir(APP_DIR)
    except OSError:
        pass
    sys.path.insert(0, APP_DIR)

SCALE = 0.236439
BODY_W = 200
BODY_H = 170
ARM_CELL_W = 66
ARM_CELL_H = 92
ARM_FRAME_COUNT = 6
REST_FRAME_INDEX = 6
ARM_REL_X = -24
ARM_REL_Y = -8
BLINK_X = 55
BLINK_Y = 38
POWER_X = 100
POWER_Y = 105

# Badge hardware & display setup
badge.mode(HIRES | VSYNC)
screen.font = font.nope

# Load character assets once at startup
body_img = image.load("assets/body.png")
arm_sheet = image.load("assets/arm_sheet.png").spritesheet(7, 1)
blink_img = image.load("assets/blink.png")

gc.collect()

# Color palette matching GitHub dark theme & denim tones
COLOR_BG = color.rgb(13, 17, 23)
COLOR_HEADER_BG = color.rgb(22, 27, 34)
COLOR_TEXT_PRIMARY = color.rgb(240, 246, 252)
COLOR_TEXT_MUTED = color.rgb(139, 148, 158)
COLOR_ACCENT = color.rgb(88, 166, 255)
COLOR_CYAN = color.rgb(56, 189, 248)
COLOR_BORDER = color.rgb(48, 54, 61)
COLOR_BUBBLE_BG = color.rgb(30, 41, 59)
COLOR_BUBBLE_TEXT = color.rgb(226, 232, 240)

# Layout constants for 320x240 screen
SCREEN_W = screen.width
SCREEN_H = screen.height
BASE_X = (SCREEN_W - BODY_W) // 2
BASE_Y = 36

# Cheerful dialogues
GREETINGS = [
    "Hello, Universe!",
    "All systems stitched!",
    "Bestseller Tech AI active!",
    "Ready to build cool things!",
    "Waving at awesome humans!",
    "Patch AI reporting for fun!",
    "Feeling 100% denim fresh!",
]

MODES = ["Waving", "Dancing", "Standby"]
mode_idx = 0

# Animation & state variables using badge.ticks
speech_text = GREETINGS[0]
speech_until = badge.ticks + 5000
super_wave_until = 0

next_blink = badge.ticks + 2500
blink_until = 0


def center_text(text, y, clr):
    screen.pen = clr
    tw, _ = screen.measure_text(text)
    screen.text(text, (SCREEN_W - tw) // 2, y)


def draw_speech_bubble(text, y):
    screen.font = font.nope
    tw, th = screen.measure_text(text)
    pad_x = 10
    pad_y = 5
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    bx = (SCREEN_W - bw) // 2

    # Bubble background & border
    screen.pen = COLOR_BORDER
    screen.shape(shape.rounded_rectangle(bx - 1, y - 1, bw + 2, bh + 2, 5))
    screen.pen = COLOR_BUBBLE_BG
    screen.shape(shape.rounded_rectangle(bx, y, bw, bh, 4))

    # Little speech pointer triangle
    pointer_cx = SCREEN_W // 2
    screen.pen = COLOR_BUBBLE_BG
    screen.shape(
        shape.custom(
            [
                vec2(pointer_cx - 4, y + bh),
                vec2(pointer_cx + 4, y + bh),
                vec2(pointer_cx, y + bh + 4),
            ]
        )
    )

    # Text
    screen.pen = COLOR_BUBBLE_TEXT
    screen.text(text, bx + pad_x, y + pad_y)


def update():
    global \
        mode_idx, \
        speech_text, \
        speech_until, \
        super_wave_until, \
        next_blink, \
        blink_until

    now = badge.ticks
    mode = MODES[mode_idx]

    # --- Input handling ---
    if badge.pressed(BUTTON_BACK):
        return True

    if badge.pressed(BUTTON_SELECT):
        super_wave_until = now + 3000
        speech_text = random.choice(GREETINGS)
        speech_until = now + 4500

    if badge.pressed(BUTTON_LEFT):
        mode_idx = (mode_idx - 1) % len(MODES)
        speech_text = "Mode: " + MODES[mode_idx]
        speech_until = now + 2500

    if badge.pressed(BUTTON_RIGHT):
        mode_idx = (mode_idx + 1) % len(MODES)
        speech_text = "Mode: " + MODES[mode_idx]
        speech_until = now + 2500

    # --- Clear Screen ---
    screen.pen = COLOR_BG
    screen.clear()

    # --- Header Bar ---
    screen.pen = COLOR_HEADER_BG
    screen.shape(shape.rectangle(0, 0, SCREEN_W, 20))
    screen.pen = COLOR_BORDER
    screen.shape(shape.line(0, 20, SCREEN_W, 20, 1))

    screen.font = font.nope
    screen.pen = COLOR_CYAN
    screen.text("BESTSELLER TECH", 10, 4)

    screen.pen = COLOR_TEXT_MUTED
    mode_label = "MODE: " + mode.upper()
    mlw, _ = screen.measure_text(mode_label)
    screen.text(mode_label, SCREEN_W - mlw - 10, 4)

    # --- Animation calculations ---
    t = badge.ticks

    if mode == "Standby":
        bob_y = math.sin(t / 800) * 1.5
        arm_frame = REST_FRAME_INDEX
    elif mode == "Dancing":
        bob_y = math.sin(t / 180) * 5
        arm_frame = int((t / 75) % ARM_FRAME_COUNT)
    else:  # Waving
        bob_y = math.sin(t / 350) * 3
        is_super = now < super_wave_until
        frame_interval = 60 if is_super else 110
        arm_frame = int((t / frame_interval) % ARM_FRAME_COUNT)

    char_x = BASE_X
    char_y = int(BASE_Y + bob_y)

    # --- 1. Draw Body Sprite ---
    screen.blit(body_img, vec2(char_x, char_y))

    # --- 2. Draw Waving Arm IN FRONT of body ---
    arm_sprite = arm_sheet.sprite(arm_frame, 0)
    screen.blit(arm_sprite, vec2(char_x + ARM_REL_X, char_y + ARM_REL_Y))

    # --- 3. Stitched Button-Eye Blinking ---
    if now >= next_blink:
        blink_until = now + 160
        next_blink = now + random.randint(2800, 5200)

    if now < blink_until or mode == "Standby":
        screen.blit(blink_img, vec2(char_x + BLINK_X, char_y + BLINK_Y))

    # --- 4. Power Button LED Glow ---
    pwr_x = char_x + POWER_X
    pwr_y = char_y + POWER_Y
    glow_pulse = (math.sin(t / 300) + 1.0) * 0.5  # 0.0 to 1.0
    glow_radius = 8 + glow_pulse * 4
    glow_alpha = int(60 + glow_pulse * 120)
    screen.pen = color.rgb(56, 189, 248, glow_alpha)
    screen.shape(shape.circle(pwr_x, pwr_y, glow_radius))

    # Center power icon bright pip
    screen.pen = color.rgb(224, 242, 254)
    screen.shape(shape.circle(pwr_x, pwr_y, 3))

    # --- Speech Bubble / Cheerful Message ---
    if now < speech_until:
        draw_speech_bubble(speech_text, 23)

    # --- Footer Controls Bar ---
    screen.pen = COLOR_HEADER_BG
    screen.shape(shape.rectangle(0, SCREEN_H - 18, SCREEN_W, 18))
    screen.pen = COLOR_BORDER
    screen.shape(shape.line(0, SCREEN_H - 18, SCREEN_W, SCREEN_H - 18, 1))

    footer_hint = "< > Mood   Select: Super Wave   Back: Menu"
    center_text(footer_hint, SCREEN_H - 14, COLOR_TEXT_MUTED)


run(update)
