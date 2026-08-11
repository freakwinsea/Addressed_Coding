import csv

with open('experiments/data/inventory.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if int(row['qty']) == 0:
            print(row['name'])
