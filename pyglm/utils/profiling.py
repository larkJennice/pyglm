from __future__ import division
import numpy as np
import sys, StringIO, inspect, os, functools, time, collections


try:
    import line_profiler
    _prof = line_profiler.LineProfiler()

    def line_profiled(func):
        mod = inspect.getmodule(func)
        if 'PROFILING' in os.environ or (hasattr(mod,'PROFILING') and mod.PROFILING):
            return _prof(func)
        return func

    def show_line_stats(stream=None):
        _prof.print_stats(stream=stream)
except ImportError:
    line_profiled = lambda x: x