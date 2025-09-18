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

### 4.1) Chế độ structured và định dạng câu trả lời
- `--structured`: ép model trả lời JSON theo schema, sau đó script kết xuất thành câu trả lời rõ ràng.
- `--style`: `plain` (không bảng), `markdown`, hoặc `strict` (đánh số mục 1., 2., 3. như ví dụ luật). Gợi ý dùng `strict` cho dữ liệu huấn luyện.

Ví dụ structured + strict:
```powershell
python .\generate_dataset.py --model "gpt-oss:20b" --out .\dataset_traffic_strict.csv --domain traffic --auto 50 --structured --retries 2 --style strict --num-ctx 4096 --temperature 0.2 --top-p 0.9 --repeat-penalty 1.1 --seed 42
```

### 4.2) Chạy song song (đa luồng)
- `--workers N`: số luồng gọi mô hình song song (đề xuất 2–4). Nếu thấy chậm hoặc nghẽn GPU/CPU, giảm N.

Ví dụ:
```powershell
python .\generate_dataset.py --model "gpt-oss:20b" --out .\dataset_traffic_strict.csv --domain traffic --auto 100 --structured --style strict --workers 4
```

### 4.3) Chế độ chạy liên tục đến khi dừng
- `--infinite`: tự sinh câu hỏi phức tạp và ghi từng dòng cho đến khi bạn nhấn Ctrl+C.
- `--sleep`: tạm dừng giữa các lượt (giây), mặc định 0.

Ví dụ chạy liên tục (nhấn Ctrl+C để dừng):
```powershell
python .\generate_dataset.py --model "gpt-oss:20b" --out .\dataset_traffic_stream.csv --domain traffic --structured --style strict --workers 2 --num-ctx 4096 --temperature 0.2 --top-p 0.9 --repeat-penalty 1.1 --infinite --sleep 0.0
```

### 5) Gợi ý models
- `llama3.1:8b` (nhẹ, nhanh)
- `qwen2.5:7b` (cân bằng)
- `cnshenyang/qwen3-nothink:30b` (chất lượng cao, cần VRAM lớn)
- `gpt-oss:20b` (chất lượng tốt)
- `gemma3:12b` (ổn định)
- `phi3:mini` (rất nhẹ)

> Lưu ý: Chat model không có bảo đảm chính xác tuyệt đối. Hãy kiểm chứng và bổ sung dẫn chiếu văn bản pháp luật theo nhu cầu.

### 6) Cấu hình cho model lớn (20B-30B)
Model `cnshenyang/qwen3-nothink:30b` cần VRAM cao, khuyến nghị:
- Giảm `--num-ctx` xuống 2048-3072 nếu thiếu VRAM
- Dùng `--workers 1-2` để tránh quá tải
- Tăng `--temperature` lên 0.3-0.4 cho đa dạng hơn

Ví dụ chạy qwen3-nothink 30B:
```powershell
python .\generate_dataset.py --model "cnshenyang/qwen3-nothink:30b" --out .\dataset_qwen3.csv --domain traffic --structured --style strict --workers 2 --num-ctx 3072 --temperature 0.3 --top-p 0.9 --repeat-penalty 1.1 --infinite --sleep 0.0
```


