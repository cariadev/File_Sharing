"""
P2P file sharing (single-file Python program)
- Uses TCP/IP sockets
- Basic Tkinter GUI
- Each instance is a peer: it runs a server to share files and can connect to other peers to list/download

How to use:
1) Run on 2 separate machines:
   - On machine A: run this script, choose a folder to share, note the "Listen IP" and "Port" shown (or use 0.0.0.0 and publicly routable IP).
   - On machine B: run this script, in "Connect to peer" put A's IP and port, click "List files" and download.
   Make sure firewalls allow the port and any routers have port forwarding as needed.

2) Run on 1 machine with a VM:
   - Configure VM networking so host and guest can reach each other (host-only, bridged, or port forwarding).
   - Use the VM's IP (or 127.0.0.1 with port forwarding) in the "Connect to peer" field.

Notes:
- Protocol (text-based simple):
    LIST\n  -> server responds with file names separated by '\n' and an extra '\n' termination
    GET <filename>\n -> server responds with 'SIZE <bytes>\n' then raw bytes
    QUIT\n -> closes connection
- The GUI is intentionally minimal for teaching/demo purposes.

Limitations & Security:
- No authentication or encryption. DON'T use on untrusted networks.
- Filename validation is minimal.

"""

import socket
import threading
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time

BUFFER_SIZE = 4096


def safe_filename(name):
    # prevent path traversal
    return os.path.basename(name)


class PeerServer(threading.Thread):
    def __init__(self, host, port, shared_folder, on_log=None):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.shared_folder = os.path.abspath(shared_folder)
        self.on_log = on_log or (lambda *args, **kwargs: None)
        self._sock = None
        self._stop = threading.Event()

    def log(self, *args):
        self.on_log('SERVER:', *args)

    def run(self):
        self.log(f"Starting server on {self.host}:{self.port}, sharing {self.shared_folder}")
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.listen(5)
        except Exception as e:
            self.log('Failed to bind/listen:', e)
            return

        while not self._stop.is_set():
            try:
                self._sock.settimeout(1.0)
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except Exception as e:
                self.log('Accept error:', e)
                break

            self.log('Connection from', addr)
            t = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
            t.start()

        self.log('Server stopped')

    def stop(self):
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except: pass

    def list_shared_files(self):
        files = []
        for entry in os.listdir(self.shared_folder):
            path = os.path.join(self.shared_folder, entry)
            if os.path.isfile(path):
                files.append(entry)
        return files

    def handle_client(self, conn, addr):
        with conn:
            conn.settimeout(10)
            try:
                data = b''
                while True:
                    line = self._recvline(conn)
                    if not line:
                        break
                    cmd = line.strip()
                    self.log(f'Recv {cmd} from {addr}')
                    if cmd.upper() == 'LIST':
                        files = self.list_shared_files()
                        response = '\n'.join(files) + '\n\n'
                        conn.sendall(response.encode('utf-8'))
                    elif cmd.upper().startswith('GET '):
                        fname = cmd[4:]
                        fname = safe_filename(fname)
                        fpath = os.path.join(self.shared_folder, fname)
                        if not os.path.exists(fpath) or not os.path.isfile(fpath):
                            conn.sendall(b'ERROR File not found\n')
                            continue
                        size = os.path.getsize(fpath)
                        conn.sendall(f'SIZE {size}\n'.encode('utf-8'))
                        # send raw bytes
                        with open(fpath, 'rb') as f:
                            while True:
                                chunk = f.read(BUFFER_SIZE)
                                if not chunk:
                                    break
                                conn.sendall(chunk)
                        self.log(f'Sent file {fname} to {addr}')
                    elif cmd.upper() == 'QUIT':
                        break
                    else:
                        conn.sendall(b'ERROR Unknown command\n')
            except Exception as e:
                self.log('Client handler error:', e)

    def _recvline(self, conn):
        # receive until \n
        data = b''
        while True:
            ch = conn.recv(1)
            if not ch:
                break
            data += ch
            if ch == b'\n':
                break
        return data.decode('utf-8') if data else ''


class PeerClient:
    def __init__(self, on_log=None):
        self.on_log = on_log or (lambda *args, **kwargs: None)

    def log(self, *args):
        self.on_log('CLIENT:', *args)

    def list_files(self, host, port, timeout=5):
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(b'LIST\n')
            # read until double newline
            data = b''
            s.settimeout(2)
            while True:
                try:
                    part = s.recv(BUFFER_SIZE)
                    if not part:
                        break
                    data += part
                    if b'\n\n' in data:
                        break
                except socket.timeout:
                    break
            text = data.decode('utf-8', errors='ignore')
            files = [ln for ln in text.splitlines() if ln.strip()]
            self.log(f'Found {len(files)} files on {host}:{port}')
            return files

    def download_file(self, host, port, filename, dest_folder, progress_callback=None, timeout=10):
        filename = safe_filename(filename)
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(f'GET {filename}\n'.encode('utf-8'))
            # read header line
            header = self._recvline(s)
            if not header:
                raise RuntimeError('No response from server')
            if header.startswith('ERROR'):
                raise RuntimeError(header)
            if not header.startswith('SIZE '):
                raise RuntimeError('Bad response: ' + header)
            size = int(header.split(' ', 1)[1].strip())
            out_path = os.path.join(dest_folder, filename)
            received = 0
            start = time.time()
            with open(out_path, 'wb') as f:
                while received < size:
                    chunk = s.recv(min(BUFFER_SIZE, size - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    if progress_callback:
                        progress_callback(received, size)
            elapsed = time.time() - start
            self.log(f'Downloaded {filename} to {out_path} ({received}/{size} bytes) in {elapsed:.2f}s')
            if received != size:
                raise RuntimeError('Incomplete download')
            return out_path

    def _recvline(self, sock):
        data = b''
        while True:
            ch = sock.recv(1)
            if not ch:
                break
            data += ch
            if ch == b'\n':
                break
        return data.decode('utf-8') if data else ''


class App:
    def __init__(self, root):
        self.root = root
        root.title('P2P File Share (TCP)')
        self.server = None
        self.client = PeerClient(on_log=self.log)

        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky='nsew')
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # Shared folder selection
        folder_frame = ttk.LabelFrame(main, text='Shared folder')
        folder_frame.grid(row=0, column=0, sticky='ew')
        self.shared_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.shared_var, width=50).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(folder_frame, text='Browse', command=self.browse_folder).grid(row=0, column=1, padx=5)

        # Server controls
        server_frame = ttk.LabelFrame(main, text='Server')
        server_frame.grid(row=1, column=0, sticky='ew', pady=6)
        ttk.Label(server_frame, text='Listen IP:').grid(row=0, column=0)
        self.listen_ip = tk.StringVar(value='0.0.0.0')
        ttk.Entry(server_frame, textvariable=self.listen_ip, width=18).grid(row=0, column=1)
        ttk.Label(server_frame, text='Port:').grid(row=0, column=2)
        self.listen_port = tk.IntVar(value=9009)
        ttk.Entry(server_frame, textvariable=self.listen_port, width=8).grid(row=0, column=3)
        ttk.Button(server_frame, text='Start Server', command=self.start_server).grid(row=0, column=4, padx=6)
        ttk.Button(server_frame, text='Stop Server', command=self.stop_server).grid(row=0, column=5)

        # Client controls
        client_frame = ttk.LabelFrame(main, text='Connect to peer')
        client_frame.grid(row=2, column=0, sticky='ew')
        ttk.Label(client_frame, text='Host:').grid(row=0, column=0)
        self.peer_host = tk.StringVar(value='127.0.0.1')
        ttk.Entry(client_frame, textvariable=self.peer_host, width=18).grid(row=0, column=1)
        ttk.Label(client_frame, text='Port:').grid(row=0, column=2)
        self.peer_port = tk.IntVar(value=9009)
        ttk.Entry(client_frame, textvariable=self.peer_port, width=8).grid(row=0, column=3)
        ttk.Button(client_frame, text='List files', command=self.list_files).grid(row=0, column=4, padx=6)
        ttk.Button(client_frame, text='Download selected', command=self.download_selected).grid(row=0, column=5)

        # Files list
        files_frame = ttk.LabelFrame(main, text='Files on peer')
        files_frame.grid(row=3, column=0, sticky='nsew', pady=6)
        files_frame.columnconfigure(0, weight=1)
        self.files_list = tk.Listbox(files_frame, height=10)
        self.files_list.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(files_frame, orient='vertical', command=self.files_list.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.files_list.configure(yscrollcommand=scrollbar.set)

        # Progress and logs
        bottom = ttk.Frame(main)
        bottom.grid(row=4, column=0, sticky='ew')
        ttk.Label(bottom, text='Download progress:').grid(row=0, column=0)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(bottom, variable=self.progress_var, maximum=100)
        self.progress.grid(row=0, column=1, sticky='ew', padx=6)
        bottom.columnconfigure(1, weight=1)

        self.log_text = tk.Text(main, height=8)
        self.log_text.grid(row=5, column=0, sticky='nsew', pady=6)
        main.rowconfigure(5, weight=1)

        # initial shared folder
        self.shared_var.set(os.path.abspath('.'))

        # closure handling
        root.protocol('WM_DELETE_WINDOW', self.on_close)

    def browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.shared_var.set(d)

    def start_server(self):
        if self.server:
            messagebox.showinfo('Info', 'Server already running')
            return
        folder = self.shared_var.get()
        if not os.path.isdir(folder):
            messagebox.showerror('Error', 'Shared folder invalid')
            return
        host = self.listen_ip.get()
        port = int(self.listen_port.get())
        self.server = PeerServer(host, port, folder, on_log=self.log)
        self.server.start()
        self.log('Server thread started')

    def stop_server(self):
        if self.server:
            self.server.stop()
            self.server = None
            self.log('Server stopped')
        else:
            self.log('No server running')

    def list_files(self):
        host = self.peer_host.get()
        port = int(self.peer_port.get())
        try:
            files = self.client.list_files(host, port)
            self.files_list.delete(0, tk.END)
            for f in files:
                self.files_list.insert(tk.END, f)
        except Exception as e:
            messagebox.showerror('Error', str(e))
            self.log('Error listing files:', e)

    def download_selected(self):
        sel = self.files_list.curselection()
        if not sel:
            messagebox.showinfo('Info', 'No file selected')
            return
        filename = self.files_list.get(sel[0])
        dest = filedialog.askdirectory(title='Choose destination folder')
        if not dest:
            return
        host = self.peer_host.get()
        port = int(self.peer_port.get())

        def progress_cb(received, total):
            pct = (received / total) * 100 if total else 0
            self.progress_var.set(pct)

        def dl_thread():
            try:
                self.client.download_file(host, port, filename, dest, progress_callback=progress_cb)
                messagebox.showinfo('Done', f'Download complete: {filename}')
            except Exception as e:
                messagebox.showerror('Error', str(e))
                self.log('Download error:', e)
            finally:
                self.progress_var.set(0)

        t = threading.Thread(target=dl_thread, daemon=True)
        t.start()

    def log(self, *args):
        txt = ' '.join(map(str, args)) + '\n'
        try:
            self.log_text.insert('end', txt)
            self.log_text.see('end')
        except Exception:
            pass

    def on_close(self):
        if self.server:
            self.server.stop()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
