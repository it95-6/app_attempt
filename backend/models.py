from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    learning_items = relationship("LearningItem", back_populates="user")

class LearningItem(Base):
    __tablename__ = "learning_items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(String)
    learning_date = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="learning_items")
    review_schedules = relationship("ReviewSchedule", back_populates="learning_item")

class ReviewSchedule(Base):
    __tablename__ = "review_schedules"

    id = Column(Integer, primary_key=True, index=True)
    learning_item_id = Column(Integer, ForeignKey("learning_items.id"))
    review_number = Column(Integer)
    review_date = Column(DateTime)
    completed = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    learning_item = relationship("LearningItem", back_populates="review_schedules") 