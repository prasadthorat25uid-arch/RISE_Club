import os, sqlite3, secrets, hashlib, hmac, base64, json, csv, io, smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

BASE = Path(__file__).resolve().parent
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./rise.db")
if DB_URL.startswith("sqlite:///"):
    DB_PATH = BASE / DB_URL.replace("sqlite:///", "")
else:
    raise RuntimeError("This packaged build uses SQLite by default. For PostgreSQL, adapt DATABASE_URL support or use the provided schema.")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = BASE / "private_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
SECRET = os.getenv("SECRET_KEY", "dev-only-change-me")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = 7

app = FastAPI(title="RISE Club Portal API", version="1.0.0")


def now(): return datetime.now(timezone.utc).isoformat()

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def hash_password(p: str, salt: Optional[bytes] = None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1)
    return base64.urlsafe_b64encode(salt + digest).decode()

def verify_password(p, encoded):
    try:
        raw = base64.urlsafe_b64decode(encoded.encode()); salt, expected = raw[:16], raw[16:]
        actual = hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except Exception: return False

def init_db():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('member','lead','mentor','admin','superadmin')),
      department TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active', password_hash TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, programme TEXT,
      domain TEXT, why TEXT, status TEXT DEFAULT 'Pending', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ideas(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, domain TEXT, status TEXT,
      owner_id INTEGER, statement TEXT, impact TEXT, created_at TEXT NOT NULL, FOREIGN KEY(owner_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, project TEXT, priority TEXT,
      deadline TEXT, status TEXT DEFAULT 'To Do', assigned_to INTEGER, created_at TEXT NOT NULL, FOREIGN KEY(assigned_to) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, priority TEXT,
      audience TEXT, message TEXT, published_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, date_time TEXT, venue TEXT,
      limit_count INTEGER DEFAULT 0, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, actor TEXT, action TEXT);
    CREATE TABLE IF NOT EXISTS uploads(id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, filename TEXT, stored_name TEXT,
      content_type TEXT, created_at TEXT NOT NULL, FOREIGN KEY(owner_id) REFERENCES users(id));
    ''')
    admin_email=os.getenv('ADMIN_EMAIL','admin@localhost').lower().strip()
    if not c.execute('SELECT id FROM users WHERE email=?',(admin_email,)).fetchone():
        c.execute('INSERT INTO users(name,email,role,status,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
          (os.getenv('ADMIN_NAME','RISE Office'),admin_email,'admin','active',hash_password(os.getenv('ADMIN_PASSWORD','ChangeMe123!')),now(),now()))
        audit(c, os.getenv('ADMIN_NAME','RISE Office'), 'Created initial administrator account')
    if c.execute('SELECT COUNT(*) n FROM announcements').fetchone()['n']==0:
        for x in [('Research Ethics orientation','Important','All members','Orientation session'),('Registration open: AI workshop','Normal','AI & ML domain','Registration is open'),('Project milestone reviews','Urgent','Project leads','Milestone reviews are scheduled'),('New IEEE paper call','Normal','Research groups','New call for papers')]:
            c.execute('INSERT INTO announcements(title,priority,audience,message,published_at) VALUES(?,?,?,?,?)',(*x,now()))
    c.commit(); c.close()

def audit(c, actor, action): c.execute('INSERT INTO audit(timestamp,actor,action) VALUES(?,?,?)',(now(),actor,action))

def current_user(request: Request):
    sid=request.cookies.get('rise_session')
    if not sid: raise HTTPException(401,'Authentication required')
    c=db(); row=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=? AND s.expires_at>?',(sid,now())).fetchone(); c.close()
    if not row or row['status']!='active': raise HTTPException(401,'Session expired or account disabled')
    return dict(row)

def require_roles(user, *roles):
    if user['role'] not in roles: raise HTTPException(403,'Insufficient permissions')

def send_email(to, subject, body):
    host=os.getenv('SMTP_HOST'); user=os.getenv('SMTP_USERNAME'); pw=os.getenv('SMTP_PASSWORD')
    if not host: return False
    msg=EmailMessage(); msg['Subject']=subject; msg['From']=os.getenv('SMTP_FROM','RISE Club'); msg['To']=to; msg.set_content(body)
    port=int(os.getenv('SMTP_PORT','587'))
    with smtplib.SMTP(host,port,timeout=20) as s:
        if os.getenv('SMTP_TLS','true').lower()=='true': s.starttls()
        if user: s.login(user,pw)
        s.send_message(msg)
    return True

class Login(BaseModel): email: EmailStr; password: str
class MemberIn(BaseModel): name: str; email: EmailStr; department: str=''; role: str='member'
class ApplicationIn(BaseModel): name: str; email: EmailStr; domain: str; why: str; programme: str=''
class IdeaIn(BaseModel): title: str; domain: str; statement: str=''; impact: str=''
class TaskIn(BaseModel): title: str; project: str=''; priority: str='Medium'; deadline: str=''; assigned_to: Optional[int]=None
class AnnouncementIn(BaseModel): title: str; priority: str='Normal'; audience: str='All members'; message: str=''
class EventIn(BaseModel): title: str; date_time: str; venue: str=''; limit_count: int=0
class StatusIn(BaseModel): status: str

@app.on_event('startup')
def startup(): init_db()

@app.get('/api/health')
def health(): return {'ok':True,'service':'RISE Club Portal'}

@app.post('/api/login')
def login(data: Login, response: JSONResponse):
    c=db(); u=c.execute('SELECT * FROM users WHERE email=?',(str(data.email).lower(),)).fetchone()
    if not u or not u['password_hash'] or not verify_password(data.password,u['password_hash']): c.close(); raise HTTPException(401,'Invalid email or password')
    if u['status']!='active': c.close(); raise HTTPException(403,'Your account is disabled. Contact RISE administration.')
    sid=secrets.token_urlsafe(32); exp=(datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)).isoformat()
    c.execute('INSERT INTO sessions(id,user_id,expires_at) VALUES(?,?,?)',(sid,u['id'],exp)); audit(c,u['name'],'Signed in'); c.commit(); c.close()
    out=JSONResponse({'ok':True,'user':{k:u[k] for k in ['id','name','email','role','department','status']}})
    out.set_cookie('rise_session',sid,max_age=SESSION_DAYS*86400,httponly=True,samesite='lax',secure=COOKIE_SECURE,path='/')
    return out

@app.post('/api/logout')
def logout(request: Request):
    sid=request.cookies.get('rise_session'); out=JSONResponse({'ok':True})
    if sid:
        c=db(); c.execute('DELETE FROM sessions WHERE id=?',(sid,)); c.commit(); c.close()
    out.delete_cookie('rise_session',path='/'); return out

@app.get('/api/me')
def me(request: Request):
    u=current_user(request); return {'user':{k:u[k] for k in ['id','name','email','role','department','status']}}

@app.get('/api/state')
def state(request: Request):
    u=current_user(request); c=db()
    members=c.execute('SELECT id,name,department,role,status,email FROM users ORDER BY name').fetchall()
    apps=c.execute('SELECT id,name,programme,domain,status,email,why,created_at FROM applications ORDER BY id DESC').fetchall()
    ideas=c.execute('SELECT i.id,i.title,i.domain,i.status,COALESCE(u.name,"Unknown") owner FROM ideas i LEFT JOIN users u ON u.id=i.owner_id ORDER BY i.id DESC').fetchall()
    if u['role'] in ('member','lead'):
        tasks=c.execute('SELECT t.id,t.title,t.project,t.priority,t.deadline,t.status,t.assigned_to FROM tasks t WHERE t.assigned_to=? OR t.assigned_to IS NULL ORDER BY t.id DESC',(u['id'],)).fetchall()
    else: tasks=c.execute('SELECT id,title,project,priority,deadline,status,assigned_to FROM tasks ORDER BY id DESC').fetchall()
    anns=c.execute('SELECT id,title,priority,audience,published_at,message FROM announcements ORDER BY id DESC').fetchall()
    events=c.execute('SELECT * FROM events ORDER BY id DESC').fetchall()
    auditrows=c.execute('SELECT timestamp,actor,action FROM audit ORDER BY id DESC LIMIT 100').fetchall() if u['role'] in ('admin','superadmin') else []
    c.close()
    return {'user':{k:u[k] for k in ['id','name','email','role','department','status']},'members':[dict(x) for x in members] if u['role'] in ('admin','superadmin') else [],'applications':[dict(x) for x in apps] if u['role'] in ('admin','superadmin') else [],'ideas':[dict(x) for x in ideas],'tasks':[dict(x) for x in tasks],'announcements':[dict(x) for x in anns],'events':[dict(x) for x in events],'audit':[dict(x) for x in auditrows]}

@app.post('/api/applications')
def application(data: ApplicationIn):
    c=db(); c.execute('INSERT INTO applications(name,email,programme,domain,why,status,created_at) VALUES(?,?,?,?,?,?,?)',(data.name,data.email,data.programme,data.domain,data.why,'Pending',now())); c.commit(); c.close()
    try: send_email(data.email,'RISE application received',f'Hello {data.name},\n\nYour RISE Club application has been received. The RISE team will review it and contact you.')
    except Exception: pass
    return {'ok':True,'message':'Application received. The RISE team will contact you by email.'}

@app.post('/api/members')
def create_member(data: MemberIn, request: Request):
    u=current_user(request); require_roles(u,'admin','superadmin')
    if data.role not in ('member','lead','mentor'): raise HTTPException(400,'Invalid member role')
    temp=secrets.token_urlsafe(9)
    c=db()
    try:
        c.execute('INSERT INTO users(name,email,department,role,status,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(data.name,str(data.email).lower(),data.department,data.role,'active',hash_password(temp),now(),now()))
        audit(c,u['name'],f'Created {data.role} account for {data.email}'); c.commit()
    except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'An account with this email already exists')
    c.close()
    base=os.getenv('PUBLIC_BASE_URL','http://localhost:8000')
    sent=False
    try: sent=send_email(str(data.email),'Your RISE Club account',f'Hello {data.name},\n\nAn RISE Club account was created for you by an administrator.\n\nLogin: {base}/portal.html\nEmail: {data.email}\nTemporary password: {temp}\n\nPlease change this password after signing in.')
    except Exception: pass
    return {'ok':True,'email_sent':sent,'message':'Account created and invitation email sent.' if sent else 'Account created. Configure SMTP to send invitation emails automatically.'}

@app.patch('/api/members/{member_id}')
def update_member(member_id:int,data:StatusIn,request:Request):
    u=current_user(request); require_roles(u,'admin','superadmin')
    if data.status not in ('active','disabled'): raise HTTPException(400,'Status must be active or disabled')
    c=db(); row=c.execute('SELECT * FROM users WHERE id=?',(member_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404,'Member not found')
    c.execute('UPDATE users SET status=?,updated_at=? WHERE id=?',(data.status,now(),member_id)); c.execute('DELETE FROM sessions WHERE user_id=?',(member_id,)); audit(c,u['name'],f'Set {row["email"]} status to {data.status}'); c.commit(); c.close()
    return {'ok':True}

@app.post('/api/ideas')
def idea(data:IdeaIn,request:Request):
    u=current_user(request); c=db(); c.execute('INSERT INTO ideas(title,domain,status,owner_id,statement,impact,created_at) VALUES(?,?,?,?,?,?,?)',(data.title,data.domain,'Submitted',u['id'],data.statement,data.impact,now())); audit(c,u['name'],f'Submitted research idea: {data.title}'); c.commit(); c.close(); return {'ok':True}

@app.post('/api/tasks')
def task(data:TaskIn,request:Request):
    u=current_user(request); require_roles(u,'admin','superadmin','lead'); c=db(); c.execute('INSERT INTO tasks(title,project,priority,deadline,status,assigned_to,created_at) VALUES(?,?,?,?,?,?,?)',(data.title,data.project,data.priority,data.deadline,'To Do',data.assigned_to,now())); audit(c,u['name'],f'Created task: {data.title}'); c.commit(); c.close(); return {'ok':True}

@app.patch('/api/tasks/{task_id}')
def task_status(task_id:int,data:StatusIn,request:Request):
    u=current_user(request); c=db(); row=c.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404,'Task not found')
    if u['role'] in ('member','lead') and row['assigned_to'] not in (u['id'],None): c.close(); raise HTTPException(403,'Not your task')
    c.execute('UPDATE tasks SET status=? WHERE id=?',(data.status,task_id)); audit(c,u['name'],f'Updated task {task_id} to {data.status}'); c.commit(); c.close(); return {'ok':True}

@app.post('/api/announcements')
def announcement(data:AnnouncementIn,request:Request):
    u=current_user(request); require_roles(u,'admin','superadmin'); c=db(); c.execute('INSERT INTO announcements(title,priority,audience,message,published_at) VALUES(?,?,?,?,?)',(data.title,data.priority,data.audience,data.message,now())); audit(c,u['name'],f'Published announcement: {data.title}'); c.commit(); c.close(); return {'ok':True}

@app.post('/api/events')
def event(data:EventIn,request:Request):
    u=current_user(request); require_roles(u,'admin','superadmin','lead'); c=db(); c.execute('INSERT INTO events(title,date_time,venue,limit_count,created_at) VALUES(?,?,?,?,?)',(data.title,data.date_time,data.venue,data.limit_count,now())); audit(c,u['name'],f'Created event: {data.title}'); c.commit(); c.close(); return {'ok':True}

@app.post('/api/uploads')
def upload(request:Request,file:UploadFile=File(...)):
    u=current_user(request); raw=secrets.token_hex(16)+'_'+Path(file.filename or 'file').name
    path=UPLOAD_DIR/raw
    with open(path,'wb') as f: f.write(file.file.read())
    c=db(); c.execute('INSERT INTO uploads(owner_id,filename,stored_name,content_type,created_at) VALUES(?,?,?,?,?)',(u['id'],file.filename,raw,file.content_type or 'application/octet-stream',now())); audit(c,u['name'],f'Uploaded file: {file.filename}'); c.commit(); c.close()
    return {'ok':True,'filename':file.filename}

@app.get('/api/reports/{kind}.csv')
def report(kind:str,request:Request):
    u=current_user(request); require_roles(u,'admin','superadmin'); c=db()
    maps={'members':('SELECT name,email,department,role,status,created_at FROM users',), 'applications':('SELECT name,email,programme,domain,status,created_at FROM applications',), 'tasks':('SELECT title,project,priority,deadline,status,assigned_to,created_at FROM tasks',), 'audit':('SELECT timestamp,actor,action FROM audit',)}
    if kind not in maps: c.close(); raise HTTPException(404,'Unknown report')
    rows=c.execute(maps[kind][0]).fetchall(); c.close(); out=io.StringIO(); w=csv.writer(out)
    if rows: w.writerow(rows[0].keys()); [w.writerow(list(r)) for r in rows]
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename=rise-{kind}.csv'})

@app.get('/portal.html')
def portal(): return FileResponse(BASE/'portal.html')
@app.get('/')
def root(): return FileResponse(BASE/'index.html')
app.mount('/', StaticFiles(directory=BASE, html=False), name='static')
