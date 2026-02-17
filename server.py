import socket
import select
import threading
import sys

PORT = int(sys.argv[1])

def sendall(s:socket.socket, msg:bytes) -> None:
    s.sendall(msg)

class MessageFromClient:
    def __init__(self, hostid:str, paste:str):
        self.hostid = hostid
        self.paste = paste

    def make_msg_to_client(self) -> bytes:
        return int(len(self.paste)).to_bytes(4) + self.paste.encode('utf-8')


class MessageParser:
    def __init__(self) -> None:
        self.raw = bytes()
        self.raw_length = int()

    def load(self, msg:bytes) -> None | MessageFromClient:
        self.raw += msg
        self.raw_length += len(msg)

        try:
            hostid_length = int.from_bytes(self.raw[:2])
            hostid = self.raw[2 : 2 + hostid_length].decode('utf-8')
            paste_length = int.from_bytes(self.raw[2 + hostid_length : 2 + hostid_length + 4])
            paste = self.raw[2 + hostid_length + 4:].decode('utf-8')

            complete_msg_length = 2 + hostid_length + 4 + paste_length
            if len(self.raw) < complete_msg_length:
                raise IndexError
            else:
                self.raw = self.raw[complete_msg_length:]
                self.raw_length -= complete_msg_length
                return MessageFromClient(hostid, paste)
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
        for ri in range(len(self.inputs)):
            if not (self.inputs[ri] in rs): continue
            if self.inputs[ri] is self.server_socket:
                # 新的客户端连接
                conn, addr = self.server_socket.accept()
                conn.setblocking(False)
                self.inputs.append(conn)
                self.parsers.append(MessageParser())
            else:
                # 已有客户端发来的消息
                try:
                    data = self.inputs[ri].recv(4096)
                    if data:
                        msg_from_client = self.parsers[ri].load(self.inputs[ri].recv(4096))
                        if msg_from_client is not None:
                            loaded_msgs.append(msg_from_client)
                    else:
                        raise ConnectionResetError
                except ConnectionResetError:
                    # 客户端断开
                    self.inputs[ri].close()
                    self.inputs.pop(ri)
                    self.parsers.pop(ri)

        return loaded_msgs

    def broadcast(self, msg:MessageFromClient) -> None:
        for cs in self.inputs[1:]:
            peername = cs.getpeername()
            peerid = f'{peername[0]}:{peername[1]}'
            if peerid != msg.hostid:
                threading.Thread(target = sendall, args = (cs, msg.make_msg_to_client())).start()


class App:
    def __init__(self) -> None:
        self.msg_peeker = MessagePeeker()

    def start_loop(self) -> None:
        while True:
            loaded_msgs = self.msg_peeker.peek_message()
            if len(loaded_msgs) == 0:
                continue
            self.msg_peeker.broadcast(loaded_msgs[-1])


if __name__ == '__main__':
    app = App()
    app.start_loop()
