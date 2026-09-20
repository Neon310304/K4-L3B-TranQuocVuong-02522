"""Benchmark retrieval strategies on the Shopee return/refund corpus.

Change only ACTIVE_STRATEGY to compare chunkers on the same documents
and the same 5 queries.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from src.agent import KnowledgeBaseAgent
from src.chunking import (
    ChunkingStrategyComparator,
    FixedSizeChunker,
    RecursiveChunker,
    SentenceChunker,
)
from src.models import Document
from src.store import EmbeddingStore

CORPUS_DIR = Path("data/chinh-sach-doi-tra-shopee")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# One-line switch used for the personal strategy. Other strategies stay
# available so the same script can emit a comparison table.
ACTIVE_STRATEGY = "heading"


class HeadingChunker:
    """Split policy text on Markdown headings, then recurse if a section is long.

    Policy pages are already authored as numbered sections. Keeping the heading
    on every sub-chunk preserves "this fragment belongs to which article".
    """

    def __init__(self, max_chars: int = 700) -> None:
        self.max_chars = max_chars
        self._fallback = RecursiveChunker(chunk_size=max_chars)

    def chunk(self, text: str) -> list[str]:
        if not text.strip():
            return []
        parts = re.split(r"(?=^#{1,6} )", text, flags=re.MULTILINE)
        sections: list[str] = []
        pending_heading = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            lines = [line for line in part.splitlines() if line.strip()]
            heading_only = len(lines) == 1 and part.startswith("#")
            if heading_only:
                pending_heading = f"{pending_heading}\n\n{part}".strip() if pending_heading else part
                continue
            if pending_heading:
                part = f"{pending_heading}\n\n{part}"
                pending_heading = ""
            sections.append(part)
        if pending_heading:
            sections.append(pending_heading)

        chunks: list[str] = []
        for part in sections:
            heading = part.split("\n", 1)[0].strip() if part.startswith("#") else ""
            if len(part) <= self.max_chars:
                chunks.append(part)
                continue
            for index, piece in enumerate(self._fallback.chunk(part)):
                piece = piece.strip()
                if not piece:
                    continue
                if index and heading and not piece.lstrip().startswith("#"):
                    chunks.append(f"{heading}\n\n{piece}")
                else:
                    chunks.append(piece)
        return chunks


class LexicalEmbedder:
    """Bag-of-words embedder for the benchmark run.

    MockEmbedder hashes MD5 and has no semantics, so retrieval scores would be
    noise. This embedder stays local (no API key) and is only used by bench.py.
    pytest still uses _mock_embed.
    """

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}
        self._backend_name = "lexical bag-of-words"

    def fit(self, texts: list[str]) -> None:
        tokens: set[str] = set()
        for text in texts:
            tokens.update(self._tokenize(text))
        self.vocab = {token: index for index, token in enumerate(sorted(tokens))}

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ0-9]+", text.lower())

    def __call__(self, text: str) -> list[float]:
        dim = max(len(self.vocab), 1)
        vector = [0.0] * dim
        for token in self._tokenize(text):
            index = self.vocab.get(token)
            if index is not None:
                vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


CHUNKERS = {
    "fixed_size": lambda: FixedSizeChunker(chunk_size=400, overlap=80),
    "sentence": lambda: SentenceChunker(max_sentences_per_chunk=3),
    "recursive": lambda: RecursiveChunker(chunk_size=500),
    "heading": lambda: HeadingChunker(max_chars=700),
}


QUERIES = [
    {
        "id": 1,
        "query": "Người mua có bao nhiêu ngày để gửi yêu cầu trả hàng hoàn tiền sau khi đơn giao thành công?",
        "gold": "15 ngày kể từ lúc đơn cập nhật giao hàng thành công; thực phẩm tươi sống/đông lạnh: 24 giờ.",
        "markers": ["15 ngày", "24 giờ"],
        "gold_doc": "buyer-dieu-kien-tra-hang",
        "metadata_filter": None,
    },
    {
        "id": 2,
        "query": "Shopee có hỗ trợ đổi hàng sang sản phẩm khác khi đã nhận hàng không?",
        "gold": "Shopee hiện chưa hỗ trợ yêu cầu đổi hàng; người mua gửi trả hàng/hoàn tiền nếu hàng có vấn đề.",
        "markers": ["chưa hỗ trợ"],
        "gold_doc": "buyer-thoi-han-gui-yeu-cau",
        "metadata_filter": None,
    },
    {
        "id": 3,
        "query": "Người mua gửi yêu cầu trả hàng hoàn tiền trên ứng dụng Shopee bằng cách nào?",
        "gold": "Tôi > Chờ giao hàng/Đã giao > Trả hàng/Hoàn tiền, chọn lý do và tải bằng chứng.",
        "markers": ["Chờ giao hàng", "Gửi yêu cầu"],
        "gold_doc": "buyer-huong-dan-gui-yeu-cau",
        "metadata_filter": None,
    },
    {
        "id": 4,
        "query": "Những nhóm sản phẩm nào bị hạn chế trả hàng với lý do đổi ý?",
        "gold": "Sức khỏe/vệ sinh, thực phẩm mau hỏng, hàng đặc thù vận chuyển, sản phẩm số/dịch vụ.",
        "markers": ["Sức khỏe", "Thực phẩm"],
        "gold_doc": "buyer-san-pham-han-che",
        "metadata_filter": None,
    },
    {
        "id": 5,
        "query": "Thời hạn phản hồi yêu cầu trả hàng hoàn tiền là bao lâu?",
        "gold": "Người bán phải phản hồi trong vòng 02 ngày lịch kể từ thông báo của Shopee; quá hạn bị xem như đồng ý.",
        "markers": ["02 ngày lịch", "tự động hoàn tiền"],
        "gold_doc": "seller-thoi-han-phan-hoi",
        "metadata_filter": {"audience": "seller"},
    },
]


def parse_markdown(path: Path) -> tuple[dict[str, str], str]:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"Missing YAML front matter: {path}")
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, match.group(2).strip()


def load_corpus() -> list[tuple[dict[str, str], str, Path]]:
    records = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        metadata, body = parse_markdown(path)
        records.append((metadata, body, path))
    return records


def make_chunk_documents(records, chunker) -> list[Document]:
    documents: list[Document] = []
    for metadata, body, path in records:
        chunks = chunker.chunk(body)
        for index, chunk in enumerate(chunks):
            documents.append(
                Document(
                    id=f"{path.stem}#{index}",
                    content=chunk,
                    metadata={**metadata, "doc_id": path.stem, "chunk_index": index},
                )
            )
    return documents


def context_contains(results: list[dict], markers: list[str]) -> bool:
    blob = " ".join(item["content"] for item in results)
    return all(marker.lower() in blob.lower() for marker in markers)


def preview(text: str, limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def extractive_llm(prompt: str) -> str:
    context_match = re.search(r"Ngữ cảnh:\n(.*)\n\nCâu hỏi:", prompt, re.DOTALL)
    question_match = re.search(r"Câu hỏi: (.*)\nCâu trả lời:", prompt, re.DOTALL)
    context = context_match.group(1).strip() if context_match else prompt
    question = question_match.group(1).strip() if question_match else ""
    numbered = re.findall(r"\[(\d+)\] \(source: ([^\)]+)\)\n(.*?)(?=\n\[\d+\] |\Z)", context, re.DOTALL)
    if not numbered:
        return context[:400]
    lines = [f"Câu hỏi: {question}", "Câu trả lời grounded trên chunk đã truy xuất:"]
    for number, source, body in numbered:
        lines.append(f"- [{number}] {source}: {preview(body, 220)}")
    return "\n".join(lines)


def build_store(documents: list[Document], embedder: LexicalEmbedder) -> EmbeddingStore:
    store = EmbeddingStore(collection_name="bench", embedding_fn=embedder)
    store.add_documents(documents)
    return store


def run_queries(store: EmbeddingStore, agent: KnowledgeBaseAgent, queries) -> list[dict]:
    rows = []
    for item in queries:
        results = store.search_with_filter(
            item["query"],
            top_k=3,
            metadata_filter=item["metadata_filter"],
        )
        answer = agent.answer(item["query"], top_k=3)
        # Agent.answer uses unfiltered search; re-run a filtered grounded answer
        # when the query declares a metadata filter.
        if item["metadata_filter"]:
            filtered_store_hits = results
            numbered = []
            for index, hit in enumerate(filtered_store_hits, start=1):
                numbered.append(
                    f"[{index}] (source: {hit['metadata'].get('doc_id')})\n{hit['content']}"
                )
            answer = extractive_llm(
                "Ngữ cảnh:\n"
                + "\n\n".join(numbered)
                + f"\n\nCâu hỏi: {item['query']}\nCâu trả lời:"
            )
        gold_in_top3 = any(hit["metadata"].get("doc_id") == item["gold_doc"] for hit in results)
        marker_hit = context_contains(results, item["markers"])
        top1_doc = results[0]["metadata"].get("doc_id") if results else None
        if marker_hit and results and results[0]["metadata"].get("doc_id") == item["gold_doc"]:
            score = 2
        elif marker_hit or gold_in_top3:
            score = 1
        else:
            score = 0
        rows.append(
            {
                "item": item,
                "results": results,
                "answer": answer,
                "gold_in_top3": gold_in_top3,
                "marker_hit": marker_hit,
                "top1_doc": top1_doc,
                "score": score,
            }
        )
    return rows


def format_run(title: str, documents: list[Document], rows: list[dict]) -> str:
    lines = [title, f"Chunks nạp: {len(documents)}", ""]
    for row in rows:
        item = row["item"]
        lines.append(f"Q{item['id']}. {item['query']}")
        if item["metadata_filter"]:
            lines.append(f"    filter: {item['metadata_filter']}")
        lines.append(f"    gold: {item['gold']}")
        for rank, hit in enumerate(row["results"], start=1):
            lines.append(
                f"    top-{rank}: score={hit['score']:.3f} doc_id={hit['metadata'].get('doc_id')} "
                f"audience={hit['metadata'].get('audience')}"
            )
            lines.append(f"           {preview(hit['content'])}")
        lines.append(
            f"    gold_doc in top-3: {row['gold_in_top3']} | "
            f"markers in context: {row['marker_hit']} | điểm {row['score']}/2"
        )
        lines.append(f"    agent: {preview(row['answer'], 280)}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    records = load_corpus()
    if not (5 <= len(records) <= 10):
        print(f"Corpus size {len(records)} is outside 5-10", file=sys.stderr)

    output: list[str] = []
    output.append("=== Benchmark Lab 07 — chính sách đổi trả Shopee ===")
    output.append(f"Corpus: {CORPUS_DIR} ({len(records)} tài liệu)")
    output.append(f"Chiến lược đang chấm: {ACTIVE_STRATEGY}")
    output.append("Embedder: lexical bag-of-words (không dùng MockEmbedder cho benchmark)")
    output.append("")

    output.append("=== Baseline ChunkingStrategyComparator ===")
    comparator = ChunkingStrategyComparator()
    for metadata, body, path in records[:3]:
        stats = comparator.compare(body, chunk_size=400)
        output.append(f"Tài liệu: {path.stem} ({len(body)} ký tự, bỏ frontmatter)")
        for name, info in stats.items():
            output.append(
                f"  {name:13} count={info['count']:3}  avg_length={info['avg_length']:.1f}"
            )
        output.append("")

    all_bodies = [body for _, body, _ in records]
    all_queries = [item["query"] for item in QUERIES]

    def evaluate(strategy_name: str) -> tuple[list[Document], list[dict], EmbeddingStore]:
        chunker = CHUNKERS[strategy_name]()
        documents = make_chunk_documents(records, chunker)
        embedder = LexicalEmbedder()
        embedder.fit(all_bodies + all_queries + [doc.content for doc in documents])
        store = build_store(documents, embedder)
        agent = KnowledgeBaseAgent(store=store, llm_fn=extractive_llm)
        rows = run_queries(store, agent, QUERIES)
        return documents, rows, store

    documents, rows, store = evaluate(ACTIVE_STRATEGY)
    output.append(format_run(f"=== Kết quả chiến lược {ACTIVE_STRATEGY} ===", documents, rows))

    output.append("=== A/B metadata filter trên câu 5 (mọi chiến lược) ===")
    query5 = QUERIES[4]["query"]
    for name in ("fixed_size", "recursive", "heading"):
        _, _, strategy_store = evaluate(name)
        unfiltered = strategy_store.search(query5, top_k=3)
        filtered = strategy_store.search_with_filter(
            query5, top_k=3, metadata_filter={"audience": "seller"}
        )
        output.append(f"-- {name} / không filter --")
        for rank, hit in enumerate(unfiltered, start=1):
            output.append(
                f"  top-{rank}: {hit['metadata'].get('doc_id')} audience={hit['metadata'].get('audience')} "
                f"score={hit['score']:.3f} | {preview(hit['content'], 100)}"
            )
        output.append(f"-- {name} / filter audience=seller --")
        for rank, hit in enumerate(filtered, start=1):
            output.append(
                f"  top-{rank}: {hit['metadata'].get('doc_id')} audience={hit['metadata'].get('audience')} "
                f"score={hit['score']:.3f} | {preview(hit['content'], 100)}"
            )
        output.append("")

    output.append("=== So sánh 4 chiến lược trên cùng 5 câu ===")
    output.append(f"{'strategy':12} {'chunks':>6} " + " ".join(f"Q{i}" for i in range(1, 6)) + "  tổng")
    for name in ("fixed_size", "sentence", "recursive", "heading"):
        docs, strategy_rows, _ = evaluate(name)
        points = [str(row["score"]) for row in strategy_rows]
        total = sum(row["score"] for row in strategy_rows)
        output.append(f"{name:12} {len(docs):6} " + " ".join(f"{p:>2}" for p in points) + f"  {total}/10")

    text = "\n".join(output) + "\n"
    Path("ket_qua_benchmark.txt").write_text(text, encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
