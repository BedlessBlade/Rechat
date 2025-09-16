
from copy import deepcopy as copy
import socket, threading, datetime, json, shutil, sys

def getLogin():
    try:
        with open("cache", "r") as f:
            f.seek(0)
            contents = f.readlines()
        contents = [i.strip() for i in contents]
        return contents[0], contents[1], int(contents[2])
    except (FileNotFoundError,Exception):
        print("Cache not found or corrupted.")
        user = input("Username> ")
        print(f"Name> {user}")
        serverip = input("Server (default: bedless.xyz)>")
        if serverip.strip():
            print(f"Using given ip> {serverip}")
        else:
            print("Using ip> bedless.xyz")
            serverip = "bedless.xyz"
        with open("cache", "w") as f:
            f.write(user.strip() + "\n")
            f.write(serverip.strip() + "\n")
            f.write("50000\n")
        return user, serverip, 50000

class Terminal:
    def __init__(self):
        self.original_flags = None
        self.input_buffer = ""
        self.initialized = False

    def finalize_linux_io(self):
        if sys.platform != "linux": return 2
        if not self.initialized: return 1
        self.termios.tcsetattr(sys.stdin, self.termios.TCSANOW, self.original_flags)
        self.initialized = False
        return 0

    def init_linux_io(self):
        if sys.platform != "linux": return 2
        if self.initialized: return 1
        self.termios = __import__("termios")
        flags = self.termios.tcgetattr(sys.stdin)
        self.original_flags = copy(flags)
        flags[0] = flags[0] & ~(self.termios.IGNBRK | self.termios.BRKINT | self.termios.PARMRK | self.termios.ISTRIP | self.termios.INLCR | self.termios.IGNCR | self.termios.ICRNL | self.termios.IXON)
        flags[1] = flags[1] & ~ self.termios.OPOST
        flags[2] = flags[2] & ~(self.termios.CSIZE | self.termios.PARENB)
        flags[2] = flags[2] | self.termios.CS8
        flags[3] = flags[3] & ~(self.termios.ECHO | self.termios.ECHONL | self.termios.ICANON | self.termios.ISIG | self.termios.IEXTEN)
        self.termios.tcsetattr(sys.stdin, self.termios.TCSANOW, flags)
        self.initialized = True
        return 0
    
    def readline(self, flush=False, update=None):
        if flush:
            sys.stdin.flush()
            self.input_buffer = ""
        if sys.platform != "linux":
            return input()
        if "\n" in self.input_buffer:
            data, self.input_buffer = self.input_buffer.split("\n", 1)
            return data
        while True:
            char = sys.stdin.read(1)
            if char == "\n": break
            self.input_buffer += char
            if update != None: update()
        data = self.input_buffer
        self.input_buffer = ""
        return data


class Main:
    def __init__(self):
        self.sock = None
        self.username = None
        self.host = None
        self.port = None
        self.messages = []
        self.receiving_thread = None
        self.current_line = 1
        self.twidth, self.theight = shutil.get_terminal_size()
        self.terminal = Terminal()
    
    def main(self):

        self.username, self.host, self.port = getLogin()

        print(f"Got: {self.username}@{self.host}:{self.port}")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))

        self.sock.sendall((self.username + "\n").encode())

        prompt = self.sock.recv(1024).decode().strip()
        if prompt == "PASSWORD?":
            password = input("Password> ").strip()
            self.sock.sendall((password + "\n").encode())
        elif prompt == "SET PASSWORD>":
            password = input("Set a new password> ").strip()
            self.sock.sendall((password + "\n").encode())
            print(self.sock.recv(1024).decode().strip())
        
        print("Connected.")
        print("\n" * self.theight)
        self.drawUi()
        self.terminal.init_linux_io()

        self.receiving_thread = threading.Thread(target=self.receive, daemon=True)
        self.receiving_thread.start()

        while True:
            msg = self.terminal.readline(update=self.drawUi)
            if not msg:
                break
            timestamp = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            data = json.dumps([timestamp, self.username, msg])
            self.send(data)
            self.drawUi()
        
        self.terminal.finalize_linux_io()
    
    def disconnect(self, message=None, error=True):
        print("Error occured, disconnecting!" if error else "Disconnecting.")
        try:
            self.sock.close()
        except Exception as err:
            print("Error disconnecting!")
            raise err
        if error: raise Exception(message)

    def receive(self):
        while True:
            length = 0
            length_length = 0
            while True:
                data = self.sock.recv(1)
                if not data: self.disconnect("Receive error.")
                length |= (data << (7 * length_length))
                length_length += 1
                if (data & 0x80) == 0: break
            data = b""
            while len(data) < length:
                data_chunk = self.sock.recv(min(length - len(data), 2048))
                if not data_chunk: self.disconnect("Receive error.")
                data += data_chunk
            if not data:
                continue
            try:
                data = data.decode("utf-8")
            except Exception as err:
                continue
            try:
                data = json.loads(data)
                if len(data) == 3:
                    self.messages.append(f"[{str(data[0])}] <{str(data[1])}> {data[2]}")
                else:
                    data = json.dumps(data)
                    raise Exception
            except Exception:
                self.messages.append(data)
            
            self.drawUi()

    def drawUi(self):
        print("\x1b[2J", end="")
        total_rows = sum([(len(message) // self.twidth) + 1 for message in self.messages])
        while total_rows > (self.theight - 3):
            self.messages = self.messages[1:]
            total_rows = sum([(len(message) // self.twidth) + 1 for message in self.messages])
        current_row = 1
        for message in self.messages:
            rows_needed = (len(message) // self.twidth) + 1
            print(f"\x1b[{current_row};1H{message}", end="")
            current_row += rows_needed
        print(f"\x1b[{self.theight};1H> {self.terminal.input_buffer}", end="")
        sys.stdout.flush()


    def send(self, data):
        encoed_data = data.encode("utf-8")
        data_length = len(encoed_data)
        encoded_length = bytearray(0)
        encoed_length.append(data_length & 0x7f)
        data_length >>= 7
        while data_length > 0:
            encoded_length[-1] |= 0x80
            encoded_length.append(data_length & 0x7f)
            data_length >>= 7
        encoded_length = bytes(encoded_length)
        packet = encoded_length + encoed_data
        self.sock.send(packet)

if __name__ == "__main__": Main().main()
