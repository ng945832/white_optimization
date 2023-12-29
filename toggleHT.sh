#!/bin/bash

HYPERTHREADING=1

function disableHTOnCore() {
    local core_id=$1
    echo "Disabling HyperThreading on Core $core_id"

    local sibling_path="/sys/devices/system/cpu/cpu${core_id}/topology/thread_siblings_list"
    if [ -f "$sibling_path" ]; then
        local siblings=$(cat $sibling_path)
        for sibling in ${siblings//,/ }; do
            if [ "$sibling" != "$core_id" ]; then
                echo "Disabling logical CPU: $sibling"
                echo "0" > "/sys/devices/system/cpu/cpu$sibling/online"
            fi
        done
    else
        echo "thread_siblings_list for core $core_id not found."
    fi
}

function disableHTOnNUMANode() {
    local numa_node=$1
    echo "Disabling HyperThreading on NUMA Node $numa_node"

    for CPU in /sys/devices/system/cpu/cpu[0-9]*; do
        CPUID=$(basename $CPU | cut -b4-)
        CPU_NODE=$(cat $CPU/topology/physical_package_id)
        if [ "$CPU_NODE" -eq "$numa_node" ]; then
            THREAD1=$(cat $CPU/topology/thread_siblings_list | cut -f1 -d,)
            if [ "$CPUID" != "$THREAD1" ]; then
                echo "Disabling logical CPU: $CPUID on NUMA Node $numa_node"
                echo "0" > $CPU/online
            fi
        fi
    done
}


function toggleHyperThreading() {
  for CPU in /sys/devices/system/cpu/cpu[0-9]*; do
      CPUID=`basename $CPU | cut -b4-`
      echo -en "CPU: $CPUID\t"
      [ -e $CPU/online ] && echo "1" > $CPU/online
      THREAD1=`cat $CPU/topology/thread_siblings_list | cut -f1 -d,`
      if [ $CPUID = $THREAD1 ]; then
          echo "-> enable"
          [ -e $CPU/online ] && echo "1" > $CPU/online
      else
        if [ "$HYPERTHREADING" -eq "0" ]; then echo "-> disabled"; else echo "-> enabled"; fi
          echo "$HYPERTHREADING" > $CPU/online
      fi
  done
}

function enabled() {
        echo -en "Enabling HyperThreading\n"
        HYPERTHREADING=1
        toggleHyperThreading
}

function disabled() {
        echo -en "Disabling HyperThreading\n"
        HYPERTHREADING=0
        toggleHyperThreading
}

#
ONLINE=$(cat /sys/devices/system/cpu/online)
OFFLINE=$(cat /sys/devices/system/cpu/offline)
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root"
   exit 1
fi
echo "---------------------------------------------------"
echo -en "CPU's online: $ONLINE\t CPU's offline: $OFFLINE\n"
echo "---------------------------------------------------"
while true; do
    read -p "Type in e to enable or d disable hyperThreading or q to quit [e/d/c/n/q] ?" ed
    case $ed in
        [Ee]* ) enabled; break;;
        [Dd]* ) disabled;exit;;
        [Nn]* ) read -p "Enter NUMA Node ID to disable HT on: " numa_node
                disableHTOnNUMANode $numa_node
                break;;
        [Cc]* ) read -p "Enter core ID to disable HT on: " core_id
                disableHTOnCore $core_id
                break;;
        [Qq]* ) exit;;
        * ) echo "Please answer e for enable or d for disable hyperThreading.";;
    esac
done
