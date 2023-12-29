#!/bin/bash

set_affinity() {
    local thread_id=$1
    local cpu=$2
    echo "Setting affinity of thread $thread_id to CPU $cpu"
    taskset -pc $cpu $thread_id
}

check_and_set_threads() {
    local process_id=$1
    local name_order_sender="order_sender"
    local name_efvi_receiver="EfviReceiver"
    local cpu_order_sender=32
    local cpu_efvi_receiver=17

    local threads=$(ps -T -p $process_id | awk 'NR>1{print $2, $NF}')
    while read -r tid tname; do
        if [[ $tname == "$name_order_sender"* ]]; then
            set_affinity $tid $cpu_order_sender
            ((cpu_order_sender++))
        elif [[ $tname == "$name_efvi_receiver"* ]]; then
            set_affinity $tid $cpu_efvi_receiver
        fi
    done <<< "$threads"
}

echo "Scanning for processes with 'white'..."
processes=$(pgrep -f "white")
for pid in $processes; do
    echo "Checking threads in process $pid..."
    check_and_set_threads $pid
done

echo "Affinity setting completed."
