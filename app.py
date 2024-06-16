# main.py
import os
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Cookie
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, engine
from models import DeviceRecord, Base
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from runner import fetch_records_with_issuance_history_changes, scrape, write_to_db
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uuid
import json

app = FastAPI()

# Templates setup
templates = Jinja2Templates(directory="templates")

# Static files setup
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create the database tables if they don't exist
Base.metadata.create_all(bind=engine)

# Mock user database (for demonstration purposes)
users = {
    "user": {
        "username": os.getenv('USER'),
        "password": os.getenv('PASSWORD')
    }
}

# Session management (for storing logged-in users)
sessions = {}


# Authentication function
def authenticate_user(credentials: HTTPBasicCredentials = Depends(HTTPBasic())):
    user = users.get(credentials.username)
    if not user or user["password"] != credentials.password:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user["username"]


# Dependency to get current username based on session token
def get_current_username(session_token: str = Cookie(None)):
    if session_token not in sessions:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )
    return sessions[session_token]


# Login page
@app.get("/")
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def do_login(request: Request, credentials: HTTPBasicCredentials = Depends(HTTPBasic())):
    user = authenticate_user(credentials)
    if user:
        session_token = str(uuid.uuid4())
        sessions[session_token] = user
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="session_token", value=session_token)
        return response
    else:
        return templates.TemplateResponse("login.html", {"request": request, "message": "Invalid credentials"})


# Logout
@app.get("/logout")
async def logout(request: Request, session_token: str = Cookie(None)):
    if session_token in sessions:
        del sessions[session_token]
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_token")
    return response


# Root page
@app.get("/last_7_days")
async def read_root(request: Request, db: Session = Depends(get_db), username: str = Depends(get_current_username)):
    records = db.query(DeviceRecord).all()
    devices = [i.device for i in records]
    # Replace this with the actual fetching logic
    records = fetch_records_with_issuance_history_changes(devices, days=7)
    return templates.TemplateResponse("records_filtered.html", {"request": request, "records": records, "days": 7})


# Last 2 days page
@app.get("/last_2_days")
async def last_2_days(request: Request, db: Session = Depends(get_db), username: str = Depends(get_current_username)):
    records = db.query(DeviceRecord).all()
    devices = [i.device for i in records]
    records = fetch_records_with_issuance_history_changes(devices, days=2)
    return templates.TemplateResponse("records_filtered.html", {"request": request, "records": records, "days": 2})


# Form submission page
@app.get("/submit/")
async def get_form(request: Request, username: str = Depends(get_current_username)):
    return templates.TemplateResponse("submit_form.html", {"request": request})


@app.post("/submit/")
async def submit_form(request: Request,
                      device: str = Form(...),
                      name: str = Form(...),
                      metadata: Optional[str] = Form(None),
                      db: Session = Depends(get_db),
                      username: str = Depends(get_current_username)):
    # Parse the metadata as JSON if provided
    parsed_metadata = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except ValueError:
            parsed_metadata = {"error": "Invalid JSON"}

    # Create a new record
    new_record = DeviceRecord(device=device, name=name, metadata=parsed_metadata)

    # Add the record to the database
    db.add(new_record)
    db.commit()

    # Perform additional operations like scraping and writing to db
    results = scrape([device])
    write_to_db(results)

    # Redirect to a confirmation page or the home page
    return RedirectResponse(url="/submit/success", status_code=303)


# Success page after form submission
@app.get("/submit/success")
async def success_page(request: Request, username: str = Depends(get_current_username)):
    return templates.TemplateResponse("success.html", {"request": request})


# View all records API
@app.get("/records")
async def view_records(request: Request, db: Session = Depends(get_db), username: str = Depends(get_current_username)):
    records = db.query(DeviceRecord).all()
    return templates.TemplateResponse("records.html", {"request": request, "records": records})


# Delete record API
@app.delete("/delete/{record_id}")
async def delete_record(record_id: int, db: Session = Depends(get_db), request: Request = None,
                        username: str = Depends(get_current_username)):
    record = db.query(DeviceRecord).filter(DeviceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    db.delete(record)
    db.commit()

    if request:
        return templates.TemplateResponse("delete_success.html",
                                          {"request": request, "message": f"Record {record_id} deleted successfully"})
    else:
        return {"message": f"Record {record_id} deleted successfully"}
