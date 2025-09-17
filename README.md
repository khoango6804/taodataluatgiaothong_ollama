## Tạo dataset Hỏi/Đáp luật Việt Nam bằng Ollama

### 1) Yêu cầu
- Đã cài Ollama và đang chạy service (`ollama serve` chạy ngầm trên Windows sau khi cài)
- Đã pull một model: ví dụ `ollama pull llama3.1:8b`
- Python 3.9+

### 2) Cài thư viện Python
```powershell
cd K:\taodataluat_ollama
python -m pip install -r requirements.txt
```

### 3) Chuẩn bị câu hỏi
- Tạo file `questions.txt` (UTF-8), mỗi dòng là một câu hỏi.
- Ví dụ có sẵn trong repo.

### 4) Tạo CSV
```powershell
# Giới hạn miền giao thông (mặc định):
python .\generate_dataset.py --model "llama3.1:8b" --questions .\questions.txt --out .\dataset.csv --domain traffic

# Hoặc dùng miền tổng quát:
python .\generate_dataset.py --model "llama3.1:8b" --questions .\questions.txt --out .\dataset.csv --domain general
```

Mặc định nếu không truyền `--out`, chương trình sẽ tạo tên dạng `dataset_YYYYmmdd_HHMM.csv`.

Các cột của CSV:
- `question`: câu hỏi
- `answer`: câu trả lời sinh từ model

Tùy chọn thêm:
- `--system`: system prompt để điều chỉnh cách trả lời (mặc định đã tối ưu cho giao thông VN nếu chọn `--domain traffic`).
- `--domain`: `traffic` (mặc định) để chỉ trả lời trong phạm vi luật giao thông; `general` cho phạm vi rộng.

### 5) Gợi ý models
- `llama3.1:8b` (nhẹ, nhanh)
- `qwen2.5:7b`
- `phi3:mini`

> Lưu ý: Chat model không có bảo đảm chính xác tuyệt đối. Hãy kiểm chứng và bổ sung dẫn chiếu văn bản pháp luật theo nhu cầu.


