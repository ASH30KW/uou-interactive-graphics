#!/usr/bin/env python3
"""
Interactive Graphics Control Panel - Native macOS
Launch and control all rendering projects with the chair model.
Sends keyboard events to project windows for interactive control.
"""

import subprocess
import os
import Quartz

import AppKit
import Foundation
from objc import super  # noqa

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAIR_OBJ = os.path.join(ROOT_DIR, "common-assets", "chair", "chair.obj")
CARGO = os.path.expanduser("~/.cargo/bin/cargo")

# Key codes for macOS
KEY_1 = 18
KEY_2 = 19
KEY_3 = 20
KEY_4 = 21
KEY_SPACE = 49
KEY_UP = 126
KEY_DOWN = 125
KEY_LEFT = 123
KEY_RIGHT = 124
KEY_P = 35

PROJECTS = [
    ("proj-2-transformations", "2. Transformations", "Rotate, Ortho/Perspective", False,
     [("Space", "Toggle Projection", KEY_SPACE, 0)]),
    ("proj-3-shading", "3. Shading", "Ambient + Diffuse + Specular", False,
     [("1", "Ambient", KEY_1, 0), ("2", "Diffuse", KEY_2, 0),
      ("3", "Specular", KEY_3, 0), ("4", "All", KEY_4, 0)]),
    ("proj-4-textures", "4. Textures", "Material and texture rendering", True, []),
    ("proj-5-render-buffers", "5. Render Buffers", "Render-to-texture, sampling", True,
     [("1", "Nearest", KEY_1, 0), ("2", "Bilinear", KEY_2, 0),
      ("3", "Trilinear", KEY_3, 0), ("4", "Anisotropic", KEY_4, 0)]),
    ("proj-6-environment-mapping", "6. Env Map", "Skybox + mirror reflections", True,
     [("1", "Ambient", KEY_1, 0), ("2", "Diffuse", KEY_2, 0),
      ("3", "Specular", KEY_3, 0), ("4", "All", KEY_4, 0)]),
    ("proj-6-ray-traced-reflections", "6X. RT Reflections", "Multi-bounce ray traced", True,
     [("1", "Ambient", KEY_1, 0), ("2", "Diffuse", KEY_2, 0),
      ("3", "Specular", KEY_3, 0), ("4", "All", KEY_4, 0)]),
    ("proj-7-shadow-mapping", "7. Shadow Map", "Depth-based shadows", True,
     [("1", "Ambient", KEY_1, 0), ("2", "Diffuse", KEY_2, 0),
      ("3", "Specular", KEY_3, 0), ("4", "All", KEY_4, 0)]),
    ("proj-7-ray-traced-shadows", "7X. RT Shadows", "Ray traced shadows", True,
     [("1", "Ambient", KEY_1, 0), ("2", "Diffuse", KEY_2, 0),
      ("3", "Specular", KEY_3, 0), ("4", "All", KEY_4, 0)]),
    ("proj-8-tesselation", "8. Tessellation", "Normal + displacement mapping", False,
     [("Up", "Tess +", KEY_UP, 0), ("Down", "Tess -", KEY_DOWN, 0),
      ("1", "Ambient", KEY_1, 0), ("2", "Diffuse", KEY_2, 0),
      ("3", "Specular", KEY_3, 0), ("4", "All", KEY_4, 0)]),
    ("proj-9-bedroom-envmap", "9. Bedroom Env Map", "Chair in bedroom environment", False,
     [("1", "Ambient", KEY_1, 0), ("2", "Diffuse", KEY_2, 0),
      ("3", "Specular", KEY_3, 0), ("4", "All", KEY_4, 0)]),
    ("x-rt", "X. Ray Tracing", "Primary ray, accel structures", True, []),
]

SUBTEXT_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.68, 0.78, 1.0)
GREEN_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.89, 0.63, 1.0)
TEXT_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.84, 0.96, 1.0)
TEAL_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.58, 0.89, 0.83, 1.0)
RED_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.55, 0.66, 1.0)
YELLOW_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.98, 0.90, 0.53, 1.0)
BG_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.12, 0.18, 1.0)
CARD_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.19, 0.20, 0.27, 1.0)
CTRL_BG_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.15, 0.16, 0.22, 1.0)

# Global state
g_processes = {}
g_status_fields = {}
g_buttons = {}
g_tag_to_pid = {}
g_tag_to_key = {}  # tag -> (pid, keycode, modifiers)


def send_key_to_process(pid, keycode, modifiers=0):
    """Send a key event to the project's window via CGEvent."""
    if pid not in g_processes or g_processes[pid].poll() is not None:
        return
    proc_pid = g_processes[pid].pid

    flags = 0
    if modifiers & 1:  # shift
        flags |= Quartz.kCGEventFlagMaskShift
    if modifiers & 2:  # control
        flags |= Quartz.kCGEventFlagMaskControl

    event_down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    event_up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    if flags:
        Quartz.CGEventSetFlags(event_down, flags)
        Quartz.CGEventSetFlags(event_up, flags)
    Quartz.CGEventPostToPid(proc_pid, event_down)
    Quartz.CGEventPostToPid(proc_pid, event_up)


def make_label(text, size, bold=False, color=TEXT_CLR):
    lbl = AppKit.NSTextField.labelWithString_(text)
    if bold:
        lbl.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size))
    else:
        lbl.setFont_(AppKit.NSFont.systemFontOfSize_(size))
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setTextColor_(color)
    return lbl


def make_button(title, target, action):
    btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 100, 30))
    btn.setTitle_(title)
    btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
    btn.setTarget_(target)
    btn.setAction_(action)
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


def make_card(pid, name, desc, key_controls, y, width, target):
    has_controls = len(key_controls) > 0
    card_height = 120 if has_controls else 80

    card = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(20, y, width, card_height))
    card.setWantsLayer_(True)
    card.layer().setBackgroundColor_(CARD_CLR.CGColor())
    card.layer().setCornerRadius_(8)

    top_y = card_height - 25

    # Name
    lbl = make_label(name, 14, bold=True, color=TEXT_CLR)
    lbl.setFrame_(Foundation.NSMakeRect(12, top_y, 300, 22))
    card.addSubview_(lbl)

    # Description
    dlbl = make_label(desc, 11, color=SUBTEXT_CLR)
    dlbl.setFrame_(Foundation.NSMakeRect(12, top_y - 18, 400, 16))
    card.addSubview_(dlbl)

    # Status
    status = make_label("\u25cf Stopped", 10, color=SUBTEXT_CLR)
    status.setFrame_(Foundation.NSMakeRect(width - 250, top_y, 100, 18))
    status.setAlignment_(AppKit.NSTextAlignmentRight)
    card.addSubview_(status)
    g_status_fields[pid] = status

    # Launch button
    btn = make_button("\u25b6 Launch", target, "toggleProject:")
    btn.setFrame_(Foundation.NSMakeRect(width - 130, top_y - 5, 110, 28))
    tag = hash(pid) & 0x7FFFFFFF
    btn.setTag_(tag)
    card.addSubview_(btn)
    g_buttons[pid] = btn
    g_tag_to_pid[tag] = pid

    # Control buttons row
    if has_controls:
        ctrl_bg = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(8, 4, width - 16, 34))
        ctrl_bg.setWantsLayer_(True)
        ctrl_bg.layer().setBackgroundColor_(CTRL_BG_CLR.CGColor())
        ctrl_bg.layer().setCornerRadius_(5)
        card.addSubview_(ctrl_bg)

        ctrl_label = make_label("Controls:", 9, bold=True, color=YELLOW_CLR)
        ctrl_label.setFrame_(Foundation.NSMakeRect(6, 7, 60, 16))
        ctrl_bg.addSubview_(ctrl_label)

        x_offset = 70
        for key_label, btn_title, keycode, mods in key_controls:
            ctrl_tag = hash(f"{pid}_{key_label}") & 0x7FFFFFFF
            g_tag_to_key[ctrl_tag] = (pid, keycode, mods)
            ctrl_btn = make_small_button(btn_title, target, "sendKey:")
            ctrl_btn.setTag_(ctrl_tag)
            btn_width = max(55, len(btn_title) * 7 + 16)
            ctrl_btn.setFrame_(Foundation.NSMakeRect(x_offset, 5, btn_width, 24))
            ctrl_bg.addSubview_(ctrl_btn)
            x_offset += btn_width + 4

    return card, card_height


def launch_project(pid):
    if pid in g_processes and g_processes[pid].poll() is None:
        return
    proj = next(p for p in PROJECTS if p[0] == pid)
    cmd = [CARGO, "run", "-p", pid]
    if proj[3]:
        cmd += ["--", CHAIR_OBJ]
    env = os.environ.copy()
    env["PATH"] = os.path.expanduser("~/.cargo/bin") + ":" + env.get("PATH", "")
    proc = subprocess.Popen(cmd, cwd=ROOT_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    g_processes[pid] = proc
    g_status_fields[pid].setStringValue_("\u25cf Running")
    g_status_fields[pid].setTextColor_(GREEN_CLR)
    g_buttons[pid].setTitle_("\u25a0 Stop")


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
        g_buttons[pid].setTitle_("\u25b6 Launch")


class AppDelegate(AppKit.NSObject):
    def applicationDidFinishLaunching_(self, notification):
        # Menu
        menubar = AppKit.NSMenu.new()
        app_menu_item = AppKit.NSMenuItem.new()
        menubar.addItem_(app_menu_item)
        app_menu = AppKit.NSMenu.new()
        app_menu.addItem_(
            AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "terminate:", "q"))
        app_menu_item.setSubmenu_(app_menu)
        AppKit.NSApp.setMainMenu_(menubar)

        # Window
        W, H = 820, 780
        frame = Foundation.NSMakeRect(200, 100, W, H)
        style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable |
                 AppKit.NSWindowStyleMaskMiniaturizable | AppKit.NSWindowStyleMaskResizable)
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False)
        self.window.setTitle_("Interactive Graphics Control Panel")
        self.window.setBackgroundColor_(BG_CLR)
        self.window.setMinSize_(Foundation.NSMakeSize(650, 500))

        # Scroll view
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, W, H))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        scroll.setDrawsBackground_(False)

        # Calculate total height
        total_card_height = 0
        for proj in PROJECTS:
            has_controls = len(proj[4]) > 0
            total_card_height += (130 if has_controls else 90)
        doc_height = 120 + total_card_height + 20

        doc = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, W - 20, doc_height))

        y = doc_height

        # Header
        y -= 45
        title = make_label("Interactive Computer Graphics", 22, bold=True, color=TEXT_CLR)
        title.setFrame_(Foundation.NSMakeRect(20, y, 500, 30))
        doc.addSubview_(title)

        y -= 22
        sub = make_label("Chair Model \u2022 Metal 3 \u2022 Rust  |  Use controls below to interact",
                         12, color=SUBTEXT_CLR)
        sub.setFrame_(Foundation.NSMakeRect(20, y, 600, 18))
        doc.addSubview_(sub)

        # Global buttons
        y -= 40
        launch_all = make_button("\u25b6 Launch All", self, "launchAll:")
        launch_all.setFrame_(Foundation.NSMakeRect(20, y, 120, 30))
        doc.addSubview_(launch_all)

        stop_all = make_button("\u25a0 Stop All", self, "stopAll:")
        stop_all.setFrame_(Foundation.NSMakeRect(150, y, 120, 30))
        doc.addSubview_(stop_all)

        # Info
        info = make_label("Drag: rotate camera  |  Ctrl+Drag: move light  |  Buttons send keys to project windows",
                          10, color=TEAL_CLR)
        info.setFrame_(Foundation.NSMakeRect(290, y + 7, 500, 16))
        doc.addSubview_(info)

        # Cards
        for pid, name, desc, uses_args, key_controls in PROJECTS:
            has_controls = len(key_controls) > 0
            card_space = 130 if has_controls else 90
            y -= card_space
            card, _ = make_card(pid, name, desc, key_controls, y, W - 60, self)
            doc.addSubview_(card)

        scroll.setDocumentView_(doc)
        self.window.setContentView_(scroll)
        self.window.makeKeyAndOrderFront_(None)
        self.window.center()

        # Poll timer
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
            launch_project(pid)

    def sendKey_(self, sender):
        info = g_tag_to_key.get(sender.tag())
        if info is None:
            return
        pid, keycode, mods = info
        send_key_to_process(pid, keycode, mods)

    def launchAll_(self, sender):
        for pid, _, _, _, _ in PROJECTS:
            launch_project(pid)

    def stopAll_(self, sender):
        for pid in list(g_processes.keys()):
            stop_project(pid)

    def pollProcesses_(self, timer):
        for pid in list(g_processes.keys()):
            if g_processes[pid].poll() is not None:
                del g_processes[pid]
                g_status_fields[pid].setStringValue_("\u25cf Stopped")
                g_status_fields[pid].setTextColor_(SUBTEXT_CLR)
                g_buttons[pid].setTitle_("\u25b6 Launch")


def main():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
