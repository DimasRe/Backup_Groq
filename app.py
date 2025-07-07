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
import csv
import random # For picking random examples

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
    next_action: str = "continue_chat" # 'continue_chat', 'await_selection'

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
            -- excel_document_id bisa tetap ada untuk konteks chat terkait dokumen unggahan,
            -- tapi tidak lagi untuk Data_Full_Name.csv
            excel_document_id TEXT, 
            chat_turn INTEGER DEFAULT 0 
        )
    """)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

# --- GLOBAL VARIABLES for archive data and conversation state ---
ARCHIVE_DATA = [] # Akan menyimpan data dari Data_Full_Name.csv
# Menyimpan konteks percakapan untuk 'deep dive'
# Contoh: {'last_search_results': [...], 'state': 'initial_search'/'awaiting_selection'/'deep_diving'}
conversation_context = {} 

# --- Fungsi untuk memuat data arsip dari Data_Full_Name.csv ---
def load_archive_data(csv_file_path="Data_Full_Name.csv"):
    global ARCHIVE_DATA
    try:
        # Membaca CSV tanpa header, setiap baris adalah satu entri
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            ARCHIVE_DATA = [row[0].strip() for row in reader if row and row[0].strip()] 
        print(f"[INFO] Data arsip berhasil dimuat dari {csv_file_path}. Jumlah entri: {len(ARCHIVE_DATA)}")
    except FileNotFoundError:
        print(f"[ERROR] File CSV '{csv_file_path}' tidak ditemukan. Fitur pencarian awal mungkin tidak berfungsi.")
        ARCHIVE_DATA = [] 
    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan saat memuat CSV '{csv_file_path}': {e}")
        ARCHIVE_DATA = []

# --- Fungsi untuk melakukan pencarian di ARCHIVE_DATA (Data_Full_Name.csv) ---
def search_initial_archive_list(query: str) -> List[str]:
    query_lower = query.lower()
    results = [entry for entry in ARCHIVE_DATA if query_lower in entry.lower()]
    return results

# Function to extract data from Excel or CSV (for uploaded files, unchanged)
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
                    "content": "Anda adalah asisten cerdas yang fokus pada pencarian dan penjelasan arsip serta data terstruktur. Berikan jawaban yang akurat, informatif, dan relevan dalam bahasa Indonesia. Jika pertanyaan tidak relevan dengan arsip atau data terstruktur, jawablah dengan sopan bahwa Anda hanya berfokus pada informasi tersebut."
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

# Function for searching structured data (Excel or CSV that were UPLOADED, unchanged logic)
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

# Placeholder for Internet Search Function (unchanged)
def search_internet(query: str) -> tuple[str, dict]:
    """
    This is a placeholder for actual internet search integration.
    """
    print(f"Performing internet search for: {query}")
    try:
        return "Ini adalah hasil pencarian dari internet (placeholder): Informasi tentang '" + query + "' dapat ditemukan melalui berbagai sumber online.", {"dummy_result": "internet_search_placeholder"}
    except requests.exceptions.RequestError as e:
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

    global conversation_context 
    conn = get_db_connection()

    ai_response = ""
    source_doc_name = None
    next_action_type = "continue_chat" 
    
    user_message_lower = message.message.lower()

    print(f"\n[DEBUG] Pesan Pengguna: {message.message}")
    print(f"[DEBUG] Status Konteks Awal: {conversation_context.get('state', 'none')}")
    print(f"[DEBUG] Jumlah Entri ARCHIVE_DATA: {len(ARCHIVE_DATA)}")


    # --- Step 1: Check for numerical deep dive selection ---
    try:
        user_choice = int(user_message_lower.strip())
        if 'state' in conversation_context and conversation_context['state'] == 'awaiting_selection':
            last_results = conversation_context.get('last_search_results', [])
            if 1 <= user_choice <= len(last_results):
                selected_item = last_results[user_choice - 1]
                conversation_context['selected_item'] = selected_item
                conversation_context['state'] = 'deep_diving'
                
                print(f"[DEBUG] Intent: Deep Dive (pilihan nomor {user_choice})")

                # --- Logika Deep Dive ---
                prompt_for_deep_dive = f"""
                Pengguna telah memilih arsip berjudul: "{selected_item}".
                Sebagai asisten cerdas yang fokus pada arsip, jelaskan lebih detail tentang arsip ini. 
                Sertakan konteks umum mengenai jenis arsip seperti ini (misalnya, jika 'Inventaris Arsip', jelaskan apa itu inventaris arsip dan apa yang mungkin terkandung di dalamnya). 
                Jelaskan dengan jelas dan informatif.
                """
                ai_response = query_groq(prompt_for_deep_dive, max_tokens=1000)
                ai_response += "\n\nApakah ada hal lain yang ingin Anda tanyakan terkait ini, atau ingin mencari arsip lain?"
                next_action_type = "continue_chat" 
                source_doc_name = "Daftar Khasanah Arsip (Data_Full_Name.csv)"
            else:
                ai_response = "Pilihan nomor tidak valid. Silakan pilih nomor dari daftar hasil sebelumnya, atau ketikkan pencarian baru."
                next_action_type = "await_selection" 
                if 'last_search_results' in conversation_context and conversation_context['last_search_results']:
                    response_text = "Berikut adalah hasil pencarian yang relevan:\n"
                    for i, entry in enumerate(conversation_context['last_search_results']):
                        response_text += f"{i+1}. {entry}\n"
                    response_text += "\n\nUntuk informasi lebih detail mengenai salah satu hasil di atas, silakan sebutkan nomornya (misal: '1')."
                    ai_response = response_text
                else:
                    ai_response = "Maaf, saya tidak memiliki daftar hasil pencarian sebelumnya untuk dipilih."
            
            # Jika ini adalah pilihan nomor, kita selesai memproses di blok try.
            # Lanjutkan ke penyimpanan histori chat di bagian akhir fungsi.
            pass 
        else: # Angka diketik tapi tidak dalam mode awaiting_selection, lanjutkan ke intent classification
            raise ValueError("Not a valid selection for current state.") # Paksa ke blok except
    except ValueError: # Pesan pengguna bukan angka, atau angka tidak valid untuk deep dive
        # Reset state jika pengguna memulai query baru (bukan deep dive)
        if conversation_context.get('state') not in ['awaiting_selection', 'deep_diving']:
            conversation_context = {'state': 'initial_search'}

        # --- Step 2: Intent Classification (using Groq) ---
        # Ini adalah bagian kunci untuk membedakan antara 'minta contoh umum' vs 'cari spesifik'
        intent_classification_prompt = f"""
        Tinjau permintaan pengguna: "{message.message}"
        Tentukan niat pengguna:
        - Jika pengguna meminta daftar contoh umum atau gambaran isi dari daftar arsip (misalnya, "berikan contoh", "apa isinya", "daftar arsip yang ada", "sebutkan beberapa data").
        - Jika pengguna meminta pencarian dengan kata kunci spesifik yang ada dalam arsip (misalnya, "biro otonomi daerah", "dinas kehutanan", "pabrik gula").

        Jawablah hanya dengan salah satu dari label berikut:
        'INTENT_LIST_GENERAL_EXAMPLES'
        'INTENT_SEARCH_SPECIFIC_KEYWORD'
        'INTENT_OTHER'
        """
        intent_response = query_groq(intent_classification_prompt, max_tokens=20).strip().upper()
        
        print(f"[DEBUG] Intent Response from Groq: {intent_response}")

        if "INTENT_LIST_GENERAL_EXAMPLES" in intent_response:
            print("[DEBUG] Intent: LIST_GENERAL_EXAMPLES")
            if ARCHIVE_DATA:
                num_examples = 5 # Anda bisa mengatur ini
                # Ambil beberapa contoh acak dari ARCHIVE_DATA
                displayed_results = random.sample(ARCHIVE_DATA, min(num_examples, len(ARCHIVE_DATA)))
                
                response_text = "Berikut adalah beberapa contoh dari daftar arsip yang tersedia:\n"
                for i, entry in enumerate(displayed_results):
                    response_text += f"{i+1}. {entry}\n"
                response_text += "\n\nAnda bisa ketikkan nomor untuk detail lebih lanjut, atau ketikkan kata kunci untuk mencari arsip tertentu."
                
                ai_response = response_text
                source_doc_name = "Daftar Khasanah Arsip (Data_Full_Name.csv)"
                next_action_type = "await_selection" 
                conversation_context['last_search_results'] = displayed_results
                conversation_context['state'] = 'awaiting_selection'
            else:
                ai_response = "Maaf, daftar arsip saat ini kosong atau tidak dapat dimuat. Saya tidak bisa memberikan contoh."
                next_action_type = "continue_chat"
                conversation_context = {'state': 'general_chat'}
        
        elif "INTENT_SEARCH_SPECIFIC_KEYWORD" in intent_response:
            print("[DEBUG] Intent: SEARCH_SPECIFIC_KEYWORD")
            # --- Step 3: Initial Keyword Search in Data_Full_Name.csv ---
            search_results = search_initial_archive_list(message.message)

            if search_results:
                display_limit = 10
                displayed_results = search_results[:display_limit]

                response_text = "Berikut adalah hasil pencarian yang relevan dari daftar arsip:\n"
                for i, entry in enumerate(displayed_results):
                    response_text += f"{i+1}. {entry}\n"
                
                if len(search_results) > display_limit:
                    response_text += f"\nAda {len(search_results) - display_limit} hasil lainnya. Silakan perjelas pencarian Anda atau sebutkan nomor untuk detail lebih lanjut."

                response_text += "\n\nUntuk informasi lebih detail mengenai salah satu hasil di atas, silakan sebutkan nomornya (misal: '1')."
                
                ai_response = response_text
                source_doc_name = "Daftar Khasanah Arsip (Data_Full_Name.csv)"
                next_action_type = "await_selection" 
                
                # Simpan hasil pencarian untuk konteks 'deep dive'
                conversation_context['last_search_results'] = displayed_results
                conversation_context['state'] = 'awaiting_selection'

            else:
                # Jika tidak ada hasil dari Data_Full_Name.csv untuk kata kunci spesifik
                print("[DEBUG] Tidak ada hasil dari pencarian keyword di ARCHIVE_DATA.")
                general_prompt = f"""
                Anda adalah asisten AI serbaguna. Anda telah mencoba mencari informasi arsip berdasarkan kata kunci pengguna, tetapi tidak menemukan hasil spesifik di daftar arsip yang tersedia.
                Jika pertanyaan pengguna lebih luas atau tidak terkait arsip, jawablah sebagai asisten umum.
                Pertanyaan Pengguna: "{message.message}"
                """
                ai_response = query_groq(general_prompt, max_tokens=500)
                next_action_type = "continue_chat"
                conversation_context = {'state': 'general_chat'}
        
        else: # INTENT_OTHER or Groq failed to classify
            print("[DEBUG] Intent: OTHER / Tidak terklasifikasi")
            # --- Step 4: Fallback to General Groq for non-archive related queries ---
            general_prompt = f"""
            Anda adalah asisten AI serbaguna. Anda telah mencoba mencari informasi arsip, tetapi tidak menemukan hasil spesifik.
            Jika pertanyaan pengguna bukan tentang arsip, jawablah sebagai asisten umum.
            Pertanyaan Pengguna: "{message.message}"
            """
            ai_response = query_groq(general_prompt, max_tokens=500)
            next_action_type = "continue_chat"
            conversation_context = {'state': 'general_chat'}


    # Catat histori chat ke database
    try:
        conn.execute(
            "INSERT INTO chat_history (message, response, timestamp, is_predefined, excel_document_id, chat_turn) VALUES (?, ?, ?, ?, ?, ?)",
            (message.message, ai_response, datetime.now().isoformat(), message.is_predefined,
             message.structured_document_id, 0) 
        )
        conn.commit()
    except Exception as e:
        print(f"Error saving chat history: {e}")
    finally:
        conn.close()

    return {
        "response": ai_response,
        "source_document_name": source_doc_name,
        "next_action": next_action_type
    }

# Endpoint to get list of all structured data documents (Excel/CSV) - Unchanged
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
            "monthly_tokens": "1,000,000 (free tier)",
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
    """Clear all uploaded structured data files and chat history from the system."""
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
    return FileResponse("index.html") 

app.mount("/", StaticFiles(directory=".", html=True), name="static_root") 

if __name__ == "__main__":
    import uvicorn
    initialize_db()
    load_archive_data() 
    print("🚀 Starting Local Structured Data Chat System with GROQ AI (No Authentication)")
    print("📡 API Documentation: http://localhost:8000/docs")
    print("🌐 Frontend Application: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)