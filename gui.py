#!/usr/bin/env python3
"""
Interactive Graphics Control Panel - Native macOS
Launch and control all rendering projects with the chair model.
"""

import subprocess
import os
import Quartz

import AppKit
import Foundation
from objc import super  # noqa

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAIR_OBJ = os.path.join(ROOT_DIR, "common-assets", "chair", "chair.obj")
YODA_OBJ = os.path.join(ROOT_DIR, "common-assets", "yoda", "yoda.obj")
CARGO = os.path.expanduser("~/.cargo/bin/cargo")

# Key codes
KEY_1, KEY_2, KEY_3, KEY_4 = 18, 19, 20, 21
KEY_SPACE, KEY_UP, KEY_DOWN = 49, 126, 125

# Rendering technique groups - user can pick which to launch with the chair
RENDER_GROUPS = [
    {
        "title": "Shadows",
        "desc": "Choose shadow rendering technique for the chair",
        "options": [
            ("Shadow Mapping", "proj-7-shadow-mapping", True),
            ("Ray Traced Shadows", "proj-7-ray-traced-shadows", True),
        ],
        "controls": [
            ("1", "Ambient", KEY_1), ("2", "Diffuse", KEY_2),
            ("3", "Specular", KEY_3), ("4", "All", KEY_4),
        ],
    },
    {
        "title": "Reflections",
        "desc": "Choose reflection rendering technique",
        "options": [
            ("Environment Map", "proj-6-environment-mapping", True),
            ("Ray Traced Reflections", "proj-6-ray-traced-reflections", True),
        ],
        "controls": [
            ("1", "Ambient", KEY_1), ("2", "Diffuse", KEY_2),
            ("3", "Specular", KEY_3), ("4", "All", KEY_4),
        ],
    },
    {
        "title": "Bedroom Scene (Proj 9)",
        "desc": "Chair + textures + shadows + env map + skybox",
        "options": [
            ("Bedroom Env Map", "proj-9-bedroom-envmap", False),
        ],
        "controls": [
            ("1", "Ambient", KEY_1), ("2", "Diffuse", KEY_2),
            ("3", "Specular", KEY_3), ("4", "All", KEY_4),
            ("Up", "Reflect +", KEY_UP), ("Down", "Reflect -", KEY_DOWN),
        ],
    },
]

# Standalone projects
STANDALONE = [
    ("proj-2-transformations", "2. Transformations", False,
     [("Space", "Toggle Projection", KEY_SPACE)]),
    ("proj-3-shading", "3. Shading", False,
     [("1", "Ambient", KEY_1), ("2", "Diffuse", KEY_2),
      ("3", "Specular", KEY_3), ("4", "All", KEY_4)]),
    ("proj-4-textures", "4. Textures", True, []),
    ("proj-5-render-buffers", "5. Render Buffers", True,
     [("1", "Nearest", KEY_1), ("2", "Bilinear", KEY_2),
      ("3", "Trilinear", KEY_3), ("4", "Anisotropic", KEY_4)]),
    ("proj-8-tesselation", "8. Tessellation", False,
     [("Up", "Tess +", KEY_UP), ("Down", "Tess -", KEY_DOWN),
      ("1", "Ambient", KEY_1), ("2", "Diffuse", KEY_2),
      ("3", "Specular", KEY_3), ("4", "All", KEY_4)]),
    ("x-rt", "X. Ray Tracing", True, []),
]

# Colors (Catppuccin Mocha)
SUBTEXT_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.68, 0.78, 1.0)
GREEN_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.89, 0.63, 1.0)
TEXT_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.84, 0.96, 1.0)
TEAL_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.58, 0.89, 0.83, 1.0)
RED_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.55, 0.66, 1.0)
YELLOW_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.98, 0.90, 0.53, 1.0)
BLUE_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.54, 0.68, 0.99, 1.0)
MAUVE_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.62, 0.95, 1.0)
BG_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.12, 0.18, 1.0)
CARD_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.19, 0.20, 0.27, 1.0)
CTRL_BG_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.15, 0.16, 0.22, 1.0)
SECTION_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.22, 0.23, 0.30, 1.0)

# Global state
g_processes = {}
g_status_fields = {}
g_launch_buttons = {}
g_tag_to_pid = {}
g_tag_to_key = {}


def send_key_to_process(pid, keycode):
    if pid not in g_processes or g_processes[pid].poll() is not None:
        return
    proc_pid = g_processes[pid].pid
    ev_down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    ev_up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPostToPid(proc_pid, ev_down)
    Quartz.CGEventPostToPid(proc_pid, ev_up)


def make_label(text, size, bold=False, color=TEXT_CLR):
    lbl = AppKit.NSTextField.labelWithString_(text)
    lbl.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size))
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setTextColor_(color)
    return lbl


def make_button(title, target, action, tag=0):
    btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 100, 28))
    btn.setTitle_(title)
    btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
    btn.setTarget_(target)
    btn.setAction_(action)
    btn.setTag_(tag)
    btn.setWantsLayer_(True)
    btn.setFont_(AppKit.NSFont.boldSystemFontOfSize_(11))
    return btn


def make_small_button(title, target, action, tag):
    btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 70, 24))
    btn.setTitle_(title)
    btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
    btn.setTarget_(target)
    btn.setAction_(action)
    btn.setTag_(tag)
    btn.setWantsLayer_(True)
    btn.setFont_(AppKit.NSFont.systemFontOfSize_(10))
    return btn


def launch_project(pid, uses_args=False):
    if pid in g_processes and g_processes[pid].poll() is None:
        return
    cmd = [CARGO, "run", "-p", pid]
    if uses_args:
        cmd += ["--", CHAIR_OBJ]
    env = os.environ.copy()
    env["PATH"] = os.path.expanduser("~/.cargo/bin") + ":" + env.get("PATH", "")
    proc = subprocess.Popen(cmd, cwd=ROOT_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    g_processes[pid] = proc
    if pid in g_status_fields:
        g_status_fields[pid].setStringValue_("\u25cf Running")
        g_status_fields[pid].setTextColor_(GREEN_CLR)
    if pid in g_launch_buttons:
        g_launch_buttons[pid].setTitle_("\u25a0 Stop")


def stop_project(pid):
    if pid in g_processes:
        proc = g_processes[pid]
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        del g_processes[pid]
    if pid in g_status_fields:
        g_status_fields[pid].setStringValue_("\u25cf Stopped")
        g_status_fields[pid].setTextColor_(SUBTEXT_CLR)
    if pid in g_launch_buttons:
        g_launch_buttons[pid].setTitle_("\u25b6 Launch")


# Store uses_args per pid for toggle
g_uses_args = {}


def build_render_group_card(group, y, width, target):
    """Build a grouped card with multiple launch options and shared controls."""
    n_options = len(group["options"])
    n_controls = len(group["controls"])
    ctrl_rows = (n_controls + 5) // 6  # 6 buttons per row
    card_height = 40 + n_options * 32 + (38 * ctrl_rows if n_controls else 0) + 10

    card = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(20, y, width, card_height))
    card.setWantsLayer_(True)
    card.layer().setBackgroundColor_(SECTION_CLR.CGColor())
    card.layer().setCornerRadius_(8)

    cy = card_height

    # Title
    cy -= 22
    lbl = make_label(group["title"], 15, bold=True, color=MAUVE_CLR)
    lbl.setFrame_(Foundation.NSMakeRect(12, cy, 400, 22))
    card.addSubview_(lbl)

    dlbl = make_label(group["desc"], 10, color=SUBTEXT_CLR)
    dlbl.setFrame_(Foundation.NSMakeRect(12, cy - 14, 500, 14))
    card.addSubview_(dlbl)
    cy -= 18

    # Option rows (each is a launch button + status)
    for opt_name, opt_pid, opt_uses_args in group["options"]:
        cy -= 32
        g_uses_args[opt_pid] = opt_uses_args

        tag = hash(opt_pid) & 0x7FFFFFFF
        g_tag_to_pid[tag] = opt_pid

        btn = make_button("\u25b6 " + opt_name, target, "toggleProject:", tag)
        btn.setFrame_(Foundation.NSMakeRect(12, cy, 220, 26))
        btn.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        card.addSubview_(btn)
        g_launch_buttons[opt_pid] = btn

        status = make_label("\u25cf Stopped", 10, color=SUBTEXT_CLR)
        status.setFrame_(Foundation.NSMakeRect(240, cy + 4, 100, 16))
        card.addSubview_(status)
        g_status_fields[opt_pid] = status

    # Control buttons
    if n_controls:
        cy -= 6
        ctrl_bg = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(8, 4, width - 16, cy - 4))
        ctrl_bg.setWantsLayer_(True)
        ctrl_bg.layer().setBackgroundColor_(CTRL_BG_CLR.CGColor())
        ctrl_bg.layer().setCornerRadius_(5)
        card.addSubview_(ctrl_bg)

        ctrl_h = cy - 4
        clbl = make_label("Controls:", 9, bold=True, color=YELLOW_CLR)
        clbl.setFrame_(Foundation.NSMakeRect(6, ctrl_h - 18, 60, 16))
        ctrl_bg.addSubview_(clbl)

        x_off = 70
        row_y = ctrl_h - 20
        for key_label, btn_title, keycode in group["controls"]:
            # Send key to ALL running options in this group
            all_pids = [o[1] for o in group["options"]]
            ctrl_tag = hash(f"grp_{group['title']}_{key_label}") & 0x7FFFFFFF
            g_tag_to_key[ctrl_tag] = (all_pids, keycode)
            cbtn = make_small_button(btn_title, target, "sendGroupKey:", ctrl_tag)
            btn_w = max(55, len(btn_title) * 7 + 16)
            cbtn.setFrame_(Foundation.NSMakeRect(x_off, row_y, btn_w, 22))
            ctrl_bg.addSubview_(cbtn)
            x_off += btn_w + 4
            if x_off > width - 80:
                x_off = 70
                row_y -= 26

    return card, card_height


def build_standalone_card(pid, name, uses_args, key_controls, y, width, target):
    """Build a card for a standalone project."""
    has_controls = len(key_controls) > 0
    card_height = 70 if not has_controls else 105

    card = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(20, y, width, card_height))
    card.setWantsLayer_(True)
    card.layer().setBackgroundColor_(CARD_CLR.CGColor())
    card.layer().setCornerRadius_(8)

    top_y = card_height - 25
    g_uses_args[pid] = uses_args

    lbl = make_label(name, 13, bold=True, color=TEXT_CLR)
    lbl.setFrame_(Foundation.NSMakeRect(12, top_y, 300, 20))
    card.addSubview_(lbl)

    tag = hash(pid) & 0x7FFFFFFF
    g_tag_to_pid[tag] = pid

    btn = make_button("\u25b6 Launch", target, "toggleProject:", tag)
    btn.setFrame_(Foundation.NSMakeRect(width - 130, top_y - 3, 110, 26))
    card.addSubview_(btn)
    g_launch_buttons[pid] = btn

    status = make_label("\u25cf Stopped", 10, color=SUBTEXT_CLR)
    status.setFrame_(Foundation.NSMakeRect(width - 260, top_y + 2, 100, 16))
    status.setAlignment_(AppKit.NSTextAlignmentRight)
    card.addSubview_(status)
    g_status_fields[pid] = status

    if has_controls:
        ctrl_bg = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(8, 4, width - 16, 34))
        ctrl_bg.setWantsLayer_(True)
        ctrl_bg.layer().setBackgroundColor_(CTRL_BG_CLR.CGColor())
        ctrl_bg.layer().setCornerRadius_(5)
        card.addSubview_(ctrl_bg)

        clbl = make_label("Controls:", 9, bold=True, color=YELLOW_CLR)
        clbl.setFrame_(Foundation.NSMakeRect(6, 7, 60, 16))
        ctrl_bg.addSubview_(clbl)

        x_off = 70
        for key_label, btn_title, keycode in key_controls:
            ctrl_tag = hash(f"{pid}_{key_label}") & 0x7FFFFFFF
            g_tag_to_key[ctrl_tag] = ([pid], keycode)
            cbtn = make_small_button(btn_title, target, "sendGroupKey:", ctrl_tag)
            btn_w = max(55, len(btn_title) * 7 + 16)
            cbtn.setFrame_(Foundation.NSMakeRect(x_off, 5, btn_w, 24))
            ctrl_bg.addSubview_(cbtn)
            x_off += btn_w + 4

    return card, card_height


class AppDelegate(AppKit.NSObject):
    def applicationDidFinishLaunching_(self, notification):
        menubar = AppKit.NSMenu.new()
        app_menu_item = AppKit.NSMenuItem.new()
        menubar.addItem_(app_menu_item)
        app_menu = AppKit.NSMenu.new()
        app_menu.addItem_(
            AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "terminate:", "q"))
        app_menu_item.setSubmenu_(app_menu)
        AppKit.NSApp.setMainMenu_(menubar)

        W, H = 850, 820
        frame = Foundation.NSMakeRect(100, 80, W, H)
        style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable |
                 AppKit.NSWindowStyleMaskMiniaturizable | AppKit.NSWindowStyleMaskResizable)
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False)
        self.window.setTitle_("Interactive Graphics Control Panel")
        self.window.setBackgroundColor_(BG_CLR)
        self.window.setMinSize_(Foundation.NSMakeSize(700, 500))

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, W, H))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        scroll.setDrawsBackground_(False)

        # Pre-calculate total height
        doc_height = 130  # header + global buttons
        for grp in RENDER_GROUPS:
            n_opt = len(grp["options"])
            n_ctrl = len(grp["controls"])
            ctrl_rows = (n_ctrl + 5) // 6
            doc_height += 40 + n_opt * 32 + (38 * ctrl_rows if n_ctrl else 0) + 10 + 8
        doc_height += 35  # "Other Projects" label
        for proj in STANDALONE:
            has_ctrl = len(proj[3]) > 0
            doc_height += (115 if has_ctrl else 78)
        doc_height += 20

        doc = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, W - 20, doc_height))
        y = doc_height

        # Header
        y -= 40
        title = make_label("Interactive Computer Graphics", 22, bold=True, color=TEXT_CLR)
        title.setFrame_(Foundation.NSMakeRect(20, y, 500, 28))
        doc.addSubview_(title)

        y -= 20
        sub = make_label("Chair Model \u2022 Metal 3 \u2022 Rust  |  Drag: rotate  |  Ctrl+Drag: move light",
                         11, color=SUBTEXT_CLR)
        sub.setFrame_(Foundation.NSMakeRect(20, y, 700, 16))
        doc.addSubview_(sub)

        # Global buttons
        y -= 36
        stop_all = make_button("\u25a0 Stop All", self, "stopAll:")
        stop_all.setFrame_(Foundation.NSMakeRect(20, y, 120, 28))
        doc.addSubview_(stop_all)

        # Render technique groups
        y -= 12
        for grp in RENDER_GROUPS:
            card, ch = build_render_group_card(grp, 0, W - 60, self)
            y -= ch + 8
            card.setFrameOrigin_(Foundation.NSMakePoint(20, y))
            doc.addSubview_(card)

        # Separator
        y -= 30
        sep_label = make_label("Other Projects", 14, bold=True, color=BLUE_CLR)
        sep_label.setFrame_(Foundation.NSMakeRect(20, y, 200, 20))
        doc.addSubview_(sep_label)

        # Standalone projects
        for pid, name, uses_args, key_controls in STANDALONE:
            card, ch = build_standalone_card(pid, name, uses_args, key_controls, 0, W - 60, self)
            y -= ch + 8
            card.setFrameOrigin_(Foundation.NSMakePoint(20, y))
            doc.addSubview_(card)

        scroll.setDocumentView_(doc)
        self.window.setContentView_(scroll)
        self.window.makeKeyAndOrderFront_(None)
        self.window.center()

        Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "pollProcesses:", None, True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True

    def applicationWillTerminate_(self, notification):
        for pid in list(g_processes.keys()):
            stop_project(pid)

    def toggleProject_(self, sender):
        pid = g_tag_to_pid.get(sender.tag())
        if pid is None:
            return
        if pid in g_processes and g_processes[pid].poll() is None:
            stop_project(pid)
        else:
            launch_project(pid, g_uses_args.get(pid, False))

    def sendGroupKey_(self, sender):
        info = g_tag_to_key.get(sender.tag())
        if info is None:
            return
        pids, keycode = info
        for pid in pids:
            send_key_to_process(pid, keycode)

    def stopAll_(self, sender):
        for pid in list(g_processes.keys()):
            stop_project(pid)

    def pollProcesses_(self, timer):
        for pid in list(g_processes.keys()):
            if g_processes[pid].poll() is not None:
                del g_processes[pid]
                if pid in g_status_fields:
                    g_status_fields[pid].setStringValue_("\u25cf Stopped")
                    g_status_fields[pid].setTextColor_(SUBTEXT_CLR)
                if pid in g_launch_buttons:
                    g_launch_buttons[pid].setTitle_("\u25b6 Launch")


def main():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
