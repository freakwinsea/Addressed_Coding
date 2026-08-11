import csv

rows_written = 0
with open('experiments/data/inventory.csv', 'r', encoding='utf-8') as fin:
    reader = csv.DictReader(fin)
    with open('experiments/out/restock.csv', 'w', encoding='utf-8', newline='') as fout:
        writer = csv.DictWriter(fout, fieldnames=['name', 'qty'])
        writer.writeheader()
        for row in reader:
            if int(row['qty']) > 10:
                writer.writerow({'name': row['name'], 'qty': row['qty']})
                rows_written += 1
print(rows_written)
