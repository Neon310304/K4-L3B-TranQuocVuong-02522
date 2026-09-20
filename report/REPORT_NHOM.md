# Báo Cáo Nhóm — Lab 7: Embedding & Vector Store

**Nhóm:** làm cá nhân (không chia vai)
**Thành viên:** Trần Quốc Vượng — 2A202602522
**Ngày:** 2026-09-20

> Nộp theo README: một `REPORT_NHOM.md` (lựa chọn tài liệu, chiến lược, bộ câu hỏi, phân tích). Bài này làm một mình nên phần “từng thành viên” là các chiến lược khác nhau **cùng một người** chạy trên cùng corpus. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần nhóm: 40** = Lựa chọn tài liệu (10) + Thiết kế chiến lược (15) + Chất lượng truy xuất (10) + Thuyết trình (5).

---

## 1. Lựa chọn tài liệu (Document Set Quality) — Nhóm (10 điểm)

### Chủ đề (Domain) & Lý Do Chọn

**Chủ đề:** Chính sách đổi trả / hoàn tiền / trách nhiệm người bán–người mua trên Shopee (đúng ràng buộc K4-L3B).

**Tại sao chọn chủ đề này?**
> L3B bắt buộc corpus TMĐT. Shopee help công khai, `robots.txt` Allow, có số liệu cụ thể (15 ngày, 24 giờ, 02 ngày lịch, 25.000/40.000 Xu) để gold answer kiểm chứng được. Một trang điều khoản gộp cả buyer và seller — tách thành file theo `audience` thì `metadata_filter` mới có việc thật.

### Danh sách tài liệu (Data Inventory)

Số ký tự = phần thân (đã bỏ YAML). Nguồn: `data/chinh-sach-doi-tra-shopee/sources.csv`.

| # | Tên tài liệu | Nguồn (Source URL) | Ngày lấy / Phiên bản | Số ký tự | Metadata đã gán |
|---|--------------|------------|--------------------|----------|-----------------|
| 1 | Thời hạn người mua gửi yêu cầu | https://help.shopee.vn/4/article/79314 | 2026-09-20 / not-stated | 1703 | audience=buyer, category=returns-deadline, language=vi |
| 2 | Điều kiện trả hàng/hoàn tiền | https://help.shopee.vn/portal/4/article/77491 | 2026-09-20 / hieu-luc-2025-11-24 | 1952 | audience=buyer, category=returns-eligibility, language=vi |
| 3 | Hướng dẫn gửi yêu cầu | https://help.shopee.vn/portal/article/79233 | 2026-09-20 / not-stated | 1615 | audience=buyer, category=returns-process, language=vi |
| 4 | Thời gian nhận tiền hoàn | https://help.shopee.vn/portal/4/article/189473 | 2026-09-20 / not-stated | 1772 | audience=buyer, category=refund-timeline, language=vi |
| 5 | Sản phẩm hạn chế trả hàng | https://help.shopee.vn/4/article/79465 | 2026-09-20 / not-stated | 1276 | audience=buyer, category=restricted-returns, language=vi |
| 6 | Phương thức & phí trả hàng | https://help.shopee.vn/4/article/189477 | 2026-09-20 / shopee-xu-tu-2026-01-15 | 2013 | audience=buyer, category=return-shipping, language=vi |
| 7 | Thời hạn người bán phản hồi | https://help.shopee.vn/portal/4/article/77491 | 2026-09-20 / hieu-luc-2025-11-24 | 1868 | audience=seller, category=seller-response-deadline, language=vi |
| 8 | Chi phí vận chuyển hoàn trả (seller) | https://help.shopee.vn/portal/4/article/77491 | 2026-09-20 / hieu-luc-2025-11-24 | 1662 | audience=seller, category=seller-shipping-cost, language=vi |

**Danh sách kiểm tra quản trị dữ liệu (Data governance checklist):**
- [x] Tập tài liệu chỉ chứa nguồn công khai (`public-source`), không dữ liệu cá nhân / đăng nhập / nội bộ.
- [x] Mỗi tài liệu có `source_url`, `retrieved_at`, `document_version` (không bịa số hiệu: không nêu thì `not-stated`).

Crawl thô bằng `scripts/fetch_public_pages.py` + `data/urls.csv` (8/8 saved, robots cho phép). Bản thô trang 77491 ~25KB, menu + cùng nội dung gắn cả buyer lẫn seller — đã làm sạch và **tách audience** trước khi nạp store.

### Cấu trúc Metadata (Metadata Schema)

| Trường metadata | Kiểu | Ví dụ giá trị | Tại sao hữu ích cho truy xuất (retrieval)? |
|----------------|------|---------------|-------------------------------|
| doc_id | str | seller-thoi-han-phan-hoi | Khóa xóa (`delete_document`) và đối chiếu gold; trỏ file gốc chứ không phải `file#0`. |
| audience | str | buyer / seller | Filter bắt buộc L3B: cùng chủ đề “thời hạn” nhưng đáp án khác đối tượng. |
| category | str | returns-deadline, refund-timeline | Lọc hẹp hơn audience khi câu hỏi về phí vs thời hạn. |
| language | str | vi | Chặn nhiễu nếu sau này thêm trang EN. |
| source_url | str | https://help.shopee.vn/... | Truy vết nguồn khi agent trích dẫn. |
| retrieved_at | date | 2026-09-20 | Kiểm độ mới. |
| document_version | str | hieu-luc-2025-11-24 / not-stated | Phân biệt bản chính sách; không bịa số hiệu. |

---

## 2. Thiết kế chiến lược (Strategy Design) — Nhóm (15 điểm)

> Một người chạy **bốn chiến lược** trên cùng 8 tài liệu và cùng 5 câu. Chiến lược nộp: HeadingChunker (ràng buộc L3B: chunk theo tiêu đề/mục).

### Phân tích đường cơ sở (Baseline Analysis)

`ChunkingStrategyComparator().compare(body, chunk_size=400)` — **đã bỏ frontmatter**. Heading đo thêm bằng `HeadingChunker(max_chars=700)`.

| Tài liệu | Chiến lược (Strategy) | Số lượng Chunk | Độ dài trung bình | Giữ được ngữ cảnh không? |
|-----------|----------|-------------|------------|-------------------|
| buyer-dieu-kien-tra-hang (1952 ký tự) | FixedSizeChunker (`fixed_size`) | 6 | 367.0 | Trung bình — cắt giữa câu |
| | SentenceChunker (`by_sentences`) | 9 | 215.4 | Câu trọn nhưng mốc 15 ngày / 24 giờ dễ tách file khác |
| | RecursiveChunker (`recursive`) | 7 | 277.3 | Giữ đoạn/xuống dòng tốt |
| | HeadingChunker (custom) | 5 | 388.8 | Đúng mục điều khoản |
| buyer-huong-dan-gui-yeu-cau (1615 ký tự) | FixedSizeChunker (`fixed_size`) | 5 | 363.0 | Cắt giữa bước 1–8 |
| | SentenceChunker (`by_sentences`) | 10 | 160.3 | Từng bước là câu riêng — retrieval thao tác tốt |
| | RecursiveChunker (`recursive`) | 6 | 267.7 | Gom heading+đoạn |
| | HeadingChunker (custom) | 4 | 402.2 | Cách 1 / Cách 2 thành chunk riêng |
| buyer-phi-va-phuong-thuc-tra-hang (2013 ký tự) | FixedSizeChunker (`fixed_size`) | 6 | 377.2 | Số Xu có thể rơi đúng chỗ cắt |
| | SentenceChunker (`by_sentences`) | 5 | 400.2 | Ít câu dài → chunk to |
| | RecursiveChunker (`recursive`) | 8 | 250.0 | Nhiều mục con, hơi vụn |
| | HeadingChunker (custom) | 6 | 333.8 | Mỗi hình thức trả hàng một chunk |

### Chiến lược đã thử (cùng một người)

**Chiến lược nộp — HeadingChunker (custom)**
- **Loại chiến lược:** custom, tách theo tiêu đề Markdown
- **Mô tả & lý do chọn:** Văn bản Shopee đã chia mục (`## Thời hạn…`, `## Cách 1…`). Ranh giới heading là đơn vị ngữ nghĩa người soạn đặt sẵn — hợp L3B. Section dài thì đệ quy; mảnh con được gắn lại tiêu đề để không mất “đây là mục nào”.
- **Code snippet:**
```python
class HeadingChunker:
    def chunk(self, text: str) -> list[str]:
        parts = re.split(r"(?=^#{1,6} )", text, flags=re.MULTILINE)
        # gộp heading-only vào section sau; section dài → RecursiveChunker
        # mảnh con i>0 được prepend heading của section
        ...
```

**Đối chứng 1 — FixedSizeChunker (`chunk_size=400`, `overlap=80`)**
- Cửa sổ trượt, overlap giữ biên. Dễ cắt giữa điều kiện/số liệu.

**Đối chứng 2 — SentenceChunker (`max_sentences_per_chunk=3`)**
- Giữ trọn câu. Thắng câu hỏi quy trình vì “Chờ giao hàng” nằm trong một cụm câu.

**Đối chứng 3 — RecursiveChunker (`chunk_size=500`)**
- Ưu tiên `\n\n` rồi `\n`. Không biết mục điều khoản nên câu 5 không filter dễ lấy nhầm file buyer.

### So Sánh giữa các chiến lược

Điểm = rubric 2/1/0 × 5 câu, chấm **mức nội dung** (marker đáp án có trong top-3), không chỉ `doc_id`. Embedder lexical bag-of-words (không MockEmbedder). Nguồn: `ket_qua_benchmark.txt`.

| Thành viên / lần chạy | Chiến lược (Strategy) | Điểm truy xuất (/10) | Điểm mạnh | Điểm yếu |
|-----------|----------|----------------------|-----------|----------|
| Trần Quốc Vương | HeadingChunker | 8 | Đúng mục; câu 5 filter sạch | Câu 4 đúng file sai section |
| (đối chứng) | SentenceChunker | 8 | Thắng câu 3 (thao tác app) | Câu 5 không filter lẫn buyer |
| (đối chứng) | RecursiveChunker | 7 | Ít chunk (38), mạch đoạn | Không filter: buyer chiếm top-1 câu 5 |
| (đối chứng) | FixedSizeChunker | 7 | Overlap cứu biên | Câu 3 = 0 (cắt nát bước) |

**Chiến lược nào tốt nhất cho chủ đề này? Tại sao?**
> Heading và Sentence cùng 8/10 nhưng **Heading hợp corpus điều khoản hơn**: mỗi `##` đã là một điều. Sentence thắng đúng một câu quy trình. Điểm không phải tất cả — câu 4 cho thấy heading có thể “thắng file, thua section”: cosine đo chủ đề, không đo mật độ đáp án. Với văn bản mục lục sẵn, heading vẫn là lựa chọn nộp; nên bổ sung overlap nhẹ hoặc rerank keyword.

---

## 3. Câu hỏi đánh giá & Chất lượng truy xuất (Retrieval Quality) — Nhóm (10 điểm)

### Câu hỏi đánh giá & Câu trả lời chuẩn

| # | Câu hỏi (Query) | Câu trả lời chuẩn (Gold Answer) | Chunk nào chứa thông tin? |
|---|-------|-------------------------------|--------------------------|
| 1 | Người mua có bao nhiêu ngày để gửi yêu cầu trả hàng hoàn tiền sau khi đơn giao thành công? | 15 ngày kể từ giao thành công; thực phẩm tươi sống/đông lạnh: 24 giờ. | `buyer-dieu-kien-tra-hang` mục Thời hạn gửi yêu cầu |
| 2 | Shopee có hỗ trợ đổi hàng sang sản phẩm khác khi đã nhận hàng không? | Chưa hỗ trợ đổi hàng; dùng trả hàng/hoàn tiền nếu hàng có vấn đề. | `buyer-thoi-han-gui-yeu-cau` mục Lưu ý cho người mua |
| 3 | Người mua gửi yêu cầu trả hàng hoàn tiền trên ứng dụng Shopee bằng cách nào? | Tôi > Chờ giao hàng/Đã giao > Trả hàng/Hoàn tiền, chọn lý do, tải bằng chứng. | `buyer-huong-dan-gui-yeu-cau` Cách 1 |
| 4 | Những nhóm sản phẩm nào bị hạn chế trả hàng với lý do đổi ý? | Sức khỏe/vệ sinh, thực phẩm mau hỏng, hàng đặc thù vận chuyển, sản phẩm số/dịch vụ. | `buyer-san-pham-han-che` mục Danh mục hạn chế |
| 5 | Thời hạn phản hồi yêu cầu trả hàng hoàn tiền là bao lâu? | Người bán phản hồi trong **02 ngày lịch**; quá hạn xem như đồng ý, Shopee tự động hoàn tiền. Cần `metadata_filter={"audience":"seller"}`. | `seller-thoi-han-phan-hoi` mục Quyền phản hồi / Hậu quả quá hạn |

Câu 5 **không nêu** người hỏi là ai; corpus có hai tài liệu cùng từ “thời hạn / trả hàng / hoàn tiền” nhưng đáp án 15 ngày (buyer) vs 02 ngày lịch (seller).

### Tổng hợp chất lượng truy xuất

HeadingChunker (chiến lược nộp):

| # | Câu hỏi | Chiến lược tốt nhất cho câu này | Có chunk liên quan trong top-3? | Ghi chú |
|---|---------|-------------------------------|-------------------------------|---------|
| 1 | Số ngày gửi yêu cầu | heading / sentence (2đ) | Có, top-1 có 15 ngày + 24 giờ | recursive chỉ 1đ |
| 2 | Có đổi hàng không | cả bốn (2đ) | Có | Marker “chưa hỗ trợ” dễ bắt |
| 3 | Cách gửi trên app | **sentence (2đ)** | Heading: file đúng, **Cách 1 không lọt** | Failure: top-1 là Shopee Đảm Bảo |
| 4 | Nhóm hạn chế đổi ý | không chiến lược nào 2đ | Heading: đúng file, **sai section** | Định nghĩa thắng danh mục |
| 5 | Thời hạn phản hồi | heading / fixed / recursive (2đ) **khi có filter** | Có, sau filter toàn seller | Không filter: recursive top-1 = buyer |

**Lọc bằng metadata có giúp ích không? Ở câu hỏi nào?**
> Có, **câu 5**. Không filter: recursive đưa `buyer-huong-dan-gui-yeu-cau` lên top-1; heading vẫn lẫn 1 slot buyer. Có `audience=seller` thì cả fixed/recursive/heading chỉ còn `seller-thoi-han-phan-hoi`. Filter tăng precision, không làm mất đáp án seller (recall trên tập seller vẫn đủ).

---

## 4. Thuyết trình (Demo) & Bài học — Nhóm (5 điểm)

**Những phân tích sẽ trình bày:**
> 1. Tách một trang 77491 thành hai file audience — nếu để `audience: both` thì filter không làm gì.
> 2. Chấm theo `doc_id` thổi phồng câu 4 (đúng file, sai mục); phải kiểm chuỗi đặc trưng (`Sức khỏe`, `Chờ giao hàng`).
> 3. MockEmbedder phá benchmark; số liệu thật dùng lexical (hoặc embedder ngữ nghĩa).

**Bài học khi so sánh chiến lược trên cùng dữ liệu:**
> Cùng 8 file và 5 câu, heading và sentence cùng 8/10 nhưng **thắng ở câu khác**. Ranh giới chunk quyết định slot top-k, không phải “chiến lược nào luôn tốt”. Cosine/lexical đo giống chủ đề, không đo “chunk nào chứa số/bước”.

**Nếu làm lại, sẽ thay đổi gì trong chiến lược dữ liệu?**
> Gắn heading cha vào mọi mục con; overlap ngắn giữa section liền kề; thêm một câu gold bắt buộc filter `category` (phí vs thời hạn). Không nạp bản crawl thô — 25KB menu chiếm hết top-k.

---

## Tự Đánh Giá (Phần Nhóm)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Lựa chọn tài liệu (Document Set Quality) | 9 / 10 |
| Thiết kế chiến lược (Strategy Design) | 13 / 15 |
| Chất lượng truy xuất (Retrieval Quality) | 8 / 10 |
| Thuyết trình (Demo) | 4 / 5 |
| **Tổng phần nhóm** | **34 / 40** |
