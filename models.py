import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import jwt
from datetime import datetime, timedelta
from database import SessionLocal, init_db
from modules.account_manager import signup, login, get_user_by_wallet
from modules.account_book import get_account
from modules.eth_manager import send_eth_to_user
from models import User

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from modules.interest_manager import schedule_weekly_interest

from modules.eth_manager import generate_deposit_wallet

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중엔 * 허용, 배포 시엔 특정 도메인만
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.on_event("startup")
def on_startup():
    init_db()
    db = next(get_db())
    schedule_weekly_interest(db)   # ← 이자 스케줄러 시작

# 변경:
class SignupRequest(BaseModel):
    username: str
    password: str

@app.post("/signup")
def signup_route(req: SignupRequest, db: Session = Depends(get_db)):
    try:
        # 변경:
        user = signup(db, req.username, req.password)
        return {"msg": "회원가입 성공", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = login(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/balance")
def read_balance(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = get_account(db, current_user.id)
    return {"balance": account.balance}

@app.post("/deposit_wallet")
def deposit_wallet_route(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    addr = generate_deposit_wallet(db, current_user.id)
    return {"deposit_address": addr}

@app.post("/withdraw")
def withdraw(amount: float, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        tx_hash = send_eth_to_user(db, current_user.wallet_address, amount)
        return {"tx_hash": tx_hash}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# static 디렉토리에서 index.html 서빙
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_ui():
    return FileResponse("static/index.html")
