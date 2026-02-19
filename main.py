from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pymongo import MongoClient
from bson import ObjectId
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from pydantic import BaseModel, EmailStr
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

client = MongoClient("mongodb://localhost:27017")
db = client["Azienda"]

utenti_collection = db["Utente"]
categorie_collection = db["CategoriaPermesso"]
richieste_collection = db["RichiestaPermesso"]

def get_current_user(x_user_email: str = Header(None)):
    if not x_user_email:
        raise HTTPException(status_code=401, detail="Email mancante negli header")
    user = utenti_collection.find_one({"email": x_user_email})
    if not user:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    return user


class UserRegister(BaseModel):
    nome: str
    cognome: str
    email: EmailStr 
    password: str
    ruolo: str

@app.post("/utenti/register")
def register(user: UserRegister):
    
    if utenti_collection.find_one({"email": user.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Email già registrata"
        )

    
    new_user = {
        "nome": user.nome,
        "cognome": user.cognome,
        "email": user.email,
        "password": user.password,  
        "ruolo": user.ruolo         
    }

    utenti_collection.insert_one(new_user)
    
    return {"message": "Utente registrato con successo"}


@app.post("/utenti/login")
def login(user: dict):
    db_user = utenti_collection.find_one({"email": user["email"]})
    if not db_user or user["password"] != db_user["password"]:  
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    return {"message": "Login effettuato con successo", "utente": {
        "nome": db_user["nome"],
        "cognome": db_user["cognome"],
        "email": db_user["email"],
        "ruolo": db_user["ruolo"]
    }}




@app.delete("/richieste/{id}")
def elimina_richiesta(id: str, current_user: dict = Depends(get_current_user)):
    richiesta = richieste_collection.find_one({"_id": ObjectId(id)})
    if not richiesta:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    if richiesta["utenteID"] != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Non autorizzato")
    if richiesta["stato"] != "In attesa":
        raise HTTPException(status_code=400, detail="Impossibile eliminare richieste già valutate")
    
    richieste_collection.delete_one({"_id": ObjectId(id)})
    return {"message": "Richiesta eliminata"}

@app.put("/richieste/{id}")
def modifica_richiesta(id: str, data: dict, current_user: dict = Depends(get_current_user)):
    richiesta = richieste_collection.find_one({"_id": ObjectId(id)})
    if not richiesta:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    if richiesta["stato"] != "In attesa":
        raise HTTPException(status_code=400, detail="Impossibile modificare richieste già valutate")
    
    richieste_collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "dataInizio": data["dataInizio"],
            "dataFine": data["dataFine"],
            "motivazione": data["motivazione"],
            "categoriaID": data["categoriaID"]
        }}
    )
    return {"message": "Richiesta aggiornata"}




@app.get("/categorie")
def get_categorie():
    categorie = list(categorie_collection.find({}, {"_id": 0}))
    return categorie


@app.get("/richieste")
def get_richieste(current_user: dict = Depends(get_current_user)):
    if current_user["ruolo"] == "Responsabile":
        richieste = list(richieste_collection.find())
    else:
        richieste = list(richieste_collection.find({"utenteID": str(current_user["_id"])}))

    for r in richieste:
        r["_id"] = str(r["_id"])
        
        utente_info = utenti_collection.find_one({"_id": int(r["utenteID"]) if r["utenteID"].isdigit() else r["utenteID"]})
        if utente_info:
            r["nomeUtente"] = f"{utente_info['nome']} {utente_info['cognome']}"
        else:
            r["nomeUtente"] = "Utente Sconosciuto"
            
    return richieste


@app.get("/richieste/{id}")
def get_richiesta(id: str, current_user: dict = Depends(get_current_user)):
    richiesta = richieste_collection.find_one({"_id": ObjectId(id)})
    if not richiesta:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")

    if current_user["ruolo"] != "Responsabile" and richiesta["utenteID"] != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Non autorizzato")

    richiesta["_id"] = str(richiesta["_id"])
    return richiesta


@app.post("/richieste")
def crea_richiesta(data: dict, current_user: dict = Depends(get_current_user)):
    if current_user["ruolo"] != "Dipendente":
        raise HTTPException(status_code=403, detail="Solo dipendenti")

    nuova = {
        "dataRichiesta": datetime.utcnow(),
        "dataInizio": data["dataInizio"],
        "dataFine": data["dataFine"],
        "categoriaID": data["categoriaID"],
        "motivazione": data["motivazione"],
        "stato": "In attesa",
        "utenteID": str(current_user["_id"]),
        "dataValutazione": None,
        "utenteValutazioneID": None
    }

    richieste_collection.insert_one(nuova)
    return {"message": "Richiesta creata"}


@app.put("/richieste/{id}/approva")
def approva_richiesta(id: str, current_user: dict = Depends(get_current_user)):
    if current_user["ruolo"] != "Responsabile":
        raise HTTPException(status_code=403, detail="Solo responsabili")

    richieste_collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "stato": "Approvato",
            "dataValutazione": datetime.utcnow(),
            "utenteValutazioneID": str(current_user["_id"])
        }}
    )
    return {"message": "Richiesta approvata"}


@app.put("/richieste/{id}/rifiuta")
def rifiuta_richiesta(id: str, current_user: dict = Depends(get_current_user)):
    if current_user["ruolo"] != "Responsabile":
        raise HTTPException(status_code=403, detail="Solo responsabili")

    richieste_collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "stato": "Rifiutato",
            "dataValutazione": datetime.utcnow(),
            "utenteValutazioneID": str(current_user["_id"])
        }}
    )
    return {"message": "Richiesta rifiutata"}



@app.put("/richieste/{id}/rifiuta")
def rifiuta_richiesta(id: str, current_user: dict = Depends(get_current_user)):
    if current_user["ruolo"] != "Responsabile":
        raise HTTPException(status_code=403, detail="Solo responsabili")

    richieste_collection.update_one(
        {"_id": int(id)},
        {"$set": {
            "stato": "Rifiutato",
            "dataValutazione": datetime.utcnow(),
            "utenteValutazioneID": str(current_user["_id"])
        }}
    )
    return {"message": "Richiesta rifiutata"}