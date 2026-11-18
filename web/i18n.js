// Two languages for the interface. English by default, Romanian on request.
// Elements with data-i18n get their text swapped; app.js uses t() for the rest.

const STRINGS = {
  en: {
    title: "Reliable transfer over UDP",
    sub: "Stop-and-Wait, Go-Back-N, Selective Repeat and TCP congestion control",
    protocol: "Protocol", scenarios: "Scenarios:",
    p_clean: "clean link", p_congestion: "congestion", p_lossy: "lossy",
    g_file: "The file", size: "Size", window: "Window (GBN/SR)", u_packets: "packets",
    g_link: "The link", delay: "One-way delay", jitter: "Jitter",
    rate: "Router rate", u_rate: "packets/s, 0 = unlimited", queue: "Router queue",
    g_errors: "Errors", loss: "Data loss", ack_loss: "ACK loss", corrupt: "Corrupted packets",
    seed: "Seed", u_seed: "same seed, same result", go: "Start the transfer",
    tab_cwnd: "Congestion window", tab_seq: "Sequence–time", tab_ladder: "Packet diagram", tab_cmp: "Comparison",
    hint_cwnd: "cwnd is how many packets the sender may have in flight without an ACK. Watch slow start (exponential growth), then AIMD (+1 per RTT, halved on loss).",
    hint_seq: "Each dot is a packet sent. The slope is the transfer speed. Red dots are retransmissions, and the green line (the cumulative ACK) stalls until the missing packet arrives.",
    hint_ladder: "The ladder diagram from the lecture slides: time runs downwards. Slanted arrows are packets in flight, ✕ marks a lost packet.",
    hint_cmp: "Runs every protocol at several loss rates with the settings on the left. Takes about a minute.",
    from: "From", span: "Span", jump: "Jump to the first loss", no_loss: "no losses",
    cmp_go: "Run the comparison", sending: "sending...", done_in: "done in {s} s",
    err: "error: {m} (is server.py running?)", done: "done",
    c_ok: "file arrived intact", yes: "yes", no: "NO", c_dur: "transfer time", c_good: "goodput (useful data)",
    c_pk: "useful / sent packets", c_eff: "efficiency", c_retx: "retransmissions", c_to: "timeouts",
    c_fr: "fast retransmits", c_lost: "lost: random / queue", c_rtt: "final SRTT / RTO",
    fixed_win: "window (fixed)", in_flight: "packets in flight", dup3: "3 duplicate ACKs",
    cwnd_title: "{name}: window over time", time: "time (s)", packets: "packets",
    rtt_title: "RTT estimate (RFC 6298)",
    seq_title: "{name}: sequence number over time", seq_no: "packet no.",
    cum_ack: "cumulative ACK", ind_ack: "individual ACK", sent: "sent", resent: "resent", lost: "lost",
    sender: "Sender", receiver: "Receiver", dup_ack: "3 dup ACKs", queue_full: "queue full",
    corrupted: "corrupted", empty: "nothing on the wire in this span",
    cmp_title: "Goodput against loss rate", loss_axis: "loss on the data path (%)",
  },
  ro: {
    title: "Transfer fiabil peste UDP",
    sub: "Stop-and-Wait, Go-Back-N, Selective Repeat și controlul congestiei din TCP",
    protocol: "Protocol", scenarios: "Scenarii:",
    p_clean: "rețea bună", p_congestion: "congestie", p_lossy: "pierderi",
    g_file: "Fișierul", size: "Dimensiune", window: "Fereastră (GBN/SR)", u_packets: "pachete",
    g_link: "Legătura", delay: "Întârziere, un sens", jitter: "Jitter",
    rate: "Debit router", u_rate: "pachete/s, 0 = nelimitat", queue: "Coada routerului",
    g_errors: "Erori", loss: "Pierdere date", ack_loss: "Pierdere ACK", corrupt: "Pachete corupte",
    seed: "Seed", u_seed: "același seed = același rezultat", go: "Pornește transferul",
    tab_cwnd: "Fereastra de congestie", tab_seq: "Secvență–timp", tab_ladder: "Diagrama pachetelor", tab_cmp: "Comparație",
    hint_cwnd: "cwnd = câte pachete poate avea expeditorul „pe drum” fără confirmare. Se vede slow start (creștere exponențială), apoi AIMD (+1 pe RTT, înjumătățire la pierdere).",
    hint_seq: "Fiecare punct e un pachet trimis. Panta = viteza de transfer. Unde apar puncte roșii s-a retrimis ceva, iar linia verde (ACK-ul cumulativ) stă pe loc până vine pachetul lipsă.",
    hint_ladder: "Diagrama clasică din curs: timpul curge în jos. Săgețile oblice sunt pachete pe drum, ✕ înseamnă pachet pierdut.",
    hint_cmp: "Rulează toate protocoalele la mai multe rate de pierdere, cu ceilalți parametri din stânga. Durează cam un minut.",
    from: "De la", span: "Interval", jump: "Sari la prima pierdere", no_loss: "nicio pierdere",
    cmp_go: "Rulează comparația", sending: "se transferă...", done_in: "gata în {s} s",
    err: "eroare: {m} (e pornit server.py?)", done: "gata",
    c_ok: "fișier primit identic", yes: "da", no: "NU", c_dur: "durata transferului", c_good: "goodput (date utile)",
    c_pk: "pachete utile / trimise", c_eff: "eficiență", c_retx: "retransmisii", c_to: "timeout-uri",
    c_fr: "fast retransmit", c_lost: "pierdute: aleator / coadă", c_rtt: "SRTT / RTO final",
    fixed_win: "fereastra (fixă)", in_flight: "pachete în zbor", dup3: "3 ACK duplicate",
    cwnd_title: "{name}: fereastra în timp", time: "timp (s)", packets: "pachete",
    rtt_title: "Estimarea RTT (RFC 6298)",
    seq_title: "{name}: numărul de secvență în timp", seq_no: "nr. pachet",
    cum_ack: "ACK cumulativ", ind_ack: "ACK individual", sent: "trimis", resent: "retrimis", lost: "pierdut",
    sender: "Expeditor", receiver: "Receptor", dup_ack: "3 dup ACK", queue_full: "coadă plină",
    corrupted: "corupt", empty: "nimic pe fir în intervalul ăsta",
    cmp_title: "Goodput în funcție de rata de pierdere", loss_axis: "pierdere pe calea de date (%)",
  },
};

let LANG = "en";
try { LANG = localStorage.getItem("lang") || "en"; } catch (e) { /* private mode, stay on en */ }
const hashLang = new URLSearchParams(location.hash.slice(1)).get("lang");
if (hashLang && STRINGS[hashLang]) LANG = hashLang;

function t(key, vars) {
  let s = (STRINGS[LANG] && STRINGS[LANG][key]) || STRINGS.en[key] || key;
  for (const k in vars || {}) s = s.replace("{" + k + "}", vars[k]);
  return s;
}

// decimal comma in Romanian, dot in English
function num(x, digits) {
  const s = digits == null ? String(x) : Number(x).toFixed(digits);
  return LANG === "ro" ? s.replace(".", ",") : s;
}

function applyLang() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-lang]").forEach(b => b.setAttribute("aria-pressed", b.dataset.lang === LANG));
  document.title = t("title");
}

function setLang(l) {
  LANG = l;
  try { localStorage.setItem("lang", l); } catch (e) { /* not saved, no harm */ }
  applyLang();
  if (typeof onLangChange === "function") onLangChange();
}
