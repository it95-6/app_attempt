import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import ReviewSchedule, LearningItem

def analyze_learning_pattern(db: Session, user_id: int):
    # 総学習項目数を取得
    total_items = db.query(LearningItem).filter(
        LearningItem.user_id == user_id
    ).count()

    # 復習完了率を計算
    all_schedules = db.query(ReviewSchedule).join(
        LearningItem
    ).filter(
        LearningItem.user_id == user_id,
        ReviewSchedule.is_deleted == False
    ).count()

    completed_schedules = db.query(ReviewSchedule).join(
        LearningItem
    ).filter(
        LearningItem.user_id == user_id,
        ReviewSchedule.completed.isnot(None),
        ReviewSchedule.is_deleted == False
    ).count()

    completion_rate = (completed_schedules / all_schedules * 100) if all_schedules > 0 else 0

    return {
        "total_items": total_items,
        "completion_rate": round(completion_rate, 1)
    }

def optimize_review_intervals(completion_rate: float, base_intervals: list):
    # 完了率に基づいて間隔を調整
    adjustment = 1.0
    if completion_rate < 50:
        adjustment = 0.8  # 間隔を短く
    elif completion_rate > 80:
        adjustment = 1.2  # 間隔を長く

    return [int(interval * adjustment) for interval in base_intervals] 