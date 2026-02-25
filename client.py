import pyperclip
import spclipbd
import time
import socket
import sys
import logging
import ipaddress
import hashlib
from server import MessageParser, MessageFromClient

HOST = set([info[4][0] for info in socket.getaddrinfo(sys.argv[1], None)]).pop()
PORT = int(sys.argv[2])
IP_VER = ipaddress.ip_address(HOST).version

class ClipboardMonitor:
    def __init__(self) -> None:
        self.current_paste: spclipbd.ClipboardContent | None = None
        self.current_paste_digest: str | None = None

    def destruct(self) -> None:
        pass

    def check_update(self) -> bool:
        if self.current_paste == None:
            self.current_paste = spclipbd.ClipboardContent()
            suffix_digest = hashlib.sha256(self.current_paste.get_suffix().encode('utf-8')).hexdigest()
            raw_digest = hashlib.sha256(self.current_paste.get_raw()).hexdigest()
            self.current_paste_digest = suffix_digest + raw_digest
            return False
        else:
            new_paste = spclipbd.ClipboardContent()
            new_suffix_digest = hashlib.sha256(new_paste.get_suffix().encode('utf-8')).hexdigest()
            new_raw_digest = hashlib.sha256(new_paste.get_raw()).hexdigest()
            new_digest = new_suffix_digest + new_raw_digest

            if new_digest != self.current_paste_digest:
                self.current_paste = new_paste
                self.current_paste_digest = new_digest
                return True
        return False

    # 格式:
    # | paste类型长度(1字节) | paste类型 | paste长度(4字节) | paste |
    def make_msg(self) -> bytes:
        if isinstance(self.current_paste, spclipbd.ClipboardContent):
            msg = int(len(self.current_paste.get_suffix())).to_bytes(1, 'big') + \
                  self.current_paste.get_suffix().encode('utf-8') + \
                  int(len(self.current_paste.get_raw())).to_bytes(4, 'big') + \
                  self.current_paste.get_raw()
            return msg
        else:
            raise RuntimeError


class MessageMonitor:
    def __init__(self) -> None:
        self.paste: spclipbd.ClipboardContent = spclipbd.ClipboardContent(read = False)
        self.parser: MessageParser = MessageParser()
        self.msg_raw = bytes()
        self.msg_raw_length = 0
        
        if IP_VER == 4:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif IP_VER == 6:
            self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

        try:
            self.socket.connect((HOST, PORT))
            self.socket.setblocking(False)
        except TimeoutError:
            self.reconnect()

    def destruct(self) -> None:
        self.socket.close()

    def get_paste(self) -> spclipbd.ClipboardContent:
        return self.paste

    def load_raw(self, raw: bytes) -> bool:
        result = self.parser.load(raw)
        if result is None:
            return False
        else:
            self.paste = result.paste
            return True

    def reconnect(self) -> None:
        self.socket.close()
        while True:
            time.sleep(3)
            if IP_VER == 4:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            elif IP_VER == 6:
                self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            try:
                self.socket.connect((HOST, PORT))
                self.socket.setblocking(False)
                logging.info(f'Reconnected to {HOST}:{PORT}')
                break
            except KeyboardInterrupt:
                logging.info('Exit by KeyboardInterrupt.')
                sys.exit(0)
            except:
                logging.info(f'Reconnect to {HOST}:{PORT} failed, retry...')

    def check_msg(self) -> bool:
        try:
            data = self.socket.recv(4096)
            logging.info(f'Receive data: {data} with length {len(data)}.')

            if not data:
                # Connection was closed
                self.reconnect()
                return False

            return self.load_raw(data)
        except (BlockingIOError, TimeoutError):
            # On macOS, non-blocking socket.recv() may raise TimeoutError (errno 60)
            # instead of BlockingIOError when no data is available.
            # On Linux, BlockingIOError (errno 11) is typically raised.
            # This difference is due to platform-specific socket implementations.
            return False
        except ConnectionResetError:
            self.reconnect()
            return False
        except OSError as e:
            # Handle socket errors like EADDRNOTAVAIL (errno 49) after system wake
            # or other connection issues after sleep
            logging.warning(f'Socket error: {e}, reconnecting...')
            self.reconnect()
            return False
        except:
            logging.info('Unknown exception')
            return False

    def send_msg(self, msg:bytes) -> None:
        logging.info(f'Send msg: {msg}')
        try:
            self.socket.sendall(msg)
            logging.info('Send OK.')
        except:
            self.reconnect()
            logging.info('Send canceled but reconnected.')

class EventMonitor:
    def __init__(self) -> None:
        self.clipboard_monitor = ClipboardMonitor()
        self.message_monitor = MessageMonitor()

    def start_loop(self) -> None:
        idx = 0
        try:
            while True:
                if self.clipboard_monitor.check_update():
                    logging.info(f'Clipboard update: {self.clipboard_monitor.current_paste}')
                    self.message_monitor.send_msg(
                        self.clipboard_monitor.make_msg()
                    )
                if self.message_monitor.check_msg():
                    logging.info(f'New message from server: {self.message_monitor.get_paste()}')
                    paste = self.message_monitor.get_paste()
                    spclipbd.copy_to_clipboard(paste.get_suffix(), paste.get_raw())
                if idx > 300:
                    # heart beat
                    idx = 0
                    self.message_monitor.send_msg(b'\xff\xff')
                time.sleep(0.1)
                idx += 1
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
