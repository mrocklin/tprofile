from .core import Profiler

try:
    from .bokeh import serve
except ImportError:
    pass
