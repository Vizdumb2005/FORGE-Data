import csv
import random
from datetime import datetime, timedelta

n = 5000
categories = ['Electronics', 'Clothing', 'Home', 'Beauty', 'Sports']
regions = ['North', 'South', 'East', 'West', 'Central']

with open('synthetic_sales_data.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['TransactionID', 'TransactionDate', 'Category', 'Region', 'Price', 'Quantity', 'Revenue', 'CustomerAge', 'SatisfactionScore', 'Returned'])
    
    start_date = datetime(2023, 1, 1)
    for i in range(1, n + 1):
        t_date = start_date + timedelta(days=random.randint(0, 365), hours=random.randint(0, 23))
        cat = random.choice(categories)
        reg = random.choice(regions)
        price = round(random.uniform(10.0, 500.0), 2)
        qty = random.randint(1, 10)
        rev = round(price * qty, 2)
        age = random.randint(18, 75)
        sat = random.randint(1, 5)
        ret = random.random() < 0.05
        
        writer.writerow([f"TXN-{i:05d}", t_date.strftime("%Y-%m-%d %H:%M:%S"), cat, reg, price, qty, rev, age, sat, ret])

print("Generated synthetic_sales_data.csv successfully.")
