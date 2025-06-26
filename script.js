// Local Structured Data Chat System - Main JavaScript
// Version: 3.4.1 (Implemented individual Delete button for structured data)

// --- GLOBAL STATE & CONFIGURATION ---
const API_BASE_URL = 'http://localhost:8000';

const MAX_STRUCTURED_FILES_UPLOAD = 1;
const MAX_STRUCTURED_FILE_SIZE_MB = 10;
const MAX_STRUCTURED_FILE_SIZE_BYTES = MAX_STRUCTURED_FILE_SIZE_MB * 1024 * 1024;

let selectedChatStructuredDocumentId = null;
let currentChatSessionMessages = [];
let selectedStructuredUploadFile = null;
let confirmCallback = null;

// --- DOM ELEMENTS CACHE ---
const elements = {
    loadingOverlay: document.getElementById('loading-overlay'),
    dashboardSection: document.getElementById('dashboard-section'),

    navLinks: {
        uploadStructured: document.getElementById('nav-upload-structured'),
        structuredDocuments: document.getElementById('nav-structured-documents'),
        chat: document.getElementById('nav-chat'),
        history: document.getElementById('nav-history'),
        faq: document.getElementById('nav-faq'),
    },

    contentSections: {
        uploadStructured: document.getElementById('upload-structured-section'),
        structuredDocuments: document.getElementById('structured-documents-section'),
        chat: document.getElementById('chat-section'),
        history: document.getElementById('history-section'),
        faq: document.getElementById('faq-section'),
    },

    uploadStructuredForm: document.getElementById('upload-structured-form'),
    uploadStructuredArea: document.getElementById('upload-structured-area'),
    structuredFileInput: document.getElementById('structured-file-input'),
    structuredFileListDisplay: document.getElementById('structured-file-list'),
    uploadStructuredBtn: document.getElementById('upload-structured-btn'),

    structuredDocumentsContainer: document.getElementById('structured-documents-container'),

    chatStructuredDocumentList: document.getElementById('chat-structured-document-list'),
    predefinedQuestionsContainer: document.getElementById('predefined-questions'),
    predefinedQuestionsList: document.getElementById('questions-list'),
    chatMessagesContainer: document.getElementById('chat-messages'),
    chatForm: document.getElementById('chat-form'),
    chatInput: document.getElementById('chat-input'),
    chatSendBtn: document.getElementById('chat-send-btn'),

    historyContainer: document.getElementById('history-container'),
    faqContainer: document.querySelector('.faq-container'),
    alertContainer: document.getElementById('alert-container'),
    confirmationModal: {
        element: document.getElementById('confirmation-modal'),
        title: document.getElementById('modal-title'),
        message: document.getElementById('modal-message'),
        cancelBtn: document.getElementById('modal-cancel'),
        confirmBtn: document.getElementById('modal-confirm'),
    },
    // The "Clear All Data" button itself is removed from HTML, so this cache is no longer directly used for an event listener.
    // clearAllDataBtn: document.getElementById('clear-all-data-btn')
};

// --- UTILITY FUNCTIONS ---
function showLoading(show = true) {
    if (elements.loadingOverlay) {
        elements.loadingOverlay.style.display = show ? 'flex' : 'none';
    }
}

function hideLoading() {
    if (elements.loadingOverlay) {
        elements.loadingOverlay.style.display = 'none';
    }
}

function showAlert(message, type = 'info', duration = 5000) {
    if (!elements.alertContainer) return;
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.setAttribute('role', 'alert');
    alertDiv.textContent = message;
    elements.alertContainer.appendChild(alertDiv);
    setTimeout(() => {
        alertDiv.style.opacity = '0';
        setTimeout(() => alertDiv.remove(), 400);
    }, duration - 400);
}

function showModal(title, message, onConfirm) {
    const modal = elements.confirmationModal;
    if (!modal || !modal.element) return;
    modal.title.textContent = title;
    modal.message.textContent = message;
    modal.element.classList.add('active');
    modal.element.style.display = 'flex';
    confirmCallback = onConfirm;
}

function closeModal() {
    const modal = elements.confirmationModal;
    if (!modal || !modal.element) return;
    modal.element.classList.remove('active');
    modal.element.style.display = 'none';
    confirmCallback = null;
}

function formatDate(dateString) {
    if (!dateString) return 'Tanggal tidak diketahui';
    try {
        return new Date(dateString).toLocaleString('id-ID', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch (e) {
        return dateString;
    }
}

function setButtonLoading(buttonElement, isLoading, originalText = "Submit") {
    if (!buttonElement) return;
    if (isLoading) {
        buttonElement.disabled = true;
        if (!buttonElement.dataset.originalText) {
            buttonElement.dataset.originalText = buttonElement.innerHTML;
        }
        buttonElement.innerHTML = `<span class="loading-spinner-btn"></span> Memproses...`;
    } else {
        buttonElement.disabled = false;
        buttonElement.innerHTML = buttonElement.dataset.originalText || originalText;
    }
}

function sanitizeText(text) {
    if (text === null || typeof text === 'undefined') return '';
    const tempDiv = document.createElement('div');
    tempDiv.textContent = String(text);
    return tempDiv.innerHTML;
}

function renderEmptyState(containerElement, message) {
    if (containerElement) {
        containerElement.innerHTML = `<div class="empty-state"><p>${sanitizeText(message)}</p></div>`;
    }
}

// --- API FUNCTIONS ---
async function apiCall(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const config = {
        ...options,
        headers: {
            ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
            ...options.headers,
        },
    };

    try {
        const response = await fetch(url, config);
        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.json();
            } catch (e) {
                errorData = { detail: `Server error: ${response.status} ${response.statusText}.` };
            }
            throw new Error(errorData.detail || `HTTP error ${response.status}`);
        }
        if (response.status === 204 || response.headers.get("content-length") === "0") {
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('API Call Error:', error.message, `Endpoint: ${endpoint}`);
        throw new Error(error.message || 'Gagal terhubung ke server. Periksa koneksi Anda.');
    }
}

// --- GENERAL APP STATE & UI FUNCTIONS ---
function resetAppState() {
    selectedChatStructuredDocumentId = null;
    currentChatSessionMessages = [];
    selectedStructuredUploadFile = null;

    if (elements.uploadStructuredForm) elements.uploadStructuredForm.reset();
    updateSelectedStructuredFilesUI();
    resetChatUI();
}

function showDashboard() {
    elements.dashboardSection.style.display = 'flex';
    navigateToSection('uploadStructured');
}

function navigateToSection(sectionName) {
    Object.values(elements.contentSections).forEach(section => {
        if(section) section.classList.remove('active');
    });
    Object.values(elements.navLinks).forEach(link => {
        if (link) {
            link.classList.remove('active');
            link.removeAttribute('aria-current');
        }
    });

    if (elements.contentSections[sectionName]) {
        elements.contentSections[sectionName].classList.add('active');
    }
    if (elements.navLinks[sectionName]) {
        elements.navLinks[sectionName].classList.add('active');
        elements.navLinks[sectionName].setAttribute('aria-current', 'page');
    }

    showLoading();
    let loadPromise;
    switch (sectionName) {
        case 'uploadStructured':
            loadPromise = Promise.resolve();
            break;
        case 'structuredDocuments':
            loadPromise = loadAllStructuredDocuments();
            break;
        case 'chat':
            loadPromise = loadStructuredDocumentsForChat();
            break;
        case 'history':
            loadPromise = loadAllChatHistory();
            break;
        case 'faq':
            loadPromise = Promise.resolve();
            break;
        default:
            console.warn(`Navigasi ke bagian tidak dikenal: ${sectionName}`);
            loadPromise = Promise.resolve();
    }
    if (loadPromise && typeof loadPromise.finally === 'function') {
        loadPromise.catch(err => {
            console.error(`Error loading section ${sectionName}:`, err);
        }).finally(() => {
            hideLoading();
        });
    } else {
        hideLoading();
    }
}

// --- STRUCTURED DOCUMENT UPLOAD & LISTING (Excel/CSV) ---
function handleStructuredFileSelection(eventFiles) {
    if (eventFiles.length === 0) {
        selectedStructuredUploadFile = null;
        updateSelectedStructuredFilesUI();
        return;
    }
    const file = eventFiles[0];

    if (file.size > MAX_STRUCTURED_FILE_SIZE_BYTES) {
        showAlert(`File data terstruktur "${sanitizeText(file.name)}" (${(file.size / 1024 / 1024).toFixed(2)}MB) melebihi batas ${MAX_STRUCTURED_FILE_SIZE_MB}MB.`, 'error', 7000);
        selectedStructuredUploadFile = null;
    } else {
        const allowedExtensions = ['xlsx', 'xls', 'csv'];
        const fileExtension = file.name.split('.').pop().toLowerCase();
        if (!allowedExtensions.includes(fileExtension)) {
            showAlert(`Tipe file "${sanitizeText(file.name)}" tidak didukung. Hanya XLSX, XLS, CSV.`, 'error', 7000);
            selectedStructuredUploadFile = null;
        } else {
            selectedStructuredUploadFile = file;
        }
    }
    updateSelectedStructuredFilesUI();
    if (elements.uploadStructuredBtn) elements.uploadStructuredBtn.disabled = !selectedStructuredUploadFile;
}

function updateSelectedStructuredFilesUI() {
    if (!elements.structuredFileListDisplay) return;
    elements.structuredFileListDisplay.innerHTML = '';

    if (!selectedStructuredUploadFile) {
        renderEmptyState(elements.structuredFileListDisplay, "Belum ada file data terstruktur dipilih.");
        if (elements.uploadStructuredBtn) elements.uploadStructuredBtn.disabled = true;
        return;
    }

    const file = selectedStructuredUploadFile;
    const fileSizeMB = (file.size / 1024 / 1024).toFixed(2);
    const fileItem = document.createElement('div');
    fileItem.className = 'file-item';
    fileItem.innerHTML = `
        <div class="file-info">
            <span class="file-icon" aria-hidden="true">📊</span>
            <span class="file-name">${sanitizeText(file.name)}</span>
            <span class="file-size">(${fileSizeMB} MB)</span>
        </div>
        <button type="button" class="file-remove" data-index="0" aria-label="Hapus file ${sanitizeText(file.name)}">×</button>
    `;
    elements.structuredFileListDisplay.appendChild(fileItem);
    if (elements.uploadStructuredBtn) elements.uploadStructuredBtn.disabled = false;
}

function removeStructuredFileFromSelection() {
    selectedStructuredUploadFile = null;
    if (elements.structuredFileInput) elements.structuredFileInput.value = '';
    updateSelectedStructuredFilesUI();
}

async function performUploadStructuredDocument() {
    if (!selectedStructuredUploadFile) {
        showAlert("Tidak ada file data terstruktur yang dipilih untuk diunggah.", "info");
        return;
    }
    setButtonLoading(elements.uploadStructuredBtn, true, "Unggah Data");

    const formData = new FormData();
    formData.append('file', selectedStructuredUploadFile);

    try {
        const data = await apiCall('/upload-structured-data', { method: 'POST', body: formData });
        showAlert(`Dokumen data terstruktur "${sanitizeText(data.filename)}" berhasil diunggah!`, 'success');

        selectedStructuredUploadFile = null;
        if (elements.structuredFileInput) elements.structuredFileInput.value = '';
        updateSelectedStructuredFilesUI();

        showModal(
            "Unggah Selesai",
            `Dokumen data terstruktur "${sanitizeText(data.filename)}" (${data.row_count} baris) berhasil diunggah. Apakah Anda ingin langsung chat dengan data ini?`,
            () => {
                selectedChatStructuredDocumentId = data.id;
                navigateToSection('chat');
            }
        );

    } catch (error) {
        showAlert(`Error Unggah Dokumen Data Terstruktur: ${error.message}`, 'error');
    } finally {
        setButtonLoading(elements.uploadStructuredBtn, false, "Unggah Data");
    }
}

async function loadAllStructuredDocuments() {
    try {
        const data = await apiCall('/structured-documents');
        renderStructuredDocumentList(data || [], elements.structuredDocumentsContainer);
    } catch (error) {
        showAlert(`Gagal memuat dokumen data terstruktur: ${error.message}`, 'error');
        renderEmptyState(elements.structuredDocumentsContainer, 'Gagal memuat dokumen data terstruktur.');
    } finally {
        // hideLoading() will be called by navigateToSection
    }
}

// MODIFIED: renderStructuredDocumentList to include the Delete button
function renderStructuredDocumentList(documents, containerElement = elements.structuredDocumentsContainer) {
    if (!containerElement) return;
    containerElement.innerHTML = '';

    if (!documents || documents.length === 0) {
        renderEmptyState(containerElement, 'Tidak ada dokumen data terstruktur di sistem.');
        return;
    }

    documents.forEach(doc => {
        const docCard = document.createElement('div');
        docCard.className = 'document-card';
        docCard.setAttribute('tabindex', '0');
        docCard.setAttribute('aria-labelledby', `doc-title-${doc.id}`);

        // Added delete button HTML
        const actionsHtml = `
            <button class="btn btn-primary btn-small action-chat-structured" data-doc-id="${doc.id}" data-doc-filename="${sanitizeText(doc.filename)}">Chat</button>
            <button class="btn btn-danger btn-small action-delete-structured" data-doc-id="${doc.id}" data-doc-filename="${sanitizeText(doc.filename)}">Hapus</button>
        `;

        docCard.innerHTML = `
            <div class="document-header">
                <h3 class="document-title" id="doc-title-${doc.id}">${sanitizeText(doc.filename)}</h3>
                <p class="document-meta">
                    Diunggah: ${formatDate(doc.upload_date)}<br>
                    Baris: ${doc.row_count || 'N/A'}
                </p>
            </div>
            <div class="document-actions">${actionsHtml}</div>
        `;
        containerElement.appendChild(docCard);
    });
}

// --- CHAT LOGIC ---
async function loadStructuredDocumentsForChat() {
    console.log("Loading structured documents for chat sidebar...");
    try {
        const structuredData = await apiCall('/structured-documents');
        renderChatDocumentSelectionList(structuredData || [], elements.chatStructuredDocumentList, 'structured');

        if (selectedChatStructuredDocumentId) {
            const stillExists = (structuredData || []).some(doc => doc.id === selectedChatStructuredDocumentId);
            if (stillExists) {
                document.querySelectorAll('#chat-structured-document-list .chat-document-item').forEach(item => {
                    const isCurrentSelected = (item.dataset.docId === selectedChatStructuredDocumentId);
                    item.classList.toggle('selected', isCurrentSelected);
                    item.setAttribute('aria-pressed', isCurrentSelected ? 'true' : 'false');
                });
            } else {
                selectedChatStructuredDocumentId = null;
                resetChatUI();
            }
        } else {
            resetChatUI();
        }
        if(elements.predefinedQuestionsContainer) elements.predefinedQuestionsContainer.style.display = 'none';

    }
    catch (error) {
        showAlert(`Gagal memuat dokumen data terstruktur untuk chat: ${error.message}`, 'error');
        renderEmptyState(elements.chatStructuredDocumentList, 'Gagal memuat dokumen data terstruktur.');
        resetChatUI();
    } finally {
        // hideLoading() will be called by navigateToSection
    }
}

function renderChatDocumentSelectionList(documents, containerElement, docType) {
    containerElement.innerHTML = '';
    if (!documents || documents.length === 0) {
        renderEmptyState(containerElement, `Belum ada dokumen ${docType === 'structured' ? 'data terstruktur' : ''} untuk dichat.`);
        return;
    }
    documents.forEach(doc => {
        const docItem = document.createElement('div');
        docItem.className = 'chat-document-item';
        docItem.dataset.docId = doc.id;
        docItem.dataset.docFilename = doc.filename;
        docItem.dataset.docType = docType;
        docItem.setAttribute('tabindex', '0');
        docItem.setAttribute('role', 'button');
        docItem.innerHTML = `<div class="document-title">${sanitizeText(doc.filename)}</div>
                                 <div class="document-meta">${formatDate(doc.upload_date)}</div>`;
        containerElement.appendChild(docItem);
    });
}

function activateChatWithDocument(docId, docFilename, docType) {
    console.log("Activating chat with document:", docId, docFilename, docType);

    if (selectedChatStructuredDocumentId !== docId) {
        selectedChatStructuredDocumentId = docId;
        currentChatSessionMessages = [];
        renderChatMessageHistoryUI();
        showAlert(`Data "${sanitizeText(docFilename)}" dipilih. Anda bisa mulai chat.`, 'info', 3000);
    } else {
        console.log("Document already active, just navigating.");
    }

    document.querySelectorAll('#chat-structured-document-list .chat-document-item').forEach(item => {
        const isCurrentSelected = (item.dataset.docId === docId);
        item.classList.toggle('selected', isCurrentSelected);
        item.setAttribute('aria-pressed', isCurrentSelected ? 'true' : 'false');
    });

    if(elements.chatInput) {
        elements.chatInput.disabled = false;
        elements.chatInput.placeholder = `Bertanya tentang ${sanitizeText(docFilename || "data terpilih")}...`;
        elements.chatInput.focus();
    }
    if(elements.chatSendBtn) elements.chatSendBtn.disabled = false;

    if(elements.predefinedQuestionsContainer) elements.predefinedQuestionsContainer.style.display = 'none';
    navigateToSection('chat');
}

function resetChatUI() {
    selectedChatStructuredDocumentId = null;
    currentChatSessionMessages = [];
    if(elements.chatInput) {
        elements.chatInput.disabled = true;
        elements.chatInput.placeholder = 'Pilih data untuk memulai chat...';
    }
    if(elements.chatSendBtn) elements.chatSendBtn.disabled = true;
    if(elements.predefinedQuestionsContainer) elements.predefinedQuestionsContainer.style.display = 'none';

    document.querySelectorAll('#chat-structured-document-list .chat-document-item').forEach(item => {
        item.classList.remove('selected');
        item.setAttribute('aria-pressed', 'false');
    });

    renderChatMessageHistoryUI();
}

function submitChatMessage(messageContent) {
    console.log("Submit chat message called.");
    console.log("Selected structured doc ID:", selectedChatStructuredDocumentId);
    console.log("Message content:", messageContent);

    if (!selectedChatStructuredDocumentId) {
        showAlert("Pilih data terstruktur terlebih dahulu untuk memulai chat.", "error");
        return;
    }
    if (!messageContent.trim()) {
        showAlert("Ketik pertanyaan Anda pada kolom input.", "info");
        return;
    }

    addMessageToChatUI(messageContent, 'user', new Date().toISOString());
    if (elements.chatInput) elements.chatInput.value = '';
    setButtonLoading(elements.chatSendBtn, true, "Kirim");
    if (elements.chatInput) elements.chatInput.disabled = true;

    (async () => {
        try {
            const payload = {
                message: messageContent,
                structured_document_id: selectedChatStructuredDocumentId,
            };
            console.log("Sending payload to /chat:", payload);

            const responseData = await apiCall('/chat', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            console.log("Received response from /chat:", responseData);


            addMessageToChatUI(responseData.response, 'assistant', new Date().toISOString());

            if (selectedChatStructuredDocumentId) {
                if (responseData.next_action === "search_internet") {
                    showAlert("AI akan menggunakan pencarian internet untuk pertanyaan selanjutnya mengenai data ini.", "info", 5000);
                }
            }

        } catch (error) {
            console.error("Error during chat submission:", error);
            showAlert(`Error Chat: ${error.message}`, 'error');
            addMessageToChatUI('Maaf, terjadi kesalahan internal saat memproses pertanyaan Anda.', 'assistant', new Date().toISOString());
        } finally {
            setButtonLoading(elements.chatSendBtn, false, "Kirim");
            if (elements.chatInput) {
                elements.chatInput.disabled = false;
                elements.chatInput.focus();
            }
        }
    })();
}

function addMessageToChatUI(content, sender, timestamp, isNew = true) {
    if (!elements.chatMessagesContainer) return;
    const welcomeMsg = elements.chatMessagesContainer.querySelector('.chat-welcome');
    if (welcomeMsg && isNew) {
        welcomeMsg.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;

    const metaDiv = document.createElement('div');
    metaDiv.className = 'message-meta';
    metaDiv.textContent = formatDate(timestamp);

    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(metaDiv);
    elements.chatMessagesContainer.appendChild(messageDiv);
    elements.chatMessagesContainer.scrollTop = elements.chatMessagesContainer.scrollHeight;

    if (isNew) {
        currentChatSessionMessages.push({ content, sender, timestamp });
    }
}

function renderChatMessageHistoryUI() {
    if (!elements.chatMessagesContainer) return;
    elements.chatMessagesContainer.innerHTML = '';

    if (currentChatSessionMessages.length === 0) {
        const welcomeDiv = document.createElement('div');
        welcomeDiv.className = 'chat-welcome';
        welcomeDiv.innerHTML = `
            <p>Pilih data terstruktur di samping untuk memulai percakapan dengan AI.</p>
            <p>Anda bisa bertanya tentang isi data, atau melanjutkan chat untuk pencarian internet.</p>
        `;
        elements.chatMessagesContainer.appendChild(welcomeDiv);
    } else {
        currentChatSessionMessages.forEach(msg => {
            addMessageToChatUI(msg.content, msg.sender, msg.timestamp, false);
        });
    }
}


async function loadAllChatHistory() {
    try {
        const data = await apiCall('/history');
        renderChatHistoryList(data.history || []);
    }
    catch (error) {
        showAlert(`Gagal memuat riwayat chat: ${error.message}`, 'error');
        renderEmptyState(elements.historyContainer, 'Gagal memuat riwayat percakapan.');
    } finally {
        // hideLoading() will be called by navigateToSection
    }
}

function renderChatHistoryList(historyItems) {
    if (!elements.historyContainer) return;
    elements.historyContainer.innerHTML = '';
    if (!historyItems || historyItems.length === 0) {
        renderEmptyState(elements.historyContainer, 'Belum ada riwayat chat yang tersimpan.');
        return;
    }
    historyItems.forEach(item => {
        const historyItemDiv = document.createElement('div');
        historyItemDiv.className = 'history-item';

        let docContextInfo = "Konteks Umum";
        if (item.excel_document_id) {
            docContextInfo = `Dok. Data ID: ${sanitizeText(item.excel_document_id)}`;
            if (item.chat_turn && item.chat_turn === 1) {
                docContextInfo += " (Pencarian Data)";
            } else if (item.chat_turn && item.chat_turn > 1) {
                docContextInfo += " (Pencarian Internet)";
            }
        }

        historyItemDiv.innerHTML = `
            <div class="history-question"><strong>Q:</strong> <span class="question-text">${sanitizeText(item.message)}</span></div>
            <div class="history-answer"><span class="answer-text">${sanitizeText(item.response)}</span></div>
            <div class="history-meta">
                <span>${sanitizeText(docContextInfo)}</span>
                <span>${formatDate(item.timestamp)}</span>
            </div>
        `;
        elements.historyContainer.appendChild(historyItemDiv);
    });
}

// Removed the global clearAllData function and its button listener.
// Individual delete handles confirmation.

// --- EVENT LISTENERS & APP INITIALIZATION ---

function initializeEventListeners() {
    // Main Navigation
    Object.entries(elements.navLinks).forEach(([sectionName, navElement]) => {
        navElement?.addEventListener('click', (e) => {
            e.preventDefault();
            navigateToSection(sectionName);
        });
    });

    // Structured Document Upload (Excel/CSV)
    const uploadStructuredArea = elements.uploadStructuredArea;
    if (uploadStructuredArea) {
        uploadStructuredArea.addEventListener('click', () => elements.structuredFileInput?.click());
        uploadStructuredArea.addEventListener('keypress', (e) => { if (e.key === 'Enter' || e.key === ' ') elements.structuredFileInput?.click(); });
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadStructuredArea.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); }, false);
        });
        uploadStructuredArea.addEventListener('dragenter', () => uploadStructuredArea.classList.add('dragover'));
        uploadStructuredArea.addEventListener('dragleave', () => uploadStructuredArea.classList.remove('dragover'));
        uploadStructuredArea.addEventListener('drop', (e) => {
            uploadStructuredArea.classList.remove('dragover');
            handleStructuredFileSelection(e.dataTransfer.files);
        });
    }
    elements.structuredFileInput?.addEventListener('change', (e) => handleStructuredFileSelection(e.target.files));
    elements.uploadStructuredForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        await performUploadStructuredDocument();
    });
    elements.structuredFileListDisplay?.addEventListener('click', (e) => {
        const removeButton = e.target.closest('.file-remove');
        if (removeButton) {
            removeStructuredFileFromSelection();
        }
    });

    // Removed Clear All Data Button event listener

    // Document & Chat Actions (for structured documents list)
    elements.structuredDocumentsContainer?.addEventListener('click', (e) => {
        const targetChatButton = e.target.closest('button.action-chat-structured');
        const targetDeleteButton = e.target.closest('button.action-delete-structured'); // New delete button listener

        if (targetChatButton) {
            const docId = targetChatButton.dataset.docId;
            const docFilename = targetChatButton.dataset.docFilename;
            console.log(`Chat button clicked from Document List for Doc ID: ${docId}, Filename: ${docFilename}`);
            activateChatWithDocument(docId, docFilename, 'structured');
        } else if (targetDeleteButton) { // Handle delete button click
            const docId = targetDeleteButton.dataset.docId;
            const docFilename = targetDeleteButton.dataset.docFilename;
            console.log(`Delete button clicked for Doc ID: ${docId}, Filename: ${docFilename}`);
            confirmDeleteStructuredDocument(docId, docFilename); // Call confirmation function
        }
    });

    // Chat document selection (in chat sidebar)
    elements.chatStructuredDocumentList?.addEventListener('click', (e) => {
        const targetItem = e.target.closest('.chat-document-item');
        if (targetItem?.dataset.docId && targetItem?.dataset.docType) {
            console.log(`Chat document selected from sidebar for Doc ID: ${targetItem.dataset.docId}`);
            activateChatWithDocument(targetItem.dataset.docId, targetItem.dataset.docFilename, targetItem.dataset.docType);
        }
    });

    if (elements.predefinedQuestionsList) {
        elements.predefinedQuestionsList.addEventListener('click', (e) => {
            const targetQuestion = e.target.closest('.question-item');
            if (targetQuestion) {
                submitChatMessage(targetQuestion.textContent);
            }
        });
    }

    elements.chatForm?.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = elements.chatInput.value.trim();
        if (message) submitChatMessage(message);
    });

    // FAQ Accordion
    elements.faqContainer?.addEventListener('click', (e) => {
        const questionButton = e.target.closest('.faq-question');
        if (questionButton) {
            const isActive = questionButton.classList.toggle('active');
            const answer = questionButton.nextElementSibling;
            answer.style.maxHeight = isActive ? answer.scrollHeight + "px" : null;
        }
    });

    // Modal Confirmation
    elements.confirmationModal.confirmBtn?.addEventListener('click', () => {
        if (typeof confirmCallback === 'function') confirmCallback();
        closeModal();
    });
    elements.confirmationModal.cancelBtn?.addEventListener('click', closeModal);
    elements.confirmationModal.element?.addEventListener('click', (e) => {
        if (e.target === elements.confirmationModal.element) closeModal();
    });
}

// NEW: Function to confirm and delete a single structured document
async function confirmDeleteStructuredDocument(docId, filename) {
    showModal(
        "Hapus Data",
        `Apakah Anda yakin ingin menghapus dokumen "${sanitizeText(filename)}"? Riwayat chat yang terkait juga akan dihapus. Tindakan ini tidak dapat diurungkan.`,
        async () => {
            showLoading();
            try {
                // Call the new backend endpoint for deleting a single document
                const response = await apiCall(`/structured-documents/${docId}`, { method: 'DELETE' });
                showAlert(response.message || `Dokumen "${sanitizeText(filename)}" berhasil dihapus.`, 'success');

                // After deletion, refresh the document list
                await loadAllStructuredDocuments();

                // If the deleted document was currently selected for chat, reset chat UI
                if (selectedChatStructuredDocumentId === docId) {
                    resetChatUI();
                }
            } catch (error) {
                showAlert(`Gagal menghapus dokumen "${sanitizeText(filename)}": ${error.message}`, 'error');
            } finally {
                hideLoading();
            }
        }
    );
}


async function initializeApp() {
    console.log("Initializing local structured data chat application...");
    showLoading();
    try {
        initializeEventListeners();
        showDashboard();
    } catch (error) {
        console.error("Error during application initialization:", error);
        showAlert("Terjadi kesalahan saat memulai aplikasi. Silakan coba lagi.", "error");
    } finally {
        hideLoading();
    }
}

document.addEventListener('DOMContentLoaded', initializeApp);