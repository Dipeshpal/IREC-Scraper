import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field
import time
import requests
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, JSON, Date, UniqueConstraint
from tqdm import tqdm
from dotenv import load_dotenv
from datetime import date, timedelta
from sqlalchemy import and_

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
BASE_URL_SCRAPE = os.getenv('BASE_URL_SCRAPE')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
LLM_MODEL_NAME = os.getenv('LLM_MODEL_NAME')
JINA_BASE_URL = os.getenv('JINA_BASE_URL')
JINA_API_KEY = os.getenv('JINA_API_KEY')
SYSTEM_PROMPT = os.getenv('SYSTEM_PROMPT')

# Setup the database
Base = declarative_base()
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()


# Define the table schema
class DataRecord(Base):
    __tablename__ = 'data_records_table2'
    id = Column(Integer, primary_key=True, autoincrement=True)
    devices = Column(String, nullable=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    country = Column(String, nullable=False)
    issuance_history = Column(JSON, nullable=False)
    url = Column(String, nullable=False)
    today = Column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint('name', 'today', name='unique_name_today'),
    )


# Create the tables in the database
Base.metadata.create_all(engine)


def write_to_db(data):
    # Insert or update the records in the database
    for record in data:
        print("Inserting record: ", record)
        issuance_history_json = record['issuance_history']
        new_record = {
            'name': record['name'],
            'devices': record['devices'],
            'address': record['address'],
            'country': record['country'],
            'issuance_history': issuance_history_json,
            'url': record['url'],
            'today': datetime.strptime(record['today'], "%m/%d/%Y").date()
        }
        # Use SQLAlchemy's insert with on_conflict_do_update to handle upserts
        stmt = insert(DataRecord).values(new_record)
        stmt = stmt.on_conflict_do_update(
            index_elements=['name', 'today'],  # Use these columns to identify conflicts
            set_=new_record  # Update the record with the new values
        )
        session.execute(stmt)
    session.commit()
    print("Inserted to DB")


# Define your desired data structure.
class IssuanceHistory(BaseModel):
    year: str = Field(description="issuance's year")
    volume: str = Field(description="issuance's volume")
    name: str = Field(description="Name of Device")
    country: str = Field(description="Country of Device")
    address: str = Field(description="Address of Device")
    url: str = Field(description="URL of Device")
    issuance_history: str = Field(description="URL of Device")


def chat(context):
    llm = ChatGroq(
        temperature=0,
        model=LLM_MODEL_NAME,
        api_key=GROQ_API_KEY
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", "{input}")
    ])

    parser = JsonOutputParser(pydantic_object=IssuanceHistory)

    chain = prompt | llm | parser
    ans = chain.invoke({"input": f"{context}"})
    return ans


def scrape(devices):
    results = []
    count_failed = 0
    for device in tqdm(devices, desc="Scraping Devices", unit="device"):
        time.sleep(1)
        headers = {
            'Authorization': f'Bearer {JINA_API_KEY}',
        }

        response = requests.get(f'{JINA_BASE_URL}/{BASE_URL_SCRAPE}/{device}', headers=headers)
        response_text = response.text

        context = ""

        position = response_text.find('Issuance')
        if position != -1:
            context += response_text[position:]
        else:
            # count_failed += 1
            continue

        position1 = response_text.find('Device')
        position2 = response_text.find('Supported')
        if position1 != -1:
            context += response_text[position1:position2]
        else:
            context = None

        if context is not None:
            answer = chat(context=context)
        else:
            answer = {}

        data = {
            "today": (datetime.now() + timedelta(2)).strftime("%m/%d/%Y"),
            "url": f"{BASE_URL_SCRAPE}/{device}",
            "devices": device,
            "issuance_history": answer.get('issuance_history') if isinstance(answer.get('issuance_history'),
                                                                             list) else [
                answer.get('issuance_history')],
            "name": answer.get("name"),
            "country": answer.get("country"),
            "address": answer.get("address")
        }
        results.append(data)
    print("Failed: ", count_failed)
    return results


def fetch_records_by_devices(devices):
    print("Fetching records for devices:", devices)
    # Fetch records from the database based on device names
    records = session.query(DataRecord).filter(DataRecord.devices.in_(devices)).all()
    if not records:
        print("No records found for the given devices.")
    # for record in records:
    #     print(
    #         f"Fetched Record - Name: {record.name}, Address: {record.address}, Country: {record.country}, Issuance History: {record.issuance_history}, URL: {record.url}, Date: {record.today}")
    return records


def print_all_records():
    # Print all records in the database ordered by the 'today' field
    records = session.query(DataRecord).order_by(DataRecord.today).all()

    if not records:
        print("No records in the database.")
        return  # Exit the function if no records are found

    # for record in records:
        # print(
        #     f"ID: {record.id}, Name: {record.name}, Address: {record.address}, "
        #     f"Country: {record.country}, Issuance History: {record.issuance_history}, "
        #     f"URL: {record.url}, Date: {record.today}"
        # )
    return records


def fetch_records_with_issuance_history_changes(devices, days=7):
    print("Fetching records for devices with issuance history changes:", devices)

    # Define the date range for the last 7 days
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Fetch all records within the last 7 days for the specified devices
    records = session.query(DataRecord).filter(
        and_(
            DataRecord.devices.in_(devices),
            DataRecord.today >= start_date,
            DataRecord.today <= end_date
        )
    ).order_by(DataRecord.devices, DataRecord.today).all()

    # Dictionary to store the records by device
    device_records = {}

    for record in records:
        if record.devices not in device_records:
            device_records[record.devices] = []
        device_records[record.devices].append(record)

    # List to store devices with changes in the 'Issuance History'
    devices_with_changes = []

    for device, device_record_list in device_records.items():
        for i in range(1, len(device_record_list)):
            prev_record = device_record_list[i - 1]
            current_record = device_record_list[i]

            if prev_record.issuance_history != current_record.issuance_history:
                devices_with_changes.append(device)
                break

    # Collect all records for devices with changes in the 'Issuance History'
    filtered_records = []
    for device in devices_with_changes:
        filtered_records.extend(device_records[device])

    if not filtered_records:
        print("No records found with changes in issuance history in the last 7 days.")
    else:
        for record in filtered_records:
            print(
                f"Filtered Record - Name: {record.name}, Address: {record.address}, Country: {record.country}, Issuance History: {record.issuance_history}, URL: {record.url}, Date: {record.today}")

    return filtered_records


if __name__ == "__main__":
    devices = ['ADAMSOLA001']
    # results = scrape(devices)
    # write_to_db(results)
    # print("Inserted Data:")
    # print(results)

    # print("\nFetched Records:")
    # records = fetch_records_by_devices(devices)

    # print("\nAll Records in Database:")
    # print_all_records()

    print("\nFiltered Records with Issuance History Changes:")
    filtered_records = fetch_records_with_issuance_history_changes(devices, days=1)
