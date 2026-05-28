import asyncio
import math
import serial
import serial.tools.list_ports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

app = FastAPI()

# Giao diện Web App
@app.get("/")
async def get_index():
    return FileResponse("index.html")

# API Quét cổng COM thực tế đang cắm trên máy
@app.get("/api/ports")
async def get_ports():
    ports = serial.tools.list_ports.comports()
    port_list = [port.device for port in ports]
    port_list.append("TEST_MÔ_PHỎNG") # Giữ lại mode test phần mềm
    return {"ports": port_list}

# Kênh truyền dữ liệu Real-time
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    port_name = await websocket.receive_text()
    
    try:
        # --- CHẾ ĐỘ 1: CHẠY MÔ PHỎNG (SOFTWARE IN-THE-LOOP) ---
        if port_name == "TEST_MÔ_PHỎNG":
            await websocket.send_json({"type": "status", "msg": "Đang chạy chế độ MÔ PHỎNG...", "color": "#8e44ad"})
            v_bias = -5.0
            while v_bias <= 5.0:
                cap_pf = 10.0 + (5.0 * math.sin(v_bias)) + 0.1
                inv_c2 = 1.0 / (cap_pf ** 2) if cap_pf != 0 else 0
                
                await websocket.send_json({
                    "type": "data", "v_bias": v_bias, "c_pf": cap_pf, "inv_c2": inv_c2
                })
                v_bias += 0.2
                await asyncio.sleep(0.1)
            await websocket.send_json({"type": "status", "msg": "Hoàn thành quét mô phỏng!", "color": "#2980b9"})
            return

        # --- CHẾ ĐỘ 2: KẾT NỐI MẠCH ĐO THỰC TẾ (HARDWARE IN-THE-LOOP) ---
        await websocket.send_json({"type": "status", "msg": f"Đang đồng bộ với phần cứng tại {port_name}...", "color": "#27ae60"})
        
        # Mở cổng Serial (Baudrate 9600, thay đổi nếu code Arduino của bạn khác)
        ser = serial.Serial(port_name, 9600, timeout=1)
        ser.reset_input_buffer() # Xóa sạch bộ đệm chứa rác dữ liệu lúc mới cắm cáp
        
        while True:
            # Kiểm tra xem có dữ liệu trong bộ đệm UART chưa (Non-blocking I/O)
            if ser.in_waiting > 0:
                try:
                    # Đọc 1 dòng từ Arduino gửi lên
                    raw_line = ser.readline().decode('utf-8').strip()
                    
                    # Bộ lọc dữ liệu: Chỉ bắt các dòng đúng định dạng "V_bias | V_out | C"
                    if "|" in raw_line:
                        parts = raw_line.split("|")
                        if len(parts) == 3:
                            v_bias = float(parts[0].strip())
                            v_out = float(parts[1].strip())
                            cap_pf = float(parts[2].strip())
                            
                            # Tính toán vật lý nội suy
                            inv_c2 = 1.0 / (cap_pf ** 2) if cap_pf != 0 else 0
                            
                            # Đẩy JSON qua mạng xuống Trình duyệt
                            await websocket.send_json({
                                "type": "data", 
                                "v_bias": v_bias, 
                                "c_pf": cap_pf, 
                                "inv_c2": inv_c2
                            })
                            
                    # Tín hiệu kết thúc chu trình từ Arduino
                    elif "===" in raw_line or "Hoan thanh" in raw_line:
                        await websocket.send_json({"type": "status", "msg": "Hoàn thành một chu trình đo vật lý!", "color": "#2980b9"})
                        
                except (ValueError, UnicodeDecodeError):
                    # Bỏ qua các chuỗi rác do nhiễu vật lý trên đường truyền cáp đồng
                    pass
            
            # Nhường luồng cho hệ điều hành xử lý các tác vụ mạng khác (Chống treo CPU)
            await asyncio.sleep(0.005) 
            
    except WebSocketDisconnect:
        print("Trình duyệt đã ngắt kết nối WebSocket.")
    except Exception as e:
        await websocket.send_json({"type": "status", "msg": f"Lỗi Giao Tiếp Phần Cứng: {str(e)}", "color": "#e74c3c"})
        if 'ser' in locals() and ser.is_open:
            ser.close()