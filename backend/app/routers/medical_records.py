"""
住院记录管理路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.case import HospitalRecord, Case
from app.schemas.case import HospitalRecordCreate, HospitalRecordUpdate, HospitalRecordResponse

router = APIRouter(prefix="/api/hospital-records", tags=["住院记录"])


@router.get("/case/{case_id}", response_model=List[HospitalRecordResponse])
def list_hospital_records(case_id: int, db: Session = Depends(get_db)):
    """获取案件的所有住院记录"""
    records = db.query(HospitalRecord).filter(HospitalRecord.case_id == case_id).all()
    return records


@router.get("/{record_id}", response_model=HospitalRecordResponse)
def get_hospital_record(record_id: int, db: Session = Depends(get_db)):
    """获取单条住院记录"""
    record = db.query(HospitalRecord).filter(HospitalRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="住院记录不存在")
    return record


@router.post("", response_model=HospitalRecordResponse)
def create_hospital_record(data: HospitalRecordCreate, db: Session = Depends(get_db)):
    """创建住院记录"""
    case = db.query(Case).filter(Case.id == data.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    record = HospitalRecord(**data.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{record_id}", response_model=HospitalRecordResponse)
def update_hospital_record(record_id: int, data: HospitalRecordUpdate, db: Session = Depends(get_db)):
    """更新住院记录"""
    record = db.query(HospitalRecord).filter(HospitalRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="住院记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)

    db.commit()
    db.refresh(record)
    return record


@router.delete("/{record_id}")
def delete_hospital_record(record_id: int, db: Session = Depends(get_db)):
    """删除住院记录"""
    record = db.query(HospitalRecord).filter(HospitalRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="住院记录不存在")
    db.delete(record)
    db.commit()
    return {"message": "删除成功"}
