from collections import Counter

with open('experiments/data/words.txt', 'r', encoding='utf-8') as f:
    words = f.read().split()

counts = Counter(words)
repeated = [word for word, count in counts.items() if count > 2]
for word in sorted(repeated):
    print(word)
