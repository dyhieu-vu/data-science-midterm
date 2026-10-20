# Dự án giữa kỳ Data Science: chương trình AI và Data Science

## Mục tiêu và phạm vi

Dự án xây dựng tập dữ liệu có thể truy nguyên về các chương trình AI/Data Science trong registry hiện tại, sau đó làm sạch, kiểm tra và mô tả độ phủ dữ liệu. Đơn vị phân tích là **một bản ghi chương trình theo `program_id`**; chương trình/chuyên ngành hoặc phiên bản tuyển sinh khác nhau chỉ được gộp khi có bằng chứng xác nhận cùng thực thể. Snapshot hiện có 20 bản ghi, đều mang quốc gia triển khai `Vietnam`; đây không phải mẫu đại diện cho toàn bộ chương trình tại Việt Nam hay quốc tế. Đối tác cấp bằng nước ngoài không làm thay đổi quốc gia triển khai đã ghi.

## Cấu trúc thư mục chính

- `data/raw/`: registry và dữ liệu đầu vào gốc.
- `data/processed/`: snapshot thu thập, dữ liệu sạch, sổ bằng chứng và báo cáo audit.
- `src/`: collector, audit, cleaner, validator, EDA và dashboard.
- `tests/`: unit tests.
- `reports/eda/`: data dictionary, báo cáo chất lượng, chart eligibility và EDA outputs.
- `index.html`: dashboard tự chứa.

## Môi trường Windows

Khuyến nghị Python 3.12. Mở PowerShell tại thư mục gốc dự án:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Trong Command Prompt, kích hoạt bằng `.venv\Scripts\activate.bat`.

## Chạy dự án

Chạy các lệnh từ thư mục gốc theo thứ tự:

```powershell
python src/collect_data.py
python src/merge_official_evidence.py
python src/clean_data.py
python src/audit_data.py
python src/validate_data.py
python src/eda.py
```

`merge_official_evidence.py` chạy offline sau collector: tổng hợp các thuộc tính có bằng chứng đã xác minh vào `programs_expanded.csv`, giữ các khoảng thời lượng ở cột riêng và dừng nếu phát hiện conflict. Cleaner sau đó tạo `programs_clean.csv`.

Chạy toàn bộ unit tests:

```powershell
python -m unittest discover -s tests -v
```

`collect_data.py` cần mạng để truy cập `robots.txt` và các URL trong registry. Audit, clean, validate và EDA chạy trên file đã lưu, không cần truy cập web. Collector tuân theo robots.txt và có timeout. DNS/lỗi mạng có thể làm request thất bại. `source_error`/`collection_error` mô tả lỗi request hoặc xử lý đã ghi, không chứng minh trang hay chương trình không tồn tại. Khi DNS lỗi, kiểm tra kết nối rồi thử lại có kiểm soát hoặc xác minh thủ công bằng nguồn chính thức; tránh lặp request liên tục.

HTTP 2xx chỉ biểu thị request nhận được response thành công; `content_available` nghĩa là nội dung trang đọc được; `verified_identity` yêu cầu bằng chứng nhận diện chương trình và trường nhưng **không xác minh mọi thuộc tính**; `needs_manual_review` cần kiểm tra danh tính; `source_error` là lỗi thu thập. Mỗi thuộc tính cần bằng chứng riêng tương ứng trong `official_attribute_evidence.csv`.

## EDA và dashboard

`src/eda.py` sinh báo cáo/biểu đồ EDA và gọi builder dashboard. `index.html` dùng HTML/CSS/JavaScript, SVG cho một số biểu đồ cấu trúc và Plotly.js cho Histogram/Boxplot/Violin cùng ba biểu đồ minh họa tương tác. Plotly.js được tải từ CDN nên cần kết nối mạng khi mở dashboard.

Histogram/boxplot/violin dùng tập con thời lượng dạng số đơn có bằng chứng; violin chỉ mang tính khám phá với mẫu nhỏ. Network hiện có 21 liên kết chương trình–học phần từ 5 chương trình có danh sách trích đoạn, không phải 21 chương trình và không phải curriculum đầy đủ. Trong phần phân tích dữ liệu thực, Scatter/hồi quy và heatmap tương quan vẫn bị chặn do chưa đủ cặp số liệu phù hợp cùng đơn vị; line/area thực thiếu các quan sát thời gian lặp lại có thể so sánh. Để minh họa đủ kỹ thuật trực quan hóa theo yêu cầu môn học, dashboard có một khu vực riêng gồm ba biểu đồ Plotly tương tác (Scatter + OLS regression, Correlation Heatmap, Line/Area) dùng dữ liệu tổng hợp được đánh dấu rõ ràng. Dữ liệu minh họa nằm trong `data/processed/synthetic_visualization_demo.csv` và `data/processed/synthetic_time_series_demo.csv`; không trộn vào snapshot thật, không dùng để kết luận về các chương trình đại học và không được mô tả là dữ liệu thu thập từ nguồn.

Giá trị thiếu được giữ NA, không tự điền bằng 0 hoặc suy luận từ tên trường/chương trình. Khoảng thời lượng giữ nguyên dạng khoảng; tổng tín chỉ giữ nguyên hệ được nguồn nêu và không quy đổi. `curriculum_candidate_text` chưa xác minh không được coi là curriculum. Tập dữ liệu nhỏ và phụ thuộc nguồn sẵn có/trạng thái truy cập; kết quả chỉ mô tả snapshot, không khái quát cho toàn bộ Việt Nam hoặc quốc tế.
