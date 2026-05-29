#!/usr/bin/env python3
"""
Project 9 - Bedroom Environment Map with floating control panel.
Launches the Metal renderer and overlays a native macOS control panel.
Supports switching between Shadow Mapping and Ray Traced Shadows.
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

# Key codes
KEY_1, KEY_2, KEY_3, KEY_4 = 18, 19, 20, 21
KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = 126, 125, 123, 124
KEY_P = 35   # Toggle Blinn-Phong / PBR
KEY_M = 46   # Toggle metallic

# Available scenes
BIN_DIR = os.path.join(ROOT_DIR, "target", "debug")

SCENES = {
    "bedroom": {
        "name": "Bedroom Env Map",
        "cmd": [os.path.join(BIN_DIR, "proj-9-bedroom-envmap")],
        "desc": "Shadow Mapping + Env Map + Textures",
        "shadow": "Shadow Mapping (Depth)",
        "has_reflect": True,
    },
    "rt-shadows": {
        "name": "Ray Traced Shadows",
        "cmd": [os.path.join(BIN_DIR, "proj-7-ray-traced-shadows"), CHAIR_OBJ],
        "desc": "Ray Traced Shadows + Textures",
        "shadow": "Ray Traced (Metal RT)",
        "has_reflect": False,
    },
    "rt-reflections": {
        "name": "Ray Traced Reflections",
        "cmd": [os.path.join(BIN_DIR, "proj-6-ray-traced-reflections"), CHAIR_OBJ],
        "desc": "Multi-bounce Ray Traced Reflections",
        "shadow": "N/A",
        "has_reflect": False,
    },
    "shadow-map": {
        "name": "Shadow Mapping",
        "cmd": [os.path.join(BIN_DIR, "proj-7-shadow-mapping"), CHAIR_OBJ],
        "desc": "Depth-based Shadow Mapping + Textures",
        "shadow": "Shadow Mapping (Depth)",
        "has_reflect": False,
    },
    "env-map": {
        "name": "Environment Mapping",
        "cmd": [os.path.join(BIN_DIR, "proj-6-environment-mapping"), CHAIR_OBJ],
        "desc": "Skybox + Mirror Reflections",
        "shadow": "N/A",
        "has_reflect": False,
    },
}

# Colors
BG = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.10, 0.16, 0.92)
TEXT = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.88, 0.96, 1.0)
SUBTEXT = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.60, 0.63, 0.73, 1.0)
TEAL = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.58, 0.89, 0.83, 1.0)
YELLOW = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.98, 0.90, 0.53, 1.0)
MAUVE = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.62, 0.95, 1.0)
GREEN = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.65, 0.89, 0.63, 1.0)
RED = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.55, 0.66, 1.0)
BLUE = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.54, 0.68, 0.99, 1.0)
SECTION_BG = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.14, 0.14, 0.20, 0.95)
ACTIVE_BG = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.35, 0.20, 1.0)

g_proc = None
g_current_scene = "bedroom"
g_state = {
    "reflectivity": 0.15,
    "shading": "All",
    "shader": "Blinn-Phong",
    "shader_mode": 0,
    "roughness": 0.5,
    "metallic": False,
}
g_status_label = None
g_reflect_label = None
g_shadow_label = None
g_scene_label = None
g_shader_label = None
g_rough_label = None
g_metal_label = None
g_scene_buttons = {}
g_reflect_section = None
g_pbr_section = None


def send_key(keycode):
    """Send keystroke to the renderer process via AppleScript System Events."""
    global g_proc
    if g_proc is None or g_proc.poll() is not None:
        return

    # Map keycode to character for AppleScript
    key_char_map = {
        18: "1", 19: "2", 20: "3", 21: "4",
        35: "p", 46: "m",
    }
    # Map keycode to key code for arrow keys (use key code, not keystroke)
    key_code_arrows = {126, 125, 123, 124}

    # Get process name from command
    proc_name = os.path.basename(g_proc.args[0]) if g_proc.args else ""

    if keycode in key_char_map:
        char = key_char_map[keycode]
        script = f'''
            tell application "System Events"
                tell process "{proc_name}"
                    keystroke "{char}"
                end tell
            end tell
        '''
    elif keycode in key_code_arrows:
        script = f'''
            tell application "System Events"
                tell process "{proc_name}"
                    key code {keycode}
                end tell
            end tell
        '''
    else:
        return

    subprocess.Popen(["osascript", "-e", script],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch_scene(scene_id):
    global g_proc, g_current_scene
    # Stop current
    if g_proc and g_proc.poll() is None:
        g_proc.terminate()
        try:
            g_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            g_proc.kill()
        g_proc = None

    g_current_scene = scene_id
    scene = SCENES[scene_id]

    env = os.environ.copy()
    env["PATH"] = os.path.expanduser("~/.cargo/bin") + ":" + env.get("PATH", "")
    g_proc = subprocess.Popen(scene["cmd"], cwd=ROOT_DIR, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Update UI
    if g_scene_label:
        g_scene_label.setStringValue_(f"Active: {scene['name']}")
    if g_shadow_label:
        g_shadow_label.setStringValue_(scene["shadow"])
    if g_status_label:
        g_status_label.setStringValue_(f"Running: {scene['desc']}")

    # Highlight active button
    for sid, btn in g_scene_buttons.items():
        if sid == scene_id:
            btn.setFont_(AppKit.NSFont.boldSystemFontOfSize_(10))
        else:
            btn.setFont_(AppKit.NSFont.systemFontOfSize_(10))

    # Show/hide reflectivity
    if g_reflect_section:
        g_reflect_section.setHidden_(not scene["has_reflect"])


def update_labels():
    pass  # Status updated in launch_scene


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


# Scene tag mapping
SCENE_TAGS = {}
_next_tag = [1000]
def scene_tag(scene_id):
    if scene_id not in SCENE_TAGS:
        SCENE_TAGS[scene_id] = _next_tag[0]
        _next_tag[0] += 1
    return SCENE_TAGS[scene_id]

TAG_TO_SCENE = {}


class PanelDelegate(AppKit.NSObject):
    def applicationDidFinishLaunching_(self, notification):
        global g_status_label, g_reflect_label, g_shadow_label, g_scene_label, g_reflect_section

        PW, PH = 270, 720
        frame = Foundation.NSMakeRect(50, 150, PW, PH)
        style = (AppKit.NSWindowStyleMaskTitled |
                 AppKit.NSWindowStyleMaskClosable |
                 AppKit.NSWindowStyleMaskUtilityWindow |
                 AppKit.NSWindowStyleMaskNonactivatingPanel)
        self.panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False)
        self.panel.setTitle_("Scene Controls")
        self.panel.setBackgroundColor_(BG)
        self.panel.setFloatingPanel_(True)
        self.panel.setBecomesKeyOnlyIfNeeded_(True)
        self.panel.setLevel_(AppKit.NSFloatingWindowLevel)
        self.panel.setAlphaValue_(0.95)

        content = self.panel.contentView()
        y = PH - 10

        # === Title ===
        y -= 22
        t = make_label("Chair Scene Controller", 14, bold=True, color=TEXT)
        t.setFrame_(Foundation.NSMakeRect(10, y, 250, 20))
        content.addSubview_(t)

        y -= 18
        g_status_label = make_label("Starting...", 9, color=TEAL)
        g_status_label.setFrame_(Foundation.NSMakeRect(10, y, 250, 14))
        content.addSubview_(g_status_label)

        # === Rendering Technique ===
        y -= 26
        sl = make_label("Rendering Technique", 11, bold=True, color=MAUVE)
        sl.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(sl)

        y -= 4
        scene_order = [
            ("bedroom",         "\u2302 Bedroom Env Map"),
            ("shadow-map",      "\u2600 Shadow Mapping"),
            ("rt-shadows",      "\u26a1 Ray Traced Shadows"),
            ("env-map",         "\u2728 Environment Map"),
            ("rt-reflections",  "\u2b50 RT Reflections"),
        ]
        for scene_id, label in scene_order:
            y -= 28
            tag = scene_tag(scene_id)
            TAG_TO_SCENE[tag] = scene_id
            btn = make_btn(label, self, "switchScene:", tag, 240)
            btn.setFrame_(Foundation.NSMakeRect(10, y, 240, 26))
            content.addSubview_(btn)
            g_scene_buttons[scene_id] = btn

        # Active scene label
        y -= 20
        g_scene_label = make_label("Active: Bedroom Env Map", 10, bold=True, color=GREEN)
        g_scene_label.setFrame_(Foundation.NSMakeRect(10, y, 240, 16))
        content.addSubview_(g_scene_label)

        # === Shading Mode ===
        y -= 28
        sl2 = make_label("Shading Mode", 11, bold=True, color=YELLOW)
        sl2.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(sl2)

        y -= 28
        modes = [("Ambient", KEY_1), ("Diffuse", KEY_2),
                 ("Specular", KEY_3), ("All", KEY_4)]
        x = 10
        for label, keycode in modes:
            tag = keycode * 100 + 1
            btn = make_btn(label, self, "shadingMode:", tag, 55)
            btn.setFrame_(Foundation.NSMakeRect(x, y, 55, 24))
            content.addSubview_(btn)
            x += 59

        # === Shader Model ===
        y -= 30
        sml = make_label("Shader Model", 11, bold=True, color=YELLOW)
        sml.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(sml)

        y -= 28
        btn_bp = make_btn("Blinn-Phong", self, "shaderBlinnPhong:", 0, 115)
        btn_bp.setFrame_(Foundation.NSMakeRect(10, y, 115, 24))
        btn_bp.setFont_(AppKit.NSFont.boldSystemFontOfSize_(10))
        content.addSubview_(btn_bp)

        btn_pbr = make_btn("PBR (Cook-Torrance)", self, "shaderPBR:", 0, 130)
        btn_pbr.setFrame_(Foundation.NSMakeRect(130, y, 130, 24))
        content.addSubview_(btn_pbr)

        y -= 20
        g_shader_label = make_label("Active: Blinn-Phong", 10, bold=True, color=GREEN)
        g_shader_label.setFrame_(Foundation.NSMakeRect(10, y, 240, 16))
        content.addSubview_(g_shader_label)

        # === PBR Parameters (visible when PBR active) ===
        y -= 4
        g_pbr_section = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, y - 62, PW, 62))
        content.addSubview_(g_pbr_section)
        g_pbr_section.setHidden_(True)

        rgl = make_label("Roughness", 10, bold=True, color=TEAL)
        rgl.setFrame_(Foundation.NSMakeRect(10, 38, 80, 14))
        g_pbr_section.addSubview_(rgl)

        g_rough_label = make_label("50%", 10, bold=True, color=GREEN)
        g_rough_label.setFrame_(Foundation.NSMakeRect(115, 38, 40, 14))
        g_pbr_section.addSubview_(g_rough_label)

        btn_rg_minus = make_btn("\u25c0", self, "roughDown:", 0, 30)
        btn_rg_minus.setFrame_(Foundation.NSMakeRect(85, 34, 30, 22))
        g_pbr_section.addSubview_(btn_rg_minus)

        btn_rg_plus = make_btn("\u25b6", self, "roughUp:", 0, 30)
        btn_rg_plus.setFrame_(Foundation.NSMakeRect(155, 34, 30, 22))
        g_pbr_section.addSubview_(btn_rg_plus)

        mtl = make_label("Metallic", 10, bold=True, color=TEAL)
        mtl.setFrame_(Foundation.NSMakeRect(10, 10, 80, 14))
        g_pbr_section.addSubview_(mtl)

        g_metal_label = make_label("Off", 10, bold=True, color=RED)
        g_metal_label.setFrame_(Foundation.NSMakeRect(115, 10, 40, 14))
        g_pbr_section.addSubview_(g_metal_label)

        btn_metal = make_btn("Toggle", self, "toggleMetal:", 0, 55)
        btn_metal.setFrame_(Foundation.NSMakeRect(155, 6, 55, 22))
        g_pbr_section.addSubview_(btn_metal)

        y -= 66

        # === Reflectivity (only for bedroom scene) ===
        y -= 4
        g_reflect_section = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, y - 24, PW, 56))
        content.addSubview_(g_reflect_section)

        rl = make_label("Reflectivity", 11, bold=True, color=YELLOW)
        rl.setFrame_(Foundation.NSMakeRect(10, 32, 200, 16))
        g_reflect_section.addSubview_(rl)

        g_reflect_label = make_label(f"{g_state['reflectivity']:.0%}", 12, bold=True, color=GREEN)
        g_reflect_label.setFrame_(Foundation.NSMakeRect(110, 4, 50, 20))
        g_reflect_section.addSubview_(g_reflect_label)

        btn_minus = make_btn("\u25bc Less", self, "reflectDown:", 0, 55)
        btn_minus.setFrame_(Foundation.NSMakeRect(10, 4, 55, 24))
        g_reflect_section.addSubview_(btn_minus)

        btn_plus = make_btn("\u25b2 More", self, "reflectUp:", 0, 55)
        btn_plus.setFrame_(Foundation.NSMakeRect(170, 4, 55, 24))
        g_reflect_section.addSubview_(btn_plus)

        y -= 60

        # === Camera & Light ===
        y -= 8
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
            d.setFrame_(Foundation.NSMakeRect(105, y, 155, 14))
            content.addSubview_(d)

        # === Rendering Info ===
        y -= 26
        il = make_label("Rendering Info", 11, bold=True, color=YELLOW)
        il.setFrame_(Foundation.NSMakeRect(10, y, 200, 16))
        content.addSubview_(il)

        y -= 18
        k = make_label("Shader", 10, bold=True, color=TEAL)
        k.setFrame_(Foundation.NSMakeRect(10, y, 70, 14))
        content.addSubview_(k)
        v = make_label("Blinn-Phong", 10, color=SUBTEXT)
        v.setFrame_(Foundation.NSMakeRect(85, y, 165, 14))
        content.addSubview_(v)

        y -= 18
        k2 = make_label("Shadows", 10, bold=True, color=TEAL)
        k2.setFrame_(Foundation.NSMakeRect(10, y, 70, 14))
        content.addSubview_(k2)
        g_shadow_label = make_label("Shadow Mapping (Depth)", 10, color=SUBTEXT)
        g_shadow_label.setFrame_(Foundation.NSMakeRect(85, y, 165, 14))
        content.addSubview_(g_shadow_label)

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

        # Poll timer
        Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "pollProcess:", None, True)

        # Launch default scene
        launch_scene("bedroom")

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True

    def applicationWillTerminate_(self, notification):
        global g_proc
        if g_proc and g_proc.poll() is None:
            g_proc.terminate()

    def switchScene_(self, sender):
        scene_id = TAG_TO_SCENE.get(sender.tag())
        if scene_id:
            launch_scene(scene_id)

    def shadingMode_(self, sender):
        keycode = sender.tag() // 100
        send_key(keycode)
        names = {KEY_1: "Ambient", KEY_2: "Diffuse", KEY_3: "Specular", KEY_4: "All"}
        g_state["shading"] = names.get(keycode, "All")

    def shaderBlinnPhong_(self, sender):
        if g_state.get("shader_mode", 0) == 0:
            return  # already Blinn-Phong
        send_key(KEY_P)
        g_state["shader_mode"] = 0
        if g_shader_label:
            g_shader_label.setStringValue_("Active: Blinn-Phong")
        if g_pbr_section:
            g_pbr_section.setHidden_(True)

    def shaderPBR_(self, sender):
        if g_state.get("shader_mode", 0) == 1:
            return  # already PBR
        send_key(KEY_P)
        g_state["shader_mode"] = 1
        if g_shader_label:
            g_shader_label.setStringValue_("Active: PBR (Cook-Torrance)")
        if g_pbr_section:
            g_pbr_section.setHidden_(False)

    def roughDown_(self, sender):
        send_key(KEY_LEFT)
        g_state["roughness"] = max(0.05, g_state.get("roughness", 0.5) - 0.05)
        if g_rough_label:
            g_rough_label.setStringValue_(f"{g_state['roughness']:.0%}")

    def roughUp_(self, sender):
        send_key(KEY_RIGHT)
        g_state["roughness"] = min(1.0, g_state.get("roughness", 0.5) + 0.05)
        if g_rough_label:
            g_rough_label.setStringValue_(f"{g_state['roughness']:.0%}")

    def toggleMetal_(self, sender):
        send_key(KEY_M)
        is_metal = g_state.get("metallic", False)
        g_state["metallic"] = not is_metal
        if g_metal_label:
            if g_state["metallic"]:
                g_metal_label.setStringValue_("On")
                g_metal_label.setTextColor_(GREEN)
            else:
                g_metal_label.setStringValue_("Off")
                g_metal_label.setTextColor_(RED)

    def reflectUp_(self, sender):
        send_key(KEY_UP)
        g_state["reflectivity"] = min(1.0, g_state["reflectivity"] + 0.05)
        if g_reflect_label:
            g_reflect_label.setStringValue_(f"{g_state['reflectivity']:.0%}")

    def reflectDown_(self, sender):
        send_key(KEY_DOWN)
        g_state["reflectivity"] = max(0.0, g_state["reflectivity"] - 0.05)
        if g_reflect_label:
            g_reflect_label.setStringValue_(f"{g_state['reflectivity']:.0%}")

    def pollProcess_(self, timer):
        global g_proc
        if g_proc and g_proc.poll() is not None:
            g_proc = None
            # Don't quit - let user pick another scene
            if g_scene_label:
                g_scene_label.setStringValue_("Active: None (pick a scene)")
            if g_status_label:
                g_status_label.setStringValue_("Renderer stopped")


def main():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    delegate = PanelDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
