import threading
import sqlite3
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
import os

app = Flask(__name__)
CORS(app)

DB_NAME = "utenti_sogni_server.db"

# 1. Inizializzazione del Database SQLite
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utenti (
            nome TEXT PRIMARY KEY,
            password TEXT,
            sesso TEXT,
            eta TEXT,
            condizione TEXT,
            titolo_studio TEXT,
            tipo_lavoro TEXT,
            hobby TEXT,
            altezza TEXT,
            peso TEXT,
            traumi TEXT,
            medicinali TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sogni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_utente TEXT,
            data TEXT,
            contesto TEXT,
            pasto TEXT,
            sostanze TEXT,
            stato_iniziale TEXT,
            racconto TEXT,
            stato_finale TEXT,
            interpretazione TEXT,
            cabala TEXT,
            FOREIGN KEY (nome_utente) REFERENCES utenti (nome)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 2. Configurazione e Inizializzazione del Client Gemini
client = None
try:
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
        client = genai.Client(api_key=api_key)
        print("Client Gemini inizializzato con successo.")
    else:
        print("Attenzione: GEMINI_API_KEY non trovata nelle variabili d'ambiente.")
except Exception as e:
    print(f"Errore nell'inizializzazione di Gemini: {e}")

# 3. Funzione ultraleggera per il recupero delle estrazioni (zero RAM)
def scarica_ultime_estrazioni():
    try:
        url = "https://www.totoproject.com/giochi/lotto_stat_u50.asp"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            return response.text[:1000]
    except Exception as e:
        print(f"Errore recupero archivio: {e}")
    return "Archivio estrazioni non disponibile temporaneamente."

# 4. Rotta API per la Registrazione Utente
@app.route('/api/registra', methods=['POST'])
def registra():
    data = request.json
    nome = data.get('nome', '').strip()
    password = data.get('password', '').strip()
    
    if not nome or not password:
        return jsonify({"success": False, "error": "Nome utente e password obbligatori."}), 400

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO utenti (nome, password, sesso, eta, condizione, titolo_studio, tipo_lavoro, hobby, altezza, peso, traumi, medicinali)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            nome, password, data.get('sesso'), data.get('eta'), data.get('condizione'),
            data.get('titolo_studio'), data.get('tipo_lavoro'), data.get('hobby'), data.get('altezza'),
            data.get('peso'), data.get('traumi'), data.get('medicinali')
        ))
        conn.commit()
        return jsonify({"success": True}), 200
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Nome utente già esistente."}), 400
    finally:
        conn.close()

# 5. Rotta API per il Login (Case-Insensitive)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    nome = data.get('nome', '').strip()
    password = data.get('password', '').strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM utenti WHERE LOWER(nome) = LOWER(?) AND password = ?', (nome, password))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "error": "Credenziali non valide o utente inesistente."}), 401

    real_name = user[0]
    cursor.execute('SELECT data, contesto, pasto, sostanze, stato_iniziale, racconto, stato_finale, interpretazione, cabala FROM sogni WHERE nome_utente = ? ORDER BY id DESC', (real_name,))
    rows = cursor.fetchall()
    conn.close()

    archivio = []
    for r in rows:
        archivio.append({
            'data': r[0], 'contesto': r[1], 'pasto': r[2], 'sostanze': r[3],
            'statoIniziale': r[4], 'racconto': r[5], 'statoFinale': r[6], 'interpretazione': r[7], 'cabala': r[8] or ''
        })

    profilo = {
        'nome': user[0], 'sesso': user[2], 'eta': user[3], 'condizione': user[4],
        'titolo_studio': user[5], 'tipo_lavoro': user[6], 'hobby': user[7], 'altezza': user[8],
        'peso': user[9], 'traumi': user[10], 'medicinali': user[11]
    }

    return jsonify({"success": True, "profilo": profilo, "archivio": archivio}), 200

# 6. Rotta API per l'Aggiornamento del Profilo
@app.route('/api/aggiorna-profilo', methods=['POST'])
def aggiorna_profilo():
    data = request.json
    nome = data.get('nome')
    
    if not nome:
        return jsonify({"success": False, "error": "Nome utente obbligatorio."}), 400

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE utenti SET 
                sesso = ?, eta = ?, condizione = ?, titolo_studio = ?, 
                tipo_lavoro = ?, hobby = ?, altezza = ?, peso = ?, 
                traumi = ?, medicinali = ?
            WHERE nome = ?
        ''', (
            data.get('sesso'), data.get('eta'), data.get('condizione'), data.get('titolo_studio'),
            data.get('tipo_lavoro'), data.get('hobby'), data.get('altezza'),
            data.get('peso'), data.get('traumi'), data.get('medicinali'), nome
        ))
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# 7. Rotta API per l'Interpretazione del Sogno e Cabala (Unica chiamata Gemini)
@app.route('/api/interpreta-sogno', methods=['POST'])
def interpreta_sogno():
    try:
        data = request.json
        profilo = data.get('profilo', {})
        nome_utente = profilo.get('nome')
        
        stato_iniziale = data.get('stato_iniziale', 'Non specificato')
        racconto_sogno = data.get('racconto_sogno', '')
        stato_finale = data.get('stato_finale', 'Non specificato')
        contesto_recente = data.get('contesto_recente', 'Nessuno specificato')
        pasto = data.get('pasto', 'Non specificato')
        sostanze = data.get('sostanze', 'Nessuna')
        
        if not racconto_sogno.strip():
            return jsonify({"error": "Il racconto del sogno è obbligatorio."}), 400
        
        if not client:
            return jsonify({"status": "error", "interpretazione": "Errore: Client Gemini non inizializzato.", "cabala": ""}), 200

        titolo_studio = profilo.get('titolo_studio', '').strip()
        istruzioni_linguaggio = "Usa un linguaggio estremamente semplice, chiaro e colloquiale." if not titolo_studio else f"Adatta il registro linguistico al titolo di studio: '{titolo_studio}'."

        estrazioni_50 = scarica_ultime_estrazioni()

        prompt_combinato = (
            f"Agisci come un esperto di analisi onirica, psicodinamica e di cabala napoletana.\n"
            f"Utente: {profilo.get('sesso')}, {profilo.get('eta')} anni, Condizione: {profilo.get('condizione')}, "
            f"Titolo di studio: {titolo_studio}, Lavoro: {profilo.get('tipo_lavoro')}, Hobby: {profilo.get('hobby')}.\n"
            f"{istruzioni_linguaggio}\n\n"
            f"Cena: {pasto}, Sostanze/Alcol: {sostanze}, Contesto: {contesto_recente}.\n"
            f"Stato iniziale: {stato_iniziale} ➔ Sogno: \"{racconto_sogno}\" ➔ Stato finale: {stato_finale}.\n"
            f"Storico ultime estrazioni lotto:\n{estrazioni_50}\n\n"
            f"Fornisci la risposta strutturata esattamente in questo modo:\n"
            f"---INTERPRETAZIONE---\n"
            f"[Scrivi qui un'interpretazione profonda e saggia del significato del sogno]\n\n"
            f"---CABALA---\n"
            f"[Estrai i simboli chiave, convertili nei numeri della Smorfia e suggerisci una previsione mirata]"
        )

        response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_combinato)
        testo_totale = response.text

        interpretazione = testo_totale
        cabala = "Numeri e cabala elaborati dal sogno."
        
        if "---CABALA---" in testo_totale:
            parti = testo_totale.split("---CABALA---")
            interpretazione = parti[0].replace("---INTERPRETAZIONE---", "").strip()
            cabala = parti[1].strip()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sogni (nome_utente, data, contesto, pasto, sostanze, stato_iniziale, racconto, stato_finale, interpretazione, cabala)
            VALUES (?, datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nome_utente, contesto_recente, pasto, sostanze, stato_iniziale, racconto_sogno, stato_finale, interpretazione, cabala))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "interpretazione": interpretazione, "cabala": cabala}), 200

    except Exception as e:
        return jsonify({"status": "error", "interpretazione": f"Errore interno: {str(e)}", "cabala": ""}), 200

# 8. Rotta API per i Consigli sul Sonno Personalizzati (Aggiornata e blindata)
@app.route('/api/consigli-personalizzati', methods=['POST'])
def consigli_personalizzati():
    try:
        data = request.json or {}
        profilo = data.get('profilo', {})
        if not profilo and 'nome' in data:
            profilo = data
        
        if not client:
            return jsonify({"status": "success", "success": True, "consigli": "Client Gemini non inizializzato."}), 200

        nome = profilo.get('nome', 'Utente')
        sesso = profilo.get('sesso', 'Non specificato')
        eta = profilo.get('eta', 'Non specificata')
        condizione = profilo.get('condizione', 'Non specificata')
        lavoro = profilo.get('tipo_lavoro', 'Non specificato')

        prompt = (
            f"Agisci come un medico del sonno e uno psicologo clinico esperto in igiene del sonno.\n"
            f"Genera 4 consigli personalizzati per il sonno basati su questo profilo:\n"
            f"- Nome: {nome}, Sesso: {sesso}, Età: {eta}\n"
            f"- Condizione: {condizione}, Lavoro: {lavoro}\n"
            f"Fornisci consigli pratici ed empatici formattati chiaramente."
        )

        response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
        testo_consigli = response.text if response and hasattr(response, 'text') else "Impossibile generare i consigli al momento."
        
        return jsonify({"status": "success", "success": True, "consigli": testo_consigli}), 200
    except Exception as e:
        print(f"Errore consigli personalizzati: {e}")
        return jsonify({"status": "success", "success": True, "consigli": "Impossibile generare i consigli personalizzati al momento."}), 200

# 9. Rotta API per l'Analisi Periodica del Diario
@app.route('/api/analisi-periodica', methods=['POST'])
def analisi_periodica():
    try:
        data = request.json
        profilo = data.get('profilo', {})
        sogni = data.get('sogni', [])
        
        if not sogni:
            return jsonify({"status": "success", "analisi": "Nessun sogno registrato."}), 200
        
        storico_testo = "".join([f"\n- Sogno: {s.get('racconto')[:100]}..." for s in sogni[-10:]])
        prompt = f"Analizza la tendenza dei sogni recenti di {profilo.get('nome')}:\n{storico_testo}\nFornisci una sintesi."
        
        response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
        return jsonify({"status": "success", "analisi": response.text}), 200
    except Exception as e:
        return jsonify({"status": "success", "analisi": f"Errore: {str(e)}"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
