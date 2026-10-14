from backend.core.rag.retriever import Retriever
from langchain_classic.docstore.document import Document
from typing import Dict, List, Optional

class RAGManager:
    """
    Manages the retrieval part of the RAG pipeline.
    Searches the Postgres knowledge base and fetches relevant context.
    """
    def __init__(self):
        """Initializes the RAGManager. The database pool and embedding model open on first use."""
        self.retriever = Retriever()

    def retrieve_context(self, query: str, filters: Optional[Dict] = None, k: int = 5) -> List[Document]:
        """
        Retrieves relevant parent chunks for a given query.

        Args:
            query: The user's question.
            filters: Optional 'page_number' and 'title_keyword' (e.g. 'Lecture 4') from extract_filters.
            k: The number of search hits; up to two more related chunks may come from the concept graph.

        Returns:
            A list of retrieved LangChain Document objects.
        """
        print(f"RAGManager: Retrieving top {k} documents for query: '{query}' with filters: {filters or {}}")
        try:
            results = self.retriever.search(query, filters, k=k)
            print(f"RAGManager: Found {len(results)} relevant document chunks.")
            return results
        except Exception as e:
            print(f"RAGManager: An error occurred during retrieval: {e}")
            return []
