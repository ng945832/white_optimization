#!/bin/bash

check_affinity() {
    local thread_id=$1
    local thread_name=$2
    echo "Thread $thread_name CPU affinity:"
    taskset -pc $thread_id
}

check_threads_affinity() {
    local process_id=$1
    local name_order_sender="order_sender"
    local name_efvi_receiver="EfviReceiver"

    local threads=$(ps -T -p $process_id | awk 'NR>1{print $2, $NF}')
    while read -r tid tname; do
        if [[ $tname == "$name_order_sender"* ]] || [[ $tname == "$name_efvi_receiver"* ]]; then
            check_affinity $tid $tname
        fi
    done <<< "$threads"
}

echo "Scanning for processes with 'white' to check CPU affinity..."
processes=$(pgrep -f "white")
for pid in $processes; do
    #echo "Checking threads in process $pid..."
    check_threads_affinity $pid
done

echo "Affinity check completed."
