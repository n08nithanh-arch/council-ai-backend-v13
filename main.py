
"""
Council AI V14.8 Final - Real API Backend
Dual Flow: Auto Expand + Classic 5 Debate
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal
import os, uuid, asyncio, random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Council AI V14.8 Final Real API", version="14.8.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models ----------
class ApiRole(BaseModel):
    id: str
    name: str
    aspect: str
    model: str = "gpt-4o-mini"
    color: str = "#3B82F6"
    api_key: Optional[str] = None  # allow override from frontend

class Flow1Request(BaseModel):
    topic: str
    context: Optional[str] = ""
    desired_count: int = 7
    custom_roles: Optional[List[ApiRole]] = None
    provider: Literal["openai","anthropic","auto"] = "auto"

class Flow2Request(BaseModel):
    topic: str
    context: Optional[str] = ""
    rounds: int = 2
    provider: Literal["openai","anthropic","auto"] = "auto"
    custom_api_keys: Optional[dict] = None  # {member_id: api_key}

ROLE_POOL = [
    ("Chuyên gia Kỹ thuật", "Phân tích kiến trúc, scalability, stack, rủi ro kỹ thuật", "#3B82F6"),
    ("Chuyên gia Thị trường", "Phân tích PMF, đối thủ, xu hướng, positioning", "#8B5CF6"),
    ("Chuyên gia Tài chính", "Phân tích chi phí, ROI, burn rate, pricing", "#10B981"),
    ("Chuyên gia Người dùng", "Phân tích UX, Jobs-to-be-Done, hành vi, pain points", "#F59E0B"),
    ("Chuyên gia Đạo đức & Pháp lý", "Phân tích đạo đức AI, pháp lý, compliance, rủi ro", "#EF4444"),
    ("Chuyên gia Dữ liệu", "Phân tích metrics, đo lường, data pipeline", "#06B6D4"),
    ("Chuyên gia Vận hành", "Phân tích SOP, triển khai, hiring, quy trình", "#84CC16"),
    ("Chuyên gia Sáng tạo", "Phân tích ý tưởng đột phá, khác biệt, viral hook", "#EC4899"),
    ("Chuyên gia Tăng trưởng", "Phân tích growth loops, marketing, acquisition", "#6366F1"),
    ("Chuyên gia Bảo mật", "Phân tích bảo mật, an toàn, privacy", "#14B8A6"),
]

# ---------- LLM Helpers with REAL API ----------
async def call_llm(prompt: str, model: str, api_key: Optional[str], system_prompt: str) -> str:
    """
    Gọi API thật: ưu tiên Anthropic nếu model chứa claude, ngược lại OpenAI.
    Nếu không có key -> fallback mock để không crash.
    """
    try:
        # Anthropic
        if "claude" in model.lower():
            from anthropic import AsyncAnthropic
            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError("Missing ANTHROPIC_API_KEY")
            client = AsyncAnthropic(api_key=key)
            resp = await client.messages.create(
                model=model,
                max_tokens=800,
                system=system_prompt,
                messages=[{"role":"user","content":prompt}]
            )
            return resp.content[0].text

        # OpenAI compatible (gpt, gemini via openai compat nếu cần)
        else:
            from openai import AsyncOpenAI
            key = api_key or os.getenv("OPENAI_API_KEY")
            if not key:
                raise ValueError("Missing OPENAI_API_KEY")
            client = AsyncOpenAI(api_key=key)
            # map gemini to openai if needed, but default gpt-4o-mini
            use_model = model if "gpt" in model else "gpt-4o-mini"
            resp = await client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role":"system","content":system_prompt},
                    {"role":"user","content":prompt}
                ],
                temperature=0.8,
                max_tokens=800
            )
            return resp.choices[0].message.content
    except Exception as e:
        # Fallback mock vẫn trả về nội dung để demo không gãy
        print(f"[LLM Fallback] {e} for model {model}")
        return f"[MOCK - thiếu API key {model}] {system_prompt[:80]}... Phân tích cho: {prompt[:120]}..."

def generate_council(topic: str, count: int) -> List[ApiRole]:
    # deterministic sample + shuffle
    pool = ROLE_POOL.copy()
    random.seed(hash(topic) % 10000)
    random.shuffle(pool)
    selected = pool[:count]
    council=[]
    for i,(name,aspect,color) in enumerate(selected):
        council.append(ApiRole(
            id=f"auto_{i}_{uuid.uuid4().hex[:4]}",
            name=name,
            aspect=aspect,
            color=color,
            model=random.choice(["gpt-4o-mini","claude-3-5-sonnet-20241022"])
        ))
    return council

@app.get("/")
def root():
    return {
        "service":"Council AI",
        "version":"14.8 FINAL Real API",
        "flows":{
            "flow1":"/flow1/analyze - Auto expand đa khía cạnh",
            "flow2":"/flow2/debate - 5 vai tranh luận"
        },
        "env_keys_present":{
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY"))
        }
    }

@app.post("/flow1/analyze")
async def flow1_analyze(req: Flow1Request):
    if not req.topic.strip():
        raise HTTPException(400, "Topic trống")
    council = req.custom_roles if req.custom_roles and len(req.custom_roles)>0 else generate_council(req.topic, req.desired_count)

    messages=[]
    for member in council:
        system_prompt = f"Bạn là {member.name}. Chuyên môn: {member.aspect}. Hãy phân tích chủ đề từ đúng góc nhìn này, ngắn gọn 3-5 câu, tiếng Việt, sắc bén, có insight."
        user_prompt = f"Chủ đề: {req.topic}\nBối cảnh thêm: {req.context}\nNhiệm vụ: Phân tích từ góc nhìn {member.aspect}. Đưa ra 2 rủi ro và 1 đề xuất hành động."
        content = await call_llm(user_prompt, member.model, member.api_key, system_prompt)
        messages.append({
            "member_id": member.id,
            "member_name": member.name,
            "aspect": member.aspect,
            "model": member.model,
            "color": member.color,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    # Synthesis
    all_contents = "\n".join([f"- {m['member_name']}: {m['content']}" for m in messages])
    synth_system = "Bạn là Chủ tịch Hội đồng, tổng hợp phân tích đa chiều thành kết luận hành động rõ ràng, tiếng Việt, có bullet points."
    synth_prompt = f"Chủ đề: {req.topic}\nCác phân tích thành viên:\n{all_contents}\n\nHãy tổng hợp thành: 1) Điểm đồng thuận, 2) Mâu thuẫn cần giải quyết, 3) Kế hoạch hành động 3 bước MVP."
    synthesis = await call_llm(synth_prompt, "gpt-4o-mini", None, synth_system)

    return {
        "id": str(uuid.uuid4())[:8],
        "topic": req.topic,
        "council": [c.dict() for c in council],
        "messages": messages,
        "synthesis": synthesis,
        "created_at": datetime.now().isoformat()
    }

@app.post("/flow2/debate")
async def flow2_debate(req: Flow2Request):
    if not req.topic.strip():
        raise HTTPException(400, "Topic trống")

    fixed_roles = [
        ApiRole(id="analyst", name="Analyst", aspect="Phân tích logic, dữ liệu, rủi ro", color="#3B82F6", model="gpt-4o-mini"),
        ApiRole(id="creator", name="Creator", aspect="Sáng tạo đột phá, ý tưởng điên rồ khả thi", color="#8B5CF6", model="claude-3-5-sonnet-20241022"),
        ApiRole(id="critic", name="Critic", aspect="Phản biện, tìm lỗ hổng giả định", color="#EF4444", model="gpt-4o-mini"),
        ApiRole(id="empath", name="Empath", aspect="Con người, đạo đức, cảm xúc người dùng", color="#10B981", model="claude-3-5-sonnet-20241022"),
        ApiRole(id="executor", name="Executor", aspect="Thực thi, MVP, timeline, cắt scope", color="#F59E0B", model="gpt-4o-mini"),
    ]

    # override api keys if provided
    if req.custom_api_keys:
        for r in fixed_roles:
            if r.id in req.custom_api_keys:
                r.api_key = req.custom_api_keys[r.id]

    messages=[]
    history=""
    for rnd in range(1, req.rounds+1):
        for member in fixed_roles:
            system_prompt = f"Bạn là {member.name} - {member.aspect}. Bạn đang ở vòng {rnd} của cuộc tranh luận hội đồng 5 người về chủ đề. Phong cách: sắc bén, ngắn gọn 3-4 câu, tiếng Việt."
            if rnd==1:
                user_prompt = f"Chủ đề tranh luận: {req.topic}\nBối cảnh: {req.context}\nVòng 1: Đưa ra quan điểm đầu tiên từ góc nhìn {member.aspect} của bạn."
            else:
                user_prompt = f"Chủ đề: {req.topic}\nLịch sử tranh luận trước đó:\n{history[-2000:]}\n\nVòng {rnd}: Bạn là {member.name}. Phản hồi lại các ý kiến trên từ góc nhìn {member.aspect}, bổ sung hoặc phản biện."

            content = await call_llm(user_prompt, member.model, member.api_key, system_prompt)
            messages.append({
                "round": rnd,
                "member_id": member.id,
                "member_name": member.name,
                "role": member.aspect,
                "color": member.color,
                "model": member.model,
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
            history += f"\n[{member.name} - Vòng {rnd}]: {content}"

    # final conclusion
    synth_system = "Bạn là Chủ tịch hội đồng, tổng hợp tranh luận 5 vai thành kết luận cuối cùng cân bằng, tiếng Việt, rõ ràng, hành động được."
    synth_prompt = f"Chủ đề: {req.topic}\nToàn bộ tranh luận:\n{history[-4000:]}\n\nTổng hợp thành kết luận: Đồng thuận, Bất đồng, và Đề xuất MVP 7 ngày."
    final = await call_llm(synth_prompt, "gpt-4o-mini", None, synth_system)

    return {
        "id": str(uuid.uuid4())[:8],
        "topic": req.topic,
        "rounds": req.rounds,
        "messages": messages,
        "final_conclusion": final,
        "created_at": datetime.now().isoformat()
    }

# uvicorn main:app --reload --port 8000
