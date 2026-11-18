#!/bin/bash
# Captureaza un transfer complet intr-un fisier .pcap pe care il deschizi in Wireshark.
# Ruleaza din folderul proiectului:   bash wireshark/captura.sh
# Cere parola de administrator, pentru ca tcpdump are nevoie de drepturi ca sa asculte reteaua.

cd "$(dirname "$0")/.." || exit 1
OUT="wireshark/transfer_reno.pcap"
IFACE=lo0                               # loopback pe macOS
[ "$(uname)" = "Linux" ] && IFACE=lo    # loopback pe Linux

head -c 100000 /dev/urandom > /tmp/rdt_test.bin

sudo tcpdump -i "$IFACE" -w "$OUT" udp port 9000 &
TCPDUMP=$!
sleep 2

python3 recv.py --port 9000 --out /tmp/rdt_primit.bin &
sleep 1
python3 send.py /tmp/rdt_test.bin --port 9000 --mode reno --loss 0.03
sleep 3

sudo kill -INT $TCPDUMP
wait $TCPDUMP 2>/dev/null

if cmp -s /tmp/rdt_test.bin /tmp/rdt_primit.bin; then
    echo "fisierul a ajuns identic"
else
    echo "ATENTIE: fisierele difera"
fi
echo "captura e in $OUT"
