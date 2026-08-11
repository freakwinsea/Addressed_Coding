import csv

total_value = 0
with open('experiments/data/inventory.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_value += int(row['qty']) * int(row['price_cents'])
print(total_value)
