# modules/eth_manager.py

import os
import threading
import time
from datetime import datetime, timedelta
from web3 import Web3
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database import SessionLocal
from modules.account_manager import get_user_by_wallet
from modules.account_book import update_balance
from models import (
    Account,
    DepositWallet,
    EthStoreWallet,
    NonChunkWallet,
)

# Web3 세팅
ETH_PROVIDER = os.getenv("ETH_PROVIDER_URL")
BANK_PRIVATE_KEY = os.getenv("BANK_PRIVATE_KEY")
BANK_ADDRESS = Web3.to_checksum_address(os.getenv("BANK_ADDRESS"))
w3 = Web3(Web3.HTTPProvider(ETH_PROVIDER))

# 상수
CHUNK_WEI = Web3.to_wei(0.001, "ether")
DEPOSIT_TTL = timedelta(minutes=30)
CHECK_INTERVAL = 5 * 60  # 5분

def generate_deposit_wallet(db: Session, user_id: int) -> str:
    """
    입금용 지갑 생성 → DB에 기록 → 30분간 감시 스레드 시작
    """
    acct = w3.eth.account.create()
    now = datetime.utcnow()
    deposit = DepositWallet(
        user_id=user_id,
        address=acct.address,
        private_key=acct.key.hex(),
        created_at=now,
        expires_at=now + DEPOSIT_TTL,
        processed=False
    )
    db.add(deposit)
    db.commit()
    db.refresh(deposit)

    threading.Thread(
        target=_monitor_deposit, args=(deposit.id,), daemon=True
    ).start()

    return deposit.address

def _monitor_deposit(deposit_id: int):
    """
    단일 입금 지갑 감시:
    5분마다 최대 6회, 입금 확인되면 즉시 처리 후 종료
    """
    db = SessionLocal()
    try:
        deposit = db.query(DepositWallet).get(deposit_id)
        attempts = 0
        while datetime.utcnow() < deposit.expires_at and attempts < 6:
            balance = w3.eth.get_balance(deposit.address)
            if balance > 0:
                # 1) 사용자 계좌에 입금액 반영
                deposit.processed = True
                db.commit()
                eth_amount = float(w3.fromWei(balance, "ether"))
                update_balance(db, deposit.user_id, eth_amount)

                # 2) 잔액 분해 & 저장
                _split_and_store(db, deposit.address, deposit.private_key, balance)
                break

            time.sleep(CHECK_INTERVAL)
            attempts += 1
            deposit = db.query(DepositWallet).get(deposit_id)
    finally:
        db.close()

def _split_and_store(db: Session, src_addr: str, src_priv: str, total_wei: int):
    """
    src_addr 지갑의 잔액을
      • 0.001 ETH 단위로 EthStoreWallet에 저장
      • 나머지(<0.001 ETH)는 NonChunkWallet에 저장
    """
    # 몇 개의 CHUNK_WEI 가 있는지
    num_chunks = total_wei // CHUNK_WEI
    leftover = total_wei - num_chunks * CHUNK_WEI
    nonce = w3.eth.getTransactionCount(src_addr)

    # 0.001 ETH 단위 이체 & EthStoreWallet 기록
    for i in range(num_chunks):
        new_acct = w3.eth.account.create()
        tx = {
            "nonce": nonce + i,
            "to": new_acct.address,
            "value": CHUNK_WEI,
            "gas": 21000,
            "gasPrice": w3.eth.gasPrice,
        }
        signed = w3.eth.account.sign_transaction(tx, private_key=src_priv)
        w3.eth.sendRawTransaction(signed.rawTransaction)

        db.add(EthStoreWallet(
            address=new_acct.address,
            private_key=new_acct.key.hex(),
            used=False
        ))

    # 나머지 잔액이 있으면 NonChunkWallet에 기록
    if leftover > 0:
        db.add(NonChunkWallet(
            address=src_addr,
            private_key=src_priv,
            balance_wei=leftover
        ))

    db.commit()

def send_eth_to_user(db: Session, wallet_address: str, amount: float) -> str:
    """
    출금 요청:
     - 0.001 ETH 단위로만 가능
     - EthStoreWallet(0.001 ETH 지갑)에서 오래된 순으로 사용
    """
    user = get_user_by_wallet(db, wallet_address)
    if not user:
        raise ValueError("User not found")

    # 계좌 잔액 확인
    acct = db.query(Account).filter(Account.user_id == user.id).first()
    if amount > acct.balance:
        raise ValueError("잔액 부족")

    # 단위 체크
    wei_amt = Web3.to_wei(amount, "ether")
    if wei_amt % CHUNK_WEI != 0:
        raise ValueError("0.001 ETH 단위로만 전송 가능합니다")

    needed = wei_amt // CHUNK_WEI

    # 오래된 순으로 사용 가능한 지갑 가져오기
    wallets = (
        db.query(EthStoreWallet)
          .filter(EthStoreWallet.used == False)
          .order_by(EthStoreWallet.created_at.asc())
          .limit(needed)
          .all()
    )
    if len(wallets) < needed:
        raise ValueError("출금용 지갑이 부족합니다")

    # N개의 지갑에서 각각 0.001 ETH 전송
    for w in wallets:
        nonce = w3.eth.getTransactionCount(w.address)
        tx = {
            "nonce": nonce,
            "to": Web3.to_checksum_address(wallet_address),
            "value": CHUNK_WEI,
            "gas": 21000,
            "gasPrice": w3.eth.gasPrice,
        }
        signed = w3.eth.account.sign_transaction(tx, private_key=w.private_key)
        w3.eth.sendRawTransaction(signed.rawTransaction)

        w.used = True
        db.commit()

    # 계좌 잔액 차감
    update_balance(db, user.id, -amount)
    return "success"
