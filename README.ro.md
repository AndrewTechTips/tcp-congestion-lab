# Transfer fiabil peste UDP

*[English version](README.md)*

Proiect la Rețele de calculatoare, Condrea Andrei, grupa 2.

Am implementat peste UDP mecanismele prin care TCP face transferul fiabil și
controlul congestiei, ca să le pot vedea „pe viu”: Stop-and-Wait, Go-Back-N,
Selective Repeat și trei variante de TCP (Tahoe, Reno, NewReno). Între
expeditor și receptor stă o legătură simulată care pierde, întârzie și strică
pachete, plus un router cu coadă finită. Așa apare congestia și pe localhost.

Partea teoretică și rezultatele sunt în `referat/`.

## Ce trebuie instalat

Doar Python 3.8 sau mai nou. Programul în sine folosește numai biblioteca
standard. `matplotlib` trebuie doar pentru `figuri.py`.

## Cum se rulează

Interfața web (cel mai simplu):

```
python3 server.py
```

Se deschide singură la http://localhost:8000. Alegi protocolul, setezi
pierderile și debitul routerului și apeși „Pornește transferul”. Ai patru
grafice: fereastra de congestie, secvență–timp, diagrama pachetelor și o
comparație între toate protocoalele.

Din terminal:

```
python3 run.py --mode reno --size 500 --loss 0.02
python3 run.py --mode gbn --window 10 --loss 0.05
python3 compare.py --runs 5        # tabelul cu toate protocoalele -> rezultate/
python3 fairness.py                # doua fluxuri prin acelasi router, indicele Jain
python3 figuri.py                  # graficele din referat -> referat/figuri/
python3 -m unittest -v             # testele automate (16 teste)
```

## Captura in Wireshark

1. Instalezi Wireshark (gratuit, wireshark.org).
2. Copiezi `wireshark/rdt.lua` in folderul de plugin-uri personale
   (`~/.local/lib/wireshark/plugins/` pe macOS/Linux) si repornesti Wireshark.
   Asa Wireshark afiseaza campurile antetului nostru (tip, seq, ack, lungime, checksum).
3. Rulezi `bash wireshark/captura.sh` (cere parola, tcpdump are nevoie de drepturi).
   Captura se salveaza in `wireshark/transfer_reno.pcap`.
4. O deschizi in Wireshark. Filtre utile: `rdt`, `rdt.type == 1` (doar ACK-uri).

Cu două terminale, ca să vezi pachetele în Wireshark (interfața loopback,
filtrul `udp.port == 9000`):

```
python3 recv.py --port 9000 --out primit.bin
python3 send.py un_fisier.pdf --mode reno --loss 0.03
```

## Structura

```
rdt/packet.py     formatul pachetului (antet de 13 octeți) și checksum-ul
rdt/link.py       legătura simulată (Link) și coada routerului (Router), care poate fi comună
rdt/rtt.py        estimarea RTT și a timeout-ului (RFC 6298)
rdt/sender.py     expeditorul, toate cele 6 moduri
rdt/receiver.py   receptorul
rdt/session.py    pornește ambele capete și strânge jurnalul pentru grafice
web/              interfața (HTML + JS, fără biblioteci externe)
tests/            testele automate
wireshark/        disectorul pentru Wireshark și scriptul de captură
```

## Simplificări față de TCP-ul real

- numerotez pachete, nu octeți;
- fereastra receptorului e fixă (64 de pachete), nu se anunță în fiecare ACK;
- nu am SACK, timestamps sau window scaling;
- numărul de secvență inițial e 0, nu unul aleator.
