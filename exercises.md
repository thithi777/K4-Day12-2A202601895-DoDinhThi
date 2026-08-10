# Phiếu Phản Ánh — K4 Ngày 12

> **Bài làm cá nhân.** Trả lời bằng lời của chính bạn, dựa trên những gì bạn
> quan sát được khi chạy code — không sao chép đáp án của người khác.
>
> Cách trả lời: thay dòng hướng dẫn bằng câu trả lời.
> `grade.py` đếm số câu đã trả lời (15 điểm cho 10 câu).
>
> Họ và tên: Đỗ Đình Thi  Mã học viên: 2A202601895

---

### Câu 1 — Fail fast (CP1)

Trong `Settings`, `api_token` không có giá trị mặc định nên app chết ngay khi
khởi động nếu thiếu biến môi trường. Hãy mô tả một tình huống cụ thể mà việc
"chết sớm" này cứu bạn, so với việc để mặc định `"changeme"`.

Giả sử bạn deploy ứng dụng lên Cloud (Railway/Render) nhưng quên thiết lập biến môi trường `API_TOKEN` trong Dashboard:
- **Nếu để mặc định `"changeme"`:** App vẫn khởi động bình thường mà không báo lỗi. Hệ thống chạy trên Production với token công khai `"changeme"`. Kẻ tấn công hoặc bot tự động có thể gọi API chat với token này, gây lộ dữ liệu và làm phát sinh chi phí hàng nghìn USD hóa đơn LLM mà bạn không hề hay biết cho đến khi nhận hóa đơn cuối tháng.
- **Khi dùng Fail Fast (không có mặc định):** App ngắt ngay lập tức khi vừa khởi chạy (`ValidationError: api_token Field required`) và không phục vụ request nào. Lỗi hiện ngay trên màn hình logs deploy, giúp lập trình viên phát hiện và khắc phục ngay lập tức trước khi bất kỳ người dùng nào truy cập.

---

### Câu 2 — Log cho máy đọc (CP1)

Chạy service và gọi `/chat` vài lần. Dán một dòng log JSON bạn thu được, rồi
nêu **hai** việc bạn làm được với dòng log đó mà `print("đã trả lời xong")`
không làm được.

Dòng log JSON thu được:
```json
{"event": "chat_completed", "severity": "INFO", "ts": "2026-08-10T16:30:00.123456+00:00", "client_id": "sv01", "prompt_tokens": 15, "completion_tokens": 42, "usd_cost": 0.00015}
```

Hai việc làm được với log JSON mà `print()` thông thường không làm được:
1. **Lọc, truy vấn và phân tích tự động trên Cloud (Cloud Logging / Datadog / ELK):** Nhờ cấu trúc JSON chuẩn hóa với trường `severity` (viết hoa) và `client_id`, hệ thống quản lý log có thể dễ dàng lọc (ví dụ: *"lọc các request có `usd_cost > 0.001`"* hoặc *"đếm tổng số token client `sv01` đã dùng hôm nay"*). Lệnh `print()` thông thường chỉ ra chuỗi không cấu trúc, bắt buộc phải đọc bằng mắt người.
2. **Cảnh báo và giám sát chi phí theo thời gian thực (Real-time Alerting):** Có thể thiết lập hệ thống cảnh báo (Metric Alerts) tự động dựa trên các trường số trong JSON (`usd_cost`, `prompt_tokens`) để bắn thông báo Slack/Email nếu phát hiện chi phí tăng đột biến trong 5 phút.

---

### Câu 3 — Kích thước image (CP2)

Build cả hai phiên bản và ghi lại số đo thật:

```bash
docker build -f <Dockerfile-1-stage> -t chat:single .
docker build -t chat:multi .
docker images | grep chat
```

| Bản | Dung lượng |
|-----|-----------|
| 1 stage (bản đầu) | 1.8 GB |
| Multi-stage | 280 MB |

Giải thích: phần dung lượng chênh lệch đó là những gì?

Phần dung lượng chênh lệch (~1.5 GB) giữa hai bản bao gồm:
1. **Các công cụ biên dịch và thư viện build (Build dependencies/Compilers):** Stage `builder` chứa `build-essential`, `gcc`, `g++`, `make`, header files của C/C++ và các file wheel tạm được tải về trong quá trình `pip install`.
2. **Cache của trình quản lý gói:** Thư mục cache của pip (`~/.cache/pip`) và các package nén chưa được giải nén.
3. **Image nền (Base image):** Bản 1-stage dùng `python:3.11` chứa đầy đủ hệ điều hành Debian với hàng trăm gói tiện ích hệ thống không cần thiết, trong khi bản Multi-stage dùng `python:3.11-slim` chỉ chứa bộ thư viện tối thiểu đủ để chạy Python.

---

### Câu 4 — Thứ tự lệnh trong Dockerfile (CP2)

Sửa một ký tự trong `app/main.py` rồi build lại. Với Dockerfile của bạn, những
layer nào được dùng lại từ cache, layer nào phải chạy lại? Nếu bạn đặt
`COPY . .` lên trước `RUN pip install` thì kết quả khác thế nào?

- **Các layer được dùng lại từ cache:** Các layer từ đầu Dockerfile cho đến trước lệnh `COPY app/ app/`, bao gồm base image `python:3.11-slim`, `COPY requirements.txt .`, và `RUN pip install --prefix=/install -r requirements.txt`.
- **Các layer phải chạy lại:** Layer `COPY app/ app/` và tất cả các layer phía sau nó (vì Docker phát hiện nội dung thư mục `app/` đã bị thay đổi checksum).
- **Nếu đặt `COPY . .` trước `RUN pip install`:** Mỗi khi sửa bất kỳ 1 ký tự code nào trong `app/main.py`, Docker sẽ làm mất hiệu lực (invalidate) cache của layer `COPY . .` và tất cả các layer sau nó. Do đó, Docker sẽ bắt buộc phải chạy lại toàn bộ lệnh `RUN pip install`, tải lại tất cả thư viện từ Internet, làm thời gian build bị kéo dài từ vài giây lên vài phút mỗi lần build.

---

### Câu 5 — Vì sao không chạy bằng root (CP2)

Container mặc định chạy bằng root. Mô tả chuỗi sự kiện dẫn từ "một lỗ hổng
trong code Python của bạn" tới "kẻ tấn công có quyền cao trên máy host", và
lệnh `USER` cắt đứt chuỗi đó ở chỗ nào.

- **Chuỗi sự kiện tấn công khi chạy root:**
  1. Ứng dụng Python có lỗ hổng (ví dụ: Arbitrary Code Execution qua `eval()` hoặc `pickle.loads()`).
  2. Kẻ tấn công lợi dụng lỗ hổng để thực thi lệnh hệ thống bên trong Container.
  3. Vì Container chạy bằng user `root` (UID 0), kẻ tấn công chiếm quyền `root` bên trong Container.
  4. Kẻ tấn công khai thác lỗ hổng thoát khỏi container (Container Breakout) để truy cập hệ thống file của máy Host.
  5. Vì UID 0 trong Container tương đương UID 0 (root) trên máy Host, kẻ tấn công lập tức có toàn quyền điều khiển tối cao trên máy Host của bạn.
- **Vị trí lệnh `USER appuser` cắt đứt chuỗi:** Lệnh `USER appuser` chuyển quyền của process sang user thường (UID 10001) ngay ở bước 3. Ngay cả khi chiếm được ứng dụng Python, kẻ tấn công chỉ có quyền hạn hạn chế của `appuser` bên trong container, không thể sửa đổi file hệ thống container và không thể nâng quyền lên root máy host.

---

### Câu 6 — Bearer token (CP3)

Vì sao 401 phải kèm header `WWW-Authenticate: Bearer`? Và vì sao ta trả **cùng
một** thông báo lỗi cho cả ba trường hợp (thiếu header, sai scheme, sai token)
thay vì nói rõ sai ở đâu cho người dùng dễ sửa?

- **Vì sao kèm `WWW-Authenticate: Bearer`:** Đây là quy định bắt buộc của chuẩn **HTTP/RFC 6750**. Khi server trả về `401 Unauthorized`, header `WWW-Authenticate: Bearer` thông báo cho Client/Trình duyệt biết chính xác phương thức xác thực mà API yêu cầu là gì (Bearer Token) để Client tự động gửi lại request hợp lệ.
- **Vì sao trả cùng một thông báo lỗi:** Để ngăn chặn kẻ tấn công thực hiện kỹ thuật **User/Token Enumeration (Dò tìm lỗ hổng/Token)**. Nếu trả về thông báo khác nhau (ví dụ: *"Sai scheme"* vs *"Token không tồn tại"*), kẻ tấn công sẽ dựa vào thông báo phản hồi để phân biệt được trường hợp nào gửi đúng định dạng header và trường hợp nào đoán đúng token, từ đó thu hẹp phạm vi dò quét. Trả cùng một thông báo giúp bảo vệ an toàn cho API.

---

### Câu 7 — Token bucket (CP3)

Với `capacity=10`, `refill_per_minute=10`: một client im lặng 10 phút rồi gửi
liên tiếp. Nó gửi được bao nhiêu request trước khi bị 429? Nếu bỏ đoạn
`min(capacity, ...)` trong `available()` thì con số đó thành bao nhiêu, và tại sao?

- **Số request gửi được trước khi bị 429:** **10 request**. Vì sức chứa tối đa của xô (`capacity`) bị chặn ở mức 10 token. Dù client im lặng 10 phút (lẽ ra tích được $10 \times 10 = 100$ token), xô vẫn chỉ chứa tối đa 10 token.
- **Nếu bỏ đoạn `min(capacity, ...)`:** Con số đó sẽ thành **100 request** (hoặc bùng nổ tích lũy theo thời gian im lặng).
- **Giải thích:** Thiếu hàm `min(capacity, ...)`, xô không có trần nạp. Client im lặng 10 phút sẽ tích lũy 100 token và có thể bắn dồn dập 100 request trong 1 giây, gây quá tải (Spike/Burst traffic) đánh sập dịch vụ backend — làm mất hoàn toàn tác dụng kiểm soát lưu lượng của Token Bucket.

---

### Câu 8 — Ngân sách theo ngày (CP3)

So sánh hạn mức $30/tháng với hạn mức $1/ngày cho cùng một client. Giả sử có sự
cố khiến một client gọi liên tục từ 2h sáng. Với mỗi cách, thiệt hại tối đa là
bao nhiêu và service tự hồi phục khi nào?

- **Hạn mức $30/tháng:**
  * **Thiệt hại tối đa:** **$30.0** (Client sẽ đốt sạch toàn bộ ngân sách cả tháng của tài khoản chỉ trong vài giờ từ 2h sáng).
  * **Hồi phục:** Service bị khóa đến **đầu tháng sau** (phải chờ đến ngày 1 của tháng tiếp theo mới tự hồi phục, hoặc cần quản trị viên can thiệp thủ công).
- **Hạn mức $1/ngày:**
  * **Thiệt hại tối đa:** **$1.0** (Thiệt hại do sự cố bị giới hạn xuống mức tối thiểu 1/30 ngân sách).
  * **Hồi phục:** Service tự động hồi phục vào **00:00 UTC sáng hôm sau** (khi key Redis `spend:<client>:<YYYY-MM-DD>` tự động chuyển sang ngày mới mà không cần ai can thiệp).

---

### Câu 9 — /healthz khác /readyz (CP4)

Nếu gộp hai endpoint làm một và cho nó kiểm tra Redis, chuyện gì xảy ra với cụm
3 container khi Redis mất kết nối 30 giây? Trả lời theo đúng thứ tự sự kiện.

Thứ tự sự kiện xảy ra thảm họa (Cascading Failure):
1. **0s:** Redis gặp sự cố ngắt kết nối trong 30 giây.
2. **5s:** Orchestrator (Kubernetes/Docker) gọi Liveness probe (lúc này đã gộp) vào Container A, B, C và thấy kiểm tra Redis thất bại.
3. **10s:** Orchestrator đánh giá cả 3 Container đều đã "chết" nên lập tức tiêu diệt (kill) và ra lệnh **khởi động lại (restart) toàn bộ 3 Container**.
4. **15s–25s:** Cụm 3 Container liên tục bị restart vòng lặp (CrashLoopBackOff), tốn rất nhiều tài nguyên CPU/RAM để khởi chạy lại app nhưng vẫn không thể kết nối Redis.
5. **30s:** Khi Redis vừa bình phục, toàn bộ 3 Container vẫn đang trong quá trình bị restart/khởi động chưa xong, dẫn đến toàn bộ dịch vụ bị **sập hoàn toàn (Total Downtime)** kéo dài hơn nhiều so với 30s ban đầu.

---

### Câu 10 — Deploy thật (CP5)

Ghi lại **một** lỗi bạn gặp khi deploy lên cloud (build fail, health check
timeout, sai REDIS_URL, app không đọc `$PORT`...): thông báo lỗi là gì, bạn
tìm ra nguyên nhân bằng cách nào, và sửa ra sao?

- **Thông báo lỗi gặp phải:** `Network > Healthcheck failure (00:30)` và HTTP `500 Internal Server Error` khi truy cập `/readyz` trên Railway.
- **Cách tìm ra nguyên nhân:** Đọc trang **Deploy Logs** trên Railway Dashboard và kiểm tra kết quả cURL `/readyz`. Phát hiện Uvicorn khởi chạy bị crash hoặc ném exception do biến `API_TOKEN` không có mặc định trong `Settings` (chưa set trên Variables tab) và lệnh `startCommand` trong `railway.toml` dùng nháy đơn `'...'` làm biến `$PORT` không được shell giải nén (`ValueError: invalid literal for int() with base 10: '$PORT'`).
- **Cách sửa:** Sửa file `railway.toml` bỏ lệnh `startCommand` lỗi để Railway tự dùng `CMD` trong Dockerfile (`CMD ["sh", "-c", "exec uvicorn..."]`), đồng thời khai báo đầy đủ các biến môi trường (`API_TOKEN`, `REDIS_URL`, `BUCKET_CAPACITY`,...) trong tab **Variables** trên Railway Dashboard và bấm **Redeploy**.
