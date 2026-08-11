import csv

with open('experiments/data/inventory.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    items = []
    for row in reader:
        items.append(f"{row['name']} ({row['category']})")

for item in sorted(items):
    print(item)
