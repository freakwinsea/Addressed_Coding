with open('experiments/data/log.txt', 'r', encoding='utf-8') as f:
    count = sum(1 for line in f if 'ERROR' in line)
print(count)
