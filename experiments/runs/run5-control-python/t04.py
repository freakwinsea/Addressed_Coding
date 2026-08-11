with open('experiments/data/words.txt', 'r', encoding='utf-8') as f:
    words = f.read().split()
distinct_words = set(words)
print(len(distinct_words))
