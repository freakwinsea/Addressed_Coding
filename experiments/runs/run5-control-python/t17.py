with open('experiments/data/words.txt', 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()
print(max(len(line) for line in lines))
