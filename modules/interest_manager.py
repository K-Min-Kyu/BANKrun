# modules/interest_manager.py

import threading
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import Account, Transaction
from modules.account_book import update_balance

def calculate_interest_for_account(db: Session, account: Account) -> float:
    """
    - 지난 7일 이내에 발생한 모든 거래(Transaction)를 조회
    - 각 거래 시점까지의 누적 잔액을 계산
    - 현재 잔액도 포함해 최소 잔액(min_balance)을 구함
    - 이자 = min_balance * 0.002 (0.2%)
    """
    # 1) 현재 잔액
    current_balance = account.balance

    # 2) 7일 전 시점
    cutoff = datetime.now() - timedelta(days=7)

    # 3) 지난 7일간의 거래만 가져오기
    recent_txs = (
        db.query(Transaction)
          .filter(Transaction.account_id == account.id,
                  Transaction.timestamp >= cutoff)
          .order_by(Transaction.timestamp)
          .all()
    )

    # 4) 거래 발생 시점의 잔액들 계산
    balances = []
    for tx in recent_txs:
        bal = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
              .filter(Transaction.account_id == account.id,
                      Transaction.timestamp <= tx.timestamp)
              .scalar()
        )
        balances.append(bal)

    # 5) 현재 잔액도 포함
    balances.append(current_balance)

    # 6) 최소값으로 이자 계산
    min_balance = min(balances) if balances else 0.0
    interest = min_balance * 0.002
    return interest

def run_weekly_interest(db: Session) -> None:
    """
    모든 계좌에 대해 calculate_interest_for_account() 호출,
    계산된 이자를 update_balance()로 반영
    """
    accounts = db.query(Account).all()
    for acc in accounts:
        interest = calculate_interest_for_account(db, acc)
        if interest > 0:
            # 계좌의 user_id를 기준으로 잔액 추가
            update_balance(db, acc.user_id, interest)

def schedule_weekly_interest(db: Session) -> None:
    """
    백그라운드 쓰레드로 매주 일요일 00시에 run_weekly_interest()를 호출
    """
    def worker():
        while True:
            now = datetime.now()
            # 이번 주 일요일 00:00
            days_ahead = 6 - now.weekday()
            if days_ahead < 0:
                days_ahead += 7
            next_sunday = (now + timedelta(days=days_ahead)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # 이미 지났으면 다음 주 일요일로
            if next_sunday <= now:
                next_sunday += timedelta(days=7)
            # 대기
            wait_seconds = (next_sunday - now).total_seconds()
            time.sleep(wait_seconds)
            # 이자 계산 실행
            run_weekly_interest(db)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
