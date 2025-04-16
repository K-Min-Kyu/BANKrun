import uuid
from sqlalchemy.orm import Session
from models import Account, Transaction

def create_account(db: Session, user_id: int):
    account_number = str(uuid.uuid4())
    account = Account(user_id=user_id, account_number=account_number, balance=0.0)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account

def get_account(db: Session, user_id: int):
    return db.query(Account).filter(Account.user_id == user_id).first()

def update_balance(db: Session, user_id: int, amount: float, tx_hash: str = None, status: str = "completed"):
    account = get_account(db, user_id)
    if not account:
        raise ValueError("Account not found")
    if account.balance + amount < 0:
        raise ValueError("Insufficient funds")
    account.balance += amount
    tx_type = "deposit" if amount > 0 else "withdrawal"
    transaction = Transaction(
        account_id=account.id,
        type=tx_type,
        amount=amount,
        counterparty=None,
        tx_hash=tx_hash,
        status=status,
    )
    db.add(transaction)
    db.commit()
    db.refresh(account)
    return account
