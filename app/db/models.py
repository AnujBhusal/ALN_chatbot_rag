from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Document(Base):
    """Stores metadata for uploaded documents."""

    __tablename__ = "documents"

    id: int = Column(Integer, primary_key=True, index=True, autoincrement=True)
    filename: str = Column(String, nullable=False)
    filetype: str = Column(String, nullable=False)
    title: str = Column(String, nullable=False)
    document_type: str = Column(String, nullable=False, index=True, default="general")
    year: int = Column(Integer, nullable=True, index=True)
    program_name: str = Column(String, nullable=True)
    donor_name: str = Column(String, nullable=True)
    uploaded_at: datetime = Column(DateTime, default=datetime.utcnow)

    # Relationship with chunks
    chunks = relationship("DocumentChunk", back_populates="document")


class DocumentChunk(Base):
    """Stores individual chunks of a document."""

    __tablename__ = "document_chunks"

    id: int = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id: int = Column(Integer, ForeignKey("documents.id"))
    chunk_text: str = Column(Text, nullable=False)

    document = relationship("Document", back_populates="chunks")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    datetime = Column(DateTime, nullable=False)


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    answer = Column(Text, nullable=False)
    rating = Column(String, nullable=False)  # up | down
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("UserChatMessage", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")


class UserChatMessage(Base):
    __tablename__ = "user_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="chat_messages")