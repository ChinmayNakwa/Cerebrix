from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class AskRequest(BaseModel):
    """
    Defines the structure for a user's question.
    """
    query: str
    session_id: str
    image_data: Optional[str] = Field(None, description="Base64-encoded image data") 

class SourceDocument(BaseModel):
    """
    Represents a singe retrieved source document for citation.
    """
    source_type: str
    location: str  # short label, e.g. "Lecture 3 · 20:24" or "Book p. 31-33"
    title: Optional[str] = None  # lecture topic or book section, for a tooltip
    url: Optional[str] = None

class AskResponse(BaseModel):
    """
    Defines the structure for the AI's answer
    """
    answer: str
    sources: List[SourceDocument]=[]