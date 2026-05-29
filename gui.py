#!/usr/bin/env python3
"""
Interactive Graphics Control Panel - Native macOS
Launch and control all rendering projects with the chair model.
"""

import subprocess
import os

import AppKit
import Foundation
from objc import super  # noqa

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAIR_OBJ = os.path.join(ROOT_DIR, "common-assets", "chair", "chair.obj")
CARGO = os.path.expanduser("~/.cargo/bin/cargo")

PROJECTS = [
    ("proj-2-transformations", "2. Transformations", "Rotate, Ortho/Perspective", False,
     "Drag: rotate | Space: toggle projection"),
    ("proj-3-shading", "3. Shading", "Ambient + Diffuse + Specular", False,
     "Drag: rotate | Ctrl+Drag: light | 1-4: modes"),
    ("proj-4-textures", "4. Textures", "Material and texture rendering", True,
     "Drag: rotate | Ctrl+Drag: light"),
    ("proj-5-render-buffers", "5. Render Buffers", "Render-to-texture, sampling", True,
     "Drag: rotate | 1-4: sampling modes"),
    ("proj-6-environment-mapping", "6. Env Map", "Skybox + mirror reflections", True,
     "Drag: rotate | Ctrl+Drag: light"),
    ("proj-6-ray-traced-reflections", "6X. RT Reflections", "Multi-bounce ray traced", True,
     "Drag: rotate | Ctrl+Drag: light | Right-click: laser"),
    ("proj-7-shadow-mapping", "7. Shadow Map", "Depth-based shadows", True,
     "Drag: rotate | Ctrl+Drag: light"),
    ("proj-7-ray-traced-shadows", "7X. RT Shadows", "Ray traced shadows", True,
     "Drag: rotate | Ctrl+Drag: light"),
    ("proj-8-tesselation", "8. Tessellation", "Normal + displacement mapping", False,
     "Drag: rotate | Arrows: tess level"),
    ("x-rt", "X. Ray Tracing", "Primary ray, accel structures", True,
     "Drag: rotate"),
]

SUBTEXT_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.68, 0.78, 1.0)
GREEN_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.89, 0.63, 1.0)
TEXT_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.84, 0.96, 1.0)
TEAL_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.58, 0.89, 0.83, 1.0)
RED_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.55, 0.66, 1.0)
BG_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.12, 0.18, 1.0)
CARD_CLR = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.19, 0.20, 0.27, 1.0)

# Global state
g_processes = {}
g_status_fields = {}
g_buttons = {}
g_tag_to_pid = {}


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


def make_card(pid, name, desc, controls, y, width, target):
    card = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(20, y, width, 85))
    card.setWantsLayer_(True)
    card.layer().setBackgroundColor_(CARD_CLR.CGColor())
    card.layer().setCornerRadius_(8)

    lbl = make_label(name, 14, bold=True, color=TEXT_CLR)
    lbl.setFrame_(Foundation.NSMakeRect(12, 55, 300, 22))
    card.addSubview_(lbl)

    dlbl = make_label(desc, 11, color=SUBTEXT_CLR)
    dlbl.setFrame_(Foundation.NSMakeRect(12, 36, 400, 16))
    card.addSubview_(dlbl)

    clbl = make_label(controls, 10, color=TEAL_CLR)
    clbl.setFrame_(Foundation.NSMakeRect(12, 8, 500, 26))
    card.addSubview_(clbl)

    status = make_label("\u25cf Stopped", 10, color=SUBTEXT_CLR)
    status.setFrame_(Foundation.NSMakeRect(width - 250, 58, 100, 18))
    status.setAlignment_(AppKit.NSTextAlignmentRight)
    card.addSubview_(status)
    g_status_fields[pid] = status

    btn = make_button("\u25b6 Launch", target, "toggleProject:")
    btn.setFrame_(Foundation.NSMakeRect(width - 130, 50, 110, 28))
    tag = hash(pid) & 0x7FFFFFFF
    btn.setTag_(tag)
    card.addSubview_(btn)
    g_buttons[pid] = btn
    g_tag_to_pid[tag] = pid

    return card


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
        W, H = 780, 720
        frame = Foundation.NSMakeRect(200, 200, W, H)
        style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable |
                 AppKit.NSWindowStyleMaskMiniaturizable | AppKit.NSWindowStyleMaskResizable)
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False)
        self.window.setTitle_("Interactive Graphics - Chair Model")
        self.window.setBackgroundColor_(BG_CLR)
        self.window.setMinSize_(Foundation.NSMakeSize(600, 400))

        # Scroll view
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, W, H))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        scroll.setDrawsBackground_(False)

        doc_height = 110 + len(PROJECTS) * 95
        doc = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, W - 20, doc_height))

        y = doc_height

        # Header
        y -= 45
        title = make_label("Interactive Computer Graphics", 20, bold=True, color=TEXT_CLR)
        title.setFrame_(Foundation.NSMakeRect(20, y, 500, 30))
        doc.addSubview_(title)

        y -= 20
        sub = make_label("Chair Model \u2022 Metal 3 \u2022 Rust  |  Each project opens its own Metal window",
                         12, color=SUBTEXT_CLR)
        sub.setFrame_(Foundation.NSMakeRect(20, y, 600, 18))
        doc.addSubview_(sub)

        # Global buttons
        y -= 38
        launch_all = make_button("\u25b6 Launch All", self, "launchAll:")
        launch_all.setFrame_(Foundation.NSMakeRect(20, y, 120, 30))
        doc.addSubview_(launch_all)

        stop_all = make_button("\u25a0 Stop All", self, "stopAll:")
        stop_all.setFrame_(Foundation.NSMakeRect(150, y, 120, 30))
        doc.addSubview_(stop_all)

        # Cards
        for pid, name, desc, uses_args, controls in PROJECTS:
            y -= 95
            card = make_card(pid, name, desc, controls, y, W - 60, self)
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
