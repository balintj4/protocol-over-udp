import socket
import sys
import threading
import random
from pathlib import Path
import struct
import queue
import time

# Flags
SYN = 0b000000000001
ACK = 0b000000000010
FIN = 0b000000000100
NAK = 0b000000001000
FNM = 0b000000010000

# Versions
END_S = 0b1110
HBT_V = 0b1000
FRG_V = 0b0100
FLG_V = 0b0010

# Keep-alive parameters
HEARTBEAT_INTERVAL = 5
HEARTBEAT_ATTEMPTS = 3

# Configuration data
max_fragment_size = 1024
path = Path('')
mistake_rate = 0
max_mistakes = 0
mistakes = 0


#############################################
#              CONFIG & UTILS               #
#############################################

def config(sock, peer_ip, peer_port, session_active):
    global max_fragment_size, path, mistake_rate, max_mistakes

    print("[1]: Zmeň maximálnu veľkosť fragmentu")
    print("[2]: Zmeň cestu na uloženie súborov")
    print("[3]: Nastav stav chybovosti.")
    print("[4]: Ukonči spojenie")
    option = str(input("Vyber možnosť: "))

    if option == "1":
        fragment_size = int(input("Nová maximálna veľkosť: "))
        if fragment_size < 1460:
            max_fragment_size = fragment_size
        else:
            print("Príliš veľké fragmenty. Nastavujem na najvyššiu hodnotu - 1450 Bytov")
            max_fragment_size = 1460

    elif option == "2":
        path = Path(str(input("Nová cesta: ")))

    elif option == "3":
        mistake_rate = float(input("Zadaj percentuálnu chybovosť: "))
        max_mistakes = int(input("Zadaj maximálny počet chýb: "))

    elif option == "4":
        print("Ukončujem spojenie...")
        send_end_signal(sock, peer_ip, peer_port)
        session_active.clear()
        sock.close()
        sys.exit(0)
        return


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc & 0xFFFF


def modify_crc(header: bytes) -> bytes:
    header_bytes = bytearray(header)
    crc_int = struct.unpack('!H', header[6:8])[0]
    crc_int ^= 0xA001

    packed_crc = struct.pack("!H", crc_int)
    header_bytes[6:8] = packed_crc

    return bytes(header_bytes)


def start_listening(listen_ip, listen_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((listen_ip, listen_port))
    return sock

def get_local_ip():

    #getting my own IP
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print("Moja IP adresa je:", local_ip)

    return local_ip


#############################################
#             HEADER FUNCTIONS              #
#############################################

def create_header(version, flags=0, payload_len=0, seq_num=0, crc=0):
    version_byte = version & 0b1111
    flags_byte = flags & 0b111111111111

    if version_byte == FRG_V:
        header = struct.pack("!H H H H", (version_byte << 12) | flags_byte, seq_num, payload_len, crc)
    elif version_byte == FLG_V or version_byte == END_S or version_byte == HBT_V:
        header = struct.pack("!H", (version_byte << 12) | flags_byte)
    else:
        header = b''
    return header


def parse_header(data):
    if len(data) < 2:
        return {'type': 'invalid'}

    control_info = data[:2]
    remaining = data[2:]
    header_control = struct.unpack("!H", control_info)
    version = (header_control[0] >> 12) & 0b1111
    flags = header_control[0] & 0b111111111111

    if version == FLG_V:
        return {'type': 'control', 'flags': flags, 'data': None, 'addr': None}

    elif version == HBT_V:
        return {'type': 'beat', 'flags': flags, 'data': None, 'addr': None}

    elif version == FRG_V:
        if len(remaining) < 6:
            return {'type': 'invalid'}
        header_part = remaining[:6]
        message_part = remaining[6:]

        header = struct.unpack("!H H H", header_part)
        seq_num = header[0]
        payload_len = header[1]
        crc = header[2]

        return {
            'type': 'data',
            'flags': flags,
            'seq_num': seq_num,
            'payload_len': payload_len,
            'crc': crc,
            'data': message_part
        }

    elif version == END_S:
        return {'type': 'end', 'flags': flags, 'data': None, 'addr': None}

    else:
        return {'type': 'unknown'}


#############################################
#                FRAGMENTING                #
#############################################

def fragment_data(data, fragment_size):
    global mistakes
    mistakes = 0
    fragmented_data = []
    total_fragments = (len(data) + fragment_size - 1) // fragment_size

    for i in range(total_fragments):
        start = i * fragment_size
        end = start + fragment_size
        fragment = data[start:end]
        crc = crc16(fragment)
        if i == total_fragments - 1:
            # ending last fragment with FIN flag
            fragmented_data.append((FIN, i, fragment, crc))
        else:
            fragmented_data.append((0, i, fragment, crc))
    return fragmented_data


#############################################
#             SENDING FUNCTIONS             #
#############################################

def send_arq(sock, target_ip, target_port, header, fragment, ack_queue, session_active,last_activity):
    global mistakes

    while session_active.is_set():
        try:
            if random.random() < mistake_rate and mistakes < max_mistakes:
                mistakes += 1
                modified_header = modify_crc(header)
                sock.sendto(modified_header + fragment, (target_ip, target_port))
            else:
                sock.sendto(header + fragment, (target_ip, target_port))

            try:
                # Wait for ACK/NAK with timeout
                response = ack_queue.get(timeout=2)
                if isinstance(response, int):
                    if response & ACK:
                        # ACK received for fragment

                        with last_activity_lock:
                            last_activity[0] = time.time()
                        return True
                    elif response & NAK:
                        print("Obdržané NAK - odosielam fragment opätovne")
                else:
                    # Handle unexpected response types
                    print("Obdržaná neznáma odozva:", response)
            except queue.Empty:
                print("Timeout, odosielam fragment opätovne")
        except OSError:
            time.sleep(0.1)



def send_data(sock, target_ip, target_port, ack_queue, last_activity, session_active):
    global mistakes

    while session_active.is_set():
        try:

            print("\nPre prístup ku konfiguráciám zadaj '$'")
            message = input("Zadaj správu, alebo súbor vo formáte 'file:/path/to/file': \n")

            if message == "$":
                print("\n\nSpúšťam konfiguráciu...")
                config(sock, target_ip, target_port, session_active)
                continue


            # Update last activity
            with last_activity_lock:
                last_activity[0] = time.time()

            #########################################
            #####       SENDING A FILE          #####
            #########################################

            if message.startswith("file:"):
                file_path = Path(message[5:])
                try:
                    with open(file_path, "rb") as f:
                        data = f.read()

                    ############# SENDING NAME #############

                    file_name = file_path.name.encode('utf-8')
                    print(f"\nOdosielam súbor: {file_path}")
                    if len(file_name) > max_fragment_size:
                        # sending fragmented name

                        name_fragments = fragment_data(file_name, max_fragment_size)
                        for i, (flg, seq_num, fragment, crc) in enumerate(name_fragments):
                            if not session_active.is_set():
                                print("\nSpojenie bolo prerušené")
                                return
                            header = create_header(FRG_V, FNM | flg, len(fragment), seq_num, crc)
                            send_arq(sock, target_ip, target_port, header, fragment, ack_queue, session_active,last_activity)
                        print(f"Odoslaný názov súboru. ({len(file_name)} B)")
                    else:
                        # sending name in one piece
                        mistakes = 0
                        crc = crc16(file_name)
                        header = create_header(FRG_V, FNM | FIN, payload_len=len(file_name), seq_num=0, crc=crc)
                        send_arq(sock, target_ip, target_port, header, file_name, ack_queue, session_active,last_activity)
                        print(f"Odoslaný názov súboru. ({len(file_name)} B)")

                    ############# SENDING THE CONTENT #############

                    if len(data) > max_fragment_size:
                        # sending content fragmented
                        fragments = fragment_data(data, max_fragment_size)

                        for i, (flg, seq_num, fragment, crc) in enumerate(fragments):
                            if not session_active.is_set():
                                print("\nSpojenie bolo prerušené")
                                return
                            header = create_header(FRG_V, flg, len(fragment), seq_num, crc)
                            send_arq(sock, target_ip, target_port, header, fragment, ack_queue, session_active,last_activity)
                            print(f"Odoslaný fragment č. {i + 1} ({len(fragment)} B)")
                            if flg == FIN:
                                print(
                                    f"\nSúbor odoslaný na {target_ip}:{target_port} v {i + 1} fragmentoch ({i * max_fragment_size + len(fragment)} B)")

                    elif len(data) < max_fragment_size and len(data) > 0:
                        # sending content in one piece

                        mistakes = 0
                        crc = crc16(data)
                        header = create_header(FRG_V, FIN, payload_len=len(data), seq_num=0, crc=crc)
                        send_arq(sock, target_ip, target_port, header, data, ack_queue, session_active,last_activity)
                        print(
                            f"\nSúbor odoslaný na {target_ip}:{target_port} ako 1 fragment ({len(data)} B)")

                    else:
                        continue

                except FileNotFoundError:
                    print("Súbor sa nenašiel, skontrolujte cestu.")
                    continue

            ############################################
            #####       SENDING A MESSAGE          #####
            ############################################

            else:
                data = message.encode("utf-8")

                if len(data) > max_fragment_size:
                    # sending message fragmented
                    fragments = fragment_data(data, max_fragment_size)

                    for i, (flg, seq_num, fragment, crc) in enumerate(fragments):
                        if not session_active.is_set():
                            print("\nSpojenie bolo prerušené")
                            return
                        header = create_header(FRG_V, flg, len(fragment), seq_num, crc)
                        send_arq(sock, target_ip, target_port, header, fragment, ack_queue, session_active,last_activity)
                        print(f"Odoslaný fragment č. {i + 1} ({len(fragment)} B)")
                        if flg == FIN:
                            print(
                                f"\nSpráva odoslaná na {target_ip}:{target_port} v {i + 1} fragmentoch ({i * max_fragment_size + len(fragment)} B)")

                elif len(data) < max_fragment_size and len(data) > 0:
                    # sending message in one piece

                    mistakes = 0
                    crc = crc16(data)
                    header = create_header(FRG_V, FIN, payload_len=len(data), seq_num=0, crc=crc)
                    send_arq(sock, target_ip, target_port, header, data, ack_queue, session_active,last_activity)
                    print(
                        f"\nSpráva odoslaná na {target_ip}:{target_port} ako 1 fragment ({len(data)} B)")

                else:
                    continue

        except EOFError:
            break
        except Exception as e:
             print(f"Error pri odosielaní: {e}")
             break

    return


#############################################
#            RECEIVING FUNCTIONS            #
#############################################

def receive_arq(sock, beat_queue, ack_queue, data_queue, last_activity, session_active):
    while session_active.is_set():
        try:
            data, addr = sock.recvfrom(4096)  # Increased buffer size
            parsed = parse_header(data)
            if parsed['type'] == 'control':
                ack_queue.put(parsed['flags'])
            elif parsed['type'] == 'beat':
                beat_queue.put(parsed['flags'])
            elif parsed['type'] == 'end':
                print("Spojenie ukončené druhou stranou.")
                session_active.clear()
                return

            elif parsed['type'] == 'data':
                flags = parsed['flags']
                seq_num = parsed['seq_num']
                payload_len = parsed['payload_len']
                received_crc = parsed['crc']
                message = parsed['data'][:payload_len]

                calculated_crc = crc16(message)
                if calculated_crc == received_crc:
                    # Valid fragment
                    response_flags = ACK
                    # Update last activity
                    with last_activity_lock:
                        last_activity[0] = time.time()
                    response = create_header(FLG_V, response_flags)
                    sock.sendto(response, addr)
                    data_queue.put({'flags': flags, 'seq_num': seq_num, 'payload_len': payload_len, 'data': message})
                else:
                    # CRC mismatch
                    response = create_header(FLG_V, NAK)
                    sock.sendto(response, addr)
                    print("Porušený fragment, žiadam opätovné poslanie.")
        except Exception as e:
            pass


def receive_data(sock, data_queue, session_active):
    print("\n")
    buffer = []
    name_buffer = []
    bytes_received = 0
    file_name = None

    while session_active.is_set():
        try:
            item = data_queue.get(timeout=1)
            if isinstance(item, dict) and 'flags' in item:
                flags = item['flags']
                seq_num = item['seq_num']
                payload_len = item['payload_len']
                fragment = item['data']

                if flags & FNM:
                    name_buffer.append((seq_num, fragment))
                    if flags & FIN:
                        name_buffer.sort(key=lambda x: x[0])
                        file_name = (b''.join(part for _, part in name_buffer)).decode('utf-8', errors='ignore')
                        print(f"Obdržiavanie súboru: {file_name}")
                        continue
                else:
                    buffer.append((seq_num, fragment))
                    bytes_received += len(fragment)
                    print(f"Obdržaný fragment č. {seq_num + 1} ({len(fragment)} B)")

                if flags & FIN:
                    buffer.sort(key=lambda x: x[0])
                    if file_name:  # assembling a file
                        save_path = path / file_name
                        with open(save_path, "wb") as f:
                            for _, part in buffer:
                                f.write(part)

                        print(f"\nSúbor uložený: {save_path}")
                        print(
                            f"\n\nObdržané v {seq_num + 1} fragmentoch ({bytes_received} B)\n")

                    else:  # assembling a message
                        full_message = b''.join(part for _, part in buffer)

                        print(
                            f"\nObdržané v {seq_num + 1} fragmentoch s ({bytes_received} B)")
                        print(f"\n\nObdržaná správa: {full_message.decode('utf-8', 'ignore')}\n")

                    buffer = []
                    bytes_received = 0
                    file_name = None
                    name_buffer = []

        except queue.Empty:
            continue
        except Exception as e:
            print(f"Systémová chyba: {e}")


#############################################
#            HANDSHAKE FUNCTION             #
#############################################

def three_way_handshake(sock, my_ip, peer_ip, check1, check2, peer_port, ack_queue, session_active):
    if check1 < check2:
        attempt = 0
        print("Inicializujem spojenie...")

        while attempt < 10 and session_active.is_set():
            header = create_header(FLG_V, SYN)
            sock.sendto(header, (peer_ip, peer_port))
            print("Začínam synchronizáciu")

            try:
                response = ack_queue.get(timeout=5)
                if (response & SYN) and (response & ACK):
                    print("Druhá strana dostupná.")
                    header = create_header(FLG_V, ACK)
                    sock.sendto(header, (peer_ip, peer_port))
                    print("Synchronizácia spojenia úspešná!")
                    return True
                else:
                    print(f"Sznchronizácia zlyhala: {response}")
            except queue.Empty:
                attempt += 1
                print("Žiadna odpoveď, opakujem synchronizáciu...")

        print("Synchronizácia neúspešná, spojenie zrušené.")
        send_end_signal(sock, peer_ip, peer_port)
        session_active.clear()
        sock.close()
        sys.exit(0)
        return

    else:
        print("Čakám na synchronizáciu...")
        try:
            while session_active.is_set():
                response = ack_queue.get(timeout=50)
                if response & SYN:
                    print("Informujem o dostupnosti")
                    header = create_header(FLG_V, SYN | ACK)
                    sock.sendto(header, (peer_ip, peer_port))

                    # Wait for ACK
                    response_ack = ack_queue.get(timeout=5)
                    if (response_ack & ACK) and not (response_ack & SYN):
                        print("Druhá strana dostupná, synchronizácia úspešná.")
                        return True
                    else:
                        print(f"Synchronizácia zlyhala: {response_ack}")
        except queue.Empty:
            print("Synchronizácia zlyhala...")
            send_end_signal(sock, peer_ip, peer_port)
            session_active.clear()
            sock.close()
            sys.exit(0)
            return
        except Exception as e:
            print(f"Synchronizácia zlyhala: {e}")
            send_end_signal(sock, peer_ip, peer_port)
            session_active.clear()
            sock.close()
            sys.exit(0)
            return


#############################################
#          HEARTBEAT & TERMINATION          #
#############################################

def send_end_signal(sock, peer_ip, peer_port):
    header = create_header(END_S, FIN)
    sock.sendto(header, (peer_ip, peer_port))
    print("Informujem o ukončení spojenia.")


def heartbeat_monitor(sock, peer_ip, peer_port, last_activity, beat_queue, session_active):
    heartbeat_count = 0
    while session_active.is_set():
        try:
            time.sleep(1)  # Check every second
            with last_activity_lock:
                elapsed = time.time() - last_activity[0]
            if elapsed >= HEARTBEAT_INTERVAL:
                if heartbeat_count < HEARTBEAT_ATTEMPTS:
                    header = create_header(HBT_V, ACK)  # FLG_V with no flags indicates heartbeat
                    sock.sendto(header, (peer_ip, peer_port))
                    heartbeat_count += 1
                    # Wait for ACK
                    try:
                        response = beat_queue.get(timeout=HEARTBEAT_INTERVAL)
                        if response & ACK:
                            heartbeat_count = 0
                            with last_activity_lock:
                                last_activity[0] = time.time()
                    except queue.Empty:
                        pass

                else:
                    try:
                        print("\nDruhá strana neodpovedá, ukončujem spojenie.")
                        send_end_signal(sock, peer_ip, peer_port)
                        session_active.clear()
                        sock.close()
                        sys.exit(0)
                        return
                    except Exception as e:
                        session_active.clear()
                        sock.close()
                        sys.exit(0)
                        return
        except Exception as e:
            heartbeat_count += 1
            time.sleep(HEARTBEAT_INTERVAL)


# Shared resources
last_activity = [time.time()]
last_activity_lock = threading.Lock()


#############################################
#               MAIN FUNCTION               #
#############################################


def main():
    global peer_ip  # Needed for send_data
    # Local device
    my_ip = get_local_ip()
    my_port = int(input("Zadaj svoj port: "))

    # remote device
    peer_ip = str(input("Zadaj ip ciela: "))
    peer_port = int(input("Zadaj port ciela: "))

    sock = start_listening(my_ip, my_port)
    check1 = int(my_ip.replace('.', '') + str(my_port))
    check2 = int(peer_ip.replace('.', '') + str(peer_port))

    ack_queue = queue.Queue()
    data_queue = queue.Queue()
    beat_queue = queue.Queue()

    # Session active flag
    session_active = threading.Event()
    session_active.set()

    # Start the central receiver
    receiver_thread = threading.Thread(target=receive_arq,
                                       args=(sock, beat_queue, ack_queue, data_queue, last_activity, session_active))
    receiver_thread.daemon = True
    receiver_thread.start()

    # Start the data receiver
    data_receiver_thread = threading.Thread(target=receive_data, args=(sock, data_queue, session_active))
    data_receiver_thread.daemon = True
    data_receiver_thread.start()

    # Perform handshake
    handshake_thread = threading.Thread(target=three_way_handshake, args=(
        sock, my_ip, peer_ip, check1, check2, peer_port, ack_queue, session_active))
    handshake_thread.start()
    handshake_thread.join()

    if not session_active.is_set():
        print("Synchronizácia neúspešná, spojenie ukončené.")
        sock.close()
        sys.exit(0)

    # Start the heartbeat monitor
    heartbeat_thread = threading.Thread(target=heartbeat_monitor,
                                        args=(sock, peer_ip, peer_port, last_activity, beat_queue, session_active))
    heartbeat_thread.daemon = True
    heartbeat_thread.start()

    # Start the sending thread
    sending_thread = threading.Thread(target=send_data,
                                      args=(sock, peer_ip, peer_port, ack_queue, last_activity, session_active))
    sending_thread.start()

    try:
        sending_thread.join()
        receiver_thread.join()
    except KeyboardInterrupt:
        print("Spojenie vypnuté nasilu.")
        send_end_signal(sock, peer_ip, peer_port)
        session_active.clear()
    finally:
        receiver_thread.join(timeout=2)
        data_receiver_thread.join(timeout=2)
        heartbeat_thread.join(timeout=2)
        sock.close()
        print("Úspešné ukončenie programu.")
        sys.exit(0)


if __name__ == "__main__":
    main()
