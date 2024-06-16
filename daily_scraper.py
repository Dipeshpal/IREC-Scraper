from runner import *
from models import DeviceRecord

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
db = Session()

records = db.query(DeviceRecord).all()
devices = [i.device for i in records]

results = scrape(devices)
write_to_db(results)
print("Inserted Data:")
print(results)
