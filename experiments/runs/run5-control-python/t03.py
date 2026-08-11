with open('experiments/data/words.txt', 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()
for line in reversed(lines):
    print(line)
