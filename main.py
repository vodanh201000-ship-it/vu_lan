import sys
import math
import csv
import os
import serial
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QComboBox, QLabel, QTableWidget, 
                             QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import QThread, pyqtSignal, QUrl, Qt
from PyQt5.QtWebEngineWidgets import QWebEngineView

# ================= WORKER THREAD (PRODUCER) =================
# Luồng độc lập chuyên trách đọc dữ liệu từ phần cứng, cách ly hoàn toàn với UI
class SerialReaderWorker(QThread):
    # Định nghĩa luồng tín hiệu an toàn (Thread-safe Signal)
    # Trả về: (v_bias, v_out_psd, cap_pf)
    data_raw_signal = pyqtSignal(float, float, float)
    status_signal = pyqtSignal(str, str) # (Thông điệp, Mã màu CSS)

    def __init__(self, port, baudrate=9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.is_running = True

    def run(self):
        import time, random, math
        self.status_signal.emit("Trạng thái: Đang CHẠY TEST MÔ PHỎNG...", "#8e44ad")
        
        v_bias = -5.0 # Bắt đầu quét từ -5V
        
        while self.is_running and v_bias <= 5.0:
            # 1. Sinh dữ liệu ảo mô phỏng đặc tuyến C-V của Diode
            # Giả lập C tăng khi V_bias tăng (phân cực thuận)
            cap_pf = 10.0 + (5.0 * math.sin(v_bias)) + random.uniform(-0.5, 0.5) 
            v_out_psd = cap_pf * 0.05 / 100 # Giả lập V_out
            
            # 2. Bắn tín hiệu về UI
            self.data_raw_signal.emit(v_bias, v_out_psd, cap_pf)
            
            # 3. Tăng V_bias và tạo độ trễ (100ms mỗi điểm)
            v_bias += 0.2
            time.sleep(0.1) 
            
        self.status_signal.emit("Trạng thái: Hoàn thành quét mô phỏng!", "#2980b9")
    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()


# ================= MAIN UI WINDOW (CONSUMER) =================
class CVSweepMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Hệ thống Đo phân tích Đặc tuyến C-V & Mott-Schottky")
        self.resize(1200, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- CONTROL PANEL ---
        control_layout = QHBoxLayout()
        self.combo_ports = QComboBox()
        self.refresh_ports()
        
        self.btn_connect = QPushButton("Kết nối Máy đo")
        self.btn_connect.clicked.connect(self.toggle_connection)
        
        self.btn_clear = QPushButton("Xóa dữ liệu")
        self.btn_clear.clicked.connect(self.clear_data)

        self.btn_save = QPushButton("Lưu file CSV")
        self.btn_save.clicked.connect(self.save_csv)
        self.btn_save.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        
        self.lbl_status = QLabel("Trạng thái: Chưa kết nối")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #d35400; margin-left: 20px;")

        control_layout.addWidget(QLabel("Chọn cổng COM:"))
        control_layout.addWidget(self.combo_ports)
        control_layout.addWidget(self.btn_connect)
        control_layout.addWidget(self.btn_clear)
        control_layout.addWidget(self.btn_save)
        control_layout.addWidget(self.lbl_status)
        control_layout.addStretch() 
        
        main_layout.addLayout(control_layout)

        # --- DATA & VISUALIZATION PANEL ---
        data_layout = QHBoxLayout()
        
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["V_bias (V)", "V_out (V)", "C (pF)", "1/C² (pF⁻²)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setFixedWidth(420)
        data_layout.addWidget(self.table)
        
        # Nhúng WebEngine điều khiển file index.html
        self.web_view = QWebEngineView()
        html_path = os.path.abspath("index.html")
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))
        data_layout.addWidget(self.web_view)
        
        main_layout.addLayout(data_layout)

    def refresh_ports(self):
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        self.combo_ports.clear()
        for port in ports:
            self.combo_ports.addItem(port.device)

    def toggle_connection(self):
        if self.worker and self.worker.isRunning():
            # Thực hiện ngắt kết nối an toàn
            self.worker.stop()
            self.btn_connect.setText("Kết nối Máy đo")
            self.lbl_status.setText("Trạng thái: Đã ngắt kết nối")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #d35400;")
        else:
            selected_port = self.combo_ports.currentText()
            if not selected_port:
                return
            
            # Khởi tạo và kích hoạt Luồng chạy ngầm độc lập
            self.worker = SerialReaderWorker(selected_port)
            # Kết nối Tín hiệu từ Worker vào Hàm xử lý của UI (Event-Driven mapping)
            self.worker.data_raw_signal.connect(self.process_new_data)
            self.worker.status_signal.connect(self.update_status_ui)
            
            self.worker.start() # Kích hoạt hàm run() của luồng phụ
            self.btn_connect.setText("Ngắt kết nối")

    def update_status_ui(self, message, color_hex):
        self.lbl_status.setText(message)
        self.lbl_status.setStyleSheet(f"font-weight: bold; color: {color_hex}; margin-left: 20px;")

    # Slot nhận dữ liệu an toàn từ Worker Thread truyền sang
    def process_new_data(self, v_bias, v_out_psd, cap_pf):
        # 1. Tính toán toán học tuyến tính
        inv_c2 = 1.0 / (cap_pf ** 2) if cap_pf != 0 else 0
        
        # 2. Cập nhật bảng PyQt UI
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"{v_bias:.2f}"))
        self.table.setItem(row, 1, QTableWidgetItem(f"{v_out_psd:.4f}"))
        self.table.setItem(row, 2, QTableWidgetItem(f"{cap_pf:.3f}"))
        self.table.setItem(row, 3, QTableWidgetItem(f"{inv_c2:.4f}"))
        self.table.scrollToBottom()
        
        # 3. Gửi chuyển tiếp dữ liệu xuống môi trường Chromium (index.html)
        # Hàm runJavaScript là hàm Asynchronous (bất đồng bộ), nó chỉ đẩy lệnh vào hàng đợi IPC
        # và quay lại xử lý việc khác ngay lập tức, không làm trễ luồng nhận tín hiệu phần cứng.
        js_code = f"if(window.receiveDataFromPython) {{ window.receiveDataFromPython({v_bias}, {cap_pf}, {inv_c2}); }}"
        self.web_view.page().runJavaScript(js_code)

    def clear_data(self):
        self.table.setRowCount(0)
        self.web_view.page().runJavaScript("clearCharts();")

    def save_csv(self):
        if self.table.rowCount() == 0:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Lưu file dữ liệu", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(["V_bias (V)", "V_out_PSD (V)", "Capacitance (pF)", "1/C^2 (pF^-2)"])
                for row in range(self.table.rowCount()):
                    writer.writerow([self.table.item(row, col).text() for col in range(4)])

    def closeEvent(self, event):
        # Đảm bảo tắt luồng ngầm an toàn khi đóng ứng dụng để tránh rò rỉ bộ nhớ (Memory leak)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CVSweepMonitor()
    window.show()
    sys.exit(app.exec_())