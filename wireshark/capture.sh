#!/bin/bash
# Records a full transfer into a .pcap file you can open in Wireshark.
# Run from the project folder:   bash wireshark/capture.sh
# It asks for your password: tcpdump needs root to listen on an interface.

cd "$(dirname "$0")/.." || exit 1
OUT="wireshark/transfer_reno.pcap"
IFACE=lo0                               # loopback on macOS
[ "$(uname)" = "Linux" ] && IFACE=lo    # loopback on Linux

head -c 100000 /dev/urandom > /tmp/rdt_test.bin

sudo tcpdump -i "$IFACE" -w "$OUT" udp port 9000 &
TCPDUMP=$!
sleep 2

python3 recv.py --port 9000 --out /tmp/rdt_received.bin &
sleep 1
python3 send.py /tmp/rdt_test.bin --port 9000 --mode reno --loss 0.03
sleep 3

sudo kill -INT $TCPDUMP
wait $TCPDUMP 2>/dev/null

if cmp -s /tmp/rdt_test.bin /tmp/rdt_received.bin; then
    echo "the file arrived identical"
else
    echo "WARNING: the files differ"
fi
echo "capture saved to $OUT"
