"""Module files the tests write: a correct one, a broken one and the example that calls it."""

GOOD = '''
from gemini import ops
from gemini.modules import Control, Inlet, Module, Outlet, Output, Parameter
from gemini.physics import energy
from gemini.units.quantities import Efficiency, Power


class ResistanceHeater(Module):
    """Electric resistance heater that delivers the heat asked, up to its capacity."""

    category = "heating"

    def __init__(self):
        super().__init__()
        self.capacity = Parameter(Power)
        self.efficiency = Parameter(Efficiency)
        self.requested = Control(Power)
        self.power_in = Inlet(Power, kind="electricity")
        self.heat_out = Outlet(Power, kind="heat")
        self.duty = Output(Power)

    def forward(self, inputs, inlets, state):
        duty = ops.minimum(inputs["requested"], self.capacity)
        power_in = energy.input_power(duty, self.efficiency)
        return dict(duty=duty), dict(heat_out=duty, power_in=power_in)
'''

BROKEN = '''
from gemini.modules import Module, Output, Parameter


class Wrong(Module):
    """Declares numbers without a unit and a wrong forward."""

    category = "heating"

    def __init__(self):
        super().__init__()
        self.factor = Parameter(float, default=1.0)
        self.value = Output(float)

    def forward(self, inputs):
        return {}, {}
'''

EXAMPLE = {
    "parameters": {
        "capacity": {"value": 2, "unit": "MW"},
        "efficiency": {"value": 0.98, "unit": "-"},
    },
    "controls": {"requested": {"value": 1, "unit": "MW"}},
}
