

2. Chuẩn bị Môi trường (Dependencies)
Yêu cầu máy tính phải cài đặt sẵn Python 3.8 trở lên. Mở Terminal (Command Prompt / PowerShell / VS Code Terminal) tại thư mục chứa code và chạy lệnh sau để cài đặt toàn bộ thư viện cần thiết:

cài cái này trên terminal: copy nguyên dòng bên dưới vào terminal
pip install fastapi uvicorn websockets pyserial

3. Khởi động Máy chủ (Backend)
Bắt buộc phải chạy Backend trước khi thao tác trên giao diện. Tại thư mục dự án, chạy lệnh:

Bash
uvicorn server:app --reload
Lưu ý: Cờ --reload giúp máy chủ tự động khởi động lại nếu bạn chỉnh sửa code trong file server.py. Khi thấy Terminal báo Uvicorn running on http://127.0.0.1:8000, máy chủ đã sẵn sàng.

4. Giao diện & Test Hệ thống (Frontend)
Mở trình duyệt web (Khuyên dùng Chrome/Edge) và truy cập vào địa chỉ:
👉 http://localhost:8000

Hệ thống hỗ trợ 2 chế độ vận hành chính:

Chế độ 1: Test Mô Phỏng (Software-in-the-Loop)
Dùng để kiểm thử đường truyền mạng và UI khi không có phần cứng.

Nhấn F5 để hệ thống quét lại danh sách thiết bị.

Tại Dropdown chọn cổng, chọn TEST_MÔ_PHỎNG.

Bấm Kết Nối Thiết Bị. Hệ thống sẽ giả lập các đặc tuyến hình sin để test khả năng render đồ thị.

Chế độ 2: Chạy Mạch Thực Tế (Hardware-in-the-Loop)
Dùng khi lấy dữ liệu trực tiếp từ mạch Arduino.

Cắm cáp USB nối mạch vào máy tính.

Nhấn F5 trên trình duyệt để Backend quét lại cổng USB mới.

Chọn cổng COM tương ứng của mạch (VD: COM3, COM4 trên Windows hoặc /dev/ttyUSB0 trên Linux).

Bấm Kết Nối Thiết Bị. Dữ liệu sẽ tự động đồng bộ theo chu kỳ quét của mạch.

5. ⚠️ Các Lưu ý Kỹ thuật Quan Trọng (Troubleshooting)
Lỗi "Access Denied" (Từ chối quyền truy cập cổng COM):
Cổng COM của hệ điều hành có tính độc quyền. Nếu một phần mềm khác (như Serial Monitor của Arduino IDE) đang mở cổng này, Backend Python sẽ bị văng lỗi. Giải pháp: Tắt cửa sổ Serial Monitor của Arduino IDE trước khi bấm kết nối trên Web.

Dữ liệu trả về bị rác (Ký tự lạ, dấu ?):
Do tốc độ Baudrate giữa phần cứng và phần mềm không khớp. Kiểm tra dòng ser = serial.Serial(port_name, 9600) trong file server.py và đảm bảo con số 9600 giống hệt với lệnh Serial.begin(...) trong code vi điều khiển.

Đồ thị không hiển thị:
Kiểm tra kết nối Internet của máy tính, vì thư viện Chart.js đang được kéo về từ CDN. Nếu máy tính ở phòng Lab không có mạng, cần tải file chart.js về thư mục dự án và sửa đường dẫn <script> trong file HTML thành đường dẫn cục bộ.