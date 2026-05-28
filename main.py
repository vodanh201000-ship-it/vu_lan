import sys
import math
import csv
import serial
import serial.tools.list_ports
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QComboBox, QLabel, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QTabWidget, QFileDialog)
from PyQt5.QtCore import QTimer, Qt

class CVSweepMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.serial_port = None
        
        # ================= CÁC CÔNG THỨC VÀ HẰNG SỐ (TỪ ẢNH) =================
        # Các thông số này dựa trên mạch thiết kế (có thể tinh chỉnh lại)
        self.f = 10000.0             # Tần số f = 10 kHz (như trong Proteus)
        self.omega = 2 * math.pi * self.f  # Tần số góc: w = 2 * pi * f
        
        self.V_DUT_AC = 0.05         # Điện áp AC cấp cho DUT (VA = 50mV)
        self.C_F = 100e-12           # Tụ phản hồi C_F = 100pF (Ví dụ)
        self.R_F = 10e6              # Điện trở phản hồi R_F = 10 MOhm (Ví dụ)
        
        self.C0 = 1.0                # Hằng số điện dung C0 (để mô phỏng DUT)
        self.V_bi = 0.7              # Điện áp nội xây V_bi (Built-in potential)
        # =====================================================================

        # Các mảng lưu trữ dữ liệu để vẽ đồ thị
        self.v_bias_data = []
        self.capacitance_data = []
        self.inv_c2_data = []        # Mảng lưu 1/C^2 cho đồ thị phụ
        
        self.initUI()
        
        # Timer để quét Serial mỗi 100ms
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial)

    # --- CÁC HÀM TÍNH TOÁN VẬT LÝ ---
    def calc_theoretical_C_DUT(self, V_R):
        """ Điện dung mô phỏng của DUT: C(V_R) = C0 * sqrt(V_bi / (V_bi + V_R)) """
        if (self.V_bi + V_R) > 0:
            return self.C0 * math.sqrt(self.V_bi / (self.V_bi + V_R))
        return 0

    def calc_Cdut_from_Vout(self, V_out):
        """ 
        Tính điện dung từ Vout của bộ TIA:
        C_DUT = (V_out * C_F / V_DUT_AC) * sqrt(1 + 1/(w * R_F * C_F)^2) 
        """
        wRC = self.omega * self.R_F * self.C_F
        he_so = math.sqrt(1 + 1 / (wRC**2))
        C_DUT = (V_out * self.C_F / self.V_DUT_AC) * he_so
        return C_DUT
    # --------------------------------

    def initUI(self):
        self.setWindowTitle("Hệ thống Đo phân tích Đặc tuyến C-V & Mott-Schottky")
        self.resize(1100, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ================= CONTROL PANEL =================
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

        # ================= DATA PANEL =================
        data_layout = QHBoxLayout()
        
        # 1. Bảng dữ liệu (Table)
        self.table = QTableWidget(0, 4) # Tăng lên 4 cột để hiển thị thêm 1/C^2
        self.table.setHorizontalHeaderLabels(["V_bias (V)", "V_out (V)", "C (pF)", "1/C² (pF⁻²)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setFixedWidth(420)
        data_layout.addWidget(self.table)
        
        # 2. Khu vực Đồ thị (Dùng Tabs để chuyển đổi C-V và 1/C^2)
        self.tabs = QTabWidget()
        
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        # --- Đồ thị 1: Đặc tuyến C-V ---
        self.plot_cv = pg.PlotWidget()
        self.plot_cv.setTitle("Đặc tuyến Điện dung - Điện áp (C-V)", color="b", size="14pt")
        self.plot_cv.setLabel('left', 'Điện dung C (pF)', color='red', size="12pt")
        self.plot_cv.setLabel('bottom', 'Điện áp phân cực V_bias (V)', color='blue', size="12pt")
        self.plot_cv.showGrid(x=True, y=True)
        self.curve_cv = self.plot_cv.plot(pen=pg.mkPen('b', width=2), symbol='o', symbolBrush='r')
        self.tabs.addTab(self.plot_cv, "Đồ thị C-V")

        # --- Đồ thị 2: Đặc tuyến Mott-Schottky (1/C^2) ---
        self.plot_ms = pg.PlotWidget()
        self.plot_ms.setTitle("Đặc tuyến Mott-Schottky (Y = 1/C²)", color="purple", size="14pt")
        self.plot_ms.setLabel('left', '1 / C² (pF⁻²)', color='purple', size="12pt")
        self.plot_ms.setLabel('bottom', 'Điện áp phân cực V_bias (V)', color='blue', size="12pt")
        self.plot_ms.showGrid(x=True, y=True)
        self.curve_ms = self.plot_ms.plot(pen=pg.mkPen('g', width=2), symbol='s', symbolBrush='purple')
        self.tabs.addTab(self.plot_ms, "Đồ thị Mott-Schottky (1/C²)")

        data_layout.addWidget(self.tabs)
        main_layout.addLayout(data_layout)

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        self.combo_ports.clear()
        for port in ports:
            self.combo_ports.addItem(port.device)

    def toggle_connection(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.btn_connect.setText("Kết nối Máy đo")
            self.timer.stop()
            self.lbl_status.setText("Trạng thái: Đã ngắt kết nối")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #d35400;")
        else:
            try:
                selected_port = self.combo_ports.currentText()
                self.serial_port = serial.Serial(selected_port, 9600, timeout=1)
                self.btn_connect.setText("Ngắt kết nối")
                self.timer.start(100)
                self.lbl_status.setText("Trạng thái: Đang chờ dữ liệu quét...")
                self.lbl_status.setStyleSheet("font-weight: bold; color: #27ae60;")
            except Exception as e:
                self.lbl_status.setText("Lỗi mở cổng COM!")

    def clear_data(self):
        self.table.setRowCount(0)
        self.v_bias_data.clear()
        self.capacitance_data.clear()
        self.inv_c2_data.clear()
        self.curve_cv.setData(self.v_bias_data, self.capacitance_data)
        self.curve_ms.setData(self.v_bias_data, self.inv_c2_data)

    def save_csv(self):
        if not self.v_bias_data:
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "Lưu file dữ liệu", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(["V_bias (V)", "V_out_PSD (V)", "Capacitance (pF)", "1/C^2 (pF^-2)"])
                for row in range(self.table.rowCount()):
                    v = self.table.item(row, 0).text()
                    vout = self.table.item(row, 1).text()
                    c = self.table.item(row, 2).text()
                    inv_c2 = self.table.item(row, 3).text()
                    writer.writerow([v, vout, c, inv_c2])
            self.lbl_status.setText(f"Đã lưu thành công: {path.split('/')[-1]}")

    def read_serial(self):
        if self.serial_port and self.serial_port.in_waiting > 0:
            try:
                raw_line = self.serial_port.readline().decode('utf-8').strip()
                
                if "Bat dau" in raw_line or "V_bias" in raw_line or "---" in raw_line:
                    return
                if "===" in raw_line:
                    self.lbl_status.setText("Trạng thái: Đã hoàn thành 1 chu trình quét!")
                    return
                
                if "|" in raw_line:
                    parts = raw_line.split("|")
                    if len(parts) == 3:
                        v_bias = float(parts[0].strip())
                        v_out_psd = float(parts[1].strip())
                        
                        # Bạn có thể dùng hàm tính toán Python ở đây thay vì lấy từ Arduino nếu muốn:
                        # cap_pf = self.calc_Cdut_from_Vout(v_out_psd) * 1e12 # Đổi từ F sang pF
                        # Nhưng hiện tại ta vẫn ưu tiên lấy giá trị Arduino gửi lên cho đồng bộ:
                        cap_pf = float(parts[2].strip())
                        
                        # --- Tính toán đồ thị phụ: Y = 1 / C^2 ---
                        if cap_pf != 0:
                            inv_c2 = 1.0 / (cap_pf ** 2)
                        else:
                            inv_c2 = 0
                        
                        # 1. Thêm vào bảng (Table)
                        row_position = self.table.rowCount()
                        self.table.insertRow(row_position)
                        self.table.setItem(row_position, 0, QTableWidgetItem(f"{v_bias:.2f}"))
                        self.table.setItem(row_position, 1, QTableWidgetItem(f"{v_out_psd:.4f}"))
                        self.table.setItem(row_position, 2, QTableWidgetItem(f"{cap_pf:.3f}"))
                        self.table.setItem(row_position, 3, QTableWidgetItem(f"{inv_c2:.4f}"))
                        self.table.scrollToBottom()
                        
                        # 2. Thêm vào mảng đồ thị và vẽ lại (Graph)
                        self.v_bias_data.append(v_bias)
                        self.capacitance_data.append(cap_pf)
                        self.inv_c2_data.append(inv_c2)
                        
                        self.curve_cv.setData(self.v_bias_data, self.capacitance_data)
                        self.curve_ms.setData(self.v_bias_data, self.inv_c2_data)
                        
            except ValueError:
                pass
            except Exception as e:
                print(f"Lỗi đọc dữ liệu: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CVSweepMonitor()
    window.show()
    sys.exit(app.exec_())