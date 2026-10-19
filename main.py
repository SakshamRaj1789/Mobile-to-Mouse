"""PhoneMouse - Android app (Kivy, pure Python).

Gyroscope moves the cursor, left/right pads click, centre strip scrolls.
"""
import socket
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from plyer import gyroscope

TCP_PORT = 5005
DISCOVERY_PORT = 5006
DEADZONE = 0.03          # rad/s ignored (kills hand jitter / drift)
SCROLL_DIR = -1          # flip to +1 if scrolling feels inverted
SCROLL_GAIN = 1 / dp(18) # one wheel notch per ~18dp of finger travel
Window.clearcolor = (0.08, 0.09, 0.11, 1)


class Link:
    sock = None

    def find_pc(self, timeout=2.5):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        try:
            s.sendto(b"PHONEMOUSE?", ("255.255.255.255", DISCOVERY_PORT))
            _, addr = s.recvfrom(256)
            return addr[0]
        except OSError:
            return None
        finally:
            s.close()

    def connect(self, host, pin):
        s = socket.create_connection((host, TCP_PORT), timeout=4)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.sendall(f"HELLO {pin}\n".encode())
        if s.makefile("r").readline().strip() != "OK":
            s.close()
            raise ConnectionError("Wrong PIN")
        s.settimeout(1.0)
        self.sock = s

    def send(self, msg):
        if self.sock:
            try:
                self.sock.sendall((msg + "\n").encode())
            except OSError:
                self.close()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None


class Pad(Widget):
    """Click pad: press = button down, release = button up (so drag works)."""

    def __init__(self, text, code, color, link, **kw):
        super().__init__(**kw)
        self.code, self.color, self.link, self.down = code, color, link, False
        self.label = Label(text=text, font_size=dp(22))
        self.add_widget(self.label)
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            r, g, b = self.color
            k = 1.5 if self.down else 1.0
            Color(min(r * k, 1), min(g * k, 1), min(b * k, 1), 1)
            RoundedRectangle(pos=(self.x + dp(4), self.y + dp(4)),
                             size=(self.width - dp(8), self.height - dp(8)),
                             radius=[dp(18)])
        self.label.center = self.center

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self.down = True
            self.redraw()
            self.link.send(f"D {self.code}")
            return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.down = False
            self.redraw()
            self.link.send(f"U {self.code}")
            return True


class ScrollStrip(Widget):
    """Vertical scroll bar in the middle: drag up/down to scroll."""

    def __init__(self, link, **kw):
        super().__init__(**kw)
        self.link, self.offset = link, 0.0
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(0.16, 0.17, 0.20, 1)
            RoundedRectangle(pos=(self.x + dp(4), self.y + dp(4)),
                             size=(self.width - dp(8), self.height - dp(8)),
                             radius=[dp(18)])
            Color(0.5, 0.52, 0.6, 1)
            spacing = dp(28)
            yy = self.y + (self.offset % spacing)
            while yy < self.top - dp(10):
                if yy > self.y + dp(10):
                    Line(points=[self.center_x - dp(10), yy, self.center_x + dp(10), yy],
                         width=dp(1.5))
                yy += spacing

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.offset += touch.dy
            self.link.send(f"S {SCROLL_DIR * touch.dy * SCROLL_GAIN:.2f}")
            self.redraw()
            return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True


class PhoneMouseApp(App):
    def build(self):
        self.title = "PhoneMouse"
        self.link = Link()
        self.sm = ScreenManager(transition=NoTransition())
        self.sm.add_widget(self.build_connect())
        self.sm.add_widget(self.build_control())
        Clock.schedule_interval(self.tick, 1 / 60)
        return self.sm

    # ---------- connect screen ----------
    def build_connect(self):
        scr = Screen(name="connect")
        box = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        box.add_widget(Label(text="PhoneMouse", font_size=dp(30)))
        self.status = Label(text="Run server.py on your PC, then connect.",
                            size_hint_y=None, height=dp(40))
        box.add_widget(self.status)
        self.host = TextInput(hint_text="PC IP address", multiline=False,
                              size_hint_y=None, height=dp(48))
        self.pin = TextInput(hint_text="PIN shown on the PC", multiline=False,
                             input_filter="int", size_hint_y=None, height=dp(48))
        box.add_widget(self.host)
        box.add_widget(self.pin)
        for text, cb in (("Find PC on Wi-Fi", self.find_pc),
                         ("USB cable (127.0.0.1)", self.use_usb),
                         ("Connect", self.do_connect)):
            box.add_widget(Button(text=text, on_release=cb,
                                  size_hint_y=None, height=dp(52)))
        scr.add_widget(box)
        return scr

    def set_status(self, text):
        self.status.text = text

    def find_pc(self, *_):
        self.set_status("Searching...")

        def work():
            ip = self.link.find_pc()
            Clock.schedule_once(lambda dt: self.found(ip))
        threading.Thread(target=work, daemon=True).start()

    def found(self, ip):
        if ip:
            self.host.text = ip
            self.set_status(f"Found PC at {ip} - enter PIN")
        else:
            self.set_status("No PC found - type its IP")

    def use_usb(self, *_):
        self.host.text = "127.0.0.1"
        self.set_status("USB mode - run server with --usb, enter PIN")

    def do_connect(self, *_):
        host, pin = self.host.text.strip(), self.pin.text.strip()
        self.set_status("Connecting...")

        def work():
            try:
                self.link.connect(host, pin)
                err = None
            except Exception as e:
                err = str(e) or "Could not connect"
            Clock.schedule_once(lambda dt: self.after_connect(err))
        threading.Thread(target=work, daemon=True).start()

    def after_connect(self, err):
        if err:
            self.set_status(err)
            return
        try:
            gyroscope.enable()
        except Exception:
            self.set_status("No gyroscope available on this device")
            self.link.close()
            return
        self.sm.current = "control"

    # ---------- control screen ----------
    def build_control(self):
        scr = Screen(name="control")
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.gyro_btn = ToggleButton(text="Gyro ON", state="down")
        self.gyro_btn.bind(state=lambda b, s: setattr(
            b, "text", "Gyro ON" if s == "down" else "Gyro OFF"))
        top.add_widget(self.gyro_btn)
        top.add_widget(Button(text="Disconnect",
                              on_release=lambda *_: self.disconnect("Disconnected")))
        root.add_widget(top)

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(Label(text="Speed", size_hint_x=0.2))
        self.speed = Slider(min=200, max=3000, value=1200)
        row.add_widget(self.speed)
        root.add_widget(row)

        pads = BoxLayout(spacing=dp(2))
        pads.add_widget(Pad("LEFT", "L", (0.20, 0.40, 0.75), self.link, size_hint_x=0.38))
        pads.add_widget(ScrollStrip(self.link, size_hint_x=0.24))
        pads.add_widget(Pad("RIGHT", "R", (0.55, 0.30, 0.65), self.link, size_hint_x=0.38))
        root.add_widget(pads)
        scr.add_widget(root)
        return scr

    def disconnect(self, msg):
        self.link.close()
        try:
            gyroscope.disable()
        except Exception:
            pass
        self.set_status(msg)
        self.sm.current = "connect"

    # ---------- gyro -> cursor ----------
    @staticmethod
    def dead(v):
        return 0.0 if abs(v) < DEADZONE else v

    def tick(self, dt):
        if self.sm.current != "control":
            return
        if not self.link.sock:
            self.disconnect("Connection lost")
            return
        if self.gyro_btn.state != "down":
            return
        try:
            v = gyroscope.rotation  # angular velocity (x, y, z) in rad/s
        except Exception:
            return
        if not v or None in v:
            return
        gx, gy, _gz = (self.dead(a) for a in v)
        dt = min(dt, 0.05)
        # Phone held upright, screen facing you:
        #   turn left/right (rotation about Y) -> cursor X
        #   tilt up/down   (rotation about X) -> cursor Y
        dx = -gy * dt * self.speed.value
        dy = gx * dt * self.speed.value
        if dx or dy:
            self.link.send(f"M {dx:.2f} {dy:.2f}")

    def on_pause(self):
        return True

    def on_resume(self):
        if self.sm.current == "control":
            try:
                gyroscope.enable()
            except Exception:
                pass


if __name__ == "__main__":
    PhoneMouseApp().run()
