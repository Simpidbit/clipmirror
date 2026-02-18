import pyperclip
import time
import socket
import sys
import logging

IP = sys.argv[1]
PORT = int(sys.argv[2])


class ClipboardMonitor:
    def __init__(self) -> None:
        self.current_paste = str()

    def destruct(self) -> None:
        pass

    def check_update(self):
        if self.current_paste == str():
            self.current_paste = pyperclip.paste()
            return False
        else:
            new_paste = pyperclip.paste()
            if new_paste != self.current_paste:
                self.current_paste = new_paste
                return True
    # 格式:
    # | ID长度(2字节) | ID | paste长度(4字节) | paste
    def make_msg(self, identity:str) -> bytes:
        msg = int(len(identity)).to_bytes(2, 'big') + \
              identity.encode('utf-8') + \
              int(len(self.current_paste)).to_bytes(4, 'big') + \
              self.current_paste.encode('utf-8')
        return msg


# 报文格式:
# | 四位数字 | 消息
class MessageMonitor:
    def __init__(self) -> None:
        self.paste = str()
        self.raw = bytes()
        self.raw_length = 0

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((IP, PORT))
        self.socket.setblocking(False)

    def destruct(self) -> None:
        self.socket.close()

    def get_paste(self) -> str:
        return self.paste

    def load_raw(self, raw) -> bool:
        self.raw += raw
        self.raw_length += len(raw)
        if self.raw_length >= 4:
            paste_length = int.from_bytes(self.raw[:4], 'big')
        else:
            return False
        
        if len(self.raw) >= 4 + paste_length:
            self.paste = self.raw[4 : 4 + paste_length].decode('utf-8')
            self.raw = self.raw[4 + paste_length:]
            self.raw_length -= 4 + paste_length
            return True
        else:
            return False

    def check_msg(self) -> bool:
        try:
            data = self.socket.recv(4096)
            logging.info(f'Receive data: {data} with length {len(data)}.')

            if not data:
                # Connection was closed
                self.socket.close()
                sys.exit(1)

            return self.load_raw(data)
        except BlockingIOError:
            return False
        except ConnectionResetError:
            self.socket.close()
            sys.exit(3)

    def send_msg(self, msg:bytes) -> None:
        logging.info(f'Send msg: {msg}')
        self.socket.sendall(msg)
        logging.info('Send OK.')

    def get_id(self) -> str:
        sockname = self.socket.getsockname()
        return f'{sockname[0]}:{sockname[1]}'


class EventMonitor:
    def __init__(self) -> None:
        self.clipboard_monitor = ClipboardMonitor()
        self.message_monitor = MessageMonitor()

    def start_loop(self):
        try:
            while True:
                if self.clipboard_monitor.check_update():
                    logging.info(f'Clipboard update: {self.clipboard_monitor.current_paste}')
                    self.message_monitor.send_msg(
                        self.clipboard_monitor.make_msg(self.message_monitor.get_id())
                    )
                elif self.message_monitor.check_msg():
                    logging.info(f'New message from server: {self.message_monitor.get_paste()}')
                    pyperclip.copy(self.message_monitor.get_paste())
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.message_monitor.destruct()
            self.clipboard_monitor.destruct()

if __name__ == '__main__':
    logging.basicConfig(
        level = logging.INFO,
        format = '[%(asctime)s %(levelname)s] %(message)s',
        filename = f'log_client.txt',
        filemode = 'w'
    )

    event_monitor = EventMonitor()
    event_monitor.start_loop()
