import bcrypt
from sqlalchemy.orm import Session
from models import User
from modules.account_book import create_account

# 변경:
def signup(db: Session, username: str, password: str):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise ValueError("User already exists")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = User(
        username=username,
        password_hash=hashed.decode("utf-8"),
        wallet_address=None,  # 또는 "", 또는 생략
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    create_account(db, user.id)
    return user

def login(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return user
    return None

def get_user_by_wallet(db: Session, wallet_address: str):
    return db.query(User).filter(User.wallet_address == wallet_address).first()
