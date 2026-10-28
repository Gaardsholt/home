import os
import sys
import math

APP_DIRS = (
    "/system/apps/mona_teleporter",
    "/apps/mona_teleporter",
    "/mona_teleporter",
    ".",
)

APP_DIR = "."
for path in APP_DIRS:
    if is_dir(path):
        APP_DIR = path
        break

try:
    os.chdir(APP_DIR)
except OSError:
    pass

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Set up screen mode
try:
    badge.mode(HIRES | VSYNC)
except Exception:
    pass

try:
    screen.antialias = image.X2
except Exception:
    pass

# Hardware Constants
BEACON_ADDRESS = 0x45
RESET_CODE = 0xF0
IR_TX_PIN = 16

# Case LEDs
CASE_LED_PINS = (0, 1, 2, 3)
case_leds = []
try:
    import machine
    for pin_id in CASE_LED_PINS:
        try:
            case_leds.append(machine.Pin(pin_id, machine.Pin.OUT))
        except Exception:
            pass
except Exception:
    pass

def set_case_leds(state):
    for led in case_leds:
        try:
            led.value(1 if state else 0)
        except Exception:
            pass

# Catalog of locations matching official Mona's Expedition
# (Display Name, Code, Icon filename, Accent RGB, Description)
CATALOG = (
    ("Mo's Diner", 0x11, "diner", (139, 210, 231), "Station 1 - Diner Award"),
    ("Under the Hood", 0x22, "frying-pan", (240, 160, 80), "Station 2 - Pan Award"),
    ("Creator Cabana", 0x33, "cabana", (100, 220, 160), "Station 3 - Cabana Award"),
    ("Open Source Records", 0x44, "vinyl", (180, 140, 230), "Station 4 - Vinyl Award"),
    ("Makerspace", 0x55, "keycap", (255, 204, 100), "Station 5 - Keycap Award"),
    ("Hack Your Badge", 0x66, "ascii-mona", (255, 204, 255), "Station 6 - Mona Award"),
    ("Demos & Donuts", 0x77, "ascii-donut", (255, 150, 180), "Station 7 - Donut Award"),
    ("Level Up Lounge", 0x88, "up-arrow", (110, 210, 255), "Station 8 - Arrow Award"),
    ("CAB Member", 0x99, "cab", (140, 184, 56), "Station 9 - CAB Award"),
    ("TOUR: UNLOCK ALL", 0x00, "compass", (255, 215, 0), "Rapid burst of all 9 codes"),
    ("EXPEDITION RESET", 0xF0, "compass-needle", (255, 70, 70), "Wipes target achievements"),
)

ALL_EXPEDITION_CODES = (0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99)

# Preload award images
images = {}
for item in CATALOG:
    slug = item[2]
    if slug not in images:
        img_path = f"assets/{slug}.png"
        try:
            images[slug] = image.load(img_path)
        except Exception:
            try:
                images[slug] = image.load(f"/system/apps/menu/awards/{slug}.png")
            except Exception:
                images[slug] = None

# ---------------------------------------------------------------------------
# IR Transmitter (aye_arr / PIO NEC sender)
# ---------------------------------------------------------------------------
class HardwareIR:
    def __init__(self):
        self.sender = None
        self.ready = False
        self._init_sender()

    def _init_sender(self):
        # 1. Try standard aye_arr.nec.NECSender
        try:
            from aye_arr.nec import NECSender
            self.sender = NECSender(IR_TX_PIN, 0, 1)
            try:
                self.sender.start()
            except Exception:
                pass
            self.ready = True
            return
        except Exception:
            pass

        # 2. Try PIO-based custom sender if aye_arr is unavailable
        try:
            import rp2
            from machine import Pin

            @rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, autopull=True, pull_thresh=32, fifo_join=rp2.PIO.JOIN_TX)
            def pio_nec_pulses():
                out(y, 16).delay(1)
                label("high_check")
                nop().side(1)
                jmp(y_dec, "high_check").side(0)
                out(x, 16).side(1)
                nop().side(0)
                label("low_check")
                nop()
                jmp(x_dec, "low_check")

            class PIOPulseSender:
                def __init__(self, pin_num, pio=0, sm=1):
                    carrier_freq = 38000
                    clocks_per_cycle = 2
                    self.freq = carrier_freq * clocks_per_cycle
                    self.sm = rp2.StateMachine(sm + (pio * 4), pio_nec_pulses, freq=self.freq, sideset_base=Pin(pin_num))
                    self.sm.active(1)

                def send_pair(self, high_us, low_us):
                    h_cycles = int((high_us * 38000) / 1000000)
                    l_cycles = int((low_us * 38000) / 1000000)
                    self.sm.put((l_cycles << 16) | (h_cycles & 0xFFFF))

                def send_code(self, code):
                    # 9ms burst, 4.5ms space
                    self.send_pair(9000, 4500)
                    for bit in range(32):
                        if code & (1 << bit):
                            self.send_pair(560, 1680)
                        else:
                            self.send_pair(560, 560)
                    # End burst: 560us burst, 9.5ms space
                    self.send_pair(560, 9500)

                def send_addr_cmd(self, addr, cmd):
                    code = addr | ((addr ^ 0xFF) << 8)
                    code |= (cmd | ((cmd ^ 0xFF) << 8)) << 16
                    self.send_code(code)

            self.sender = PIOPulseSender(IR_TX_PIN, 0, 1)
            self.ready = True
        except Exception:
            self.sender = None
            self.ready = False

    def send_addr_cmd(self, addr, cmd):
        if self.sender is not None:
            try:
                self.sender.send_addr_cmd(addr, cmd)
            except Exception:
                pass

ir_device = HardwareIR()

# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.selected = 0
        self.auto_broadcast = True
        self.last_burst_tick = 0
        self.pulse_active_until = 0
        self.broadcast_interval = 1000  # ms
        self.tour_active = False
        self.tour_step = 0
        self.tour_next_tick = 0
        self.burst_flash = 0.0

    def trigger_transmit(self, is_manual=False):
        now = badge.ticks
        item = CATALOG[self.selected]
        code = item[1]

        self.last_burst_tick = now
        self.pulse_active_until = now + 240
        self.burst_flash = 1.0

        if code == 0x00:
            # Tour Guide mode: Start multi-step sequence
            self.tour_active = True
            self.tour_step = 0
            self.tour_next_tick = now
        else:
            # Send single location or reset code
            # 3 repetitions for reliability
            for _ in range(3):
                ir_device.send_addr_cmd(BEACON_ADDRESS, code)

state = AppState()

# ---------------------------------------------------------------------------
# UI Drawing
# ---------------------------------------------------------------------------
# Color palette
bg_dark = color.rgb(13, 16, 24)
card_bg = color.rgb(23, 28, 42)
card_border = color.rgb(45, 54, 78)
accent_cyan = color.rgb(64, 210, 255)
accent_green = color.rgb(95, 237, 131)
accent_gold = color.rgb(255, 215, 0)
accent_red = color.rgb(255, 75, 75)
text_dim = color.rgb(140, 150, 175)
text_bright = color.rgb(245, 248, 255)

def draw():
    now = badge.ticks
    w = screen.width
    h = screen.height

    # Handle tour progress if active
    if state.tour_active:
        if now >= state.tour_next_tick:
            if state.tour_step < len(ALL_EXPEDITION_CODES):
                code = ALL_EXPEDITION_CODES[state.tour_step]
                for _ in range(2):
                    ir_device.send_addr_cmd(BEACON_ADDRESS, code)
                state.tour_step += 1
                state.tour_next_tick = now + 70
                state.burst_flash = 1.0
                state.pulse_active_until = now + 120
            else:
                state.tour_active = False

    # Auto broadcast check
    if state.auto_broadcast and not state.tour_active:
        if now - state.last_burst_tick >= state.broadcast_interval:
            state.trigger_transmit(is_manual=False)

    is_pulsing = now < state.pulse_active_until or state.tour_active

    # Update case LEDs with pulsing
    set_case_leds(is_pulsing)

    # Decay burst flash animation
    if state.burst_flash > 0:
        state.burst_flash = max(0.0, state.burst_flash - 0.05)

    # 1. Background
    screen.pen = bg_dark
    screen.clear()

    # 2. Header Bar
    screen.pen = color.rgb(20, 26, 38)
    screen.shape(shape.rectangle(rect(0, 0, w, 24)))
    screen.pen = color.rgb(40, 52, 75)
    screen.shape(shape.line(vec2(0, 24), vec2(w, 24), 1))

    # Title
    screen.pen = accent_cyan
    screen.font = font.ark
    screen.text("MONA TELEPORTER", 10, 6)

    # Auto-broadcast pill
    pill_text = "AUTO: ON" if state.auto_broadcast else "AUTO: OFF"
    pill_col = accent_green if state.auto_broadcast else text_dim
    screen.pen = pill_col
    tw, _ = screen.measure_text(pill_text)
    screen.text(pill_text, w - tw - 12, 6)

    # 3. Main Center Card
    card_x = 16
    card_y = 32
    card_w = w - 32
    card_h = 154

    item = CATALOG[state.selected]
    name = item[0]
    code = item[1]
    slug = item[2]
    rgb = item[3]
    desc = item[4]

    loc_col = color.rgb(*rgb)

    # Card background
    screen.pen = card_bg
    screen.shape(shape.rounded_rectangle(rect(card_x, card_y, card_w, card_h), 8))

    # Border (glows brighter when pulsing)
    border_col = loc_col if is_pulsing else card_border
    screen.pen = border_col
    screen.shape(shape.rounded_rectangle(rect(card_x, card_y, card_w, card_h), 8).stroke(2))

    # Index indicator: e.g. "Location 1 of 9" or "Special Mode"
    if code in ALL_EXPEDITION_CODES:
        idx_str = f"LOCATION {state.selected + 1} OF 9"
    elif code == 0x00:
        idx_str = "SPECIAL: ALL-IN-ONE UNLOCK"
    else:
        idx_str = "SPECIAL: FACTORY RESET"

    screen.font = font.ark
    screen.pen = text_dim
    screen.text(idx_str, card_x + 14, card_y + 12)

    # Hex Code pill on right of card
    if code == 0x00:
        code_str = "CMD: 0x11..0x99"
    else:
        code_str = f"CMD: 0x{code:02X} | ADDR: 0x{BEACON_ADDRESS:02X}"
    screen.pen = text_bright
    cw, _ = screen.measure_text(code_str)
    screen.text(code_str, card_x + card_w - cw - 14, card_y + 12)

    # Center icon & radar wave animations
    cx = card_x + 58
    cy = card_y + 80

    # Animated radar rings when transmitting
    if is_pulsing or state.burst_flash > 0:
        ring_prog = (now % 800) / 800.0
        for r_offset in (0.0, 0.33, 0.66):
            r_val = ((ring_prog + r_offset) % 1.0) * 52.0
            alpha = int(255 * (1.0 - (r_val / 52.0)))
            ring_pen = color.rgb(rgb[0], rgb[1], rgb[2], alpha)
            screen.pen = ring_pen
            screen.shape(shape.circle(vec2(cx, cy), r_val).stroke(1))

    # Icon base backing circle
    screen.pen = color.rgb(16, 20, 30)
    screen.shape(shape.circle(vec2(cx, cy), 32))
    screen.pen = loc_col
    screen.shape(shape.circle(vec2(cx, cy), 32).stroke(2))

    # Draw icon image
    icon_img = images.get(slug)
    if icon_img is not None:
        screen.blit(icon_img, rect(0, 0, icon_img.width, icon_img.height), rect(cx - 24, cy - 24, 48, 48))
    else:
        # Fallback text glyph if image missing
        screen.pen = loc_col
        screen.font = font.ark
        screen.text(slug[:4].upper(), cx - 12, cy - 4)

    # Location Name (Large title)
    screen.font = font.ark
    screen.pen = text_bright
    # Split or wrap if name is long
    tx = card_x + 104
    screen.text(name, tx, card_y + 54)

    # Description / station note
    screen.pen = text_dim
    screen.text(desc, tx, card_y + 76)

    # Live Beacon Signal Status
    if state.tour_active:
        sig_str = f"BEAMING: Station {state.tour_step}/{len(ALL_EXPEDITION_CODES)}..."
        sig_col = accent_gold
    elif is_pulsing:
        sig_str = ">>> TRANSMITTING IR SIGNAL >>>"
        sig_col = accent_green
    elif state.auto_broadcast:
        time_to_next = max(0, (state.last_burst_tick + state.broadcast_interval - now) // 100)
        sig_str = f"Next pulse in 0.{time_to_next}s"
        sig_col = text_dim
    else:
        sig_str = "Ready (Press SELECT to burst)"
        sig_col = text_dim

    screen.pen = sig_col
    screen.text(sig_str, tx, card_y + 104)

    # Left & Right Arrow hints
    screen.pen = text_bright
    screen.text("<", card_x + 6, card_y + card_h // 2 - 4)
    screen.text(">", card_x + card_w - 14, card_y + card_h // 2 - 4)

    # 4. Instructions & Footer Controls
    screen.pen = color.rgb(20, 26, 38)
    screen.shape(shape.rectangle(rect(0, h - 42, w, 42)))
    screen.pen = color.rgb(40, 52, 75)
    screen.shape(shape.line(vec2(0, h - 42), vec2(w, h - 42), 1))

    # Instructions line 1: Tap instructions
    screen.font = font.ark
    screen.pen = accent_cyan
    guide_text = "Point top IR LEDs at another badge to unlock"
    gw, _ = screen.measure_text(guide_text)
    screen.text(guide_text, (w - gw) // 2, h - 36)

    # Instructions line 2: Button controls
    screen.pen = text_dim
    btns_text = "[< / >] Station   [SELECT] Burst   [^/v] Auto"
    bw, _ = screen.measure_text(btns_text)
    screen.text(btns_text, (w - bw) // 2, h - 18)

# ---------------------------------------------------------------------------
# Input Loop
# ---------------------------------------------------------------------------
def update():
    # Left / Right cycle through catalog
    if badge.pressed(BUTTON_LEFT):
        state.selected = (state.selected - 1) % len(CATALOG)
        state.trigger_transmit(is_manual=True)

    if badge.pressed(BUTTON_RIGHT):
        state.selected = (state.selected + 1) % len(CATALOG)
        state.trigger_transmit(is_manual=True)

    # Select triggers instant burst
    if badge.pressed(BUTTON_SELECT):
        state.trigger_transmit(is_manual=True)

    # Up / Down toggles auto-broadcast
    if badge.pressed(BUTTON_UP) or badge.pressed(BUTTON_DOWN):
        state.auto_broadcast = not state.auto_broadcast
        if state.auto_broadcast:
            state.trigger_transmit(is_manual=False)

    draw()

# Launch the app loop
run(update)
