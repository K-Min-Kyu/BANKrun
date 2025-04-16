from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
import datetime

from sqlalchemy import Boolean

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    wallet_address = Column(String, unique=True, index=True)
    account = relationship("Account", back_populates="user", uselist=False)

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    account_number = Column(String, unique=True, index=True)
    balance = Column(Float, default=0.0)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="account")
    transactions = relationship("Transaction", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    type = Column(String)
    amount = Column(Float)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    counterparty = Column(String, nullable=True)
    tx_hash = Column(String, nullable=True)
    status = Column(String)
    account = relationship("Account", back_populates="transactions")

class EthStoreWallet(Base):
    __tablename__ = "eth_store_wallets"
    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, unique=True, index=True)
    private_key = Column(String)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class NonChunkWallet(Base):
    __tablename__ = "non_chunk_wallets"
    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, unique=True, index=True)
    private_key = Column(String)
    balance_wei = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DepositWallet(Base):
    __tablename__ = "deposit_wallets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    address = Column(String, unique=True)
    private_key = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime)
    processed = Column(Boolean, default=False)
