
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import os, uuid, json, random
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Council AI V14.8 FINAL", version="14.8.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PERSONNEL_FILE = DATA_DIR / "personnel.json"
MEMORY_FILE = DATA_DIR / "memory.json"

def load_personnel():
    if PERSONNEL_FILE.exists():
        try:
            return json.loads(PERSONNEL_FILE.read_text(encoding="utf-8"))
        except:
            return {"classic_5":[],"expand_pool":[]}
    return {"classic_5":[],"expand_pool":[]}

def load_memory():
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

def save_memory(entry):
    try:
        DATA_DIR.mkdir(exist_ok=True)
        mem = load_memory()
        mem.append(entry)
        if len(mem) > 50:
            mem = mem[-50:]
        MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass

class ApiRole(BaseModel):
    id: str
    name: str
    aspect: str
    model: str = "gpt-4o-mini"
    color: str = "#3B82F6"
    api_key: Optional[str] = None

class Flow1Request(BaseModel):
    topic: str
    context: Optional[str] = ""
    desired_count: int = 7
    custom_roles: Optional[List[ApiRole]] = None

class Flow2Request(BaseModel):
    topic: str
    context: Optional[str] = ""
    rounds: int = 2
    custom_api_keys: Optional[dict] = None

async def call_llm(prompt: str, model: str, api_key: Optional[str], system_prompt: str) -> str:
    try:
        if "claude" in model.lower():
            from anthropic import AsyncAnthropic
            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError("Missing ANTHROPIC_API_KEY")
            client = AsyncAnthropic(api_key=key)
            resp = await client.messages.create(model=model, max_tokens=800, system=system_prompt, messages=[{"role":"user","content":prompt}])
            return resp.content[0].text
        else:
            from openai import AsyncOpenAI
            key = api_key or os.getenv("OPENAI_API_KEY")
            if not key:
                raise ValueError("Missing OPENAI_API_KEY")
            client = AsyncOpenAI(api_key=key)
            use_model = model if "gpt" in model else "gpt-4o-mini"
            resp = await client.chat.completions.create(model=use_model, messages=[{"role":"system","content":system_prompt},{"role":"user","content":prompt}], temperature=0.8, max_tokens=800)
            return resp.choices[0].message.content
    except Exception as e:
        print(f"[FALLBACK] {e}")
        return f"[MOCK - Chưa có API key cho {model}] Phân tích: {prompt[:150]}..."

@app.get("/")
def root():
    return {
        "service": "Council AI",
        "version": "14.8 FINAL Flat - Complete",
        "structure": "flat - data/personnel.json",
        "flows": {
            "flow1": "/flow1/analyze - Auto expand đa khía cạnh",
            "flow2": "/flow2/debate - 5 vai tranh luận"
        },
        "routes": ["/", "/health", "/personnel", "/memory", "/frontend", "/docs", "/flow1/analyze", "/flow2/debate"],
        "env_keys_present": {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY"))
        },
        "personnel_loaded": PERSONNEL_FILE.exists()
    }

@app.get("/health")
def health():
    return {"status":"ok"}

@app.get("/personnel")
def get_personnel():
    return load_personnel()

@app.get("/memory")
def get_memory():
    return load_memory()

@app.get("/frontend", response_class=HTMLResponse)
def serve_frontend():
    html_path = BASE_DIR / "council-v20-frontend.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend not found - council-v20-frontend.html missing</h1><a href='/docs'>/docs</a>")

@app.post("/flow1/analyze")
async def flow1_analyze(req: Flow1Request):
    personnel_data = load_personnel()
    pool = personnel_data.get("expand_pool", [])
    if req.custom_roles and len(req.custom_roles)>0:
        council = req.custom_roles
    else:
        random.seed(hash(req.topic) % 10000)
        selected = random.sample(pool, min(req.desired_count, len(pool))) if pool else []
        council = [ApiRole(id=f"auto_{i}_{uuid.uuid4().hex[:4]}", name=s["name"], aspect=s["aspect"], color=s["color"], model=random.choice(["gpt-4o-mini","claude-3-5-sonnet-20241022"])) for i,s in enumerate(selected)]
    messages=[]
    for member in council:
        sys_prompt = f"Bạn là {member.name}. Chuyên môn: {member.aspect}. Phân tích ngắn gọn 3-5 câu, tiếng Việt."
        user_prompt = f"Chủ đề: {req.topic}\nBối cảnh: {req.context}\nNhiệm vụ: Phân tích từ góc nhìn {member.aspect}. 2 rủi ro + 1 đề xuất."
        content = await call_llm(user_prompt, member.model, member.api_key, sys_prompt)
        messages.append({"member_id":member.id,"member_name":member.name,"aspect":member.aspect,"color":member.color,"model":member.model,"content":content,"timestamp":datetime.now().isoformat()})
    all_text = "\n".join([f"- {m['member_name']}: {m['content']}" for m in messages])
    synthesis = await call_llm(f"Chủ đề: {req.topic}\nPhân tích:\n{all_text}\n\nTổng hợp đồng thuận, mâu thuẫn, MVP 3 bước.", "gpt-4o-mini", None, "Bạn là Chủ tịch, tổng hợp đa chiều.")
    result = {"id":str(uuid.uuid4())[:8],"topic":req.topic,"council":[c.dict() for c in council],"messages":messages,"synthesis":synthesis,"created_at":datetime.now().isoformat()}
    save_memory({"type":"flow1","topic":req.topic,"at":datetime.now().isoformat()})
    return result

@app.post("/flow2/debate")
async def flow2_debate(req: Flow2Request):
    personnel_data = load_personnel()
    classic = personnel_data.get("classic_5", [])
    fixed = [ApiRole(**c) for c in classic] if classic else [
        ApiRole(id="analyst", name="Analyst", aspect="Phân tích logic", color="#3B82F6", model="gpt-4o-mini"),
        ApiRole(id="creator", name="Creator", aspect="Sáng tạo", color="#8B5CF6", model="claude-3-5-sonnet-20241022"),
        ApiRole(id="critic", name="Critic", aspect="Phản biện", color="#EF4444", model="gpt-4o-mini"),
        ApiRole(id="empath", name="Empath", aspect="Con người", color="#10B981", model="claude-3-5-sonnet-20241022"),
        ApiRole(id="executor", name="Executor", aspect="Thực thi", color="#F59E0B", model="gpt-4o-mini"),
    ]
    if req.custom_api_keys:
        for r in fixed:
            if r.id in req.custom_api_keys:
                r.api_key = req.custom_api_keys[r.id]
    messages=[]; history=""
    for rnd in range(1, req.rounds+1):
        for member in fixed:
            sys_prompt = f"Bạn là {member.name} - {member.aspect}. Vòng {rnd} tranh luận 5 người."
            user_prompt = f"Chủ đề: {req.topic}\nBối cảnh: {req.context}\nLịch sử:\n{history[-2000:]}\n\nVòng {rnd}: Quan điểm của bạn." if rnd>1 else f"Chủ đề: {req.topic}\nVòng 1: Quan điểm đầu tiên từ góc nhìn {member.aspect}."
            content = await call_llm(user_prompt, member.model, member.api_key, sys_prompt)
            messages.append({"round":rnd,"member_id":member.id,"member_name":member.name,"role":member.aspect,"color":member.color,"model":member.model,"content":content,"timestamp":datetime.now().isoformat()})
            history+=f"\n[{member.name}-V{rnd}]: {content}"
    final = await call_llm(f"Chủ đề: {req.topic}\nTranh luận:\n{history[-4000:]}\n\nKết luận đồng thuận, bất đồng, MVP 7 ngày.", "gpt-4o-mini", None, "Bạn là Chủ tịch, tổng hợp tranh luận.")
    result = {"id":str(uuid.uuid4())[:8],"topic":req.topic,"rounds":req.rounds,"messages":messages,"final_conclusion":final,"created_at":datetime.now().isoformat()}
    save_memory({"type":"flow2","topic":req.topic,"at":datetime.now().isoformat()})
    return result
