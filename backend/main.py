from fastapi import FastAPI, HTTPException, Depends, status, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import numpy as np
from pydantic import BaseModel
import logging
from passlib.context import CryptContext

# パスワードハッシュ化の設定
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from database import get_db, engine, Base
from models import User, LearningItem, ReviewSchedule
from analytics import analyze_learning_pattern, optimize_review_intervals

# データベーステーブルの作成
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Learning Reminder API")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # フロントエンドのオリジン
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# リクエストボディのバリデーション用モデル
class LearningItemCreate(BaseModel):
    title: str
    content: str
    learning_date: str
    user_id: int

class UserCreate(BaseModel):
    email: str
    password: str

# 基本の復習間隔（時間）
BASE_INTERVALS = [1, 24, 72, 168, 336, 720]

@app.post("/calculate-reviews")
async def calculate_reviews(learning_date: str, repetition_number: int = 0, db: Session = Depends(get_db)):
    try:
        date = datetime.fromisoformat(learning_date)
        # 基本の復習間隔（時間）: 1時間後、1日後、3日後、1週間後、2週間後、1ヶ月後
        base_intervals = [1, 24, 72, 168, 336, 720]
        
        # 学習回数に応じて間隔を調整（学習回数が増えるほど間隔を広げる）
        adjusted_intervals = [interval * (1 + 0.1 * repetition_number) for interval in base_intervals]
        
        # 復習日時のリストを生成
        review_dates = [
            date + timedelta(hours=interval)
            for interval in adjusted_intervals
        ]
        
        return {
            "review_schedule": [
                {
                    "review_number": i + 1,
                    "review_date": review_date.isoformat(),
                    "interval_hours": interval,
                    "completed": False,
                    "is_deleted": False
                }
                for i, (review_date, interval) in enumerate(zip(review_dates, adjusted_intervals))
            ]
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

@app.post("/learning-items/")
async def create_learning_item(
    item: LearningItemCreate,
    db: Session = Depends(get_db)
):
    try:
        logger.info(f"Received learning item: {item}")
        
        # 文字列の日時をdatetimeオブジェクトに変換
        learning_date = datetime.fromisoformat(item.learning_date)
        
        # ユーザーの学習パターンを分析
        analytics = analyze_learning_pattern(db, item.user_id)
        logger.info(f"Analytics result: {analytics}")
        
        # 復習間隔を最適化
        intervals = optimize_review_intervals(analytics["completion_rate"], BASE_INTERVALS)
        logger.info(f"Optimized intervals: {intervals}")
        
        # 学習アイテムの作成
        db_item = LearningItem(
            title=item.title,
            content=item.content,
            learning_date=learning_date,
            user_id=item.user_id
        )
        db.add(db_item)
        db.flush()
        logger.info(f"Created learning item with ID: {db_item.id}")
        
        # 復習スケジュールの作成
        review_dates = [
            learning_date + timedelta(hours=interval)
            for interval in intervals
        ]
        
        for i, review_date in enumerate(review_dates, 1):
            db_schedule = ReviewSchedule(
                learning_item_id=db_item.id,
                review_number=i,
                review_date=review_date
            )
            db.add(db_schedule)
        
        db.commit()
        logger.info("Successfully committed to database")
        
        return {
            "message": "学習アイテムを作成しました",
            "item_id": db_item.id,
            "title": db_item.title,
            "learning_date": db_item.learning_date.isoformat()
        }
    except ValueError as e:
        logger.error(f"Value error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid data format: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/learning-items/{user_id}")
async def get_learning_items(user_id: int, db: Session = Depends(get_db)):
    try:
        items = db.query(LearningItem).filter(LearningItem.user_id == user_id).all()
        # IDで一意に
        unique = {item.id: item for item in items}.values()
        return [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "learning_date": item.learning_date.isoformat(),
                "user_id": item.user_id
            }
            for item in unique
        ]
    except Exception as e:
        logger.error(f"Error fetching learning items: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/review-complete/{schedule_id}")
async def complete_review(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    schedule = db.query(ReviewSchedule).filter(ReviewSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="スケジュールが見つかりません")
    
    schedule.completed = datetime.utcnow()
    db.commit()
    
    return {
        "message": "復習を完了しました",
        "completed": True,
        "completed_at": schedule.completed.isoformat()
    }

@app.post("/review-delete/{schedule_id}")
async def delete_review(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    schedule = db.query(ReviewSchedule).filter(ReviewSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="スケジュールが見つかりません")
    
    schedule.is_deleted = True
    db.commit()
    
    return {
        "message": "復習をキャンセルしました",
        "is_deleted": True
    }

@app.get("/review-schedules/{learning_item_id}")
async def get_review_schedules(
    learning_item_id: int,
    db: Session = Depends(get_db)
):
    schedules = db.query(ReviewSchedule).filter(
        ReviewSchedule.learning_item_id == learning_item_id,
        ReviewSchedule.is_deleted == False
    ).all()
    
    return {
        "schedules": [
            {
                "id": schedule.id,
                "review_number": schedule.review_number,
                "review_date": schedule.review_date.isoformat(),
                "completed": schedule.completed is not None,
                "completed_at": schedule.completed.isoformat() if schedule.completed else None,
                "is_deleted": schedule.is_deleted
            }
            for schedule in schedules
        ]
    }

@app.get("/analytics/{user_id}")
async def get_analytics(user_id: int, db: Session = Depends(get_db)):
    return analyze_learning_pattern(db, user_id)

@app.post("/users/")
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    try:
        # 既存のユーザーをチェック
        existing_user = db.query(User).filter(User.email == user.email).first()
        if existing_user:
            return {"message": "ユーザーは既に存在します", "user_id": existing_user.id}

        # 新しいユーザーを作成
        hashed_password = pwd_context.hash(user.password)
        db_user = User(
            email=user.email,
            hashed_password=hashed_password
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        logger.info(f"Created new user with ID: {db_user.id}")
        return {"message": "ユーザーを作成しました", "user_id": db_user.id}
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/test")
async def create_test_user(db: Session = Depends(get_db)):
    try:
        # テストユーザーを作成
        test_email = "test@example.com"
        existing_user = db.query(User).filter(User.email == test_email).first()
        
        if existing_user:
            return {"message": "テストユーザーは既に存在します", "user_id": existing_user.id}
        
        test_user = User(
            email=test_email,
            hashed_password=pwd_context.hash("testpassword")
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        
        logger.info(f"Created test user with ID: {test_user.id}")
        return {"message": "テストユーザーを作成しました", "user_id": test_user.id}
    except Exception as e:
        logger.error(f"Error creating test user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Learning Reminder API"}

@app.delete("/learning-items/{item_id}")
async def delete_learning_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(LearningItem).filter(LearningItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="学習項目が見つかりません")
    # 関連する復習スケジュールも削除
    db.query(ReviewSchedule).filter(ReviewSchedule.learning_item_id == item_id).delete()
    db.delete(item)
    db.commit()
    return {"message": "学習項目を削除しました"} 