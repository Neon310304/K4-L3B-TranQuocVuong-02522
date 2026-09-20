# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** Trần Quốc Vương
**MSSV:** 02522
**Nhóm:** làm cá nhân (không chia vai nhóm)
**Ngày:** 2026-09-20

> **Nộp 1 bản / sinh viên.** Tài liệu, 5 query và so sánh chiến lược nằm ở `REPORT_NHOM.md` (làm một mình). Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần cá nhân: 60** = Khởi động (5) + Hướng tiếp cận (10) + Hoàn thiện code (30) + Dự đoán độ tương tự (5) + Kết quả truy xuất của tôi (10).

---

## 1. Khởi động (Warm-up) — Cá nhân (5 điểm)

### Độ tương tự Cosine (Cosine Similarity) (Bài tập 1.1)

**Độ tương tự cosine cao (High cosine similarity) nghĩa là gì?**
> Hai vector embedding gần cùng hướng trong không gian số. Với text, điều đó nghĩa là hai đoạn nói về nội dung/ý nghĩa gần nhau, dù từ vựng không trùng từng chữ.

**Ví dụ có độ tương tự CAO:**
- Câu A: Shopee chưa hỗ trợ đổi hàng sang sản phẩm khác.
- Câu B: Không thể đổi sang mặt hàng khác trên Shopee.
- Tại sao tương đồng: khác từ vựng (chưa hỗ trợ / không thể đổi) nhưng cùng một quy tắc chính sách.

**Ví dụ có độ tương tự THẤP:**
- Câu A: Thời gian hoàn tiền về thẻ tín dụng là 7–14 ngày làm việc.
- Câu B: Người bán chịu phí vận chuyển tối đa 40.000 đồng.
- Tại sao khác: cùng sàn TMĐT nhưng một bên nói mốc hoàn tiền cho buyer, một bên nói chi phí vận chuyển cho seller.

**Tại sao độ tương tự cosine (cosine similarity) được ưu tiên hơn khoảng cách Euclid (Euclidean distance) cho text embeddings?**
> Embedding thường được chuẩn hoá; cosine (và dot product trên vector đơn vị) đo góc/hướng, ít bị ảnh hưởng bởi độ dài câu. Khoảng cách Euclid nhạy với độ lớn vector nên hai câu cùng nghĩa nhưng dài/ngắn khác nhau dễ bị đẩy xa.

### Bài toán tính toán Chunking (Bài tập 1.2)

**Tài liệu 10,000 ký tự, chunk_size=500, overlap=50. Bao nhiêu chunks?**
> Công thức: `ceil((10000 - 50) / (500 - 50)) = ceil(9950 / 450) = ceil(22.111) = 23`
> Kiểm lại bằng `FixedSizeChunker(chunk_size=500, overlap=50).chunk('a'*10000)` → **23 chunks**.

**Nếu độ chồng chéo (overlap) tăng lên 100, số lượng chunk thay đổi thế nào? Tại sao muốn độ chồng chéo nhiều hơn?**
> `ceil((10000 - 100) / (500 - 100)) = ceil(9900 / 400) = 25` chunks (tăng 2). Overlap lớn hơn giữ câu/ý bị cắt ở biên chunk, giảm trường hợp đáp án nằm đúng chỗ cắt nên không lọt top-k — đổi lại là nhiều chunk hơn, tốn lưu trữ và dễ nhiễu.

---

## 2. Hướng tiếp cận của tôi (My Approach) — Cá nhân (10 điểm)

### Các hàm chia nhỏ (Chunking Functions)

**`SentenceChunker.chunk` — hướng tiếp cận:**
> Tách câu bằng `re.split(r"(?<=[.!?]) |(?<=\.)\n", text)`: lookbehind giữ dấu `.!?`, rồi mới cắt ở khoảng trắng hoặc `.\n`. Gom `max_sentences_per_chunk` câu, `strip()` từng chunk; text rỗng trả `[]`. Edge case chưa xử lý: viết tắt (`TS.`, `v.v.`) và số thập phân bị cắt nhầm vì regex không phân biệt dấu chấm viết tắt với hết câu.

**`RecursiveChunker.chunk` / `_split` — hướng tiếp cận:**
> Thử separator theo thứ tự `["\n\n", "\n", ". ", " ", ""]`. Base case: rỗng → `[]`; `len <= chunk_size` → giữ nguyên; hết separator hoặc separator `""` → cắt cứng theo `chunk_size` (cả khi `separators=[]`). Mảnh còn dài thì đệ quy với separator còn lại; mảnh nhỏ liền kề được nối lại bằng đúng separator cho tới sát `chunk_size` để tránh chunk vụn.

### Lớp EmbeddingStore

**`add_documents` + `search` — hướng tiếp cận:**
> Không bật Chroma (máy chấm nếu có chromadb sẽ rẽ nhánh chưa cài). `_make_record` copy metadata, gán `metadata['doc_id']` mặc định bằng `doc.id`, lưu embedding. `search` và `search_with_filter` cùng đi qua `_search_records`: dot product query–chunk, sort giảm dần, bỏ vector khi trả về.

**`search_with_filter` + `delete_document` — hướng tiếp cận:**
> Lọc metadata **trước**, rồi mới search trên tập còn lại — nếu lọc sau top-k thì slot có thể bị chiếm hết bởi tài liệu sai audience. `delete_document` xoá mọi record có `metadata['doc_id']` khớp, trả `True`/`False` tùy có xoá được gì.

### Tác tử KnowledgeBaseAgent

**`answer` — hướng tiếp cận:**
> Store rỗng hoặc không có hit → trả thông báo, không gọi LLM. Có hit thì đánh số `[1] [2] [3]` kèm `doc_id`, ràng buộc chỉ dùng ngữ cảnh, trích dẫn số nguồn. `llm_fn` nhận nguyên prompt đó; test chỉ cần chuỗi khác rỗng, benchmark dùng LLM extractive in lại chunk đã retrieve.

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Vượt qua bộ kiểm thử là điều kiện tính điểm phần này.

### Kết Quả Kiểm Thử (Test Results)

Môi trường: Python 3.12.6 (lab khuyến nghị 3.11; 3.10+ vẫn chạy đủ test), venv `.venv`, `pip install -r requirements.txt`.

```
============================= test session starts =============================
platform win32 -- Python 3.12.6, pytest-9.1.1, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: D:\Python\K4-L3B-TranQuocVuong-02522
collected 42 items

tests/test_solution.py::TestProjectStructure::test_root_main_entrypoint_exists PASSED
tests/test_solution.py::TestProjectStructure::test_src_package_exists PASSED
tests/test_solution.py::TestClassBasedInterfaces::test_chunker_classes_exist PASSED
tests/test_solution.py::TestClassBasedInterfaces::test_mock_embedder_exists PASSED
tests/test_solution.py::TestFixedSizeChunker::test_chunks_respect_size PASSED
tests/test_solution.py::TestFixedSizeChunker::test_correct_number_of_chunks_no_overlap PASSED
tests/test_solution.py::TestFixedSizeChunker::test_empty_text_returns_empty_list PASSED
tests/test_solution.py::TestFixedSizeChunker::test_no_overlap_no_shared_content PASSED
tests/test_solution.py::TestFixedSizeChunker::test_overlap_creates_shared_content PASSED
tests/test_solution.py::TestFixedSizeChunker::test_returns_list PASSED
tests/test_solution.py::TestFixedSizeChunker::test_single_chunk_if_text_shorter PASSED
tests/test_solution.py::TestSentenceChunker::test_chunks_are_strings PASSED
tests/test_solution.py::TestSentenceChunker::test_respects_max_sentences PASSED
tests/test_solution.py::TestSentenceChunker::test_returns_list PASSED
tests/test_solution.py::TestSentenceChunker::test_single_sentence_max_gives_many_chunks PASSED
tests/test_solution.py::TestRecursiveChunker::test_chunks_within_size_when_possible PASSED
tests/test_solution.py::TestRecursiveChunker::test_empty_separators_falls_back_gracefully PASSED
tests/test_solution.py::TestRecursiveChunker::test_handles_double_newline_separator PASSED
tests/test_solution.py::TestRecursiveChunker::test_returns_list PASSED
tests/test_solution.py::TestEmbeddingStore::test_add_documents_increases_size PASSED
tests/test_solution.py::TestEmbeddingStore::test_add_more_increases_further PASSED
tests/test_solution.py::TestEmbeddingStore::test_initial_size_is_zero PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_content_key PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_score_key PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_results_sorted_by_score_descending PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_returns_at_most_top_k PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_returns_list PASSED
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_non_empty PASSED
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_returns_string PASSED
tests/test_solution.py::TestComputeSimilarity::test_identical_vectors_return_1 PASSED
tests/test_solution.py::TestComputeSimilarity::test_opposite_vectors_return_minus_1 PASSED
tests/test_solution.py::TestComputeSimilarity::test_orthogonal_vectors_return_0 PASSED
tests/test_solution.py::TestComputeSimilarity::test_zero_vector_returns_0 PASSED
tests/test_solution.py::TestCompareChunkingStrategies::test_counts_are_positive PASSED
tests/test_solution.py::TestCompareChunkingStrategies::test_each_strategy_has_count_and_avg_length PASSED
tests/test_solution.py::TestCompareChunkingStrategies::test_returns_three_strategies PASSED
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_filter_by_department PASSED
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_no_filter_returns_all_candidates PASSED
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_returns_at_most_top_k PASSED
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_reduces_collection_size PASSED
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_false_for_nonexistent_doc PASSED
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_true_for_existing_doc PASSED

============================= 42 passed in 0.08s ==============================
```

`python main.py "Chunking là gì?"` chạy hết pipeline; dòng `Skipping missing file: data/customer_support_playbook.txt` là bình thường.

**Số lượng bài test vượt qua (pass):** 42 / 42

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

Điểm thực tế dưới đây là cosine trên **MockEmbedder** (backend mặc định của lab, băm MD5 — không có ngữ nghĩa). Cột lexical là bag-of-words trong `bench.py`, chỉ để đối chiếu.

| Cặp | Câu A | Câu B | Dự đoán | Điểm thực tế (mock) | Đúng? |
|------|-----------|-----------|---------|--------------|-------|
| 1 | Người mua được trả hàng trong 15 ngày. | Khách hàng có hai tuần để hoàn trả sản phẩm. | cao | -0.047 | không (mock) |
| 2 | Shopee chưa hỗ trợ đổi hàng sang sản phẩm khác. | Không thể đổi sang mặt hàng khác trên Shopee. | cao | -0.185 | không (mock) |
| 3 | Thời gian hoàn tiền về thẻ tín dụng là 7-14 ngày làm việc. | Người bán chịu phí vận chuyển tối đa 40.000 đồng. | thấp | -0.039 | có (cùng vùng thấp) |
| 4 | Người mua gửi yêu cầu trong 15 ngày sau khi giao thành công. | Người bán phải phản hồi trong 2 ngày lịch. | thấp | -0.119 | có (mock luôn thấp) |
| 5 | Tiền hoàn về Ví ShopeePay trong 24 giờ. | Số tiền hoàn được chuyển vào ShopeePay sau một ngày. | cao | -0.147 | không (mock) |

Lexical (đối chiếu, không phải mock): cặp 2 = 0.527 (cao), cặp 3 = 0.000 (thấp), cặp 5 = 0.335, cặp 1 = 0.224, cặp 4 = 0.277.

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn ý nghĩa?**
> Cặp 2 cùng nghĩa nhưng mock cho -0.185 — gần như vuông góc/ngược hướng. MockEmbedder không mã hoá ngữ nghĩa, chỉ băm chuỗi, nên dự đoán "cao/thấp theo nghĩa" không áp dụng được. Muốn cosine phản ánh nghĩa thì phải embedder thật (local/OpenAI/Gemini) hoặc ít nhất lexical như trong `bench.py`. Pytest vẫn đúng vì test không đòi ngữ nghĩa.

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

Corpus: `data/chinh-sach-doi-tra-shopee/` (8 file). Chiến lược chấm: **HeadingChunker** — tách theo `##`, section dài thì recursive và gắn lại tiêu đề vào mảnh con. Embedder: lexical bag-of-words trong `bench.py` (**không** dùng MockEmbedder; mock băm MD5 nên số liệu sẽ là nhiễu). Chi tiết: `ket_qua_benchmark.txt`.

Chấm hai mức: (A) `doc_id` gold có trong top-3 không; (B) ngữ cảnh có chuỗi đặc trưng của đáp án không. Rubric 2/1/0 theo (B) + vị trí.

| # | Câu hỏi (Query) | Top-1 Chunk truy xuất được (tóm tắt) | Điểm Score | Có liên quan không? (Relevant) | Câu trả lời của Agent (tóm tắt) |
|---|-------|--------------------------------|-------|-----------|------------------------|
| 1 | Người mua có bao nhiêu ngày để gửi yêu cầu trả hàng hoàn tiền sau khi đơn giao thành công? | `buyer-dieu-kien-tra-hang` mục thời hạn: **15 ngày** + thực phẩm **24 giờ** | 0.589 | Có, top-1 chứa đủ số liệu | Agent trích 15 ngày / 24 giờ |
| 2 | Shopee có hỗ trợ đổi hàng sang sản phẩm khác khi đã nhận hàng không? | Lưu ý người mua: **chưa hỗ trợ đổi hàng** | 0.564 | Có, top-1 đúng | Agent đọc được "chưa hỗ trợ" |
| 3 | Người mua gửi yêu cầu trả hàng hoàn tiền trên ứng dụng Shopee bằng cách nào? | Top-1 nhầm sang Shopee Đảm Bảo; Cách 2 ở top-3, **Cách 1 ("Chờ giao hàng") không lọt** | 0.609 | File gold ở top-3 nhưng **không có marker thao tác** | Agent mô tả Đảm Bảo, không ra 8 bước |
| 4 | Những nhóm sản phẩm nào bị hạn chế trả hàng với lý do đổi ý? | Top-1 đúng file nhưng chỉ **định nghĩa**; mục "Sức khỏe / Thực phẩm..." không vào top-3 | 0.725 | Đúng tài liệu, **sai section** | Agent nhắc định nghĩa, chưa liệt kê nhóm |
| 5 | Thời hạn phản hồi yêu cầu trả hàng hoàn tiền là bao lâu? (filter `audience=seller`) | Cả top-3 là `seller-thoi-han-phan-hoi`: **02 ngày lịch**, quá hạn = đồng ý | 0.469 | Có | Agent grounded file người bán |

**Bao nhiêu câu hỏi trả về chunk có liên quan trong top-3?** 5/5 nếu chỉ đếm `doc_id`; **3/5** nếu đếm đúng đoạn chứa đáp án (câu 3 và 4 fail mức nội dung). Điểm rubric: 2+2+1+1+2 = **8/10**.

Chênh lệch hai cách chấm: câu 4 `doc_id` đúng nên tưởng 2 điểm, nhưng marker `Sức khỏe`/`Thực phẩm` vắng — đúng cảnh báo lab (heading lấy trọn top-3 cùng file, section trả lời không lọt).

**A/B filter câu 5** (cùng query, không nêu buyer/seller):

| Chiến lược | Không filter (top-3 audience) | Có `audience=seller` |
|---|---|---|
| fixed_size | seller, **buyer**, **buyer** | seller, seller, seller |
| recursive | **buyer**, **buyer**, seller | seller, seller, seller |
| heading | seller, seller, **buyer** | seller, seller, seller |

Không filter, recursive đưa hướng dẫn người mua lên top-1; filter thì cả ba chiến lược chỉ còn file người bán. Câu hỏi **có cần filter**.

**Failure case — câu 4 (và câu 3 cùng cơ chế):**
- Hỏng: hỏi danh mục hạn chế; top-1 là mục Định nghĩa cùng file, không có tên nhóm.
- Vì sao: lexical/cosine đo trùng chủ đề ("hạn chế trả hàng", "đổi ý"), không đo mật độ thông tin trả lời được. Heading không overlap nên mỗi mục chỉ có một cơ hội lọt top-k.
- Sửa: gắn heading cha vào mọi mục con, hoặc rerank bằng keyword bắt buộc (`Sức khỏe`, `Chờ giao hàng`); overlap nhẹ giữa section liền kề.

**Điều hay nhất tôi học được từ thành viên khác / nhóm khác (qua demo):**
> Không demo nhóm. Tự so trên cùng 5 câu: heading 8/10, sentence 8/10 (thắng câu 3 vì "Chờ giao hàng" nằm trọn một cụm câu), recursive 7/10, fixed_size 7/10. Cùng corpus, khác ranh giới chunk là đủ để một câu đổi từ 0 thành 2.

---

## Tự Đánh Giá (Phần Cá Nhân)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Khởi động (Warm-up) | 5 / 5 |
| Hướng tiếp cận của tôi (My Approach) | 10 / 10 |
| Hoàn thiện code (Core Implementation — tests) | 30 / 30 |
| Dự đoán độ tương tự (Similarity Predictions) | 5 / 5 |
| Kết quả truy xuất của tôi (Competition Results) | 8 / 10 |
| **Tổng phần cá nhân** | **58 / 60** |
