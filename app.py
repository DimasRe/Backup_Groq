from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import sqlite3
import os
import uuid
import json
import requests
from datetime import datetime
import shutil
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Structured Data Processing
import pandas as pd
import openpyxl

# Constants
STRUCTURED_DATA_UPLOAD_DIR = "excel_uploads"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Ensure upload directory exists
Path(STRUCTURED_DATA_UPLOAD_DIR).mkdir(exist_ok=True)

# Check if GROQ API key is provided
if not GROQ_API_KEY:
    print("⚠️  WARNING: GROQ_API_KEY not found in environment variables!")
    print("   Please create a .env file with your GROQ API key")
    print("   Get your free API key at: https://console.groq.com/")

# Initialize FastAPI
app = FastAPI(
    title="Local Structured Data Chat System",
    description="Local structured data analysis and chat system powered by Groq AI",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    structured_document_id: Optional[str] = None
    is_predefined: bool = False

class ChatResponse(BaseModel):
    response: str
    source_document_name: Optional[str] = None
    next_action: str = "continue_chat"

class StructuredDocument(BaseModel):
    id: str
    filename: str
    upload_date: str
    data_preview: Optional[List[Dict[str, Any]]] = None
    row_count: int

class SystemStats(BaseModel):
    total_structured_documents: int
    total_chats: int
    recent_activity: List[Dict[str, Any]]

class SystemHealth(BaseModel):
    status: str
    groq_api: str
    database: str
    model_info: Optional[Dict[str, Any]] = None

# Database connection
def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# Database Initialization
def initialize_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS excel_documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            row_count INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            is_predefined INTEGER,
            excel_document_id TEXT,
            chat_turn INTEGER DEFAULT 0
        )
    """)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

# Function to extract data from Excel or CSV
def extract_data_from_structured_file(file_path: Path):
    try:
        file_extension = file_path.suffix.lower()
        df = None
        if file_extension in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path)
        elif file_extension == '.csv':
            df = pd.read_csv(file_path)
        else:
            raise ValueError("Unsupported file type for structured data extraction.")

        num_rows_for_ai = min(len(df), 50)
        num_cols_for_ai = min(len(df.columns), 10)

        data_string = df.head(num_rows_for_ai).iloc[:, :num_cols_for_ai].to_string()
        return data_string, len(df)
    except Exception as e:
        print(f"Error extracting data from structured file {file_path}: {e}")
        return None, 0

def query_groq(prompt: str, max_tokens: int = 2000, model: str = "llama3-8b-8192") -> str:
    """
    Query GROQ API for AI responses
    """
    if not GROQ_API_KEY:
        return "Error: GROQ API key not configured. Please check your .env file."

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Anda adalah asisten analisis data lokal yang membantu pengguna memahami konten dokumen terstruktur. Berikan jawaban yang akurat, informatif, dan relevan dalam bahasa Indonesia. Jika pertanyaan tidak relevan dengan dokumen atau bersifat umum yang tidak terkait analisis dokumen, jawablah dengan sopan bahwa Anda hanya berfokus pada analisis data terstruktur."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": False
        }

        response = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                return "Error: Invalid response format from GROQ API"
        elif response.status_code == 401:
            return "Error: Invalid GROQ API key. Please check your credentials."
        elif response.status_code == 429:
            return "Error: Rate limit exceeded. Please try again later."
        else:
            print(f"GROQ API error: {response.status_code} {response.text}")
            return f"Error: GROQ API returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        return "Error: Unable to connect to GROQ API. Please check your internet connection."
    except requests.exceptions.Timeout:
        return "Error: GROQ API request timed out. Please try again."
    except Exception as e:
        print(f"Error querying GROQ: {e}")
        return f"Error: {str(e)}"

# Function for searching structured data (Excel/CSV)
def search_structured_data(doc_id: str, query: str) -> tuple[str, list]:
    conn = get_db_connection()
    doc = conn.execute(
        "SELECT file_path FROM excel_documents WHERE id = ?",
        (doc_id,)
    ).fetchone()
    conn.close()

    if not doc:
        return "Dokumen data terstruktur tidak ditemukan.", []

    file_path = Path(doc["file_path"])
    try:
        df = None
        if file_path.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path)
        elif file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path)
        else:
            return "Tipe file data terstruktur tidak didukung untuk pencarian.", []

        df_str = df.astype(str)

        results = []
        query_lower = query.lower()

        for index, row in df_str.iterrows():
            if any(query_lower in str(cell).lower() for cell in row):
                results.append(row.to_dict())
                if len(results) >= 5:
                    break

        if results:
            formatted_results = []
            for i, res in enumerate(results):
                formatted_results.append(f"Row {i+1}: {', '.join(f'{k}: {v}' for k, v in res.items())}")
            return "Ditemukan data relevan di dokumen terstruktur Anda:\n" + "\n".join(formatted_results), results
        else:
            return "Tidak ditemukan data relevan di dokumen terstruktur.", []
    except Exception as e:
        print(f"Error searching structured data: {e}")
        return f"Gagal mencari di dokumen data terstruktur: {str(e)}", []

# Placeholder for Internet Search Function
def search_internet(query: str) -> tuple[str, dict]:
    """
    This is a placeholder for actual internet search integration.
    """
    print(f"Performing internet search for: {query}")
    try:
        return "Ini adalah hasil pencarian dari internet (placeholder): Informasi tentang '" + query + "' dapat ditemukan melalui berbagai sumber online.", {"dummy_result": "internet_search_placeholder"}
    except requests.exceptions.RequestException as e:
        print(f"Error during internet search request: {e}")
        return f"Maaf, gagal melakukan pencarian internet (koneksi/API): {str(e)}", {}
    except Exception as e:
        print(f"Generic error during internet search: {e}")
        return f"Maaf, terjadi kesalahan tak terduga saat pencarian internet: {str(e)}", {}

# --- API ENDPOINTS ---

@app.get("/health", response_model=SystemHealth, tags=["System"])
def health_check():
    """Check if API and dependencies are healthy"""
    health_status = {
        "status": "healthy",
        "groq_api": "disconnected",
        "database": "disconnected",
        "model_info": None
    }

    try:
        response_test = requests.post(GROQ_API_URL, json={
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 5
        }, headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, timeout=5)
        if response_test.status_code == 200:
            health_status["groq_api"] = "connected"
            health_status["model_info"] = {
                "provider": "GROQ",
                "model": "llama3-8b-8192",
                "status": "operational"
            }
        else:
            health_status["groq_api"] = f"error (HTTP {response_test.status_code})"
    except Exception as e:
        health_status["groq_api"] = f"error ({str(e)})"


    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = f"disconnected ({str(e)})"

    if health_status["groq_api"] == "connected" and health_status["database"] == "connected":
        health_status["status"] = "healthy"
    else:
        health_status["status"] = "degraded"

    return health_status

# Endpoint for uploading structured documents (Excel/CSV)
@app.post("/upload-structured-data", response_model=StructuredDocument, tags=["Structured Data"])
async def upload_structured_document(file: UploadFile = File(...)):
    """Upload structured data documents for processing (XLSX, XLS, CSV)"""

    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in ('.xlsx', '.xls', '.csv'):
        raise HTTPException(status_code=400, detail="Hanya file .xlsx, .xls, atau .csv yang diizinkan.")

    doc_id = str(uuid.uuid4())
    file_path = Path(STRUCTURED_DATA_UPLOAD_DIR) / f"{doc_id}{file_extension}"

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        _, row_count = extract_data_from_structured_file(file_path)

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO excel_documents (id, filename, file_path, upload_date, row_count) VALUES (?, ?, ?, ?, ?)",
            (doc_id, file.filename, str(file_path), datetime.now().isoformat(), row_count)
        )
        conn.commit()
        conn.close()

        df_preview = None
        if file_extension in ['.xlsx', '.xls']:
            df_preview = pd.read_excel(file_path)
        elif file_extension == '.csv':
            df_preview = pd.read_csv(file_path)

        data_preview = df_preview.head(5).to_dict(orient='records') if df_preview is not None else []

        return StructuredDocument(
            id=doc_id,
            filename=file.filename,
            upload_date=datetime.now().isoformat(),
            data_preview=data_preview,
            row_count=row_count
        )
    except Exception as e:
        if file_path.exists():
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Gagal memproses file data terstruktur: {e}")


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    message: ChatMessage
):
    """Chat with structured data using GROQ AI, with turn-based logic"""

    conn = get_db_connection()

    ai_response = ""
    source_doc_name = None
    next_action_type = "continue_chat"

    if message.structured_document_id:
        doc_info = conn.execute(
            "SELECT filename, file_path FROM excel_documents WHERE id = ?", (message.structured_document_id,)
        ).fetchone()

        if not doc_info:
            conn.close()
            raise HTTPException(status_code=404, detail="Dokumen data terstruktur tidak ditemukan.")

        source_doc_name = doc_info["filename"]

        cursor = conn.execute(
            "SELECT chat_turn FROM chat_history WHERE excel_document_id = ? ORDER BY timestamp DESC LIMIT 1",
            (message.structured_document_id,)
        )
        last_turn_record = cursor.fetchone()
        last_chat_turn = last_turn_record["chat_turn"] if last_turn_record else 0
        current_chat_turn = last_chat_turn + 1

        if current_chat_turn == 1:
            structured_data_search_result_text, _ = search_structured_data(message.structured_document_id, message.message)

            prompt_to_groq = f"""
            Anda adalah asisten analisis data yang akan menjawab pertanyaan berdasarkan data terstruktur yang disediakan.
            Berikut adalah hasil pencarian dari dokumen data terstruktur yang dipilih:
            {structured_data_search_result_text}

            Berdasarkan hasil pencarian ini, jawablah pertanyaan pengguna: "{message.message}"
            Jika tidak ada data relevan dari dokumen terstruktur, katakan bahwa tidak ditemukan di dokumen terstruktur dan bahwa Anda akan mencari di internet di giliran berikutnya.
            """
            ai_response = query_groq(prompt_to_groq, max_tokens=1500)
            next_action_type = "search_internet"
        else:
            internet_search_result_text, _ = search_internet(message.message)

            prompt_to_groq = f"""
            Anda adalah asisten cerdas yang dapat melakukan pencarian internet.
            Berikut adalah hasil pencarian internet untuk pertanyaan: "{message.message}"
            {internet_search_result_text}

            Berikan jawaban yang komprehensif berdasarkan informasi ini. Jika hasil pencarian internet kurang relevan atau tidak ada, informasikan kepada pengguna dengan sopan.
            """
            ai_response = query_groq(prompt_to_groq, max_tokens=1500)
            next_action_type = "continue_chat"

        conn.execute(
            "INSERT INTO chat_history (message, response, timestamp, is_predefined, excel_document_id, chat_turn) VALUES (?, ?, ?, ?, ?, ?)",
            (message.message, ai_response, datetime.now().isoformat(), message.is_predefined,
             message.structured_document_id, current_chat_turn)
        )

    else: # No structured document selected. General chat.
        general_prompt = f"""
        Anda adalah asisten AI serbaguna. Jika pengguna memberikan dokumen terstruktur, Anda menganalisis dokumen tersebut.
        Jika tidak ada dokumen yang diberikan, Anda bisa menjawab pertanyaan umum.
        Pertanyaan Pengguna: "{message.message}"
        """
        ai_response = query_groq(general_prompt, max_tokens=500)
        next_action_type = "continue_chat"
        conn.execute(
            "INSERT INTO chat_history (message, response, timestamp, is_predefined) VALUES (?, ?, ?, ?)",
            (message.message, ai_response, datetime.now().isoformat(), message.is_predefined)
        )

    conn.commit()
    conn.close()

    return {
        "response": ai_response,
        "source_document_name": source_doc_name,
        "next_action": next_action_type
    }

# Endpoint to get list of all structured data documents (Excel/CSV)
@app.get("/structured-documents", response_model=List[StructuredDocument], tags=["Structured Data"])
def get_structured_documents():
    """Get list of all structured data documents (Excel/CSV)"""
    conn = get_db_connection()
    documents = conn.execute(
        "SELECT id, filename, upload_date, row_count FROM excel_documents ORDER BY upload_date DESC"
    ).fetchall()
    conn.close()

    result = []
    for doc in documents:
        result.append(StructuredDocument(
            id=doc["id"],
            filename=doc["filename"],
            upload_date=doc["upload_date"],
            row_count=doc["row_count"]
        ))
    return result

# NEW: Endpoint to delete a single structured document
@app.delete("/structured-documents/{doc_id}", tags=["Structured Data"])
def delete_structured_document(doc_id: str):
    """Delete a single structured data document by its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get file path before deleting from DB
    doc_info = cursor.execute("SELECT file_path, filename FROM excel_documents WHERE id = ?", (doc_id,)).fetchone()

    if not doc_info:
        conn.close()
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan.")

    file_path = Path(doc_info["file_path"])
    filename = doc_info["filename"]

    try:
        # Delete from database
        cursor.execute("DELETE FROM excel_documents WHERE id = ?", (doc_id,))
        # Also delete related chat history for this document
        cursor.execute("DELETE FROM chat_history WHERE excel_document_id = ?", (doc_id,))
        conn.commit()

        # Delete file from disk
        if file_path.exists():
            os.remove(file_path)
            print(f"Deleted file from disk: {file_path}")

        conn.close()
        return {"message": f"Dokumen '{filename}' dan riwayat chat terkait berhasil dihapus."}
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"Gagal menghapus dokumen: {str(e)}")


@app.get("/history", tags=["Chat"])
def get_chat_history():
    """Get all chat history"""

    conn = get_db_connection()
    history = conn.execute(
        "SELECT message, response, timestamp, is_predefined, excel_document_id, chat_turn FROM chat_history ORDER BY timestamp DESC LIMIT 100"
    ).fetchall()
    conn.close()

    parsed_history = []
    for item in history:
        item_dict = dict(item)
        parsed_history.append(item_dict)

    return {"history": parsed_history}

@app.get("/api-info", tags=["System"])
def get_api_info():
    """Get information about the AI API being used"""
    health = health_check()
    return {
        "provider": "GROQ",
        "model": "llama3-8b-8192",
        "status": health.groq_api,
        "features": [
            "Fast inference speed",
            "High quality responses",
            "Indonesian language support",
            "Structured data (Excel/CSV) analysis (turn 1)",
            "Internet search (turn 2+ for structured data)"
        ],
        "limits": {
            "monthly_tokens": "1,000,000 (free-tier)",
            "max_tokens_per_request": 32768,
            "concurrent_requests": 20
        }
    }

@app.get("/system-stats", response_model=SystemStats, tags=["System"])
def get_system_stats():
    """Get system statistics"""
    conn = get_db_connection()

    total_structured_documents = conn.execute("SELECT COUNT(*) as count FROM excel_documents").fetchone()["count"]
    total_chats = conn.execute("SELECT COUNT(*) as count FROM chat_history").fetchone()["count"]

    recent_activity = []
    recent_chats = conn.execute(
        """
        SELECT message, timestamp
        FROM chat_history
        ORDER BY timestamp DESC
        LIMIT 5
        """
    ).fetchall()

    for chat in recent_chats:
        recent_activity.append({
            "type": "chat",
            "description": f"Asked: {chat['message'][:50]}{'...' if len(chat['message']) > 50 else ''}",
            "timestamp": chat["timestamp"]
        })

    recent_uploads_structured = conn.execute(
        """
        SELECT filename, upload_date
        FROM excel_documents
        ORDER BY upload_date DESC
        LIMIT 5
        """
    ).fetchall()

    for upload in recent_uploads_structured:
        recent_activity.append({
            "type": "upload_structured_data",
            "description": f"Uploaded Data: {upload['filename']}",
            "timestamp": upload["upload_date"]
        })

    recent_activity.sort(key=lambda x: x["timestamp"], reverse=True)
    recent_activity = recent_activity[:10]

    conn.close()

    return SystemStats(
        total_structured_documents=total_structured_documents,
        total_chats=total_chats,
        recent_activity=recent_activity
    )

@app.delete("/clear-all-data", tags=["System"])
def clear_all_data():
    """Clear all uploaded structured data files and chat history from the system. (Internal use, not exposed in UI)"""
    conn = get_db_connection()

    try:
        if os.path.exists(STRUCTURED_DATA_UPLOAD_DIR):
            shutil.rmtree(STRUCTURED_DATA_UPLOAD_DIR)
            Path(STRUCTURED_DATA_UPLOAD_DIR).mkdir(exist_ok=True)

        conn.execute("DELETE FROM excel_documents")
        conn.execute("DELETE FROM chat_history")

        conn.commit()
        conn.close()

        return {"message": "Semua dokumen data terstruktur dan riwayat chat berhasil dihapus."}
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"Gagal menghapus semua data: {str(e)}")

# --- FRONTEND SERVING ---
@app.get("/", response_class=FileResponse, include_in_schema=False)
async def read_index():
    return "index.html"

app.mount("/", StaticFiles(directory="."), name="static_root")

if __name__ == "__main__":
    import uvicorn
    initialize_db()
    print("🚀 Starting Local Structured Data Chat System with GROQ AI (No Authentication)")
    print("📡 API Documentation: http://localhost:8000/docs")
    print("🌐 Frontend Application: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)