import csv

with open('experiments/data/inventory.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    categories = set(row['category'] for row in reader)

for category in sorted(categories):
    print(category)
