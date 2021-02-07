import random

import framebuf
import utime
from machine import ADC, I2C, Pin
from ssd1306 import SSD1306_I2C

PRESSED = 0

def button_press(b):
    global PRESSED
    if PRESSED == 0 and b.value():
        PRESSED = 1

button = Pin(1, Pin.IN, Pin.PULL_UP)
button.irq(handler=button_press, trigger=Pin.IRQ_RISING)
y_pot = ADC(Pin(26))
x_pot = ADC(Pin(27))

FLYING = 0
FUELING = 1
PARKED = 2
MODE = PARKED
BOOSTING = False

class Starfield:

    WIDTH  = 128
    HEIGHT = 64

    def __init__(self):
        i2c = I2C(0)
        self.oled = SSD1306_I2C(self.WIDTH, self.HEIGHT, i2c)
        self.oled.fill(0)
        self.drops = [[random.randint(0, self.WIDTH), random.randint(-32, 0), random.randint(1, 2), random.randint(1,3)] for _ in range(10)]
        self.text = []

    def tick(self):
        for d in self.drops:
            if d[1] >= 0:
                self.oled.vline(d[0], d[1], d[2], 1)

            if MODE == FLYING:
                d[1] += d[3] * (5 if BOOSTING else 3)
            else:
                d[1] += d[3]

            if d[1] > self.HEIGHT:
                d[1] = random.randint(-3, 0)
                d[0] = random.randint(0, self.WIDTH)
                if MODE == FLYING:
                    d[2] = random.randint(6, 10)
                else:
                    d[2] = random.randint(0, 3)
        if self.text:
            for idx, txt in enumerate(self.text):
                self.oled.text(txt, 0, idx * 8)
        self.oled.show()
        self.oled.fill(0)

    def clampx(self, x):
        return max(0, min(self.WIDTH, x))

    def clampy(self, y):
        return max(16, min(self.HEIGHT, y))
stars = Starfield()


class Fuel:
    MAX_FUEL = 9999

    def __init__(self):
        self.fuel = self.MAX_FUEL

    def tick(self):
        global MODE
        burn_rate = 8 if BOOSTING else 1

        if MODE == FLYING and self.fuel > 0:
            self.fuel -= (1 + burn_rate)
        elif MODE == FUELING:
            self.add(1)
        if self.fuel <= 0:
            self.fuel = 0 # in case we burned into the negatives
            MODE = FUELING

        # fuel graphics
        stars.oled.text("fuel", 0, 7 * 8)
        fuel_width = int((stars.WIDTH - 36) * (self.fuel / self.MAX_FUEL))
        for x in range(1, 5):
            stars.oled.hline(36, (7 * 8) + x, fuel_width, 1)

    def add(self, amount):
        self.fuel = min(self.MAX_FUEL, self.fuel + amount)
fuel = Fuel()


class Pickup:

    def __init__(self, active_deadline=120000):
        self.x = stars.clampx(random.randint(0, 128))
        self.y = stars.clampy(random.randint(0, 64))
        self.active_deadline = utime.ticks_ms() + active_deadline
        self.last_moved = 0

    def tick(self):
        now = utime.ticks_ms()
        if now < self.active_deadline:
            return

        if now > self.last_moved + 500:
            self.x = stars.clampx(self.x + random.choice((-1, 0, 1)))
            self.y = stars.clampy(self.y + random.choice((-1, 0, 1)))
            self.last_moved = now

        self.draw()

    def draw(self):
        pass


class FuelPickup(Pickup):

    def __init__(self):
        super().__init__(active_deadline=120000)
        self.v = random.randint(1000, 4000)

    def draw(self):
        stars.oled.text("F", self.x, self.y)

    def collide(self, ship):
        if utime.ticks_ms() >= self.active_deadline:
            ship.fuel.add(self.v)


class BoostPickup(Pickup):

    def __init__(self):
        super().__init__(active_deadline=60000)
        self.duration = 4000
        self.start_time = None

    def draw(self):
        stars.oled.text("B", self.x, self.y)

    def tick(self):
        if self.start_time and utime.ticks_ms() > self.start_time + self.duration:
            return False

        if not self.start_time:
            super().tick()

        return True

    def collide(self, ship):
        if BOOSTING:
            return False

        now = utime.ticks_ms()
        if now >= self.active_deadline:
            self.start_time = now
            return True
        return False


class Ship:

    def __init__(self, fuel):
        with open("ship3.pbm", "rb") as fp:
            fp.readline()
            fp.readline()
            fp.readline()
            ship_bytes = bytearray(fp.read())
            self.fb = framebuf.FrameBuffer(ship_bytes, 16, 16, framebuf.MONO_HLSB)
            self.y = 20
            self.x = int(stars.WIDTH / 2) - 8
            self.fuel = fuel
            self.move_size = 2

    def tick(self):
        v = x_pot.read_u16()
        if v < 29000:
            self.x = max(0, self.x - self.move_size)
        elif v > 36000:
            self.x = min(stars.WIDTH - 16, self.x + self.move_size)

        yv = y_pot.read_u16()
        if yv < 29000:
            self.y = max(0, self.y - self.move_size)
        elif yv > 36000:
            self.y = min(48, self.y + self.move_size)

        stars.oled.blit(self.fb, self.x, self.y)

    def collides(self, pickup):
        if (self.x <= pickup.x < self.x + 16
        and self.y <= pickup.y < self.y + 16):
            return True
        return False


class Mission:

    def __init__(self, distance):
        self.goal_distance = distance
        self.flown = 0
        self.reward = int(self.goal_distance * (max(.1, min(.5, random.random()))))
        self.done = False
        self.draw_mission()

    def tick(self):
        global MODE
        global fuel
        if MODE == FLYING and not self.done:
            distance_mod = 4 if BOOSTING else 1
            self.flown += distance_mod
            if self.flown >= self.goal_distance:
                self.done = True
                MODE = PARKED
                fuel.add(self.reward)
                stars.text = ["Mission complete!", "Got %d fuel!" % self.reward]
            else:
                self.draw_mission()

    def draw_mission(self):
        if MODE != PARKED:
            stars.text = ["Mission time!"]
        else:
            stars.text = ["Accept mission?"]
        line_len = int(stars.WIDTH * self.flown/self.goal_distance)
        for x in range(4):
            stars.oled.hline(0, 12 + x, line_len, 1)

stars.oled.fill(0)
stars.oled.show()

# game loop
mission = Mission(random.randint(2000, 5000))
ship = Ship(fuel)
fuelPickup = FuelPickup()
boostPickup = BoostPickup()
while True:
    if MODE == FLYING:
        if PRESSED:
            MODE = FUELING
            PRESSED = 0
    elif MODE == FUELING:
        if PRESSED:
            MODE = FLYING
            PRESSED = 0
    elif MODE == PARKED:
        if PRESSED:
            mission = Mission(random.randint(2000, 5000))
            MODE = FLYING
            PRESSED = 0

    stars.tick()
    ship.tick()
    fuel.tick()
    mission.tick()
    fuelPickup.tick()
    if not boostPickup.tick():
        del boostPickup
        BOOSTING = False
        boostPickup = BoostPickup()

    if ship.collides(fuelPickup):
        fuelPickup.collide(ship)
        del fuelPickup
        fuelPickup = FuelPickup()

    if ship.collides(boostPickup) and boostPickup.collide(ship):
        BOOSTING = True
