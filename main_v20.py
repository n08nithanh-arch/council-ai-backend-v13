import os, uuid, asyncio, requests, re, json, traceback
from typing import Dict, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv, dotenv_values
from datetime import datetime
from pathlib import Path

load_dotenv()
app = FastAPI(title="Council AI V13 CLEAN - Local Memory + Google Drive Ready")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
PERSONNEL_FILE = DATA_DIR / "personnel.json"
FRONTEND_FILE = Path(__file__).parent / "council-v20-frontend.html"

councils_db: Dict = {}
ALIVE_PROVIDERS: List[Dict] = []

def scan_env_apis():
    env = {}
    if os.path.exists(".env"):
        env.update(dotenv_values(".env"))
    env.update(dict(os.environ))
    apis_raw = []
    for k, v in env.items():
        if not v or len(v.strip()) < 10: continue
        uk = k.upper()
        if "API_KEY" not in uk: continue
        if uk in ["ANDROID_API_KEY"]: continue
        provider = uk.replace("_API_KEY","").lower()
        if provider in ["android"]: continue
        prov_base = provider.split("_")[0]
        if "mistral" in provider: prov_base = "mistral"
        elif "groq" in provider: prov_base = "groq"
        elif "openrouter" in provider: prov_base = "openrouter"
        else:
            if prov_base not in ["mistral","groq","openrouter"]: continue
        base_url = env.get(f"{provider.upper()}_API_URL") or env.get(f"{prov_base.upper()}_API_URL") or ""
        model = env.get(f"{provider.upper()}_MODEL") or env.get(f"{prov_base.upper()}_MODEL") or ""
        if not base_url:
            if "mistral" in prov_base: base_url = "https://api.mistral.ai/v1"
            elif "groq" in prov_base: base_url = "https://api.groq.com/openai/v1"
            elif "openrouter" in prov_base: base_url = "https://openrouter.ai/api/v1"
        apis_raw.append({"provider": prov_base, "api_key": v.strip(), "base_url": base_url.strip().rstrip("/"), "model": model.strip(), "env_key": k})
    deduped = {}
    for api in apis_raw:
        pb = api["provider"]
        if pb not in deduped:
            deduped[pb] = api
        else:
            if len(api["model"]) > len(deduped[pb]["model"]):
                deduped[pb] = api
    return list(deduped.values())

def test_provider_alive(api: Dict) -> bool:
    p, key, base, model = api["provider"], api["api_key"], api["base_url"], api["model"]
    try:
        if "mistral" in p:
            m = model or "mistral-small-latest"
            r = requests.post(f"{base or 'https://api.mistral.ai/v1'}/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"}, json={"model": m, "messages": [{"role":"user","content":"hi"}], "max_tokens":5}, timeout=12)
            if r.status_code in [200,429]:
                api["model"]=m; api["status"]="alive" if r.status_code==200 else "rate_limited"; return True
            print(f"❌ {p} fail {r.status_code} {r.text[:200]}")
            return False
        elif "groq" in p:
            for m in [model, "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
                if not m: continue
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"}, json={"model": m, "messages": [{"role":"user","content":"hi"}], "max_tokens":5}, timeout=12)
                if r.status_code in [200,429]:
                    api["model"]=m; api["status"]="alive" if r.status_code==200 else "rate_limited"; return True
                print(f"❌ groq {m} {r.status_code}")
            return False
        elif "openrouter" in p:
            headers = {"Authorization": f"Bearer {key}", "Content-Type":"application/json", "HTTP-Referer":"http://localhost:3000", "X-Title":"Council AI"}
            # FIX: dùng model free chắc chắn tồn tại trên OpenRouter
            for m in [model, "openai/gpt-4o-mini", "meta-llama/llama-3.1-8b-instruct:free", "google/gemini-flash-1.5-8b:free", "openai/gpt-3.5-turbo"]:
                if not m: continue
                r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json={"model": m, "messages":[{"role":"user","content":"hi"}], "max_tokens":5}, timeout=15)
                if r.status_code in [200,429]:
                    api["model"]=m; api["status"]="alive" if r.status_code==200 else "rate_limited"; print(f"✅ openrouter alive with {m}"); return True
                print(f"❌ openrouter {m} {r.status_code} {r.text[:300]}")
            return False
        else: return False
    except Exception as e:
        print(f"❌ {p} exception {e}")
        return False

def refresh_alive_providers():
    global ALIVE_PROVIDERS
    all_apis = scan_env_apis()
    print(f"🔍 Scan {len(all_apis)} API keys: {[a['provider'] for a in all_apis]}")
    alive = []
    for api in all_apis:
        if test_provider_alive(api):
            alive.append(api)
    if not alive and all_apis:
        print(f"⚠️ Không có API nào alive, dùng fallback {all_apis[0]['provider']}")
        alive = [all_apis[0]]; alive[0]["status"]="fallback"
    ALIVE_PROVIDERS = alive
    print(f"\n🔥 {len(ALIVE_PROVIDERS)} API SONG THAT: {[p['provider']+':'+p['model'] for p in ALIVE_PROVIDERS]}")
    return ALIVE_PROVIDERS

refresh_alive_providers()

def get_default_personnel():
    prov = lambda i: ALIVE_PROVIDERS[i % len(ALIVE_PROVIDERS)]["provider"] if ALIVE_PROVIDERS else "mistral"
    mod = lambda i: ALIVE_PROVIDERS[i % len(ALIVE_PROVIDERS)]["model"] if ALIVE_PROVIDERS else "mistral-small-latest"
    return [
        {"id": "core_thuky", "name": "Thư Ký Hội Đồng", "role": "Thư Ký Hội Đồng", "desc": "Ghi biên bản, điểm danh, lưu file", "system_prompt": "Bạn là Thư Ký Hội Đồng - vai CORE. Điểm danh, ghi biên bản 80-120 từ.", "color": "#2B2D42", "type": "core", "core_type": "thuky", "provider": prov(0), "model": mod(0), "trained": True},
        {"id": "core_phoql", "name": "Phó Quản Lý Điều Hành", "role": "Phó Quản Lý Điều Hành", "desc": "Tổng hợp, ra quyết định cuối", "system_prompt": "Bạn là Phó Quản Lý Điều Hành - vai CORE quyền lực thứ 2. Tổng hợp ý kiến, ra quyết định cuối cùng, 3 bước hành động có deadline.", "color": "#EF476F", "type": "core", "core_type": "phoql", "provider": prov(1) if len(ALIVE_PROVIDERS)>1 else prov(0), "model": mod(1) if len(ALIVE_PROVIDERS)>1 else mod(0), "trained": True},
        {"id": "core_nhansu", "name": "Trưởng Phòng Nhân Sự", "role": "Trưởng Phòng Nhân Sự", "desc": "Quản lý Danh sách Hội đồng", "system_prompt": "Bạn là Trưởng Phòng Nhân Sự - vai CORE quản lý Danh sách Hội đồng. Đặt chức danh theo nhu cầu, viết system_prompt riêng.", "color": "#118AB2", "type": "core", "core_type": "nhansu", "provider": prov(2) if len(ALIVE_PROVIDERS)>2 else prov(0), "model": mod(2) if len(ALIVE_PROVIDERS)>2 else mod(0), "trained": True},
    ]

def load_personnel():
    try:
        if PERSONNEL_FILE.exists():
            txt = PERSONNEL_FILE.read_text(encoding='utf-8').strip()
            if txt:
                data = json.loads(txt)
                if isinstance(data, list) and len(data)>=3:
                    return data
    except Exception as e:
        print(f"load_personnel error {e}, reset")
    data = get_default_personnel()
    PERSONNEL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data

def get_provider_info(name: str):
    for p in ALIVE_PROVIDERS:
        if p["provider"]==name.lower():
            return p
    return ALIVE_PROVIDERS[0] if ALIVE_PROVIDERS else {"provider":"mistral","api_key":"demo","base_url":"https://api.mistral.ai/v1","model":"mistral-small-latest","status":"demo"}

def call_llm_real(provider_info, system_prompt, user_prompt, max_tokens=600, temp=0.7):
    try:
        if not provider_info or provider_info.get("api_key")=="demo":
            return f"[{provider_info.get('provider','demo')}] Fallback cho: {user_prompt[:120]}"
        base=provider_info.get("base_url") or "https://api.mistral.ai/v1"
        model=provider_info.get("model") or "mistral-small-latest"
        key=provider_info.get("api_key") or ""
        msgs=[{"role":"system","content":system_prompt},{"role":"user","content":user_prompt}]
        headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"}
        if "openrouter" in provider_info.get("provider",""):
            headers.update({"HTTP-Referer":"http://localhost:3000","X-Title":"Council AI"})
        r=requests.post(f"{base}/chat/completions", headers=headers, json={"model":model,"messages":msgs,"max_tokens":max_tokens,"temperature":temp}, timeout=30)
        if r.status_code==200 and "choices" in r.json():
            return r.json()["choices"][0]["message"]["content"]
        # fallback qua provider khac
        for alt in ALIVE_PROVIDERS:
            if alt["provider"]!=provider_info["provider"]:
                try:
                    b2=alt.get("base_url") or base; m2=alt.get("model") or model; k2=alt.get("api_key")
                    h2={"Authorization": f"Bearer {k2}", "Content-Type":"application/json"}
                    if "openrouter" in alt.get("provider",""): h2.update({"HTTP-Referer":"http://localhost:3000","X-Title":"Council AI"})
                    r2=requests.post(f"{b2}/chat/completions", headers=h2, json={"model":m2,"messages":msgs,"max_tokens":max_tokens,"temperature":temp}, timeout=25)
                    if r2.status_code==200 and "choices" in r2.json():
                        return r2.json()["choices"][0]["message"]["content"] + f" (via {alt['provider']})"
                except: continue
        return f"[FALLBACK] {user_prompt[:120]}"
    except Exception as e:
        return f"[FALLBACK EX] {str(e)[:80]}"

class CreateCouncilReq(BaseModel):
    problem: str
    selected_personnel_ids: List[str]
    room: str = "Phòng Họp A"

class ChatMessage(BaseModel):
    message: str

class SuggestReq(BaseModel):
    problem: str

def suggest_roles_by_context(problem: str, existing_roles: List[Dict]) -> List[Dict]:
    pl = problem.lower()
    km = {
        "kỹ thuật|lập trình|code|phần mềm|AI|hệ thống": {"role": "Chuyên gia Kỹ thuật", "desc": "Phân tích kỹ thuật", "prompt": "Bạn là Chuyên gia Kỹ thuật.", "color": "#6EC1E4"},
        "marketing|bán hàng|truyền thông|quảng cáo": {"role": "Chuyên gia Marketing", "desc": "Chiến lược marketing", "prompt": "Bạn là Chuyên gia Marketing.", "color": "#FF6B6B"},
        "tài chính|đầu tư|kinh tế|tiền": {"role": "Chuyên gia Tài chính", "desc": "Phân tích tài chính", "prompt": "Bạn là Chuyên gia Tài chính.", "color": "#4ECDC4"},
        "ngọc hoàng|đại đế|tôn giáo|tín ngưỡng|văn hóa dân gian|thần thoại": {"role": "Chuyên gia Văn hóa Dân gian & Tôn giáo", "desc": "Phân tích tín ngưỡng", "prompt": "Bạn là Chuyên gia Văn hóa Dân gian & Tôn giáo.", "color": "#F59E0B"},
        "khí tượng|thủy văn|câu cá|thời tiết|mưa giông|gió|nhiệt độ|thủy triều|mưa hay nắng": {"role": "Chuyên gia Khí tượng Thủy văn", "desc": "Đánh giá thời tiết", "prompt": "Bạn là Chuyên gia Khí tượng Thủy văn. Đánh giá thời tiết mưa nắng.", "color": "#06B6D4"},
    }
    suggested = []
    existing_names = [r["role"].lower() for r in existing_roles]
    for pat, tpl in km.items():
        if re.search(pat, pl):
            if tpl["role"].lower() not in existing_names and tpl["role"] not in [s["role"] for s in suggested]:
                suggested.append(tpl)
    if not suggested:
        suggested = [{"role": "Chuyên gia Tổng hợp", "desc": "Phân tích tổng hợp", "prompt": f"Bạn là Chuyên gia Tổng hợp cho vấn đề: {problem[:100]}", "color": "#6EC1E4"}]
    return suggested[:3]

def make_bien_ban_filename(problem: str, ext: str = "txt"):
    now = datetime.now()
    time_str = now.strftime("%d-%m-%Y %H-%M-%S")
    summary = re.sub(r'[^\w\s\-]', '', problem.strip()[:40]).strip() or "Cuoc hop hoi dong"
    base_name = f"bien ban hop - {summary} - {time_str}"
    safe_name = re.sub(r'[\/\:\*\?\"\<\>\|]', '-', base_name)
    return f"{safe_name}.{ext}", base_name

@app.get("/")
def root():
    return {"name":"Council AI V13 CLEAN - Local Memory + Google Drive Ready","alive_apis":len(ALIVE_PROVIDERS),"providers":[{"provider":p["provider"],"model":p["model"],"status":p.get("status"),"env_key":p.get("env_key")} for p in ALIVE_PROVIDERS],"personnel_count":len(load_personnel()),"note":"V13 CLEAN: bien ban luu localStorage, khong ghi 9.89GB ra disk"}

@app.get("/personnel")
def get_personnel():
    return load_personnel()

@app.post("/personnel")
def create_personnel(req: dict):
    role = req.get("role","").strip()
    if not role: return {"error":"Thiếu role"}
    all_p = load_personnel()
    nid = f"role_{uuid.uuid4().hex[:6]}"
    prov = ALIVE_PROVIDERS[len(all_p) % len(ALIVE_PROVIDERS)] if ALIVE_PROVIDERS else {"provider":"mistral","model":"mistral-small-latest"}
    new_role = {"id": nid, "name": role, "role": role, "desc": req.get("desc",""), "system_prompt": req.get("system_prompt","") or f"Bạn là {role}", "color": "#%06x" % (hash(role) % 0xFFFFFF), "type": "council", "provider": prov["provider"], "model": prov["model"], "trained": True}
    all_p.append(new_role)
    PERSONNEL_FILE.write_text(json.dumps(all_p, ensure_ascii=False, indent=2), encoding='utf-8')
    return new_role

@app.delete("/personnel/{pid}")
def delete_personnel(pid: str):
    all_p = load_personnel()
    all_p = [p for p in all_p if p["id"]!=pid and p.get("type")!="core" or p["id"]==pid and p.get("type")=="core" and False or p["id"]!=pid]
    # Actually keep core
    all_p = [p for p in load_personnel() if p["id"]!=pid or p.get("type")=="core"]
    PERSONNEL_FILE.write_text(json.dumps(all_p, ensure_ascii=False, indent=2), encoding='utf-8')
    return {"ok":True}

@app.put("/personnel/{pid}")
def update_personnel(pid: str, req: dict):
    all_p = load_personnel()
    for p in all_p:
        if p["id"]==pid:
            if "desc" in req: p["desc"]=req["desc"]
            if "system_prompt" in req: p["system_prompt"]=req["system_prompt"]
            if "provider" in req: p["provider"]=req["provider"]
    PERSONNEL_FILE.write_text(json.dumps(all_p, ensure_ascii=False, indent=2), encoding='utf-8')
    return {"ok":True}

@app.post("/personnel/suggest")
@app.post("/api/suggest")
@app.post("/suggest")
@app.post("/api/personnel/suggest")
def suggest_personnel(req: SuggestReq):
    existing=load_personnel()
    suggested=suggest_roles_by_context(req.problem, existing)
    auto_added = []
    current = load_personnel()
    existing_roles_lower = [p["role"].lower() for p in current]
    for idx, s in enumerate(suggested):
        if s["role"].lower() not in existing_roles_lower:
            nid = f"role_{uuid.uuid4().hex[:6]}"
            prov_idx = (len(current) + idx) % len(ALIVE_PROVIDERS) if ALIVE_PROVIDERS else 0
            prov = get_provider_info(ALIVE_PROVIDERS[prov_idx]["provider"] if ALIVE_PROVIDERS else "mistral")
            new_role = {
                "id": nid, "name": s["role"], "role": s["role"],
                "desc": s["desc"], "system_prompt": s["prompt"] + f" Ngữ cảnh: {req.problem[:300]}",
                "color": s["color"], "type": "council",
                "provider": prov["provider"], "model": prov["model"],
                "trained": True, "auto_generated": True,
                "created_at": datetime.now().isoformat()
            }
            current.append(new_role)
            auto_added.append(new_role)
    if auto_added:
        Path(PERSONNEL_FILE).write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    return {"problem":req.problem,"suggested":suggested,"auto_added":auto_added,"auto_call":True}

@app.get("/app")
@app.get("/frontend")
@app.get("/ui")
def serve_frontend():
    if FRONTEND_FILE.exists():
        return FileResponse(FRONTEND_FILE, media_type="text/html")
    return {"error":"Chua co council-v20-frontend.html"}

councils_db: Dict = {}

@app.post("/councils")
def create_council(req: CreateCouncilReq):
    try:
        cid=uuid.uuid4().hex[:8]
        all_personnel={p["id"]:p for p in load_personnel()}
        core_ids=["core_thuky","core_phoql","core_nhansu"]
        selected=set(req.selected_personnel_ids)
        for c in core_ids: selected.add(c)
        suggested=suggest_roles_by_context(req.problem, [all_personnel[i] for i in selected if i in all_personnel])
        auto_added=[]
        for s in suggested:
            exists=any(all_personnel[pid]["role"].lower()==s["role"].lower() for pid in selected if pid in all_personnel)
            if not exists:
                nid=f"role_{uuid.uuid4().hex[:6]}"
                prov_idx = (len(all_personnel) + len(auto_added)) % len(ALIVE_PROVIDERS) if ALIVE_PROVIDERS else 0
                prov=get_provider_info(ALIVE_PROVIDERS[prov_idx]["provider"] if ALIVE_PROVIDERS else "mistral")
                new_role={"id":nid,"name":s["role"],"role":s["role"],"desc":s["desc"],"system_prompt":s["prompt"]+f" Ngữ cảnh: {req.problem[:300]}","color":s["color"],"type":"council","provider":prov["provider"],"model":prov["model"],"trained":True,"auto_generated":True,"created_at":datetime.now().isoformat()}
                cur=load_personnel(); cur.append(new_role); Path(PERSONNEL_FILE).write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding='utf-8')
                all_personnel[nid]=new_role; selected.add(nid); auto_added.append(new_role)
        roles={}
        for pid in selected:
            if pid not in all_personnel: continue
            p=all_personnel[pid]
            roles[pid]={"short_name":p["name"],"role":p["role"],"system":p["system_prompt"],"color":p["color"],"provider_info":get_provider_info(p["provider"]),"trained":p.get("trained",False),"core_type":p.get("core_type",""),"is_core":p.get("type")=="core"}
        councils_db[cid]={"id":cid,"title":req.problem[:80],"problem":req.problem,"room":req.room,"roles":roles,"active_roles":list(roles.keys()),"history":[],"minutes":[],"created_at":datetime.now().isoformat(),"auto_added":auto_added}
        return {"id":cid,"title":req.problem[:80],"roles":list(roles.values()),"active_roles":list(roles.keys()),"auto_added":auto_added}
    except Exception as e:
        return {"error":str(e), "detail": traceback.format_exc()[:1000]}

@app.post("/councils/{cid}/run")
async def run_council(cid: str):
    try:
        if cid not in councils_db: return {"error":"Council not found"}
        data=councils_db[cid]
        thuky=next((v for k,v in data["roles"].items() if v.get("core_type")=="thuky"), None)
        # FIX: diem danh chi ghi co mat, khong duoc bia vang mat
        active_names = [data["roles"][rid]["short_name"] for rid in data["active_roles"] if rid in data["roles"]]
        rollcall_prompt = f"""Vấn đề: '{data['problem']}' 
Danh sách tham dự THỰC TẾ có mặt: {', '.join(active_names)} ({len(active_names)} người)
Nhiệm vụ: Ghi điểm danh NGẮN GỌN, chỉ liệt kê những người CÓ MẶT ở trên, KHÔNG được bịa thêm người vắng mặt, không được ghi lý do vắng.
Format: 
- Ngày: hôm nay
- Chủ trì: Trưởng Phòng Nhân Sự
- Thư ký: Thư Ký Hội Đồng
- Có mặt: {', '.join(active_names)}
Chỉ ghi đúng danh sách có mặt, không thêm gì khác, 50-80 từ."""
        rollcall = await asyncio.to_thread(call_llm_real, thuky["provider_info"] if thuky else get_provider_info("mistral"), thuky["system"] if thuky else "Ban la Thu Ky - chi ghi co mat, khong bia vang mat", rollcall_prompt, 300, 0.5) if thuky else f"Có mặt: {', '.join(active_names)}"
        experts=[]
        for rid,info in data["roles"].items():
            if info.get("core_type") in ["thuky","phoql","nhansu"]: continue
            if rid not in data["active_roles"]: continue
            try:
                ans=await asyncio.to_thread(call_llm_real, info["provider_info"], info["system"], f"Vấn đề: '{data['problem']}' - Bạn là {info['short_name']} ({info['role']}). Đưa ý kiến đầy đủ chi tiết 250-400 từ.", 600, 0.8)
                experts.append({"personnel_id":rid,"name":info["short_name"],"role":info["role"],"content":ans,"provider":info["provider_info"]["provider"]})
            except Exception as ex:
                experts.append({"personnel_id":rid,"name":info["short_name"],"role":info["role"],"content":f"[Lỗi {ex}]","provider":info["provider_info"]["provider"]})
        phoql=next((v for k,v in data["roles"].items() if v.get("core_type")=="phoql"), None)
        summary_prompt = f"Vấn đề: '{data['problem']}'\nCác ý kiến chuyên gia:\n" + "\n".join([f"- {e['name']} ({e['role']}): {e['content'][:400]}" for e in experts]) + "\nTổng hợp ra quyết định cuối cùng 3 bước hành động có deadline."
        summary = await asyncio.to_thread(call_llm_real, phoql["provider_info"] if phoql else get_provider_info("mistral"), phoql["system"] if phoql else "Ban la Pho Quan Ly", summary_prompt, 700, 0.7)
        minutes_content = f"# Biên bản họp - {data['problem']}\n\n## Điểm danh\n{rollcall}\n\n## Ý kiến chuyên gia\n" + "\n\n".join([f"### {e['name']} - {e['role']} [{e['provider']}]\n{e['content']}" for e in experts]) + f"\n\n## Tổng hợp - Phó Quản Lý Điều Hành\n{summary}\n"
        base_txt, base_name = make_bien_ban_filename(data['problem'], "txt")
        # V13 CLEAN: KHÔNG ghi ra disk data/meetings/ để tránh 9.89GB, chỉ trả về local memory
        result = {"rollcall": rollcall, "experts": experts, "summary": summary, "minutes_content": minutes_content, "base_name": base_name, "minutes_files": [], "total_chars": len(minutes_content)}
        councils_db[cid]["last_result"]=result
        return result
    except Exception as e:
        traceback.print_exc()
        return {"error":str(e), "detail": traceback.format_exc()[:2000]}

@app.post("/councils/{cid}/chat")
async def continue_chat(cid: str, msg: ChatMessage):
    try:
        if cid not in councils_db: return {"error":"Not found"}
        data=councils_db[cid]
        clean=msg.message.replace("@@","@")
        clean_lower=clean.lower()
        if "@thư ký" in clean_lower or "@thu ky" in clean_lower:
            all_personnel = {p["id"]: p for p in load_personnel()}
            added = []
            for pid, p in all_personnel.items():
                role_lower = p["role"].lower()
                if role_lower in clean_lower and pid not in data["active_roles"]:
                    if pid not in data["roles"]:
                        data["roles"][pid] = {"short_name": p["name"], "role": p["role"], "system": p["system_prompt"], "color": p["color"], "provider_info": get_provider_info(p["provider"]), "trained": p.get("trained",False), "core_type": p.get("core_type",""), "is_core": p.get("type")=="core"}
                    data["active_roles"].append(pid)
                    added.append(p["role"])
            if added:
                return {"action":"add_team","added_roles":added,"text":f"Đã gọi thêm: {', '.join(added)}"}
        mentioned_ids = []
        for rid, info in data["roles"].items():
            if f"@{info['short_name']}" in clean and rid in data["active_roles"]:
                mentioned_ids.append(rid)
        if mentioned_ids:
            results = {}
            for rid in mentioned_ids[:6]:
                info = data["roles"][rid]
                ans = await asyncio.to_thread(call_llm_real, info["provider_info"], info["system"], f"Chủ sự hỏi riêng: '{clean}' - Vấn đề gốc: '{data['problem']}'", 300, 0.85)
                results[rid] = {"type":"text","text":ans,"name":info["short_name"],"short_name":info["short_name"],"color":info["color"],"provider":info["provider_info"]["provider"]}
            return {"action":"mention","results":results}
        summary_role=next((v for v in data["roles"].values() if v.get("core_type")=="phoql"), None) or next(iter(data["roles"].values()))
        ans=await asyncio.to_thread(call_llm_real, summary_role["provider_info"], summary_role["system"], f"Chủ sự hỏi: '{clean}' - Vấn đề gốc: '{data['problem']}'", 300, 0.8)
        return {"action":"general","type":"text","name":summary_role["short_name"],"short_name":summary_role["short_name"],"color":summary_role["color"],"text":ans}
    except Exception as e:
        traceback.print_exc()
        return {"action":"general","type":"text","name":"Phó Quản Lý","short_name":"Phó Quản Lý","color":"#EF476F","text":f"Fallback: {str(e)[:100]}"}

@app.get("/admin/reload-apis")
def reload_apis():
    refresh_alive_providers()
    return {"ok":True,"alive":len(ALIVE_PROVIDERS),"providers":ALIVE_PROVIDERS}

@app.get("/admin/fix-personnel")
def fix_personnel():
    if PERSONNEL_FILE.exists():
        PERSONNEL_FILE.unlink(missing_ok=True)
    data=get_default_personnel()
    PERSONNEL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return {"ok":True,"data":data}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
