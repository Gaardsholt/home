"""Beam: Peer-to-peer app sharing for GitHub Universe 2026 badges."""

import json
import os
import struct
import sys
import time

try:
    from badgeware import link as badgelink
except ImportError:
    badgelink = None

try:
    from badgeware import State
except ImportError:
    State = None

APP_DIRS = ("/remote/apps/beam", "/system/apps/beam", "/apps/beam", "/beam")
try:
    APP_DIR = next(p for p in APP_DIRS if is_dir(p))
except (NameError, StopIteration):
    APP_DIR = "/system/apps/beam"

try:
    os.chdir(APP_DIR)
except OSError:
    pass

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

try:
    badge.mode(HIRES | VSYNC)
except NameError:
    pass

try:
    screen.antialias = image.X2
except NameError:
    pass

WIDTH = 320
HEIGHT = 240
GAME = "beam"

# Excluded system apps that cannot or should not be shared
EXCLUDED_APPS = {"menu", "startup", "beam", "mass_storage"}
MAX_BEAM_SIZE = 250 * 1024  # Max size per app to safely fit in / (LittleFS)
CHUNK_PAYLOAD_SIZE = 96

# Colors
black = color.rgb(13, 17, 23)
card_bg = color.rgb(22, 27, 34)
card_border = color.rgb(48, 54, 61)
card_selected = color.rgb(33, 41, 54)
white = color.rgb(255, 255, 255)
dim_white = color.rgb(255, 255, 255, 160)
faint_white = color.rgb(255, 255, 255, 60)
accent = color.rgb(56, 189, 248)       # Sky blue
accent_glow = color.rgb(14, 116, 144)  # Deep cyan
emerald = color.rgb(52, 211, 153)      # Success green
purple = color.rgb(129, 140, 248)      # Lavender
amber = color.rgb(251, 191, 36)        # Warning amber
rose = color.rgb(244, 63, 94)          # Error rose

try:
    title_font = getattr(font, "ignore", getattr(font, "nope", None))
    body_font = getattr(font, "sins", getattr(font, "ark", None))
except (NameError, AttributeError):
    title_font = None
    body_font = None


def format_size(bytes_count):
    if bytes_count < 1024:
        return f"{bytes_count} B"
    return f"{bytes_count // 1024} KB"


def capitalize_word(word):
    if not word:
        return ""
    if len(word) == 1:
        return word.upper()
    return word[0].upper() + word[1:]


def capitalize_slug(slug):
    parts = slug.split("_")
    return " ".join([capitalize_word(p) for p in parts if p])


def free_storage_bytes():
    try:
        stat = os.statvfs("/")
        return stat[0] * stat[3]
    except OSError:
        return 900000


def ensure_directory(path):
    parts = path.split("/")
    cur = ""
    for part in parts:
        if not part:
            continue
        cur += "/" + part
        try:
            os.mkdir(cur)
        except OSError:
            pass


def list_dir_entries(path):
    """List directory entries compatible with MicroPython os.ilistdir and CPython."""
    if hasattr(os, "ilistdir"):
        try:
            return list(os.ilistdir(path))
        except OSError:
            return []
    try:
        results = []
        for entry in os.scandir(path):
            mode = 0x4000 if entry.is_dir() else 0x8000
            results.append((entry.name, mode))
        return results
    except OSError:
        return []


def get_app_files(app_dir):
    """Recursively collect relative files and sizes for an app."""
    collected = []
    total_size = 0

    def walk_dir(current_dir, prefix=""):
        nonlocal total_size
        entries = list_dir_entries(current_dir)
        for entry in entries:
            name = entry[0]
            mode = entry[1]
            if name.startswith(".") or name == "__pycache__":
                continue
            sub_path = f"{current_dir}/{name}"
            rel_path = f"{prefix}/{name}" if prefix else name
            if mode == 0x4000:  # Directory
                walk_dir(sub_path, rel_path)
            else:
                try:
                    size = os.stat(sub_path)[6]
                except OSError:
                    size = 0
                total_size += size
                collected.append((rel_path, sub_path, size))

    walk_dir(app_dir)
    return collected, total_size


def scan_apps():
    """Discover apps from /system/apps and /apps."""
    shareable = []
    seen = set()

    roots = []
    try:
        os.stat("/system/apps")
        roots.append(("/system/apps", False))
    except OSError:
        pass

    try:
        os.stat("/apps")
        roots.append(("/apps", True))
    except OSError:
        pass

    # Fallback to local apps directory if in repo or simulator
    if not roots:
        roots.append(("badge/apps", False))

    for root_dir, is_sideloaded in roots:
        entries = list_dir_entries(root_dir)
        for entry in sorted(entries, key=lambda e: e[0]):
            slug = entry[0]
            if entry[1] != 0x4000 or slug in EXCLUDED_APPS or slug in seen:
                continue
            app_path = f"{root_dir}/{slug}"
            has_init = False
            try:
                os.stat(f"{app_path}/__init__.py")
                has_init = True
            except OSError:
                try:
                    os.stat(f"{app_path}/__init__.mpy")
                    has_init = True
                except OSError:
                    pass
            if not has_init:
                continue

            files, total_size = get_app_files(app_path)
            if not files or total_size > MAX_BEAM_SIZE:
                continue

            seen.add(slug)
            shareable.append({
                "slug": slug,
                "name": capitalize_slug(slug),
                "path": app_path,
                "size": total_size,
                "files": files,
                "is_sideloaded": is_sideloaded,
            })
    return shareable


def scan_sideloaded():
    """List apps installed in /apps."""
    sideloaded = []
    entries = list_dir_entries("/apps")
    for entry in sorted(entries, key=lambda e: e[0]):
        slug = entry[0]
        if entry[1] != 0x4000:
            continue
        app_path = f"/apps/{slug}"
        has_init = False
        try:
            os.stat(f"{app_path}/__init__.py")
            has_init = True
        except OSError:
            try:
                os.stat(f"{app_path}/__init__.mpy")
                has_init = True
            except OSError:
                pass
        if not has_init:
            continue
        files, total_size = get_app_files(app_path)
        sideloaded.append({
            "slug": slug,
            "name": capitalize_slug(slug),
            "path": app_path,
            "size": total_size,
        })
    return sideloaded


class SenderEngine:
    def __init__(self, app_info):
        self.app_info = app_info
        self.files_data = []
        for rel_path, full_path, size in app_info["files"]:
            try:
                with open(full_path, "rb") as f:
                    content = f.read()
            except OSError:
                content = b""
            self.files_data.append((rel_path, content))

        manifest = {
            "slug": app_info["slug"],
            "name": app_info["name"],
            "total_size": app_info["size"],
            "files": [{"path": r, "size": len(c)} for r, c in self.files_data],
        }
        self.manifest_raw = json.dumps(manifest).encode()
        self.manifest_chunks = [
            self.manifest_raw[i:i + CHUNK_PAYLOAD_SIZE]
            for i in range(0, len(self.manifest_raw), CHUNK_PAYLOAD_SIZE)
        ]
        self.manifest_sent = 0

        # File chunking
        self.all_file_chunks = []
        for file_idx, (rel_path, content) in enumerate(self.files_data):
            chunks = [
                content[i:i + CHUNK_PAYLOAD_SIZE]
                for i in range(0, len(content), CHUNK_PAYLOAD_SIZE)
            ]
            if not chunks:
                chunks = [b""]  # Empty file
            for chunk_idx, payload in enumerate(chunks):
                self.all_file_chunks.append((file_idx, chunk_idx, len(chunks), payload))

        self.data_sent = 0
        self.accepted = False
        self.rejected_reason = None
        self.finished = False

    def pump(self, link):
        if link is None or not link.linked:
            return

        # 1. Send Manifest
        if not self.accepted and self.rejected_reason is None:
            while self.manifest_sent < len(self.manifest_chunks):
                chunk = (
                    b"M"
                    + struct.pack(">HH", self.manifest_sent, len(self.manifest_chunks))
                    + self.manifest_chunks[self.manifest_sent]
                )
                if not link.send(chunk):
                    return
                self.manifest_sent += 1
            return

        # 2. Send File Data Chunks
        if self.accepted and not self.finished:
            while self.data_sent < len(self.all_file_chunks):
                f_idx, c_idx, total_c, payload = self.all_file_chunks[self.data_sent]
                frame = b"D" + struct.pack(">HHH", f_idx, c_idx, total_c) + payload
                if not link.send(frame):
                    return
                self.data_sent += 1

            # 3. Finish Signal
            if self.data_sent >= len(self.all_file_chunks):
                link.send(b"FDONE")

    def handle(self, message):
        tag = message[:1]
        if tag == b"A":
            status = message[1:2]
            if status == b"1":
                self.accepted = True
            else:
                self.rejected_reason = message[2:].decode() or "Peer rejected"
        elif tag == b"K":
            if message[1:] == b"DONE":
                self.finished = True

    @property
    def progress(self):
        total = len(self.all_file_chunks)
        return (self.data_sent / total) if total > 0 else 1.0


class ReceiverEngine:
    def __init__(self):
        self.manifest_parts = {}
        self.manifest_total = None
        self.manifest = None
        self.file_chunks = {}  # file_idx -> {chunk_idx: payload}
        self.file_totals = {}  # file_idx -> total_chunks
        self.installed = False
        self.error_msg = None
        self.accepted = False

    def handle(self, message, link):
        tag = message[:1]
        if tag == b"M":
            if len(message) < 5 or self.manifest is not None:
                return
            part_idx, total_parts = struct.unpack_from(">HH", message, 1)
            self.manifest_total = total_parts
            self.manifest_parts[part_idx] = message[5:]

            if len(self.manifest_parts) == self.manifest_total:
                try:
                    raw = b"".join(self.manifest_parts[i] for i in range(self.manifest_total))
                    self.manifest = json.loads(raw)
                except Exception as e:
                    self.error_msg = "Manifest parse error"
                    if link:
                        link.send(b"A0" + b"Corrupt manifest")
                    return

                # Validate space
                needed = self.manifest.get("total_size", 0) + 8192
                free = free_storage_bytes()
                if free < needed:
                    self.error_msg = f"Need {format_size(needed)}, free: {format_size(free)}"
                    if link:
                        link.send(b"A0" + self.error_msg.encode())
                    return

                self.accepted = True
                if link:
                    link.send(b"A1")

        elif tag == b"D":
            if len(message) < 7 or self.manifest is None:
                return
            file_idx, chunk_idx, total_chunks = struct.unpack_from(">HHH", message, 1)
            payload = message[7:]

            if file_idx not in self.file_chunks:
                self.file_chunks[file_idx] = {}
                self.file_totals[file_idx] = total_chunks

            self.file_chunks[file_idx][chunk_idx] = payload

        elif tag == b"F":
            if message[1:] == b"DONE" and self.manifest is not None and not self.installed:
                success = self.install_files()
                if success:
                    self.installed = True
                    if link:
                        link.send(b"KDONE")
                else:
                    self.error_msg = "Installation write failed"

    def install_files(self):
        slug = self.manifest["slug"]
        base_dir = f"/apps/{slug}"
        ensure_directory(base_dir)

        files_meta = self.manifest.get("files", [])
        for file_idx, meta in enumerate(files_meta):
            rel_path = meta["path"]
            chunks_dict = self.file_chunks.get(file_idx, {})
            expected_chunks = self.file_totals.get(file_idx, 0)

            # Reconstruct content
            content = b"".join(chunks_dict.get(c, b"") for c in range(expected_chunks))

            target_path = f"{base_dir}/{rel_path}"
            # Ensure subdirectories
            parent_dir = target_path.rsplit("/", 1)[0]
            ensure_directory(parent_dir)

            # If writing __init__.py, ensure it can run from /apps
            if rel_path == "__init__.py":
                try:
                    text = content.decode("utf-8")
                    if f"/system/apps/{slug}" in text:
                        text = text.replace(f"/system/apps/{slug}", f"/apps/{slug}")
                        content = text.encode("utf-8")
                except Exception:
                    pass

            try:
                with open(target_path, "wb") as f:
                    f.write(content)
            except OSError as e:
                print(f"Error writing {target_path}:", e)
                return False
        return True

    @property
    def progress(self):
        if not self.manifest:
            return 0.0
        files_meta = self.manifest.get("files", [])
        if not files_meta:
            return 1.0
        total_chunks = sum(self.file_totals.get(idx, 1) for idx in range(len(files_meta)))
        received_chunks = sum(len(self.file_chunks.get(idx, {})) for idx in range(len(files_meta)))
        return min(1.0, received_chunks / max(1, total_chunks))


class BeamApp:
    TAB_SHARE = 0
    TAB_INSTALLED = 1

    STATE_BROWSE = 0
    STATE_OFFER = 1
    STATE_TRANSFER = 2
    STATE_SUCCESS = 3
    STATE_ERROR = 4

    AUTO_LAUNCH_SECONDS = 4

    def __init__(self):
        self.link = badgelink.Link(GAME) if badgelink else None
        self.proximity = badgelink.Proximity(self.link) if badgelink and self.link else None

        self.tab = self.TAB_SHARE
        self.state = self.STATE_BROWSE
        self.state_at = time.ticks_ms() if hasattr(time, "ticks_ms") else 0

        self.shareable_apps = scan_apps()
        self.installed_apps = scan_sideloaded()

        self.cursor_share = 0
        self.cursor_installed = 0

        self.sender = None
        self.receiver = None
        self.partner_name = "Badge"
        self.partner_id = None
        self.launch_path = None
        self.status_msg = ""
        self.was_linked = False

    def now_ms(self):
        return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)

    def set_state(self, new_state):
        self.state = new_state
        self.state_at = self.now_ms()

    def update_radio(self, now):
        if not self.link:
            return

        self.link.pump()
        linked = self.link.linked

        if linked and not self.was_linked:
            partner = self.link.partner
            if partner:
                self.partner_name = partner.name
                self.partner_id = partner.id

        if self.was_linked and not linked and self.state == self.STATE_TRANSFER:
            if self.receiver and self.receiver.installed:
                self.set_state(self.STATE_SUCCESS)
            elif self.sender and self.sender.finished:
                self.set_state(self.STATE_SUCCESS)
            else:
                self.status_msg = "Link disconnected"
                self.set_state(self.STATE_ERROR)

        self.was_linked = linked

        # Pump active transmissions
        if self.sender and linked:
            self.sender.pump(self.link)

        # Receive incoming packets
        if linked:
            for message in self.link.receive():
                if self.state == self.STATE_BROWSE or self.state == self.STATE_OFFER:
                    # Incoming beam offer
                    if message.startswith(b"M"):
                        self.receiver = ReceiverEngine()
                        self.set_state(self.STATE_TRANSFER)
                        self.receiver.handle(message, self.link)
                        continue

                if self.sender:
                    self.sender.handle(message)
                    if self.sender.rejected_reason:
                        self.status_msg = self.sender.rejected_reason
                        self.set_state(self.STATE_ERROR)
                    elif self.sender.finished:
                        self.set_state(self.STATE_SUCCESS)

                if self.receiver:
                    self.receiver.handle(message, self.link)
                    if self.receiver.error_msg:
                        self.status_msg = self.receiver.error_msg
                        self.set_state(self.STATE_ERROR)
                    elif self.receiver.installed:
                        self.installed_apps = scan_sideloaded()
                        self.set_state(self.STATE_SUCCESS)

        self.link.update()

    def handle_inputs(self, now):
        if self.state == self.STATE_BROWSE:
            if badge.pressed(BUTTON_LEFT):
                self.tab = self.TAB_SHARE
            elif badge.pressed(BUTTON_RIGHT):
                self.tab = self.TAB_INSTALLED
            elif badge.pressed(BUTTON_UP):
                if self.tab == self.TAB_SHARE:
                    self.cursor_share = max(0, self.cursor_share - 1)
                else:
                    self.cursor_installed = max(0, self.cursor_installed - 1)
            elif badge.pressed(BUTTON_DOWN):
                if self.tab == self.TAB_SHARE:
                    self.cursor_share = min(max(0, len(self.shareable_apps) - 1), self.cursor_share + 1)
                else:
                    self.cursor_installed = min(max(0, len(self.installed_apps) - 1), self.cursor_installed + 1)
            elif badge.pressed(BUTTON_SELECT):
                if self.tab == self.TAB_SHARE and self.shareable_apps:
                    selected_app = self.shareable_apps[self.cursor_share]
                    self.sender = SenderEngine(selected_app)
                    self.receiver = None
                    self.set_state(self.STATE_OFFER)
                elif self.tab == self.TAB_INSTALLED and self.installed_apps:
                    app = self.installed_apps[self.cursor_installed]
                    self.launch_path = app["path"]

        elif self.state == self.STATE_OFFER:
            if badge.pressed(BUTTON_BACK) or badge.pressed(BUTTON_LEFT):
                if self.link:
                    self.link.leave()
                self.sender = None
                self.set_state(self.STATE_BROWSE)
            elif self.link and self.link.linked:
                self.set_state(self.STATE_TRANSFER)

        elif self.state == self.STATE_TRANSFER:
            if badge.pressed(BUTTON_BACK):
                if self.link:
                    self.link.leave()
                self.sender = None
                self.receiver = None
                self.set_state(self.STATE_BROWSE)

        elif self.state == self.STATE_SUCCESS:
            elapsed = (now - self.state_at) // 1000
            if self.receiver and self.receiver.installed:
                slug = self.receiver.manifest["slug"]
                if badge.pressed(BUTTON_SELECT) or elapsed >= self.AUTO_LAUNCH_SECONDS:
                    self.launch_path = f"/apps/{slug}"
            if badge.pressed(BUTTON_BACK):
                self.sender = None
                self.receiver = None
                self.set_state(self.STATE_BROWSE)

        elif self.state == self.STATE_ERROR:
            if badge.pressed(BUTTON_SELECT) or badge.pressed(BUTTON_BACK):
                self.sender = None
                self.receiver = None
                self.set_state(self.STATE_BROWSE)

    def draw_header(self, title, tab_active=None):
        screen.pen = black
        screen.clear()

        # Top banner
        screen.pen = card_bg
        screen.rectangle(0, 0, WIDTH, 28)
        screen.pen = card_border
        screen.rectangle(0, 27, WIDTH, 1)

        # Title
        screen.pen = accent
        if title_font:
            screen.font = title_font
        screen.text("BEAM", 8, 4)

        screen.pen = dim_white
        if body_font:
            screen.font = body_font
        screen.text(title, 55, 6)

        # Free space indicator
        free_kb = free_storage_bytes() // 1024
        free_str = f"Free: {free_kb}KB"
        w, _ = screen.measure_text(free_str)
        screen.pen = faint_white
        screen.text(free_str, WIDTH - w - 8, 6)

    def draw_tabs(self):
        # Tabs bar
        screen.pen = card_bg
        screen.rectangle(0, 28, WIDTH, 22)
        screen.pen = card_border
        screen.rectangle(0, 49, WIDTH, 1)

        # Tab 1: Share Apps
        t1_color = accent if self.tab == self.TAB_SHARE else dim_white
        screen.pen = t1_color
        screen.text("< 1. Share Apps >", 16, 32)

        # Tab 2: Sideloaded Apps
        t2_color = accent if self.tab == self.TAB_INSTALLED else dim_white
        screen.pen = t2_color
        screen.text("< 2. Installed Apps >", 175, 32)

    def draw_app_list(self, apps_list, cursor):
        if not apps_list:
            screen.pen = faint_white
            screen.text("No applications found.", 24, 80)
            if self.tab == self.TAB_INSTALLED:
                screen.text("Hold badges back-to-back to receive an app!", 24, 102)
            return

        visible_count = 4
        start_idx = max(0, min(cursor - 1, len(apps_list) - visible_count))
        row_y = 54
        row_height = 36

        for i in range(start_idx, min(start_idx + visible_count, len(apps_list))):
            app = apps_list[i]
            is_active = (i == cursor)

            screen.pen = card_selected if is_active else card_bg
            screen.rectangle(6, row_y, WIDTH - 12, row_height - 3)
            screen.pen = accent if is_active else card_border
            screen.rectangle(6, row_y, WIDTH - 12, 1)
            screen.rectangle(6, row_y + row_height - 4, WIDTH - 12, 1)
            screen.rectangle(6, row_y, 1, row_height - 3)
            screen.rectangle(WIDTH - 7, row_y, 1, row_height - 3)

            # Bullet / Active glyph
            screen.pen = accent if is_active else dim_white
            screen.text(">" if is_active else " ", 12, row_y + 8)

            # App Title
            screen.pen = white if is_active else dim_white
            screen.text(app["name"][:20], 26, row_y + 8)

            # Size & Tag
            size_str = format_size(app["size"])
            tag = "sideload" if app.get("is_sideloaded") else "system"
            info = f"[{tag}] {size_str}"
            w, _ = screen.measure_text(info)
            screen.pen = emerald if is_active else faint_white
            screen.text(info, WIDTH - w - 16, row_y + 8)

            row_y += row_height

        # Footer hints
        screen.pen = card_bg
        screen.rectangle(0, HEIGHT - 24, WIDTH, 24)
        screen.pen = card_border
        screen.rectangle(0, HEIGHT - 25, WIDTH, 1)
        screen.pen = dim_white
        if self.tab == self.TAB_SHARE:
            screen.text("SELECT: Beam App  |  Tap badge to receive", 10, HEIGHT - 18)
        else:
            screen.text("SELECT: Launch App  |  BACK: Exit", 10, HEIGHT - 18)

    def draw_offer(self, now):
        self.draw_header("Hold Badges Together")
        app = self.sender.app_info

        # Card
        screen.pen = card_bg
        screen.rectangle(16, 42, WIDTH - 32, 160)
        screen.pen = card_border
        screen.rectangle(16, 42, WIDTH - 32, 1)
        screen.rectangle(16, 201, WIDTH - 32, 1)
        screen.rectangle(16, 42, 1, 160)
        screen.rectangle(WIDTH - 17, 42, 1, 160)

        # Content
        screen.pen = accent
        screen.text(f"Beaming: {app['name']}", 28, 54)
        screen.pen = dim_white
        screen.text(f"Size: {format_size(app['size'])} ({len(app['files'])} files)", 28, 74)

        # Proximity instructions
        screen.pen = white
        screen.text("HOLD BADGES BACK-TO-BACK", 28, 102)

        peer = self.proximity.syncing() if self.proximity else None
        prog = self.proximity.progress(now) if self.proximity else 0.0

        if peer:
            screen.pen = emerald
            screen.text(f"Found {peer.name}! Syncing...", 28, 126)
            # Progress bar
            screen.pen = faint_white
            screen.rectangle(28, 146, WIDTH - 56, 12)
            screen.pen = emerald
            screen.rectangle(28, 146, int((WIDTH - 56) * prog), 12)
        else:
            screen.pen = dim_white
            screen.text("Align antennas back-to-back to pair", 28, 126)
            # Pulse animation
            pulse = int((now % 1000) / 1000.0 * (WIDTH - 56))
            screen.pen = faint_white
            screen.rectangle(28, 146, WIDTH - 56, 6)
            screen.pen = purple
            screen.rectangle(28 + (pulse % (WIDTH - 76)), 146, 20, 6)

        # Cancel hint
        screen.pen = dim_white
        screen.text("BACK: Cancel", 28, 176)

    def draw_transfer(self, now):
        is_sending = bool(self.sender)
        action_name = "Sending" if is_sending else "Receiving"
        self.draw_header(f"{action_name}...")

        # Card
        screen.pen = card_bg
        screen.rectangle(16, 42, WIDTH - 32, 165)
        screen.pen = card_border
        screen.rectangle(16, 42, WIDTH - 32, 1)
        screen.rectangle(16, 206, WIDTH - 32, 1)
        screen.rectangle(16, 42, 1, 165)
        screen.rectangle(WIDTH - 17, 42, 1, 165)

        # Peer info
        if self.partner_id and badgelink:
            badgelink.draw_identicon(screen, self.partner_id, 28, 52, 36)

        screen.pen = white
        screen.text(f"Connected to {self.partner_name}", 74, 56)

        app_name = self.sender.app_info["name"] if self.sender else (
            self.receiver.manifest.get("name", "App") if self.receiver and self.receiver.manifest else "App"
        )
        screen.pen = accent
        screen.text(f"{action_name}: {app_name}", 74, 76)

        # Progress bar
        prog = self.sender.progress if self.sender else (self.receiver.progress if self.receiver else 0.0)
        screen.pen = faint_white
        screen.rectangle(28, 110, WIDTH - 56, 16)
        screen.pen = accent
        screen.rectangle(28, 110, int((WIDTH - 56) * prog), 16)

        percent_str = f"{int(prog * 100)}%"
        screen.pen = white
        screen.text(percent_str, 28, 134)

        status = "Transferring data over BLE..." if prog < 1.0 else "Finalizing..."
        screen.pen = dim_white
        screen.text(status, 28, 154)

        screen.pen = faint_white
        screen.text("Do not separate badges until complete", 28, 178)

    def draw_success(self, now):
        self.draw_header("Transfer Complete")
        is_sender = bool(self.sender)

        screen.pen = card_bg
        screen.rectangle(16, 42, WIDTH - 32, 165)
        screen.pen = emerald
        screen.rectangle(16, 42, WIDTH - 32, 1)
        screen.rectangle(16, 206, WIDTH - 32, 1)
        screen.rectangle(16, 42, 1, 165)
        screen.rectangle(WIDTH - 17, 42, 1, 165)

        screen.pen = emerald
        screen.text("SUCCESS!", 28, 54)

        if is_sender:
            app_name = self.sender.app_info["name"]
            screen.pen = white
            screen.text(f"Shared {app_name}", 28, 80)
            screen.pen = dim_white
            screen.text(f"Installed on {self.partner_name}'s badge.", 28, 104)
            screen.pen = accent
            screen.text("BACK: Done", 28, 150)
        else:
            app_name = self.receiver.manifest.get("name", "App")
            elapsed = (now - self.state_at) // 1000
            countdown = max(0, self.AUTO_LAUNCH_SECONDS - elapsed)

            screen.pen = white
            screen.text(f"{app_name} Installed!", 28, 80)
            screen.pen = dim_white
            screen.text(f"Saved to /apps/{self.receiver.manifest['slug']}", 28, 104)

            screen.pen = emerald
            screen.text(f"Launching in {countdown}s...", 28, 134)

            screen.pen = accent
            screen.text("SELECT: Launch Now   BACK: Close", 28, 164)

    def draw_error(self):
        self.draw_header("Error")
        screen.pen = card_bg
        screen.rectangle(16, 42, WIDTH - 32, 160)
        screen.pen = rose
        screen.rectangle(16, 42, WIDTH - 32, 1)
        screen.rectangle(16, 201, WIDTH - 32, 1)
        screen.rectangle(16, 42, 1, 160)
        screen.rectangle(WIDTH - 17, 42, 1, 160)

        screen.pen = rose
        screen.text("TRANSFER FAILED", 28, 56)

        screen.pen = white
        screen.text(self.status_msg or "Unknown error", 28, 86)

        screen.pen = dim_white
        screen.text("Check badge distance and storage.", 28, 116)
        screen.pen = accent
        screen.text("SELECT / BACK: Return", 28, 156)

    def draw(self, now):
        if self.state == self.STATE_BROWSE:
            self.draw_header("Share & Install Apps")
            self.draw_tabs()
            apps = self.shareable_apps if self.tab == self.TAB_SHARE else self.installed_apps
            cursor = self.cursor_share if self.tab == self.TAB_SHARE else self.cursor_installed
            self.draw_app_list(apps, cursor)
        elif self.state == self.STATE_OFFER:
            self.draw_offer(now)
        elif self.state == self.STATE_TRANSFER:
            self.draw_transfer(now)
        elif self.state == self.STATE_SUCCESS:
            self.draw_success(now)
        elif self.state == self.STATE_ERROR:
            self.draw_error()

    def update(self):
        now = self.now_ms()
        self.update_radio(now)
        self.handle_inputs(now)
        self.draw(now)

        if self.launch_path:
            return self.launch_path
        return None


app = BeamApp()


def update():
    return app.update()


run(update)
