usage() {
    echo "Usage: $0 [ENV_VAR=value ...] [onload] /path/to/binary [arguments...]"
    echo "  ENV_VAR=value    Set environment variable. Repeat for multiple variables."
    echo "  onload           If provided, use 'onload' command to start the binary."
    echo "  /path/to/binary  Specify the binary to execute."
    echo "  arguments...     Arguments passed to the binary."
    exit 1
}

if [ "$#" -eq 0 ]; then
    usage
fi

declare -A env_vars
use_onload=0

# Loop through the arguments
while [ "$#" -gt 0 ]; do
    case $1 in
        # Match key=value patterns
        *=*)
            key=${1%%=*}
            value=${1#*=}
            env_vars[$key]=$value
            ;;
        onload)
            use_onload=1
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

# Execute the binary with or without 'onload' based on the parameter
if [ -x "$binary" ]; then
    if [ "$use_onload" -eq 1 ]; then
        onload taskset -c $available_cores $binary "$@"
    else
        taskset -c $available_cores $binary "$@"
    fi
else
    echo "Error: Binary '$binary' not found or not executable."
    exit 2
fi

