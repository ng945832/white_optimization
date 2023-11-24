#!/usr/bin/env python3

from collections import defaultdict

cpuinfo = defaultdict(list)

with open("/proc/cpuinfo") as f:
    for line in f:
        if line.strip():
            key, value = line.split(":", 1)
            cpuinfo[key.strip()].append(value.strip())

physical_core_dict = defaultdict(list)

for i in range(len(cpuinfo['processor'])):
    physical_core_dict[(cpuinfo['physical id'][i], cpuinfo['core id'][i])].append(cpuinfo['processor'][i])
    
for physical_core_id, processors in physical_core_dict.items():
    if len(processors) > 1:
        print(f"Physical ID: {physical_core_id[0]}, Core ID: {physical_core_id[1]}, Processors: {processors}")
