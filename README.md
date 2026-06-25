# P2P File Transfer Protocol (over UDP)

This repository contains a Python implementation of a custom Peer-to-Peer (P2P) file transfer and messaging application built on top of the **UDP (User Datagram Protocol)**. The project was developed as part of the "Computer and Communication Networks" course at FIIT STU Bratislava (2024/2025).

## Overview
The application enables communication between two participants in a local Ethernet network, allowing for the concurrent exchange of text messages and arbitrary files. To compensate for the unreliable nature of UDP, the project implements a custom protocol header, fragmentation, Stop-and-Wait ARQ mechanisms, and CRC16 checksum integrity validation.

## Key Features
* **P2P Architecture**: Nodes operate simultaneously as both receivers and senders. No strict server/client relationship.
* **Reliable Data Transfer (ARQ)**: Implements a Stop-and-Wait ARQ protocol to handle packet loss and corruption.
* **Fragmentation**: Large files and messages are automatically fragmented, with support for reassembly based on sequence numbers.
* **Integrity Verification**: Uses CRC16 checksums to detect errors; corrupted packets trigger automatic retransmission (NAK).
* **Connection Management**:
    * Three-way handshake for reliable session initialization.
    * Keep-Alive (Heartbeat) mechanism to monitor peer availability and handle timeouts.
* **Configurability**: Interactive CLI allows users to set fragment sizes, save paths, and simulate network error rates.
* **Protocol Analysis**: Includes a Wireshark Lua dissector for deep packet inspection.

## Protocol Specification
The protocol uses a custom header structure to manage communication. Depending on the packet type, it utilizes either a 2-byte control header or a full data header:

| Field | Size | Description |
| :--- | :--- | :--- |
| **Version** | 4 bits | Packet identification (CONTROL, DATA, HEARTBEAT, END) |
| **Flags** | 12 bits | Command flags (SYN, ACK, FIN, NAK, FNM) |
| **Sequence Number** | 16 bits | Order identification for reassembly (DATA only) |
| **Payload Length** | 16 bits | Size of the data payload (DATA only) |
| **CRC16** | 16 bits | Integrity check (DATA only) |

## Getting Started

### Prerequisites
* Python 3.x
* Wireshark (optional, for traffic analysis)

### Usage
1. Clone the repository.
2. Run the main script:
   ```bash
   python socket.py
3. Follow the on-screen prompts to enter your local port, target IP address, and target port.

### Configuration Menu
During the active session, you can enter `$` into the message input to open the interactive configuration menu. This menu allows you to dynamically alter the application behavior:
* **Change Maximum Fragment Size**: Adjust the upper bound for data packets (up to 1460 bytes).
* **Change Save Path**: Define a custom directory where incoming files will be stored.
* **Set Error Rate Simulation**: Configure a custom mistake percentage (`mistake_rate`) and maximum mistake threshold (`max_mistakes`) to simulate packet corruption and test the ARQ resilience.
* **Terminate Connection**: Gracefully close down the socket, notify the peer, and exit the program.

All configuration options are handled inside the `config` function located in `socket.py`.

## Wireshark Dissector
To analyze the custom protocol traffic using the provided `final_script.lua`:
1. Open Wireshark and navigate to `Help` -> `About Wireshark` -> `Folders` -> `Personal Lua Plugins`.
2. Place the `final_script.lua` file into that folder.
3. Restart Wireshark or reload your Lua plugins.
4. The packet dissector will automatically decode the custom **MUP (My UDP Protocol)** headers, filtering traffic on the designated UDP ports (such as 5500 and 5503).

## Reference Documentation
For a deep dive into the network application analysis, architecture details, behavioral state machines, and wire communication logs, please refer to the complete `Documentation.pdf` file included in this repository.

---
*Developed by Bálint Janik, FIIT STU (School Year 2024/2025).*
