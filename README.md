# File_Sharing
P2P file sharing (single-file Python program) - Uses TCP/IP sockets - Basic Tkinter GUI - Each instance is a peer: it runs a server to share files and can connect to other peers to list/download
<img width="832" height="711" alt="image" src="https://github.com/user-attachments/assets/92cafb81-c7f5-40ce-b0ce-bc96bcd3da1f" />

🖥️ Máy 1 (làm Server)

Mở Terminal/Command Prompt.

Di chuyển vào thư mục chứa file:

cd Desktop


Chạy chương trình:

python3 P2P_File_Sharing_TCPIP.py


Trong GUI, chọn thư mục chia sẻ (Share Folder).

Start Server → nhập IP của máy này (ví dụ 192.168.1.10) và port (ví dụ 9009).

Nhấn Start.

🖥️ Máy 2 (làm Client)

Cũng chạy chương trình:

python3 P2P_File_Sharing_TCPIP.py


Trong GUI, nhập IP của máy 1 (server), ví dụ 192.168.1.10 và port 9009.

Nhấn "List Files" để xem danh sách file chia sẻ.

Chọn file và nhấn "Download".
