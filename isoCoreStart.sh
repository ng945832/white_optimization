#!/bin/bash
# Dynamic environment variable and binary execution script

usage() {
    echo "Usage: $0 [ENV_VAR=value ...] /path/to/binary [arguments...]"
    echo "  ENV_VAR=value    Set environment variable. Repeat for multiple variables."
    echo "  /path/to/binary  Specify the binary to execute."
    echo "  arguments...     Arguments passed to the binary."
    exit 1
}

if [ "$#" -eq 0 ]; then
    usage
fi

declare -A env_vars

# Loop through the arguments
while [ "$#" -gt 0 ]; do
    case $1 in
        # Match key=value patterns
        *=*)
            key=${1%%=*}
            value=${1#*=}
            env_vars[$key]=$value
            ;;
        *)
            binary=$1
            shift
            break
            ;;
    esac
    shift
done

# Export environment variables
for key in "${!env_vars[@]}"; do
    export $key="${env_vars[$key]}"
done

# Error handling if no binary is specified
if [ -z "$binary" ]; then
    echo "Error: No binary specified."
    exit 1
fi

all_cores=$(seq 0 $(( $(nproc) - 1 )))

isolated_cores=$(cat /proc/cmdline | tr ' ' '\n' | grep "isolcpus" | cut -d '=' -f 2)

IFS=',' read -r -a isolated_array <<< "$isolated_cores"

available_cores=""
for core in $all_cores; do
    if [[ ! " ${isolated_array[@]} " =~ " ${core} " ]]; then
        if [ -z "$available_cores" ]; then
            available_cores="$core"
        else
            available_cores="$available_cores,$core"
        fi
    fi
done

if [ -z "$available_cores" ]; then
    echo "no available cores"
    exit 1
fi

# Execute the binary if it is found and executable
if [ -x "$binary" ]; then
    taskset -c $available_cores $binary "$@"
else
    echo "Error: Binary '$binary' not found or not executable."
    exit 2
fi
