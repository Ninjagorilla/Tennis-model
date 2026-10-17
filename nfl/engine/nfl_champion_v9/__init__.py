"""NFL v9.1 integrated research engine.

`predict` remains the backwards-compatible explicit-input TD kernel.
Use nfl_champion_v9.engine.run for integrated forecasts.
"""
from .td import TDRequest, predict, VERSION
__version__ = "9.1.0"
__all__ = ["TDRequest", "predict", "VERSION", "__version__"]
