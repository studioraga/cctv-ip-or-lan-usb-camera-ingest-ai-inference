#!/usr/bin/env python3
import re, statistics, sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/node2/camera_stream_tegrastats.log")
lines = path.read_text().splitlines()
fields = {"ram_mb": [], "cpu_temp_c": [], "gpu_temp_c": [], "tj_c": [], "vdd_in_mw": []}
for line in lines:
    if m := re.search(r"RAM (\d+)/(\d+)MB", line): fields["ram_mb"].append(int(m.group(1)))
    if m := re.search(r"cpu@([0-9.]+)C", line): fields["cpu_temp_c"].append(float(m.group(1)))
    if m := re.search(r"gpu@([0-9.]+)C", line): fields["gpu_temp_c"].append(float(m.group(1)))
    if m := re.search(r"tj@([0-9.]+)C", line): fields["tj_c"].append(float(m.group(1)))
    if m := re.search(r"VDD_IN (\d+)mW", line): fields["vdd_in_mw"].append(int(m.group(1)))
for k, v in fields.items():
    if v:
        print(f"{k}: samples={len(v)} min={min(v):.2f} avg={statistics.mean(v):.2f} max={max(v):.2f}")
