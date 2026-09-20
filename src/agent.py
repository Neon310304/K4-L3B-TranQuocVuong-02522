from typing import Callable

from .store import EmbeddingStore


class KnowledgeBaseAgent:
    """
    An agent that answers questions using a vector knowledge base.

    Retrieval-augmented generation (RAG) pattern:
        1. Retrieve top-k relevant chunks from the store.
        2. Build a prompt with the chunks as context.
        3. Call the LLM to generate an answer.
    """

    def __init__(self, store: EmbeddingStore, llm_fn: Callable[[str], str]) -> None:
        self.store = store
        self.llm_fn = llm_fn

    def answer(self, question: str, top_k: int = 3) -> str:
        if self.store.get_collection_size() == 0:
            return "Không tìm thấy ngữ cảnh liên quan trong cơ sở tri thức."

        retrieved = self.store.search(question, top_k=top_k)
        if not retrieved:
            return "Không tìm thấy ngữ cảnh liên quan trong cơ sở tri thức."

        context_blocks: list[str] = []
        for index, chunk in enumerate(retrieved, start=1):
            source = chunk.get("metadata", {}).get("doc_id") or chunk.get("id") or "unknown"
            context_blocks.append(f"[{index}] (source: {source})\n{chunk['content']}")
        context = "\n\n".join(context_blocks)

        prompt = (
            "Bạn là trợ lý trả lời câu hỏi chỉ dựa trên ngữ cảnh được cung cấp.\n"
            "Chỉ dùng thông tin trong ngữ cảnh. Không bịa thêm. "
            "Nếu ngữ cảnh không đủ, nói rõ là không tìm thấy.\n"
            "Khi trả lời, trích dẫn số nguồn [1], [2], [3] tương ứng với chunk đã dùng.\n\n"
            f"Ngữ cảnh:\n{context}\n\n"
            f"Câu hỏi: {question}\n"
            "Câu trả lời:"
        )
        return self.llm_fn(prompt)
