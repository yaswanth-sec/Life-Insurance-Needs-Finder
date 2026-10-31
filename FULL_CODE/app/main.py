
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import sqlite3, csv, json, hashlib, hmac, secrets, os, math
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = ROOT / "cybernex.db"
app = FastAPI(title="CyberNex Needs Finder API", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT/"static"), name="static")

def conn():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def rows_csv(filename):
    p = DATA / filename
    if not p.exists(): return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE, salt TEXT NOT NULL, password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS customer_profiles(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
          age INTEGER, annual_income REAL, monthly_expenses REAL, dependents INTEGER,
          existing_cover REAL DEFAULT 0, loans REAL DEFAULT 0, savings REAL DEFAULT 0,
          city TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bookings(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
          advisor_id TEXT NOT NULL, slot_id TEXT NOT NULL UNIQUE, customer_name TEXT NOT NULL,
          customer_email TEXT NOT NULL, mode TEXT NOT NULL, notes TEXT DEFAULT '',
          status TEXT NOT NULL DEFAULT 'confirmed', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS advisor_slots(
          slot_id TEXT PRIMARY KEY, advisor_id TEXT NOT NULL, slot_start TEXT NOT NULL,
          slot_end TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(product_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS premium_rates(id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT,
          payment_option TEXT, premium_paying_term INTEGER, entry_age INTEGER, policy_term INTEGER,
          gender TEXT, smoker_status TEXT, rate REAL);
        CREATE TABLE IF NOT EXISTS advisors(advisor_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS riders(rider_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ulip_funds(fund_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS goals(goal_id TEXT PRIMARY KEY, profile_id TEXT, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS demo_profiles(profile_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mortality_charges(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL);
        """)
        count = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            for r in rows_csv("products.csv"):
                c.execute("INSERT OR REPLACE INTO products VALUES (?,?)",(r["product_id"],json.dumps(r)))
            for r in rows_csv("premium_rates.csv"):
                c.execute("""INSERT INTO premium_rates(product_id,payment_option,premium_paying_term,entry_age,policy_term,gender,smoker_status,rate)
                VALUES(?,?,?,?,?,?,?,?)""",(r["product_id"],r["premium_payment_option"],int(float(r["premium_paying_term_years"])),int(float(r["entry_age"])),int(float(r["policy_term_years"])),r["gender"],r["smoker_status"],float(r["rate_per_1000_sa_inr"])))
            for r in rows_csv("advisors.csv"):
                c.execute("INSERT OR REPLACE INTO advisors VALUES (?,?)",(r["advisor_id"],json.dumps(r)))
            for r in rows_csv("riders.csv"):
                c.execute("INSERT OR REPLACE INTO riders VALUES (?,?)",(r["rider_id"],json.dumps(r)))
            for r in rows_csv("ulip_funds.csv"):
                c.execute("INSERT OR REPLACE INTO ulip_funds VALUES (?,?)",(r["fund_id"],json.dumps(r)))
            for r in rows_csv("customer_profiles.csv"):
                c.execute("INSERT OR REPLACE INTO demo_profiles VALUES (?,?)",(r["profile_id"],json.dumps(r)))
            for r in rows_csv("customer_goals.csv"):
                c.execute("INSERT OR REPLACE INTO goals VALUES (?,?,?)",(r["goal_id"],r["profile_id"],json.dumps(r)))
            for r in rows_csv("advisor_slots.csv"):
                c.execute("INSERT OR REPLACE INTO advisor_slots VALUES (?,?,?,?,?)",(r["slot_id"],r["advisor_id"],r["slot_start"],r["slot_end"],r["status"]))
            for r in rows_csv("ulip_mortality_charges.csv"):
                c.execute("INSERT INTO mortality_charges(data) VALUES (?)",(json.dumps(r),))
        c.commit()

@app.on_event("startup")
def startup(): init_db()

def auth_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401,"Please sign in to continue.")
    token=authorization.split(" ",1)[1]
    with conn() as c:
        row=c.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                         WHERE s.token=? AND s.expires_at>?""",(token,datetime.utcnow().isoformat())).fetchone()
    if not row: raise HTTPException(401,"Session expired. Please sign in again.")
    return dict(row)

class Register(BaseModel):
    name: str = Field(min_length=2,max_length=80)
    email: str
    password: str = Field(min_length=8,max_length=128)
class Login(BaseModel):
    email: str
    password: str
class Profile(BaseModel):
    age: int = Field(ge=18,le=75)
    annual_income: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    dependents: int = Field(ge=0,le=20)
    existing_cover: float = Field(ge=0)
    loans: float = Field(ge=0)
    savings: float = Field(ge=0)
    city: str = Field(default="",max_length=80)
class NeedsInput(Profile):
    years_to_support: int = Field(default=15,ge=1,le=40)
    income_replacement_multiple: float = Field(default=10,ge=1,le=25)
class BookingInput(BaseModel):
    slot_id: str
    mode: str = Field(pattern="^(video|chat|phone)$")
    notes: str = Field(default="",max_length=500)

def safe_profile(row):
    if not row: return None
    return {k:row[k] for k in ["age","annual_income","monthly_expenses","dependents","existing_cover","loans","savings","city"]}

@app.get("/")
def home(): return FileResponse(ROOT/"static"/"index.html")

@app.get("/api/health")
def health():
    with conn() as c:
        return {"status":"ok","database":"connected","products":c.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                "premium_rate_rows":c.execute("SELECT COUNT(*) FROM premium_rates").fetchone()[0],
                "advisors":c.execute("SELECT COUNT(*) FROM advisors").fetchone()[0]}

@app.post("/api/register")
def register(body:Register):
    email=body.email.strip().lower()
    if "@" not in email: raise HTTPException(400,"Enter a valid email address.")
    salt=secrets.token_hex(16)
    ph=hashlib.pbkdf2_hmac("sha256",body.password.encode(),bytes.fromhex(salt),180000).hex()
    token=secrets.token_urlsafe(32); now=datetime.utcnow()
    try:
        with conn() as c:
            cur=c.execute("INSERT INTO users(name,email,salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                          (body.name.strip(),email,salt,ph,now.isoformat()))
            uid=cur.lastrowid
            c.execute("INSERT INTO sessions VALUES(?,?,?)",(token,uid,(now+timedelta(days=7)).isoformat()))
            c.commit()
    except sqlite3.IntegrityError: raise HTTPException(409,"An account with this email already exists.")
    return {"token":token,"user":{"id":uid,"name":body.name.strip(),"email":email}}

@app.post("/api/login")
def login(body:Login):
    email=body.email.strip().lower()
    with conn() as c: u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not u: raise HTTPException(401,"Email or password is incorrect.")
    check=hashlib.pbkdf2_hmac("sha256",body.password.encode(),bytes.fromhex(u["salt"]),180000).hex()
    if not hmac.compare_digest(check,u["password_hash"]): raise HTTPException(401,"Email or password is incorrect.")
    token=secrets.token_urlsafe(32); now=datetime.utcnow()
    with conn() as c:
        c.execute("INSERT INTO sessions VALUES(?,?,?)",(token,u["id"],(now+timedelta(days=7)).isoformat())); c.commit()
    return {"token":token,"user":{"id":u["id"],"name":u["name"],"email":u["email"]}}

@app.post("/api/logout")
def logout(user=Depends(auth_user), authorization: str=Header(...)):
    token=authorization.split(" ",1)[1]
    with conn() as c: c.execute("DELETE FROM sessions WHERE token=?",(token,)); c.commit()
    return {"ok":True}

@app.get("/api/me")
def me(user=Depends(auth_user)):
    with conn() as c:
        p=c.execute("SELECT * FROM customer_profiles WHERE user_id=?",(user["id"],)).fetchone()
    return {"user":{"name":user["name"],"email":user["email"]},"profile":safe_profile(p)}

@app.get("/api/demo-profiles")
def demo_profiles(user=Depends(auth_user)):
    with conn() as c:
        rs=c.execute("SELECT profile_id,data FROM demo_profiles ORDER BY profile_id LIMIT 100").fetchall()
    return [{"profile_id":r["profile_id"],"full_name":json.loads(r["data"]).get("full_name"),
             "age":json.loads(r["data"]).get("age"),"city":json.loads(r["data"]).get("city")} for r in rs]

@app.get("/api/demo-profiles/{pid}")
def demo_profile(pid:str,user=Depends(auth_user)):
    with conn() as c:
        r=c.execute("SELECT data FROM demo_profiles WHERE profile_id=?",(pid,)).fetchone()
        goals=c.execute("SELECT data FROM goals WHERE profile_id=?",(pid,)).fetchall()
    if not r: raise HTTPException(404,"Demo profile not found.")
    p=json.loads(r["data"])
    return {"profile":p,"goals":[json.loads(g["data"]) for g in goals]}

@app.put("/api/profile")
def save_profile(body:Profile,user=Depends(auth_user)):
    with conn() as c:
        c.execute("""INSERT INTO customer_profiles(user_id,age,annual_income,monthly_expenses,dependents,existing_cover,loans,savings,city,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET age=excluded.age,annual_income=excluded.annual_income,
        monthly_expenses=excluded.monthly_expenses,dependents=excluded.dependents,existing_cover=excluded.existing_cover,
        loans=excluded.loans,savings=excluded.savings,city=excluded.city,updated_at=excluded.updated_at""",
        (user["id"],body.age,body.annual_income,body.monthly_expenses,body.dependents,body.existing_cover,body.loans,body.savings,body.city,datetime.utcnow().isoformat()))
        c.commit()
    return {"ok":True,"profile":body.model_dump()}

@app.post("/api/calculate")
def calculate(body:NeedsInput,user=Depends(auth_user)):
    income_cover=body.annual_income*body.income_replacement_multiple
    debt_cover=body.loans
    family_buffer=body.monthly_expenses*12*min(body.years_to_support,10)*0.25*min(body.dependents,5)
    total_need=income_cover+debt_cover+family_buffer
    available=body.existing_cover+body.savings
    gap=max(0,total_need-available)
    return {"income_replacement_need":round(income_cover),"debt_cover_need":round(debt_cover),
            "family_support_buffer":round(family_buffer),"total_estimated_need":round(total_need),
            "existing_cover_and_savings":round(available),"estimated_cover_gap":round(gap),
            "method_note":"Illustrative planning estimate: income multiple + outstanding loans + a simplified family-support buffer − existing cover and savings. Not a financial recommendation."}

@app.get("/api/products")
def products(user=Depends(auth_user), q:str=""):
    with conn() as c: rs=c.execute("SELECT data FROM products").fetchall()
    items=[json.loads(r["data"]) for r in rs]
    if q: items=[x for x in items if q.lower() in (x.get("product_name","")+" "+x.get("product_type","")+" "+x.get("plain_language_summary","")).lower()]
    return items

@app.get("/api/products/{pid}")
def product(pid:str,user=Depends(auth_user)):
    with conn() as c:
        r=c.execute("SELECT data FROM products WHERE product_id=?",(pid,)).fetchone()
        riders=c.execute("SELECT data FROM riders").fetchall()
        funds=c.execute("SELECT data FROM ulip_funds").fetchall()
    if not r: raise HTTPException(404,"Product not found.")
    p=json.loads(r["data"])
    p["riders"]=[json.loads(x["data"]) for x in riders if pid in (json.loads(x["data"]).get("available_on_product_ids") or "").split(";")]
    p["funds"]=[json.loads(x["data"]) for x in funds if pid in (json.loads(x["data"]).get("available_on_product_ids") or "").split(";")]
    return p

@app.post("/api/recommend")
def recommend(body:NeedsInput,user=Depends(auth_user)):
    gap=max(0,body.annual_income*10+body.loans+body.monthly_expenses*12*min(body.years_to_support,10)*.25*min(body.dependents,5)-body.existing_cover-body.savings)
    with conn() as c: rs=c.execute("SELECT data FROM products").fetchall()
    result=[]
    for r in rs:
        p=json.loads(r["data"])
        try: minage=int(float(p.get("min_entry_age") or 18)); maxage=int(float(p.get("max_entry_age") or 99))
        except: minage,maxage=18,99
        if not (minage<=body.age<=maxage): continue
        minsa=float(p.get("min_sum_assured_inr") or 0); maxsa=float(p.get("max_sum_assured_inr") or 10**15)
        cover=min(max(gap,minsa),maxsa) if gap else minsa
        score=70
        if "Term" in (p.get("product_type") or ""): score+=20
        if gap>maxsa: score-=15
        if body.annual_income < float(p.get("min_annual_income_inr") or 0): score-=20
        result.append({"product":p,"illustrative_cover_inr":round(cover),"match_score":max(20,min(99,score)),
                       "reason":"Age range checked; cover amount compared with estimated protection gap. Confirm all eligibility and underwriting rules with an authorized insurer."})
    result.sort(key=lambda x:(x["match_score"],x["product"].get("product_type")=="Term Life"),reverse=True)
    return {"estimated_gap_inr":round(gap),"recommendations":result[:8]}

@app.get("/api/advisors")
def advisors(user=Depends(auth_user)):
    with conn() as c: rs=c.execute("SELECT data FROM advisors").fetchall()
    return [json.loads(r["data"]) for r in rs]

@app.get("/api/slots")
def slots(user=Depends(auth_user), advisor_id:str=""):
    with conn() as c:
        if advisor_id:
            rs=c.execute("SELECT * FROM advisor_slots WHERE advisor_id=? AND status='available' ORDER BY slot_start LIMIT 100",(advisor_id,)).fetchall()
        else:
            rs=c.execute("SELECT * FROM advisor_slots WHERE status='available' ORDER BY slot_start LIMIT 100").fetchall()
    return [dict(r) for r in rs]

@app.post("/api/bookings")
def book(body:BookingInput,user=Depends(auth_user)):
    with conn() as c:
        slot=c.execute("SELECT * FROM advisor_slots WHERE slot_id=?",(body.slot_id,)).fetchone()
        if not slot or slot["status"]!="available": raise HTTPException(409,"This slot is no longer available. Please choose another.")
        c.execute("UPDATE advisor_slots SET status='booked' WHERE slot_id=? AND status='available'",(body.slot_id,))
        if c.total_changes==0: raise HTTPException(409,"This slot has already been booked.")
        c.execute("""INSERT INTO bookings(user_id,advisor_id,slot_id,customer_name,customer_email,mode,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?)""",(user["id"],slot["advisor_id"],body.slot_id,user["name"],user["email"],body.mode,body.notes,datetime.utcnow().isoformat()))
        bid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.commit()
    return {"booking_id":bid,"status":"confirmed","slot_id":body.slot_id,"message":"Demo booking saved in CyberNex database. No real advisor notification is sent."}

@app.get("/api/bookings")
def my_bookings(user=Depends(auth_user)):
    with conn() as c:
        rs=c.execute("""SELECT b.*,a.data AS advisor_data,s.slot_start,s.slot_end FROM bookings b
        JOIN advisors a ON a.advisor_id=b.advisor_id JOIN advisor_slots s ON s.slot_id=b.slot_id
        WHERE b.user_id=? ORDER BY b.created_at DESC""",(user["id"],)).fetchall()
    out=[]
    for r in rs:
        x=dict(r); x["advisor"]=json.loads(x.pop("advisor_data")); out.append(x)
    return out

@app.get("/api/dashboard")
def dashboard(user=Depends(auth_user)):
    with conn() as c:
        p=c.execute("SELECT * FROM customer_profiles WHERE user_id=?",(user["id"],)).fetchone()
        b=c.execute("SELECT COUNT(*) FROM bookings WHERE user_id=?",(user["id"],)).fetchone()[0]
        pc=c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        ac=c.execute("SELECT COUNT(*) FROM advisors").fetchone()[0]
    return {"profile":safe_profile(p),"bookings_count":b,"product_count":pc,"advisor_count":ac}
