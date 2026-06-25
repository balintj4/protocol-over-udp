# P2P File Transfer Protocol (over UDP)

[cite_start]This repository contains a Python implementation of a custom Peer-to-Peer (P2P) file transfer and messaging application built on top of the **UDP (User Datagram Protocol)**[cite: 16]. [cite_start]The project was developed as part of the "Computer and Communication Networks" course at FIIT STU Bratislava[cite: 5, 10].

## Overview
[cite_start]The application enables communication between two participants in a local Ethernet network, allowing for the exchange of text messages and arbitrary files[cite: 17]. [cite_start]To compensate for the unreliable nature of UDP, the project implements a custom protocol header, fragmentation, Automatic Repeat Request (ARQ) mechanisms, and CRC16 checksum integrity validation[cite: 34, 54, 79, 176].

## Key Features
* [cite_start]**P2P Architecture**: Nodes operate simultaneously as both receivers and senders[cite: 18].
* [cite_start]**Reliable Data Transfer**: Implements a Stop-and-Wait ARQ protocol to handle packet loss and corruption[cite: 178].
* [cite_start]**Fragmentation**: Large files and messages are automatically fragmented, with support for reassembly based on sequence numbers[cite: 51, 52].
* [cite_start]**Integrity Verification**: Uses CRC16 checksums to detect errors; corrupted packets trigger automatic retransmission (NAK)[cite: 54, 180, 189].
* **Connection Management**:
    * [cite_start]Three-way handshake for reliable session initialization[cite: 164].
    * [cite_start]Keep-Alive (Heartbeat) mechanism to monitor peer availability[cite: 192].
* [cite_start]**Configurability**: Interactive CLI allows users to set fragment sizes, save paths, and simulate network error rates[cite: 42, 216].
* [cite_start]**Protocol Analysis**: Includes a Wireshark Lua dissector for deep packet inspection.

## Protocol Specification
[cite_start]The protocol uses a custom header structure to manage communication[cite: 57]. 

| Field | Size | Description |
| :--- | :--- | :--- |
| **Version** | 4 bits | [cite_start]Packet identification (Control, Data, Heartbeat, End) [cite: 208] |
| **Flags** | 12 bits | [cite_start]Command flags (SYN, ACK, FIN, NAK, FNM) [cite: 209] |
| **Sequence Number** | 16 bits | [cite_start]Order identification for reassembly [cite: 72] |
| **Payload Length** | 16 bits | [cite_start]Size of the data payload [cite: 114] |
| **CRC16** | 16 bits | [cite_start]Integrity check [cite: 101, 182] |

## Getting Started

### Prerequisites
* Python 3.x
* Wireshark (optional, for traffic analysis)

### Usage
1. Clone the repository.
2. Run the main script:
   ```bash
   python socket.py
