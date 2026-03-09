import math
import re
import asyncio
import fitz  # PyMuPDF
from fastapi import UploadFile, HTTPException

def clean_html_tags(text: str) -> str:
    """Remove HTML tags like <em>, &nbsp;, etc. from text."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Normalize whitespace
    return " ".join(clean.split())

async def extract_text_from_file(file: UploadFile) -> str:
    content_type = file.content_type
    filename = file.filename.lower()
    
    try:
        if filename.endswith(".pdf"):
            content = await file.read()
            return await asyncio.to_thread(_extract_from_pdf, content)
        elif filename.endswith(".txt") or filename.endswith(".md"):
            content = await file.read()
            return content.decode("utf-8")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, TXT, or MD.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")

def _extract_from_pdf(content: bytes) -> str:
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        raise Exception(f"PDF parsing error: {str(e)}")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points on Earth in km."""
    R = 6371.0  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
