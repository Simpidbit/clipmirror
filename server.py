import spclipbd
import socket
import select
import threading
import sys
import logging
import ipaddress

if __name__ == '__main__':
    HOST = sys.argv[1]
    PORT = int(sys.argv[2])

def sendall(s:socket.socket, msg:bytes) -> None:
    logging.info(f'Send {msg} to {s.getpeername()}...')
    try:
        s.sendall(msg)
        logging.info('Send OK.')
    except:
        logging.info(f'Failed to send {msg} to {s.getpeername()}!')

class MessageFromClient:
    def __init__(self, paste: spclipbd.ClipboardContent) -> None:
        self.paste = paste

    def make_msg_to_client(self) -> bytes:
        msg = int(len(self.paste.get_suffix())).to_bytes(1, 'big') + \
              self.paste.get_suffix().encode('utf-8') + \
              int(len(self.paste.get_raw())).to_bytes(4, 'big') + \
              self.paste.get_raw()
        return msg


class MessageParser:
    def __init__(self) -> None:
        self.suffix: str = str()
        self.suffix_length: int = int()
        self.raw: bytes = bytes()
        self.raw_length: int = int()
        self.msg_raw: bytes = bytes()
        self.msg_raw_length: int = int()

    def load(self, msg:bytes) -> None | MessageFromClient:
        self.msg_raw += msg
        self.msg_raw_length += len(msg)

        try:
            suffix_length = int.from_bytes(self.msg_raw[:1], 'big')
            if suffix_length == 0xff and self.msg_raw[1] == 0xff:
                # heart beat
                self.msg_raw = self.msg_raw[2:]
                self.msg_raw_length -= 2
                return None
            suffix = self.msg_raw[1 : 1 + suffix_length].decode('utf-8')
            raw_length = int.from_bytes(self.msg_raw[1 + suffix_length : 1 + suffix_length + 4], 'big')
            raw = self.msg_raw[1 + suffix_length + 4 : 1 + suffix_length + 4 + raw_length]
            if len(raw) < raw_length:
                raise IndexError
            else:
                self.suffix_length = suffix_length
                self.suffix = suffix
                self.raw_length = raw_length
                self.raw = raw
                paste = spclipbd.ClipboardContent(read = False)
                paste._suffix = self.suffix
                paste._raw = self.raw
                self.msg_raw = self.msg_raw[1 + suffix_length + 4 + raw_length:]
                self.msg_raw_length -= 1 + suffix_length + 4 + raw_length
                return MessageFromClient(paste)
        except IndexError:
            return None

class MessagePeeker:
    def __init__(self) -> None:
        addr = ipaddress.ip_address(HOST)
        if addr.version == 4:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif addr.version == 6:
            self.server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.server_socket.setblocking(False)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(32)
        self.inputs = [self.server_socket]
        self.parsers = [MessageParser()]
        

    def peek_message(self) -> list:
        loaded_msgs = list()
        rs, _, es = select.select(self.inputs, [], self.inputs)
        pop_idx = list()
        for ri in range(len(self.inputs)):
            if self.inputs[ri] not in rs: continue
            if self.inputs[ri] in es:
                pop_idx.append(ri)
                continue
            if self.inputs[ri] is self.server_socket:
                # 新的客户端连接
                logging.info('New client!')
                conn, addr = self.server_socket.accept()
                logging.info(f'Accept client: {addr}')
                self.inputs.append(conn)
                self.parsers.append(MessageParser())
            else:
                # 已有客户端发来的消息
                logging.info('New msg from client!')
                try:
                    data = self.inputs[ri].recv(4096)
                    logging.info(f'Receive data: {data} with length {len(data)}')
                    if data:
                        msg_from_client = self.parsers[ri].load(data)
                        if msg_from_client is not None:
                            loaded_msgs.append(msg_from_client)
                    else:
                        logging.info(f'Client closed: {self.inputs[ri].getpeername()}')
                        pop_idx.append(ri)
                except ConnectionResetError:
                    # 客户端断开
                    logging.info(f'Client ConnectionResetError')
                    pop_idx.append(ri)
        for ri in sorted(pop_idx, reverse = True):
            logging.info(f'Close: {self.inputs[ri].getpeername()}')
            self.inputs[ri].close()
            self.inputs.pop(ri)
            self.parsers.pop(ri)

        return loaded_msgs

    def broadcast(self, msg:MessageFromClient) -> None:
        logging.info(f'broadcast: {msg.make_msg_to_client()}')
        for cs in self.inputs[1:]:
            try:
                peername = cs.getpeername()
                logging.info(f'broadcast to: {peername[0]}:{peername[1]}')
                threading.Thread(target = sendall, args = (cs, msg.make_msg_to_client()), daemon = True).start()
            except:
                logging.info('broadcast failed, pass.')


class App:
    def __init__(self) -> None:
        self.msg_peeker = MessagePeeker()

    def start_loop(self) -> None:
        while True:
            logging.info('Waiting for loaded_msgs.')
            loaded_msgs = self.msg_peeker.peek_message()
            logging.info(f'len(loaded_msgs) = {len(loaded_msgs)}.')
            if len(loaded_msgs) == 0:
                continue
            self.msg_peeker.broadcast(loaded_msgs[-1])


if __name__ == '__main__':
    logging.basicConfig(
        level = logging.INFO,
        format = '[%(asctime)s %(levelname)s] %(message)s',
        filename = f'log_server.txt',
        filemode = 'w'
    )

    app = App()
    try:
        app.start_loop()
    except KeyboardInterrupt:
        logging.info('KeyboardInterrupt.')
        for s in app.msg_peeker.inputs:
            s.close()
    logging.info('Exit.')
