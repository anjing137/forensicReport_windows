"""
系统配置路由（鉴定人信息等）
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.case import AppSettings

router = APIRouter(prefix="/api/settings", tags=["系统配置"])


class AppraiserInfo(BaseModel):
    """鉴定人信息"""
    name: Optional[str] = ""
    title: Optional[str] = ""      # 职称（如：副教授、主任法医师）
    unit: Optional[str] = ""       # 工作单位


class AppraiserResponse(BaseModel):
    name: str = ""
    title: str = ""
    unit: str = ""


@router.get("/appraiser", response_model=AppraiserResponse)
def get_appraiser(db: Session = Depends(get_db)):
    """获取鉴定人信息"""
    result = {}
    for key in ["appraiser_name", "appraiser_title", "appraiser_unit"]:
        row = db.query(AppSettings).filter(AppSettings.key == key).first()
        result[key] = row.value if row else ""
    
    return AppraiserResponse(
        name=result.get("appraiser_name", ""),
        title=result.get("appraiser_title", ""),
        unit=result.get("appraiser_unit", ""),
    )


@router.put("/appraiser", response_model=AppraiserResponse)
def update_appraiser(data: AppraiserInfo, db: Session = Depends(get_db)):
    """更新鉴定人信息"""
    mapping = {
        "appraiser_name": data.name,
        "appraiser_title": data.title,
        "appraiser_unit": data.unit,
    }
    for key, value in mapping.items():
        row = db.query(AppSettings).filter(AppSettings.key == key).first()
        if row:
            row.value = value or ""
        else:
            db.add(AppSettings(key=key, value=value or ""))
    
    db.commit()
    
    return AppraiserResponse(
        name=data.name or "",
        title=data.title or "",
        unit=data.unit or "",
    )
