import os
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Cookie
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, engine
from models import DeviceRecord, Base
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from runner import fetch_records_with_issuance_history_changes, scrape, write_to_db, print_all_records
from fastapi.security import OAuth2PasswordBearer
import uuid
from daily_scraper import scrape_all
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Scraper",
              redoc_url=None,
              docs_url=None,
              )

# Templates setup
templates = Jinja2Templates(directory="templates")

# Static files setup
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create the database tables if they don't exist
Base.metadata.create_all(bind=engine)

# Mock user database (for demonstration purposes)
registered_users = {
    os.getenv('USER'): os.getenv('PASSWORD')
}

# Session management (for storing logged-in users)
sessions = {}

# OAuth2 Password Bearer token for authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


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
async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username in registered_users and registered_users[username] == password:
        session_token = str(uuid.uuid4())
        sessions[session_token] = username
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="session_token", value=session_token)
        return response
    else:
        return RedirectResponse(url="/", status_code=303)


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


@app.get("/all_records")
async def all_records(request: Request, db: Session = Depends(get_db), username: str = Depends(get_current_username)):
    records = print_all_records()
    return templates.TemplateResponse("records_filtered.html", {"request": request, "records": records, "days": 2})


# Form submission page
@app.get("/submit/")
async def get_form(request: Request):
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
    # results = scrape([device])
    # write_to_db(results)

    # Redirect to a confirmation page or the home page
    return RedirectResponse(url="/submit/success", status_code=303)


# Success page after form submission
@app.get("/submit/success")
async def success_page(request: Request):
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


@app.get("/health_check")
async def health_check(request: Request, db: Session = Depends(get_db)):
    return JSONResponse({"status": "working"})


@app.get("/scrape")
async def scrape(request: Request, db: Session = Depends(get_db)):
    res = scrape_all()
    return JSONResponse({"data": res})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
