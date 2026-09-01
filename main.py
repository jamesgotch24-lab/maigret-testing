"""FastAPI dashboard application for the Maigret search engine."""

import asyncio
import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import maigret
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select

from maigret.checking import build_cloudflare_bypass_config
from maigret.report import generate_markdown_report
from maigret.result import MaigretCheckStatus
from maigret.sites import MaigretDatabase
from maigret.settings import Settings

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static2"
DB_PATH = Path(os.getenv("MAIGRET_DASHBOARD_DB", str(ROOT / "maigret-dashboard.db")))
MAIGRET_DB = ROOT / "maigret" / "resources" / "data.json"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
logger = logging.getLogger("maigret.dashboard")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def utcnow() -> datetime:
	return datetime.now(timezone.utc).replace(tzinfo=None)


class Investigation(SQLModel, table=True):
	id: Optional[int] = Field(default=None, primary_key=True)
	title: str = Field(index=True)
	description: str = ""
	notes: str = ""
	primary_username: str = Field(default="", index=True)
	status: str = Field(default="active", index=True)
	created_at: datetime = Field(default_factory=utcnow, index=True)
	updated_at: datetime = Field(default_factory=utcnow, index=True)
	searches: list["Search"] = Relationship(back_populates="investigation", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Search(SQLModel, table=True):
	id: Optional[int] = Field(default=None, primary_key=True)
	investigation_id: int = Field(foreign_key="investigation.id", index=True)
	username: str = Field(index=True)
	options_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
	status: str = Field(default="queued", index=True)
	progress: int = 0
	total_sites: int = 0
	sites_checked: int = 0
	positive_count: int = 0
	negative_count: int = 0
	error_count: int = 0
	current_site: str = ""
	error_message: str = ""
	started_at: Optional[datetime] = None
	finished_at: Optional[datetime] = None
	created_at: datetime = Field(default_factory=utcnow, index=True)
	investigation: Optional[Investigation] = Relationship(back_populates="searches")
	results: list["Result"] = Relationship(back_populates="search", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Result(SQLModel, table=True):
	id: Optional[int] = Field(default=None, primary_key=True)
	search_id: int = Field(foreign_key="search.id", index=True)
	site_name: str = Field(index=True)
	username: str = Field(index=True)
	url: str = ""
	url_main: str = ""
	status: str = Field(index=True)
	status_text: str = ""
	http_status: Optional[int] = None
	query_time: Optional[float] = None
	rank: Optional[int] = Field(default=None, index=True)
	tags_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
	profile_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
	discovered_at: datetime = Field(default_factory=utcnow, index=True)
	search: Optional[Search] = Relationship(back_populates="results")


class DiscoveredIdentity(SQLModel, table=True):
	id: Optional[int] = Field(default=None, primary_key=True)
	search_id: int = Field(foreign_key="search.id", index=True)
	identifier: str = Field(index=True)
	identifier_type: str = "username"
	source_site: str = ""


class AnalystNote(SQLModel, table=True):
	id: Optional[int] = Field(default=None, primary_key=True)
	investigation_id: Optional[int] = Field(default=None, foreign_key="investigation.id", index=True)
	result_id: Optional[int] = Field(default=None, foreign_key="result.id", index=True)
	body: str
	created_at: datetime = Field(default_factory=utcnow)


class InvestigationCreate(BaseModel):
	title: Optional[str] = None
	description: str = ""


class SearchCreate(BaseModel):
	username: str = PydanticField(min_length=1, max_length=200)
	investigation_id: Optional[int] = None
	title: Optional[str] = None
	timeout: int = PydanticField(default=10, ge=1, le=120)
	top_sites: int = PydanticField(default=500, ge=1, le=100000)
	all_sites: bool = False
	tags: list[str] = []
	excluded_tags: list[str] = []
	site_list: list[str] = []
	recursive: bool = True
	permute: bool = False
	extract: bool = True
	keywords: list[str] = []
	check_domains: bool = False


class NoteCreate(BaseModel):
	body: str = PydanticField(min_length=1, max_length=10000)


class ResultUpdate(BaseModel):
	status_text: Optional[str] = None


def json_load(value: str, default: Any) -> Any:
	try:
		return json.loads(value)
	except (TypeError, json.JSONDecodeError):
		return default


def update_search(search_id: int, **values: Any) -> None:
	with Session(engine) as session:
		search = session.get(Search, search_id)
		if search:
			for key, value in values.items():
				setattr(search, key, value)
			session.commit()


class ProgressNotify:
	def __init__(self, search_id: int):
		self.search_id = search_id
		self.total = 0
		self.checked = 0

	def set_total(self, total: int) -> None:
		self.total = total
		update_search(self.search_id, total_sites=total)

	def set_sites(self, sites: dict[str, Any]) -> None:
		self.sites = sites

	def update(self, result: Any, is_similar: bool = False) -> None:
		self.checked += 1
		update_search(self.search_id, sites_checked=self.checked, progress=round(self.checked / self.total * 100) if self.total else 0, current_site=result.site_name)

	def start(self, *args: Any, **kwargs: Any) -> None:
		pass

	finish = warning = info = success = enrich = start


def serialize_result(result: Result) -> dict[str, Any]:
	return {"id": result.id, "site": result.site_name, "username": result.username, "url": result.url, "url_main": result.url_main, "status": result.status, "status_text": result.status_text, "http_status": result.http_status, "query_time": result.query_time, "rank": result.rank, "tags": json_load(result.tags_json, []), "profile": json_load(result.profile_json, {}), "discovered_at": result.discovered_at.isoformat()}


def serialize_search(search: Search) -> dict[str, Any]:
	return {"id": search.id, "investigation_id": search.investigation_id, "username": search.username, "options": json_load(search.options_json, {}), "status": search.status, "progress": search.progress, "total_sites": search.total_sites, "sites_checked": search.sites_checked, "positive_count": search.positive_count, "negative_count": search.negative_count, "error_count": search.error_count, "current_site": search.current_site, "error_message": search.error_message, "started_at": search.started_at.isoformat() if search.started_at else None, "finished_at": search.finished_at.isoformat() if search.finished_at else None, "created_at": search.created_at.isoformat()}


def persist_results(search_id: int, results: dict[str, Any]) -> None:
	with Session(engine) as session:
		search = session.get(Search, search_id)
		if not search:
			return
		positive = negative = errors = 0
		for site_name, item in results.items():
			status_obj = item.get("status")
			if not status_obj:
				continue
			status = status_obj.status.value if hasattr(status_obj.status, "value") else str(status_obj.status)
			site = item.get("site")
			ids = status_obj.ids_data or {}
			tags = list(getattr(status_obj, "tags", None) or getattr(site, "tags", []) or [])
			session.add(Result(search_id=search_id, site_name=site_name, username=status_obj.username or search.username, url=item.get("url_user") or status_obj.site_url_user or "", url_main=item.get("url_main") or getattr(site, "url_main", "") or "", status=status, status_text=str(status_obj), http_status=item.get("http_status") if isinstance(item.get("http_status"), int) else None, query_time=status_obj.query_time, rank=getattr(site, "alexa_rank", None), tags_json=json.dumps(tags), profile_json=json.dumps(ids, default=str)))
			if status == MaigretCheckStatus.CLAIMED.value:
				positive += 1
			elif status == MaigretCheckStatus.AVAILABLE.value:
				negative += 1
			else:
				errors += 1
			for identifier, identifier_type in (item.get("ids_usernames") or {}).items():
				session.add(DiscoveredIdentity(search_id=search_id, identifier=identifier, identifier_type=identifier_type, source_site=site_name))
		search.positive_count, search.negative_count, search.error_count = positive, negative, errors
		session.commit()


def run_maigret(search_id: int, username: str, options: dict[str, Any]) -> None:
	notify = ProgressNotify(search_id)
	update_search(search_id, status="running", started_at=utcnow())
	try:
		async def execute() -> dict[str, Any]:
			settings = Settings()
			settings.load()
			database = MaigretDatabase().load_from_path(str(MAIGRET_DB))
			top = 999999999 if options.get("all_sites") else options["top_sites"]
			sites = database.ranked_sites_dict(top=top, tags=options.get("tags", []), excluded_tags=options.get("excluded_tags", []), names=options.get("site_list", []), disabled=False, id_type="username")
			notify.set_total(len(sites))
			return await maigret.search(username=username, site_dict=sites, timeout=options["timeout"], logger=logger, id_type="username", query_notify=notify, no_progressbar=True, is_parsing_enabled=options["extract"], recursive_search_enabled=options["recursive"], check_domains=options["check_domains"], keywords=options.get("keywords") or None, cloudflare_bypass=build_cloudflare_bypass_config(settings), output_container=partial)
		results = asyncio.run(execute())
		persist_results(search_id, results)
		update_search(search_id, status="completed", progress=100, finished_at=utcnow(), current_site="")
	except Exception as exc:
		logger.exception("Dashboard search %s failed", search_id)
		if partial:
			persist_results(search_id, partial)
		update_search(search_id, status="failed", finished_at=utcnow(), error_message=str(exc))


app = FastAPI(title="Maigret Intelligence Dashboard", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
	SQLModel.metadata.create_all(engine)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
	return FileResponse(STATIC_DIR / "index.html")


app.mount("/static2", StaticFiles(directory=STATIC_DIR), name="static2")


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
	with Session(engine) as session:
		investigations = session.exec(select(Investigation)).all(); searches = session.exec(select(Search)).all(); results = session.exec(select(Result)).all()
		categories: dict[str, int] = {}
		for result in results:
			for tag in json_load(result.tags_json, []): categories[tag] = categories.get(tag, 0) + 1
		return {"metrics": {"investigations": len(investigations), "searches": len(searches), "accounts": sum(r.status == "Claimed" for r in results), "sites_checked": sum(s.sites_checked for s in searches)}, "status_distribution": {status: sum(r.status == status for r in results) for status in ["Claimed", "Available", "Unknown", "Illegal"]}, "categories": categories, "recent_investigations": [item.model_dump() for item in sorted(investigations, key=lambda x: x.updated_at, reverse=True)[:8]], "recent_searches": [serialize_search(item) for item in sorted(searches, key=lambda x: x.created_at, reverse=True)[:8]]}


@app.get("/api/investigations")
def investigations() -> list[dict[str, Any]]:
	with Session(engine) as session:
		values = session.exec(select(Investigation).order_by(Investigation.updated_at.desc())).all()
		return [{**item.model_dump(), "search_count": len(item.searches), "result_count": sum(s.positive_count for s in item.searches)} for item in values]


@app.post("/api/investigations", status_code=201)
def create_investigation(payload: InvestigationCreate) -> dict[str, Any]:
	with Session(engine) as session:
		item = Investigation(title=(payload.title or "New investigation").strip()[:200], description=payload.description); session.add(item); session.commit(); session.refresh(item); return item.model_dump()


@app.get("/api/investigations/{investigation_id}")
def investigation_detail(investigation_id: int) -> dict[str, Any]:
	with Session(engine) as session:
		item = session.get(Investigation, investigation_id)
		if not item: raise HTTPException(404, "Investigation not found")
		values = session.exec(select(Search).where(Search.investigation_id == investigation_id).order_by(Search.created_at.desc())).all()
		return {**item.model_dump(), "searches": [serialize_search(value) for value in values]}


@app.delete("/api/investigations/{investigation_id}", status_code=204)
def delete_investigation(investigation_id: int) -> None:
	with Session(engine) as session:
		item = session.get(Investigation, investigation_id)
		if not item: raise HTTPException(404, "Investigation not found")
		session.delete(item); session.commit()


@app.post("/api/search", status_code=202)
def create_search(payload: SearchCreate, background_tasks: BackgroundTasks) -> dict[str, Any]:
	username = payload.username.strip()
	if not username or any(char in username for char in "\x00\r\n"): raise HTTPException(422, "Username is invalid")
	options = payload.model_dump(exclude={"username", "investigation_id", "title"})
	with Session(engine) as session:
		investigation = session.get(Investigation, payload.investigation_id) if payload.investigation_id else None
		if not investigation:
			investigation = Investigation(title=(payload.title or f"Investigation: {username}")[:200], primary_username=username); session.add(investigation); session.flush()
		elif not investigation.primary_username: investigation.primary_username = username
		search = Search(investigation_id=investigation.id, username=username, options_json=json.dumps(options)); session.add(search); investigation.updated_at = utcnow(); session.commit(); session.refresh(search)
		background_tasks.add_task(run_maigret, search.id, username, options)
		return serialize_search(search)


@app.get("/api/searches")
def searches(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
	with Session(engine) as session: return [serialize_search(item) for item in session.exec(select(Search).order_by(Search.created_at.desc()).limit(limit)).all()]


@app.get("/api/searches/{search_id}")
def search_detail(search_id: int) -> dict[str, Any]:
	with Session(engine) as session:
		item = session.get(Search, search_id)
		if not item: raise HTTPException(404, "Search not found")
		return serialize_search(item)


@app.get("/api/searches/{search_id}/status")
def search_status(search_id: int) -> dict[str, Any]: return search_detail(search_id)


@app.get("/api/searches/{search_id}/results")
def search_results(search_id: int, status: Optional[str] = None) -> list[dict[str, Any]]:
	with Session(engine) as session:
		if not session.get(Search, search_id): raise HTTPException(404, "Search not found")
		query = select(Result).where(Result.search_id == search_id)
		if status: query = query.where(Result.status == status)
		return [serialize_result(item) for item in session.exec(query.order_by(Result.rank)).all()]


@app.get("/api/results/{result_id}")
def result_detail(result_id: int) -> dict[str, Any]:
	with Session(engine) as session:
		item = session.get(Result, result_id)
		if not item: raise HTTPException(404, "Result not found")
		identities = session.exec(select(DiscoveredIdentity).where(DiscoveredIdentity.search_id == item.search_id, DiscoveredIdentity.source_site == item.site_name)).all()
		notes = session.exec(select(AnalystNote).where(AnalystNote.result_id == result_id)).all()
		return {**serialize_result(item), "identities": [value.model_dump() for value in identities], "notes": [value.model_dump() for value in notes]}


@app.patch("/api/results/{result_id}")
def update_result(result_id: int, payload: ResultUpdate) -> dict[str, Any]:
	with Session(engine) as session:
		item = session.get(Result, result_id)
		if not item: raise HTTPException(404, "Result not found")
		if payload.status_text is not None: item.status_text = payload.status_text
		session.commit(); session.refresh(item); return serialize_result(item)


@app.post("/api/investigations/{investigation_id}/notes", status_code=201)
def add_investigation_note(investigation_id: int, payload: NoteCreate) -> dict[str, Any]:
	with Session(engine) as session:
		if not session.get(Investigation, investigation_id): raise HTTPException(404, "Investigation not found")
		note = AnalystNote(investigation_id=investigation_id, body=payload.body.strip()); session.add(note); session.commit(); session.refresh(note); return note.model_dump()


@app.post("/api/results/{result_id}/notes", status_code=201)
def add_result_note(result_id: int, payload: NoteCreate) -> dict[str, Any]:
	with Session(engine) as session:
		if not session.get(Result, result_id): raise HTTPException(404, "Result not found")
		note = AnalystNote(result_id=result_id, body=payload.body.strip()); session.add(note); session.commit(); session.refresh(note); return note.model_dump()


@app.get("/api/statistics")
def statistics() -> dict[str, Any]: return dashboard()


@app.get("/api/sites")
def sites() -> list[dict[str, Any]]:
	database = MaigretDatabase().load_from_path(str(MAIGRET_DB))
	return [{"name": site.name, "url": site.url_main, "tags": site.tags, "rank": site.alexa_rank} for site in database.ranked_sites_dict(top=100000, disabled=False, id_type="username").values()]


@app.get("/api/graph")
def graph() -> dict[str, Any]:
	with Session(engine) as session:
		searches = session.exec(select(Search)).all()
		results = session.exec(select(Result)).all()
		identities = session.exec(select(DiscoveredIdentity)).all()
		nodes = [{"id": f"search:{item.id}", "label": item.username, "type": "username"} for item in searches]
		nodes.extend({"id": f"result:{item.id}", "label": item.site_name, "type": "site", "status": item.status} for item in results if item.status == MaigretCheckStatus.CLAIMED.value)
		nodes.extend({"id": f"identity:{item.id}", "label": item.identifier, "type": item.identifier_type} for item in identities)
		edges = []
		for item in results:
			if item.status == MaigretCheckStatus.CLAIMED.value:
				edges.append({"source": f"search:{item.search_id}", "target": f"result:{item.id}"})
		for item in identities:
			edges.append({"source": f"search:{item.search_id}", "target": f"identity:{item.id}"})
		return {"nodes": nodes, "edges": edges}


@app.get("/api/searches/{search_id}/report")
def report(search_id: int, format: str = Query(default="json", pattern="^(json|csv)$")) -> Any:
	with Session(engine) as session:
		search = session.get(Search, search_id)
		if not search: raise HTTPException(404, "Search not found")
		results = session.exec(select(Result).where(Result.search_id == search_id)).all()
		if format == "json": return {"search": serialize_search(search), "results": [serialize_result(item) for item in results]}
		output = io.StringIO(); writer = csv.writer(output); writer.writerow(["site", "username", "url", "status", "http_status", "rank"])
		for item in results: writer.writerow([item.site_name, item.username, item.url, item.status, item.http_status or "", item.rank or ""])
		return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="maigret-search-{search_id}.csv"'})


if __name__ == "__main__":
	import uvicorn
	uvicorn.run("main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), reload=False)
