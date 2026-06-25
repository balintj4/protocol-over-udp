
local apc_proto = Proto("MUP", "MY UDP PROTOCOL")

-- Define ProtoFields

-- Version field: 4 bits (bits 15-12 of the first two bytes)
local f_version = ProtoField.uint16("apc.version", "Version", base.DEC, nil, 0xF000)

-- Flags field: 12 bits (bits 11-0 of the first two bytes)
local f_flags = ProtoField.uint16("apc.flags", "Flags", base.HEX, 
    {
        [0x0001] = "SYN",
        [0x0002] = "ACK",
        [0x0004] = "FIN",
        [0x0010] = "NAK",
        [0x0020] = "FNM"
    }, 0x0FFF)

-- Fields for FRG_V (Version 4 - DATA)
local f_seq_num = ProtoField.uint16("apc.seq_num", "Sequence Number", base.DEC)
local f_payload_len = ProtoField.uint16("apc.payload_len", "Payload Length", base.DEC)
local f_crc = ProtoField.uint16("apc.crc", "CRC16", base.HEX)
local f_data = ProtoField.bytes("apc.data", "Data")

-- Add fields to the Proto
apc_proto.fields = {f_version, f_flags, f_seq_num, f_payload_len, f_crc, f_data}

-- Define version enums for better readability
local VERSION = {
    [2]  = "CONTROL",
    [4]  = "DATA",
    [8]  = "HEARTBEAT",
    [14] = "END"
}

-- Define flag enums
local FLAGS = {
    [0x0001] = "SYN",
    [0x0002] = "ACK",
    [0x0004] = "FIN",
    [0x0010] = "NAK",
    [0x0020] = "FNM"
}

-- Utility function to decode flags
local function decode_flags(flags)
    local decoded = {}
    for bit, name in pairs(FLAGS) do
        if (flags & bit) ~= 0 then
            table.insert(decoded, name)
        end
    end
    return table.concat(decoded, ", ")
end

-- Dissector function
function apc_proto.dissector(buffer, pinfo, tree)
    pinfo.cols.protocol = "APC"

    local subtree = tree:add(apc_proto, buffer(), "APC Protocol Data")

    -- Check if buffer has at least 2 bytes for the header
    if buffer:len() < 2 then
        subtree:append_text(" (Incomplete Header)")
        pinfo.cols.info = "Incomplete Header"
        return
    end

    -- Parse the first 2 bytes for version and flags
    local version_and_flags = buffer(0,2):uint()
    local version = (version_and_flags >> 12) & 0xF
    local flags = version_and_flags & 0x0FFF

    -- Add version to the tree
    subtree:add(f_version, buffer(0,2)):append_text(" (" .. (VERSION[version] or "Unknown") .. ")")

    -- Add flags to the tree with dropdown and inline display
    local flags_field = subtree:add(f_flags, buffer(0,2))
    flags_field:append_text(" [" .. (decode_flags(flags) or "None") .. "]")

    -- Handle different versions
    if version == 4 then  -- FRG_V (DATA)
        -- Check if buffer has enough bytes for DATA header
        if buffer:len() < 8 then
            subtree:append_text(" (Incomplete DATA Header)")
            pinfo.cols.info = "DATA (Incomplete)"
            return
        end

        -- Extract FRG_V specific fields
        local seq_num = buffer(2,2):uint()
        local payload_len = buffer(4,2):uint()
        local crc = buffer(6,2):uint()
        local data_length = payload_len

        -- Ensure buffer has enough data for the payload
        if buffer:len() < 8 + data_length then
            subtree:append_text(" (Incomplete DATA Payload)")
            pinfo.cols.info = string.format("DATA (%d bytes) - Incomplete", data_length)
            return
        end

        local data = buffer(8, data_length)

        -- Add fields to the tree
        subtree:add(f_seq_num, buffer(2,2))
        subtree:add(f_payload_len, buffer(4,2))
        subtree:add(f_crc, buffer(6,2))

        -- Set the Info column
        pinfo.cols.info = string.format("DATA -> %d + 8 bytes", data_length)

    elseif version == 2 then  -- FLG_V (CONTROL)
        pinfo.cols.info = "CONTROL"
        -- Additional fields for CONTROL can be parsed here if needed

    elseif version == 8 then  -- HBT_V (HEARTBEAT)
        pinfo.cols.info = "HEARTBEAT"
        -- Additional fields for HEARTBEAT can be parsed here if needed

    elseif version == 14 then  -- END_S (END)
        pinfo.cols.info = "END"
        -- Additional fields for END can be parsed here if needed

    else
        pinfo.cols.info = "Unknown Version"
    end
end

-- Register the dissector for specific UDP ports
local udp_table = DissectorTable.get("udp.port")
udp_table:add(5000, apc_proto)  -- Registering port 5500
udp_table:add(5003, apc_proto)  -- Registering port 5503