import pandas as pd
import qrcode
import random
import string
from faker import Faker
from datetime import datetime, timedelta
import os

fake = Faker()
os.makedirs("qrcodes", exist_ok=True)

def rand_qr_id():
    return "QR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def rand_date():
    start = datetime(2022, 1, 1)
    return (start + timedelta(days=random.randint(0, 900))).strftime("%Y-%m-%d")

statuses = ["Verified", "Pending", "Rejected"]
items = []
qr_ids = set()

for i in range(1, 101):
    qr_id = rand_qr_id()
    while qr_id in qr_ids:
        qr_id = rand_qr_id()
    qr_ids.add(qr_id)

    items.append({
        "Serial Number": f"SN-{i:04d}",
        "Item Name": fake.unique.bs().title() + f" {random.randint(100,999)}",
        "Description": fake.sentence(nb_words=12),
        "Value": f"₹{random.randint(1500, 95000):,}",
        "Verification Status": random.choice(statuses),
        "Varied Date": rand_date(),
        "QR Code ID": qr_id
    })

    qr = qrcode.make(qr_id)
    qr.save(f"qrcodes/{qr_id}.png")

df = pd.DataFrame(items)
df.to_excel("inventory.xlsx", index=False)
print("Done! inventory.xlsx and 100 QR codes generated.")