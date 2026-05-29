#!/usr/bin/env python3
"""
Project 9 - Bedroom Environment Map with floating control panel.
Launches the Metal renderer and overlays a native macOS control panel.
"""

import subprocess
import os
import time
import Quartz

import AppKit
import Foundation
from objc import super  # noqa

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CARGO = os.path.expanduser("~/.cargo/bin/cargo")

# Key codes
KEY_1, KEY_2, KEY_3, KEY_4 = 18, 19, 20, 21
KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = 126, 125, 123, 124
KEY_P = 35

# Colors
BG = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.10, 0.16, 0.92)
TEXT = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.88, 0.96, 1.0)
SUBTEXT = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.60, 0.63, 0.73, 1.0)
TEAL = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.58, 0.89, 0.83, 1.0)
YELLOW = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.98, 0.90, 0.53, 1.0)
MAUVE = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.62, 0.95, 1.0)
GREEN = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.89, 0.63, 1.0)
SECTION_BG = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.14, 0.14, 0.20, 0.95)

g_proc = None
g_state = {
    "reflectivity": 0.15,
    "shading": "All",
    "model": "Blinn-Phong",
}
g_status_label = None
g_reflect_label = None


def send_key(keycode):
    global g_proc
    if g_proc is None or g_proc.poll() is not None:
        return
    ev_down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    ev_up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPostToPid(g_proc.pid, ev_down)
    Quartz.CGEventPostToPid(g_proc.pid, ev_up)


def update_labels():
    if g_status_label:
        g_status_label.setStringValue_(
            f"Shading: {g_state['shading']}  |  Reflectivity: {g_state['reflectivity']:.0%}"
        )


def make_label(text, size, bold=False, color=TEXT):
    lbl = AppKit.NSTextField.labelWithString_(text)
    lbl.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size))
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setTextColor_(color)
    return lbl


def make_btn(title, target, action, tag=0, width=70):
    btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, width, 24))
    btn.setTitle_(title)
    btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
    btn.setTarget_(target)
    btn.setAction_(action)
    btn.setTag_(tag)
    btn.setWantsLayer_(True)
    btn.setFont_(AppKit.NSFont.systemFontOfSize_(10))
    return btn


def make_section(title, y, width):
    view = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, width, 1))
    view.setWantsLayer_(True)
    view.layer().setBackgroundColor_(SECTION_BG.CGColor())
    view.layer().setCornerRadius_(6)
    lbl = make_label(title, 11, bold=True, color=MAUVE)
    lbl.setFrame_(Foundation.NSMakeRect(8, 0, width - 16, 16))
    return view, lbl


class PanelDelegate(AppKit.NSObject):
    def applicationDidFinishLaunching_(self, notification):
        global g_proc, g_status_label, g_reflect_label

        # Launch proj-9
        env = os.environ.copy()
        env["PATH"] = os.path.expanduser("~/.cargo/bin") + ":" + env.get("PATH", "")
        g_proc = subprocess.Popen(
            [CARGO, "run", "-p", "proj-9-bedroom-envmap"],
            cwd=ROOT_DIR, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Create floating panel
        PW, PH = 260, 420
        frame = Foundation.NSMakeRect(50, 200, PW, PH)
        # Use NSPanel for floating utility window
        style = (AppKit.NSWindowStyleMaskTitled |
                 AppKit.NSWindowStyleMaskClosable |
                 AppKit.NSWindowStyleMaskUtilityWindow |
                 AppKit.NSWindowStyleMaskNonactivatingPanel)
        self.panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False)
        self.panel.setTitle_("Controls")
        self.panel.setBackgroundColor_(BG)
        self.panel.setFloatingPanel_(True)
        self.panel.setBecomesKeyOnlyIfNeeded_(True)
        self.panel.setLevel_(AppKit.NSFloatingWindowLevel)
        self.panel.setAlphaValue_(0.95)

        content = self.panel.contentView()
        y = PH - 10

        # Title
        y -= 22
        t = make_label("Project 9 - Bedroom Scene", 13, bold=True, color=TEXT)
        t.setFrame_(Foundation.NSMakeRect(10, y, 240, 20))
        content.addSubview_(t)

        y -= 16
        s = make_label("Chair + Texture + Shadow + Env Map", 9, color=SUBTEXT)
        s.setFrame_(Foundation.NSMakeRect(10, y, 240, 14))
        content.addSubview_(s)

        # Status
        y -= 22
        g_status_label = make_label("", 10, color=TEAL)
        g_status_label.setFrame_(Foundation.NSMakeRect(10, y, 240, 16))
        content.addSubview_(g_status_label)
        update_labels()

        # === Shading Mode ===
        y -= 28
        sl = make_label("Shading Mode", 11, bold=True, color=YELLOW)
        sl.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(sl)

        y -= 28
        modes = [("Ambient", KEY_1, "ambient"), ("Diffuse", KEY_2, "diffuse"),
                 ("Specular", KEY_3, "specular"), ("All", KEY_4, "all")]
        x = 10
        for label, keycode, mode_name in modes:
            tag = keycode * 100 + 1
            btn = make_btn(label, self, "shadingMode:", tag, 55)
            btn.setFrame_(Foundation.NSMakeRect(x, y, 55, 24))
            content.addSubview_(btn)
            x += 59

        # === Reflectivity ===
        y -= 36
        rl = make_label("Reflectivity", 11, bold=True, color=YELLOW)
        rl.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(rl)

        y -= 28
        g_reflect_label = make_label(f"{g_state['reflectivity']:.0%}", 12, bold=True, color=GREEN)
        g_reflect_label.setFrame_(Foundation.NSMakeRect(110, y, 50, 20))
        content.addSubview_(g_reflect_label)

        btn_minus = make_btn("\u25bc Less", self, "reflectDown:", 0, 55)
        btn_minus.setFrame_(Foundation.NSMakeRect(10, y, 55, 24))
        content.addSubview_(btn_minus)

        btn_plus = make_btn("\u25b2 More", self, "reflectUp:", 0, 55)
        btn_plus.setFrame_(Foundation.NSMakeRect(170, y, 55, 24))
        content.addSubview_(btn_plus)

        # === Camera Tips ===
        y -= 36
        cl = make_label("Camera & Light", 11, bold=True, color=YELLOW)
        cl.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(cl)

        tips = [
            ("Mouse Drag", "Rotate camera"),
            ("Ctrl + Drag", "Move light / shadow"),
            ("Scroll", "Zoom in/out"),
        ]
        for tip_key, tip_desc in tips:
            y -= 18
            k = make_label(tip_key, 10, bold=True, color=TEAL)
            k.setFrame_(Foundation.NSMakeRect(10, y, 90, 14))
            content.addSubview_(k)
            d = make_label(tip_desc, 10, color=SUBTEXT)
            d.setFrame_(Foundation.NSMakeRect(105, y, 145, 14))
            content.addSubview_(d)

        # === Info ===
        y -= 30
        il = make_label("Rendering", 11, bold=True, color=YELLOW)
        il.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(il)

        info_items = [
            ("Shader", "Blinn-Phong"),
            ("Shadows", "Shadow Mapping (Depth)"),
            ("Env Map", "Bedroom Cubemap"),
            ("Textures", "Diffuse + Specular"),
        ]
        for info_key, info_val in info_items:
            y -= 18
            k = make_label(info_key, 10, bold=True, color=TEAL)
            k.setFrame_(Foundation.NSMakeRect(10, y, 70, 14))
            content.addSubview_(k)
            v = make_label(info_val, 10, color=SUBTEXT)
            v.setFrame_(Foundation.NSMakeRect(85, y, 165, 14))
            content.addSubview_(v)

        self.panel.makeKeyAndOrderFront_(None)

        # Menu
        menubar = AppKit.NSMenu.new()
        app_menu_item = AppKit.NSMenuItem.new()
        menubar.addItem_(app_menu_item)
        app_menu = AppKit.NSMenu.new()
        app_menu.addItem_(
            AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "terminate:", "q"))
        app_menu_item.setSubmenu_(app_menu)
        AppKit.NSApp.setMainMenu_(menubar)

        # Poll for proj-9 exit
        Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "pollProcess:", None, True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True

    def applicationWillTerminate_(self, notification):
        global g_proc
        if g_proc and g_proc.poll() is None:
            g_proc.terminate()

    def shadingMode_(self, sender):
        tag = sender.tag()
        keycode = tag // 100
        send_key(keycode)
        names = {KEY_1: "Ambient", KEY_2: "Diffuse", KEY_3: "Specular", KEY_4: "All"}
        g_state["shading"] = names.get(keycode, "All")
        update_labels()

    def reflectUp_(self, sender):
        send_key(KEY_UP)
        g_state["reflectivity"] = min(1.0, g_state["reflectivity"] + 0.05)
        if g_reflect_label:
            g_reflect_label.setStringValue_(f"{g_state['reflectivity']:.0%}")
        update_labels()

    def reflectDown_(self, sender):
        send_key(KEY_DOWN)
        g_state["reflectivity"] = max(0.0, g_state["reflectivity"] - 0.05)
        if g_reflect_label:
            g_reflect_label.setStringValue_(f"{g_state['reflectivity']:.0%}")
        update_labels()

    def pollProcess_(self, timer):
        global g_proc
        if g_proc and g_proc.poll() is not None:
            g_proc = None
            AppKit.NSApp.terminate_(None)


def main():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    delegate = PanelDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
