from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from pathlib import Path
import os, re, json, httpx

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-change-me"
    DATABASE_URL: str = "sqlite:///./careerforge.db"
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_MODEL: str = ""
    ACCESS_TOKEN_MINUTES: int = 1440
    class Config:
        env_file = ".env"

settings = Settings()
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class User(Base):
    __tablename__="users"
    id=Column(Integer, primary_key=True)
    name=Column(String(120), nullable=False)
    email=Column(String(255), unique=True, index=True, nullable=False)
    password_hash=Column(String(255), nullable=False)
    target_role=Column(String(120), default="Data Analyst")

class Resume(Base):
    __tablename__="resumes"
    id=Column(Integer, primary_key=True)
    user_id=Column(Integer, ForeignKey("users.id"), nullable=False)
    filename=Column(String(255))
    text=Column(Text, default="")
    ats_score=Column(Float, default=0)
    created_at=Column(DateTime, default=datetime.utcnow)

class Interview(Base):
    __tablename__="interviews"
    id=Column(Integer, primary_key=True)
    user_id=Column(Integer, ForeignKey("users.id"), nullable=False)
    role=Column(String(120))
    score=Column(Float)
    feedback=Column(Text)
    answers_json=Column(Text, default="[]")
    created_at=Column(DateTime, default=datetime.utcnow)

class Job(Base):
    __tablename__="jobs"
    id=Column(Integer, primary_key=True)
    title=Column(String(180))
    company=Column(String(180))
    location=Column(String(180))
    description=Column(Text)
    skills=Column(Text)

Base.metadata.create_all(engine)

def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()

def token_for(user):
    return jwt.encode({"sub":str(user.id),"exp":datetime.utcnow()+timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)}, settings.SECRET_KEY, algorithm="HS256")

def current_user(token=Depends(oauth2), s:Session=Depends(db)):
    try: uid=int(jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])["sub"])
    except (JWTError, ValueError, KeyError): raise HTTPException(401,"Invalid or expired token")
    u=s.get(User,uid)
    if not u: raise HTTPException(401,"User not found")
    return u

class Register(BaseModel):
    name:str
    email:EmailStr
    password:str

class Login(BaseModel):
    email:EmailStr
    password:str

class InterviewRequest(BaseModel):
    role:str="Data Analyst"
    difficulty:str="Medium"
    type:str="Technical + HR"

class EvaluationRequest(BaseModel):
    role:str
    question:str
    answer:str

app=FastAPI(title="CareerForge AI API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def seed():
    s=SessionLocal()
    if s.query(Job).count()==0:
        jobs=[
            ("Junior Data Analyst","InsightWorks","Pune · Hybrid","Analyze business data and build reports.","SQL,Excel,Power BI"),
            ("Data Analyst Intern","AnalyticsNest","Remote · India","Support data cleaning, dashboards and analysis.","Python,SQL,Tableau"),
            ("Business Intelligence Analyst","NovaData","Pune · On-site","Create BI dashboards and KPI reporting.","Power BI,SQL,DAX"),
            ("Data Operations Analyst","DataX Labs","Mumbai · Hybrid","Maintain data quality and operational reporting.","Excel,SQL,Python"),
            ("Junior Data Scientist","ModelMint","Bengaluru · Hybrid","Build analytical and machine-learning solutions.","Python,Statistics,Machine Learning")
        ]
        for j in jobs:s.add(Job(title=j[0],company=j[1],location=j[2],description=j[3],skills=j[4]))
        s.commit()
    s.close()
seed()

def keywords_score(text):
    keys=["sql","python","excel","power bi","statistics","project","education","skills","communication","data"]
    low=text.lower()
    hits=sum(k in low for k in keys)
    return min(98, round(55+hits*4.3,1))

async def ai_json(system,prompt):
    if not (settings.AI_API_KEY and settings.AI_BASE_URL and settings.AI_MODEL):
        return None
    url=settings.AI_BASE_URL.rstrip("/")+"/chat/completions"
    headers={"Authorization":f"Bearer {settings.AI_API_KEY}","Content-Type":"application/json"}
    body={"model":settings.AI_MODEL,"temperature":0.4,"response_format":{"type":"json_object"},
          "messages":[{"role":"system","content":system},{"role":"user","content":prompt}]}
    async with httpx.AsyncClient(timeout=60) as c:
        r=await c.post(url,headers=headers,json=body); r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

@app.get("/api/health")
def health(): return {"ok":True,"ai_enabled":bool(settings.AI_API_KEY and settings.AI_BASE_URL and settings.AI_MODEL)}

@app.post("/api/auth/register")
def register(x:Register,s:Session=Depends(db)):
    if s.query(User).filter_by(email=x.email.lower()).first(): raise HTTPException(409,"Email already registered")
    if len(x.password)<6: raise HTTPException(400,"Password must be at least 6 characters")
    u=User(name=x.name,email=x.email.lower(),password_hash=pwd.hash(x.password))
    s.add(u);s.commit();s.refresh(u)
    return {"token":token_for(u),"user":{"id":u.id,"name":u.name,"email":u.email,"target_role":u.target_role}}

@app.post("/api/auth/login")
def login(x:Login,s:Session=Depends(db)):
    u=s.query(User).filter_by(email=x.email.lower()).first()
    if not u or not pwd.verify(x.password,u.password_hash): raise HTTPException(401,"Incorrect email or password")
    return {"token":token_for(u),"user":{"id":u.id,"name":u.name,"email":u.email,"target_role":u.target_role}}

@app.get("/api/me")
def me(u=Depends(current_user)): return {"id":u.id,"name":u.name,"email":u.email,"target_role":u.target_role}

@app.post("/api/resume/analyze")
async def resume(file:UploadFile=File(...),u=Depends(current_user),s:Session=Depends(db)):
    data=await file.read()
    text=""
    name=file.filename or "resume"
    try:
        if name.lower().endswith(".pdf"):
            from pypdf import PdfReader
            import io
            text="\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        elif name.lower().endswith(".docx"):
            from docx import Document
            import io
            text="\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        else:
            text=data.decode("utf-8","ignore")
    except Exception as e: raise HTTPException(400,f"Could not parse document: {e}")
    if len(text.strip())<20: raise HTTPException(400,"No readable text found in resume")
    score=keywords_score(text)
    r=Resume(user_id=u.id,filename=name,text=text[:50000],ats_score=score);s.add(r);s.commit()
    return {"filename":name,"ats_score":score,"strengths":["Education/skills are detected","Projects can support the target role","Technical keywords are present"],"improvements":["Quantify project outcomes","Add missing role-specific keywords","Use stronger action verbs"],"text_preview":text[:1000]}

@app.post("/api/interview/questions")
async def questions(x:InterviewRequest,u=Depends(current_user)):
    system="You are an expert technical recruiter. Return JSON only."
    prompt=f"Create 5 interview questions for role={x.role}, difficulty={x.difficulty}, type={x.type}. Return {{\"questions\":[{{\"question\":\"...\",\"category\":\"...\"}}]}}."
    raw=await ai_json(system,prompt)
    if raw:
        try:return json.loads(raw)
        except: pass
    fallback={
      "Data Analyst":["Tell me about yourself and why you want to become a Data Analyst.","Explain WHERE vs HAVING in SQL.","How would you investigate a 30% sales drop?","What is an outlier and how would you handle it?","Describe a data project and its impact."],
      "Software Developer":["Tell me about yourself.","Explain OOP principles.","How do you debug a slow application?","Process vs thread?","Describe a project you built."],
      "UI/UX Designer":["Tell me about your design process.","How do you conduct user research?","UX vs UI?","How do you handle feedback?","Walk through a portfolio project."]
    }.get(x.role,["Tell me about yourself.","What are your strongest skills?","Describe a difficult problem you solved.","How do you learn new technology?","Why are you a good fit for this role?"])
    return {"questions":[{"question":q,"category":"General"} for q in fallback]}

@app.post("/api/interview/evaluate")
async def evaluate(x:EvaluationRequest,u=Depends(current_user),s:Session=Depends(db)):
    system="You are an expert interview evaluator. Return JSON only with score (0-100), strengths (array), improvements (array), feedback (string)."
    prompt=f"Role: {x.role}\nQuestion: {x.question}\nCandidate answer: {x.answer}\nEvaluate relevance, accuracy, structure, clarity and examples."
    raw=await ai_json(system,prompt)
    if raw:
        try:return json.loads(raw)
        except: pass
    words=len(x.answer.split())
    sc=45 if words<10 else 65 if words<25 else 78 if words<45 else 86
    if re.search(r"example|project|result|sql|python|power bi",x.answer,re.I): sc=min(96,sc+6)
    return {"score":sc,"strengths":["Answer addresses the question","Shows practical thinking"],"improvements":["Add a concrete example","Quantify the result where possible"],"feedback":"Good foundation. Make the answer more specific and measurable."}

@app.post("/api/interview/complete")
def complete(payload:dict,u=Depends(current_user),s:Session=Depends(db)):
    score=float(payload.get("score",0)); role=payload.get("role","Data Analyst")
    i=Interview(user_id=u.id,role=role,score=score,feedback=payload.get("feedback",""),answers_json=json.dumps(payload.get("answers",[])))
    s.add(i);s.commit();s.refresh(i);return {"id":i.id,"score":i.score}

@app.get("/api/interviews")
def history(u=Depends(current_user),s:Session=Depends(db)):
    return [{"id":i.id,"role":i.role,"score":i.score,"date":i.created_at.isoformat()} for i in s.query(Interview).filter_by(user_id=u.id).order_by(Interview.created_at.desc()).limit(20)]

@app.get("/api/jobs")
def jobs(q:str="",u=Depends(current_user),s:Session=Depends(db)):
    rows=s.query(Job).all(); out=[]
    resume=s.query(Resume).filter_by(user_id=u.id).order_by(Resume.created_at.desc()).first()
    text=(resume.text if resume else "").lower()
    for j in rows:
        skills=[x.strip() for x in j.skills.split(",")]
        hits=sum(x.lower() in text for x in skills)
        match=min(97,60+hits*10)
        if q and q.lower() not in (j.title+" "+j.company+" "+j.skills).lower():continue
        out.append({"id":j.id,"title":j.title,"company":j.company,"location":j.location,"description":j.description,"skills":skills,"match":match})
    return sorted(out,key=lambda x:x["match"],reverse=True)

@app.get("/api/skill-gap")
def skillgap(role:str="Data Analyst",u=Depends(current_user),s:Session=Depends(db)):
    resume=s.query(Resume).filter_by(user_id=u.id).order_by(Resume.created_at.desc()).first()
    text=(resume.text if resume else "").lower()
    role_skills={"Data Analyst":["SQL","Excel","Python","Power BI","Statistics"],"Software Developer":["Python","Java","Git","APIs","DSA"],"UI/UX Designer":["Figma","UX Research","Wireframing","Prototyping","Design Systems"]}.get(role,["Communication","Problem Solving","Technical Skills"])
    result=[]
    for skill in role_skills:
        score=90 if skill.lower() in text else 45
        result.append({"skill":skill,"score":score,"priority":"Strong" if score>=80 else "Priority"})
    return {"role":role,"skills":result}

@app.get("/")
def root(): return FileResponse(ROOT/"frontend/index.html")

app.mount("/static",StaticFiles(directory=ROOT/"frontend"),name="static")
