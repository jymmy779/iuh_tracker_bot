# Bot LMS IUH - Hệ thống Nhắc nhở Deadline & Báo điểm tự động

Dự án này là một **Dịch vụ dạng SaaS (Software as a Service)** dành cho nhiều người dùng. Bot đóng vai trò như một "Cầu nối" (Middleware) nằm giữa 2 hệ thống:
1. **Hệ thống A:** LMS của trường Đại học Công nghiệp TP.HCM (Moodle).
2. **Hệ thống B:** Telegram (Nơi tương tác trực tiếp với sinh viên).

Bot sẽ lấy dữ liệu từ LMS, phân tích, lưu trữ và gửi thông báo trực tiếp qua Telegram cho từng sinh viên riêng biệt dựa trên tài khoản cá nhân của họ.

---

## 🏗️ 1. Kiến trúc Thư mục và Các Thành phần (Components)

Dự án được chia thành 4 phân hệ chính:

### 🌐 `moodle/` (Phân hệ Giao tiếp với Trường):
- **`auth.py`**: Chịu trách nhiệm nhận MSSV/Mật khẩu của sinh viên và gọi đến trường để đổi lấy một "Chìa khóa" gọi là **Token**.
- **`courses.py`**: Dùng Token để kéo danh sách các môn học (kèm logic tự động lọc ra những môn thuộc học kỳ hiện tại).
- **`assignments.py`**: Dùng Token kéo danh sách các bài tập/deadline chưa nộp.
- **`grades.py`**: Dùng Token kéo chi tiết bảng điểm.

### 💬 `tg_bot/` (Phân hệ Giao tiếp với Telegram):
- **`client.py`**: Chứa các hàm gửi tin nhắn (bắn thông báo) tới một `chat_id` cụ thể của Telegram.
- **`formatter.py`**: Định dạng dữ liệu thô thành các tin nhắn đẹp mắt (có icon, bôi đậm, xuống dòng) và tạo các nút bấm (Inline Keyboard).

### 🗄️ `db/` (Phân hệ Cơ sở dữ liệu):
- **`database.py`**: Quản lý file SQLite cục bộ (`bot_database.sqlite`). Nó có 3 bảng chính:
  - `users`: Lưu `chat_id` (Telegram) và Token (LMS).
  - `assignments`: Lưu trạng thái deadline (đã nhắc 3 ngày chưa, đã đánh dấu nộp chưa) của từng người dùng.
  - `grades`: Lưu vết điểm số cũ để so sánh xem điểm có thay đổi hay không (tránh việc báo điểm cũ bị spam nhiều lần).

### ⚙️ Các File Điều phối (Orchestration):
- **`bot.py`**: Trái tim của chương trình. File này dùng để lắng nghe các lệnh người dùng gõ trên Telegram (như `/login`, `/deadlines`, `/grades`) và phản hồi ngay lập tức.
- **`scheduler.py`**: Khối óc chạy ngầm (Background Job). File này không đợi người dùng gõ lệnh, mà cứ đúng **mỗi 2 tiếng**, nó sẽ tự thức dậy, lặp qua tất cả user trong Database để kiểm tra xem có deadline mới hay điểm mới không.

---

## 🔄 2. Hai Luồng Hoạt Động Cốt Lõi (Core Workflows)

Dự án hoạt động xoay quanh 2 luồng chính:

### Luồng 1: Tương tác trực tiếp (On-Demand)
*Diễn ra ở file `bot.py` khi người dùng chủ động gõ lệnh.*

- **Ví dụ Login:** Sinh viên gõ `/login mssv pass`.
  1. `bot.py` nhận lệnh ➡️ Gọi `moodle/auth.py` để lấy Token.
  2. Nếu lấy Token thành công, gọi `db/database.py` lưu Token + `chat_id` vào Database.
  3. Xóa tin nhắn chứa mật khẩu của user để bảo mật.
  4. Báo đăng nhập thành công.
- **Ví dụ kéo Deadline:** Khi gõ `/deadlines`, Bot móc Token ra từ DB ➡️ Lên Moodle lấy bài ➡️ Trả kết quả cho User qua màn hình chat.

### Luồng 2: Đồng bộ ngầm (Background Sync)
*Diễn ra ở file `scheduler.py`, chạy tự động định kỳ (VD: mỗi 2 giờ).*

1. **Lấy danh sách:** Kéo tất cả User từ bảng `users`.
2. **Xử lý từng User:**
   - **Check Deadline:** Kéo danh sách bài tập từ LMS về. So sánh với bảng `assignments`. Nếu có bài nào cách hạn nộp 7 ngày, 3 ngày, 1 ngày, hoặc 3 tiếng... mà **chưa nộp**, bot gọi `client.py` để tự động gửi tin nhắn nhắc nhở.
   - **Check Điểm:** Kéo bảng điểm của kỳ hiện tại. So sánh với bảng `grades`. Nếu thấy một điểm số trên LMS khác với điểm lưu trong Database, bot gọi `client.py` báo "VỪA CÓ ĐIỂM" kèm theo link tra cứu, rồi ghi đè điểm mới vào Database.

---

## 🛠️ 3. Công nghệ & Thư viện (Tech Stack)

Để hệ thống hoạt động mượt mà cho nhiều người dùng mà không bị "nghẽn mạng", toàn bộ code được viết bằng mô hình **Bất đồng bộ (Asynchronous)**.

- **`python-telegram-bot`**: Thư viện framework chính để tạo bot. Cung cấp Application, CommandHandler (bắt lệnh /), CallbackQueryHandler (bắt sự kiện bấm nút).
- **`httpx`**: Thư viện thay thế cho `requests`. Giúp bot gửi API Request lên server của trường cực nhanh và không bị treo luồng khi mạng chậm.
- **`aiosqlite`**: Thư viện thay thế cho `sqlite3` thông thường, thao tác đọc/ghi Database phi đồng bộ (không chặn các tác vụ khác đang chạy).
- **`APScheduler`**: Thư viện đặt giờ chạy các hàm ngầm (Background Task Scheduling).

---

## 🚀 4. Hướng dẫn Deploy (Miễn phí 100%)

Phiên bản này được thiết kế theo chuẩn Cloud-Native, sử dụng Webhook và PostgreSQL, rất thích hợp để host trên Render (hoặc Koyeb/Railway) kết hợp với Supabase.

### Bước 1: Chuẩn bị Database (Supabase)
1. Đăng ký tài khoản [Supabase](https://supabase.com).
2. Tạo Project mới, vào phần Database Settings để lấy chuỗi kết nối (Database URL).
   - Chuỗi có dạng: `postgresql://postgres.[id]:[password]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`

### Bước 2: Triển khai lên VPS (Ubuntu/Linux)
Code đã được tối ưu siêu nhẹ để chạy ngầm trên VPS (Polling mode) mà không chiếm Port web của bạn.

1. Đăng nhập vào VPS của bạn qua SSH.
2. Clone code về:
   ```bash
   git clone https://github.com/jymmy779/iuh_tracker_bot.git
   cd iuh_tracker_bot
   ```
3. Tạo file `.env` và điền thông tin:
   ```env
   TELEGRAM_TOKEN=token_cua_ban
   DATABASE_URL=link_supabase_cua_ban
   LMS_URL=https://lms.iuh.edu.vn
   ```
4. Cài đặt thư viện:
   ```bash
   pip install -r requirements.txt
   ```
5. Khởi chạy Bot ngầm (chạy mãi mãi ngay cả khi tắt SSH):
   ```bash
   nohup python bot.py > bot.log 2>&1 &
   ```

Vậy là xong! Bot của bạn sẽ chạy 24/7 hoàn toàn an toàn và không lo bị trường chặn IP nhờ chạy qua mạng của VPS.
Để xem log, bạn gõ `tail -f bot.log`. Để tắt bot, gõ `pkill -f "python bot.py"`.
