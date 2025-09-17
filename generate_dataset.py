import csv
import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict

try:
    import ollama  # type: ignore
except Exception as exc:
    raise SystemExit(
        "Missing dependency 'ollama'. Install with: pip install ollama"
    ) from exc


def read_prompts_file(prompts_path: str) -> List[str]:
    if not os.path.exists(prompts_path):
        return []
    with open(prompts_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    return [line for line in lines if line]


def ask_ollama(
    model_name: str,
    question: str,
    system_prompt: str = "",
    options: Dict[str, object] | None = None,
) -> str:
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": question})

    response = ollama.chat(model=model_name, messages=messages, options=options or {})
    content = response.get("message", {}).get("content", "").strip()
    return content


def build_json_instruction(domain: str) -> str:
    domain_line = (
        "CHỈ trong phạm vi luật giao thông Việt Nam (ưu tiên đường bộ)."
        if domain == "traffic"
        else "Trong phạm vi pháp luật Việt Nam."
    )
    return (
        f"{domain_line}\n"
        "Trả lời DUY NHẤT bằng JSON thuần (không Markdown, không bảng, không gạch đầu dòng) theo schema sau, không thêm văn bản ngoài JSON.\n"
        "YÊU CẦU: với mỗi vi phạm hãy đưa khung phạt tiền (fine_min_vnd, fine_max_vnd) và số tháng tước GPLX nếu có;\n"
        "đồng thời trong 'summary' phải có câu tổng hợp kiểu: 'Nếu vi phạm đồng thời, tiền phạt được cộng dồn (tổng từ X đến Y đồng), và có nguy cơ bị tước GPLX tối đa Z tháng.'\n"
        "{\n"
        "  \"question\": string,\n"
        "  \"violations\": [ { \"name\": string, \"details\": string } ],\n"
        "  \"citations\": [ { \"law\": string, \"article\": string, \"clause\": string } ],\n"
        "  \"penalties\": [ { \"violation\": string, \"fine_min_vnd\": number, \"fine_max_vnd\": number, \"license_suspension_months\": number | 0 } ],\n"
        "  \"summary\": string\n"
        "}\n"
        "Nếu câu hỏi ngoài phạm vi, trả về JSON: {\"summary\": \"Ngoài phạm vi giao thông\", \"violations\":[], \"citations\":[], \"penalties\":[], \"question\": q}."
    )


def _strip_tables(text: str) -> str:
    # Loại bỏ dấu '|' và tiêu đề bảng nếu còn sót
    lines = []
    for raw in text.splitlines():
        if raw.strip().startswith("|") or "|" in raw:
            raw = raw.replace("|", " ")
        lines.append(raw)
    return "\n".join(lines)


def render_answer_from_json(payload: Dict[str, object], style: str) -> str:
    lines: List[str] = []
    question = str(payload.get("question", "")).strip()
    if question:
        lines.append(f"Câu hỏi: {question}")
    lines.append("1) Hành vi vi phạm:")
    violations = payload.get("violations", []) or []
    if not violations:
        lines.append("- Không xác định vi phạm hoặc ngoài phạm vi giao thông." if style == "markdown" else "* Không xác định vi phạm hoặc ngoài phạm vi giao thông.")
    else:
        for v in violations:  # type: ignore
            name = str(v.get("name", "")).strip()
            details = str(v.get("details", "")).strip()
            bullet = "-" if style == "markdown" else "*"
            lines.append(f"{bullet} {name}: {details}")

    lines.append("\n2) Căn cứ pháp lý:")
    citations = payload.get("citations", []) or []
    if citations:
        for c in citations:  # type: ignore
            law = str(c.get("law", "")).strip()
            article = str(c.get("article", "")).strip()
            clause = str(c.get("clause", "")).strip()
            cite = ", ".join([p for p in [law, article, clause] if p])
            if cite:
                bullet = "-" if style == "markdown" else "*"
                lines.append(f"{bullet} {cite}")

    lines.append("\n3) Mức phạt áp dụng:")
    penalties = payload.get("penalties", []) or []
    if penalties:
        for p in penalties:  # type: ignore
            vio = str(p.get("violation", "")).strip()
            fmin = p.get("fine_min_vnd", 0)
            fmax = p.get("fine_max_vnd", 0)
            months = int(p.get("license_suspension_months", 0) or 0)
            span = f"{int(fmin):,}–{int(fmax):,} VND" if fmax else f"{int(fmin):,} VND"
            extra = f", tước GPLX {months} tháng" if months else ""
            bullet = "-" if style == "markdown" else "*"
            lines.append(f"{bullet} {vio}: phạt {span}{extra}")

    summary = str(payload.get("summary", "")).strip()
    if summary:
        lines.append("\n4) Tổng hợp:")
        lines.append(summary)

    final_text = "\n".join(lines)
    if style != "markdown":
        final_text = _strip_tables(final_text)
    return final_text


def render_strict_answer(payload: Dict[str, object]) -> str:
    question = str(payload.get("question", "")).strip()
    citations = payload.get("citations", []) or []
    penalties = payload.get("penalties", []) or []
    violations = payload.get("violations", []) or []

    # Intro line
    basis_hint = "Luật Giao thông đường bộ Việt Nam"
    decree_mentions: List[str] = []
    for c in citations:  # type: ignore
        law = str(c.get("law", ""))
        if law:
            decree_mentions.append(law)
    if decree_mentions:
        basis_hint += ", " + ", ".join(sorted(set(decree_mentions)))

    parts: List[str] = []
    if question:
        parts.append(f"Đối với tình huống: {question}")
    parts.append(
        f"Theo {basis_hint}, xử lý như sau:"
    )

    # Map penalties by violation name for easy lookup
    name_to_pen: Dict[str, Dict[str, object]] = {}
    for p in penalties:  # type: ignore
        name = str(p.get("violation", "")).strip()
        if name:
            name_to_pen[name.lower()] = p

    # Numbered sections
    total_min = 0
    total_max = 0
    max_susp = 0
    for idx, v in enumerate(violations or [], start=1):  # type: ignore
        vname = str(v.get("name", "")).strip()
        vdet = str(v.get("details", "")).strip()
        parts.append(f"{idx}. {vname}")
        if vdet:
            parts.append(vdet)
        p = name_to_pen.get(vname.lower(), {})
        fmin = int(p.get("fine_min_vnd", 0) or 0)
        fmax = int(p.get("fine_max_vnd", 0) or 0)
        months = int(p.get("license_suspension_months", 0) or 0)
        if fmin or fmax:
            span = f"{fmin:,} – {fmax:,} đồng" if fmax else f"{fmin:,} đồng"
            parts.append(f"Mức phạt tiền: từ {span}.")
            total_min += fmin
            total_max += fmax if fmax else fmin
        if months:
            parts.append(f"Hình phạt bổ sung: có thể bị tước Giấy phép lái xe {months} tháng.")
            if months > max_susp:
                max_susp = months

    # If there are general citations, add a concise basis line
    if citations:
        basis_lines: List[str] = []
        for c in citations:  # type: ignore
            law = str(c.get("law", "")).strip()
            article = str(c.get("article", "")).strip()
            clause = str(c.get("clause", "")).strip()
            cite = ", ".join([p for p in [law, article, clause] if p])
            if cite:
                basis_lines.append(cite)
        if basis_lines:
            parts.append("Căn cứ: " + "; ".join(basis_lines) + ".")

    summary = str(payload.get("summary", "")).strip()
    if summary:
        parts.append(summary)

    # Combined penalty note
    if total_min or total_max or max_susp:
        comb = "Nếu vi phạm đồng thời, tiền phạt được cộng dồn"
        if total_min or total_max:
            if total_min and total_max and total_max >= total_min:
                comb += f" (tổng khoảng {total_min:,} – {total_max:,} đồng)"
            elif total_min:
                comb += f" (tối thiểu {total_min:,} đồng)"
        if max_susp:
            comb += f", và có nguy cơ bị tước GPLX tối đa {max_susp} tháng."
        else:
            comb += "."
        parts.append(comb)

    text = "\n".join(parts)
    return _strip_tables(text)


def synthesize_complex_question(model_name: str, domain: str, options: Dict[str, object] | None) -> str:
    domain_scaffold = (
        "trong PHẠM VI LUẬT GIAO THÔNG VIỆT NAM (đường bộ là chính)"
        if domain == "traffic"
        else "trong phạm vi pháp luật Việt Nam"
    )
    system_prompt = (
        "Bạn là chuyên gia xây dựng dữ liệu hỏi đáp pháp lý. "
        f"Hãy tạo duy nhất 1 câu hỏi tình huống phức tạp {domain_scaffold}. "
        "Câu hỏi phải chứa ÍT NHẤT 2 hành vi vi phạm giao thông trong cùng tình huống, "
        "mô tả rõ bối cảnh (thời gian/địa điểm/loại đường/phương tiện). "
        "Chỉ TRẢ VỀ CÂU HỎI, không thêm chú thích hay đánh số."
    )

    response = ollama.chat(
        model=model_name,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "Tạo câu hỏi."}],
        options=options or {},
    )
    return response.get("message", {}).get("content", "").strip()


def generate_dataset(
    model_name: str,
    questions: List[str],
    output_csv: str,
    system_prompt: str = (
        "Bạn là trợ lý pháp lý Việt Nam. Trả lời ngắn gọn, chính xác, dẫn chiếu "
        "căn cứ pháp lý (tên văn bản, điều/khoản nếu có). Nếu không chắc, nói rõ."
    ),
    options: Dict[str, object] | None = None,
    enforce_structured: bool = False,
    retries: int = 0,
    domain: str = "traffic",
    style: str = "plain",
    workers: int = 1,
) -> None:
    def generate_answer_for_question(q: str) -> str:
        try:
            if enforce_structured:
                attempt = 0
                payload = None
                json_instruction = build_json_instruction(domain)
                while attempt <= max(retries, 0):
                    attempt += 1
                    raw = ask_ollama(
                        model_name,
                        f"{json_instruction}\n\nQ: {q}",
                        system_prompt,
                        options,
                    )
                    try:
                        payload = json.loads(raw)
                        break
                    except Exception:
                        if attempt > max(retries, 0):
                            payload = {"question": q, "summary": raw, "violations": [], "citations": [], "penalties": []}
                            break
                if style == "strict":
                    return render_strict_answer(payload)  # type: ignore
                return render_answer_from_json(payload, style)  # type: ignore
            else:
                analysis_hint = (
                    "Trả lời theo cấu trúc:\n"
                    "1) Phân tích hành vi\n2) Căn cứ pháp lý\n3) Mức phạt áp dụng\n4) Tổng hợp."
                )
                full_prompt = q if not system_prompt else f"{q}\n\n{analysis_hint}"
                return ask_ollama(model_name, full_prompt, system_prompt, options)
        except Exception as e:
            return f"[Lỗi gọi mô hình: {e}]"
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question", "answer"])  # header
        try:
            f.flush()
            os.fsync(f.fileno())
        except Exception:
            pass
        if workers and workers > 1:
            lock = threading.Lock()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_q = {pool.submit(generate_answer_for_question, q): q for q in questions}
                done = 0
                for future in as_completed(future_to_q):
                    q = future_to_q[future]
                    ans = future.result()
                    with lock:
                        writer.writerow([q, ans])
                        try:
                            f.flush(); os.fsync(f.fileno())
                        except Exception:
                            pass
                    done += 1
                    print(f"{done}/{len(questions)} ✓")
        else:
            for idx, q in enumerate(questions, start=1):
                ans = generate_answer_for_question(q)
                writer.writerow([q, ans])
                try:
                    f.flush(); os.fsync(f.fileno())
                except Exception:
                    pass
                print(f"{idx}/{len(questions)} ✓")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Vietnamese law Q/A dataset using Ollama"
    )
    parser.add_argument(
        "--model",
        default="llama3.1:8b",
        help="Tên model đã được 'ollama pull' (ví dụ: llama3.1:8b)",
    )
    parser.add_argument(
        "--questions",
        default="questions.txt",
        help="Đường dẫn file chứa danh sách câu hỏi (mỗi dòng 1 câu)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Đường dẫn file CSV đầu ra. Mặc định: dataset_YYYYmmdd_HHMM.csv",
    )
    parser.add_argument(
        "--system",
        default="",
        help="System prompt tuỳ chọn để điều chỉnh phong cách trả lời",
    )
    parser.add_argument(
        "--domain",
        choices=["general", "traffic"],
        default="traffic",
        help="Miền nội dung. 'traffic' giới hạn trong luật giao thông VN",
    )
    parser.add_argument(
        "--auto",
        type=int,
        default=0,
        help="Tự sinh N câu hỏi complex (bỏ qua --questions nếu > 0)",
    )
    parser.add_argument(
        "--structured",
        action="store_true",
        help="Bắt mô hình trả lời JSON để dựng lại câu trả lời rõ ràng",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Số lần retry khi JSON không hợp lệ",
    )
    parser.add_argument(
        "--style",
        choices=["plain", "markdown", "strict"],
        default="plain",
        help="Định dạng câu trả lời: plain (không bảng), markdown, hoặc strict (đánh số mục)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Số luồng gọi mô hình song song (đề xuất 2-4). 1 = tuần tự",
    )
    parser.add_argument(
        "--infinite",
        action="store_true",
        help="Chạy liên tục cho tới khi nhấn Ctrl+C (tự sinh câu hỏi)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Tạm dừng giữa các lượt (giây) khi chạy --infinite",
    )
    # Generation options for larger models
    parser.add_argument("--num-ctx", type=int, default=4096, help="Ngữ cảnh tối đa (tokens)")
    parser.add_argument("--temperature", type=float, default=0.2, help="Độ sáng tạo (0-1)")
    parser.add_argument("--top-p", type=float, default=0.9, help="Nucleus sampling (0-1)")
    parser.add_argument("--repeat-penalty", type=float, default=1.1, help="Phạt lặp lại")
    parser.add_argument("--seed", type=int, default=0, help="Seed tái lập kết quả (0: ngẫu nhiên)")

    args = parser.parse_args()

    if args.infinite:
        questions = []
    elif args.auto > 0:
        questions = [
            synthesize_complex_question(args.model, args.domain, None)
            for _ in range(args.auto)
        ]
    else:
        questions = read_prompts_file(args.questions)
        if not questions:
            example = (
                "Không tìm thấy câu hỏi. Tạo file 'questions.txt' (UTF-8), mỗi dòng 1 câu hỏi.\n"
                "Ví dụ:\n- Nếu đi xe máy không đội mũ bảo hiểm và vượt đèn đỏ thì bị xử lý thế nào?\n"
            )
            raise SystemExit(example)

    out_path = args.out or f"dataset_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    if args.system:
        system_prompt = args.system
    else:
        if args.domain == "traffic":
            system_prompt = (
                "Bạn là trợ lý pháp lý Việt Nam, CHỈ trả lời về lĩnh vực luật giao thông "
                "(đường bộ, đường sắt, đường thủy nội địa, hàng hải, hàng không trong phạm vi pháp luật VN). "
                "Nếu câu hỏi ngoài phạm vi giao thông, hãy trả lời đúng một dòng: 'Ngoài phạm vi giao thông'. "
                "Câu trả lời cần ngắn gọn, chính xác, nêu căn cứ pháp lý (tên văn bản, điều/khoản nếu có)."
            )
        else:
            system_prompt = (
                "Bạn là trợ lý pháp lý Việt Nam. Trả lời ngắn gọn, chính xác, dẫn chiếu "
                "căn cứ pháp lý (tên văn bản, điều/khoản nếu có). Nếu không chắc, nói rõ."
            )

    print(f"Model: {args.model}")
    print(f"Số câu hỏi: {len(questions)}")
    print(f"Xuất: {out_path}")
    gen_options: Dict[str, object] = {
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "repeat_penalty": args.repeat_penalty,
    }
    if args.seed:
        gen_options["seed"] = args.seed

    if args.infinite:
        import time
        # Stream mode: keep generating until Ctrl+C
        counter = 0
        try:
            with open(out_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # Write header if file is empty
                if f.tell() == 0:
                    writer.writerow(["question", "answer"])
                while True:
                    q = synthesize_complex_question(args.model, args.domain, None)
                    # Reuse the same machinery to produce the answer
                    gen_list = [q]
                    tmp_out = out_path  # not used here
                    # Compute one answer synchronously for stability
                    def _one(qs: List[str]) -> str:
                        return ask_ollama(
                            args.model,
                            f"{build_json_instruction(args.domain)}\n\nQ: {qs[0]}",
                            system_prompt,
                            gen_options,
                        )
                    # Structured rendering path
                    if args.structured:
                        raw = _one(gen_list)
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            payload = {"question": q, "summary": raw, "violations": [], "citations": [], "penalties": []}
                        ans = render_strict_answer(payload) if args.style == "strict" else render_answer_from_json(payload, args.style)
                    else:
                        analysis_hint = (
                            "Trả lời theo cấu trúc:\n1) Phân tích hành vi\n2) Căn cứ pháp lý\n3) Mức phạt áp dụng\n4) Tổng hợp."
                        )
                        ans = ask_ollama(args.model, f"{q}\n\n{analysis_hint}", system_prompt, gen_options)

                    writer.writerow([q, ans])
                    try:
                        f.flush(); os.fsync(f.fileno())
                    except Exception:
                        pass
                    counter += 1
                    print(f"{counter} ✓")
                    if args.sleep > 0:
                        time.sleep(args.sleep)
        except KeyboardInterrupt:
            print("Đã dừng theo yêu cầu (Ctrl+C).")
    else:
        generate_dataset(
            args.model,
            questions,
            out_path,
            system_prompt,
            gen_options,
            enforce_structured=args.structured,
            retries=args.retries,
            domain=args.domain,
            style=args.style,
            workers=max(1, args.workers),
        )
    print("Hoàn tất.")


if __name__ == "__main__":
    main()


