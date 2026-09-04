
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import os, uuid, json, random
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Council AI V14.8 FINAL", version="14.8.1")

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
            pass
    return {"classic_5":[],"expand_pool":[]}

def load_memory():
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return []

def save_memory(entry):
    try:
        DATA_DIR.mkdir(exist_ok=True)
        mem = load_memory()
        mem.append(entry)
        if len(mem)>50: mem=mem[-50:]
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

def get_api_key(provider: str, explicit: Optional[str]=None):
    if explicit: return explicit
    # Support all env names Boss has
    mapping = {
        "openai": ["OPENAI_API_KEY", "OPENAI_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "groq": ["GROQ_API_KEY", "GROQ_KEY"],
        "mistral": ["MISTRAL_API_KEY", "MISTRAL_KEY"],
        "openrouter": ["OPENROUTER_API_KEY", "OPENROUTER_KEY"],
    }
    for key_name in mapping.get(provider, []):
        v = os.getenv(key_name)
        if v: return v
    # fallback any key available
    for env in ["GROQ_API_KEY","OPENROUTER_API_KEY","OPENAI_API_KEY","ANTHROPIC_API_KEY","MISTRAL_API_KEY"]:
        v = os.getenv(env)
        if v: return v
    return None

def get_provider_from_model(model: str):
    m = model.lower()
    if "claude" in m: return "anthropic"
    if "mistral" in m: return "mistral"
    if "llama" in m or "groq" in m or "mixtral" in m: return "groq"
    if "openrouter" in m: return "openrouter"
    return "openai"

async def call_llm(prompt: str, model: str, api_key: Optional[str], system_prompt: str) -> str:
    provider = get_provider_from_model(model)
    key = get_api_key(provider, api_key)
    if not key:
        return f"[MOCK - Thieu API key cho {model} ({provider}). Da tim: GROQ/OPENROUTER/OPENAI/ANTHROPIC/MISTRAL nhung khong thay] Phân tích cho: {prompt[:150]}"

    try:
        if provider == "anthropic":
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=key)
            use_model = model if "claude" in model.lower() else "claude-3-5-sonnet-20241022"
            resp = await client.messages.create(model=use_model, max_tokens=900, system=system_prompt, messages=[{"role":"user","content":prompt}])
            return resp.content[0].text

        # For OpenAI-compatible: OpenAI, Groq, OpenRouter, Mistral
        from openai import AsyncOpenAI

        # Determine base_url
        base_url = None
        if provider == "groq":
            base_url = os.getenv("GROQ_API_URL") or "https://api.groq.com/openai/v1"
            use_model = os.getenv("GROQ_MODEL") or "llama-3.1-70b-versatile"
            if "gpt" not in model.lower() and "llama" not in model.lower():
                # if user set specific model like groq/llama, use it
                use_model = model if "llama" in model or "mixtral" in model or "gemma" in model else use_model
        elif provider == "openrouter":
            base_url = os.getenv("OPENROUTER_API_URL") or "https://openrouter.ai/api/v1"
            use_model = os.getenv("OPENROUTER_MODEL") or model or "meta-llama/llama-3.1-70b-instruct"
        elif provider == "mistral":
            base_url = os.getenv("MISTRAL_API_URL") or "https://api.mistral.ai/v1"
            use_model = os.getenv("MISTRAL_MODEL") or "mistral-large-latest"
        else: # openai
            base_url = os.getenv("OPENAI_API_URL") or None
            use_model = model if model else "gpt-4o-mini"

        client = AsyncOpenAI(api_key=key, base_url=base_url) if base_url else AsyncOpenAI(api_key=key)
        resp = await client.chat.completions.create(
            model=use_model,
            messages=[{"role":"system","content":system_prompt},{"role":"user","content":prompt}],
            temperature=0.8,
            max_tokens=900
        )
        return resp.choices[0].message.content

    except Exception as e:
        return f"[LOI API {provider}/{model}: {str(e)[:300]}] Fallback phan tich: {prompt[:120]}"

@app.get("/")
def root():
    keys = {
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "mistral": bool(os.getenv("MISTRAL_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
    }
    return {
        "service":"Council AI",
        "version":"14.8.1 - Multi Provider (GROQ/MISTRAL/OPENROUTER/OPENAI/CLAUDE)",
        "structure":"flat",
        "keys_detected": keys,
        "env_keys_present": {k: v for k,v in keys.items() if v},
        "has_any_key": any(keys.values()),
        "routes":["/","/personnel","/frontend","/docs","/flow1/analyze","/flow2/debate"],
        "note":"Add ENV GROUP to service in Render > Environment > Add from Group"
    }

@app.get("/health")
def health(): return {"ok":True, "has_key": any([bool(os.getenv(k)) for k in ["GROQ_API_KEY","OPENROUTER_API_KEY","OPENAI_API_KEY","ANTHROPIC_API_KEY","MISTRAL_API_KEY"]])}

@app.get("/personnel")
def get_personnel(): return load_personnel()

@app.get("/frontend", response_class=HTMLResponse)
def frontend():
    p = BASE_DIR / "council-v20-frontend.html"
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend missing</h1>")

@app.post("/flow1/analyze")
async def flow1(req: Flow1Request):
    personnel_data = load_personnel()
    pool = personnel_data.get("expand_pool", [])
    if req.custom_roles and len(req.custom_roles)>0:
        council = req.custom_roles
    else:
        selected = random.sample(pool, min(req.desired_count, len(pool))) if pool else []
        council = [ApiRole(id=f"auto_{i}", name=s["name"], aspect=s["aspect"], color=s.get("color","#3B82F6"), model=random.choice(["llama-3.1-70b-versatile","gpt-4o-mini","claude-3-5-sonnet-20241022"])) for i,s in enumerate(selected)]
    msgs=[]
    for member in council:
        sys_p = f"Bạn là {member.name}, chuyên môn {member.aspect}. Trả lời tiếng Việt ngắn gọn 3-5 câu."
        user_p = f"Chủ đề: {req.topic}\nBối cảnh: {req.context}\nNhiệm vụ: Phân tích từ góc {member.aspect}, 2 rủi ro + 1 đề xuất."
        content = await call_llm(user_p, member.model, member.api_key, sys_p)
        msgs.append({"member_id":member.id,"member_name":member.name,"aspect":member.aspect,"color":member.color,"model":member.model,"content":content})
    all_text = "\n".join([f"{m['member_name']}: {m['content']}" for m in msgs])
    synth = await call_llm(f"Chủ đề: {req.topic}\nPhân tích:\n{all_text}\nTổng hợp đồng thuận, mâu thuẫn, MVP 3 bước.", "llama-3.1-70b-versatile", None, "Bạn là chủ tịch tổng hợp.")
    return {"id":str(uuid.uuid4())[:8],"topic":req.topic,"council":[c.dict() for c in council],"messages":msgs,"synthesis":synth}

@app.post("/flow2/debate")
async def flow2(req: Flow2Request):
    personnel_data = load_personnel()
    classic = personnel_data.get("classic_5", [])
    fixed = [ApiRole(**c) for c in classic] if classic else [
        ApiRole(id="analyst",name="Analyst",aspect="Phân tích logic",color="#3B82F6",model="llama-3.1-70b-versatile"),
        ApiRole(id="creator",name="Creator",aspect="Sáng tạo",color="#8B5CF6",model="claude-3-5-sonnet-20241022"),
        ApiRole(id="critic",name="Critic",aspect="Phản biện",color="#EF4444",model="gpt-4o-mini"),
        ApiRole(id="empath",name="Empath",aspect="Con người",color="#10B981",model="gpt-4o-mini"),
        ApiRole(id="executor",name="Executor",aspect="Thực thi",color="#F59E0B",model="llama-3.1-70b-versatile"),
    ]
    msgs=[]; hist=""
    for rnd in range(1, req.rounds+1):
        for member in fixed:
            sys_p = f"Bạn là {member.name} - {member.aspect}. Vòng {rnd}"
            user_p = f"Chủ đề: {req.topic}\nLịch sử:\n{hist[-2000:]}\n\nVòng {rnd}: Quan điểm của bạn." if rnd>1 else f"Chủ đề: {req.topic}\nVòng 1: Quan điểm đầu từ góc {member.aspect}"
            content = await call_llm(user_p, member.model, member.api_key, sys_p)
            msgs.append({"round":rnd,"member_id":member.id,"member_name":member.name,"role":member.aspect,"color":member.color,"model":member.model,"content":content})
            hist+=f"\n[{member.name} V{rnd}]: {content}"
    final = await call_llm(f"Chủ đề: {req.topic}\nTranh luận:\n{hist[-4000:]}\nKết luận đồng thuận, bất đồng, MVP 7 ngày.", "llama-3.1-70b-versatile", None, "Bạn là chủ tịch")
    return {"id":str(uuid.uuid4())[:8],"topic":req.topic,"rounds":req.rounds,"messages":msgs,"final_conclusion":final}
