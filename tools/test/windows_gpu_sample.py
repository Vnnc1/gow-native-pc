"""Optional PDH GPU engine samples for local benchmarks; no vendor dependency.

Percentages describe engine and total CPU busy time, not watts, clocks or temperature.
Only the selected child's engine names and system engine totals are retained.
Unavailable/first samples are explicit, never zero utilization.
"""
import ctypes as ct
from ctypes import wintypes as wt
import math
import os
import re
import time


def child_pid(parent, executable):
    """Resolve only the helper's direct child; never attach to another game."""
    class Entry(ct.Structure):
        _fields_ = [("size", wt.DWORD), ("usage", wt.DWORD), ("pid", wt.DWORD),
                    ("heap", ct.c_size_t), ("module", wt.DWORD), ("threads", wt.DWORD),
                    ("parent", wt.DWORD), ("priority", wt.LONG), ("flags", wt.DWORD),
                    ("exe", wt.WCHAR * 260)]
    kernel = ct.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    for name in ("Process32FirstW", "Process32NextW"):
        getattr(kernel, name).argtypes = [wt.HANDLE, ct.POINTER(Entry)]
        getattr(kernel, name).restype = wt.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ct.c_void_p(-1).value:
        raise ct.WinError(ct.get_last_error())
    try:
        entry = Entry()
        entry.size = ct.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ct.byref(entry))
        while found:
            if entry.parent == parent and entry.exe.lower() == executable.lower():
                return entry.pid
            found = kernel.Process32NextW(snapshot, ct.byref(entry))
        return None
    finally:
        kernel.CloseHandle(snapshot)


def summarize_engines(items, pid):
    child, total = {}, {}
    for name, status, value in items:
        match = re.fullmatch(r"pid_(\d+)_(luid_.+)", name)
        if not match or status not in (0, 1) or not math.isfinite(value) or value < 0:
            continue
        engine = match[2]
        total[engine] = total.get(engine, 0) + value
        if int(match[1]) == pid:
            child[engine] = child.get(engine, 0) + value
    return {"available": bool(child), "child_engines_percent": child,
            "child_busiest_engine_percent": max(child.values(), default=None),
            "system_engines_percent": total,
            "system_busiest_engine_percent": max(total.values(), default=None)}


def cpu_rate(previous, current):
    if previous is None or current is None or previous[0] != current[0]: return None
    elapsed, used = current[1] - previous[1], current[2] - previous[2]
    if elapsed <= 0 or used < 0: return None
    return used * 10000.0 / elapsed  # 100-ns process ticks / monotonic nanoseconds, percent of one core.


def process_cpu_snapshot(pid):
    kernel = ct.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.GetProcessTimes.argtypes = [wt.HANDLE] + [ct.POINTER(wt.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle: return None
    try:
        created, exited, system, user = (wt.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, ct.byref(created), ct.byref(exited), ct.byref(system), ct.byref(user)): return None
        ticks = lambda value: (value.dwHighDateTime << 32) | value.dwLowDateTime
        return ((pid, ticks(created)), time.monotonic_ns(), ticks(system) + ticks(user))
    finally:
        kernel.CloseHandle(handle)


class GpuSampler:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows PDH counters required")
        self.dll = ct.WinDLL("pdh")
        self.query, self.counter, self.cpu_counter = wt.HANDLE(), wt.HANDLE(), wt.HANDLE()
        self.primed = False
        self.previous_cpu = None
        signatures = {
            "PdhOpenQueryW": [wt.LPCWSTR, ct.c_size_t, ct.POINTER(wt.HANDLE)],
            "PdhAddEnglishCounterW": [wt.HANDLE, wt.LPCWSTR, ct.c_size_t, ct.POINTER(wt.HANDLE)],
            "PdhCollectQueryData": [wt.HANDLE],
            "PdhGetFormattedCounterArrayW": [wt.HANDLE, wt.DWORD, ct.POINTER(wt.DWORD), ct.POINTER(wt.DWORD), ct.c_void_p],
            "PdhGetFormattedCounterValue": [wt.HANDLE, wt.DWORD, ct.POINTER(wt.DWORD), ct.c_void_p],
            "PdhCloseQuery": [wt.HANDLE],
        }
        for name, args in signatures.items():
            fn = getattr(self.dll, name)
            fn.argtypes, fn.restype = args, wt.DWORD
        status = self.dll.PdhOpenQueryW(None, 0, ct.byref(self.query))
        if status:
            raise OSError(f"PdhOpenQueryW: 0x{status:08x}")
        status = self.dll.PdhAddEnglishCounterW(self.query, r"\GPU Engine(*)\Utilization Percentage", 0, ct.byref(self.counter))
        if status:
            self.close()
            raise OSError(f"GPU counter unavailable: 0x{status:08x}")
        # Classic total CPU busy time, independent of the child's CPU time and
        # turbo-frequency weighting. Keep GPU sampling usable if this is absent.
        status = self.dll.PdhAddEnglishCounterW(self.query, r"\Processor(_Total)\% Processor Time", 0, ct.byref(self.cpu_counter))
        if status:
            self.cpu_counter = wt.HANDLE()

    def close(self):
        if self.query:
            self.dll.PdhCloseQuery(self.query)
            self.query = wt.HANDLE()

    def sample(self, pid):
        current_cpu = process_cpu_snapshot(pid)
        cpu_percent = cpu_rate(self.previous_cpu, current_cpu)
        cpu_seconds = (current_cpu[1] - self.previous_cpu[1]) / 1e9 if current_cpu and self.previous_cpu and cpu_percent is not None else None
        self.previous_cpu = current_cpu
        status = self.dll.PdhCollectQueryData(self.query)
        if status:
            return {"available": False, "reason": f"collect: 0x{status:08x}"}
        if not self.primed:
            self.primed = True
            return {"available": False, "reason": "first rate sample"}
        class Value(ct.Structure):
            _fields_ = [("status", wt.DWORD), ("value", ct.c_double)]
        class Item(ct.Structure):
            _fields_ = [("name", wt.LPWSTR), ("counter", Value)]
        size, count = wt.DWORD(), wt.DWORD()
        fmt_double, more_data = 0x200, 0x800007D2
        # New engine instances may appear between sizing and reading the array.
        for _ in range(3):
            if size.value > 4 * 1024 * 1024:
                return {"available": False, "reason": "counter array exceeded bound"}
            buffer = ct.create_string_buffer(size.value) if size.value else None
            status = self.dll.PdhGetFormattedCounterArrayW(self.counter, fmt_double, ct.byref(size), ct.byref(count), buffer)
            if status == more_data:
                continue
            if status or not buffer:
                return {"available": False, "reason": f"array: 0x{status:08x}"}
            if count.value * ct.sizeof(Item) > ct.sizeof(buffer):
                return {"available": False, "reason": "invalid counter array"}
            items = ct.cast(buffer, ct.POINTER(Item))
            result = summarize_engines([(items[i].name, items[i].counter.status, items[i].counter.value)
                                        for i in range(count.value)], pid)
            cpu = Value()
            cpu_status = self.dll.PdhGetFormattedCounterValue(self.cpu_counter, fmt_double, None, ct.byref(cpu)) if self.cpu_counter else 1
            result["system_cpu_percent"] = cpu.value if not cpu_status and cpu.status in (0, 1) and math.isfinite(cpu.value) and 0 <= cpu.value <= 100 else None
            result["child_cpu_percent_one_core"] = cpu_percent
            result["child_cpu_interval_seconds"] = cpu_seconds
            return result
        return {"available": False, "reason": "counter instances changed repeatedly"}
