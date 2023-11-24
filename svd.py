#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from collections import defaultdict
import sys


class Flags(object):
    def __init__(self, file: Path):
        self.exe_path = None
        self.numa_node = None
        self.log_path = None
        self.kbp = None
        svd_flags = [i.strip()[2:].strip() for i in file.read_text().split("\n") if i and i.strip().startswith("#!")]
        for flag in svd_flags:
            if flag.startswith("exe_path/"):
                self.exe_path = flag[len("exe_path/") :]
                continue
            if flag.startswith("log_path/"):
                self.log_path = flag[len("log_path/") :]
                continue
            if flag.startswith("numa_node/"):
                self.numa_node = flag[len("numa_node/") :]
                continue
            if flag.startswith("kbp/"):
                self.kbp = flag[len("kbp/") :]


def get_default_exe(run_path: Path) -> Optional[str]:
    flags_path = run_path.joinpath("flags.csv")
    if not flags_path.exists():
        return None
    flags_file = flags_path.open("r")
    for line in flags_file:
        m = re.match(r"\s*#\s*exe\/(\w+)", line)
        if m:
            return m.group(1)
    return None


def is_onload_version_valid(required_version="7.1.1.75"):
    try:
        output = subprocess.check_output(["onload", "--version"], env={"EF_MAX_ENDPOINTS":"16384"})
        version_str = output.decode("utf-8").strip()
        version = re.search(r"\d+(\.\d+){2,}", version_str).group(0)

        if version:
            version_parts = list(map(int, version.split(".")))
            required_version_parts = list(map(int, required_version.split(".")))

            return version_parts >= required_version_parts
        else:
            return False
    except Exception as e:
        return False


def cmd_exists(cmd: str) -> bool:
    res = subprocess.run(f"type {cmd}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    return res.returncode == 0


def get_kbp_version():
    return """onload --version | grep OpenOnload | awk '{print $2}' | tr '\n' ' """


def get_kbp_snippet(args, system_has_kbp, kbp_mode):
    if args.nokbp:
        return "", ""

    if args.kbp and not system_has_kbp:
        raise ValueError("Forced kernel bypass, but it is not configured on this sytem")

    if not system_has_kbp:
        return "", ""

    if kbp_mode == "onload":
        return kbp_mode, " onload --profile=latency "
    elif kbp_mode == "exasock":
        return kbp_mode, " exasock "
    else:
        raise ValueError(f"Unexpected kernel bypass mode {kbp_mode}")


def get_kbp_snippet_exanic(args):
    if args.nokbp:
        return ""

    system_has_kbp = cmd_exists("exasock")

    if args.kbp and not system_has_kbp:
        raise ValueError("Forced kernel bypass, but it is not configured on this sytem")

    if system_has_kbp:
        return " exasock "
    else:
        return ""


def get_kbp_snippet_old(args):
    if args.nokbp:
        return ""

    system_has_kbp = cmd_exists("onload")

    if args.kbp and not system_has_kbp:
        raise ValueError("Forced kernel bypass, but it is not configured on this sytem")

    if system_has_kbp:
        return " onload --profile=latency "
    else:
        return ""


def get_root_snippet(run_as_root, kbp_mode, logpath, disable_jemalloc):
    snippet = "sudo LD_LIBRARY_PATH=$LD_LIBRARY_PATH " if run_as_root else ""
    snippet += "SVD_VERSION=$SVD_VERSION "
    if kbp_mode == "onload":
        snippet += "EF_MAX_ENDPOINTS=16384 "
    if is_onload_version_valid() and not disable_jemalloc and Path("/shared/deploy/lib/system/libjemalloc.so").exists():
        snippet += "LD_PRELOAD=/shared/deploy/lib/system/libjemalloc.so "
    if logpath is None:
        return snippet
    date_string = datetime.now().strftime("%Y%m%d")
    time_string = datetime.now().strftime("%H%M%S")
    pre_action = [
        f"mkdir -m 770 -p {logpath}",
        f"cp flags.csv {logpath}/flags_{date_string}_{time_string}.csv",
        f"chgrp -R pull {logpath}",
    ]
    if run_as_root:
        return f"sudo {' && sudo '.join(pre_action)} && {snippet} LOGSFOLDER={logpath} "
    return f"{' && '.join(pre_action)} && {snippet} LOGSFOLDER={logpath} "

def get_physcpubind_cores(numa_node):
    # Parse /proc/cpuinfo and get the processors on NUMA node 0
    cpuinfo = defaultdict(list)
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.strip():
                key, value = line.split(":", 1)
                cpuinfo[key.strip()].append(value.strip())

    numa_node_processors = []
    for i in range(len(cpuinfo['processor'])):
        if cpuinfo['physical id'][i] == numa_node:
            numa_node_processors.append(cpuinfo['processor'][i])

    # Read /proc/cmdline and get the isolated cores
    with open("/proc/cmdline") as f:
        cmdline = f.read()

    isolcpus = re.search(r'isolcpus=(?:managed_irq,domain,)?([\d,]+)', cmdline)
    if isolcpus:
        isolcpus = isolcpus.group(1).split(",")
    else:
        isolcpus = []

    # Remove the isolated cores from the processors on NUMA node 0
    physcpubind_processors = [p for p in numa_node_processors if p not in isolcpus]

    return physcpubind_processors

def is_ubuntu():
    try:
        with open('/etc/os-release') as os_release_file:
            return 'Ubuntu' in os_release_file.read()
    except FileNotFoundError:
        return False

def get_numa_node(flag_conf: Flags):
    cpu_number = int(subprocess.check_output("lscpu -b -p=Core,Socket | grep -v '^#' | sort -u | wc -l", shell=True))
    if os.getcwd().find("staserver") != -1 and cpu_number >= 32 and flag_conf.numa_node is None:
        print(
            "Please specify numa_node 0 for staserver in flags.csv files with format '#! numa_node/0'", file=sys.stderr
        )
        raise ValueError("Please specify numa_node 0 for staserver in flags.csv files with format '#! numa_node/0'")
    if flag_conf.numa_node is None or flag_conf.numa_node == "-1":
        if is_ubuntu():
            numa_node_0_processors = get_physcpubind_cores('0')
            numa_node_1_processors = get_physcpubind_cores('1')
            numa_node_processors = numa_node_0_processors + numa_node_1_processors
            return f"numactl --physcpubind={','.join(numa_node_processors)}"
        return ""
    try:
        numa_node_processors = get_physcpubind_cores(flag_conf.numa_node)
        return f"numactl --physcpubind={','.join(numa_node_processors)}"
    except Exception as e:
        raise ValueError(f"An error occurred while getting the processor cores: {str(e)}")


def get_rlwrap_snippet(args):
    if args.norlwrap:
        return ""

    system_has_rlwrap = cmd_exists("rlwrap")

    if args.rlwrap and not system_has_rlwrap:
        raise ValueError("Forced rlwrap, but is does not exist on the system")

    # We will only use this if requested
    if args.rlwrap or system_has_rlwrap:
        return " rlwrap -H ~/.white.hist -D 2 "
    else:
        return ""


def get_beep(args):
    return r" ; echo -ne '\007' ; sleep 1; echo -ne '\007' ; sleep 1; echo -ne '\007'  "


def get_exe(prefix, ver, minver, maxver, lookback, flag_conf: Flags, verbose=True, test_paths=None):
    if flag_conf.exe_path is None:
        bin_path = Path(f"/shared/deploy/exe/{prefix}/bin")
    else:
        bin_path = Path(flag_conf.exe_path)
    if not bin_path.exists():
        print(f"Exe folder {bin_path} does not exist")
        raise ValueError(f"Exe folder {bin_path} does not exist")
    candidates = bin_path.glob(f"{prefix}-*-*")

    # Filter by version
    if ver > 0:
        if minver > ver or maxver < ver:
            if verbose:
                print("usage would not have yielded exe (non-verlapping version range).  exiting")
            return

        minver = ver
        maxver = ver
    candidates = [
        x for x in candidates if int(x.name.split("-")[1]) >= minver and int(x.name.split("-")[1]) <= int(maxver)
    ]

    # Filter by time
    cur_time = time.time() + 15.0 / (24.0 * 60 * 60)  # Give a 15 second grace period
    candidates = [x for x in candidates if lookback < (cur_time - os.path.getmtime(x)) / (24.0 * 60 * 60)]

    if len(candidates) == 0:
        if verbose:
            print("usage would not have yielded an exe.  exiting")
        return None

    chosen = sorted(candidates, key=lambda candidate: candidate.name)[-1]
    return chosen


def list_last_exes(exe_path, prefix):
    T = subprocess.run(f"ls -ltra {exe_path}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    exe_txt = T.stdout.decode("utf-8")

    T = subprocess.run(
        f"""ls -ltra {exe_path.parent}/{prefix}* | tail""", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    list_txt = T.stdout.decode("utf-8")

    return """
found exe:
{fe}
latest exes (up to 10):
{aex}
""".format(
        fe=exe_txt, aex=list_txt
    )


def sys_support_kbp(flag_conf: Flags):
    if flag_conf.kbp is None:
        return cmd_exists("onload"), "onload"
    return cmd_exists(flag_conf.kbp), flag_conf.kbp


def get_log_path(args, flag_conf: Flags):
    curpath = str(os.getcwd())
    if args.logpath is not None:
        return Path(args.logpath).joinpath(f"{Path(curpath).name}")
    elif flag_conf.log_path is not None:
        return Path(flag_conf.log_path).joinpath(f"{Path(curpath).name}")
    return None


def main():
    flag_conf = Flags(Path("./flags.csv"))

    system_has_kbp, kbp_mode = sys_support_kbp(flag_conf)
    system_has_rlwrap = cmd_exists("rlwrap")
    default_exe = get_default_exe(Path())
    if not default_exe:
        print("No exe set in flags.csv - please verify that flags.csv has a # exe/xxx line")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Detect and launch exe with proper arguments")

    group_kb = parser.add_mutually_exclusive_group()
    group_kb.add_argument(
        "-nk",
        "--nokbp",
        action="store_true",
        default=False,
        help="disable kernel bypass" + ("" if system_has_kbp else " (default)"),
    )
    group_kb.add_argument(
        "-fk",
        "--kbp",
        action="store_true",
        default=False,
        help="force kernel bypass" + (" (default)" if system_has_kbp else ""),
    )

    group_rl = parser.add_mutually_exclusive_group()
    group_rl.add_argument(
        "-nr",
        "--norlwrap",
        action="store_true",
        default=False,
        help="disable rlwrap" + ("" if system_has_rlwrap else " (default)"),
    )
    group_rl.add_argument(
        "-r",
        "--rlwrap",
        action="store_true",
        default=False,
        help="force rlwrap" + (" (default)" if system_has_rlwrap else ""),
    )

    parser.add_argument("-minv", "--minver", type=int, default=0, help="Minimum version to use (int, default=0)")
    parser.add_argument("-maxv", "--maxver", type=int, default=1e9, help="Maximum version to use (int, default=1e9)")
    parser.add_argument("-v", "--ver", type=int, default=-1, help="Exact version to use (int, default=NaN)")

    parser.add_argument(
        "-lb", "--lookback", type=float, default=0.0, help="Days to lookback to find latest exe (float, default=0.)"
    )
    parser.add_argument("-p", "--prefix", type=str, default=default_exe, help=f"Exe to use (default={default_exe})")
    parser.add_argument("-s", "--simulate", action="store_true", default=False, help="Generate command, do not run")
    parser.add_argument(
        "-d", "--dirlist", action="store_true", default=False, help="simulate and list latest exes in directory"
    )
    parser.add_argument("--logpath", type=str, default="/shared/pull/logFiles", help="folder to keep production logs")
    parser.add_argument("--getexe", action="store_true", default=False, help="print only the name of the exe and exit")
    parser.add_argument("--root", action="store_true", default=False, help="run the exe as root")
    parser.add_argument("--disable-jemalloc", action="store_true", default=False, help="disable jemalloc")
    parser.add_argument("exe_arg", nargs="*")
    args = parser.parse_args()

    target_exe = get_exe(args.prefix, args.ver, args.minver, args.maxver, args.lookback, flag_conf)
    if args.getexe:
        if target_exe:
            print(target_exe.name)
        return
    log_path = get_log_path(args, flag_conf)

    run_as_root = args.root
    kbp_mode, kbp_snippet = get_kbp_snippet(args, system_has_kbp, kbp_mode)
    cmd = "{root} {numactl} {rl} {k} {ex} {earg} {bp}".format(
        root=get_root_snippet(run_as_root, kbp_mode, log_path, args.disable_jemalloc),
        numactl=get_numa_node(flag_conf),
        k=kbp_snippet,
        rl=get_rlwrap_snippet(args),
        ex=target_exe,
        earg=" ".join(args.exe_arg),
        bp=get_beep(args),
    )

    if args.simulate or args.dirlist:
        cmd = "usage would have yielded:\n" + cmd
        if args.dirlist:
            cmd = cmd + list_last_exes(target_exe, args.prefix)

    cmd = cmd.lstrip()
    print(cmd)


if __name__ == "__main__":
    main()
