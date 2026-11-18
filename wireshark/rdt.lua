-- Wireshark dissector for this project's protocol (a 13-byte header over UDP).
-- Install: copy this file into your personal plugins folder
--   macOS/Linux: ~/.local/lib/wireshark/plugins/
--   Windows:     %APPDATA%\Wireshark\plugins\
-- and restart Wireshark. Useful filters: rdt   or   rdt.type == 1

local rdt = Proto("rdt", "Reliable transfer over UDP (tcp-congestion-lab)")

local types = { [0] = "DATA", [1] = "ACK", [2] = "SYN", [3] = "SYN-ACK", [4] = "FIN", [5] = "FIN-ACK" }

local f_type = ProtoField.uint8("rdt.type", "Type", base.DEC, types)
local f_seq  = ProtoField.uint32("rdt.seq", "Sequence number", base.DEC)
local f_ack  = ProtoField.uint32("rdt.ack", "Ack", base.DEC)
local f_len  = ProtoField.uint16("rdt.len", "Payload length", base.DEC)
local f_cs   = ProtoField.uint16("rdt.checksum", "Checksum", base.HEX)
local f_data = ProtoField.bytes("rdt.data", "Data")
rdt.fields = { f_type, f_seq, f_ack, f_len, f_cs, f_data }

function rdt.dissector(buf, pinfo, tree)
    if buf:len() < 13 then return 0 end
    pinfo.cols.protocol = "RDT"
    local t = buf(0, 1):uint()
    local seq = buf(1, 4):uint()
    local ack = buf(5, 4):uint()
    local len = buf(9, 2):uint()

    local sub = tree:add(rdt, buf(0, 13), "RDT")
    sub:add(f_type, buf(0, 1))
    sub:add(f_seq, buf(1, 4))
    sub:add(f_ack, buf(5, 4))
    sub:add(f_len, buf(9, 2))
    sub:add(f_cs, buf(11, 2))
    if len > 0 and buf:len() >= 13 + len then
        sub:add(f_data, buf(13, len))
    end

    local name = types[t] or "?"
    if t == 1 then
        pinfo.cols.info = string.format("ACK %d", ack)
    elseif t == 0 then
        pinfo.cols.info = string.format("DATA seq=%d len=%d", seq, len)
    else
        pinfo.cols.info = string.format("%s seq=%d", name, seq)
    end
    return buf:len()
end

DissectorTable.get("udp.port"):add(9000, rdt)
