"""
被鉴定人管理路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.case import Case, Person
from app.schemas.case import PersonCreate, PersonUpdate, PersonResponse

router = APIRouter(prefix="/api/persons", tags=["被鉴定人"])


@router.get("/case/{case_id}", response_model=PersonResponse)
def get_person_by_case(case_id: int, db: Session = Depends(get_db)):
    """获取案件的被鉴定人"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if not case.person:
        raise HTTPException(status_code=404, detail="该案件暂无被鉴定人信息")

    return case.person


@router.post("", response_model=PersonResponse)
def create_person(data: PersonCreate, db: Session = Depends(get_db)):
    """创建被鉴定人"""
    case = db.query(Case).filter(Case.id == data.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if case.person:
        raise HTTPException(status_code=400, detail="该案件已有被鉴定人，请使用更新接口")

    person = Person(
        case_id=data.case_id,
        name=data.name,
        gender=data.gender,
        birth_date=data.birth_date,
        id_number=data.id_number,
        address=data.address,
    )
    db.add(person)

    # 同步 person_name 到 Case
    if data.name:
        case.person_name = data.name

    db.commit()
    db.refresh(person)
    return person


@router.put("/case/{case_id}", response_model=PersonResponse)
def update_person_by_case(case_id: int, data: PersonUpdate, db: Session = Depends(get_db)):
    """更新案件的被鉴定人（不存在则创建）"""
    import json as _json
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if not case.person:
        # 不存在则创建
        person = Person(
            case_id=case_id,
            name=data.name,
            gender=data.gender,
            birth_date=data.birth_date,
            id_number=data.id_number,
            address=data.address,
        )
        db.add(person)
    else:
        # 更新
        update_data = data.model_dump(exclude_unset=True)

        # 标记用户确认的字段
        person_editable_fields = {"name", "gender", "birth_date", "id_number", "address"}
        confirmed = set()
        try:
            confirmed = set(_json.loads(case.person.confirmed_fields or "[]"))
        except (ValueError, TypeError):
            pass
        for key, value in update_data.items():
            if key in person_editable_fields and value:  # 只有非空值才标记为已确认
                confirmed.add(key)
        case.person.confirmed_fields = _json.dumps(list(confirmed), ensure_ascii=False)

        for key, value in update_data.items():
            setattr(case.person, key, value)

    # 同步 person_name
    if data.name:
        case.person_name = data.name

    db.commit()
    db.refresh(case.person)
    return case.person
