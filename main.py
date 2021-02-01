import random

from machine import ADC, I2C, Pin
from tm1637 import TM1637

from ssd1306 import SSD1306_I2C

button = Pin(6)
pot = ADC(Pin(26))

FLYING = 0
FUELING = 1
PARKED = 2
MODE = PARKED

STATE_TM =TM1637(clk=Pin(17), dio=Pin(16))
STATE_TM.brightness(7)

class Fuel:
    def __init__(self):
        self.fuel = 9999

        self.gauge = TM1637(clk=Pin(0), dio=Pin(1))
        self.gauge.brightness(6)
        self.gauge.number(self.fuel)


    def tick(self):
        global MODE


        burn_rate = int(10 * (pot.read_u16() / 65535))

        if MODE == FLYING and self.fuel > 0:
            self.fuel -= (1 + burn_rate)
        elif MODE == FUELING:
            self.fuel += 1
        if self.fuel <= 0:
            self.fuel = 0 # in case we burned into the negatives
            MODE = FUELING

        self.gauge.number(self.fuel)

    def add(self, amount):
        self.fuel = min(9999, self.fuel + amount)
fuel = Fuel()


class Starfield:

    WIDTH  = 128
    HEIGHT = 64

    def __init__(self):
        i2c = I2C(0)
        self.oled = SSD1306_I2C(self.WIDTH, self.HEIGHT, i2c)
        self.oled.fill(0)
        self.drops = [[random.randint(0, self.WIDTH), random.randint(-32, 0), random.randint(1, 3), random.randint(1,3)] for _ in range(10)]
        self.text = []

    def tick(self):
        for d in self.drops:
            if d[1] >= 0:
                self.oled.vline(d[0], d[1], d[2], 1)
            d[1] += d[3]
            if d[1] > self.HEIGHT:
                d[1] = random.randint(-3, 0)
                d[0] = random.randint(0, self.WIDTH)
                d[2] = random.randint(0, 3)
        if self.text:
            for idx, txt in enumerate(self.text):
                self.oled.text(txt, 0, idx * 8)
        self.oled.show()
        self.oled.fill(0)
stars = Starfield()


class Mission:

    def __init__(self, distance):
        self.goal_distance = distance
        self.flown = 0
        self.reward = self.goal_distance * (max(.1, min(.5, random.random())))
        self.done = False
        stars.text = ["mission distance", "%d/%d" % (self.flown, self.goal_distance)]

    def tick(self):
        global MODE
        global fuel
        if MODE == FLYING and not self.done:
            distance_mod = 1 + int(2 * (pot.read_u16() / 65535))
            self.flown += distance_mod
            if self.flown >= self.goal_distance:
                self.done = True
                MODE = PARKED
                fuel.add(self.reward)
                stars.text = ["mission complete", "reward %d fuel" % self.reward]
            else:
                stars.text = ["mission distance", "%d/%d" % (self.flown, self.goal_distance)]

# game loop
mission = Mission(random.randint(2000, 5000))
while True:
    pressed = button.value()
    if MODE == FLYING:
        STATE_TM.show(" fly")
        if pressed:
            MODE = FUELING
    elif MODE == FUELING:
        STATE_TM.show("fuel")
        if pressed:
            MODE = FLYING
    elif MODE == PARKED:
        STATE_TM.show("park")
        if pressed:
            mission = Mission(random.randint(2000, 5000))
            MODE = FLYING
    else:
        STATE_TM.show(" err")

    stars.tick()
    fuel.tick()
    mission.tick()