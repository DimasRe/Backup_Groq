#!/usr/bin/env python3
"""
Database setup script for Local Structured Data Chat System
This script creates the necessary database tables and initial setup
"""

import sqlite3
import os
from pathlib import Path

def create_database():
    """Create database and tables"""
    print("🗄️  Setting up database...")

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Hapus tabel documents yang lama jika ada (berisi PDF, DOCX, TXT)
    cursor.execute("DROP TABLE IF EXISTS documents")
    print("   Dropped 'documents' table (text files).")

    # Pastikan tabel excel_documents ada (sekarang untuk semua data terstruktur)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS excel_documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            row_count INTEGER
        )
    ''')
    print("   Ensured 'excel_documents' table (structured data) exists.")


    # Perbarui tabel chat_history: Pastikan kolom yang relevan ada
    cursor.execute("PRAGMA table_info(chat_history)")
    columns = [col[1] for col in cursor.fetchall()]

    # Jika tabel belum ada, buat baru
    if "chat_history" not in [col[1] for col in conn.execute("PRAGMA table_list").fetchall() if col[1] == "chat_history"]:
        cursor.execute('''
            CREATE TABLE chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                is_predefined BOOLEAN DEFAULT FALSE,
                excel_document_id TEXT,      -- Untuk referensi dokumen terstruktur
                chat_turn INTEGER DEFAULT 0
            )
        ''')
    else:
        # Tambahkan kolom baru jika belum ada
        if "excel_document_id" not in columns:
            cursor.execute("ALTER TABLE chat_history ADD COLUMN excel_document_id TEXT")
        if "chat_turn" not in columns:
            cursor.execute("ALTER TABLE chat_history ADD COLUMN chat_turn INTEGER DEFAULT 0")
        # Hapus kolom document_ids jika masih ada dari versi lama (memerlukan recreate table)
        # Untuk simplicity di setup.py ini, kita tidak akan secara otomatis menghapus kolom jika sudah ada.
        # Jika Anda ingin bersih total dari `document_ids`, Anda harus menghapus `database.db` secara manual
        # dan biarkan setup.py membuat ulang tabel tanpa kolom itu.

    # Buat indeks
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)')
    print("   Ensured 'chat_history' table is up-to-date with necessary columns.")

    conn.commit()
    conn.close()
    print("✅ Database tables created successfully")

def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")

    # Hanya perlu direktori untuk upload data terstruktur
    directories = ['excel_uploads'] # Hapus 'uploads'

    for dir_name in directories:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"✅ Created directory: {dir_name}")

def check_env_file():
    """Check if .env file exists and has required variables"""
    print("🔧 Checking environment configuration...")

    if not os.path.exists('.env'):
        print("⚠️  WARNING: .env file not found!")
        print("   Please create a .env file with the following variables:")
        print("   - GROQ_API_KEY=your-groq-api-key")
        print("   Get your GROQ API key at: https://console.groq.com/")
        return False

    with open('.env', 'r') as f:
        env_content = f.read()

    required_vars = ['GROQ_API_KEY']
    missing_vars = []

    for var in required_vars:
        if var not in env_content or f'{var}=your-' in env_content.lower():
            missing_vars.append(var)

    if missing_vars:
        print(f"⚠️  WARNING: Missing or unconfigured environment variables: {', '.join(missing_vars)}")
        return False

    print("✅ Environment configuration looks good")
    return True

def install_dependencies():
    """Show dependency installation instructions"""
    print("📦 Dependencies required:")
    print("   pip install -r requirements.txt")
    print("   ")


def create_requirements_file():
    """Create requirements.txt file (reflecting the new, trimmed dependencies)"""
    requirements = """fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
requests==2.31.0
python-dotenv==1.0.0
pandas==2.2.2
openpyxl==3.1.2
"""

    with open('requirements.txt', 'w') as f:
        f.write(requirements.strip())

    print("✅ Created requirements.txt")

def main():
    """Main setup function"""
    print("🚀 Local Structured Data Chat System - Setup")
    print("=" * 50)

    create_requirements_file()
    print()

    install_dependencies()
    print()

    create_directories()
    print()

    create_database()
    print()

    env_ok = check_env_file()
    print()

    print("=" * 50)
    if env_ok:
        print("✅ Setup completed successfully!")
        print("🚀 You can now run: python app.py")
    else:
        print("⚠️  Setup completed with warnings")
        print("📝 Please configure your .env file before running the application")

    print("\n📖 Next steps:")
    print("1. Configure your .env file with GROQ API key (if not already done)")
    print("2. Install dependencies: pip install -r requirements.txt")
    print("3. Run the application: python app.py")
    print("4. Open browser: http://localhost:8000")
    print("\nNote: This is a local-only, no-authentication version of the system.")

if __name__ == "__main__":
    main()