import os
import re
import json
import shlex
import asyncio
import datetime
import argparse
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

DB_FILE = "search_history.json"

# ==============================================================================
# Job & Investigation Models
# ==============================================================================

class InvestigationJob:
    def __init__(self, job_id: int, username: str, options: Dict[str, Any], initiated_from: str = "terminal"):
        self.id = job_id
        self.username = username
        self.options = options
        self.initiated_from = initiated_from
        self.status = "queued" 
        self.created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.completed_at: Optional[str] = None
        self.total_sites = 0
        self.checked_sites = 0
        self.found_sites = 0
        self.not_found_sites = 0
        self.error_sites = 0
        self.results: List[Dict[str, Any]] = []
        self.logs: List[str] = []
        self.reports_generated: List[str] = []
        self.cancel_event = asyncio.Event()
        self.process: Optional[asyncio.subprocess.Process] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "initiated_from": self.initiated_from,
            "options": self.options,
            "found_sites": self.found_sites,
            "reports_generated": self.reports_generated
        }

    def serialize_full(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "options": self.options,
            "initiated_from": self.initiated_from,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "total_sites": self.total_sites,
            "checked_sites": self.checked_sites,
            "found_sites": self.found_sites,
            "not_found_sites": self.not_found_sites,
            "error_sites": self.error_sites,
            "results": self.results,
            "logs": self.logs,
            "reports_generated": self.reports_generated
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]):
        job = cls(data["id"], data["username"], data["options"], data["initiated_from"])
        job.status = data.get("status", "queued")
        if job.status == "running":
            job.status = "cancelled"
            job.logs.append("[!] Job was interrupted by server shutdown.")
            
        job.created_at = data.get("created_at")
        job.completed_at = data.get("completed_at")
        job.total_sites = data.get("total_sites", 0)
        job.checked_sites = data.get("checked_sites", 0)
        job.found_sites = data.get("found_sites", 0)
        job.not_found_sites = data.get("not_found_sites", 0)
        job.error_sites = data.get("error_sites", 0)
        job.results = data.get("results", [])
        job.logs = data.get("logs", [])
        job.reports_generated = data.get("reports_generated", [])
        return job

jobs_db: Dict[int, InvestigationJob] = {}
job_id_counter = 100
active_websockets: List[WebSocket] = []

# ==============================================================================
# Database Persistence Logic
# ==============================================================================

def save_db():
    try:
        data = {str(k): v.serialize_full() for k, v in jobs_db.items()}
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving DB: {e}")

def load_db():
    global job_id_counter
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                job = InvestigationJob.deserialize(v)
                jobs_db[int(k)] = job
                if int(k) >= job_id_counter:
                    job_id_counter = int(k) + 1
        except Exception as e:
            print(f"Error loading DB: {e}")

# ==============================================================================
# FastAPI Initialization & Lifespan
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    yield
    save_db()

app = FastAPI(title="Maigret OSINT Interactive Dashboard", version="3.4.0", lifespan=lifespan)

os.makedirs("static2", exist_ok=True)
os.makedirs("reports", exist_ok=True)
app.mount("/static", StaticFiles(directory="static2"), name="static")
app.mount("/reports", StaticFiles(directory="reports"), name="reports")

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

async def broadcast_message(message: Dict[str, Any]):
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

# ==============================================================================
# Custom Dossier Generator
# ==============================================================================

def generate_internal_dossier(username: str, data: Dict):
    user_data = data.get(username, {})
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Intelligence Dossier: {username}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono&display=swap');
            body {{ font-family: 'Inter', sans-serif; background: #0a0a0c; color: #e2e8f0; margin: 0; padding: 40px; }}
            .container {{ max-width: 900px; margin: auto; background: #121216; padding: 40px; border: 1px solid #B8860B; border-radius: 8px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
            h1 {{ color: #FFD700; border-bottom: 2px solid #272732; padding-bottom: 15px; text-transform: uppercase; letter-spacing: 2px; font-weight: 800; margin-top: 0; }}
            .meta-box {{ background: #18181f; border: 1px solid #272732; padding: 20px; border-radius: 6px; margin-bottom: 30px; display: flex; justify-content: space-between; }}
            .meta-box div {{ display: flex; flex-direction: column; gap: 5px; }}
            .meta-label {{ color: #718096; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }}
            .meta-value {{ color: #FFD700; font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; }}
            h2 {{ color: #fff; margin-top: 30px; font-size: 1.2rem; }}
            .site-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
            .site-card {{ background: #18181f; border-left: 4px solid #22c55e; padding: 15px; border-radius: 4px; }}
            .site-name {{ font-weight: 600; color: #fff; font-size: 1.05rem; margin-bottom: 5px; }}
            .site-url {{ color: #eab308; text-decoration: none; word-break: break-all; font-size: 0.9rem; }}
            .site-url:hover {{ text-decoration: underline; }}
            .tags {{ margin-top: 10px; font-size: 0.75rem; color: #718096; text-transform: uppercase; }}
            
            @media print {{
                body {{ background: #fff; color: #000; padding: 0; }}
                .container {{ border: none; box-shadow: none; padding: 20px; }}
                h1 {{ color: #000; border-bottom-color: #000; }}
                .meta-box {{ background: #f8f9fa; border-color: #cbd5e1; }}
                .meta-value, .site-name {{ color: #000; }}
                .site-url {{ color: #2563eb; }}
                .site-card {{ background: #fff; border: 1px solid #e2e8f0; border-left: 4px solid #22c55e; }}
                h2 {{ color: #000; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Digital Footprint Mapping</h1>
            <div class="meta-box">
                <div>
                    <span class="meta-label">Target Identity</span>
                    <span class="meta-value">{username}</span>
                </div>
                <div style="text-align: right;">
                    <span class="meta-label">Dossier Generated</span>
                    <span class="meta-value">{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
                </div>
            </div>
            <h2>Discovered Infrastructure (Returned Accounts)</h2>
            <div class="site-grid">
    """
    
    found_count = 0
    for site, details in user_data.items():
        if isinstance(details, dict) and details.get("status", "").lower() in ["claimed", "found", "true", "yes"]:
            found_count += 1
            url = details.get("url_user", "")
            tags = ", ".join(details.get("tags", []))
            html += f"""
                <div class="site-card">
                    <div class="site-name">{site}</div>
                    <a class="site-url" href="{url}" target="_blank">{url}</a>
                    <div class="tags">Categories: {tags or 'General'}</div>
                </div>
            """
            
    if found_count == 0:
        html += '<div style="color: #718096; grid-column: span 2;">No positive profile matches verified.</div>'
        
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    return html

# ==============================================================================
# Unified Search Engine Worker (Real Subprocess Execution)
# ==============================================================================

async def run_maigret_subprocess(job: InvestigationJob, cmd_args: List[str]):
    job.status = "running"
    save_db()
    await broadcast_message({"type": "job_status", "job": job.to_dict()})
    
    # Isolate this specific job into its own folder so duplicate searches are fully separated
    job_folder = f"reports/job_{job.id}"
    os.makedirs(job_folder, exist_ok=True)
    
    if "--folder" not in cmd_args:
        cmd_args.extend(["--folder", job_folder])
        
    log_header = f"[*] Engine Executing: {' '.join(cmd_args)}"
    job.logs.append(log_header)
    await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": log_header})

    try:
        job.process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=10485760 
        )

        while True:
            if job.cancel_event.is_set():
                job.process.terminate()
                job.status = "cancelled"
                cancel_msg = f"\n[!] Investigation #{job.id} halted by operator."
                job.logs.append(cancel_msg)
                await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": cancel_msg})
                break

            line_bytes = await job.process.stdout.readline()
            if not line_bytes:
                break
            
            clean_line = ANSI_ESCAPE.sub('', line_bytes.decode('utf-8', errors='replace')).rstrip('\n')
            if clean_line:
                job.logs.append(clean_line)
                
                if "FOUND" in clean_line and "NOT FOUND" not in clean_line and "Starting" not in clean_line:
                    job.found_sites += 1
                
                await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": clean_line})

        await job.process.wait()
        
        if job.status != "cancelled":
            job.status = "completed"
            
        job.completed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        potential_reports = {
            "html": f"{job_folder}/report_{job.username}.html",
            "pdf": f"{job_folder}/report_{job.username}.pdf",
            "json": f"{job_folder}/report_{job.username}.json",
            "csv": f"{job_folder}/report_{job.username}.csv",
            "txt": f"{job_folder}/report_{job.username}.txt"
        }
        for rep_type, path in potential_reports.items():
            if os.path.exists(path):
                job.reports_generated.append(rep_type)

        if job.options.get("pdf_style") == "internal" and "json" in job.reports_generated:
            json_path = f"{job_folder}/report_{job.username}.json"
            with open(json_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
            custom_html = generate_internal_dossier(job.username, report_data)
            custom_path = f"{job_folder}/report_{job.username}_internal.html"
            with open(custom_path, "w", encoding="utf-8") as f:
                f.write(custom_html)
            job.reports_generated.append("internal_html")

        completion_msg = f"\n[✓] Job #{job.id} concluded. {job.found_sites} returned accounts verified."
        job.logs.append(completion_msg)
        await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": completion_msg})
        save_db()
        await broadcast_message({"type": "job_status", "job": job.to_dict()})

    except Exception as e:
        job.status = "failed"
        err_msg = f"[!] Core Execution Error: {str(e)}"
        job.logs.append(err_msg)
        save_db()
        await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": err_msg})
        await broadcast_message({"type": "job_status", "job": job.to_dict()})

# ==============================================================================
# REST API Endpoints
# ==============================================================================

class GUIStartRequest(BaseModel):
    username: str
    tags: Optional[List[str]] = []
    timeout: Optional[int] = 15
    top_sites: Optional[int] = 500
    all_sites: Optional[bool] = False
    permute: Optional[bool] = False
    cloudflare_bypass: Optional[bool] = False
    id_type: Optional[str] = "username"
    print_mode: Optional[str] = "long"
    report_html: Optional[bool] = False
    report_pdf: Optional[bool] = False
    pdf_style: Optional[str] = "default"
    report_json: Optional[bool] = False
    report_csv: Optional[bool] = False
    report_txt: Optional[bool] = False

class CommandRequest(BaseModel):
    command: str

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join("static2", "index.html"))

@app.get("/api/overview")
async def get_overview():
    return {
        "total_searches": len(jobs_db),
        "active_tasks": sum(1 for j in jobs_db.values() if j.status == "running"),
        "total_found": sum(j.found_sites for j in jobs_db.values())
    }

@app.get("/api/history")
async def get_history():
    return [job.to_dict() for job in sorted(jobs_db.values(), key=lambda j: j.id, reverse=True)]

@app.get("/api/jobs/{job_id}")
async def get_job_detail(job_id: int):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    job = jobs_db[job_id]
    data = job.to_dict()
    data["logs"] = job.logs
    return data

@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: int):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    job = jobs_db[job_id]
    if job.status == "running":
        job.cancel_event.set()
        save_db()
        return {"status": "cancelling"}
    return {"status": "inactive"}

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    if job_id in jobs_db:
        del jobs_db[job_id]
        save_db()
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Investigation not found.")

@app.post("/api/search")
async def start_gui_search(req: GUIStartRequest):
    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    
    cmd_args = ["maigret", username]
    if req.all_sites:
        cmd_args.append("-a")
    else:
        cmd_args.extend(["--top-sites", str(req.top_sites)])
    
    if req.tags:
        cmd_args.extend(["--tags", ",".join(req.tags)])
    
    cmd_args.extend(["--timeout", str(req.timeout)])
    cmd_args.extend(["--id-type", req.id_type])
    
    if req.permute: cmd_args.append("--permute")
    if req.cloudflare_bypass: cmd_args.append("--cloudflare-bypass")
    if req.report_html: cmd_args.append("--html")
    
    if req.report_pdf:
        if req.pdf_style == "default":
            cmd_args.append("--pdf")
        elif req.pdf_style == "internal":
            req.report_json = True 

    if req.report_json: cmd_args.append("--json")
    if req.report_csv: cmd_args.append("--csv")
    if req.report_txt: cmd_args.append("--txt")

    global job_id_counter
    job_id_counter += 1
    new_job = InvestigationJob(job_id_counter, username, req.model_dump(), "gui")
    jobs_db[new_job.id] = new_job
    save_db()
    
    asyncio.create_task(run_maigret_subprocess(new_job, cmd_args))
    return {"status": "started", "job_id": new_job.id, "job": new_job.to_dict()}

class SafeParserError(Exception):
    pass

class NonExitingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise SafeParserError(message)
    def exit(self, status=0, message=None):
        if message:
            raise SafeParserError(message)

def build_maigret_parser() -> NonExitingArgumentParser:
    parser = NonExitingArgumentParser(prog="maigret", add_help=False)
    parser.add_argument("usernames", nargs="*", help="Target usernames")
    parser.add_argument("-a", "--all-sites", action="store_true")
    parser.add_argument("--tags", type=str, default="")
    parser.add_argument("--keywords", nargs="*", default=[])
    parser.add_argument("--top-sites", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--id-type", type=str, default="username")
    parser.add_argument("--permute", action="store_true")
    parser.add_argument("--cloudflare-bypass", action="store_true")
    parser.add_argument("--parse", type=str, default="")
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--txt", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return parser

maigret_cli_parser = build_maigret_parser()

@app.post("/api/terminal/execute")
async def execute_terminal_command(req: CommandRequest):
    raw_cmd = req.command.strip()
    if not raw_cmd:
        return {"output": ""}

    tokens = shlex.split(raw_cmd)
    primary = tokens[0].lower()

    blocked_commands = {"rm", "del", "powershell", "cmd", "cmd.exe", "python", "python3", "bash", "sh", "zsh", "sudo", "exec", "curl", "wget", "kill"}
    if primary in blocked_commands:
        return {"output": f"[!] Access Denied: Command '{primary}' is blocked or not recognized. Start commands with 'maigret'.\n"}

    if primary == "help":
        return {
            "output": (
                "MAIGRET DASHBOARD INTERACTIVE CONSOLE\n"
                "====================================================\n"
                "Investigation Commands:\n"
                "  maigret <user> [options]       Execute dossier investigation\n"
                "  cancel                         Halt active search\n"
                "  investigations / jobs          Display recent dossier investigations\n"
                "  open <id>                      Navigate GUI to investigation #<id>\n"
                "  status                         Show running job status\n"
                "  clear                          Clear terminal display\n"
            )
        }

    if primary in ("investigations", "jobs"):
        if not jobs_db:
            return {"output": "No investigations found.\n"}
        lines = [f"{'ID':<6} {'USERNAME':<18} {'STATUS':<12} {'FOUND':<6} {'CREATED':<20}"]
        lines.append("-" * 65)
        for j in sorted(jobs_db.values(), key=lambda x: x.id, reverse=True)[:15]:
            lines.append(f"{j.id:<6} {j.username:<18} {j.status.upper():<12} {j.found_sites:<6} {j.created_at:<20}")
        return {"output": "\n".join(lines) + "\n"}

    if primary == "status":
        running_jobs = [j for j in jobs_db.values() if j.status == "running"]
        status_txt = f"Engine Status: ONLINE\nActive Jobs: {len(running_jobs)}\n"
        if running_jobs:
            status_txt += f"Running: #{running_jobs[0].id} ({running_jobs[0].username})\n"
        return {"output": status_txt}

    if primary == "open":
        if len(tokens) < 2 or not tokens[1].isdigit():
            return {"output": "Usage: open <id>\n"}
        target_id = int(tokens[1])
        if target_id not in jobs_db:
            return {"output": f"Error: Investigation #{target_id} does not exist.\n"}
        return {"output": f"[✓] Navigating to #{target_id}...\n", "action": "open_investigation", "job_id": target_id}

    if primary == "cancel":
        running_jobs = [j for j in jobs_db.values() if j.status == "running"]
        for j in running_jobs: j.cancel_event.set()
        save_db()
        return {"output": f"[*] Cancellation signal sent.\n"}

    if primary == "maigret":
        global job_id_counter
        try:
            parsed = maigret_cli_parser.parse_args(tokens[1:])
        except SafeParserError as spe:
            return {"output": f"Parser Error: {str(spe)}\nType 'maigret --help' for syntax.\n"}

        if parsed.help:
            return {"output": maigret_cli_parser.format_help()}

        if not parsed.usernames and not parsed.parse:
            return {"output": "Error: Target username required. Usage: maigret <username> [options]\n"}

        target_user = parsed.usernames[0] if parsed.usernames else "url_target"
        
        running = [j for j in jobs_db.values() if j.status == "running"]
        if running:
            return {"output": f"[!] Search #{running[0].id} is already in progress.\n"}

        job_id_counter += 1
        new_job = InvestigationJob(job_id_counter, target_user, {"raw_cmd": raw_cmd}, "terminal")
        jobs_db[new_job.id] = new_job
        save_db()
        
        asyncio.create_task(run_maigret_subprocess(new_job, tokens))
        return {"output": f"[+] Investigation #{new_job.id} queued. Engine starting...\n", "job_id": new_job.id}

    return {"output": f"Unknown command: '{primary}'. Type 'help'.\n"}

@app.websocket("/ws/terminal")
async def websocket_terminal_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)