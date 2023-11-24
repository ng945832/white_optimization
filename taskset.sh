#!/bin/bash
arr=`ps -ef | grep "./white" | grep -v grep | awk '{print $2}'`

name="order_sender"
echo "$name"
i=32
for ays in $arr
do
    q=`ps -T -p $ays|awk '{print $2","$5}'`
    for c in $q
    do
      arrIn=(${c//,/ })
      if [[ ${arrIn[1]} == "$name"* ]]
      then
          echo `taskset -pc ${i} ${arrIn[0]}`
          i=`expr $i + 1`
      fi
    done
done

name="EfviReceiver"
echo "$name"
i=17
for ays in $arr
do
    q=`ps -T -p $ays|awk '{print $2","$5}'`
    for c in $q
    do
      arrIn=(${c//,/ })
      if [[ ${arrIn[1]} == "$name"* ]]
      then
          echo `taskset -pc ${i} ${arrIn[0]}`
          #i=`expr $i + 1`
      fi
    done
done
