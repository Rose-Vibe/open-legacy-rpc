from .scenarios import SCENARIOS, get_scenario


GENERATORS = {name: lambda mode, _n=name: [get_scenario(_n)] for name in SCENARIOS}
