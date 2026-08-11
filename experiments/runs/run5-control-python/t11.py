with open('experiments/data/log.txt', 'r', encoding='utf-8') as f:
    has_hash = any(line.startswith('#') for line in f)
print('true' if has_hash else 'false')
