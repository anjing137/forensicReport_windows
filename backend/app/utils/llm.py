"""
LLM 工具模块 - 使用硅基流动 Chat Completions API
基于 OpenAI 兼容接口，调用 Qwen3-8B 等模型进行字段提取
"""
import json
import logging
from typing import Dict, Any, Optional

import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    调用硅基流动 Chat Completions API

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户消息（通常是 OCR 文本 + 提取指令）
        model: 模型名称，默认使用 settings.LLM_MODEL
        temperature: 温度参数，默认使用 settings.LLM_TEMPERATURE
        max_tokens: 最大输出 token，默认使用 settings.LLM_MAX_TOKENS
        response_format: 响应格式，如 {"type": "json_object"} 要求输出 JSON

    Returns:
        {"success": True, "content": "模型回复文本", "usage": {...}}
        或 {"success": False, "error": "错误信息"}
    """
    api_key = settings.SILICONFLOW_API_KEY
    if not api_key:
        return {"success": False, "error": "未配置 SILICONFLOW_API_KEY"}

    url = f"{settings.SILICONFLOW_BASE_URL}/chat/completions"
    model = model or settings.LLM_MODEL
    temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
    max_tokens = max_tokens or settings.LLM_MAX_TOKENS

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.7,
    }

    # Qwen3 系列需要禁用思考模式（信息提取不需要 Chain-of-Thought）
    if "Qwen3" in model or "qwen3" in model:
        payload["enable_thinking"] = False

    # 如果要求 JSON 输出
    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(url, json=payload, headers=headers)

        if response.status_code == 401:
            return {"success": False, "error": "API Key 无效"}
        if response.status_code == 429:
            return {"success": False, "error": "请求频率超限，请稍后重试"}
        if response.status_code != 200:
            error_detail = response.text[:500]
            logger.error(f"LLM API 错误 {response.status_code}: {error_detail}")
            return {"success": False, "error": f"API 返回错误 {response.status_code}: {error_detail}"}

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        logger.info(
            f"LLM 调用成功 | model={model} | "
            f"tokens: prompt={usage.get('prompt_tokens', 0)}, "
            f"completion={usage.get('completion_tokens', 0)}"
        )

        return {
            "success": True,
            "content": content,
            "usage": usage,
            "model": model,
        }

    except httpx.TimeoutException:
        return {"success": False, "error": "LLM 请求超时（90秒）"}
    except Exception as e:
        logger.error(f"LLM 调用异常: {str(e)}")
        return {"success": False, "error": f"LLM 调用失败: {str(e)}"}


def extract_json_from_content(content: str) -> Optional[Dict]:
    """
    从 LLM 回复中提取 JSON 对象
    处理 markdown 代码块包裹、多余文本等情况
    """
    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试找第一个 { 到最后一个 } 之间的内容
    brace_start = content.find('{')
    brace_end = content.rfind('}')
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        try:
            return json.loads(content[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning(f"无法从 LLM 回复中提取 JSON: {content[:200]}")
    return None


# ==================== 字段提取 Prompt 模板 ====================

EXTRACT_SYSTEM_PROMPT = """你是一个司法鉴定意见书信息提取助手。你的任务是从 OCR 识别的医疗和法律文书中提取结构化字段。

核心规则：
1. 只提取文本中明确出现的信息，不要推测或编造
2. 找不到的字段填 null
3. 日期格式统一为 YYYY年MM月DD日
4. 医院名称要完整，不要缩写
5. 输出必须是严格的 JSON 格式
"""


# 委托书提取模板
ENTRUSTMENT_LETTER_PROMPT = """请从以下司法鉴定委托书 OCR 文本中提取信息，输出 JSON 格式：

{
  "entrusting_unit": "委托单位（委托方，通常是法院）",
  "entrustment_matter": "委托事项（必须原文照搬，一字不改，不要化简、概括或改写）",
  "accident_date": "事故发生日期",
  "accident_location": "事故发生地点",
  "accident_description": "事故经过简述",
  "person_name": "被鉴定人姓名",
  "person_gender": "被鉴定人性别",
  "litigant_info": "当事人信息（如对方姓名、车辆信息等）"
}

关于 entrusting_unit 的提取规则（非常重要，务必仔细区分）：
司法鉴定委托书中有两个容易混淆的字段：
- "委托单位" = 委托方，即委托鉴定的单位，通常是人民法院、公安局等
- "受理委托单位" = 受托方，即受理鉴定的机构，固定为"新乡医学院司法鉴定中心"

⚠️ entrusting_unit 必须提取"委托单位"（法院），绝对不能提取"受理委托单位"（鉴定中心）！

正确示例：
- "新乡县人民法院"、"卫辉市人民法院"、"新乡市公安局XX分局"
- 如果委托单位栏写的是"XX人民法院司法鉴定技术处"，提取为"XX人民法院"

错误示例（绝对不要提取这些）：
- "新乡医学院司法鉴定中心" → 这是受理委托单位，不是委托单位
- "委托单位（人民法院司法鉴定部门）" → 这是表格标签占位文字，不是实际的委托单位名称
- 空白或未填写 → 如果委托单位栏确实为空，则 entrusting_unit 输出 null

OCR 文本：
{{OCR_TEXT}}"""


# 身份证提取模板
ID_CARD_PROMPT = """请从以下身份证 OCR 文本中提取被鉴定人信息，输出 JSON 格式：

{
  "name": "姓名",
  "gender": "性别",
  "ethnicity": "民族",
  "birth_date": "出生日期（YYYY年MM月DD日）",
  "id_number": "身份证号码",
  "address": "住址"
}

OCR 文本：
{{OCR_TEXT}}"""


# 交通事故认定书提取模板
TRAFFIC_ACCIDENT_PROMPT = """请从以下道路交通事故认定书 OCR 文本中提取信息，输出 JSON 格式：

{
  "accident_date": "事故发生日期时间",
  "accident_location": "事故发生地点",
  "accident_description": "事故经过（必须原文照搬交通事故认定书中'道路交通事故发生经过'的内容，一字不改，不要化简、概括或改写）",
  "responsibility": "责任划分（如：XXX负主要责任，XXX负次要责任）",
  "person_name": "被鉴定人姓名",
  "vehicle_info": "车辆信息"
}

OCR 文本：
{{OCR_TEXT}}"""


# 住院病历按医院分组提取模板（多页合并，一次提取一条完整记录）
MEDICAL_GROUP_PROMPT = """请从以下一家医院的完整病历（多页合并）中，综合所有页面信息，提取一条完整的住院记录，输出 JSON 格式：

{
  "hospital_name": "医院名称（完整名称，不含#符号）",
  "admission_number": "住院号",
  "patient_name": "患者姓名",
  "gender": "性别",
  "age": "年龄",
  "chief_complaint": "主诉",
  "present_illness_history": "现病史",
  "past_history": "既往史（没有则填null）",
  "physical_examination": "体格检查",
  "admission_diagnosis": "入院诊断",
  "treatment_process": "治疗过程/手术记录（没有则填null）",
  "medication": "用药情况（没有则填null）",
  "discharge_diagnosis": "出院诊断",
  "discharge_orders": "出院医嘱",
  "admission_date": "入院日期",
  "discharge_date": "出院日期",
  "hospital_days": "住院天数（数字，没有则填null）"
}

重要规则：
1. 这是同一家医院的多页病历（住院病案首页、入院记录、出院记录等），请综合所有页面提取一条最完整的记录
2. 同一字段在不同页面都有描述时，取最完整的那个（如首页的入院诊断可能简略，出院记录中的更详细，取详细的）
3. 不要重复生成多条记录，只输出一个 JSON 对象
4. 医院名称要完整准确，不要缩写，不要带#符号
5. 找不到的字段填 null
6. 日期格式统一为 YYYY年MM月DD日

医院名称：{{HOSPITAL_NAME}}

OCR 文本（多页合并）：
{{OCR_TEXT}}"""


# 住院病历提取模板（单页旧版，保留兼容）
MEDICAL_RECORD_PROMPT = """请从以下医院病历 OCR 文本中提取住院记录信息，输出 JSON 格式：

{
  "hospital_name": "医院名称（完整名称，不含#符号）",
  "admission_number": "住院号",
  "patient_name": "患者姓名",
  "gender": "性别",
  "age": "年龄",
  "chief_complaint": "主诉",
  "present_illness_history": "现病史",
  "past_history": "既往史（没有则填null）",
  "physical_examination": "体格检查",
  "admission_diagnosis": "入院诊断",
  "treatment_process": "治疗过程/手术记录（没有则填null）",
  "medication": "用药情况（没有则填null）",
  "discharge_diagnosis": "出院诊断",
  "discharge_orders": "出院医嘱",
  "admission_date": "入院日期",
  "discharge_date": "出院日期",
  "hospital_days": "住院天数（数字，没有则填null）"
}

注意：
- 如果是住院病案首页，重点提取医院名称、住院号、患者基本信息和诊断
- 如果是入院记录，重点提取主诉、现病史、既往史、体格检查、入院诊断
- 如果是出院记录，重点提取出院诊断、出院医嘱、住院天数
- 同一住院号的多页内容应合并

OCR 文本：
{{OCR_TEXT}}"""


# 影像学报告提取模板
IMAGING_REPORT_PROMPT = """请从以下影像学检查报告 OCR 文本中提取信息，输出 JSON 格式：

{
  "report_date": "报告日期（YYYY年MM月DD日）",
  "hospital_name": "医院名称",
  "exam_type": "检查类型（如：CT、X线、MRI等）",
  "exam_part": "检查部位",
  "film_number": "片子编号/检查号",
  "film_count": "该检查产生的胶片张数（整数）",
  "patient_name": "患者姓名",
  "report_content": "影像学检查报告内容（描述+诊断意见）"
}

关于 exam_part（检查部位）的提取规则（必须提取，不可为空）：
- 从报告标题、检查名称、检查项目中提取部位，如"头颅""胸部""左锁骨""腰椎""膝关节"等
- 如果报告标题写"64排CT颅脑+胸部"，则 exam_part 提取为"颅脑、胸部"
- 如果写"左锁骨正位片"，则 exam_part 为"左锁骨"
- 如果写"MR膝关节平扫"，则 exam_part 为"膝关节"
- 即使没有明确标注"检查部位"字段，也要从检查名称中推断出部位
- exam_part 是必填字段，务必从文本中找出检查的解剖部位

关于 film_count 的提取规则：
- 这是法医在阅片时需要查看的胶片数量
- 如果报告中明确提到张数（如"CT片2张"），则直接提取数字
- 如果报告提到多个部位分别检查，每个部位通常产生1张胶片，合计张数（如"头颅CT+胸部CT"=2张）
- 如果只有1个检查部位且未提张数，默认为1张
- 如果无法判断，填1

关于 exam_type 的提取规则：
- 必须标准化为以下之一：CT、MRI、X线、DR、CR、PET-CT、超声
- 如果原文写"计算机断层扫描"，提取为"CT"
- 如果原文写"核磁共振"，提取为"MRI"
- 如果原文写"平片"或"透视"，提取为"X线"

OCR 文本：
{{OCR_TEXT}}"""


# 资料摘要生成模板
MATERIAL_SUMMARY_PROMPT = """请根据以下住院记录信息，撰写司法鉴定意见书的"资料摘要"部分。

要求：
1. 每个住院记录单独成段，以"据{医院名称}住院病案（住院号：{住院号}）记载："开头
2. 按时间顺序排列住院记录
3. 内容应包含：入院日期、出院日期、住院天数、主诉、现病史摘要、既往史（如有关键信息）、体格检查关键发现、入院诊断、治疗经过、出院诊断、出院医嘱
4. 语言精炼但完整，保留医学术语，不遗漏关键伤情和治疗信息
5. 如果某字段为空或缺失，跳过该部分，不要写"未提及"
6. 同一患者多次住院的，每次住院单独一段

重要：合并重复记录！
- 如果多条记录属于同一次住院（住院号相同、或住院号都为空但出院诊断完全相同），必须合并为一段
- 合并时，取最完整的字段信息（有的记录只有出院诊断，有的记录更完整，应取完整版的）
- 如果多条记录住院号都为空且出院诊断完全相同，视为同一份出院记录的重复提取，只保留一次
- 合并后，同一次住院的摘要只出现一次

7. 输出纯文本，不要JSON格式

住院记录数据：
{{RECORDS_TEXT}}"""


# 鉴定申请书提取模板
APPRAISAL_APPLICATION_PROMPT = """请从以下鉴定申请书 OCR 文本中提取信息，输出 JSON 格式：

{
  "applicant": "申请人",
  "entrusting_unit": "委托单位（即委托鉴定的法院/公安局等司法委托方，绝不是鉴定中心本身）",
  "appraisal_items": "申请鉴定的事项（必须原文照搬，一字不改，不要化简、概括或改写）",
  "person_name": "被鉴定人姓名",
  "case_brief": "案件简介"
}

关于 entrusting_unit 的提取规则：
- 委托单位 = 法院/公安局等委托方，绝对不是鉴定中心
- 常见正确值示例："新乡县人民法院"、"卫辉市人民法院"

OCR 文本：
{{OCR_TEXT}}"""


# 材料类型 → Prompt 模板映射
MATERIAL_TYPE_PROMPTS = {
    "entrustment_letter": ENTRUSTMENT_LETTER_PROMPT,
    "id_card": ID_CARD_PROMPT,
    "traffic_accident_cert": TRAFFIC_ACCIDENT_PROMPT,
    "medical_record": MEDICAL_RECORD_PROMPT,
    "imaging_report": IMAGING_REPORT_PROMPT,
    "appraisal_application": APPRAISAL_APPLICATION_PROMPT,
}


def extract_fields(material_type: str, ocr_text: str) -> Dict[str, Any]:
    """
    根据材料类型调用 LLM 提取结构化字段

    Args:
        material_type: 材料类型（对应 MaterialType 枚举值）
        ocr_text: OCR 识别的文本

    Returns:
        {"success": True, "fields": {...}, "raw_content": "...", "usage": {...}}
        或 {"success": False, "error": "错误信息"}
    """
    if not ocr_text or not ocr_text.strip():
        return {"success": False, "error": "OCR 文本为空，无法提取"}

    prompt_template = MATERIAL_TYPE_PROMPTS.get(material_type)
    if not prompt_template:
        return {"success": False, "error": f"不支持的材料类型: {material_type}"}

    # 使用 str.replace 而非 str.format，避免 JSON 中的花括号被误解析
    user_prompt = prompt_template.replace("{{OCR_TEXT}}", ocr_text)

    # 调用 LLM，要求 JSON 输出
    result = call_llm(
        system_prompt=EXTRACT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
    )

    if not result.get("success"):
        return result

    content = result["content"]
    fields = extract_json_from_content(content)

    if fields is None:
        return {
            "success": False,
            "error": "LLM 返回的内容无法解析为 JSON",
            "raw_content": content[:500],
        }

    return {
        "success": True,
        "fields": fields,
        "raw_content": content,
        "usage": result.get("usage", {}),
        "model": result.get("model", ""),
    }


def extract_case_summary(case_id: int, db) -> Dict[str, Any]:
    """
    综合所有 OCR 材料提取案件概要信息
    用于生成基本案情、资料摘要等报告部分

    Args:
        case_id: 案件ID
        db: 数据库会话

    Returns:
        {"success": True, "case_facts": "...", "material_summary": "..."}
    """
    from app.models.case import Case, Material, CaseStatus

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return {"success": False, "error": "案件不存在"}

    # 收集所有已完成 OCR 的材料
    materials = db.query(Material).filter(
        Material.case_id == case_id,
        Material.ocr_status == "completed",
        Material.ocr_text.isnot(None),
    ).all()

    if not materials:
        return {"success": False, "error": "没有已识别的材料"}

    # 按材料类型分组
    grouped_texts = {}
    for mat in materials:
        mtype = mat.material_type
        if mtype not in grouped_texts:
            grouped_texts[mtype] = []
        grouped_texts[mtype].append({
            "id": mat.id,
            "filename": mat.original_filename,
            "text": mat.ocr_text[:3000],  # 限制每份材料 3000 字符，避免 token 过多
        })

    # 拼接所有 OCR 文本
    all_text_parts = []
    for mtype, items in grouped_texts.items():
        type_label = {
            "entrustment_letter": "委托书",
            "id_card": "身份证",
            "traffic_accident_cert": "交通事故认定书",
            "appraisal_application": "鉴定申请书",
            "medical_record": "医院病历",
            "imaging_report": "影像学报告",
        }.get(mtype, mtype)

        for item in items:
            all_text_parts.append(f"【{type_label} - {item['filename']}】\n{item['text']}")

    all_text = "\n\n---\n\n".join(all_text_parts)

    # 如果文本太长，截断到 6000 字符（约 2000 tokens）
    if len(all_text) > 6000:
        all_text = all_text[:6000] + "\n\n[... 文本过长，已截断 ...]"

    # 生成基本案情
    case_facts_prompt = """请根据以下司法鉴定案件的 OCR 材料内容，撰写"基本案情"部分。

要求：
1. 语言规范、严谨，符合司法鉴定意见书格式
2. 包含事故时间、地点、经过
3. 包含就医经过（去了哪些医院）
4. 最后一句格式固定："现为处理案件需要，{委托单位}特委托我鉴定中心{委托事项}。"
5. 不要包含伤情细节（伤情在资料摘要中体现）
6. 输出纯文本，不要 JSON

OCR 材料：
""" + all_text

    case_facts_result = call_llm(
        system_prompt="你是一个司法鉴定意见书撰写助手。请根据提供的材料撰写规范的法律文书内容。",
        user_prompt=case_facts_prompt,
        temperature=0.3,
    )

    case_facts = case_facts_result.get("content", "") if case_facts_result.get("success") else ""

    return {
        "success": True,
        "case_facts": case_facts,
        "materials_count": len(materials),
        "model": case_facts_result.get("model", ""),
    }


def generate_material_summary(records_text: str) -> Dict[str, Any]:
    """
    使用 LLM 从住院记录文本生成资料摘要

    Args:
        records_text: 所有住院记录拼接的文本

    Returns:
        {"success": True, "material_summary": "..."} 或 {"success": False, "error": "..."}
    """
    if not records_text or not records_text.strip():
        return {"success": False, "error": "住院记录文本为空"}

    # 限制输入长度（Qwen3-8B 上下文约32K，输入留8K字符比较安全）
    if len(records_text) > 8000:
        records_text = records_text[:8000] + "\n\n[... 文本过长，已截断 ...]"

    user_prompt = MATERIAL_SUMMARY_PROMPT.replace("{{RECORDS_TEXT}}", records_text)

    result = call_llm(
        system_prompt="你是一个司法鉴定意见书撰写助手。请根据提供的住院记录撰写规范的资料摘要。",
        user_prompt=user_prompt,
        temperature=0.3,
    )

    if not result.get("success"):
        return {"success": False, "error": result.get("error", "LLM 调用失败")}

    return {
        "success": True,
        "material_summary": result["content"],
        "model": result.get("model", ""),
        "usage": result.get("usage", {}),
    }


def extract_medical_group_fields(hospital_name: str, combined_ocr_text: str) -> Dict[str, Any]:
    """
    按医院分组提取病历：同一医院多页OCR文本合并，一次LLM调用提取一条完整住院记录

    Args:
        hospital_name: 医院名称（来自 MaterialGroup.group_name）
        combined_ocr_text: 该医院所有页面的OCR文本拼接

    Returns:
        {"success": True, "fields": {...}, "usage": {...}}
        或 {"success": False, "error": "错误信息"}
    """
    if not combined_ocr_text or not combined_ocr_text.strip():
        return {"success": False, "error": "OCR 文本为空，无法提取"}

    # 限制输入长度
    if len(combined_ocr_text) > 12000:
        combined_ocr_text = combined_ocr_text[:12000] + "\n\n[... 文本过长，已截断 ...]"

    user_prompt = MEDICAL_GROUP_PROMPT.replace("{{HOSPITAL_NAME}}", hospital_name)
    user_prompt = user_prompt.replace("{{OCR_TEXT}}", combined_ocr_text)

    result = call_llm(
        system_prompt=EXTRACT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
    )

    if not result.get("success"):
        return result

    content = result["content"]
    fields = extract_json_from_content(content)

    if fields is None:
        return {
            "success": False,
            "error": "LLM 返回的内容无法解析为 JSON",
            "raw_content": content[:500],
        }

    # 确保医院名称使用分组名称（更可靠）
    if not fields.get("hospital_name") or fields.get("hospital_name") == "null":
        fields["hospital_name"] = hospital_name

    return {
        "success": True,
        "fields": fields,
        "raw_content": content,
        "usage": result.get("usage", {}),
        "model": result.get("model", ""),
    }
