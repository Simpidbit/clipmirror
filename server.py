import socket
import select
import threading
import sys
import logging

PORT = int(sys.argv[1])

def sendall(s:socket.socket, msg:bytes) -> None:
    logging.info(f'Send {msg} to {s.getpeername()}...')
    try:
        s.sendall(msg)
        logging.info('Send OK.')
    except:
        logging.info(f'Failed to send {msg} to {s.getpeername()}!')

class MessageFromClient:
    def __init__(self, paste:str):
        self.paste = paste

    def make_msg_to_client(self) -> bytes:
        return int(len(self.paste.encode('utf-8'))).to_bytes(4, 'big') + \
               self.paste.encode('utf-8')


class MessageParser:
    def __init__(self) -> None:
        self.raw = bytes()
        self.raw_length = int()

    def load(self, msg:bytes) -> None | MessageFromClient:
        self.raw += msg
        self.raw_length += len(msg)

        try:
            paste_length = int.from_bytes(self.raw[0:4], 'big')

            if paste_length == 0:
                # heart beat
                self.raw = self.raw[4:]
                self.raw_legnth -= 4
                return None

            complete_msg_length = 4 + paste_length
            if len(self.raw) < complete_msg_length:
                raise IndexError
            else:
                paste = self.raw[4 : 4 + paste_length].decode('utf-8')
                self.raw = self.raw[complete_msg_length:]
                self.raw_length -= complete_msg_length
                return MessageFromClient(paste)
        except IndexError:
            return None

class MessagePeeker:
    def __init__(self) -> None:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setblocking(False)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', PORT))
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
                    logging.info(f'Client ConnectionResetError: {self.inputs[ri].getpeername()}')
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
